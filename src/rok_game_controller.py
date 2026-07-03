#!/usr/bin/env python3
"""
RoK Game Controller - Main orchestrator for Rise of Kingdoms automation.

This is the main controller that coordinates game lifecycle and
delegates specific automation tasks to specialized classes.
"""
import time
import logging
import subprocess

import timings
from automation_base import DialogCloserMixin
from coordinate_manager import CoordinateManager
from ocr_helper import OCRHelper
from screen_detector import ScreenDetector
from navigation_helper import VerifiedNavigator
from build_automation import BuildAutomation
from donation_automation import DonationAutomation
from expedition_automation import ExpeditionAutomation
from character_switcher import CharacterSwitcher
from account_switcher import AccountSwitcher
from recovery_manager import RecoveryManager


class RoKGameController(DialogCloserMixin):
    """Controller for Rise of Kingdoms game operations."""

    STOP_CONTEXT = "RoK operation"

    def __init__(self, config_manager, bluestacks_controller,
                 daily_task_tracker=None, force_daily_tasks=False):
        """
        Initialize the RoK game controller.

        Args:
            config_manager: ConfigManager instance
            bluestacks_controller: BlueStacksController instance
            daily_task_tracker: Optional DailyTaskTracker for tracking daily task completion
            force_daily_tasks: If True, run daily tasks even if already completed today
        """
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.bluestacks = bluestacks_controller
        self.stop_check_callback = None
        self.daily_task_tracker = daily_task_tracker
        self.force_daily_tasks = force_daily_tasks

        # Apply any [Timings] overrides from config.ini. Safe to call more
        # than once (e.g. also called earlier by the multi-instance launcher).
        timings.load_overrides(config_manager)

        # Load RoK configurations
        rok_config = config_manager.get_rok_config()
        self.rok_version = rok_config.get('rok_version', 'global').lower()

        # Load bluestacks configuration
        bluestacks_config = config_manager.get_bluestacks_config()
        # Use game_load_wait_seconds from RoK config (for character switch), default 30s
        # Enforce minimum of 30s to ensure game has enough time to load
        self.game_load_wait_seconds = max(30, int(rok_config.get('game_load_wait_seconds', 30)))
        self.debug_mode = bool(bluestacks_config.get('debug_mode', False))

        # Set package name based on version
        self.package_name = 'com.lilithgame.roc.gp'
        match self.rok_version:
            case 'global':
                self.package_name = 'com.lilithgame.roc.gp'
            case 'kr':
                self.package_name = 'com.lilithgames.rok.gpkr'
            case 'gamota':
                self.package_name = 'com.rok.gp.vn'
        self.activity_name = rok_config.get('activity_name')

        # Load coordinates from centralized JSON config
        self.coords = CoordinateManager()

        # Navigation coordinates for game lifecycle
        self.map_button = self.coords.get_nav('map_button')

        # Click delay
        nav_config = config_manager.get_navigation_config()
        self.click_delay_ms = int(nav_config.get('click_delay_ms', 1000))

        # Initialize component classes
        self.ocr = OCRHelper(
            self.bluestacks,
            self.coords,
            self.config,
            stop_check_callback=lambda: self.stop_check_callback and self.stop_check_callback(),
            debug_mode=self.debug_mode
        )
        self.screen = ScreenDetector(
            self.ocr,
            self.coords,
            stop_check_callback=self.ocr.check_stop_requested
        )
        self.navigator = VerifiedNavigator(
            self.ocr,
            self.screen,
            self.bluestacks,
            self.coords,
            click_delay_ms=self.click_delay_ms,
            stop_check_callback=self.ocr.check_stop_requested
        )
        self.build = BuildAutomation(
            self.ocr,
            self.screen,
            self.bluestacks,
            self.coords,
            self.navigator,
            click_delay_ms=self.click_delay_ms,
            stop_check_callback=self.ocr.check_stop_requested
        )
        self.donation = DonationAutomation(
            self.ocr,
            self.screen,
            self.bluestacks,
            self.coords,
            self.navigator,
            click_delay_ms=self.click_delay_ms,
            stop_check_callback=self.ocr.check_stop_requested
        )
        self.recovery = RecoveryManager(
            self.screen,
            self.bluestacks,
            self.coords,
            click_delay_ms=self.click_delay_ms,
            stop_check_callback=self.ocr.check_stop_requested
        )
        self.expedition = ExpeditionAutomation(
            self.ocr,
            self.screen,
            self.bluestacks,
            self.coords,
            self.navigator,
            click_delay_ms=self.click_delay_ms,
            stop_check_callback=self.ocr.check_stop_requested
        )
        self.character_switcher = CharacterSwitcher(
            self.bluestacks,
            self.coords,
            self.screen,
            self.build,
            self.donation,
            self.expedition,
            self.recovery,
            self.navigator,
            num_of_chars=int(rok_config.get('num_of_characters', 1)),
            march_preset=int(rok_config.get('march_preset', 1)),
            click_delay_ms=self.click_delay_ms,
            character_login_loading_time=int(rok_config.get('character_login_screen_loading_time', 3)),
            game_load_wait_seconds=self.game_load_wait_seconds,
            will_perform_build=config_manager.get_bool('RiseOfKingdoms', 'perform_build', True),
            will_perform_donation=config_manager.get_bool('RiseOfKingdoms', 'perform_donation', True),
            will_perform_expedition=config_manager.get_bool('RiseOfKingdoms', 'perform_expedition', True),
            stop_check_callback=self.ocr.check_stop_requested,
            navigate_to_map_callback=self.navigate_to_map,
            daily_task_tracker=self.daily_task_tracker,
            force_daily_tasks=self.force_daily_tasks
        )
        self.account_switcher = AccountSwitcher(
            self.ocr,
            self.screen,
            self.bluestacks,
            self.coords,
            self.navigator,
            self.recovery,
            click_delay_ms=self.click_delay_ms,
            game_load_wait_seconds=max(60, self.game_load_wait_seconds),
            stop_check_callback=self.ocr.check_stop_requested
        )
        # Accounts configured for account rotation ([Accounts] in config.ini)
        self.accounts = AccountSwitcher.parse_accounts(config_manager)

    @property
    def stop_check_callback(self):
        """Public name for the stop callback (the GUI/launcher set this);
        aliased to self.stop_check, which the shared mixin reads."""
        return self.stop_check

    @stop_check_callback.setter
    def stop_check_callback(self, value):
        self.stop_check = value

    def is_rok_process_running(self):
        """Check whether the RoK process is actually running on the device.

        Used as a fallback check because "am start" can report a transport
        error (e.g. "error: closed") on the response channel even when the
        activity itself launched successfully.
        """
        try:
            check_cmd = [
                self.bluestacks.adb_path, "-s", self.bluestacks.adb_device,
                "shell", "pidof", self.package_name
            ]
            result = subprocess.run(check_cmd, capture_output=True, text=True,
                                    timeout=15)
            return bool(result.stdout.strip())
        except subprocess.TimeoutExpired:
            self.logger.error("ADB pidof check timed out")
            return False
        except Exception:
            return False

    def start_game(self, max_retries=3, retry_delay_seconds=timings.ADB_RETRY_DELAY):
        """Start Rise of Kingdoms app.

        Retries on transient ADB transport errors (e.g. "error: closed"), which
        happen when the ADB bridge reports the device as connected slightly
        before it is actually ready to accept shell commands.
        """
        self.logger.info("Starting Rise of Kingdoms...")
        self.logger.info(f"package name: {self.package_name}")

        start_cmd = [
            self.bluestacks.adb_path, "-s", self.bluestacks.adb_device,
            "shell", "am", "start", "-n", f"{self.package_name}/{self.activity_name}"
        ]

        for attempt in range(1, max_retries + 1):
            try:
                result = subprocess.run(start_cmd, capture_output=True, text=True,
                                        timeout=15)

                if "Error" in result.stdout or "error" in result.stderr:
                    # The "am start" response itself failed, but the activity may
                    # have launched anyway before the ADB transport dropped the
                    # connection. Verify actual process state before giving up.
                    time.sleep(timings.EXTENDED_SETTLE_WAIT)
                    if self.is_rok_process_running():
                        self.logger.info(
                            f"Rise of Kingdoms is running despite reported ADB error: {result.stderr.strip()}"
                        )
                        return True

                    self.logger.error(f"Failed to start Rise of Kingdoms (attempt {attempt}/{max_retries}): {result.stderr}")
                    if attempt < max_retries:
                        time.sleep(retry_delay_seconds)
                        continue
                    return False

                self.logger.info("Rise of Kingdoms started successfully")
                return True

            except Exception as e:
                self.logger.error(f"Error starting Rise of Kingdoms (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay_seconds)
                    continue
                return False

        return False

    def wait_for_game_load(self):
        """Wait for the game to load, returning early once the loading screen
        disappears or the home/map screen is detected."""
        self.logger.info(f"Waiting for game to load (max {self.game_load_wait_seconds}s)...")

        max_wait = self.game_load_wait_seconds
        interval = timings.POLL_INTERVAL
        elapsed = 0
        loading_detected = False

        while elapsed < max_wait:
            if self.check_stop_requested():
                return False

            if self.screen.is_loading_screen():
                loading_detected = True
                self.logger.info(f"Loading screen detected ({elapsed:.0f}s)")
            elif loading_detected:
                self.logger.info("Loading finished, waiting 3s for game to initialize...")
                time.sleep(timings.LONG_TRANSITION_WAIT)
                return True
            elif self.screen.is_in_home_village() or self.screen.is_in_map_screen():
                self.logger.info("Game already loaded (home/map screen detected)")
                return True

            time.sleep(min(interval, max_wait - elapsed))
            elapsed += interval

        self.logger.info(f"Max wait ({max_wait}s) reached, proceeding...")
        time.sleep(timings.LONG_TRANSITION_WAIT)
        return True

    def click_mid_of_screen(self):
        """Click at center of screen to dismiss loading screen or select."""
        self.logger.info("Clicking at middle of game screen to select")
        center = self.coords.get_screen('center')
        if not self.bluestacks.click(center['x'], center['y'], self.click_delay_ms):
            self.logger.error("Failed to click middle of screen")
            return False
        return True

    def dismiss_loading_screen(self):
        """Click to dismiss loading screen."""
        self.logger.info("Clicking to dismiss loading screen")
        pos = self.coords.get_screen('loading_dismiss')
        if not self.bluestacks.click(pos['x'], pos['y'], self.click_delay_ms):
            self.logger.error("Failed to dismiss loading screen")
            return False
        return True

    def navigate_to_map(self):
        """Click on map button and check if we're on the map view now."""
        if self.check_stop_requested():
            return False

        try:
            is_on_map = self.screen.is_in_map_screen()

            if not is_on_map:
                if not self.bluestacks.click(self.map_button['x'], self.map_button['y'], self.click_delay_ms):
                    self.logger.error("Failed to click on map button")
                    return False
                self.logger.info("Clicked on map button because screen was on home village")
                time.sleep(timings.MAP_LOAD_WAIT)  # Increased wait time for map to fully load after character switch

            return True

        except Exception as e:
            self.logger.error(f"Error navigating to map: {e}")
            self.logger.exception("Stack trace:")
            return False

    def switch_character(self, start_from=0):
        """
        Main function to switch through all characters.

        Args:
            start_from: Character index to start from (0-based)

        Returns:
            bool: True if completed successfully, False otherwise
        """
        return self.character_switcher.switch_all_characters(start_from)

    def switch_account(self, email, password):
        """
        Log out of the current account and log in as the given account.

        Args:
            email: Account email address
            password: Account password

        Returns:
            bool: True if the switch succeeded
        """
        return self.account_switcher.switch_to_account(email, password)

    def run_automation(self):
        """
        Run the full automation cycle.

        With an [Accounts] section configured, rotates through every account
        (switching login between them) and runs the character automation for
        each. Without one, behaves exactly like the old flow: character
        automation on the currently logged-in account only.

        Returns:
            bool: True if every account/character completed successfully
        """
        if not self.accounts:
            return self.switch_character()

        self.logger.info(f"Account rotation enabled: {len(self.accounts)} account(s) configured")
        all_success = True

        for idx, account in enumerate(self.accounts, start=1):
            if self.check_stop_requested():
                break

            email = account['email']
            self.logger.info(f"Processing account {idx}/{len(self.accounts)}: {email}")

            if not self.switch_account(email, account['password']):
                self.logger.error(f"Failed to switch to account {email}, skipping it")
                all_success = False
                # Try to get back to a workable state for the next account
                self.recovery.return_to_home(max_attempts=5)
                continue

            if not self.switch_character():
                self.logger.warning(f"Character automation reported failures for {email}")
                all_success = False

        return all_success

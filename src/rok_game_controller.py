#!/usr/bin/env python3
"""
RoK Game Controller - Main orchestrator for Rise of Kingdoms automation.

This is the main controller that coordinates game lifecycle and
delegates specific automation tasks to specialized classes.
"""
import time
import logging
import subprocess

from coordinate_manager import CoordinateManager
from ocr_helper import OCRHelper
from screen_detector import ScreenDetector
from build_automation import BuildAutomation
from donation_automation import DonationAutomation
from expedition_automation import ExpeditionAutomation
from character_switcher import CharacterSwitcher
from recovery_manager import RecoveryManager


class RoKGameController:
    """Controller for Rise of Kingdoms game operations."""

    def __init__(self, config_manager, bluestacks_controller):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.bluestacks = bluestacks_controller
        self.stop_check_callback = None

        # Load RoK configurations
        rok_config = config_manager.get_rok_config()
        self.rok_version = rok_config.get('rok_version', 'global').lower()

        # Load bluestacks configuration
        bluestacks_config = config_manager.get_bluestacks_config()
        self.game_load_wait_seconds = int(bluestacks_config.get('wait_for_startup_seconds', 30))
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
        self.build = BuildAutomation(
            self.ocr,
            self.bluestacks,
            self.coords,
            click_delay_ms=self.click_delay_ms,
            stop_check_callback=self.ocr.check_stop_requested
        )
        self.donation = DonationAutomation(
            self.ocr,
            self.screen,
            self.bluestacks,
            self.coords,
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
            num_of_chars=int(rok_config.get('num_of_characters', 1)),
            march_preset=int(rok_config.get('march_preset', 1)),
            click_delay_ms=self.click_delay_ms,
            character_login_loading_time=int(rok_config.get('character_login_screen_loading_time', 3)),
            game_load_wait_seconds=self.game_load_wait_seconds,
            will_perform_build=config_manager.get_bool('RiseOfKingdoms', 'perform_build', True),
            will_perform_donation=config_manager.get_bool('RiseOfKingdoms', 'perform_donation', True),
            will_perform_expedition=config_manager.get_bool('RiseOfKingdoms', 'perform_expedition', True),
            stop_check_callback=self.ocr.check_stop_requested,
            navigate_to_map_callback=self.navigate_to_map
        )

    def check_stop_requested(self):
        """Check if automation should stop."""
        if self.stop_check_callback and self.stop_check_callback():
            self.logger.info("Stop requested during RoK operation")
            return True
        return False

    def start_game(self):
        """Start Rise of Kingdoms app."""
        self.logger.info("Starting Rise of Kingdoms...")
        self.logger.info(f"package name: {self.package_name}")
        try:
            start_cmd = f'"{self.bluestacks.adb_path}" -s {self.bluestacks.adb_device} shell am start -n {self.package_name}/{self.activity_name}'
            result = subprocess.run(start_cmd, shell=True, capture_output=True, text=True)

            if "Error" in result.stdout or "error" in result.stderr:
                self.logger.error(f"Failed to start Rise of Kingdoms: {result.stderr}")
                return False

            self.logger.info("Rise of Kingdoms started successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error starting Rise of Kingdoms: {e}")
            return False

    def wait_for_game_load(self):
        """Wait for the game to load with stop check capability."""
        self.logger.info(f"Waiting {self.game_load_wait_seconds} seconds for game to load...")

        total_wait = self.game_load_wait_seconds
        interval = 2

        while total_wait > 0:
            if self.check_stop_requested():
                return False

            time.sleep(min(interval, total_wait))
            total_wait -= interval

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

    def close_dialogs(self):
        """Close any open dialogs using escape key."""
        if self.check_stop_requested():
            return False

        self.logger.info("Closing dialogs")

        if self.bluestacks.send_escape():
            self.logger.info("Sent escape key to close dialog")
            time.sleep(1)
            return True

        time.sleep(1)
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
                time.sleep(2)

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

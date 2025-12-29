#!/usr/bin/env python3
"""
RoK Game Controller - Main orchestrator for Rise of Kingdoms automation.

This is the main controller that coordinates character switching and
delegates specific automation tasks to specialized classes.
"""
import time
import logging
import subprocess
import numpy as np

from coordinate_manager import CoordinateManager
from ocr_helper import OCRHelper
from screen_detector import ScreenDetector
from build_automation import BuildAutomation
from donation_automation import DonationAutomation


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
        self.character_login_screen_loading_time = int(rok_config.get('character_login_screen_loading_time', 3))
        self.will_perform_build = config_manager.get_bool('RiseOfKingdoms', 'perform_build', True)
        self.will_perform_donation = config_manager.get_bool('RiseOfKingdoms', 'perform_donation', True)

        # Load coordinates from centralized JSON config
        self.coords = CoordinateManager()

        # Navigation coordinates
        self.avatar_icon = self.coords.get_nav('avatar_icon')
        self.settings_icon = self.coords.get_nav('settings_icon')
        self.characters_icon = self.coords.get_nav('characters_icon')
        self.map_button = self.coords.get_nav('map_button')
        self.yes_button = self.coords.get_nav('yes_button')

        # Character settings
        self.num_of_chars = int(rok_config.get('num_of_characters', 1))
        self.march_preset = int(rok_config.get('march_preset', 1))

        # Character grid positions
        self.character_click_positions_first_rotation = self.coords.get_character_grid('first_rotation')
        self.character_click_positions_after_first_rotation = self.coords.get_character_grid('after_scroll')

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

    def scroll_down(self):
        """Scroll down in the character list."""
        if self.check_stop_requested():
            return False

        self.logger.info("Scrolling down character list")

        scroll = self.coords.get_scroll('character_list')
        start = scroll['start']
        end = scroll['end']
        duration = scroll['duration_ms']

        if not self.bluestacks.swipe(start['x'], start['y'], end['x'], end['y'], duration):
            self.logger.error("Failed to scroll down")
            return False

        time.sleep(1.5)
        return True

    def open_character_selection(self):
        """Open the character selection screen."""
        if self.check_stop_requested():
            return False

        self.logger.info("Opening character selection screen")

        # Click avatar icon in top left
        self.logger.info("Clicking avatar icon")
        if not self.bluestacks.click(self.avatar_icon['x'], self.avatar_icon['y'], self.click_delay_ms):
            self.logger.error("Failed to click avatar icon")
            return False

        time.sleep(2)

        if self.check_stop_requested():
            return False

        # Click settings icon
        self.logger.info("Clicking settings icon")
        if not self.bluestacks.click(self.settings_icon['x'], self.settings_icon['y'], self.click_delay_ms):
            self.logger.error("Failed to click settings icon")
            return False

        time.sleep(2)

        if self.check_stop_requested():
            return False

        # Click characters icon
        self.logger.info("Clicking characters icon")
        if not self.bluestacks.click(self.characters_icon['x'], self.characters_icon['y'], self.click_delay_ms):
            self.logger.error("Failed to click characters icon")
            return False

        time.sleep(6)

        self.logger.info("Character selection screen opened")
        return True

    def switch_character(self):
        """Main function to switch through all characters."""
        self.logger.info("Starting character switching process")

        start_idx = 0

        for i in range(start_idx, self.num_of_chars):
            if self.check_stop_requested():
                self.logger.info("Automation stopped during character switching")
                return False

            self.logger.info(f"Processing character {i + 1} of {self.num_of_chars}")

            if not self.open_character_selection():
                self.logger.error("Failed to open character selection screen")
                return False

            # Get the current rotation
            current_rotation = int(np.ceil((i + 1) / 6))
            self.logger.info(f"Current character index: {i}")
            self.logger.info(f"Current rotation: {current_rotation}")

            # Perform necessary scrolls to reach the right screen
            for j in range(1, current_rotation):
                if self.check_stop_requested():
                    return False

                self.scroll_down()
                time.sleep(2)

            # Calculate position index in the current grid (0-5)
            pos_idx = i % 6

            # Choose position based on rotation
            if current_rotation == 1:
                pos = self.character_click_positions_first_rotation[pos_idx]
            else:
                pos = self.character_click_positions_after_first_rotation[pos_idx]

            # Click on the character portrait
            if not self.bluestacks.click(pos['x'], pos['y'], self.click_delay_ms):
                self.logger.error(f"Failed to click character at position {pos}")
                return False

            time.sleep(self.character_login_screen_loading_time)

            if self.check_stop_requested():
                return False

            # Check if this screen is now character login screen
            if self.screen.is_in_character_login():
                # Click the "Yes" button to confirm character switch
                if not self.bluestacks.click(self.yes_button['x'], self.yes_button['y'], self.click_delay_ms):
                    self.logger.error("Failed to click Yes to character login")
                    return False

                self.logger.info("Waiting for character to load...")
                self.wait_for_game_load()

                if self.check_stop_requested():
                    return False

            else:
                # Character being selected is already the current one
                self.logger.info("Character already selected, returning to main screen")
                for x in range(3):
                    if self.check_stop_requested():
                        return False
                    self.close_dialogs()
                    time.sleep(1)

            if self.check_stop_requested():
                return False

            # Perform configured actions for this character
            if self.will_perform_build:
                self.logger.info("Performing build for this character")
                self.build.perform_build(self.march_preset, navigate_to_map_callback=self.navigate_to_map)

            if self.check_stop_requested():
                return False

            if self.will_perform_donation:
                self.logger.info("Perform Alliance Donation for this character")
                time.sleep(1)
                self.donation.perform_recommended_tech_donation()

            self.logger.info(f"Completed processing character at position {pos}")

        self.logger.info("Character switching automation completed successfully")
        return True

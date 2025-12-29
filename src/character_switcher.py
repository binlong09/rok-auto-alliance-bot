#!/usr/bin/env python3
"""
Character Switcher - Handles character selection and switching workflow.

This module automates the process of switching between characters in
Rise of Kingdoms, navigating the character selection screen.
"""
import time
import logging
import numpy as np


class CharacterSwitcher:
    """Automates character switching workflow."""

    def __init__(self, bluestacks, coords, screen_detector, build_automation, donation_automation,
                 num_of_chars=1, march_preset=1, click_delay_ms=1000,
                 character_login_loading_time=3, game_load_wait_seconds=30,
                 will_perform_build=True, will_perform_donation=True,
                 stop_check_callback=None, navigate_to_map_callback=None):
        """
        Initialize the character switcher.

        Args:
            bluestacks: BlueStacksController instance for input
            coords: CoordinateManager instance for coordinates
            screen_detector: ScreenDetector instance for screen state detection
            build_automation: BuildAutomation instance for build workflow
            donation_automation: DonationAutomation instance for donation workflow
            num_of_chars: Number of characters to switch through
            march_preset: March preset number to use for builds
            click_delay_ms: Delay between clicks in milliseconds
            character_login_loading_time: Time to wait for character login screen
            game_load_wait_seconds: Time to wait for game to load after switch
            will_perform_build: Whether to perform build automation
            will_perform_donation: Whether to perform donation automation
            stop_check_callback: Optional callback to check if automation should stop
            navigate_to_map_callback: Optional callback to navigate to map
        """
        self.logger = logging.getLogger(__name__)
        self.bluestacks = bluestacks
        self.coords = coords
        self.screen = screen_detector
        self.build = build_automation
        self.donation = donation_automation

        # Configuration
        self.num_of_chars = num_of_chars
        self.march_preset = march_preset
        self.click_delay_ms = click_delay_ms
        self.character_login_loading_time = character_login_loading_time
        self.game_load_wait_seconds = game_load_wait_seconds
        self.will_perform_build = will_perform_build
        self.will_perform_donation = will_perform_donation

        # Callbacks
        self.stop_check = stop_check_callback
        self.navigate_to_map = navigate_to_map_callback

        # Navigation coordinates
        self.avatar_icon = coords.get_nav('avatar_icon')
        self.settings_icon = coords.get_nav('settings_icon')
        self.characters_icon = coords.get_nav('characters_icon')
        self.yes_button = coords.get_nav('yes_button')

        # Character grid positions
        self.character_positions_first_rotation = coords.get_character_grid('first_rotation')
        self.character_positions_after_scroll = coords.get_character_grid('after_scroll')

    def check_stop_requested(self):
        """Check if automation should stop."""
        if self.stop_check and self.stop_check():
            self.logger.info("Stop requested during character switching")
            return True
        return False

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

    def get_character_position(self, index):
        """
        Get the click position for a character at the given index.

        Args:
            index: Zero-based character index

        Returns:
            dict: Position {x, y} for the character
        """
        # Calculate which rotation (page) we're on
        rotation = int(np.ceil((index + 1) / 6))

        # Calculate position within the current grid (0-5)
        pos_idx = index % 6

        # Choose position based on rotation
        if rotation == 1:
            return self.character_positions_first_rotation[pos_idx]
        else:
            return self.character_positions_after_scroll[pos_idx]

    def navigate_to_character(self, index):
        """
        Navigate to and select a character at the given index.

        Args:
            index: Zero-based character index

        Returns:
            bool: True if navigation successful, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Calculate which rotation (page) we need
        rotation = int(np.ceil((index + 1) / 6))
        self.logger.info(f"Character index: {index}, rotation: {rotation}")

        # Scroll to the correct page
        for _ in range(1, rotation):
            if self.check_stop_requested():
                return False
            self.scroll_down()
            time.sleep(2)

        # Get position and click
        pos = self.get_character_position(index)
        if not self.bluestacks.click(pos['x'], pos['y'], self.click_delay_ms):
            self.logger.error(f"Failed to click character at position {pos}")
            return False

        return True

    def confirm_character_switch(self):
        """
        Confirm character switch if on login screen, or close dialogs if already selected.

        Returns:
            bool: True if successful, False otherwise
        """
        time.sleep(self.character_login_loading_time)

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
            for _ in range(3):
                if self.check_stop_requested():
                    return False
                self.close_dialogs()
                time.sleep(1)

        return True

    def perform_character_actions(self):
        """
        Perform configured actions (build, donation) for the current character.

        Returns:
            bool: True if successful, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Perform build automation
        if self.will_perform_build:
            self.logger.info("Performing build for this character")
            self.build.perform_build(self.march_preset, navigate_to_map_callback=self.navigate_to_map)

        if self.check_stop_requested():
            return False

        # Perform donation automation
        if self.will_perform_donation:
            self.logger.info("Performing Alliance Donation for this character")
            time.sleep(1)
            self.donation.perform_recommended_tech_donation()

        return True

    def switch_all_characters(self, start_from=0):
        """
        Main function to switch through all characters.

        Args:
            start_from: Character index to start from (0-based)

        Returns:
            bool: True if completed successfully, False otherwise
        """
        self.logger.info("Starting character switching process")

        for i in range(start_from, self.num_of_chars):
            if self.check_stop_requested():
                self.logger.info("Automation stopped during character switching")
                return False

            self.logger.info(f"Processing character {i + 1} of {self.num_of_chars}")

            # Open character selection screen
            if not self.open_character_selection():
                self.logger.error("Failed to open character selection screen")
                return False

            # Navigate to and click the character
            if not self.navigate_to_character(i):
                self.logger.error(f"Failed to navigate to character {i}")
                return False

            # Confirm switch or handle already-selected case
            if not self.confirm_character_switch():
                return False

            # Perform actions for this character
            if not self.perform_character_actions():
                return False

            pos = self.get_character_position(i)
            self.logger.info(f"Completed processing character at position {pos}")

        self.logger.info("Character switching automation completed successfully")
        return True

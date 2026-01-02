#!/usr/bin/env python3
"""
Character Switcher - Handles character selection and switching workflow.

This module automates the process of switching between characters in
Rise of Kingdoms, navigating the character selection screen.
Includes recovery and graceful degradation for failed characters.
"""
import time
import logging
import numpy as np

from recovery_manager import RetryConfig, with_retry
from daily_task_tracker import DailyTaskTracker


class CharacterSwitcher:
    """Automates character switching workflow with recovery support."""

    def __init__(self, bluestacks, coords, screen_detector, build_automation, donation_automation,
                 expedition_automation, recovery_manager, num_of_chars=1, march_preset=1, click_delay_ms=1000,
                 character_login_loading_time=3, game_load_wait_seconds=30,
                 will_perform_build=True, will_perform_donation=True, will_perform_expedition=True,
                 stop_check_callback=None, navigate_to_map_callback=None,
                 daily_task_tracker=None, force_daily_tasks=False):
        """
        Initialize the character switcher.

        Args:
            bluestacks: BlueStacksController instance for input
            coords: CoordinateManager instance for coordinates
            screen_detector: ScreenDetector instance for screen state detection
            build_automation: BuildAutomation instance for build workflow
            donation_automation: DonationAutomation instance for donation workflow
            expedition_automation: ExpeditionAutomation instance for expedition rewards
            recovery_manager: RecoveryManager instance for error recovery
            num_of_chars: Number of characters to switch through
            march_preset: March preset number to use for builds
            click_delay_ms: Delay between clicks in milliseconds
            character_login_loading_time: Time to wait for character login screen
            game_load_wait_seconds: Time to wait for game to load after switch
            will_perform_build: Whether to perform build automation
            will_perform_donation: Whether to perform donation automation
            will_perform_expedition: Whether to perform expedition collection
            stop_check_callback: Optional callback to check if automation should stop
            navigate_to_map_callback: Optional callback to navigate to map
            daily_task_tracker: Optional DailyTaskTracker for tracking daily task completion
            force_daily_tasks: If True, run daily tasks even if already completed today
        """
        self.logger = logging.getLogger(__name__)
        self.bluestacks = bluestacks
        self.coords = coords
        self.screen = screen_detector
        self.build = build_automation
        self.donation = donation_automation
        self.expedition = expedition_automation
        self.recovery = recovery_manager

        # Configuration
        self.num_of_chars = num_of_chars
        self.march_preset = march_preset
        self.click_delay_ms = click_delay_ms
        self.character_login_loading_time = character_login_loading_time
        self.game_load_wait_seconds = game_load_wait_seconds
        self.will_perform_build = will_perform_build
        self.will_perform_donation = will_perform_donation
        self.will_perform_expedition = will_perform_expedition

        # Daily task tracking
        self.daily_tracker = daily_task_tracker
        self.force_daily_tasks = force_daily_tasks
        self.current_character_index = 0  # Track which character we're processing

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

    def should_run_daily_task(self, task_name):
        """
        Check if a daily task should run for the current character.

        Args:
            task_name: Task name (DailyTaskTracker.TASK_BUILD or TASK_EXPEDITION)

        Returns:
            bool: True if the task should run, False if it should be skipped
        """
        # If no tracker, always run
        if self.daily_tracker is None:
            return True

        # If force mode is enabled, always run
        if self.force_daily_tasks:
            return True

        # Check if task was already completed today
        if self.daily_tracker.is_task_completed_today(self.current_character_index, task_name):
            return False

        return True

    def mark_daily_task_completed(self, task_name):
        """
        Mark a daily task as completed for the current character.

        Args:
            task_name: Task name (DailyTaskTracker.TASK_BUILD or TASK_EXPEDITION)
        """
        if self.daily_tracker is not None:
            self.daily_tracker.mark_task_completed(self.current_character_index, task_name)

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
        """
        Wait for the game to load by detecting when the loading screen disappears.

        Polls for "Loading" text on screen. Once it disappears, waits an additional
        3 seconds for the game to fully initialize.
        Falls back to max wait time if loading screen detection fails.
        """
        self.logger.info("Waiting for game to load...")

        max_wait = self.game_load_wait_seconds
        check_interval = 2
        elapsed = 0
        loading_detected = False

        # Poll until loading screen disappears or max time reached
        while elapsed < max_wait:
            if self.check_stop_requested():
                return False

            is_loading = self.screen.is_loading_screen()

            if is_loading:
                loading_detected = True
                self.logger.info(f"Loading screen detected, waiting... ({elapsed}s)")
            elif loading_detected:
                # Loading screen was visible but now it's gone - game finished loading
                self.logger.info("Loading screen finished, waiting 3s for game to initialize...")
                time.sleep(3)
                return True
            else:
                # No loading screen detected - might already be loaded or detection failed
                # Continue checking for a bit in case loading hasn't started yet
                pass

            time.sleep(check_interval)
            elapsed += check_interval

        # Max wait reached - proceed anyway
        self.logger.info(f"Max wait time ({max_wait}s) reached, proceeding...")
        time.sleep(3)  # Still wait 3s buffer
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

        time.sleep(3)  # Increased wait for profile menu to appear

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
        pos_idx = index % 6
        pos = self.get_character_position(index)
        self.logger.info(f"Character index: {index}, rotation: {rotation}, pos_idx: {pos_idx}")
        self.logger.info(f"Will click at position: ({pos['x']}, {pos['y']})")

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
        self.logger.info(f"Waiting {self.character_login_loading_time}s for character login screen...")
        time.sleep(self.character_login_loading_time)

        if self.check_stop_requested():
            return False

        # Check if this screen is now character login screen
        is_login_screen = self.screen.is_in_character_login()
        self.logger.info(f"is_in_character_login() returned: {is_login_screen}")

        if is_login_screen:
            # Click the "Yes" button to confirm character switch
            self.logger.info(f"Character login dialog detected! Clicking Yes at ({self.yes_button['x']}, {self.yes_button['y']})")
            if not self.bluestacks.click(self.yes_button['x'], self.yes_button['y'], self.click_delay_ms):
                self.logger.error("Failed to click Yes to character login")
                return False

            self.logger.info("Waiting for character to load...")
            self.wait_for_game_load()

            if self.check_stop_requested():
                return False
        else:
            # Character being selected is already the current one
            # WARNING: This could mean click landed on wrong position or current character
            self.logger.warning(
                f"No character login dialog detected for character {self.current_character_index + 1}. "
                f"This character may have been SKIPPED! Click might have hit current character or empty space."
            )
            self.logger.info("Returning to main screen with 3 escape keys...")
            for _ in range(3):
                if self.check_stop_requested():
                    return False
                self.close_dialogs()
                time.sleep(1)

        return True

    def perform_character_actions(self):
        """
        Perform configured actions (build, donation, expedition) for the current character.

        Daily tasks (build, expedition) are skipped if already completed today (UTC),
        unless force_daily_tasks is enabled. Tech donation runs every cycle.

        Returns:
            bool: True if successful, False otherwise
        """
        if self.check_stop_requested():
            return False

        char_display = self.current_character_index + 1  # 1-based for logging

        # Perform build automation (DAILY TASK)
        if self.will_perform_build:
            if self.should_run_daily_task(DailyTaskTracker.TASK_BUILD):
                self.logger.info(f"Performing build for character {char_display}")
                if self.build.perform_build(self.march_preset, navigate_to_map_callback=self.navigate_to_map):
                    self.mark_daily_task_completed(DailyTaskTracker.TASK_BUILD)
            else:
                self.logger.info(
                    f"Skipping build for character {char_display} - already completed today (UTC)"
                )

        if self.check_stop_requested():
            return False

        # Perform expedition reward collection (DAILY TASK)
        # Done before donation so screen is in cleaner state for character switch
        if self.will_perform_expedition:
            if self.should_run_daily_task(DailyTaskTracker.TASK_EXPEDITION):
                self.logger.info(f"Collecting expedition rewards for character {char_display}")
                time.sleep(1)
                if self.expedition.perform_expedition_collection():
                    self.mark_daily_task_completed(DailyTaskTracker.TASK_EXPEDITION)
            else:
                self.logger.info(
                    f"Skipping expedition for character {char_display} - already completed today (UTC)"
                )

        if self.check_stop_requested():
            return False

        # Perform donation automation (SCHEDULED TASK - runs every cycle)
        # Done last as it leaves screen in cleanest state for character switch
        if self.will_perform_donation:
            self.logger.info(f"Performing Alliance Donation for character {char_display}")
            time.sleep(1)
            self.donation.perform_recommended_tech_donation()

        return True

    @with_retry(RetryConfig(max_retries=2, recover_to_home=True, delay_between_retries=2.0))
    def _process_single_character(self, index):
        """
        Process a single character with retry support.

        This method is wrapped with @with_retry decorator for automatic
        recovery and retry on failure.

        Args:
            index: Zero-based character index

        Returns:
            bool: True if successful, False otherwise
        """
        # Set current character index for daily task tracking
        self.current_character_index = index

        # Open character selection screen
        if not self.open_character_selection():
            self.logger.error("Failed to open character selection screen")
            return False

        # Navigate to and click the character
        if not self.navigate_to_character(index):
            self.logger.error(f"Failed to navigate to character {index}")
            return False

        # Confirm switch or handle already-selected case
        if not self.confirm_character_switch():
            self.logger.error("Failed to confirm character switch")
            return False

        # Perform actions for this character
        if not self.perform_character_actions():
            self.logger.error("Failed to perform character actions")
            return False

        # Wait before switching to next character to ensure game is ready
        self.logger.info("Waiting 3 seconds before next character...")
        time.sleep(3)

        return True

    def switch_all_characters(self, start_from=0):
        """
        Main function to switch through all characters with graceful degradation.

        Failed characters are logged and skipped, allowing the automation
        to continue with remaining characters.

        Args:
            start_from: Character index to start from (0-based)

        Returns:
            bool: True if all characters processed successfully, False if any failed
        """
        self.logger.info("Starting character switching process")

        successful_characters = 0
        failed_characters = []

        for i in range(start_from, self.num_of_chars):
            if self.check_stop_requested():
                self.logger.info("Automation stopped during character switching")
                break

            self.logger.info(f"Processing character {i + 1} of {self.num_of_chars}")

            try:
                # Process this character with retry support
                if self._process_single_character(i):
                    successful_characters += 1
                    pos = self.get_character_position(i)
                    self.logger.info(f"Successfully completed character {i + 1} at position {pos}")
                else:
                    failed_characters.append(i + 1)  # 1-based for logging
                    self.logger.warning(
                        f"Character {i + 1} failed after retries, attempting recovery"
                    )
                    # Try to return to home before next character
                    self.recovery.return_to_home(max_attempts=3)

            except Exception as e:
                failed_characters.append(i + 1)
                self.logger.error(f"Exception processing character {i + 1}: {e}")
                # Try to return to home before next character
                self.recovery.return_to_home(max_attempts=3)

        # Report summary
        total = self.num_of_chars - start_from
        self.logger.info(
            f"Character switching completed: {successful_characters}/{total} successful"
        )

        if failed_characters:
            self.logger.warning(f"Failed characters: {failed_characters}")

        return len(failed_characters) == 0

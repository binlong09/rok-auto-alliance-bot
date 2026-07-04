#!/usr/bin/env python3
"""
Character Switcher - Handles character selection and switching workflow.

This module automates the process of switching between characters in
Rise of Kingdoms, navigating the character selection screen.
Includes recovery and graceful degradation for failed characters.
"""
import logging
import time

import numpy as np

import timings
from automation_base import StopCheckMixin
from recovery_manager import RetryConfig, with_retry


class CharacterSwitcher(StopCheckMixin):
    """Automates character switching workflow with recovery support."""

    STOP_CONTEXT = "character switching"

    def __init__(self, bluestacks, coords, screen_detector, build_automation, donation_automation,
                 expedition_automation, recovery_manager, navigator,
                 territory_automation=None,
                 num_of_chars=1, march_preset=1, click_delay_ms=1000,
                 character_login_loading_time=3, game_load_wait_seconds=30,
                 will_perform_build=True, will_perform_donation=True, will_perform_expedition=True,
                 will_perform_territory_claim=True,
                 stop_check_callback=None, navigate_to_map_callback=None,
                 progress=None):
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
            navigator: VerifiedNavigator instance for verified clicks
            territory_automation: TerritoryAutomation instance for territory RSS claim
            num_of_chars: Number of characters to switch through
            march_preset: March preset number to use for builds
            click_delay_ms: Delay between clicks in milliseconds
            character_login_loading_time: Time to wait for character login screen
            game_load_wait_seconds: Time to wait for game to load after switch
            will_perform_build: Whether to perform build automation
            will_perform_donation: Whether to perform donation automation
            will_perform_expedition: Whether to perform expedition collection
            will_perform_territory_claim: Whether to claim territory resources
            stop_check_callback: Optional callback to check if automation should stop
            navigate_to_map_callback: Optional callback to navigate to map
        """
        self.logger = logging.getLogger(__name__)
        self.bluestacks = bluestacks
        self.coords = coords
        self.screen = screen_detector
        self.build = build_automation
        self.donation = donation_automation
        self.expedition = expedition_automation
        self.recovery = recovery_manager
        self.nav = navigator
        self.territory = territory_automation

        # Configuration
        self.num_of_chars = num_of_chars
        self.march_preset = march_preset
        self.click_delay_ms = click_delay_ms
        self.character_login_loading_time = character_login_loading_time
        self.game_load_wait_seconds = game_load_wait_seconds
        self.will_perform_build = will_perform_build
        self.will_perform_donation = will_perform_donation
        self.will_perform_expedition = will_perform_expedition
        self.will_perform_territory_claim = will_perform_territory_claim

        self.current_character_index = 0
        self.account_index = 0

        # Callbacks
        self.stop_check = stop_check_callback
        self.navigate_to_map = navigate_to_map_callback

        # Progress tracking
        self.progress = progress

        # Navigation coordinates
        self.avatar_icon = coords.get_nav('avatar_icon')
        self.settings_icon = coords.get_nav('settings_icon')
        self.characters_icon = coords.get_nav('characters_icon')
        self.yes_button = coords.get_nav('yes_button')

        # Character grid positions
        self.character_positions_first_rotation = coords.get_character_grid('first_rotation')
        self.character_positions_after_scroll = coords.get_character_grid('after_scroll')

    def wait_for_game_load(self):
        """
        Wait for the game to load by detecting when the loading screen disappears.

        Polls for "Loading" text on screen. Once it disappears, waits an additional
        3 seconds for the game to fully initialize.
        Falls back to max wait time if loading screen detection fails.
        """
        self.logger.info("Waiting for game to load...")

        time.sleep(timings.LONG_TRANSITION_WAIT)

        max_wait = self.game_load_wait_seconds
        check_interval = timings.POLL_INTERVAL
        elapsed = 0
        loading_detected = False

        while elapsed < max_wait:
            if self.check_stop_requested():
                return False

            if self.screen.is_loading_screen():
                loading_detected = True
                self.logger.info(f"Loading screen detected, waiting... ({elapsed}s)")
            elif loading_detected:
                self.logger.info("Loading screen finished, waiting 3s for game to initialize...")
                time.sleep(timings.LONG_TRANSITION_WAIT)
                return True
            elif self.screen.is_in_home_village() or self.screen.is_in_map_screen():
                self.logger.info("Game loaded (home/map screen detected)")
                return True

            time.sleep(check_interval)
            elapsed += check_interval

        self.logger.info(f"Max wait time ({max_wait}s) reached, proceeding...")
        time.sleep(timings.LONG_TRANSITION_WAIT)
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

        time.sleep(timings.EXTENDED_SETTLE_WAIT)
        return True

    def open_character_selection(self):
        """
        Open the character selection screen, verifying each intermediate
        screen (profile menu -> settings -> character list) actually opened
        before moving on.
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Opening character selection screen")

        # Step 1: avatar icon (top left) -> profile menu
        if not self.nav.click_and_verify(
            "avatar icon",
            template='avatar_icon',
            fallback_point=self.avatar_icon,
            verify=self.screen.is_in_profile_menu,
            verify_timeout=8,
            settle_wait=timings.LONG_TRANSITION_WAIT,
        ):
            self.logger.error("Profile menu did not open after clicking avatar")
            return False

        if self.check_stop_requested():
            return False

        # Step 2: settings button -> settings screen
        # The OCR hit is the "Settings" label below the gear icon, so click
        # above the text; the template hit is the gear itself.
        if not self.nav.click_and_verify(
            "settings button",
            template='settings_icon',
            texts=["Settings"],
            region=self.coords.get_region('profile_menu'),
            offset={'x': 0, 'y': -45},
            fallback_point=self.settings_icon,
            verify=self.screen.is_in_settings_screen,
            verify_timeout=8,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        ):
            self.logger.error("Settings screen did not open")
            return False

        if self.check_stop_requested():
            return False

        # Step 3: characters button -> character selection list
        # Same label-below-icon layout as the settings button.
        if not self.nav.click_and_verify(
            "characters button",
            template='characters_icon',
            texts=["Characters", "Character"],
            region=self.coords.get_region('settings_screen'),
            offset={'x': 0, 'y': -45},
            fallback_point=self.characters_icon,
            verify=self.screen.is_in_character_selection,
            verify_timeout=12,
            settle_wait=timings.CHARACTER_SELECT_LOAD_WAIT,
        ):
            self.logger.error("Character selection screen did not open")
            return False

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
            time.sleep(timings.SCREEN_TRANSITION_WAIT)

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
        # Poll for the character login dialog instead of a single fixed-wait check.
        # A single check right after a fixed sleep is prone to a race condition
        # where the dialog hasn't finished rendering yet, causing the character
        # to be incorrectly treated as skipped.
        max_wait = 8  # total seconds to wait
        poll_interval = timings.CHARACTER_LOGIN_POLL_INTERVAL  # check every 1.5s
        elapsed = 0
        is_login_screen = False

        self.logger.info(f"Polling up to {max_wait}s for character login screen...")
        while elapsed < max_wait:
            if self.check_stop_requested():
                return False

            time.sleep(poll_interval)
            elapsed += poll_interval

            is_login_screen = self.screen.is_in_character_login()
            self.logger.info(f"is_in_character_login() returned: {is_login_screen} (elapsed: {elapsed}s)")

            if is_login_screen:
                break

        if self.check_stop_requested():
            return False

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
            # No login dialog: the clicked character is almost always the one
            # we're ALREADY logged in as (starred characters keep their list
            # position, so the current character can be sitting in the slot
            # we just clicked - e.g. slot 1 shows a green checkmark). That is
            # a normal case, not an error: the character is loaded, so just
            # get back in-game and run its actions.
            #
            # Blind escape keys are NOT safe here - one escape too many lands
            # on the home screen and opens the "Exit the game?" dialog, which
            # then breaks every subsequent action. Use the state-aware
            # recovery instead: it closes the characters/settings screens and
            # verifies the home village is actually visible.
            self.logger.info(
                f"No character login dialog for character {self.current_character_index + 1} - "
                "it is already the active character. Returning to the game screen."
            )
            if not self.recovery.return_to_home(max_attempts=5):
                self.logger.error(
                    "Could not return to the game screen after selecting the current character"
                )
                return False

        return True

    def _track_task(self, task_name, success):
        """Update progress tracking after a task runs."""
        if self.progress is None:
            return
        if success:
            self.progress.mark_task_completed(
                self.account_index, self.current_character_index, task_name)
        else:
            self.progress.mark_task_failed(
                self.account_index, self.current_character_index, task_name)

    def perform_character_actions(self):
        """
        Perform configured actions (build, donation, expedition) for the current character.

        Returns:
            bool: True if successful, False otherwise
        """
        if self.check_stop_requested():
            return False

        char_display = self.current_character_index + 1  # 1-based for logging

        if self.will_perform_build:
            self.logger.info(f"Performing build for character {char_display}")
            ok = self.build.perform_build(self.march_preset)
            self._track_task("build", ok)

        if self.check_stop_requested():
            return False

        # Done before donation so screen is in cleaner state for character switch
        if self.will_perform_expedition:
            self.logger.info(f"Collecting expedition rewards for character {char_display}")
            time.sleep(timings.ACTION_SETTLE_WAIT)
            ok = self.expedition.perform_expedition_collection()
            self._track_task("expedition", ok)

        if self.check_stop_requested():
            return False

        # Claim alliance territory resources (SCHEDULED TASK - runs every cycle)
        if self.will_perform_territory_claim and self.territory is not None:
            self.logger.info(f"Claiming territory resources for character {char_display}")
            time.sleep(timings.ACTION_SETTLE_WAIT)
            ok = self.territory.perform_territory_claim()
            self._track_task("territory", ok)

        if self.check_stop_requested():
            return False

        # Perform donation automation (SCHEDULED TASK - runs every cycle)
        # Done last as it leaves screen in cleanest state for character switch
        if self.will_perform_donation:
            self.logger.info(f"Performing Alliance Donation for character {char_display}")
            time.sleep(timings.ACTION_SETTLE_WAIT)
            ok = self.donation.perform_recommended_tech_donation()
            self._track_task("donation", ok)

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

        if index == 0:
            # The first character in the list is always the one currently
            # logged in, so skip the entire selection flow and just run
            # its actions directly.
            self.logger.info(
                "Character 1 is already active — skipping character selection"
            )
        else:
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
        time.sleep(timings.LONG_TRANSITION_WAIT)

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

            if (self.progress
                    and self.progress.is_character_completed(self.account_index, i)):
                self.logger.info(
                    f"Character {i + 1} already completed, skipping"
                )
                successful_characters += 1
                continue

            self.logger.info(f"Processing character {i + 1} of {self.num_of_chars}")

            if self.progress:
                self.progress.mark_character_started(self.account_index, i)

            try:
                # Process this character with retry support
                if self._process_single_character(i):
                    successful_characters += 1
                    pos = self.get_character_position(i)
                    self.logger.info(f"Successfully completed character {i + 1} at position {pos}")
                    if self.progress:
                        self.progress.mark_character_completed(self.account_index, i)
                else:
                    failed_characters.append(i + 1)  # 1-based for logging
                    self.logger.warning(
                        f"Character {i + 1} failed after retries, attempting recovery"
                    )
                    if self.progress:
                        self.progress.mark_character_failed(self.account_index, i)
                    # Try to return to home before next character
                    self.recovery.return_to_home(max_attempts=3)

            except Exception as e:
                failed_characters.append(i + 1)
                self.logger.error(f"Exception processing character {i + 1}: {e}")
                if self.progress:
                    self.progress.mark_character_failed(self.account_index, i)
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

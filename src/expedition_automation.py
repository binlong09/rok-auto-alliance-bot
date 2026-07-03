#!/usr/bin/env python3
"""
Expedition Automation - Handles expedition reward collection.

This module automates the process of collecting expedition rewards
from the Campaign screen in Rise of Kingdoms.

=============================================================================
HOW TO CREATE NEW AUTOMATION FEATURES - DOCUMENTATION
=============================================================================

1. COORDINATES (coordinates.json):
   - Add button positions under "navigation" section
   - Add OCR regions under "ocr_regions" section
   - Use ocr_debug_tool.py to find exact coordinates

2. CLASS STRUCTURE:
   - __init__: Receive dependencies (ocr, screen, bluestacks, coords)
   - check_stop_requested(): Allow graceful cancellation
   - Main workflow method (e.g., collect_expedition_rewards)
   - Helper methods for each step

3. OCR PATTERN:
   - Try OCR first to find text on screen
   - Fall back to hardcoded coordinates if OCR fails
   - Example: find "Campaign" text, or click (728, 674)

4. NAVIGATION PATTERN:
   - Check current screen state if needed
   - Click buttons with delays between actions
   - Use escape key to go back through screens
   - Always return to a known state (home screen)

5. ERROR HANDLING:
   - Log each step for debugging
   - Return False on failure
   - Use stop_check to allow cancellation

=============================================================================
"""
import time
import logging

import timings


class ExpeditionAutomation:
    """
    Automates expedition reward collection workflow.

    Workflow:
    1. Expand bottom bar (if not expanded)
    2. Click Campaign button (OCR or fallback position)
    3. Click Expedition (OCR or fallback position)
    4. Click chest positions to collect rewards
    5. Navigate back to home screen
    """

    def __init__(self, ocr_helper, screen_detector, bluestacks, coords, navigator,
                 click_delay_ms=1000, stop_check_callback=None):
        """
        Initialize the expedition automation.

        Args:
            ocr_helper: OCRHelper instance for text detection
            screen_detector: ScreenDetector instance for screen state detection
            bluestacks: BlueStacksController instance for input (clicks, keys)
            coords: CoordinateManager instance for coordinates
            navigator: VerifiedNavigator instance for verified clicks
            click_delay_ms: Delay between clicks in milliseconds
            stop_check_callback: Optional callback to check if automation should stop
        """
        self.logger = logging.getLogger(__name__)
        self.ocr = ocr_helper
        self.screen = screen_detector
        self.bluestacks = bluestacks
        self.coords = coords
        self.nav = navigator
        self.click_delay_ms = click_delay_ms
        self.stop_check = stop_check_callback

        # Load coordinates from coordinates.json
        # Navigation buttons
        self.expand_button = coords.get_nav('expand_button')
        self.campaign_button = coords.get_nav('campaign_button')
        self.expedition_button = coords.get_nav('expedition_button')
        self.expedition_chest_1 = coords.get_nav('expedition_chest_1')
        self.expedition_chest_2 = coords.get_nav('expedition_chest_2')
        self.expedition_collect = coords.get_nav('expedition_collect')
        self.exit_dialog_cancel = coords.get_nav('exit_dialog_cancel')

        # OCR regions
        self.campaign_screen_region = coords.get_region('campaign_screen')

    def check_stop_requested(self):
        """
        Check if automation should stop.

        This is called frequently to allow graceful cancellation.
        Returns True if stop was requested.
        """
        if self.stop_check and self.stop_check():
            self.logger.info("Stop requested during expedition automation")
            return True
        return False

    def close_dialog(self):
        """
        Close current dialog/screen using escape key.

        Returns:
            bool: True if escape was sent successfully
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Pressing Escape to close dialog")
        if self.bluestacks.send_escape():
            time.sleep(timings.ACTION_SETTLE_WAIT)
            return True
        return False

    def handle_exit_dialog(self):
        """
        Check for and handle the "Exit the game?" dialog.

        If the exit dialog is showing, click Cancel to dismiss it.

        Returns:
            bool: True if dialog was handled (or not present), False on failure
        """
        if self.check_stop_requested():
            return False

        if self.screen.is_exit_game_dialog():
            self.logger.info("Exit dialog detected, clicking Cancel to dismiss")
            if not self.bluestacks.click(self.exit_dialog_cancel['x'],
                                         self.exit_dialog_cancel['y'],
                                         self.click_delay_ms):
                self.logger.error("Failed to click Cancel on exit dialog")
                return False
            time.sleep(timings.ACTION_SETTLE_WAIT)
            return True

        return True  # No dialog present is also success

    def expand_bottom_bar(self):
        """
        Expand the bottom navigation bar if it's not already expanded.

        The bottom bar contains Campaign, Alliance, Commander, etc.

        Returns:
            bool: True if bottom bar is expanded, False on failure
        """
        if self.check_stop_requested():
            return False

        # Check if already expanded using screen detector
        if self.screen.is_bottom_bar_expanded():
            self.logger.info("Bottom bar is expanded")
            return True

        self.logger.info("Expanding bottom bar...")
        return self.nav.click_and_verify(
            "expand bottom bar button",
            template='expand_button',
            fallback_point=self.expand_button,
            verify=self.screen.is_bottom_bar_expanded,
            verify_timeout=5,
        )

    def click_campaign(self):
        """
        Click on the Campaign button to open Campaign screen, verifying
        the campaign screen actually opened.

        Returns:
            bool: True if the campaign screen opened, False otherwise
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Opening Campaign screen...")

        # OCR text position doesn't align with the button here, so the
        # priority is template image -> fixed coordinates, verified by the
        # campaign screen actually appearing.
        if not self.nav.click_and_verify(
            "Campaign button",
            template='campaign_icon',
            fallback_point=self.campaign_button,
            verify=self.screen.is_in_campaign_screen,
            verify_timeout=8,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        ):
            self.logger.error("Campaign screen did not open")
            return False

        self.logger.info("Campaign screen opened")
        return True

    def click_expedition(self):
        """
        Click on Expedition from the Campaign screen and verify the
        expedition screen opened.

        Strategy: template image -> OCR "Expedition" text -> fixed position.

        Returns:
            bool: True if the expedition screen opened, False otherwise
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Opening Expedition...")

        if not self.nav.click_and_verify(
            "Expedition banner",
            template='expedition_banner',
            texts=["Expedition", "expedition"],
            region=self.campaign_screen_region,
            fallback_point=self.expedition_button,
            verify=self.screen.is_in_expedition_screen,
            verify_timeout=8,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        ):
            self.logger.error("Expedition screen did not open")
            return False

        self.logger.info("Expedition screen opened")
        return True

    def collect_expedition_chests(self):
        """
        Collect expedition reward chests.

        Workflow:
        1. Click on first chest position (125, 125)
        2. Click on second chest position (988, 277) - 3 times
        3. Press Escape to go back to Expedition screen

        Returns:
            bool: True if collection completed, False on failure
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Collecting expedition chests...")

        # Click first chest position
        self.logger.info(f"Clicking chest 1 at ({self.expedition_chest_1['x']}, {self.expedition_chest_1['y']})")
        if not self.bluestacks.click(self.expedition_chest_1['x'],
                                     self.expedition_chest_1['y'],
                                     self.click_delay_ms):
            self.logger.error("Failed to click chest 1")
            return False
        time.sleep(timings.ACTION_SETTLE_WAIT)

        # Click second chest position 3 times
        for i in range(3):
            if self.check_stop_requested():
                return False

            self.logger.info(f"Clicking chest 2 at ({self.expedition_chest_2['x']}, {self.expedition_chest_2['y']}) - click {i+1}/3")
            if not self.bluestacks.click(self.expedition_chest_2['x'],
                                         self.expedition_chest_2['y'],
                                         self.click_delay_ms):
                self.logger.error(f"Failed to click chest 2 (attempt {i+1})")
                return False
            time.sleep(timings.MICRO_DELAY)

        # Press Escape to go back to Expedition screen
        self.logger.info("Going back to Expedition screen")
        self.close_dialog()

        return True

    def collect_expedition_rewards(self):
        """
        Final step: click collect button and navigate back.

        Workflow:
        1. Click collect position (124, 223)
        2. Check if Rewards dialog appeared (if rewards were already collected, it won't)
        3. If rewards dialog: Escape 3 times (rewards -> expedition -> campaign -> home)
        4. If no rewards dialog: Escape 2 times (expedition -> campaign -> home)
        5. After each escape, check for and handle exit dialog

        Returns:
            bool: True if completed, False on failure
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Collecting expedition rewards...")

        # Click collect position
        self.logger.info(f"Clicking collect at ({self.expedition_collect['x']}, {self.expedition_collect['y']})")
        if not self.bluestacks.click(self.expedition_collect['x'],
                                     self.expedition_collect['y'],
                                     self.click_delay_ms):
            self.logger.error("Failed to click collect")
            return False
        time.sleep(timings.EXTENDED_SETTLE_WAIT)

        # Check if rewards dialog appeared
        rewards_dialog_appeared = self.screen.is_rewards_dialog()

        if rewards_dialog_appeared:
            self.logger.info("Rewards dialog detected - need 3 escapes")
            num_escapes = 3
        else:
            self.logger.info("No rewards dialog (already collected) - need 2 escapes")
            num_escapes = 2

        # Navigate back with dynamic number of escapes
        for i in range(num_escapes):
            if self.check_stop_requested():
                return False

            self.logger.info(f"Escape {i + 1}/{num_escapes}")
            self.close_dialog()

            # Check for and handle exit dialog after each escape
            if not self.handle_exit_dialog():
                self.logger.error("Failed to handle exit dialog")
                return False

        # Wait for screen to fully return to home before next action
        self.logger.info("Waiting for screen to settle after expedition...")
        time.sleep(timings.LONG_TRANSITION_WAIT)

        return True

    def perform_expedition_collection(self):
        """
        Main method: Perform full expedition reward collection.

        This is the method to call from outside to run the full workflow.

        Workflow:
        1. Expand bottom bar
        2. Click Campaign
        3. Click Expedition
        4. Collect chests
        5. Collect rewards and return to home

        Returns:
            bool: True if completed successfully, False otherwise
        """
        self.logger.info("=== Starting Expedition Reward Collection ===")

        # Step 1: Expand bottom bar
        if not self.expand_bottom_bar():
            self.logger.error("Failed to expand bottom bar")
            return False

        if self.check_stop_requested():
            return False

        # Step 2: Click Campaign
        if not self.click_campaign():
            self.logger.error("Failed to open Campaign screen")
            return False

        if self.check_stop_requested():
            return False

        # Step 3: Click Expedition
        if not self.click_expedition():
            self.logger.error("Failed to open Expedition")
            return False

        if self.check_stop_requested():
            return False

        # Step 4: Collect chests
        if not self.collect_expedition_chests():
            self.logger.error("Failed to collect expedition chests")
            return False

        if self.check_stop_requested():
            return False

        # Step 5: Collect rewards and navigate back
        if not self.collect_expedition_rewards():
            self.logger.error("Failed to collect rewards")
            return False

        self.logger.info("=== Expedition Reward Collection Complete ===")
        return True

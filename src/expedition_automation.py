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

    def __init__(self, ocr_helper, screen_detector, bluestacks, coords,
                 click_delay_ms=1000, stop_check_callback=None):
        """
        Initialize the expedition automation.

        Args:
            ocr_helper: OCRHelper instance for text detection
            screen_detector: ScreenDetector instance for screen state detection
            bluestacks: BlueStacksController instance for input (clicks, keys)
            coords: CoordinateManager instance for coordinates
            click_delay_ms: Delay between clicks in milliseconds
            stop_check_callback: Optional callback to check if automation should stop
        """
        self.logger = logging.getLogger(__name__)
        self.ocr = ocr_helper
        self.screen = screen_detector
        self.bluestacks = bluestacks
        self.coords = coords
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
            time.sleep(1)
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
            time.sleep(1)
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
        if not self.screen.is_bottom_bar_expanded():
            self.logger.info("Expanding bottom bar...")
            if not self.bluestacks.click(self.expand_button['x'],
                                         self.expand_button['y'],
                                         self.click_delay_ms):
                self.logger.error("Failed to click expand button")
                return False
            time.sleep(1)

        self.logger.info("Bottom bar is expanded")
        return True

    def click_campaign(self):
        """
        Click on the Campaign button to open Campaign screen.

        Uses hardcoded position - OCR text position doesn't match button location.

        Returns:
            bool: True if clicked successfully, False otherwise
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Opening Campaign screen...")

        # Use hardcoded position - OCR returns text position which doesn't align with button
        click_x = self.campaign_button['x']
        click_y = self.campaign_button['y']
        self.logger.info(f"Clicking Campaign button at ({click_x}, {click_y})")

        if not self.bluestacks.click(click_x, click_y, self.click_delay_ms):
            self.logger.error("Failed to click Campaign button")
            return False

        time.sleep(2)  # Wait for Campaign screen to load
        self.logger.info("Campaign screen opened")
        return True

    def click_expedition(self):
        """
        Click on Expedition from the Campaign screen.

        Strategy:
        1. Try to find "Expedition" text using OCR
        2. Fall back to hardcoded position if OCR fails

        Returns:
            bool: True if clicked successfully, False otherwise
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Opening Expedition...")

        # Try OCR first to find "Expedition" text
        expedition_pos = self.ocr.detect_text_position(
            ["Expedition", "expedition"],
            self.campaign_screen_region
        )

        if expedition_pos:
            self.logger.info(f"Found Expedition via OCR at ({expedition_pos['x']}, {expedition_pos['y']})")
            click_x, click_y = expedition_pos['x'], expedition_pos['y']
        else:
            # Fall back to hardcoded position
            self.logger.info("Expedition not found via OCR, using fallback position")
            click_x = self.expedition_button['x']
            click_y = self.expedition_button['y']

        if not self.bluestacks.click(click_x, click_y, self.click_delay_ms):
            self.logger.error("Failed to click Expedition button")
            return False

        time.sleep(2)  # Wait for Expedition screen to load
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
        time.sleep(1)

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
            time.sleep(0.5)

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
        time.sleep(1.5)

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
        time.sleep(3)

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

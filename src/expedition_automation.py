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
import logging
import time

import timings
from automation_base import StopCheckMixin
from screen_detector import GameScreen


class ExpeditionAutomation(StopCheckMixin):
    """
    Automates expedition reward collection workflow.

    Workflow:
    1. Expand bottom bar (if not expanded)
    2. Click Campaign button (OCR or fallback position)
    3. Click Expedition (OCR or fallback position)
    4. Click chest positions to collect rewards
    5. Navigate back to home screen
    """

    STOP_CONTEXT = "expedition automation"

    def __init__(self, ocr_helper, screen_detector, bluestacks, coords, navigator,
                 router, click_delay_ms=1000, stop_check_callback=None):
        """
        Initialize the expedition automation.

        Args:
            ocr_helper: OCRHelper instance for text detection
            screen_detector: ScreenDetector instance for screen state detection
            bluestacks: BlueStacksController instance for input (clicks, keys)
            coords: CoordinateManager instance for coordinates
            navigator: VerifiedNavigator instance for verified clicks
            router: ScreenRouter instance for screen navigation
            click_delay_ms: Delay between clicks in milliseconds
            stop_check_callback: Optional callback to check if automation should stop
        """
        self.logger = logging.getLogger(__name__)
        self.ocr = ocr_helper
        self.screen = screen_detector
        self.bluestacks = bluestacks
        self.coords = coords
        self.nav = navigator
        self.router = router
        self.click_delay_ms = click_delay_ms
        self.stop_check = stop_check_callback

        # Load coordinates from coordinates.json
        self.expedition_chest_1 = coords.get_nav('expedition_chest_1')
        self.expedition_chest_2 = coords.get_nav('expedition_chest_2')
        self.expedition_collect = coords.get_nav('expedition_collect')

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

        # The rewards dialog (if any) and the way back home are handled
        # by the router in perform_expedition_collection - no blind
        # escape-counting here anymore.
        return True

    def perform_expedition_collection(self):
        """
        Main method: route to the expedition screen, collect chests and
        rewards, then route back to the home village.

        Returns:
            bool: True if completed successfully, False otherwise
        """
        self.logger.info("=== Starting Expedition Reward Collection ===")

        collected = False
        if self.router.goto(GameScreen.EXPEDITION):
            if self.collect_expedition_chests():
                collected = self.collect_expedition_rewards()
                if not collected:
                    self.logger.error("Failed to collect rewards")
            else:
                self.logger.error("Failed to collect expedition chests")
        else:
            self.logger.error("Could not reach the expedition screen")

        # Always route back to known ground for the next task. This also
        # dismisses the rewards dialog when one is open.
        if not self.router.goto(GameScreen.HOME_VILLAGE):
            self.logger.warning("Could not route back to home village")

        if collected:
            self.logger.info("=== Expedition Reward Collection Complete ===")
        else:
            self.logger.info("=== Expedition Reward Collection failed ===")
        return collected

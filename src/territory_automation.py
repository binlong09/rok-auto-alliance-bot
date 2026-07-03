#!/usr/bin/env python3
"""
Territory Automation - Claims alliance territory resource earnings.

Alliance territory (fortresses, resource centers) continuously produces
resources for every member. This module opens Alliance > Territory and
presses the CLAIM button on the "Territory Resource Earnings" row, banking
the accumulated corn/wood/stone/gold.

Runs every cycle (like tech donation): claiming is idempotent - once
everything is claimed the button simply has nothing left to give.

Every navigation step verifies the resulting screen state (template
matching / OCR) before moving on.
"""
import logging
import time

import timings
from automation_base import AllianceScreenMixin


class TerritoryAutomation(AllianceScreenMixin):
    """Automates alliance territory resource claiming."""

    STOP_CONTEXT = "territory claim"

    def __init__(self, ocr_helper, screen_detector, bluestacks, coords, navigator,
                 click_delay_ms=1000, stop_check_callback=None):
        """
        Initialize the territory automation.

        Args:
            ocr_helper: OCRHelper instance for text detection
            screen_detector: ScreenDetector instance for screen state detection
            bluestacks: BlueStacksController instance for input
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

    def open_territory_screen(self):
        """
        Click the Territory button on the alliance screen and verify the
        Alliance Territory screen opened.

        Returns:
            bool: True if the territory screen opened, False otherwise
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Looking for Territory button...")

        return self.nav.click_and_verify(
            "Territory button",
            template='territory_icon',
            texts=["Territory", "territory"],
            region=self.coords.get_region('alliance_menu'),
            # The label sits below the icon: click above the detected text
            offset={'x': 0, 'y': -50},
            fallback_point=self.coords.get_nav('territory_button'),
            verify=self.screen.is_in_territory_screen,
            verify_timeout=10,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        )

    def claim_resources(self):
        """
        Press CLAIM on the Territory Resource Earnings row.

        Returns:
            bool: True if the claim button was found and pressed
        """
        if self.check_stop_requested():
            return False

        target = self.nav.locate(
            "Claim button",
            template='claim_button',
            texts=["CLAIM", "Claim"],
            region=self.coords.get_region('territory_earnings'),
        )
        if target is None:
            # Nothing to claim right now (button absent/grayed) is not fatal
            self.logger.warning("Claim button not found - nothing to claim?")
            return False

        self.logger.info(f"Claiming territory resources at ({target['x']}, {target['y']})")
        if not self.bluestacks.click(target['x'], target['y'], self.click_delay_ms):
            return False

        time.sleep(timings.ACTION_SETTLE_WAIT)
        return True

    def perform_territory_claim(self):
        """
        Main method: open Alliance > Territory, claim resource earnings and
        return to the home screen.

        Returns:
            bool: True if the claim flow completed, False otherwise
        """
        self.logger.info("=== Starting Territory Resource Claim ===")

        if not self.open_alliance_screen():
            self.logger.error("Could not open alliance screen (character may not be in an alliance)")
            self.close_dialogs()
            return False

        self.logger.info("Alliance screen opened")

        if not self.open_territory_screen():
            self.logger.error("Failed to open territory screen")
            for _ in range(2):
                self.close_dialogs()
            return False

        self.logger.info("Territory screen opened")

        claimed = self.claim_resources()

        # Exit back to the home screen: territory -> alliance -> game.
        # Exactly two escapes - a third would land on the home screen and
        # open the "Exit the game?" dialog (the claim reward animates into
        # the resource bar without any dialog to dismiss).
        for _ in range(2):
            self.close_dialogs()

        if claimed:
            self.logger.info("=== Territory Resource Claim Complete ===")
        else:
            self.logger.info("=== Territory Resource Claim finished (nothing claimed) ===")
        return claimed

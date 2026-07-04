#!/usr/bin/env python3
"""
Territory Automation - Claims alliance territory resource earnings.

Alliance territory (fortresses, resource centers) continuously produces
resources for every member. This module routes to Alliance > Territory
and presses the CLAIM button on the "Territory Resource Earnings" row,
banking the accumulated corn/wood/stone/gold.

Runs every cycle (like tech donation): claiming is idempotent - once
everything is claimed the button simply has nothing left to give.

Navigation is delegated to the ScreenRouter, so the task can start from
any screen (including leftover dialogs) and always ends back on the
home village for the next task.
"""
import logging
import time

import timings
from automation_base import StopCheckMixin
from screen_detector import GameScreen


class TerritoryAutomation(StopCheckMixin):
    """Automates alliance territory resource claiming."""

    STOP_CONTEXT = "territory claim"

    def __init__(self, ocr_helper, screen_detector, bluestacks, coords, navigator,
                 router, click_delay_ms=1000, stop_check_callback=None):
        """
        Initialize the territory automation.

        Args:
            ocr_helper: OCRHelper instance for text detection
            screen_detector: ScreenDetector instance for screen state detection
            bluestacks: BlueStacksController instance for input
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
        Main method: route to Alliance > Territory, claim resource
        earnings and route back to the home village.

        Returns:
            bool: True if resources were claimed, False otherwise
            (routing failure and nothing-to-claim both return False)
        """
        self.logger.info("=== Starting Territory Resource Claim ===")

        claimed = False
        if self.router.goto(GameScreen.TERRITORY):
            claimed = self.claim_resources()
        else:
            self.logger.error("Could not reach the territory screen")

        # Always route back to known ground for the next task, even
        # after a failure - this is what keeps one task's mess from
        # cascading into the next.
        if not self.router.goto(GameScreen.HOME_VILLAGE):
            self.logger.warning("Could not route back to home village")

        if claimed:
            self.logger.info("=== Territory Resource Claim Complete ===")
        else:
            self.logger.info("=== Territory Resource Claim finished (nothing claimed) ===")
        return claimed

#!/usr/bin/env python3
"""
Donation Automation - Handles alliance technology donation workflow.

This module automates the process of donating to alliance technology,
specifically finding and donating to officer-recommended technologies.

Every navigation step verifies the resulting screen state (via OCR /
template matching) instead of blindly clicking fixed coordinates.
"""
import logging
import time

import timings
from automation_base import StopCheckMixin
from screen_detector import GameScreen


class DonationAutomation(StopCheckMixin):
    """Automates alliance technology donation workflow."""

    STOP_CONTEXT = "donation automation"

    def __init__(self, ocr_helper, screen_detector, bluestacks, coords, navigator,
                 router, click_delay_ms=1000, stop_check_callback=None):
        """
        Initialize the donation automation.

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

    def find_and_donate_recommended_technology(self):
        """
        Find Officer's Recommendation, open its donate dialog and donate.

        Uses color detection (red banner) as primary method, falls back to
        OCR. After clicking, verifies the donate dialog actually opened
        before spamming the Donate button.

        Returns:
            bool: True if successful, False otherwise
        """
        if self.check_stop_requested():
            return False

        region = self.coords.get_region('officer_recommendation')

        # Method 1: color detection for the red banner (most reliable)
        self.logger.info("Trying color detection for Officer's Recommendation banner...")
        result = self.ocr.detect_red_banner_position(region)

        if result:
            self.logger.info(f"Found Officer's Recommendation via color detection at ({result['x']}, {result['y']})")
        else:
            # Method 2: OCR fallback
            self.logger.info("Color detection failed, trying OCR fallback...")
            result = self.ocr.detect_text_position(
                ["Officer's Recommendation", "Officer", "Recommendation", "mendation"],
                region
            )
            if result:
                self.logger.info(f"Found Officer's Recommendation via OCR at ({result['x']}, {result['y']})")

        if not result:
            self.logger.error("Recommended Tech not found (both color and OCR detection failed)")
            return False

        offset = self.coords.get_offset('officer_recommendation_click')
        click_x = result['x'] + offset['x']
        click_y = result['y'] + offset['y']

        if not self.bluestacks.click(click_x, click_y, self.click_delay_ms):
            self.logger.error("Failed to click on Recommended Tech")
            return False

        # Verify the donate dialog opened before clicking Donate
        if not self.screen.wait_for(self.screen.is_in_donate_dialog, timeout=6,
                                    description="donate dialog"):
            self.logger.error("Donate dialog did not open after clicking recommended tech")
            return False

        # Locate the RSS Donate button (blue, right side) — skip gem button on left
        donate_target = self.nav.locate(
            "RSS Donate button",
            texts=["Donate", "DONATE"],
            region=self.coords.get_region('donate_rss_button'),
            fallback_point=self.coords.get_nav('donate_button'),
        )
        if donate_target is None:
            return False

        # Click Donate repeatedly (donations are limited by daily caps, extra
        # clicks are harmless no-ops once the cap is reached)
        for i in range(20):
            if self.check_stop_requested():
                return False
            self.bluestacks.click(donate_target['x'], donate_target['y'], 500)

        return True

    def perform_recommended_tech_donation(self):
        """
        Route to the alliance tech screen, find officer's recommendation
        and donate, then route back to the home village.

        Returns:
            bool: True if successful, False otherwise
        """
        self.logger.info("=== Starting Alliance Tech Donation ===")

        donated = False
        if self.router.goto(GameScreen.TECH):
            self.logger.info("Tech screen opened")
            donated = self.find_and_donate_recommended_technology()
            if not donated:
                self.logger.error("Failed to find and donate recommended technology")
        else:
            self.logger.error("Could not reach the alliance tech screen "
                              "(character may not be in an alliance)")

        # Always route back to known ground for the next task.
        if not self.router.goto(GameScreen.HOME_VILLAGE):
            self.logger.warning("Could not route back to home village")

        if donated:
            self.logger.info("Donate recommended technology completed")
            time.sleep(timings.ACTION_SETTLE_WAIT)
        return donated

#!/usr/bin/env python3
"""
Donation Automation - Handles alliance technology donation workflow.

This module automates the process of donating to alliance technology,
specifically finding and donating to officer-recommended technologies.

Every navigation step verifies the resulting screen state (via OCR /
template matching) instead of blindly clicking fixed coordinates.
"""
import time
import logging

import timings
from automation_base import DialogCloserMixin


class DonationAutomation(DialogCloserMixin):
    """Automates alliance technology donation workflow."""

    STOP_CONTEXT = "donation automation"

    def __init__(self, ocr_helper, screen_detector, bluestacks, coords, navigator,
                 click_delay_ms=1000, stop_check_callback=None):
        """
        Initialize the donation automation.

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

    def expand_bottom_bar(self):
        """Expand bottom bar if it's not expanded yet, and verify it expanded."""
        if self.screen.is_bottom_bar_expanded():
            self.logger.info("Bottom bar is expanded")
            return True

        return self.nav.click_and_verify(
            "expand bottom bar button",
            template='expand_button',
            fallback_point=self.coords.get_nav('expand_button'),
            verify=self.screen.is_bottom_bar_expanded,
            verify_timeout=5,
        )

    def open_alliance_screen(self):
        """
        Open the alliance screen from the bottom bar and verify it opened.

        The bottom bar can collapse again between steps, so each attempt
        re-expands it before clicking the Alliance icon - otherwise the
        click lands on the game world and the character is wrongly reported
        as not being in an alliance.

        Returns:
            bool: True if the alliance screen is open, False otherwise
        """
        for attempt in range(1, 3):
            if self.check_stop_requested():
                return False

            if not self.expand_bottom_bar():
                self.logger.warning(
                    f"Could not expand bottom bar (attempt {attempt}/2)")
                continue

            if self.nav.click_and_verify(
                "Alliance button",
                template='alliance_icon',
                region=self.coords.get_region('bottom_bar'),
                fallback_point=self.coords.get_nav('alliance_button'),
                verify=self.screen.is_char_in_alliance,
                verify_timeout=8,
                attempts=1,
                settle_wait=timings.SCREEN_TRANSITION_WAIT,
            ):
                return True

            self.logger.warning(
                f"Alliance screen did not open (attempt {attempt}/2), retrying "
                "with a fresh bottom-bar expansion")

        return False

    def click_technology_button(self):
        """
        Click the Technology button on the alliance screen and verify the
        technology screen opened.

        Locates the button via template image, then OCR "Technology" text
        (handles KvK layout changes), then hardcoded coordinates.

        Returns:
            bool: True if the tech screen opened, False otherwise
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Looking for Technology button...")

        return self.nav.click_and_verify(
            "Technology button",
            template='technology_icon',
            texts=["Technology", "technology", "TECHNOLOGY"],
            region=self.coords.get_region('alliance_menu'),
            # The label sits below the icon: click above the detected text
            offset={'x': 0, 'y': -50},
            fallback_point=self.coords.get_nav('technology_button'),
            verify=self.screen.is_in_tech_screen,
            verify_timeout=10,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        )

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
            for _ in range(2):
                self.close_dialogs()
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
            for _ in range(2):
                self.close_dialogs()
            return False

        # Locate the Donate button (template -> OCR -> fixed coords)
        donate_target = self.nav.locate(
            "Donate button",
            template='donate_button',
            texts=["Donate", "DONATE"],
            region=self.coords.get_region('donate_dialog'),
            fallback_point=self.coords.get_nav('donate_button'),
        )
        if donate_target is None:
            self.close_dialogs()
            return False

        # Click Donate repeatedly (donations are limited by daily caps, extra
        # clicks are harmless no-ops once the cap is reached)
        for i in range(20):
            if self.check_stop_requested():
                return False
            self.bluestacks.click(donate_target['x'], donate_target['y'], 500)

        # Exit to home screen after donation completes
        for _ in range(3):
            self.close_dialogs()
        return True

    def perform_recommended_tech_donation(self):
        """
        Open the alliance tech screen, find officer's recommendation and donate.
        Exit to home screen if Officer's recommendation is not found.

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.expand_bottom_bar():
            self.logger.error("Bottom bar is not expanded")
            return False

        if self.check_stop_requested():
            return False

        if not self.open_alliance_screen():
            # Either the click failed or the character is not in an alliance
            self.logger.error("Could not open alliance screen (character may not be in an alliance)")
            self.close_dialogs()
            return False

        self.logger.info("Alliance screen opened")

        # Click Technology button and verify the tech screen opened
        if not self.click_technology_button():
            self.logger.error("Failed to open technology screen")
            self.close_dialogs()
            return False

        self.logger.info("Tech screen opened")

        if not self.find_and_donate_recommended_technology():
            self.logger.error("Failed to find and donate recommended technology")
            return False

        self.logger.info("Donate recommended technology completed")
        time.sleep(timings.ACTION_SETTLE_WAIT)
        return True

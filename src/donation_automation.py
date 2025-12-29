#!/usr/bin/env python3
"""
Donation Automation - Handles alliance technology donation workflow.

This module automates the process of donating to alliance technology,
specifically finding and donating to officer-recommended technologies.
"""
import time
import logging


class DonationAutomation:
    """Automates alliance technology donation workflow."""

    def __init__(self, ocr_helper, screen_detector, bluestacks, coords, click_delay_ms=1000, stop_check_callback=None):
        """
        Initialize the donation automation.

        Args:
            ocr_helper: OCRHelper instance for text detection
            screen_detector: ScreenDetector instance for screen state detection
            bluestacks: BlueStacksController instance for input
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

    def check_stop_requested(self):
        """Check if automation should stop."""
        if self.stop_check and self.stop_check():
            self.logger.info("Stop requested during donation automation")
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

    def expand_bottom_bar(self):
        """Expand bottom bar if it's not expanded yet."""
        if not self.screen.is_bottom_bar_expanded():
            expand_button = self.coords.get_nav('expand_button')
            if not self.bluestacks.click(expand_button['x'], expand_button['y'], self.click_delay_ms):
                self.logger.error('Failed to expand bottom bar')
                return False

        self.logger.info("Bottom bar is expanded")
        time.sleep(1)
        return True

    def click_technology_button(self):
        """
        Click the Technology button on the alliance screen.

        Uses OCR to find "Technology" text first (handles KvK layout changes),
        falls back to hardcoded coordinates if OCR fails.

        Returns:
            bool: True if clicked successfully, False otherwise
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Looking for Technology button...")

        # Method 1: Try OCR to find "Technology" text
        alliance_menu_region = self.coords.get_region('alliance_menu')
        result = self.ocr.detect_text_position(
            ["Technology", "technology", "TECHNOLOGY"],
            alliance_menu_region
        )

        if result:
            self.logger.info(f"Found Technology via OCR at ({result['x']}, {result['y']})")
            if not self.bluestacks.click(result['x'], result['y'], self.click_delay_ms):
                self.logger.error("Failed to click Technology button (OCR position)")
                return False
            return True

        # Method 2: Fall back to hardcoded position
        self.logger.info("Technology not found via OCR, using fallback position")
        technology_button = self.coords.get_nav('technology_button')
        if not self.bluestacks.click(technology_button['x'], technology_button['y'], self.click_delay_ms):
            self.logger.error("Failed to click Technology button (fallback position)")
            return False

        return True

    def find_and_donate_recommended_technology(self):
        """
        Find Officer's Recommendation and donate to it.

        Uses color detection (red banner) as primary method,
        falls back to OCR if color detection fails.

        Returns:
            bool: True if successful, False otherwise
        """
        if self.check_stop_requested():
            return False

        region = self.coords.get_region('officer_recommendation')
        result = None

        # Method 1: Try color detection for red banner (most reliable)
        self.logger.info("Trying color detection for Officer's Recommendation banner...")
        result = self.ocr.detect_red_banner_position(region)

        if result:
            self.logger.info(f"Found Officer's Recommendation via color detection at ({result['x']}, {result['y']})")
        else:
            # Method 2: Fall back to OCR
            self.logger.info("Color detection failed, trying OCR fallback...")
            result = self.ocr.detect_text_position(
                ["Officer's Recommendation", "Officer", "Recommendation", "mendation"],
                region
            )
            if result:
                self.logger.info(f"Found Officer's Recommendation via OCR at ({result['x']}, {result['y']})")

        if result:
            offset = self.coords.get_offset('officer_recommendation_click')
            click_x = result['x'] + offset['x']
            click_y = result['y'] + offset['y']

            if not self.bluestacks.click(click_x, click_y, self.click_delay_ms):
                self.logger.error("Failed to click on Recommended Tech")
                return False

            donate_button = self.coords.get_nav('donate_button')
            # Click Donate 20 times
            for i in range(20):
                self.bluestacks.click(donate_button['x'], donate_button['y'], 500)

            # Exit to home screen after donation completes
            for i in range(3):
                self.close_dialogs()
            return True
        else:
            self.logger.error("Recommended Tech not found (both color and OCR detection failed)")
            for i in range(2):
                self.close_dialogs()
            return False

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

        alliance_button = self.coords.get_nav('alliance_button')
        if not self.bluestacks.click(alliance_button['x'], alliance_button['y'], self.click_delay_ms):
            self.logger.error("Failed to open alliance screen")
            return False

        self.logger.info("Alliance screen opened")
        time.sleep(2)

        if not self.screen.is_char_in_alliance():
            self.close_dialogs()
            self.logger.error("Character is not in alliance")
            return False

        # Click Technology button (OCR first, then fallback to hardcoded)
        if not self.click_technology_button():
            self.logger.error("Failed to open technology screen")
            return True

        self.logger.info("Tech screen opened")
        time.sleep(6)

        if not self.find_and_donate_recommended_technology():
            self.logger.error("Failed to find and donate recommended technology")
            return False

        self.logger.info("Donate recommended technology completed")
        time.sleep(1)
        return True

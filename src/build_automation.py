#!/usr/bin/env python3
"""
Build Automation - Handles alliance build/flag joining workflow.

This module automates the process of finding and joining alliance builds,
dispatching troops to construction projects.

Navigation steps verify the resulting screen state (OCR / template
matching) and poll for expected text instead of single-shot checks after
fixed sleeps.
"""
import logging
import time

import cv2

import timings
from automation_base import DialogCloserMixin


class BuildAutomation(DialogCloserMixin):
    """Automates alliance build participation workflow."""

    STOP_CONTEXT = "build automation"

    def __init__(self, ocr_helper, screen_detector, bluestacks, coords, navigator,
                 click_delay_ms=1000, stop_check_callback=None):
        """
        Initialize the build automation.

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

    def navigate_to_bookmark(self):
        """Navigate to bookmark screen from map screen and verify it opened."""
        if self.check_stop_requested():
            return False

        self.logger.info("Navigating to bookmark screen")

        return self.nav.click_and_verify(
            "bookmark button",
            template='bookmark_icon',
            fallback_point=self.coords.get_nav('bookmark_button'),
            verify=self.screen.is_in_bookmark_screen,
            verify_timeout=8,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        )

    def click_mid_of_screen(self):
        """Click at center of screen to select."""
        self.logger.info("Clicking at middle of game screen to select")
        center = self.coords.get_screen('center')
        if not self.bluestacks.click(center['x'], center['y'], self.click_delay_ms):
            self.logger.error("Failed to click middle of screen")
            return False
        return True

    def find_and_click_one_troop_button(self):
        """
        Locate "1 troop" button and click the corresponding Go button.

        Returns:
            bool: True if found and clicked, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Poll: the bookmark list may still be rendering when we get here
        one_troop_region = self.coords.get_region('one_troop')
        result = self.ocr.wait_for_text_position("troop", one_troop_region, timeout=6)
        if not result:
            self.logger.error("Could not find '1 troop' text")
            return False

        go_button_y_positions = self.coords.get_go_button_y_positions()
        go_button_y = self.ocr.find_closest_value(result['y'], go_button_y_positions)
        go_button_x = self.coords.get_go_button_x()

        if not self.bluestacks.click(go_button_x, go_button_y, self.click_delay_ms):
            self.logger.error("Failed to click on one troop button")
            return False

        time.sleep(timings.LONG_TRANSITION_WAIT)
        self.click_mid_of_screen()
        time.sleep(timings.ACTION_SETTLE_WAIT)
        return True

    def _detect_blue_build_button(self, region):
        """
        Detect the cyan/blue BUILD button by color in HSV space.

        Returns:
            dict: {x, y} center of the button if found, None otherwise
        """
        screenshot = self.bluestacks.take_screenshot()
        if screenshot is None:
            return None

        h, w = screenshot.shape[:2]
        rx = min(region['x'], w - 1)
        ry = min(region['y'], h - 1)
        rw = min(region['width'], w - rx)
        rh = min(region['height'], h - ry)
        crop = screenshot[ry:ry + rh, rx:rx + rw]

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (85, 100, 140), (105, 255, 255))

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < 2000:
            return None

        bx, by, bw, bh = cv2.boundingRect(largest)
        center_x = rx + bx + bw // 2
        center_y = ry + by + bh // 2
        self.logger.info(f"Blue BUILD button detected at ({center_x}, {center_y})")
        return {'x': center_x, 'y': center_y}

    def find_and_click_build_button(self):
        """
        Locate the BUILD button on the flag info panel and click it.

        Uses a narrow region that covers only the button area (not the
        popup title where "Building" text would false-match "BUILD").

        Returns:
            bool: True if found and clicked, False otherwise
        """
        if self.check_stop_requested():
            return False

        button_region = self.coords.get_region('build_action_button')
        wide_region = self.coords.get_region('build_button')

        # Primary: look for "BUILD" text in the narrow button region
        result = self.ocr.wait_for_text_position(
            ["BUILD", "Build"], button_region, timeout=8,
        )
        if result:
            self.logger.info(f"Found BUILD button via OCR at ({result['x']}, {result['y']})")
            if not self.bluestacks.click(result['x'], result['y'], self.click_delay_ms):
                self.logger.error("Failed to click on BUILD button")
                return False
            time.sleep(timings.SCREEN_TRANSITION_WAIT)
            return True

        # Fallback 1: detect the blue button by color
        result = self._detect_blue_build_button(button_region)
        if result:
            if not self.bluestacks.click(result['x'], result['y'], self.click_delay_ms):
                self.logger.error("Failed to click on blue BUILD button")
                return False
            time.sleep(timings.SCREEN_TRANSITION_WAIT)
            return True

        # Fallback 2: find "remaining time" text and offset down to the button
        result = self.ocr.wait_for_text_position(
            ["remaining", "time"], wide_region, timeout=4,
        )
        if result:
            offset_y = self.coords.get_offset('build_button_offset_y')
            build_button_y = result['y'] + offset_y
            self.logger.info(f"Clicking BUILD via offset from 'remaining' text at y={build_button_y}")
            if not self.bluestacks.click(result['x'], build_button_y, self.click_delay_ms):
                self.logger.error("Failed to click on build button")
                return False
            time.sleep(timings.SCREEN_TRANSITION_WAIT)
            return True

        self.logger.error("BUILD button not found")
        return False

    def find_and_click_tap_to_join_button(self):
        """
        Locate "tap to join" button and click it.

        Returns:
            bool: True if found and clicked, False otherwise
        """
        if self.check_stop_requested():
            return False

        tap_region = self.coords.get_region('tap_to_join')
        result = self.ocr.wait_for_text_position("tap", tap_region, timeout=6)
        if result:
            if not self.bluestacks.click(result['x'], result['y'], self.click_delay_ms):
                self.logger.error("Failed to click on tap to join button")
                return False
            return True
        else:
            self.logger.error("Tap to join button not found")
            return False

    def find_and_click_new_troop_button(self):
        """
        Locate "Dispatch" button for new troop and click it.

        Returns:
            bool: True if found and clicked, False otherwise
        """
        if self.check_stop_requested():
            return False

        new_troop_region = self.coords.get_region('new_troop')
        result = self.ocr.wait_for_text_position("Dispatch", new_troop_region, timeout=6)
        if result:
            # New troop button is 90px below the Dispatch text
            new_troop_button_y = result['y'] + 90
            if not self.bluestacks.click(result['x'], new_troop_button_y, self.click_delay_ms):
                self.logger.error("Failed to click on New Troop button")
                return False
            return True
        else:
            self.logger.error("New Troop Button not found. Not enough available marches")
            return False

    def dispatch_troop_to_join_build(self, march_preset):
        """
        Dispatch troops using the configured march preset.

        Args:
            march_preset: The march preset number to use (1-7)

        Returns:
            bool: True if successful, False otherwise
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Dispatching troops")

        # Get preset button position from coordinates
        preset_button = self.coords.get_march_preset_position(march_preset)

        if not self.bluestacks.click(preset_button['x'], preset_button['y'], self.click_delay_ms):
            self.logger.error(f"Failed to click on preset {march_preset} button")
            return False

        time.sleep(timings.SCREEN_TRANSITION_WAIT)

        if self.check_stop_requested():
            return False

        # March button: template -> OCR "March" text -> fixed coordinates
        march_target = self.nav.locate(
            "March button",
            template='march_button',
            texts=["March", "MARCH"],
            region=self.coords.get_region('march_screen'),
            fallback_point=self.coords.get_nav('march_button'),
        )
        if march_target is None:
            return False

        if not self.bluestacks.click(march_target['x'], march_target['y'], self.click_delay_ms):
            self.logger.error("Failed to click march button")
            return False

        time.sleep(timings.SCREEN_TRANSITION_WAIT)
        return True

    def perform_build(self, march_preset, navigate_to_map_callback=None):
        """
        Perform the build automation sequence.

        Args:
            march_preset: The march preset number to use
            navigate_to_map_callback: Optional callback to navigate to map first

        Returns:
            bool: True if successful, False otherwise
        """
        if self.check_stop_requested():
            return False

        self.logger.info("Starting build automation")

        # Navigate to map if callback provided
        if navigate_to_map_callback:
            navigate_to_map_callback()

        # Navigate to bookmark screen (verified)
        if not self.navigate_to_bookmark():
            self.logger.warning("Could not open bookmark screen")
            self.close_dialogs()
            return True

        # Find the word 1 troop on screen and click on Go button
        # Then click on middle to select the flag
        if self.find_and_click_one_troop_button():
            # Find the word Building Progress on screen and use it to click on Build Button
            # If the word Building Progress is not found, it means the flag is already finished or an invalid object
            if self.find_and_click_build_button():
                # Find the word Tap To Join on screen and click it
                if self.find_and_click_tap_to_join_button():
                    # Find and Click new troop button
                    if self.find_and_click_new_troop_button():
                        success = self.dispatch_troop_to_join_build(march_preset)
                        if not success:
                            self.logger.warning("Failed to dispatch troops")
                    else:
                        # If the word Dispatch is not found, it means there are no available marches
                        self.close_dialogs()
                else:
                    # If Tap To Join is not found, this account already fills the flag
                    self.close_dialogs()
        else:
            self.logger.warning("Cannot find 1 troop button")
            self.close_dialogs()

        self.logger.info("Build automation completed")
        return True

#!/usr/bin/env python3
"""
Navigation Helper - Verified, state-aware click primitives.

Historically every automation module clicked fixed coordinates and slept a
fixed time, with no idea whether the click landed or the screen changed.
This module centralizes the robust pattern all automations now share:

    locate the target  ->  click it  ->  VERIFY the expected state
    (template image)       (ADB tap)      (OCR screen detection)
    (OCR text)                            retry the whole chain if not
    (fallback coords)                     reached

Locating tries the most reliable method first and degrades gracefully:
  1. image template matching (if a template PNG exists - see template_matcher.py)
  2. OCR text position (if the target has readable text)
  3. fixed coordinates from coordinates.json (last resort, previous behavior)

so the bot never becomes *less* capable than the old fixed-position version,
it only gets more accurate as detection methods succeed.
"""
import time
import logging

import timings
from automation_base import StopCheckMixin


class VerifiedNavigator(StopCheckMixin):
    """Click primitives that verify the result before moving on."""

    STOP_CONTEXT = "navigation"

    def __init__(self, ocr_helper, screen_detector, bluestacks, coords,
                 click_delay_ms=1000, stop_check_callback=None):
        """
        Args:
            ocr_helper: OCRHelper instance (text + template detection)
            screen_detector: ScreenDetector instance (state checks)
            bluestacks: BlueStacksController instance (input)
            coords: CoordinateManager instance
            click_delay_ms: Delay after each click in milliseconds
            stop_check_callback: Optional callback to check if automation should stop
        """
        self.logger = logging.getLogger(__name__)
        self.ocr = ocr_helper
        self.screen = screen_detector
        self.bluestacks = bluestacks
        self.coords = coords
        self.click_delay_ms = click_delay_ms
        self.stop_check = stop_check_callback

    def locate(self, description, template=None, texts=None, region=None,
               fallback_point=None, offset=None, template_offset=None,
               template_threshold=None):
        """
        Locate a UI element using the best available method.

        Args:
            description: Human-readable element name for logging
            template (str, optional): Template image name to try first
            texts (str or list, optional): OCR text(s) to look for
            region (dict, optional): Region to restrict template/OCR search
            fallback_point (dict, optional): {x, y} fixed coordinates as last resort
            offset (dict, optional): {x, y} offset applied to an OCR text hit
                (e.g. the readable label sits below the actual button). Not
                applied to template hits or the fallback point, which already
                point at the click target.
            template_offset (dict, optional): {x, y} offset applied to a
                template hit only.
            template_threshold (float, optional): Confidence override for templates

        Returns:
            dict: {x, y, method} click target, or None if nothing worked
        """
        if self.check_stop_requested():
            return None

        # Method 1: image template matching
        if template:
            result = self.ocr.find_template(template, region=region,
                                            threshold=template_threshold)
            if result:
                target = self._apply_offset(result, template_offset)
                target['method'] = 'template'
                self.logger.info(
                    f"Located {description} via template at ({target['x']}, {target['y']})"
                )
                return target

        # Method 2: OCR text position
        if texts:
            result = self.ocr.detect_text_position(texts, region)
            if result:
                target = self._apply_offset(result, offset)
                target['method'] = 'ocr'
                self.logger.info(
                    f"Located {description} via OCR at ({target['x']}, {target['y']})"
                )
                return target

        # Method 3: fixed coordinates (previous behavior)
        if fallback_point:
            self.logger.info(
                f"Falling back to fixed coordinates for {description}: "
                f"({fallback_point['x']}, {fallback_point['y']})"
            )
            return {'x': fallback_point['x'], 'y': fallback_point['y'], 'method': 'fixed'}

        self.logger.warning(f"Could not locate {description} by any method")
        return None

    @staticmethod
    def _apply_offset(position, offset):
        """Apply an optional {x, y} offset to a detected position."""
        target = {'x': position['x'], 'y': position['y']}
        if offset:
            target['x'] += offset.get('x', 0)
            target['y'] += offset.get('y', 0)
        return target

    def click_and_verify(self, description, verify=None, verify_timeout=8,
                         attempts=2, settle_wait=timings.ACTION_SETTLE_WAIT,
                         **locate_kwargs):
        """
        Locate an element, click it, and verify the expected state was reached.

        If verification fails, the element is re-located and re-clicked up to
        `attempts` times (the screen may have needed longer, or the click may
        have missed / been swallowed by a popup).

        Args:
            description: Human-readable element name for logging
            verify (callable, optional): Zero-arg predicate that must return
                True after the click. If None, the click is trusted after
                settle_wait (still better than before: locating can fail loudly).
            verify_timeout (float): Seconds to poll the verify predicate per attempt
            attempts (int): Total locate+click attempts
            settle_wait (float): Seconds to let the UI settle after each click
            **locate_kwargs: Passed to locate() (template, texts, region,
                fallback_point, offset, ...)

        Returns:
            bool: True if clicked (and verified, when a verifier was given)
        """
        for attempt in range(1, attempts + 1):
            if self.check_stop_requested():
                return False

            target = self.locate(description, **locate_kwargs)
            if target is None:
                return False

            if not self.bluestacks.click(target['x'], target['y'], self.click_delay_ms):
                self.logger.error(f"ADB click failed for {description}")
                return False

            time.sleep(settle_wait)

            if verify is None:
                return True

            if self.screen.wait_for(verify, timeout=verify_timeout,
                                    description=f"result of clicking {description}"):
                return True

            self.logger.warning(
                f"Clicking {description} did not reach the expected state "
                f"(attempt {attempt}/{attempts})"
            )

            # Safety net: a stray click (e.g. a stale fixed coordinate) can
            # open a gems purchase confirmation. Dismiss it with escape (=No)
            # before retrying so the retry can't land on the Confirm button.
            if attempt < attempts and self.screen.is_cost_confirm_dialog():
                self.logger.warning(
                    "Cost-confirmation dialog opened by the previous click - "
                    "dismissing it before retrying"
                )
                self.bluestacks.send_escape()
                time.sleep(timings.ACTION_SETTLE_WAIT)

        self.logger.error(
            f"Failed to reach expected state after clicking {description} "
            f"{attempts} time(s)"
        )
        return False

#!/usr/bin/env python3
"""
Recovery Manager - Handles error recovery and retry logic.

This module provides:
- Return-to-home recovery from any screen state
- Retry decorator for wrapping operations with automatic recovery
"""
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps

import timings
from automation_base import StopCheckMixin
from screen_detector import GameScreen


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 2
    recover_to_home: bool = True
    delay_between_retries: float = 2.0


class RecoveryManager(StopCheckMixin):
    """Manages error recovery and screen state detection."""

    STOP_CONTEXT = "recovery"

    def __init__(self, screen_detector, bluestacks, coords,
                 click_delay_ms=1000, stop_check_callback=None):
        """
        Initialize the recovery manager.

        Args:
            screen_detector: ScreenDetector instance for screen state checks
            bluestacks: BlueStacksController instance for input
            coords: CoordinateManager instance for coordinates
            click_delay_ms: Delay between clicks in milliseconds
            stop_check_callback: Optional callback to check if automation should stop
        """
        self.logger = logging.getLogger(__name__)
        self.screen = screen_detector
        self.bluestacks = bluestacks
        self.coords = coords
        self.click_delay_ms = click_delay_ms
        self.stop_check = stop_check_callback

        # Navigation coordinates
        self.map_button = coords.get_nav('map_button')
        self.exit_dialog_cancel = coords.get_nav('exit_dialog_cancel')

    def get_current_screen(self) -> GameScreen:
        """
        Detect the current game screen state.

        Delegates to ScreenDetector.detect_screen() which takes a single
        ADB screenshot and runs all checks against it.

        Returns:
            GameScreen: The detected screen state
        """
        if self.check_stop_requested():
            return GameScreen.UNKNOWN

        result = self.screen.detect_screen()
        self.logger.debug(f"Detected: {result.name}")
        return result

    def return_to_home(self, max_attempts: int = 8) -> bool:
        """
        Attempt to return to home village screen from any state.

        Strategy: spam the back button until the "Exit the game?" dialog
        appears (meaning we've reached the outermost level), then dismiss
        it.  After dismissal we're either in home village or on the map;
        if on the map, toggle once to get home.

        Args:
            max_attempts: Maximum number of back-button presses

        Returns:
            bool: True if successfully returned to home, False otherwise
        """
        for attempt in range(max_attempts):
            if self.check_stop_requested():
                return False

            current_screen = self.get_current_screen()
            self.logger.info(
                f"Recovery attempt {attempt + 1}/{max_attempts}: "
                f"{current_screen.name}"
            )

            if current_screen == GameScreen.HOME_VILLAGE:
                self.logger.info("Successfully returned to home village")
                return True

            if current_screen == GameScreen.EXIT_GAME_DIALOG:
                self._dismiss_exit_dialog()
                time.sleep(timings.ACTION_SETTLE_WAIT)

                landed = self.get_current_screen()
                if landed == GameScreen.HOME_VILLAGE:
                    self.logger.info("Successfully returned to home village")
                    return True
                if landed == GameScreen.MAP_SCREEN:
                    self.logger.info("Landed on map, toggling to home village")
                    self.bluestacks.click(
                        self.map_button['x'],
                        self.map_button['y'],
                        self.click_delay_ms,
                    )
                    time.sleep(timings.MAP_LOAD_WAIT)
                    return True
                continue

            self.bluestacks.send_escape()
            time.sleep(timings.ACTION_SETTLE_WAIT)

        self.logger.error(f"Failed to return to home after {max_attempts} attempts")
        return False

    def _dismiss_exit_dialog(self):
        """Click Cancel on the 'Exit the game?' dialog."""
        self.logger.info("Exit dialog detected — clicking Cancel")
        cancel = self.screen.ocr.detect_text_position(
            ["CANCEL", "Cancel"],
            self.coords.get_region('exit_dialog'),
        ) or self.exit_dialog_cancel
        self.bluestacks.click(cancel['x'], cancel['y'], self.click_delay_ms)


def with_retry(config: RetryConfig | None = None):
    """
    Decorator that adds retry logic with optional recovery.

    When a decorated method returns False or raises an exception,
    this decorator will attempt recovery and retry the operation.

    Args:
        config: RetryConfig instance, uses defaults if None

    Usage:
        @with_retry(RetryConfig(max_retries=2, recover_to_home=True))
        def perform_build(self, ...):
            ...
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    result = func(self, *args, **kwargs)
                    if result:  # Success
                        return True

                    # Function returned False - try recovery if not last attempt
                    if attempt < config.max_retries:
                        self.logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/"
                            f"{config.max_retries + 1}), attempting recovery"
                        )

                        if config.recover_to_home:
                            recovery = getattr(self, 'recovery', None)
                            if recovery:
                                recovery.return_to_home()

                        time.sleep(config.delay_between_retries)

                except Exception as e:
                    last_exception = e
                    self.logger.error(f"{func.__name__} raised exception: {e}")

                    if attempt < config.max_retries:
                        if config.recover_to_home:
                            recovery = getattr(self, 'recovery', None)
                            if recovery:
                                recovery.return_to_home()
                        time.sleep(config.delay_between_retries)

            # All retries exhausted
            self.logger.error(
                f"{func.__name__} failed after {config.max_retries + 1} attempts"
            )
            if last_exception:
                self.logger.error(f"Last exception: {last_exception}")
            return False

        return wrapper
    return decorator

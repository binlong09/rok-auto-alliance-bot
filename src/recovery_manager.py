#!/usr/bin/env python3
"""
Recovery Manager - Handles error recovery and retry logic.

This module provides:
- Unified screen state detection via GameScreen enum
- Return-to-home recovery from any screen state
- Retry decorator for wrapping operations with automatic recovery
"""
import time
import logging
from enum import Enum, auto
from functools import wraps
from dataclasses import dataclass
from typing import Callable, Optional


class GameScreen(Enum):
    """Possible game screens the bot can detect."""
    HOME_VILLAGE = auto()      # Safe state - Age text visible
    MAP_SCREEN = auto()        # World map view - kingdom numbers visible
    CHARACTER_LOGIN = auto()   # Character selection/login screen
    ALLIANCE_MENU = auto()     # Alliance screen open
    DIALOG_OPEN = auto()       # Some dialog/popup is open
    UNKNOWN = auto()           # Cannot determine screen state


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_retries: int = 2
    recover_to_home: bool = True
    delay_between_retries: float = 2.0


class RecoveryManager:
    """Manages error recovery and screen state detection."""

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

    def check_stop_requested(self):
        """Check if automation should stop."""
        if self.stop_check and self.stop_check():
            self.logger.info("Stop requested during recovery")
            return True
        return False

    def get_current_screen(self) -> GameScreen:
        """
        Detect the current game screen state.

        Runs OCR-based detection checks in priority order (most specific first).
        This is slow (~2-3s) but reliable due to multiple preprocessing methods.

        Returns:
            GameScreen: The detected screen state
        """
        if self.check_stop_requested():
            return GameScreen.UNKNOWN

        # Check in order of specificity (most unique text first)
        # Each check uses OCR with 5 preprocessing methods internally

        if self.screen.is_in_character_login():
            self.logger.debug("Detected: CHARACTER_LOGIN")
            return GameScreen.CHARACTER_LOGIN

        if self.screen.is_char_in_alliance():
            self.logger.debug("Detected: ALLIANCE_MENU")
            return GameScreen.ALLIANCE_MENU

        if self.screen.is_in_home_village():
            self.logger.debug("Detected: HOME_VILLAGE")
            return GameScreen.HOME_VILLAGE

        if self.screen.is_in_map_screen():
            self.logger.debug("Detected: MAP_SCREEN")
            return GameScreen.MAP_SCREEN

        if self.screen.is_bottom_bar_expanded():
            self.logger.debug("Detected: DIALOG_OPEN")
            return GameScreen.DIALOG_OPEN

        self.logger.debug("Detected: UNKNOWN")
        return GameScreen.UNKNOWN

    def return_to_home(self, max_attempts: int = 5) -> bool:
        """
        Attempt to return to home village screen from any state.

        Uses a state machine approach:
        - Detect current screen
        - Apply screen-specific recovery action
        - Re-detect and repeat until home or max attempts

        Args:
            max_attempts: Maximum number of recovery attempts

        Returns:
            bool: True if successfully returned to home, False otherwise
        """
        for attempt in range(max_attempts):
            if self.check_stop_requested():
                return False

            current_screen = self.get_current_screen()
            self.logger.info(
                f"Recovery attempt {attempt + 1}/{max_attempts}: "
                f"Current screen: {current_screen.name}"
            )

            if current_screen == GameScreen.HOME_VILLAGE:
                self.logger.info("Successfully returned to home village")
                return True

            # Apply recovery action based on current screen
            if current_screen == GameScreen.MAP_SCREEN:
                # Click map button to toggle back to home
                self.logger.info("On map screen, clicking map button to return home")
                self.bluestacks.click(
                    self.map_button['x'],
                    self.map_button['y'],
                    self.click_delay_ms
                )
                time.sleep(2)

            elif current_screen == GameScreen.CHARACTER_LOGIN:
                # Multiple escapes needed to exit character selection
                self.logger.info("On character login, sending 3 escape keys")
                for _ in range(3):
                    self.bluestacks.send_escape()
                    time.sleep(1)
                time.sleep(1)

            elif current_screen == GameScreen.ALLIANCE_MENU:
                # Two escapes to close alliance menu
                self.logger.info("On alliance menu, sending 2 escape keys")
                for _ in range(2):
                    self.bluestacks.send_escape()
                    time.sleep(1)

            elif current_screen == GameScreen.DIALOG_OPEN:
                # Single escape for general dialogs
                self.logger.info("Dialog open, sending escape key")
                self.bluestacks.send_escape()
                time.sleep(1)

            else:  # UNKNOWN
                # Blind escape attempt
                self.logger.info("Unknown screen, sending escape key")
                self.bluestacks.send_escape()
                time.sleep(1.5)

        self.logger.error(f"Failed to return to home after {max_attempts} attempts")
        return False


def with_retry(config: Optional[RetryConfig] = None):
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

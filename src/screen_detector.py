#!/usr/bin/env python3
"""
Screen Detector - Detects current game screen states.

This module handles detection of various game screens and UI states
using OCR to identify text on screen.
"""
import logging


class ScreenDetector:
    """Detects current game screen states using OCR."""

    def __init__(self, ocr_helper, coords, stop_check_callback=None):
        """
        Initialize the screen detector.

        Args:
            ocr_helper: OCRHelper instance for text detection
            coords: CoordinateManager instance for regions
            stop_check_callback: Optional callback to check if automation should stop
        """
        self.logger = logging.getLogger(__name__)
        self.ocr = ocr_helper
        self.coords = coords
        self.stop_check = stop_check_callback

    def check_stop_requested(self):
        """Check if automation should stop."""
        if self.stop_check and self.stop_check():
            self.logger.info("Stop requested during screen detection")
            return True
        return False

    def is_in_home_village(self, custom_region=None):
        """
        Check if the game is currently showing the home village.

        Args:
            custom_region (dict, optional): Custom region to look in.

        Returns:
            bool: True if in home village, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Age-related keywords indicate home village
        age_keywords = ["Feudal Age", "Dark Age", "Iron Age", "Bronze Age", "Stone Age"]

        result = self.ocr.detect_text_in_region(age_keywords, custom_region)

        if result:
            self.logger.info("Currently in home village")
        else:
            self.logger.info("Not in home village")

        return result

    def is_in_map_screen(self):
        """
        Check if the game is currently showing the map screen.

        Returns:
            bool: True if in map screen, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Check for kingdom number
        keywords = ["3174", "1960", "3494"]
        region = self.coords.get_region('kingdom_check')

        result = self.ocr.detect_text_in_region(keywords, region)

        if result:
            self.logger.info("Currently in map screen")
        else:
            self.logger.info("Not in map screen")

        return result

    def is_in_character_login(self, custom_keywords=None):
        """
        Check if the game is currently showing the character login screen.

        Args:
            custom_keywords (list, optional): Custom keywords to look for.

        Returns:
            bool: True if in character login screen, False otherwise
        """
        if self.check_stop_requested():
            return False

        keywords = ["Character Login", "Log in"]
        keywords_to_check = custom_keywords if custom_keywords is not None else keywords

        region = self.coords.get_region('character_login')
        result = self.ocr.detect_text_in_region(keywords_to_check, region)

        if result:
            self.logger.info("Currently in Character Login Screen")
        else:
            self.logger.info("Not in Character Login Screen")

        return result

    def is_bottom_bar_expanded(self):
        """
        Check if the bottom navigation bar is expanded.

        Returns:
            bool: True if bottom bar is expanded, False otherwise
        """
        if self.check_stop_requested():
            return False

        keywords = ["Campaign", "Items", "Alliance", "Commander", "Mail"]
        region = self.coords.get_region('bottom_bar')

        result = self.ocr.detect_text_in_region(keywords, region)

        if result:
            self.logger.info("Bottom bar is already expanded")
        else:
            self.logger.info("Bottom bar is not expanded")

        return result

    def is_char_in_alliance(self):
        """
        Detect if this account is in an alliance.

        Returns:
            bool: True if in alliance, False otherwise
        """
        if self.check_stop_requested():
            return False

        keywords = ["Technology", "Territory"]
        region = self.coords.get_region('alliance_check')

        result = self.ocr.detect_text_in_region(keywords, region)

        if result:
            self.logger.info("Account is in an alliance")
        else:
            self.logger.info("Account is not in an alliance")

        return result

    def is_exit_game_dialog(self):
        """
        Detect if the "Exit the game?" dialog is showing.

        This dialog appears when pressing Escape on the home screen.
        It has NOTICE title and "Exit the game?" text with CONFIRM/CANCEL buttons.

        Returns:
            bool: True if exit dialog is showing, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Look for "Exit" or "NOTICE" text in the dialog region
        keywords = ["Exit", "exit", "NOTICE", "Notice"]
        region = self.coords.get_region('exit_dialog')

        result = self.ocr.detect_text_in_region(keywords, region)

        if result:
            self.logger.info("Exit game dialog detected")
        else:
            self.logger.debug("Exit game dialog not present")

        return result

    def is_rewards_dialog(self):
        """
        Detect if the "Rewards" dialog is showing.

        This dialog appears after collecting expedition rewards.
        We check for "CONFIRM" button instead of "Rewards" text because
        the Expedition screen has "First Completion Rewards" and "Daily Rewards"
        text that causes false positives.

        Returns:
            bool: True if rewards dialog is showing, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Look for "CONFIRM" button text - unique to the rewards dialog
        keywords = ["CONFIRM", "Confirm", "confirm"]
        region = self.coords.get_region('rewards_dialog')

        result = self.ocr.detect_text_in_region(keywords, region)

        if result:
            self.logger.info("Rewards dialog detected (CONFIRM button found)")
        else:
            self.logger.debug("Rewards dialog not present")

        return result

    def is_loading_screen(self):
        """
        Detect if the game is showing the loading screen.

        The loading screen shows "Loading X%" text at the bottom center.

        Returns:
            bool: True if loading screen is showing, False otherwise
        """
        if self.check_stop_requested():
            return False

        keywords = ["Loading", "loading", "LOADING"]
        region = self.coords.get_region('loading_screen')

        result = self.ocr.detect_text_in_region(keywords, region)

        if result:
            self.logger.debug("Loading screen detected")
        else:
            self.logger.debug("Loading screen not present")

        return result

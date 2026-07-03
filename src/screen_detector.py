#!/usr/bin/env python3
"""
Screen Detector - Detects current game screen states.

This module handles detection of various game screens and UI states
using OCR to identify text on screen.
"""
import logging
import time
from enum import Enum, auto

import timings
from automation_base import StopCheckMixin


class GameScreen(Enum):
    """Possible game screens the bot can detect."""
    HOME_VILLAGE = auto()
    MAP_SCREEN = auto()
    CHARACTER_LOGIN = auto()
    CHARACTER_SELECTION = auto()
    SETTINGS_MENU = auto()
    ALLIANCE_MENU = auto()
    EXIT_GAME_DIALOG = auto()
    DIALOG_OPEN = auto()
    UNKNOWN = auto()


class ScreenDetector(StopCheckMixin):
    """Detects current game screen states using OCR."""

    STOP_CONTEXT = "screen detection"

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

    def wait_for(self, predicate, timeout=10, interval=timings.POLL_INTERVAL,
                 description="screen state"):
        """
        Poll a screen-state predicate until it returns True or timeout.

        This is the core primitive for state-aware navigation: instead of
        clicking and sleeping a fixed time, callers click and then wait
        until the expected screen is actually visible.

        Args:
            predicate: Zero-arg callable returning bool (e.g. self.is_in_map_screen)
            timeout (float): Max seconds to wait
            interval (float): Seconds between checks
            description (str): What we're waiting for, used in log messages

        Returns:
            bool: True if the predicate became True within the timeout
        """
        deadline = time.time() + timeout

        while True:
            if self.check_stop_requested():
                return False

            if predicate():
                self.logger.info(f"Reached expected state: {description}")
                return True

            if time.time() >= deadline:
                self.logger.warning(f"Timed out after {timeout}s waiting for {description}")
                return False

            time.sleep(interval)

    def is_in_home_village(self, custom_region=None, screenshot=None):
        """
        Check if the game is currently showing the home village.

        Primary check: the bottom-left view-toggle button shows a MAP icon
        while in the home village (template 'home_anchor'). This is far more
        reliable than OCR-ing the small "Bronze Age"-style text, which sits
        on a noisy wooden background and often fails to recognize.

        Args:
            custom_region (dict, optional): Custom region for the OCR fallback.
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if in home village, False otherwise
        """
        if self.check_stop_requested():
            return False

        anchor_region = self.coords.get_region('nav_anchor')
        if self.ocr.find_template('home_anchor', region=anchor_region,
                                  screenshot=screenshot):
            self.logger.info("Currently in home village (map-toggle anchor)")
            return True

        # OCR fallback: age-related keywords in the (tight) age text area
        age_keywords = ["Feudal Age", "Dark Age", "Iron Age", "Bronze Age", "Stone Age"]
        region = custom_region if custom_region is not None \
            else self.coords.get_region('age_text')

        result = self.ocr.detect_text_in_region(age_keywords, region,
                                                screenshot=screenshot)

        if result:
            self.logger.info("Currently in home village")
        else:
            self.logger.info("Not in home village")

        return result

    def is_in_map_screen(self, screenshot=None):
        """
        Check if the game is currently showing the map screen.

        Rather than checking for a hardcoded list of kingdom numbers (which
        only works for a handful of specific kingdoms), this looks for
        kingdom-agnostic signals in the kingdom_check region:
          1. Coordinate-style numbers (kingdom coords are always 3-4 digit
             numbers, and the map screen shows at least two of them, e.g.
             the kingdom number and the X/Y position).
          2. Generic map UI text ("Kingdom", "K:") as a fallback in case the
             numbers aren't cleanly OCR'd.

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if in map screen, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Primary check: the bottom-left view-toggle button shows a CASTLE
        # icon while on the map (template 'map_anchor').
        anchor_region = self.coords.get_region('nav_anchor')
        if self.ocr.find_template('map_anchor', region=anchor_region,
                                  screenshot=screenshot):
            self.logger.info("Currently in map screen (castle-toggle anchor)")
            return True

        region = self.coords.get_region('kingdom_check')

        # Generic map UI keywords that aren't tied to a specific kingdom.
        keywords = ["Kingdom", "kingdom", "K:", "k:"]

        # At least two 3-4 digit numbers (kingdom number + coordinate)
        # reliably indicates the map screen regardless of which kingdom
        # the player is in.
        result = self.ocr.detect_pattern_in_region(
            r'\d{3,4}', region, min_matches=2, screenshot=screenshot
        ) or self.ocr.detect_text_in_region(keywords, region, screenshot=screenshot)

        if result:
            self.logger.info("Currently in map screen")
        else:
            self.logger.info("Not in map screen")

        return result

    def is_in_character_login(self, custom_keywords=None, screenshot=None):
        """
        Check if the game is currently showing the character login screen.

        Args:
            custom_keywords (list, optional): Custom keywords to look for.
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if in character login screen, False otherwise
        """
        if self.check_stop_requested():
            return False

        keywords = ["Character Login", "Log in"]
        keywords_to_check = custom_keywords if custom_keywords is not None else keywords

        region = self.coords.get_region('character_login')
        result = self.ocr.detect_text_in_region(keywords_to_check, region,
                                                screenshot=screenshot)

        if result:
            self.logger.info("Currently in Character Login Screen")
        else:
            self.logger.info("Not in Character Login Screen")

        return result

    def is_bottom_bar_expanded(self, screenshot=None):
        """
        Check if the bottom navigation bar is expanded.

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if bottom bar is expanded, False otherwise
        """
        if self.check_stop_requested():
            return False

        region = self.coords.get_region('bottom_bar')

        # Primary check: the Alliance shield icon is only visible when the
        # bar is expanded. Template matching here is deterministic, unlike
        # OCR on the small icon labels which can false-positive against the
        # game world behind a collapsed bar.
        if self.ocr.templates.has_template('alliance_icon'):
            result = self.ocr.find_template('alliance_icon', region=region,
                                            screenshot=screenshot) is not None
        else:
            keywords = ["Campaign", "Items", "Alliance", "Commander", "Mail"]
            result = self.ocr.detect_text_in_region(keywords, region,
                                                    screenshot=screenshot)

        if result:
            self.logger.info("Bottom bar is already expanded")
        else:
            self.logger.info("Bottom bar is not expanded")

        return result


    def is_in_profile_menu(self, screenshot=None):
        """
        Detect the profile/governor menu (opened by clicking the avatar).

        The profile screen shows a Settings button in its lower-right area.

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the profile menu is open
        """
        if self.check_stop_requested():
            return False

        keywords = ["Settings", "Setting"]
        region = self.coords.get_region('profile_menu')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Profile menu is open" if result else "Profile menu not detected")
        return result

    def is_in_settings_screen(self, screenshot=None):
        """
        Detect the Settings screen (contains Characters / Account / Language...).

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the settings screen is open
        """
        if self.check_stop_requested():
            return False

        keywords = ["Characters", "Character Management", "Account", "Language", "Notification"]
        region = self.coords.get_region('settings_screen')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Settings screen is open" if result else "Settings screen not detected")
        return result

    def is_in_character_selection(self, screenshot=None):
        """
        Detect the character selection/management list screen.

        Each character card shows a kingdom number and power value, and the
        screen has a Characters title.

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the character selection screen is open
        """
        if self.check_stop_requested():
            return False

        keywords = ["Characters", "Power", "Kingdom", "Create"]
        region = self.coords.get_region('character_selection')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Character selection screen is open" if result
                         else "Character selection screen not detected")
        return result

    def is_in_tech_screen(self, screenshot=None):
        """
        Detect the alliance technology screen.

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the technology donation screen is open
        """
        if self.check_stop_requested():
            return False

        keywords = ["Recommendation", "Recommended", "Research", "Donate"]
        region = self.coords.get_region('officer_recommendation')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Alliance tech screen is open" if result
                         else "Alliance tech screen not detected")
        return result

    def is_in_territory_screen(self, screenshot=None):
        """
        Detect the Alliance Territory screen.

        The screen has an "ALLIANCE TERRITORY" title and a
        "Territory Resource Earnings" claim row at the top.

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the alliance territory screen is open
        """
        if self.check_stop_requested():
            return False

        keywords = ["ALLIANCE TERRITORY", "Territory Resource", "Earnings"]
        region = self.coords.get_region('territory_screen')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Alliance territory screen is open" if result
                         else "Alliance territory screen not detected")
        return result

    def is_in_donate_dialog(self, screenshot=None):
        """
        Detect the technology donate dialog (per-tech popup with Donate button).

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the donate dialog is open
        """
        if self.check_stop_requested():
            return False

        keywords = ["Donate", "Donation"]
        region = self.coords.get_region('donate_dialog')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Donate dialog is open" if result else "Donate dialog not detected")
        return result

    def is_in_campaign_screen(self, screenshot=None):
        """
        Detect the Campaign screen (entry point to Expedition).

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the campaign screen is open
        """
        if self.check_stop_requested():
            return False

        keywords = ["Expedition", "Conquest", "Campaign", "Lost Kingdom"]
        region = self.coords.get_region('campaign_screen')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Campaign screen is open" if result else "Campaign screen not detected")
        return result

    def is_in_expedition_screen(self, screenshot=None):
        """
        Detect the Expedition screen (chapter rewards / chests).

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the expedition screen is open
        """
        if self.check_stop_requested():
            return False

        # The screen has an "EXPEDITION" title bar at the top center
        keywords = ["EXPEDITION", "Expedition"]
        region = self.coords.get_region('expedition_screen')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Expedition screen is open" if result else "Expedition screen not detected")
        return result

    def is_in_bookmark_screen(self, screenshot=None):
        """
        Detect the bookmarks/favorites screen (used to find the build flag).

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the bookmark screen is open
        """
        if self.check_stop_requested():
            return False

        keywords = ["Bookmark", "Bookmarks", "Favorites", "troop"]
        region = self.coords.get_region('bookmark_screen')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Bookmark screen is open" if result else "Bookmark screen not detected")
        return result

    def is_in_account_screen(self, screenshot=None):
        """
        Detect the account management screen (Settings > Account).

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the account screen is open
        """
        if self.check_stop_requested():
            return False

        # The Lilith "User Center" page shows the current UID, a
        # "Switch Accounts" button and tiles (Accounts / Manage Devices...).
        keywords = ["User Center", "Switch Accounts", "UID", "Member Center",
                    "Manage Devices"]
        region = self.coords.get_region('account_screen')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Account screen is open" if result else "Account screen not detected")
        return result

    def is_in_switch_accounts_dialog(self, screenshot=None):
        """
        Detect the "Switch Accounts" dialog (User Center > Switch Accounts).

        The dialog shows a saved-account dropdown, a Login button and a
        "Log in to another account" link - the link text is the only string
        unique to the dialog (the page behind it also says "Switch Accounts").

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the switch-accounts dialog is open
        """
        if self.check_stop_requested():
            return False

        keywords = ["Log in to another account", "another account"]
        region = self.coords.get_region('switch_accounts_dialog')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Switch Accounts dialog is open" if result
                         else "Switch Accounts dialog not detected")
        return result

    def is_in_login_screen(self, screenshot=None):
        """
        Detect the out-of-game account login screen (after logging out).

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if the account login screen is showing
        """
        if self.check_stop_requested():
            return False

        keywords = ["Log In", "Login", "Sign in", "Lilith", "Guest", "Switch Account"]
        region = self.coords.get_region('login_screen')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)
        self.logger.info("Account login screen detected" if result
                         else "Account login screen not detected")
        return result

    def is_cost_confirm_dialog(self, screenshot=None):
        """
        Detect a purchase-confirmation dialog ("This will cost N Gems.
        Continue?"). A stray click on the wrong button can open one of
        these; it must be dismissed (escape = No) and NEVER confirmed.

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if a cost-confirmation dialog is showing
        """
        if self.check_stop_requested():
            return False

        keywords = ["Continue?", "will cost", "Gems. Continue"]
        region = self.coords.get_region('exit_dialog')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)

        if result:
            self.logger.warning("Cost-confirmation dialog detected (gems purchase)")
        else:
            self.logger.debug("No cost-confirmation dialog")

        return result

    def is_exit_game_dialog(self, screenshot=None):
        """
        Detect if the "Exit the game?" dialog is showing.

        This dialog appears when pressing Escape on the home screen.
        It has NOTICE title and "Exit the game?" text with CONFIRM/CANCEL buttons.

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if exit dialog is showing, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Look for "Exit" or "NOTICE" text in the dialog region
        keywords = ["Exit", "exit", "NOTICE", "Notice"]
        region = self.coords.get_region('exit_dialog')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)

        if result:
            self.logger.info("Exit game dialog detected")
        else:
            self.logger.debug("Exit game dialog not present")

        return result

    def is_rewards_dialog(self, screenshot=None):
        """
        Detect if the "Rewards" dialog is showing.

        This dialog appears after collecting expedition rewards.
        We check for "CONFIRM" button instead of "Rewards" text because
        the Expedition screen has "First Completion Rewards" and "Daily Rewards"
        text that causes false positives.

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if rewards dialog is showing, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Look for "CONFIRM" button text - unique to the rewards dialog
        keywords = ["CONFIRM", "Confirm", "confirm"]
        region = self.coords.get_region('rewards_dialog')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)

        if result:
            self.logger.info("Rewards dialog detected (CONFIRM button found)")
        else:
            self.logger.debug("Rewards dialog not present")

        return result

    def is_loading_screen(self, screenshot=None):
        """
        Detect if the game is showing the loading screen.

        The loading screen shows "Loading X%" text at the bottom center.

        Args:
            screenshot (numpy array, optional): Pre-captured screenshot to reuse.

        Returns:
            bool: True if loading screen is showing, False otherwise
        """
        if self.check_stop_requested():
            return False

        keywords = ["Loading", "loading", "LOADING"]
        region = self.coords.get_region('loading_screen')

        result = self.ocr.detect_text_in_region(keywords, region,
                                                screenshot=screenshot)

        if result:
            self.logger.debug("Loading screen detected")
        else:
            self.logger.debug("Loading screen not present")

        return result

    # ------------------------------------------------------------------
    # Composite detection
    # ------------------------------------------------------------------

    def take_screenshot(self):
        """Take a single ADB screenshot for reuse across multiple checks."""
        return self.ocr.bluestacks.take_screenshot()

    def detect_screen(self) -> GameScreen:
        """
        Detect which game screen is currently showing.

        Takes ONE screenshot and runs all detection checks against it,
        avoiding the cost of repeated ADB screencaps. Template matches
        run first (~5-20 ms each) before falling back to OCR.

        Returns:
            GameScreen: The detected screen state
        """
        if self.check_stop_requested():
            return GameScreen.UNKNOWN

        screenshot = self.take_screenshot()
        if screenshot is None:
            return GameScreen.UNKNOWN

        if self.is_exit_game_dialog(screenshot=screenshot):
            return GameScreen.EXIT_GAME_DIALOG

        if self.is_in_character_login(screenshot=screenshot):
            return GameScreen.CHARACTER_LOGIN

        if self.is_in_character_selection(screenshot=screenshot):
            return GameScreen.CHARACTER_SELECTION

        if self.is_in_settings_screen(screenshot=screenshot):
            return GameScreen.SETTINGS_MENU

        if self.is_in_home_village(screenshot=screenshot):
            return GameScreen.HOME_VILLAGE

        if self.is_in_map_screen(screenshot=screenshot):
            return GameScreen.MAP_SCREEN

        if self.is_bottom_bar_expanded(screenshot=screenshot):
            return GameScreen.DIALOG_OPEN

        return GameScreen.UNKNOWN

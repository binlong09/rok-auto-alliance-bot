#!/usr/bin/env python3
"""Screen Router - state-aware navigation between game screens.

The tasks used to hand-roll their navigation ("expand the bar, click
alliance, hope") and assumed they started from the screen the previous
task left behind. One leftover dialog derailed everything after it.

This module models the game's screens as a small tree rooted at the
home village and navigates by *observed state*, not assumption:

    goto(target):
        loop:
            where am I?  (ScreenDetector.detect_screen - one screenshot)
            at target        -> done
            on the path      -> take the next edge (verified click)
            anywhere else    -> step toward home (state-aware dismiss)

Any task can therefore start from any screen, including screens the bot
has no name for (UNKNOWN) - those get dismissed with escape and the
screenshot is saved to debug_output so new screens can be identified
and added over time.
"""
import logging
import os
import time

import cv2

import timings
from automation_base import StopCheckMixin
from screen_detector import GameScreen

_DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_output")


class ScreenRouter(StopCheckMixin):
    """Navigate to a target screen from wherever the game currently is."""

    STOP_CONTEXT = "screen navigation"

    def __init__(self, screen_detector, bluestacks, coords, navigator,
                 click_delay_ms=1000, stop_check_callback=None):
        """
        Args:
            screen_detector: ScreenDetector (detect_screen + predicates)
            bluestacks: BlueStacksController for input
            coords: CoordinateManager
            navigator: VerifiedNavigator for located, verified clicks
            click_delay_ms: Delay after each click in milliseconds
            stop_check_callback: Optional stop-requested callback
        """
        self.logger = logging.getLogger(__name__)
        self.screen = screen_detector
        self.bluestacks = bluestacks
        self.coords = coords
        self.nav = navigator
        self.click_delay_ms = click_delay_ms
        self.stop_check = stop_check_callback

        S = GameScreen
        # Paths from home to every reachable target. goto() walks these
        # edge by edge; being anywhere off-path routes toward home first.
        self._paths = {
            S.HOME_VILLAGE: [S.HOME_VILLAGE],
            S.MAP_SCREEN: [S.HOME_VILLAGE, S.MAP_SCREEN],
            S.BOOKMARKS: [S.HOME_VILLAGE, S.MAP_SCREEN, S.BOOKMARKS],
            S.ALLIANCE_MENU: [S.HOME_VILLAGE, S.ALLIANCE_MENU],
            S.TERRITORY: [S.HOME_VILLAGE, S.ALLIANCE_MENU, S.TERRITORY],
            S.TECH: [S.HOME_VILLAGE, S.ALLIANCE_MENU, S.TECH],
            S.CAMPAIGN: [S.HOME_VILLAGE, S.CAMPAIGN],
            S.EXPEDITION: [S.HOME_VILLAGE, S.CAMPAIGN, S.EXPEDITION],
        }
        self._edges = {
            (S.HOME_VILLAGE, S.MAP_SCREEN): self._toggle_home_map,
            (S.MAP_SCREEN, S.BOOKMARKS): self._open_bookmarks,
            (S.HOME_VILLAGE, S.ALLIANCE_MENU): self._open_alliance,
            (S.ALLIANCE_MENU, S.TERRITORY): self._open_territory,
            (S.ALLIANCE_MENU, S.TECH): self._open_tech,
            (S.HOME_VILLAGE, S.CAMPAIGN): self._open_campaign,
            (S.CAMPAIGN, S.EXPEDITION): self._open_expedition,
        }
        # Identify against every screen the router knows, not just the
        # current path: a leftover overlay (e.g. Markers over the map)
        # must be recognized as itself, not as the screen visible
        # beneath it.
        self._known_screens = set().union(*self._paths.values())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def goto(self, target: GameScreen, max_steps: int = 12) -> bool:
        """
        Navigate to `target` from whatever screen the game is on.

        Args:
            target: The screen to reach (must be in the known path map)
            max_steps: Safety cap on identify->act iterations

        Returns:
            bool: True when the target screen is reached and verified
        """
        if target not in self._paths:
            raise ValueError(f"No route to {target}; known targets: "
                             f"{sorted(s.name for s in self._paths)}")

        path = self._paths[target]
        candidates = self._known_screens

        for step in range(1, max_steps + 1):
            if self.check_stop_requested():
                return False

            current = self._identify(candidates)
            self.logger.info(f"goto({target.name}) step {step}/{max_steps}: "
                             f"currently on {current.name}")

            if current == target:
                return True

            if current in path:
                edge = self._edges[(current, path[path.index(current) + 1])]
                if not edge():
                    # Edge failed; loop re-identifies and re-routes.
                    self.logger.warning(
                        f"Edge {current.name} -> "
                        f"{path[path.index(current) + 1].name} failed; "
                        "re-identifying")
                continue

            self._step_toward_home(current)

        self.logger.error(f"Could not reach {target.name} in {max_steps} steps")
        return False

    # ------------------------------------------------------------------
    # State identification and recovery
    # ------------------------------------------------------------------

    def _identify(self, candidates) -> GameScreen:
        """Classify the current screen, checking likely candidates first
        and falling back to the full sweep on the same screenshot."""
        screenshot = self.screen.take_screenshot()
        if screenshot is None:
            return GameScreen.UNKNOWN

        result = self.screen.detect_screen(screenshot=screenshot,
                                           candidates=candidates)
        if result == GameScreen.UNKNOWN:
            result = self.screen.detect_screen(screenshot=screenshot)
        if result == GameScreen.UNKNOWN:
            self._save_unknown_screenshot(screenshot)
        return result

    def _save_unknown_screenshot(self, screenshot):
        """Keep evidence of unrecognized screens so they can be named
        and added to the classifier later."""
        try:
            os.makedirs(_DEBUG_DIR, exist_ok=True)
            path = os.path.join(
                _DEBUG_DIR, f"unknown_screen_{int(time.time())}.png")
            cv2.imwrite(path, screenshot)
            self.logger.warning(f"Unknown screen; screenshot saved to {path}")
        except Exception:
            self.logger.exception("Could not save unknown-screen screenshot")

    def _step_toward_home(self, current: GameScreen):
        """One state-aware step toward the home village."""
        if current == GameScreen.MAP_SCREEN:
            # Escape on the map only toggles the bottom bar - use the
            # view-toggle button instead.
            self._toggle_home_map()
            return
        if current == GameScreen.LOADING:
            self.logger.info("Loading screen; waiting...")
            time.sleep(timings.LONG_TRANSITION_WAIT)
            return
        # Dialogs and every other screen (incl. UNKNOWN): escape acts as
        # back/cancel. On EXIT_GAME_DIALOG escape means Cancel, which is
        # exactly what we want.
        self.bluestacks.send_escape()
        time.sleep(timings.ACTION_SETTLE_WAIT)

    # ------------------------------------------------------------------
    # Edges (verified transitions)
    # ------------------------------------------------------------------

    def _toggle_home_map(self):
        """Click the bottom-left view toggle (home <-> map)."""
        button = self.coords.get_nav('map_button')
        if not self.bluestacks.click(button['x'], button['y'],
                                     self.click_delay_ms):
            return False
        time.sleep(timings.MAP_LOAD_WAIT)
        return True

    def _open_bookmarks(self):
        return self.nav.click_and_verify(
            "bookmark button",
            template='bookmark_icon',
            fallback_point=self.coords.get_nav('bookmark_button'),
            verify=self.screen.is_in_bookmark_screen,
            verify_timeout=8,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        )

    def _ensure_bottom_bar_expanded(self):
        if self.screen.is_bottom_bar_expanded():
            return True
        return self.nav.click_and_verify(
            "expand bottom bar button",
            template='expand_button',
            fallback_point=self.coords.get_nav('expand_button'),
            verify=self.screen.is_bottom_bar_expanded,
            verify_timeout=5,
        )

    def _open_alliance(self):
        if not self._ensure_bottom_bar_expanded():
            return False
        return self.nav.click_and_verify(
            "Alliance button",
            template='alliance_icon',
            region=self.coords.get_region('bottom_bar'),
            fallback_point=self.coords.get_nav('alliance_button'),
            verify=self.screen.is_in_alliance_screen,
            verify_timeout=8,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        )

    def _open_territory(self):
        return self.nav.click_and_verify(
            "Territory button",
            template='territory_icon',
            texts=["Territory", "territory"],
            region=self.coords.get_region('alliance_menu'),
            # The label sits below the icon: click above the detected text
            offset={'x': 0, 'y': -50},
            fallback_point=self.coords.get_nav('territory_button'),
            verify=self.screen.is_in_territory_screen,
            verify_timeout=10,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        )

    def _open_tech(self):
        return self.nav.click_and_verify(
            "Technology button",
            template='technology_icon',
            texts=["Technology", "technology"],
            region=self.coords.get_region('alliance_menu'),
            offset={'x': 0, 'y': -50},
            fallback_point=self.coords.get_nav('technology_button'),
            verify=self.screen.is_in_tech_screen,
            verify_timeout=10,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        )

    def _open_campaign(self):
        if not self._ensure_bottom_bar_expanded():
            return False
        return self.nav.click_and_verify(
            "Campaign button",
            template='campaign_icon',
            texts=["Campaign", "campaign"],
            region=self.coords.get_region('bottom_bar'),
            offset={'x': 0, 'y': -30},
            fallback_point=self.coords.get_nav('campaign_button'),
            verify=self.screen.is_in_campaign_screen,
            verify_timeout=8,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        )

    def _open_expedition(self):
        return self.nav.click_and_verify(
            "Expedition banner",
            template='expedition_banner',
            texts=["Expedition", "EXPEDITION"],
            region=self.coords.get_region('campaign_screen'),
            verify=self.screen.is_in_expedition_screen,
            verify_timeout=8,
            settle_wait=timings.SCREEN_TRANSITION_WAIT,
        )

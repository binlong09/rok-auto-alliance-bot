"""Tests for ScreenRouter.goto() path walking and recovery.

A scripted FakeWorld stands in for the game: it holds a current screen,
fake navigator clicks advance it along configured transitions, and
escape applies a per-screen "back" map. The router must reach targets
from on-path screens, off-path screens, unknown screens, and blocking
dialogs - or give up cleanly at max_steps.
"""
import logging

import numpy as np
import pytest

import screen_router
from screen_detector import GameScreen as S
from screen_router import ScreenRouter

DIALOGS = {S.EXIT_GAME_DIALOG, S.COST_CONFIRM_DIALOG,
           S.REWARDS_DIALOG, S.DONATE_DIALOG}


class FakeWorld:
    """Game state machine: navigator descriptions and escapes move it."""

    def __init__(self, current, nav_transitions=None, escape_map=None,
                 nav_failures=None):
        self.current = current
        self.nav_transitions = nav_transitions or {}
        self.escape_map = escape_map or {}
        self.nav_failures = nav_failures or {}  # description -> fail count
        self.escapes = 0
        self.toggle_clicks = 0
        self.actions = []


class FakeDetector:
    DIALOG_SCREENS = DIALOGS

    def __init__(self, world):
        self.world = world
        self.bar_expanded = True

    def take_screenshot(self):
        return np.zeros((2, 2, 3), dtype=np.uint8)

    def detect_screen(self, screenshot=None, candidates=None):
        cur = self.world.current
        if candidates is not None and cur not in candidates and cur not in DIALOGS:
            return S.UNKNOWN
        return cur

    def is_bottom_bar_expanded(self, screenshot=None):
        return self.bar_expanded

    # Predicates handed to click_and_verify as verify= (unused: the fake
    # navigator does not call them, it just applies the transition).
    def __getattr__(self, name):
        if name.startswith("is_"):
            return lambda screenshot=None: False
        raise AttributeError(name)


class FakeBluestacks:
    def __init__(self, world):
        self.world = world

    def click(self, x, y, delay_ms=1000):
        # Only the home/map toggle is clicked directly by the router.
        self.world.toggle_clicks += 1
        self.world.actions.append("toggle")
        if self.world.current == S.HOME_VILLAGE:
            self.world.current = S.MAP_SCREEN
        elif self.world.current == S.MAP_SCREEN:
            self.world.current = S.HOME_VILLAGE
        return True

    def send_escape(self):
        self.world.escapes += 1
        self.world.actions.append("escape")
        self.world.current = self.world.escape_map.get(
            self.world.current, S.HOME_VILLAGE)
        return True


class FakeNavigator:
    def __init__(self, world):
        self.world = world

    def click_and_verify(self, description, **kwargs):
        self.world.actions.append(description)
        fails_left = self.world.nav_failures.get(description, 0)
        if fails_left > 0:
            self.world.nav_failures[description] = fails_left - 1
            return False
        if description in self.world.nav_transitions:
            self.world.current = self.world.nav_transitions[description]
            return True
        return False


class FakeCoords:
    def get_nav(self, name):
        return {'x': 1, 'y': 1}

    def get_region(self, name):
        return {'x': 0, 'y': 0, 'width': 10, 'height': 10}


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(screen_router.time, "sleep", lambda *_: None)
    monkeypatch.setattr(screen_router.cv2, "imwrite", lambda *a, **k: True)


def make_router(world):
    detector = FakeDetector(world)
    router = ScreenRouter(
        detector, FakeBluestacks(world), FakeCoords(), FakeNavigator(world),
        click_delay_ms=0)
    router.logger = logging.getLogger("test_router")
    return router


ALLIANCE_TRANSITIONS = {
    "Alliance button": S.ALLIANCE_MENU,
    "Territory button": S.TERRITORY,
    "Technology button": S.TECH,
}


def test_already_at_target():
    world = FakeWorld(S.TERRITORY)
    assert make_router(world).goto(S.TERRITORY) is True
    assert world.actions == []


def test_walks_home_to_territory():
    world = FakeWorld(S.HOME_VILLAGE, nav_transitions=ALLIANCE_TRANSITIONS)
    assert make_router(world).goto(S.TERRITORY) is True
    assert world.actions == ["Alliance button", "Territory button"]


def test_unknown_screen_escapes_toward_home_then_routes():
    world = FakeWorld(S.UNKNOWN, nav_transitions=ALLIANCE_TRANSITIONS,
                      escape_map={S.UNKNOWN: S.HOME_VILLAGE})
    assert make_router(world).goto(S.ALLIANCE_MENU) is True
    assert world.actions == ["escape", "Alliance button"]


def test_exit_dialog_dismissed_then_routes():
    world = FakeWorld(S.EXIT_GAME_DIALOG,
                      nav_transitions=ALLIANCE_TRANSITIONS,
                      escape_map={S.EXIT_GAME_DIALOG: S.HOME_VILLAGE})
    assert make_router(world).goto(S.TECH) is True
    assert world.actions == ["escape", "Alliance button", "Technology button"]


def test_map_uses_toggle_not_escape():
    """Escape on the map only toggles the bottom bar in-game; the router
    must use the view-toggle button to get home."""
    world = FakeWorld(S.MAP_SCREEN, nav_transitions=ALLIANCE_TRANSITIONS)
    assert make_router(world).goto(S.ALLIANCE_MENU) is True
    assert world.actions == ["toggle", "Alliance button"]
    assert world.escapes == 0


def test_goto_map_from_home_uses_toggle():
    world = FakeWorld(S.HOME_VILLAGE)
    assert make_router(world).goto(S.MAP_SCREEN) is True
    assert world.actions == ["toggle"]


def test_failed_edge_retries_and_recovers():
    world = FakeWorld(S.HOME_VILLAGE, nav_transitions=ALLIANCE_TRANSITIONS,
                      nav_failures={"Alliance button": 1})
    assert make_router(world).goto(S.ALLIANCE_MENU) is True
    assert world.actions == ["Alliance button", "Alliance button"]


def test_gives_up_at_max_steps():
    # Escape from UNKNOWN leads right back to UNKNOWN: unreachable.
    world = FakeWorld(S.UNKNOWN, escape_map={S.UNKNOWN: S.UNKNOWN})
    assert make_router(world).goto(S.HOME_VILLAGE, max_steps=4) is False
    assert world.escapes == 4


def test_unroutable_target_raises():
    world = FakeWorld(S.HOME_VILLAGE)
    with pytest.raises(ValueError):
        make_router(world).goto(S.SETTINGS_MENU)


def test_deep_screen_off_path_backs_out():
    """On TECH but asked for TERRITORY: TECH is off the territory path,
    so the router escapes back to the alliance menu and re-routes."""
    world = FakeWorld(S.TECH, nav_transitions=ALLIANCE_TRANSITIONS,
                      escape_map={S.TECH: S.ALLIANCE_MENU})
    assert make_router(world).goto(S.TERRITORY) is True
    assert world.actions == ["escape", "Territory button"]


def test_leftover_overlay_recognized_not_screen_beneath():
    """Regression: routing home from the Markers overlay must identify
    BOOKMARKS (and escape it), not misread the map visible beneath the
    modal and click the map toggle under the overlay."""
    world = FakeWorld(S.BOOKMARKS, escape_map={S.BOOKMARKS: S.MAP_SCREEN})
    assert make_router(world).goto(S.HOME_VILLAGE) is True
    assert world.actions == ["escape", "toggle"]

"""Tests for VerifiedNavigator.click_and_verify retry recovery.

Covers the between-attempts safety net: a click that fails verification
because a blocking dialog opened (cost-confirmation or the "Exit the
game?" dialog) must dismiss the dialog with escape before retrying,
instead of blindly re-clicking under the modal.
"""
import logging

import pytest

import navigation_helper
from navigation_helper import VerifiedNavigator


class FakeBluestacks:
    def __init__(self):
        self.clicks = []
        self.escapes = 0

    def click(self, x, y, delay_ms=1000):
        self.clicks.append((x, y))
        return True

    def send_escape(self):
        self.escapes += 1
        return True


class FakeScreen:
    """Verify fails on attempt 1, succeeds on attempt 2."""

    def __init__(self, cost_dialog=False, exit_dialog=False):
        self.verify_results = [False, True]
        self.cost_dialog = cost_dialog
        self.exit_dialog = exit_dialog
        self.exit_dialog_checks = 0

    def wait_for(self, predicate, timeout=10, description=""):
        return self.verify_results.pop(0) if self.verify_results else True

    def is_cost_confirm_dialog(self, screenshot=None):
        return self.cost_dialog

    def is_exit_game_dialog(self, screenshot=None):
        self.exit_dialog_checks += 1
        return self.exit_dialog


@pytest.fixture(autouse=True)
def fast_sleep(monkeypatch):
    monkeypatch.setattr(navigation_helper.time, "sleep", lambda *_: None)


def make_navigator(screen):
    nav = object.__new__(VerifiedNavigator)
    nav.logger = logging.getLogger("test_navigation")
    nav.ocr = None  # locate() only touches ocr for template/texts lookups
    nav.screen = screen
    nav.bluestacks = FakeBluestacks()
    nav.coords = None
    nav.click_delay_ms = 0
    nav.stop_check = None
    return nav


def test_exit_dialog_dismissed_between_attempts():
    """Regression: expedition's trailing escapes can leave the 'Exit the
    game?' dialog open. The next task's clicks then land under the modal
    and verification can never pass. The retry path must notice the
    dialog and escape it before re-clicking."""
    screen = FakeScreen(exit_dialog=True)
    nav = make_navigator(screen)

    ok = nav.click_and_verify(
        "expand bottom bar", fallback_point={"x": 1227, "y": 670},
        verify=lambda: True, verify_timeout=1)

    assert ok is True
    assert nav.bluestacks.escapes == 1, "exit dialog was not dismissed before retry"


def test_cost_dialog_dismissed_between_attempts():
    screen = FakeScreen(cost_dialog=True)
    nav = make_navigator(screen)

    ok = nav.click_and_verify(
        "some button", fallback_point={"x": 100, "y": 100},
        verify=lambda: True, verify_timeout=1)

    assert ok is True
    assert nav.bluestacks.escapes == 1


def test_no_dialog_means_no_escape():
    screen = FakeScreen()
    nav = make_navigator(screen)

    ok = nav.click_and_verify(
        "some button", fallback_point={"x": 100, "y": 100},
        verify=lambda: True, verify_timeout=1)

    assert ok is True
    assert nav.bluestacks.escapes == 0
    assert len(nav.bluestacks.clicks) == 2  # failed attempt + successful retry


def test_verified_first_try_checks_no_dialogs():
    screen = FakeScreen()
    screen.verify_results = [True]
    nav = make_navigator(screen)

    ok = nav.click_and_verify(
        "some button", fallback_point={"x": 100, "y": 100},
        verify=lambda: True, verify_timeout=1)

    assert ok is True
    assert screen.exit_dialog_checks == 0
    assert len(nav.bluestacks.clicks) == 1

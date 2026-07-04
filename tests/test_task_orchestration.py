"""Orchestration tests for donation and expedition on the ScreenRouter.

Both tasks must: route to their screen, do the work, route home even on
failure, and return an honest result.
"""
import logging

import pytest

from donation_automation import DonationAutomation
from expedition_automation import ExpeditionAutomation
from screen_detector import GameScreen as S


class FakeRouter:
    def __init__(self, results=None):
        self.calls = []
        self.results = results or {}

    def goto(self, target, max_steps=12):
        self.calls.append(target)
        return self.results.get(target, True)


def make_donation(router):
    task = object.__new__(DonationAutomation)
    task.logger = logging.getLogger("test_donation")
    task.router = router
    task.stop_check = None
    return task


def make_expedition(router):
    task = object.__new__(ExpeditionAutomation)
    task.logger = logging.getLogger("test_expedition")
    task.router = router
    task.stop_check = None
    return task


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    import donation_automation
    import expedition_automation
    monkeypatch.setattr(donation_automation.time, "sleep", lambda *_: None)
    monkeypatch.setattr(expedition_automation.time, "sleep", lambda *_: None)


# ---------------------------------------------------------------------------
# Donation
# ---------------------------------------------------------------------------

def test_donation_routes_donates_and_returns_home(monkeypatch):
    router = FakeRouter()
    task = make_donation(router)
    monkeypatch.setattr(task, "find_and_donate_recommended_technology",
                        lambda: True, raising=False)

    assert task.perform_recommended_tech_donation() is True
    assert router.calls == [S.TECH, S.HOME_VILLAGE]


def test_donation_routing_failure_is_honest_and_recovers(monkeypatch):
    router = FakeRouter(results={S.TECH: False})
    task = make_donation(router)
    called = []
    monkeypatch.setattr(task, "find_and_donate_recommended_technology",
                        lambda: called.append(1) or True, raising=False)

    assert task.perform_recommended_tech_donation() is False
    assert called == []  # never donated on the wrong screen
    assert router.calls == [S.TECH, S.HOME_VILLAGE]


def test_donation_banner_missing_still_returns_home(monkeypatch):
    router = FakeRouter()
    task = make_donation(router)
    monkeypatch.setattr(task, "find_and_donate_recommended_technology",
                        lambda: False, raising=False)

    assert task.perform_recommended_tech_donation() is False
    assert router.calls == [S.TECH, S.HOME_VILLAGE]


# ---------------------------------------------------------------------------
# Expedition
# ---------------------------------------------------------------------------

def test_expedition_routes_collects_and_returns_home(monkeypatch):
    router = FakeRouter()
    task = make_expedition(router)
    monkeypatch.setattr(task, "collect_expedition_chests", lambda: True,
                        raising=False)
    monkeypatch.setattr(task, "collect_expedition_rewards", lambda: True,
                        raising=False)

    assert task.perform_expedition_collection() is True
    assert router.calls == [S.EXPEDITION, S.HOME_VILLAGE]


def test_expedition_routing_failure_is_honest_and_recovers(monkeypatch):
    router = FakeRouter(results={S.EXPEDITION: False})
    task = make_expedition(router)
    called = []
    monkeypatch.setattr(task, "collect_expedition_chests",
                        lambda: called.append(1) or True, raising=False)

    assert task.perform_expedition_collection() is False
    assert called == []  # never clicked chest positions on the wrong screen
    assert router.calls == [S.EXPEDITION, S.HOME_VILLAGE]


def test_expedition_chest_failure_still_returns_home(monkeypatch):
    router = FakeRouter()
    task = make_expedition(router)
    monkeypatch.setattr(task, "collect_expedition_chests", lambda: False,
                        raising=False)

    assert task.perform_expedition_collection() is False
    assert router.calls == [S.EXPEDITION, S.HOME_VILLAGE]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def make_build(router):
    from build_automation import BuildAutomation
    task = object.__new__(BuildAutomation)
    task.logger = logging.getLogger("test_build")
    task.router = router
    task.stop_check = None
    return task


def test_build_routes_dispatches_and_returns_home(monkeypatch):
    router = FakeRouter()
    task = make_build(router)
    monkeypatch.setattr(task, "_join_build_from_bookmarks", lambda p: True,
                        raising=False)

    assert task.perform_build(1) is True
    assert router.calls == [S.BOOKMARKS, S.HOME_VILLAGE]


def test_build_bookmark_routing_failure_is_honest(monkeypatch):
    """Regression: the old code returned True even when the bookmark
    screen never opened, so failed builds were recorded as successes."""
    router = FakeRouter(results={S.BOOKMARKS: False})
    task = make_build(router)
    called = []
    monkeypatch.setattr(task, "_join_build_from_bookmarks",
                        lambda p: called.append(1) or True, raising=False)

    assert task.perform_build(1) is False
    assert called == []
    assert router.calls == [S.BOOKMARKS, S.HOME_VILLAGE]


def test_build_no_marker_is_honest_failure(monkeypatch):
    router = FakeRouter()
    task = make_build(router)
    monkeypatch.setattr(task, "_join_build_from_bookmarks", lambda p: False,
                        raising=False)

    assert task.perform_build(1) is False
    assert router.calls == [S.BOOKMARKS, S.HOME_VILLAGE]

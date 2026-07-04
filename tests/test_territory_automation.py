"""Tests for TerritoryAutomation on the ScreenRouter.

The task is now pure intent: route to the territory screen, press
CLAIM, route back home. Routing failures and the nothing-to-claim case
must be distinguishable, and the task must always route home afterwards
so the next task starts from known ground.
"""
import logging

from screen_detector import GameScreen as S
from territory_automation import TerritoryAutomation


class FakeRouter:
    def __init__(self, results=None):
        self.calls = []
        self.results = results or {}

    def goto(self, target, max_steps=12):
        self.calls.append(target)
        return self.results.get(target, True)


class FakeNav:
    def __init__(self, claim_target=None):
        self.claim_target = claim_target

    def locate(self, description, **kwargs):
        return self.claim_target


class FakeBluestacks:
    def __init__(self):
        self.clicks = []

    def click(self, x, y, delay_ms=1000):
        self.clicks.append((x, y))
        return True


def make_task(router, claim_target=None, monkeypatch=None):
    task = object.__new__(TerritoryAutomation)
    task.logger = logging.getLogger("test_territory")
    task.router = router
    task.nav = FakeNav(claim_target)
    task.bluestacks = FakeBluestacks()
    task.coords = type("C", (), {"get_region": lambda self, n: {}})()
    task.click_delay_ms = 0
    task.stop_check = None
    return task


def test_claims_and_returns_home(monkeypatch):
    import territory_automation
    monkeypatch.setattr(territory_automation.time, "sleep", lambda *_: None)
    router = FakeRouter()
    task = make_task(router, claim_target={"x": 1015, "y": 140})

    assert task.perform_territory_claim() is True
    assert router.calls == [S.TERRITORY, S.HOME_VILLAGE]
    assert task.bluestacks.clicks == [(1015, 140)]


def test_nothing_to_claim_still_returns_home(monkeypatch):
    import territory_automation
    monkeypatch.setattr(territory_automation.time, "sleep", lambda *_: None)
    router = FakeRouter()
    task = make_task(router, claim_target=None)

    assert task.perform_territory_claim() is False
    assert router.calls == [S.TERRITORY, S.HOME_VILLAGE]
    assert task.bluestacks.clicks == []


def test_routing_failure_returns_false_and_recovers_home(monkeypatch):
    import territory_automation
    monkeypatch.setattr(territory_automation.time, "sleep", lambda *_: None)
    router = FakeRouter(results={S.TERRITORY: False})
    task = make_task(router, claim_target={"x": 1, "y": 1})

    assert task.perform_territory_claim() is False
    assert router.calls == [S.TERRITORY, S.HOME_VILLAGE]
    assert task.bluestacks.clicks == []

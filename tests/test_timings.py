"""Tests for timings.load_overrides().

load_overrides() mutates module-level globals, so every test runs inside
a fixture that saves and restores all overridable constants.
"""
import pytest

import timings


@pytest.fixture(autouse=True)
def restore_timings():
    saved = {name: getattr(timings, name) for name in timings._ALL_CONSTANTS}
    yield
    for name, value in saved.items():
        setattr(timings, name, value)


class StubConfig:
    """get_config backed by a dict keyed (section, key)."""

    def __init__(self, values):
        self.values = values

    def get_config(self, section, key, default=None):
        return self.values.get((section, key), default)


def test_valid_float_override_applied():
    config = StubConfig({('Timings', 'screen_transition_wait'): '4.5'})
    timings.load_overrides(config)
    assert timings.SCREEN_TRANSITION_WAIT == 4.5


def test_missing_key_keeps_default():
    default = timings.MAP_LOAD_WAIT
    timings.load_overrides(StubConfig({}))
    assert timings.MAP_LOAD_WAIT == default


def test_non_numeric_value_ignored():
    default = timings.POLL_INTERVAL
    config = StubConfig({('Timings', 'poll_interval'): 'fast'})
    timings.load_overrides(config)
    assert timings.POLL_INTERVAL == default


def test_negative_value_ignored():
    default = timings.ACTION_SETTLE_WAIT
    config = StubConfig({('Timings', 'action_settle_wait'): '-1'})
    timings.load_overrides(config)
    assert timings.ACTION_SETTLE_WAIT == default


def test_object_without_get_config_does_not_raise():
    timings.load_overrides(object())


def test_none_config_does_not_raise():
    timings.load_overrides(None)

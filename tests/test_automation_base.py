"""Tests for the shared automation mixin (automation_base)."""
import logging

from automation_base import StopCheckMixin


class _StopComponent(StopCheckMixin):
    STOP_CONTEXT = "unit testing"

    def __init__(self, stop_check=None):
        self.logger = logging.getLogger("test_automation_base")
        self.stop_check = stop_check


class TestStopCheckMixin:
    def test_no_callback_returns_false(self):
        assert _StopComponent(stop_check=None).check_stop_requested() is False

    def test_callback_false_returns_false(self):
        assert _StopComponent(stop_check=lambda: False).check_stop_requested() is False

    def test_callback_true_returns_true_and_logs_context(self, caplog):
        component = _StopComponent(stop_check=lambda: True)
        with caplog.at_level(logging.INFO, logger="test_automation_base"):
            assert component.check_stop_requested() is True
        assert "Stop requested during unit testing" in caplog.text

    def test_default_stop_context(self, caplog):
        component = _StopComponent(stop_check=lambda: True)
        component.STOP_CONTEXT = StopCheckMixin.STOP_CONTEXT
        with caplog.at_level(logging.INFO, logger="test_automation_base"):
            assert component.check_stop_requested() is True
        assert "Stop requested during operation" in caplog.text


class TestStopContextsPreserved:
    """The refactor must keep every component's original log message."""

    def test_stop_contexts(self):
        from account_switcher import AccountSwitcher
        from build_automation import BuildAutomation
        from character_switcher import CharacterSwitcher
        from donation_automation import DonationAutomation
        from expedition_automation import ExpeditionAutomation
        from navigation_helper import VerifiedNavigator
        from ocr_helper import OCRHelper
        from recovery_manager import RecoveryManager
        from rok_game_controller import RoKGameController
        from screen_detector import ScreenDetector

        expected = {
            AccountSwitcher: "account switching",
            BuildAutomation: "build automation",
            CharacterSwitcher: "character switching",
            DonationAutomation: "donation automation",
            ExpeditionAutomation: "expedition automation",
            VerifiedNavigator: "navigation",
            OCRHelper: "OCR operation",
            RecoveryManager: "recovery",
            RoKGameController: "RoK operation",
            ScreenDetector: "screen detection",
        }
        for cls, context in expected.items():
            assert issubclass(cls, StopCheckMixin)
            assert cls.STOP_CONTEXT == context

"""detect_screen() classification tests against real game screenshots.

Every fixture must classify to exactly one GameScreen - including the
modal dialogs, which must win over whatever screen is visible behind
them (e.g. the map anchor is still template-matchable underneath the
Markers modal).

Runs the real OCR pipeline; skipped when Tesseract is not installed.
"""
import os

import cv2
import pytest

from config_manager import find_tesseract_path
from coordinate_manager import CoordinateManager
from ocr_helper import OCRHelper
from screen_detector import GameScreen, ScreenDetector

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
TESSERACT = find_tesseract_path()

pytestmark = pytest.mark.skipif(
    not os.path.exists(TESSERACT), reason="Tesseract OCR not installed")


class StubConfig:
    def get_ocr_config(self):
        return {"tesseract_path": TESSERACT, "preprocess_image": True}

    def get_bool(self, section, key, default=False):
        return default


@pytest.fixture(scope="module")
def detector():
    coords = CoordinateManager()
    ocr = OCRHelper(bluestacks=None, coords=coords, config=StubConfig())
    return ScreenDetector(ocr, coords)


def classify(detector, name):
    img = cv2.imread(os.path.join(FIXTURES, name))
    assert img is not None, f"fixture {name} missing or unreadable"
    return detector.detect_screen(screenshot=img)


@pytest.mark.parametrize("fixture,expected", [
    ("home_village.jpg", GameScreen.HOME_VILLAGE),
    ("home_village_bar_expanded.jpg", GameScreen.HOME_VILLAGE),
    ("map_screen.jpg", GameScreen.MAP_SCREEN),
    ("markers_screen.jpg", GameScreen.BOOKMARKS),
    ("alliance_screen.jpg", GameScreen.ALLIANCE_MENU),
    ("tech_screen.jpg", GameScreen.TECH),
    ("territory_screen.jpg", GameScreen.TERRITORY),
    ("campaign_screen.jpg", GameScreen.CAMPAIGN),
    ("expedition_screen.jpg", GameScreen.EXPEDITION),
    ("exit_game_dialog.jpg", GameScreen.EXIT_GAME_DIALOG),
])
def test_fixture_classification(detector, fixture, expected):
    assert classify(detector, fixture) == expected


TASK_SCREENS = {
    GameScreen.HOME_VILLAGE, GameScreen.MAP_SCREEN, GameScreen.BOOKMARKS,
    GameScreen.ALLIANCE_MENU, GameScreen.TECH, GameScreen.TERRITORY,
    GameScreen.CAMPAIGN, GameScreen.EXPEDITION,
}


def test_unknown_modal_not_mistaken_for_task_screen(detector):
    """Scout Management is a screen the bot has no business being on
    (opened by a stray click). It must never classify as a screen a task
    would act on - UNKNOWN or a generic dialog state are both fine."""
    result = classify(detector, "scout_management.jpg")
    assert result not in TASK_SCREENS, f"misclassified as {result}"


def test_event_confirmation_popup_classified(detector):
    """Field capture: ENTRY CONFIRMATION popup blocked login on 22farms.
    Must classify as EVENT_DIALOG so the router dismisses it in one step
    instead of paying the full unknown-screen sweep."""
    assert classify(detector, "entry_confirmation_dialog.jpg") == GameScreen.EVENT_DIALOG


def test_claim_animation_not_misclassified(detector):
    """Field capture: territory screen mid claim-animation (flying icons
    over the title). Any of TERRITORY/UNKNOWN/DIALOG_OPEN is acceptable;
    what must never happen is classifying it as a different task screen."""
    result = classify(detector, "territory_claim_animation.jpg")
    assert result not in (TASK_SCREENS - {GameScreen.TERRITORY}), f"misclassified as {result}"

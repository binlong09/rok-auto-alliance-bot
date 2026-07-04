"""Screen detection tests against real game screenshots.

The fixtures in tests/fixtures/ were captured from a live Gamota-version
game session on a 1280x720 BlueStacks instance:
  - markers_screen.jpg:    the bookmark screen (titled "Markers" in-game)
  - exit_game_dialog.jpg:  the "Exit the game?" NOTICE dialog
  - map_screen.jpg:        the plain kingdom map (negative control)

These run the real OCR pipeline (Tesseract + preprocessing layers), so
they are skipped when Tesseract is not installed.
"""
import os

import cv2
import pytest

from config_manager import find_tesseract_path
from coordinate_manager import CoordinateManager
from ocr_helper import OCRHelper
from screen_detector import ScreenDetector

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
TESSERACT = find_tesseract_path()

pytestmark = pytest.mark.skipif(
    not os.path.exists(TESSERACT), reason="Tesseract OCR not installed")


class StubConfig:
    """Minimal ConfigManager stand-in for OCRHelper."""

    def get_ocr_config(self):
        return {"tesseract_path": TESSERACT, "preprocess_image": True}

    def get_bool(self, section, key, default=False):
        return default


@pytest.fixture(scope="module")
def detector():
    coords = CoordinateManager()
    ocr = OCRHelper(bluestacks=None, coords=coords, config=StubConfig())
    return ScreenDetector(ocr, coords)


def load(name):
    img = cv2.imread(os.path.join(FIXTURES, name))
    assert img is not None, f"fixture {name} missing or unreadable"
    return img


# ---------------------------------------------------------------------------
# Markers screen (the in-game name of the bookmark screen)
# ---------------------------------------------------------------------------

def test_markers_screen_detected_as_bookmark_screen(detector):
    """Regression: the game titles this screen 'Markers'. The bot used to
    look only for Bookmark/Favorites keywords, fail to recognize the open
    screen, and abort the build task on every run."""
    assert detector.is_in_bookmark_screen(screenshot=load("markers_screen.jpg")) is True


def test_map_screen_is_not_bookmark_screen(detector):
    assert detector.is_in_bookmark_screen(screenshot=load("map_screen.jpg")) is False


# ---------------------------------------------------------------------------
# Exit-game dialog
# ---------------------------------------------------------------------------

def test_exit_dialog_detected(detector):
    assert detector.is_exit_game_dialog(screenshot=load("exit_game_dialog.jpg")) is True


def test_map_screen_is_not_exit_dialog(detector):
    assert detector.is_exit_game_dialog(screenshot=load("map_screen.jpg")) is False


def test_markers_screen_is_not_exit_dialog(detector):
    assert detector.is_exit_game_dialog(screenshot=load("markers_screen.jpg")) is False

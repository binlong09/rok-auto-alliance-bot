"""Tests for TemplateMatcher using synthetic images."""
import cv2
import numpy as np
import pytest

from template_matcher import TemplateMatcher


PATCH_X, PATCH_Y = 120, 60      # top-left of the patch in the screenshot
PATCH_W, PATCH_H = 20, 20
CENTER = (PATCH_X + PATCH_W // 2, PATCH_Y + PATCH_H // 2)


def make_patch():
    """Distinctive high-variance 20x20 patch (deterministic)."""
    rng = np.random.RandomState(42)
    return rng.randint(0, 256, size=(PATCH_H, PATCH_W, 3), dtype=np.uint8)


def make_screenshot(with_patch=True):
    """200x200 low-noise screenshot, optionally containing the patch."""
    rng = np.random.RandomState(7)
    screenshot = rng.randint(0, 30, size=(200, 200, 3), dtype=np.uint8)
    if with_patch:
        screenshot[PATCH_Y:PATCH_Y + PATCH_H, PATCH_X:PATCH_X + PATCH_W] = make_patch()
    return screenshot


@pytest.fixture
def matcher(tmp_path):
    templates_dir = tmp_path / 'templates'
    templates_dir.mkdir()
    cv2.imwrite(str(templates_dir / 'patch.png'), make_patch())
    return TemplateMatcher(templates_dir=str(templates_dir))


def test_find_locates_patch_center(matcher):
    result = matcher.find(make_screenshot(), 'patch')
    assert result is not None
    assert abs(result['x'] - CENTER[0]) <= 2
    assert abs(result['y'] - CENTER[1]) <= 2
    assert result['confidence'] >= 0.85


def test_find_returns_none_for_missing_template(matcher):
    assert matcher.find(make_screenshot(), 'no_such_template') is None


def test_find_returns_none_when_threshold_not_met(matcher):
    # Screenshot without the patch: only low-level noise, no match possible
    assert matcher.find(make_screenshot(with_patch=False), 'patch') is None


def test_region_restriction(matcher):
    screenshot = make_screenshot()
    # Region containing the patch: found
    hit = matcher.find(screenshot, 'patch',
                       region={'x': 100, 'y': 40, 'width': 80, 'height': 80})
    assert hit is not None
    assert abs(hit['x'] - CENTER[0]) <= 2
    assert abs(hit['y'] - CENTER[1]) <= 2
    # Region away from the patch: not found
    miss = matcher.find(screenshot, 'patch',
                        region={'x': 0, 'y': 100, 'width': 100, 'height': 100})
    assert miss is None


def test_has_template(matcher):
    assert matcher.has_template('patch') is True
    assert matcher.has_template('no_such_template') is False

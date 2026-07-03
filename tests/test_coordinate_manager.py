"""Tests for CoordinateManager with a temporary coordinates.json."""
import json

import pytest

from coordinate_manager import CoordinateManager

COORDS = {
    "resolution": "1280x720",
    "navigation": {
        "avatar_icon": {"x": 30, "y": 40},
    },
    "screen": {
        "center": {"x": 640, "y": 360},
    },
    "character_grid": {
        "first_rotation": [{"x": 1, "y": 2}],
        "after_scroll": [{"x": 3, "y": 4}],
    },
    "ocr_regions": {
        "profile_menu": {"x": 10, "y": 20, "width": 300, "height": 200},
    },
    "march_presets": {
        "x": 150,
        "y_positions": [100, 160, 220],
    },
}


@pytest.fixture
def coords(tmp_path):
    path = tmp_path / "coordinates.json"
    path.write_text(json.dumps(COORDS))
    return CoordinateManager(config_path=str(path))


def test_get_nav_returns_copy(coords):
    point = coords.get_nav('avatar_icon')
    assert point == {'x': 30, 'y': 40}
    point['x'] = 9999
    assert coords.get_nav('avatar_icon') == {'x': 30, 'y': 40}


def test_get_screen_returns_copy(coords):
    point = coords.get_screen('center')
    assert point == {'x': 640, 'y': 360}
    point['y'] = -1
    assert coords.get_screen('center') == {'x': 640, 'y': 360}


def test_get_region_returns_copy(coords):
    region = coords.get_region('profile_menu')
    assert region == {'x': 10, 'y': 20, 'width': 300, 'height': 200}
    region['width'] = 0
    assert coords.get_region('profile_menu')['width'] == 300


def test_missing_key_raises_keyerror(coords):
    with pytest.raises(KeyError):
        coords.get_nav('does_not_exist')
    with pytest.raises(KeyError):
        coords.get_region('does_not_exist')


def test_missing_file_raises_filenotfounderror(tmp_path):
    with pytest.raises(FileNotFoundError):
        CoordinateManager(config_path=str(tmp_path / "nope.json"))


def test_get_march_preset_position_valid(coords):
    assert coords.get_march_preset_position(1) == {'x': 150, 'y': 100}
    assert coords.get_march_preset_position(3) == {'x': 150, 'y': 220}


def test_get_march_preset_position_out_of_range(coords):
    with pytest.raises(ValueError):
        coords.get_march_preset_position(0)
    with pytest.raises(ValueError):
        coords.get_march_preset_position(4)


def test_get_raw_traversal(coords):
    assert coords.get_raw('navigation', 'avatar_icon', 'x') == 30
    assert coords.get_raw('character_grid', 'first_rotation', 0) == {'x': 1, 'y': 2}
    with pytest.raises(KeyError):
        coords.get_raw('navigation', 'missing')

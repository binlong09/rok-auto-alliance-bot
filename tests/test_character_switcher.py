"""Tests for CharacterSwitcher.get_character_position()."""
import pytest

from character_switcher import CharacterSwitcher

FIRST = [{'x': 100 + i, 'y': 200 + i} for i in range(6)]
AFTER = [{'x': 500 + i, 'y': 600 + i} for i in range(6)]


@pytest.fixture
def switcher():
    """Bare instance with only the attributes get_character_position needs."""
    sw = object.__new__(CharacterSwitcher)
    sw.character_positions_first_rotation = FIRST
    sw.character_positions_after_scroll = AFTER
    return sw


@pytest.mark.parametrize('index', range(6))
def test_indexes_0_to_5_use_first_rotation(switcher, index):
    assert switcher.get_character_position(index) == FIRST[index]


@pytest.mark.parametrize('index', range(6, 12))
def test_indexes_6_to_11_use_after_scroll(switcher, index):
    assert switcher.get_character_position(index) == AFTER[index % 6]


def test_index_12_wraps_to_after_scroll_again(switcher):
    assert switcher.get_character_position(12) == AFTER[0]

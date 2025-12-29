#!/usr/bin/env python3
"""
Coordinate Manager - Centralized management of all UI coordinates.

This module loads coordinates from coordinates.json and provides
typed access methods for points, regions, and other coordinate data.
"""
import os
import json
import logging


class CoordinateManager:
    """Manager for loading and accessing UI coordinates from JSON config."""

    def __init__(self, config_path=None):
        """
        Initialize the coordinate manager.

        Args:
            config_path: Path to coordinates.json. If None, uses default location.
        """
        self.logger = logging.getLogger(__name__)

        if config_path is None:
            # Default to coordinates.json in same directory as this file
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "coordinates.json"
            )

        self.config_path = config_path
        self.data = {}
        self._load_coordinates()

    def _load_coordinates(self):
        """Load coordinates from JSON file."""
        try:
            if not os.path.exists(self.config_path):
                self.logger.error(f"Coordinates file not found: {self.config_path}")
                raise FileNotFoundError(f"Coordinates file not found: {self.config_path}")

            with open(self.config_path, 'r') as f:
                self.data = json.load(f)

            self.logger.info(f"Loaded coordinates for resolution: {self.data.get('resolution', 'unknown')}")
            self._validate_required_keys()

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in coordinates file: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error loading coordinates: {e}")
            raise

    def _validate_required_keys(self):
        """Validate that all required coordinate sections exist."""
        required_sections = ['navigation', 'screen', 'character_grid', 'ocr_regions']
        missing = [s for s in required_sections if s not in self.data]

        if missing:
            self.logger.warning(f"Missing coordinate sections: {missing}")

    def reload(self):
        """Reload coordinates from file (useful for hot-reloading during development)."""
        self._load_coordinates()

    # =========================================================================
    # Point Access Methods (for x, y coordinates)
    # =========================================================================

    def get_point(self, category, name):
        """
        Get a point coordinate as a dict with x, y keys.

        Args:
            category: Category name (e.g., 'navigation', 'screen')
            name: Coordinate name within the category

        Returns:
            dict: {'x': int, 'y': int}

        Raises:
            KeyError: If category or name not found
        """
        if category not in self.data:
            raise KeyError(f"Coordinate category not found: {category}")

        if name not in self.data[category]:
            raise KeyError(f"Coordinate '{name}' not found in category '{category}'")

        return self.data[category][name].copy()

    def get_nav(self, name):
        """Shorthand for get_point('navigation', name)."""
        return self.get_point('navigation', name)

    def get_screen(self, name):
        """Shorthand for get_point('screen', name)."""
        return self.get_point('screen', name)

    # =========================================================================
    # Region Access Methods (for x, y, width, height)
    # =========================================================================

    def get_region(self, name):
        """
        Get an OCR region as a dict with x, y, width, height keys.

        Args:
            name: Region name from ocr_regions

        Returns:
            dict: {'x': int, 'y': int, 'width': int, 'height': int}

        Raises:
            KeyError: If region not found
        """
        if 'ocr_regions' not in self.data:
            raise KeyError("No 'ocr_regions' section in coordinates")

        if name not in self.data['ocr_regions']:
            raise KeyError(f"OCR region not found: {name}")

        return self.data['ocr_regions'][name].copy()

    # =========================================================================
    # List/Array Access Methods
    # =========================================================================

    def get_character_grid(self, rotation='first_rotation'):
        """
        Get character grid positions.

        Args:
            rotation: 'first_rotation' or 'after_scroll'

        Returns:
            list: List of {'x': int, 'y': int} dicts
        """
        if 'character_grid' not in self.data:
            raise KeyError("No 'character_grid' section in coordinates")

        if rotation not in self.data['character_grid']:
            raise KeyError(f"Character grid rotation not found: {rotation}")

        # Return a copy to prevent modification
        return [pos.copy() for pos in self.data['character_grid'][rotation]]

    def get_character_switcher_grid(self):
        """Get character switcher grid positions."""
        if 'character_switcher_grid' not in self.data:
            raise KeyError("No 'character_switcher_grid' section in coordinates")
        return [pos.copy() for pos in self.data['character_switcher_grid']]

    def get_march_preset_position(self, preset_number):
        """
        Get position for a march preset button (1-7).

        Args:
            preset_number: Preset number (1-7)

        Returns:
            dict: {'x': int, 'y': int}
        """
        if 'march_presets' not in self.data:
            raise KeyError("No 'march_presets' section in coordinates")

        presets = self.data['march_presets']
        if preset_number < 1 or preset_number > len(presets['y_positions']):
            raise ValueError(f"Invalid preset number: {preset_number}")

        return {
            'x': presets['x'],
            'y': presets['y_positions'][preset_number - 1]
        }

    def get_go_button_y_positions(self):
        """Get list of Y positions for 'Go' buttons."""
        if 'go_button' in self.data:
            return self.data['go_button'].get('y_positions', []).copy()
        return []

    def get_go_button_x(self):
        """Get X position for 'Go' buttons."""
        if 'go_button' in self.data:
            return self.data['go_button'].get('x', 1012)
        return 1012

    # =========================================================================
    # Scroll Parameters
    # =========================================================================

    def get_scroll(self, name):
        """
        Get scroll parameters.

        Args:
            name: Scroll name (e.g., 'character_list', 'character_switcher')

        Returns:
            dict: {'start': {'x', 'y'}, 'end': {'x', 'y'}, 'duration_ms': int}
        """
        if 'scroll' not in self.data:
            raise KeyError("No 'scroll' section in coordinates")

        if name not in self.data['scroll']:
            raise KeyError(f"Scroll config not found: {name}")

        scroll = self.data['scroll'][name]
        return {
            'start': scroll['start'].copy(),
            'end': scroll['end'].copy(),
            'duration_ms': scroll.get('duration_ms', 500)
        }

    # =========================================================================
    # Offsets and Color Detection
    # =========================================================================

    def get_offset(self, name):
        """
        Get an offset value.

        Args:
            name: Offset name

        Returns:
            dict or int: Offset value (could be {'x', 'y'} or a single int)
        """
        if 'offsets' not in self.data:
            raise KeyError("No 'offsets' section in coordinates")

        if name not in self.data['offsets']:
            raise KeyError(f"Offset not found: {name}")

        value = self.data['offsets'][name]
        if isinstance(value, dict):
            return value.copy()
        return value

    def get_color_detection(self, name):
        """
        Get color detection parameters.

        Args:
            name: Color detection name (e.g., 'yellow_star', 'green_checkmark')

        Returns:
            dict: {'hsv_lower': [...], 'hsv_upper': [...], 'pixel_threshold': int}
        """
        if 'color_detection' not in self.data:
            raise KeyError("No 'color_detection' section in coordinates")

        if name not in self.data['color_detection']:
            raise KeyError(f"Color detection config not found: {name}")

        return self.data['color_detection'][name].copy()

    # =========================================================================
    # Raw Access (for advanced use cases)
    # =========================================================================

    def get_raw(self, *keys):
        """
        Get raw data by traversing keys.

        Args:
            *keys: Keys to traverse (e.g., 'navigation', 'avatar_icon', 'x')

        Returns:
            Any: The value at the specified path
        """
        result = self.data
        for key in keys:
            if isinstance(result, dict) and key in result:
                result = result[key]
            elif isinstance(result, list) and isinstance(key, int):
                result = result[key]
            else:
                raise KeyError(f"Key not found: {key}")
        return result

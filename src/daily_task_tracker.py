#!/usr/bin/env python3
"""
Daily Task Tracker - Tracks completion of daily tasks per character.

This module tracks which daily tasks (build, expedition) have been completed
for each character, using UTC time to determine the current day.
Tasks marked as completed today will be skipped unless force mode is enabled.
"""
import os
import json
import logging
from datetime import datetime, timezone


class DailyTaskTracker:
    """Tracks daily task completion per character using UTC time."""

    # Task types that are tracked as daily
    TASK_BUILD = "build"
    TASK_EXPEDITION = "expedition"

    def __init__(self, tracking_file_path):
        """
        Initialize the daily task tracker.

        Args:
            tracking_file_path: Full path to the tracking JSON file
                               (e.g., instances/default_daily_tasks.json)
        """
        self.logger = logging.getLogger(__name__)
        self.tracking_file = tracking_file_path
        self.data = self._load_tracking_data()

    def _load_tracking_data(self):
        """Load tracking data from JSON file."""
        if os.path.exists(self.tracking_file):
            try:
                with open(self.tracking_file, 'r') as f:
                    data = json.load(f)
                self.logger.debug(f"Loaded daily task tracking from {self.tracking_file}")
                return data
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Error loading tracking file, starting fresh: {e}")

        # Return empty structure if file doesn't exist or is corrupted
        return {
            "last_updated": None,
            "characters": {}
        }

    def _save_tracking_data(self):
        """Save tracking data to JSON file."""
        try:
            self.data["last_updated"] = datetime.now(timezone.utc).isoformat()

            # Ensure directory exists
            os.makedirs(os.path.dirname(self.tracking_file), exist_ok=True)

            with open(self.tracking_file, 'w') as f:
                json.dump(self.data, f, indent=2)

            self.logger.debug(f"Saved daily task tracking to {self.tracking_file}")
        except IOError as e:
            self.logger.error(f"Error saving tracking file: {e}")

    def _get_today_utc(self):
        """Get today's date in UTC as a string (YYYY-MM-DD)."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def is_task_completed_today(self, character_index, task_name):
        """
        Check if a task has been completed today (UTC) for a character.

        Args:
            character_index: Zero-based index of the character
            task_name: Name of the task (use TASK_BUILD, TASK_EXPEDITION constants)

        Returns:
            bool: True if task was completed today, False otherwise
        """
        char_key = str(character_index)
        today = self._get_today_utc()

        if char_key not in self.data["characters"]:
            return False

        char_data = self.data["characters"][char_key]
        completion_date = char_data.get(task_name)

        if completion_date == today:
            self.logger.debug(
                f"Task '{task_name}' already completed today (UTC) for character {character_index}"
            )
            return True

        return False

    def mark_task_completed(self, character_index, task_name):
        """
        Mark a task as completed for a character (records today's UTC date).

        Args:
            character_index: Zero-based index of the character
            task_name: Name of the task (use TASK_BUILD, TASK_EXPEDITION constants)
        """
        char_key = str(character_index)
        today = self._get_today_utc()

        if char_key not in self.data["characters"]:
            self.data["characters"][char_key] = {}

        self.data["characters"][char_key][task_name] = today
        self._save_tracking_data()

        self.logger.info(
            f"Marked '{task_name}' as completed for character {character_index} on {today} (UTC)"
        )

    def reset_all_tasks(self):
        """
        Reset all task completion tracking.

        This clears all completion records, allowing all tasks to run again.
        """
        self.data["characters"] = {}
        self._save_tracking_data()
        self.logger.info("Reset all daily task completion tracking")

    def reset_tasks_for_character(self, character_index):
        """
        Reset task completion tracking for a specific character.

        Args:
            character_index: Zero-based index of the character
        """
        char_key = str(character_index)
        if char_key in self.data["characters"]:
            del self.data["characters"][char_key]
            self._save_tracking_data()
            self.logger.info(f"Reset daily tasks for character {character_index}")

    def get_completion_status(self):
        """
        Get the current completion status for all characters.

        Returns:
            dict: Copy of the tracking data for UI display
        """
        return {
            "today_utc": self._get_today_utc(),
            "last_updated": self.data.get("last_updated"),
            "characters": self.data.get("characters", {}).copy()
        }

    def get_character_status(self, character_index):
        """
        Get completion status for a specific character.

        Args:
            character_index: Zero-based index of the character

        Returns:
            dict: Task completion dates for the character, or empty dict if none
        """
        char_key = str(character_index)
        return self.data["characters"].get(char_key, {}).copy()


def get_tracker_path_for_instance(instances_dir, instance_id):
    """
    Get the tracking file path for a specific instance.

    Args:
        instances_dir: Path to the instances directory
        instance_id: ID of the instance

    Returns:
        str: Full path to the tracking file
    """
    return os.path.join(instances_dir, f"{instance_id}_daily_tasks.json")

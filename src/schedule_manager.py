#!/usr/bin/env python3
"""
Schedule Manager - Manages scheduled automation runs per instance.

This module tracks when each instance should run its next scheduled automation,
based on configurable intervals (e.g., every 12 hours from last run).
"""
import os
import json
import logging
from datetime import datetime, timezone, timedelta


class ScheduleManager:
    """Manages scheduled automation runs for instances."""

    DEFAULT_INTERVAL_HOURS = 12

    def __init__(self, instances_dir):
        """
        Initialize the schedule manager.

        Args:
            instances_dir: Path to the instances directory where schedule files are stored
        """
        self.logger = logging.getLogger(__name__)
        self.instances_dir = instances_dir

    def _get_schedule_path(self, instance_id):
        """Get the path to the schedule file for an instance."""
        return os.path.join(self.instances_dir, f"{instance_id}_schedule.json")

    def _get_default_schedule(self):
        """Get default schedule configuration."""
        return {
            "enabled": False,
            "interval_hours": self.DEFAULT_INTERVAL_HOURS,
            "last_run_utc": None,
            "next_run_utc": None
        }

    def get_schedule(self, instance_id):
        """
        Get schedule configuration for an instance.

        Args:
            instance_id: ID of the instance

        Returns:
            dict: Schedule configuration
        """
        schedule_path = self._get_schedule_path(instance_id)

        if os.path.exists(schedule_path):
            try:
                with open(schedule_path, 'r') as f:
                    data = json.load(f)
                # Ensure all required fields exist
                default = self._get_default_schedule()
                for key in default:
                    if key not in data:
                        data[key] = default[key]
                return data
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Error loading schedule for {instance_id}, using defaults: {e}")

        return self._get_default_schedule()

    def save_schedule(self, instance_id, schedule):
        """
        Save schedule configuration for an instance.

        Args:
            instance_id: ID of the instance
            schedule: Schedule configuration dict
        """
        schedule_path = self._get_schedule_path(instance_id)

        try:
            os.makedirs(os.path.dirname(schedule_path), exist_ok=True)
            with open(schedule_path, 'w') as f:
                json.dump(schedule, f, indent=2)
            self.logger.debug(f"Saved schedule for instance {instance_id}")
        except IOError as e:
            self.logger.error(f"Error saving schedule for {instance_id}: {e}")

    def is_enabled(self, instance_id):
        """
        Check if scheduling is enabled for an instance.

        Args:
            instance_id: ID of the instance

        Returns:
            bool: True if scheduling is enabled
        """
        schedule = self.get_schedule(instance_id)
        return schedule.get("enabled", False)

    def enable_schedule(self, instance_id, enabled):
        """
        Enable or disable scheduling for an instance.

        Args:
            instance_id: ID of the instance
            enabled: True to enable, False to disable
        """
        schedule = self.get_schedule(instance_id)
        schedule["enabled"] = enabled

        # If enabling and no next_run is set, calculate it from now
        if enabled and not schedule.get("next_run_utc"):
            interval = schedule.get("interval_hours", self.DEFAULT_INTERVAL_HOURS)
            next_run = datetime.now(timezone.utc) + timedelta(hours=interval)
            schedule["next_run_utc"] = next_run.isoformat()

        self.save_schedule(instance_id, schedule)
        self.logger.info(f"Schedule {'enabled' if enabled else 'disabled'} for instance {instance_id}")

    def set_interval(self, instance_id, hours):
        """
        Set the interval for scheduled runs.

        Args:
            instance_id: ID of the instance
            hours: Interval in hours between runs
        """
        schedule = self.get_schedule(instance_id)
        schedule["interval_hours"] = hours

        # Recalculate next run if schedule is enabled and has a last run
        if schedule.get("enabled") and schedule.get("last_run_utc"):
            last_run = datetime.fromisoformat(schedule["last_run_utc"])
            next_run = last_run + timedelta(hours=hours)
            schedule["next_run_utc"] = next_run.isoformat()

        self.save_schedule(instance_id, schedule)
        self.logger.info(f"Set interval to {hours} hours for instance {instance_id}")

    def is_due(self, instance_id):
        """
        Check if a scheduled run is due for an instance.

        Args:
            instance_id: ID of the instance

        Returns:
            bool: True if a run is due (schedule enabled and past next_run time)
        """
        schedule = self.get_schedule(instance_id)

        # Must be enabled
        if not schedule.get("enabled", False):
            return False

        next_run_str = schedule.get("next_run_utc")
        if not next_run_str:
            # No next run set, so it's due immediately
            return True

        try:
            next_run = datetime.fromisoformat(next_run_str)
            now = datetime.now(timezone.utc)
            return now >= next_run
        except (ValueError, TypeError) as e:
            self.logger.warning(f"Invalid next_run_utc for {instance_id}: {e}")
            return True

    def mark_run_complete(self, instance_id):
        """
        Mark a scheduled run as complete and calculate next run time.

        Args:
            instance_id: ID of the instance
        """
        schedule = self.get_schedule(instance_id)

        now = datetime.now(timezone.utc)
        interval = schedule.get("interval_hours", self.DEFAULT_INTERVAL_HOURS)

        schedule["last_run_utc"] = now.isoformat()
        schedule["next_run_utc"] = (now + timedelta(hours=interval)).isoformat()

        self.save_schedule(instance_id, schedule)
        self.logger.info(
            f"Marked run complete for {instance_id}. Next run in {interval} hours at {schedule['next_run_utc']}"
        )

    def get_next_run_time(self, instance_id):
        """
        Get the next scheduled run time for an instance.

        Args:
            instance_id: ID of the instance

        Returns:
            datetime or None: Next run time, or None if not scheduled
        """
        schedule = self.get_schedule(instance_id)

        if not schedule.get("enabled", False):
            return None

        next_run_str = schedule.get("next_run_utc")
        if not next_run_str:
            return None

        try:
            return datetime.fromisoformat(next_run_str)
        except (ValueError, TypeError):
            return None

    def get_last_run_time(self, instance_id):
        """
        Get the last run time for an instance.

        Args:
            instance_id: ID of the instance

        Returns:
            datetime or None: Last run time, or None if never run
        """
        schedule = self.get_schedule(instance_id)
        last_run_str = schedule.get("last_run_utc")

        if not last_run_str:
            return None

        try:
            return datetime.fromisoformat(last_run_str)
        except (ValueError, TypeError):
            return None

    def get_time_until_next_run(self, instance_id):
        """
        Get the time remaining until the next scheduled run.

        Args:
            instance_id: ID of the instance

        Returns:
            timedelta or None: Time until next run, or None if not scheduled
        """
        next_run = self.get_next_run_time(instance_id)
        if not next_run:
            return None

        now = datetime.now(timezone.utc)
        remaining = next_run - now

        # If negative (overdue), return zero
        if remaining.total_seconds() < 0:
            return timedelta(seconds=0)

        return remaining

    def format_time_remaining(self, instance_id):
        """
        Get a human-readable string of time until next run.

        Args:
            instance_id: ID of the instance

        Returns:
            str: Formatted time string (e.g., "2h 30m") or "Not scheduled"
        """
        remaining = self.get_time_until_next_run(instance_id)
        if remaining is None:
            return "Not scheduled"

        total_seconds = int(remaining.total_seconds())
        if total_seconds <= 0:
            return "Due now"

        hours, remainder = divmod(total_seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    def format_next_run_datetime(self, instance_id):
        """
        Get a formatted string of the next run datetime.

        Args:
            instance_id: ID of the instance

        Returns:
            str: Formatted datetime (e.g., "Dec 29, 10:30 PM") or "Not scheduled"
        """
        next_run = self.get_next_run_time(instance_id)
        if not next_run:
            return "Not scheduled"

        # Convert to local time for display
        local_time = next_run.astimezone()
        return local_time.strftime("%b %d, %I:%M %p")

    def format_last_run_datetime(self, instance_id):
        """
        Get a formatted string of the last run datetime.

        Args:
            instance_id: ID of the instance

        Returns:
            str: Formatted datetime (e.g., "Dec 29, 10:30 AM") or "Never"
        """
        last_run = self.get_last_run_time(instance_id)
        if not last_run:
            return "Never"

        # Convert to local time for display
        local_time = last_run.astimezone()
        return local_time.strftime("%b %d, %I:%M %p")

    def trigger_immediate_run(self, instance_id):
        """
        Set the next run time to now, triggering an immediate run.

        Args:
            instance_id: ID of the instance
        """
        schedule = self.get_schedule(instance_id)

        if not schedule.get("enabled", False):
            self.logger.warning(f"Cannot trigger immediate run for {instance_id} - schedule not enabled")
            return

        schedule["next_run_utc"] = datetime.now(timezone.utc).isoformat()
        self.save_schedule(instance_id, schedule)
        self.logger.info(f"Triggered immediate run for instance {instance_id}")


def get_schedule_path_for_instance(instances_dir, instance_id):
    """
    Get the schedule file path for a specific instance.

    Args:
        instances_dir: Path to the instances directory
        instance_id: ID of the instance

    Returns:
        str: Full path to the schedule file
    """
    return os.path.join(instances_dir, f"{instance_id}_schedule.json")

#!/usr/bin/env python3
import os
import sys
import time
import logging
import threading
import subprocess
import queue
from queue import Queue

import timings
from instance_manager import InstanceManager
from config_manager import ConfigManager
from bluestacks_controller import BlueStacksController
from rok_game_controller import RoKGameController
from daily_task_tracker import DailyTaskTracker, get_tracker_path_for_instance


class QueueLogHandler(logging.Handler):
    """
    Custom logging handler that routes log messages to a queue for GUI display.
    This allows verbose logs from all automation modules to appear in the GUI.
    """

    def __init__(self, queue, instance_id):
        super().__init__()
        self.queue = queue
        self.instance_id = instance_id
        self.setFormatter(logging.Formatter('%(name)s - %(message)s'))

    def emit(self, record):
        try:
            msg = self.format(record)
            self.queue.put({
                "instance_id": self.instance_id,
                "type": "log",
                "message": msg
            })
        except Exception:
            self.handleError(record)


class AutomationThread(threading.Thread):
    """Thread class for running automation on a specific instance"""

    def __init__(self, instance_id, instance_name, config_manager, queue, stop_event=None,
                 exit_after_complete=True, force_daily_tasks=False, instances_dir=None,
                 on_complete_callback=None):
        super().__init__()
        self.instance_id = instance_id
        self.instance_name = instance_name
        self.config_manager = config_manager
        self.queue = queue  # Message queue for communication with main thread
        self.stop_event = stop_event or threading.Event()
        self.daemon = True  # Thread will exit when main program exits
        self.exit_after_complete = exit_after_complete  # Whether to exit BlueStacks after completion
        self.force_daily_tasks = force_daily_tasks  # Whether to run daily tasks even if completed today
        self.instances_dir = instances_dir  # Directory containing instance configs
        self.on_complete_callback = on_complete_callback  # Callback when thread completes

        # Set up logging
        self.logger = logging.getLogger(f"automation.{instance_id}")

    def log(self, message):
        """Add log message to queue and logger"""
        self.logger.info(message)
        self.queue.put({
            "instance_id": self.instance_id,
            "type": "log",
            "message": message
        })

    def update_status(self, status):
        """Update status in queue"""
        self.queue.put({
            "instance_id": self.instance_id,
            "type": "status",
            "message": status
        })

    def close_bluestacks(self, bluestacks_controller):
        """Close the specific BlueStacks instance without affecting other instances or restarting them"""
        try:
            # Get the instance name
            bs_instance_name = self.config_manager.get_config('BlueStacks', 'bluestacks_instance_name')

            self.log(f"Closing BlueStacks instance: {bs_instance_name}")

            # First check if the instance is actually running before trying to interact with it
            is_running = False
            if sys.platform == "win32":
                check_instance_cmd = [
                    "wmic", "process", "where",
                    f"name='HD-Player.exe' and commandline like '%{bs_instance_name}%'",
                    "get", "processid"
                ]
                try:
                    process_info = subprocess.run(check_instance_cmd, capture_output=True, text=True,
                                                  timeout=5)
                    process_output = process_info.stdout.strip()
                    is_running = 'ProcessId' in process_output and len(process_output.split('\n')) > 1
                except Exception as e:
                    self.log(f"Error checking if instance is running: {e}")
                    # Assume it might be running to be safe
                    is_running = True
            else:
                # For non-Windows, assume it's running
                is_running = True

            # Only proceed with ADB commands if the instance is running
            if is_running:
                # Use ADB to force stop the app first
                try:
                    # Force stop only the RoK app on this specific instance
                    package_name = self.config_manager.get_config('RiseOfKingdoms', 'package_name',
                                                                  'com.lilithgame.roc.gp')
                    adb_device = bluestacks_controller.adb_device
                    force_stop_cmd = [
                        bluestacks_controller.adb_path, "-s", adb_device,
                        "shell", "am", "force-stop", package_name
                    ]
                    self.log(f"Stopping RoK app with command: {force_stop_cmd}")
                    subprocess.run(force_stop_cmd, capture_output=True, timeout=10)

                    # Add a delay to ensure app is fully stopped
                    time.sleep(timings.APP_STOP_WAIT)
                except Exception as e:
                    self.log(f"Error force stopping RoK app: {e}")

            # Now directly kill the process for the specific instance
            if sys.platform == "win32" and is_running:
                # Find and kill the specific BlueStacks instance process
                check_instance_cmd = [
                    "wmic", "process", "where",
                    f"name='HD-Player.exe' and commandline like '%{bs_instance_name}%'",
                    "get", "processid"
                ]
                try:
                    process_info = subprocess.run(check_instance_cmd, capture_output=True, text=True,
                                                  timeout=5)
                    process_output = process_info.stdout.strip()

                    # Extract and kill PIDs
                    if 'ProcessId' in process_output:
                        lines = process_output.split('\n')
                        for line in lines[1:]:  # Skip header line
                            if line.strip():
                                pid = line.strip()
                                self.log(f"Found process ID for instance {bs_instance_name}: {pid}")
                                # Kill this specific PID
                                kill_cmd = ["taskkill", "/F", "/PID", pid]
                                self.log(f"Killing process with command: {kill_cmd}")
                                subprocess.run(kill_cmd, capture_output=True, timeout=5)
                    else:
                        self.log(f"No running process found for instance {bs_instance_name}")
                except Exception as e:
                    self.log(f"Error killing instance-specific process: {e}")
            elif not sys.platform == "win32":
                # On Linux/Mac, try to use pkill with instance name filter
                self.log(f"Using pkill to terminate BlueStacks instance {bs_instance_name}")
                subprocess.run(["pkill", "-f", f"BlueStacks.*{bs_instance_name}"], capture_output=True,
                               timeout=10)

            self.log(f"BlueStacks instance {bs_instance_name} closed")
            return True

        except Exception as e:
            self.logger.error(f"Error closing BlueStacks: {e}")
            self.logger.exception("Stack trace:")
            self.log(f"Failed to close BlueStacks: {e}")
            return False

    def run(self):
        """Run the automation sequence for this instance"""
        bluestacks_controller = None
        queue_handler = None

        # List of logger names to capture for GUI display
        automation_loggers = [
            'recovery_manager',
            'character_switcher',
            'build_automation',
            'donation_automation',
            'expedition_automation',
            'screen_detector',
            'bluestacks_controller',
            'rok_game_controller',
            'ocr_helper',
        ]

        try:
            # Apply any [Timings] overrides from this instance's config.ini
            # before any timing-dependent component is created below.
            timings.load_overrides(self.config_manager)

            # Set up queue handler to route verbose logs to GUI
            queue_handler = QueueLogHandler(self.queue, self.instance_id)
            queue_handler.setLevel(logging.INFO)

            # Attach handler to all automation-related loggers
            for logger_name in automation_loggers:
                logger = logging.getLogger(logger_name)
                logger.addHandler(queue_handler)

            self.log(f"Starting automation for instance '{self.instance_name}'")
            self.update_status("Starting")

            # Initialize controllers
            bluestacks_controller = BlueStacksController(self.config_manager)

            # Get ADB port from config
            adb_port = self.config_manager.get_config('BlueStacks', 'adb_port', '5555')
            adb_device = f"127.0.0.1:{adb_port}"
            bluestacks_controller.set_adb_device(adb_device)

            # Create daily task tracker if instances_dir is provided
            daily_tracker = None
            if self.instances_dir:
                tracker_path = get_tracker_path_for_instance(self.instances_dir, self.instance_id)
                daily_tracker = DailyTaskTracker(tracker_path)
                self.log(f"Daily task tracking enabled (force={self.force_daily_tasks})")

            # Initialize RoK controller
            rok_controller = RoKGameController(
                self.config_manager, bluestacks_controller,
                daily_task_tracker=daily_tracker,
                force_daily_tasks=self.force_daily_tasks
            )

            # Check if stop requested
            if self.stop_event.is_set():
                self.log("Automation stopped before startup")
                self.update_status("Stopped")
                return

            # Start BlueStacks
            self.log(
                f"Starting BlueStacks instance '{self.config_manager.get_config('BlueStacks', 'bluestacks_instance_name')}'")
            self.update_status("Starting BlueStacks")

            if not bluestacks_controller.start_bluestacks():
                self.log("Failed to start BlueStacks")
                self.update_status("Failed to start BlueStacks")
                return

            # Check if stop requested
            if self.stop_event.is_set():
                self.log("Automation stopped after BlueStacks startup")
                self.update_status("Stopped")
                if self.exit_after_complete and bluestacks_controller:
                    self.log("Closing BlueStacks instance")
                    self.close_bluestacks(bluestacks_controller)
                return

            # Connect to ADB
            self.log(f"Connecting to ADB on port {adb_port}")
            self.update_status("Connecting to ADB")

            if not bluestacks_controller.connect_adb():
                if bluestacks_controller.last_connect_error == "adb_disabled":
                    self.log(
                        "ADB debugging is disabled inside this BlueStacks instance. "
                        "Open the instance -> Settings -> Advanced -> enable 'Android Debug Bridge (ADB)', "
                        "then restart the instance."
                    )
                    self.update_status("ADB Disabled in Instance")
                else:
                    self.log("Failed to connect to ADB")
                    self.update_status("Failed to connect to ADB")
                if self.exit_after_complete and bluestacks_controller:
                    self.log("Closing BlueStacks instance")
                    self.close_bluestacks(bluestacks_controller)
                return

            # Verify the emulator resolution matches what the coordinate maps
            # expect; on mismatch this rewrites bluestacks.conf, restarts the
            # instance and reconnects ADB automatically.
            self.log("Checking emulator screen resolution")
            self.update_status("Checking resolution")

            if not bluestacks_controller.ensure_correct_resolution():
                self.log(
                    f"Screen resolution is wrong (expected "
                    f"{bluestacks_controller.expected_width}x{bluestacks_controller.expected_height}) "
                    "and could not be fixed automatically. Set it manually in "
                    "BlueStacks Settings > Display, then restart the instance."
                )
                self.update_status("Wrong resolution")
                if self.exit_after_complete and bluestacks_controller:
                    self.log("Closing BlueStacks instance")
                    self.close_bluestacks(bluestacks_controller)
                return

            # Start Rise of Kingdoms
            if self.stop_event.is_set():
                self.log("Automation stopped before launching game")
                self.update_status("Stopped")
                if self.exit_after_complete and bluestacks_controller:
                    self.log("Closing BlueStacks instance")
                    self.close_bluestacks(bluestacks_controller)
                return

            self.log("Starting Rise of Kingdoms")
            self.update_status("Starting RoK")

            if not rok_controller.start_game():
                self.log("Failed to start Rise of Kingdoms")
                self.update_status("Failed to start RoK")
                if self.exit_after_complete and bluestacks_controller:
                    self.log("Closing BlueStacks instance")
                    self.close_bluestacks(bluestacks_controller)
                return

            # Wait for game to load (returns early if already loaded)
            self.log("Waiting for Rise of Kingdoms to load")
            self.update_status("Game loading")

            rok_controller.stop_check_callback = lambda: self.stop_event.is_set()
            if not rok_controller.wait_for_game_load():
                self.log("Automation stopped during game loading")
                self.update_status("Stopped")
                if self.exit_after_complete and bluestacks_controller:
                    self.log("Closing BlueStacks instance")
                    self.close_bluestacks(bluestacks_controller)
                return

            # Start the automation (rotates accounts too when [Accounts] is configured)
            if rok_controller.accounts:
                self.log(f"Starting automation for {len(rok_controller.accounts)} account(s)")
            else:
                self.log("Starting character switching automation")
            self.update_status("Running character automation")

            if rok_controller.run_automation():
                self.log("Character automation completed successfully")
                self.update_status("Completed")
            else:
                if self.stop_event.is_set():
                    self.log("Character automation stopped by user")
                    self.update_status("Stopped")
                else:
                    self.log("Character automation encountered issues")
                    self.update_status("Partial completion")

        except Exception as e:
            self.logger.error(f"Error in automation thread: {e}")
            self.logger.exception("Stack trace:")
            self.update_status(f"Error: {str(e)}")
            self.log(f"Error in automation: {str(e)}")

        finally:
            # Remove queue handler from all loggers to prevent memory leaks
            if queue_handler:
                for logger_name in automation_loggers:
                    logger = logging.getLogger(logger_name)
                    logger.removeHandler(queue_handler)

            # Close BlueStacks if configured to do so
            if self.exit_after_complete and bluestacks_controller:
                self.log("Automation complete, closing BlueStacks instance")
                self.close_bluestacks(bluestacks_controller)

            self.log("Automation thread completed")

            # Notify launcher that this thread has completed
            if self.on_complete_callback:
                self.on_complete_callback(self.instance_id)


class MultiInstanceLauncher:
    """Class for launching and managing multiple BlueStacks instances"""

    def __init__(self, instance_manager):
        self.instance_manager = instance_manager
        self.logger = logging.getLogger("multi_launcher")

        # Track running automations
        self.running_threads = {}  # {instance_id: (thread, stop_event)}

        # Message queue for communication between threads
        self.message_queue = Queue()

        # Start message processing thread
        self.is_running = True
        self.message_thread = threading.Thread(target=self._process_messages)
        self.message_thread.daemon = True
        self.message_thread.start()

        # Callbacks
        self.log_callback = None
        self.status_callback = None

        # Default to exit BlueStacks after completion
        self.exit_after_complete = True

    def set_callbacks(self, log_callback=None, status_callback=None):
        """Set callbacks for log and status messages"""
        self.log_callback = log_callback
        self.status_callback = status_callback

    def set_exit_after_complete(self, exit_after_complete):
        """Set whether to exit BlueStacks after automation completes"""
        self.exit_after_complete = exit_after_complete

        # Update all running threads with the new setting
        for instance_id, (thread, stop_event) in self.running_threads.items():
            if thread.is_alive():
                thread.exit_after_complete = exit_after_complete
                self.logger.info(f"Updated exit_after_complete={exit_after_complete} for instance {instance_id}")

    def _on_thread_complete(self, instance_id):
        """Called when an automation thread completes"""
        # Remove from running threads (tolerant of stop_instance not deleting it,
        # or of this being called more than once for the same instance)
        if self.running_threads.pop(instance_id, None) is not None:
            self.logger.info(f"Instance {instance_id} removed from running threads")

        # Send a final status update to refresh the UI
        if self.status_callback:
            self.status_callback(instance_id, "Stopped")

    def _process_messages(self):
        """Process messages from automation threads"""
        while self.is_running:
            try:
                # Get message with timeout to allow checking is_running
                message = self.message_queue.get(timeout=0.5)

                if message["type"] == "log" and self.log_callback:
                    self.log_callback(message["instance_id"], message["message"])

                elif message["type"] == "status" and self.status_callback:
                    self.status_callback(message["instance_id"], message["message"])

                self.message_queue.task_done()

            except queue.Empty:
                # Expected when no message arrives within the timeout
                pass
            except Exception:
                self.logger.exception("Unexpected error processing automation message")

    def launch_instance(self, instance_id, force_daily_tasks=False):
        """Launch automation for a specific instance"""
        # Check if instance is already running
        if instance_id in self.running_threads:
            self.logger.warning(f"Instance {instance_id} is already running")
            return False

        # Get instance info
        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            self.logger.error(f"Instance {instance_id} not found")
            return False

        # Get config manager for this instance
        config_manager = self.instance_manager.get_config_manager(instance_id)
        if not config_manager:
            self.logger.error(f"Failed to get config for instance {instance_id}")
            return False

        # Create stop event
        stop_event = threading.Event()

        # Create and start automation thread
        thread = AutomationThread(
            instance_id=instance_id,
            instance_name=instance["name"],
            config_manager=config_manager,
            queue=self.message_queue,
            stop_event=stop_event,
            exit_after_complete=self.exit_after_complete,
            force_daily_tasks=force_daily_tasks,
            instances_dir=self.instance_manager.instances_dir,
            on_complete_callback=self._on_thread_complete
        )

        # Store thread and stop event
        self.running_threads[instance_id] = (thread, stop_event)

        # Start the thread
        thread.start()

        self.logger.info(f"Started automation for instance {instance['name']} ({instance_id})")
        return True

    def stop_instance(self, instance_id):
        """Stop automation for a specific instance"""
        if instance_id not in self.running_threads:
            self.logger.warning(f"Instance {instance_id} is not running")
            return False

        # Get thread and stop event
        thread, stop_event = self.running_threads[instance_id]

        # Set stop event to signal thread to stop
        stop_event.set()

        # Log the stop request
        self.logger.info(f"Requested stop for instance {instance_id}")

        # Note: We intentionally do NOT remove the instance from running_threads
        # here. The thread hasn't actually stopped yet - it will terminate on its
        # own when it checks the stop event, at which point _on_thread_complete
        # removes it. Until then, get_running_instances() correctly reports it
        # as still running (i.e. "stopping").

        return True

    def stop_all_instances(self):
        """Stop all currently running instances.

        GUI-facing concerns (confirmation dialogs, progress windows, status
        updates) belong to the caller (MultiInstanceManagerGUI.stop_all_instances) -
        this just signals every running instance to stop.
        """
        running_instances = self.get_running_instances()

        for instance_id in running_instances:
            self.stop_instance(instance_id)

        self.logger.info(f"Requested stop for {len(running_instances)} instance(s)")

    def get_running_instances(self):
        """Get list of running instance IDs"""
        return list(self.running_threads.keys())

    def is_instance_running(self, instance_id):
        """Check if an instance is currently running"""
        return instance_id in self.running_threads

    def shutdown(self):
        """Shutdown the launcher and stop all instances"""
        instance_ids = list(self.running_threads.keys())

        for instance_id in instance_ids:
            self.stop_instance(instance_id)

        self.is_running = False

        # Wait for message thread to terminate
        if self.message_thread.is_alive():
            self.message_thread.join(timeout=2.0)
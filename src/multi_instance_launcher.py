#!/usr/bin/env python3
import os
import sys
import time
import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from queue import Queue

from instance_manager import InstanceManager
from config_manager import ConfigManager
from bluestacks_controller import BlueStacksController
from rok_game_controller import RoKGameController


class AutomationThread(threading.Thread):
    """Thread class for running automation on a specific instance"""

    def __init__(self, instance_id, instance_name, config_manager, queue, stop_event=None):
        super().__init__()
        self.instance_id = instance_id
        self.instance_name = instance_name
        self.config_manager = config_manager
        self.queue = queue  # Message queue for communication with main thread
        self.stop_event = stop_event or threading.Event()
        self.daemon = True  # Thread will exit when main program exits

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

    def run(self):
        """Run the automation sequence for this instance"""
        try:
            self.log(f"Starting automation for instance '{self.instance_name}'")
            self.update_status("Starting")

            # Initialize controllers
            bluestacks_controller = BlueStacksController(self.config_manager)

            # Get ADB port from config
            adb_port = self.config_manager.get_config('BlueStacks', 'adb_port', '5555')
            adb_device = f"127.0.0.1:{adb_port}"
            bluestacks_controller.set_adb_device(adb_device)

            # Initialize RoK controller
            rok_controller = RoKGameController(self.config_manager, bluestacks_controller)

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
                return

            # Connect to ADB
            self.log(f"Connecting to ADB on port {adb_port}")
            self.update_status("Connecting to ADB")

            if not bluestacks_controller.connect_adb():
                self.log("Failed to connect to ADB")
                self.update_status("Failed to connect to ADB")
                return

            # Start Rise of Kingdoms
            if self.stop_event.is_set():
                self.log("Automation stopped before launching game")
                self.update_status("Stopped")
                return

            self.log("Starting Rise of Kingdoms")
            self.update_status("Starting RoK")

            if not rok_controller.start_game():
                self.log("Failed to start Rise of Kingdoms")
                self.update_status("Failed to start RoK")
                return

            # Wait for game to load with periodic stop checks
            self.log("Waiting for Rise of Kingdoms to load")
            self.update_status("Game loading")

            # Wait in intervals with stop checks
            total_wait = rok_controller.game_load_wait_seconds
            interval = 2  # Check for stop every 2 seconds

            for _ in range(0, total_wait, interval):
                if self.stop_event.is_set():
                    self.log("Automation stopped during game loading")
                    self.update_status("Stopped")
                    return

                time.sleep(min(interval, total_wait))
                total_wait -= interval

            # Dismiss loading screens
            if self.stop_event.is_set():
                self.log("Automation stopped before dismissing loading screens")
                self.update_status("Stopped")
                return

            rok_controller.wait_for_game_load()

            # Set stop check callback for RoK controller
            rok_controller.stop_check_callback = lambda: self.stop_event.is_set()

            # Start character switching automation
            self.log("Starting character switching automation")
            self.update_status("Running character automation")

            if rok_controller.switch_character():
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
            self.log("Automation thread completed")


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

    def set_callbacks(self, log_callback=None, status_callback=None):
        """Set callbacks for log and status messages"""
        self.log_callback = log_callback
        self.status_callback = status_callback

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

            except Exception:
                # Queue.Empty exception is expected
                pass

    def launch_instance(self, instance_id):
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
            stop_event=stop_event
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

        # Remove from running threads
        # Note: We don't wait for the thread to finish
        # It will terminate on its own when it checks the stop event
        del self.running_threads[instance_id]

        return True

    def stop_all_instances(self):
        """Stop all running instances"""
        instance_ids = list(self.running_threads.keys())

        for instance_id in instance_ids:
            self.stop_instance(instance_id)

        self.logger.info(f"Requested stop for all {len(instance_ids)} running instances")

    def get_running_instances(self):
        """Get list of running instance IDs"""
        return list(self.running_threads.keys())

    def is_instance_running(self, instance_id):
        """Check if an instance is currently running"""
        return instance_id in self.running_threads

    def shutdown(self):
        """Shutdown the launcher and stop all instances"""
        self.stop_all_instances()
        self.is_running = False

        # Wait for message thread to terminate
        if self.message_thread.is_alive():
            self.message_thread.join(timeout=2.0)
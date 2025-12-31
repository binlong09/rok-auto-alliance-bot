import os
import subprocess
import time
import logging
import cv2
import numpy as np


class BlueStacksController:
    """Controller for BlueStacks operations and interactions"""

    def __init__(self, config_manager):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager

        # Load BlueStacks configurations
        bs_config = config_manager.get_bluestacks_config()
        self.bluestacks_exe_path = bs_config.get('bluestacks_exe_path')
        self.bluestacks_instance_name = bs_config.get('bluestacks_instance_name')
        self.adb_path = bs_config.get('adb_path')
        self.wait_for_startup_seconds = int(bs_config.get('wait_for_startup_seconds', 30))

        # Default ADB device address
        self.adb_device = "127.0.0.1:5625"  # Default port, can be overridden

    def set_adb_device(self, device_address):
        """Set the ADB device address (typically IP:PORT)"""
        self.adb_device = device_address

    def start_bluestacks(self):
        """Start BlueStacks with specified instance"""
        self.logger.info(f"Starting BlueStacks instance: {self.bluestacks_instance_name}")

        try:
            if not os.path.exists(self.bluestacks_exe_path):
                self.logger.error(f"BlueStacks executable not found at: {self.bluestacks_exe_path}")
                return False

            cmd = f'"{self.bluestacks_exe_path}" --instance {self.bluestacks_instance_name}'
            subprocess.Popen(cmd, shell=True)

            self.logger.info(f"Waiting {self.wait_for_startup_seconds} seconds for BlueStacks to initialize...")
            time.sleep(self.wait_for_startup_seconds)

            return True

        except Exception as e:
            self.logger.error(f"Error starting BlueStacks: {e}")
            return False

    def connect_adb(self):
        """Connect to BlueStacks via ADB"""
        self.logger.info(f"Connecting to ADB on device: {self.adb_device}")

        try:
            # Connect to the device
            connect_cmd = f'"{self.adb_path}" connect {self.adb_device}'
            result = subprocess.run(connect_cmd, shell=True, capture_output=True, text=True)

            # Verify connection
            verify_cmd = f'"{self.adb_path}" devices'
            verify_result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True)

            if self.adb_device in verify_result.stdout:
                self.logger.info(f"Successfully connected to ADB on device: {self.adb_device}")
                return True
            else:
                self.logger.error(f"Failed to connect to ADB on device: {self.adb_device}")
                return False

        except Exception as e:
            self.logger.error(f"Error connecting to ADB: {e}")
            return False

    def take_screenshot(self):
        """Take a screenshot of the BlueStacks window using ADB"""
        try:
            # Use ADB port to create unique screenshot filename per instance
            # This prevents conflicts when running multiple instances simultaneously
            port = self.adb_device.split(':')[-1] if ':' in self.adb_device else 'default'
            screenshot_path = f"temp_screenshot_{port}.png"

            # Remove old screenshot if exists
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)

            # Take screenshot command
            screenshot_cmd = f'"{self.adb_path}" -s {self.adb_device} shell screencap -p /sdcard/screenshot.png'
            subprocess.run(screenshot_cmd, shell=True, capture_output=True)

            # Pull screenshot to PC
            pull_cmd = f'"{self.adb_path}" -s {self.adb_device} pull /sdcard/screenshot.png {screenshot_path}'
            subprocess.run(pull_cmd, shell=True, capture_output=True)

            # Check if screenshot was saved
            if not os.path.exists(screenshot_path):
                self.logger.error("Failed to save screenshot")
                return None

            # Read the image
            image = cv2.imread(screenshot_path)

            if image is None:
                self.logger.error("Failed to read screenshot image")
                return None

            return image

        except Exception as e:
            self.logger.error(f"Error taking screenshot: {e}")
            return None

    def click(self, x, y, delay_ms=1000):
        """Click at specific coordinates"""
        try:
            # Use ADB to simulate tap
            tap_cmd = f'"{self.adb_path}" -s {self.adb_device} shell input tap {x} {y}'
            result = subprocess.run(tap_cmd, shell=True, capture_output=True)

            # Add delay after click
            time.sleep(delay_ms / 1000)

            return True

        except Exception as e:
            self.logger.error(f"Error clicking at ({x}, {y}): {e}")
            return False

    def swipe(self, start_x, start_y, end_x, end_y, duration_ms=500):
        """Swipe from one point to another"""
        try:
            # Use ADB to simulate swipe
            swipe_cmd = f'"{self.adb_path}" -s {self.adb_device} shell input swipe {start_x} {start_y} {end_x} {end_y} {duration_ms}'
            result = subprocess.run(swipe_cmd, shell=True, capture_output=True)

            # Add delay after swipe
            time.sleep(0.5)

            return True

        except Exception as e:
            self.logger.error(f"Error swiping from ({start_x}, {start_y}) to ({end_x}, {end_y}): {e}")
            return False

    def send_escape(self):
        """Send escape key (back button in Android)"""
        try:
            # Use ADB to send back button keyevent
            key_cmd = f'"{self.adb_path}" -s {self.adb_device} shell input keyevent 4'
            result = subprocess.run(key_cmd, shell=True, capture_output=True)

            # Add delay after key press
            time.sleep(0.5)

            return True

        except Exception as e:
            self.logger.error(f"Error sending escape key: {e}")
            return False
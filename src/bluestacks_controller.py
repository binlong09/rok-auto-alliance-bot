import os
import subprocess
import time
import logging
import cv2
import numpy as np

import timings


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

        # Set on connect_adb() failure to let callers distinguish *why* it failed
        # (e.g. "adb_disabled" so the GUI can show a specific message)
        self.last_connect_error = None

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

            cmd = [self.bluestacks_exe_path, "--instance", self.bluestacks_instance_name]
            subprocess.Popen(cmd)

            self.logger.info(f"Waiting {self.wait_for_startup_seconds} seconds for BlueStacks to initialize...")
            time.sleep(self.wait_for_startup_seconds)

            return True

        except Exception as e:
            self.logger.error(f"Error starting BlueStacks: {e}")
            return False

    def connect_adb(self):
        """Connect to BlueStacks via ADB"""
        self.logger.info(f"Connecting to ADB on device: {self.adb_device}")
        self.last_connect_error = None

        try:
            # Connect to the device
            connect_cmd = [self.adb_path, "connect", self.adb_device]
            result = subprocess.run(connect_cmd, capture_output=True, text=True)

            # Verify connection
            verify_cmd = [self.adb_path, "devices"]
            verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)

            if self.adb_device not in verify_result.stdout:
                self.logger.error(f"Failed to connect to ADB on device: {self.adb_device}")
                self.last_connect_error = "not_found"
                return False

            # The device can show up as connected in `adb devices` while its
            # shell/data channel is still broken (commonly because ADB
            # debugging is disabled inside the BlueStacks instance). Verify a
            # real shell command actually works before trusting the connection.
            if not self._verify_adb_shell():
                self.logger.error(
                    f"Connected to {self.adb_device} but ADB shell commands are not working "
                    "(every 'adb shell' call returns 'error: closed'). This almost always means "
                    "Android Debug Bridge (ADB) is disabled inside this BlueStacks instance. "
                    "Open the instance, go to Settings > Advanced, enable 'Android Debug Bridge (ADB)', "
                    "then restart the instance and try again."
                )
                self.last_connect_error = "adb_disabled"
                return False

            self.logger.info(f"Successfully connected to ADB on device: {self.adb_device}")
            return True

        except Exception as e:
            self.logger.error(f"Error connecting to ADB: {e}")
            self.last_connect_error = "exception"
            return False

    def _verify_adb_shell(self, retries=3, delay_seconds=timings.ADB_RETRY_DELAY):
        """Verify the ADB shell/data channel actually works, not just the transport.

        Retries with a short delay first, since a freshly-connected instance can
        briefly report "closed" before its shell channel is ready.
        """
        check_cmd = [self.adb_path, "-s", self.adb_device, "shell", "echo", "ok"]

        for attempt in range(1, retries + 1):
            try:
                result = subprocess.run(check_cmd, capture_output=True, text=True)
                if "ok" in result.stdout:
                    return True
            except Exception as e:
                self.logger.debug(f"ADB shell verification attempt {attempt} failed: {e}")

            if attempt < retries:
                time.sleep(delay_seconds)

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
            screenshot_cmd = [self.adb_path, "-s", self.adb_device, "shell", "screencap", "-p", "/sdcard/screenshot.png"]
            subprocess.run(screenshot_cmd, capture_output=True)

            # Pull screenshot to PC
            pull_cmd = [self.adb_path, "-s", self.adb_device, "pull", "/sdcard/screenshot.png", screenshot_path]
            subprocess.run(pull_cmd, capture_output=True)

            # Check if screenshot was saved
            if not os.path.exists(screenshot_path):
                self.logger.error("Failed to save screenshot")
                return None

            # Guard against a stale/truncated pull: a failed screencap or an
            # interrupted pull can leave a 0-byte (or otherwise empty) file
            # behind, which cv2.imread may still "succeed" on in odd cases.
            if os.path.getsize(screenshot_path) == 0:
                self.logger.error("Screenshot file is empty (0 bytes) - screencap/pull likely failed")
                return None

            # Read the image
            image = cv2.imread(screenshot_path)

            if image is None:
                self.logger.error("Failed to read screenshot image")
                return None

            # Validate dimensions - a corrupt/truncated PNG can decode to a
            # zero-sized array instead of returning None.
            h, w = image.shape[:2]
            if h == 0 or w == 0:
                self.logger.warning("Screenshot has zero dimensions")
                return None

            expected_w, expected_h = 1280, 720
            if (w, h) != (expected_w, expected_h):
                self.logger.warning(
                    f"Screenshot resolution {w}x{h} differs from expected "
                    f"{expected_w}x{expected_h}"
                )

            # A screencap failure can sometimes still produce a valid-looking
            # but entirely black image. Flag it as a warning (informational
            # only) so automation isn't blocked on a false positive.
            if float(np.mean(image)) < 1.0:
                self.logger.warning("Screenshot appears to be all-black - screencap may have failed")

            return image

        except Exception as e:
            self.logger.error(f"Error taking screenshot: {e}")
            return None

    def click(self, x, y, delay_ms=1000):
        """Click at specific coordinates"""
        try:
            # Use ADB to simulate tap
            tap_cmd = [self.adb_path, "-s", self.adb_device, "shell", "input", "tap", str(x), str(y)]
            result = subprocess.run(tap_cmd, capture_output=True)

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
            swipe_cmd = [
                self.adb_path, "-s", self.adb_device, "shell", "input", "swipe",
                str(start_x), str(start_y), str(end_x), str(end_y), str(duration_ms)
            ]
            result = subprocess.run(swipe_cmd, capture_output=True)

            # Add delay after swipe
            time.sleep(timings.MICRO_DELAY)

            return True

        except Exception as e:
            self.logger.error(f"Error swiping from ({start_x}, {start_y}) to ({end_x}, {end_y}): {e}")
            return False

    def send_escape(self):
        """Send escape key (back button in Android)"""
        try:
            # Use ADB to send back button keyevent
            key_cmd = [self.adb_path, "-s", self.adb_device, "shell", "input", "keyevent", "4"]
            result = subprocess.run(key_cmd, capture_output=True)

            # Add delay after key press
            time.sleep(timings.MICRO_DELAY)

            return True

        except Exception as e:
            self.logger.error(f"Error sending escape key: {e}")
            return False
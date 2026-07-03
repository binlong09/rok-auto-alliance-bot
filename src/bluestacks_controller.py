import os
import re
import sys
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

        # Resolution the coordinate maps (coordinates.json, templates) were
        # captured at. If the instance runs at anything else, every click
        # lands in the wrong place, so ensure_correct_resolution() can fix
        # bluestacks.conf and restart the instance.
        self.expected_width = config_manager.get_int('BlueStacks', 'expected_resolution_width', 1280)
        self.expected_height = config_manager.get_int('BlueStacks', 'expected_resolution_height', 720)
        self.expected_dpi = config_manager.get_int('BlueStacks', 'expected_dpi', 240)
        self.auto_fix_resolution = config_manager.get_bool('BlueStacks', 'auto_fix_resolution', True)
        self.bluestacks_conf_path = bs_config.get('bluestacks_conf_path', '')

        # Default ADB device address
        self.adb_device = "127.0.0.1:5625"  # Default port, can be overridden

        # Set on connect_adb() failure to let callers distinguish *why* it failed
        # (e.g. "adb_disabled" so the GUI can show a specific message)
        self.last_connect_error = None

    def set_adb_device(self, device_address):
        """Set the ADB device address (typically IP:PORT)"""
        self.adb_device = device_address

    def start_bluestacks(self):
        """Start BlueStacks with specified instance.

        Skips launching (and the startup wait) entirely when the instance is
        already up and answering on ADB; otherwise polls for readiness instead
        of sleeping blindly, so a warm instance continues within seconds.
        """
        self.logger.info(f"Starting BlueStacks instance: {self.bluestacks_instance_name}")

        try:
            # Already up and ADB-responsive: nothing to start or wait for.
            if self._is_adb_ready():
                self.logger.info(
                    f"BlueStacks instance '{self.bluestacks_instance_name}' is already "
                    "running and ADB is ready - skipping startup wait")
                return True

            if self._is_instance_process_running():
                self.logger.info(
                    "BlueStacks process is already running but ADB is not ready yet - "
                    "waiting for it instead of launching a second time")
            else:
                if not os.path.exists(self.bluestacks_exe_path):
                    self.logger.error(f"BlueStacks executable not found at: {self.bluestacks_exe_path}")
                    return False

                cmd = [self.bluestacks_exe_path, "--instance", self.bluestacks_instance_name]
                subprocess.Popen(cmd)

            # Poll instead of a blind sleep: continue as soon as ADB responds,
            # bounded by the configured startup wait.
            max_wait = self.wait_for_startup_seconds
            self.logger.info(f"Waiting up to {max_wait} seconds for BlueStacks to initialize...")
            deadline = time.time() + max_wait
            while time.time() < deadline:
                time.sleep(timings.ADB_RETRY_DELAY)
                if self._is_adb_ready():
                    self.logger.info("BlueStacks is ready (ADB responding)")
                    return True

            # Preserve the old contract: after the configured wait we proceed
            # and let connect_adb() do the detailed verification/reporting.
            self.logger.warning(
                f"BlueStacks not ADB-ready after {max_wait}s - proceeding anyway")
            return True

        except Exception as e:
            self.logger.error(f"Error starting BlueStacks: {e}")
            return False

    def _is_adb_ready(self, timeout_seconds=4):
        """Quick probe: connect and run a shell echo. True only when the
        instance is fully responsive on ADB (transport AND shell channel)."""
        try:
            subprocess.run([self.adb_path, "connect", self.adb_device],
                           capture_output=True, text=True, timeout=timeout_seconds)
            result = subprocess.run(
                [self.adb_path, "-s", self.adb_device, "shell", "echo", "ok"],
                capture_output=True, text=True, timeout=timeout_seconds)
            return "ok" in result.stdout
        except Exception:
            return False

    def _is_instance_process_running(self):
        """Check whether an HD-Player.exe process for this specific instance
        is already running (Windows only; same wmic filter the launcher uses
        for shutdown)."""
        if sys.platform != "win32":
            return False
        try:
            cmd = ["wmic", "process", "where",
                   f"name='HD-Player.exe' and commandline like '%{self.bluestacks_instance_name}%'",
                   "get", "processid"]
            info = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            out = info.stdout.strip()
            return 'ProcessId' in out and len(out.splitlines()) > 1
        except Exception as e:
            self.logger.debug(f"BlueStacks process check failed: {e}")
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

    def get_screen_resolution(self):
        """Read the current screen resolution via `adb shell wm size`.

        Returns (width, height) or None if it cannot be determined. When an
        override size is active it takes precedence over the physical size,
        since that is what screencap/input coordinates operate on.
        """
        try:
            result = subprocess.run(
                [self.adb_path, "-s", self.adb_device, "shell", "wm", "size"],
                capture_output=True, text=True, timeout=10)

            physical = None
            override = None
            for line in result.stdout.splitlines():
                match = re.search(r'(Physical|Override) size:\s*(\d+)x(\d+)', line)
                if match:
                    size = (int(match.group(2)), int(match.group(3)))
                    if match.group(1) == 'Override':
                        override = size
                    else:
                        physical = size

            return override or physical

        except Exception as e:
            self.logger.error(f"Error reading screen resolution: {e}")
            return None

    def ensure_correct_resolution(self):
        """Verify the instance runs at the expected resolution; fix and restart if not.

        The whole automation relies on fixed coordinates captured at
        expected_width x expected_height, so a mismatched resolution makes
        every click land in the wrong place. When a mismatch is found (and
        auto_fix_resolution is enabled), this rewrites the instance's
        resolution in bluestacks.conf, restarts the instance and re-checks.

        Returns True when the resolution is correct (or could not be read,
        to avoid blocking automation on a probe failure); False when it is
        wrong and could not be fixed.
        """
        expected = (self.expected_width, self.expected_height)

        current = self.get_screen_resolution()
        if current is None:
            self.logger.warning(
                "Could not read screen resolution - skipping resolution check")
            return True

        if current == expected:
            self.logger.info(f"Screen resolution OK: {current[0]}x{current[1]}")
            return True

        self.logger.warning(
            f"Screen resolution is {current[0]}x{current[1]}, expected "
            f"{expected[0]}x{expected[1]}")

        if not self.auto_fix_resolution:
            self.logger.error(
                "auto_fix_resolution is disabled - set the instance to "
                f"{expected[0]}x{expected[1]} manually in BlueStacks settings")
            return False

        # Stop the instance BEFORE editing bluestacks.conf: BlueStacks
        # rewrites the file on shutdown, which would overwrite our edit.
        self.logger.info("Attempting to fix resolution in bluestacks.conf and restart the instance")
        if not self.stop_instance():
            self.logger.error("Could not stop the BlueStacks instance to fix its resolution")
            return False

        if not self._write_resolution_to_conf(expected[0], expected[1], self.expected_dpi):
            return False

        if not self.start_bluestacks():
            self.logger.error("Failed to restart BlueStacks after fixing resolution")
            return False

        if not self.connect_adb():
            self.logger.error("Failed to reconnect ADB after restarting BlueStacks")
            return False

        current = self.get_screen_resolution()
        if current == expected:
            self.logger.info(
                f"Resolution fixed: instance restarted at {expected[0]}x{expected[1]}")
            return True

        self.logger.error(
            f"Resolution is still {current[0]}x{current[1] if current else '?'} after "
            "restart - fix it manually in BlueStacks settings (Display tab)")
        return False

    def _get_bluestacks_conf_path(self):
        """Locate bluestacks.conf (config override first, then the standard
        %ProgramData%\\BlueStacks_nxt location)."""
        if self.bluestacks_conf_path:
            return self.bluestacks_conf_path

        program_data = os.environ.get('PROGRAMDATA', 'C:\\ProgramData')
        return os.path.join(program_data, 'BlueStacks_nxt', 'bluestacks.conf')

    def _write_resolution_to_conf(self, width, height, dpi):
        """Set this instance's fb_width/fb_height/dpi in bluestacks.conf.

        The file is a flat key="value" list; only this instance's display
        keys are touched, every other line is preserved as-is.
        """
        conf_path = self._get_bluestacks_conf_path()
        if not os.path.exists(conf_path):
            self.logger.error(
                f"bluestacks.conf not found at {conf_path} - set 'bluestacks_conf_path' "
                "in config.ini [BlueStacks] if BlueStacks stores it elsewhere")
            return False

        prefix = f"bst.instance.{self.bluestacks_instance_name}."
        new_values = {
            prefix + "fb_width": str(width),
            prefix + "fb_height": str(height),
            prefix + "dpi": str(dpi),
        }

        try:
            with open(conf_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            remaining = dict(new_values)
            updated_lines = []
            instance_has_entries = False
            for line in lines:
                key = line.split('=', 1)[0].strip()
                if key.startswith(prefix):
                    instance_has_entries = True
                if key in remaining:
                    updated_lines.append(f'{key}="{remaining.pop(key)}"\n')
                else:
                    updated_lines.append(line)

            if remaining and not instance_has_entries:
                # No keys at all for this instance name: almost certainly a
                # wrong instance name, so appending settings would be useless.
                self.logger.error(
                    f"No entries for instance '{self.bluestacks_instance_name}' found in "
                    f"{conf_path} - check 'bluestacks_instance_name' in config.ini")
                return False

            # Instance exists but some display keys are missing: append them.
            for key, value in remaining.items():
                updated_lines.append(f'{key}="{value}"\n')

            with open(conf_path, 'w', encoding='utf-8') as f:
                f.writelines(updated_lines)

            self.logger.info(
                f"Updated {conf_path}: {self.bluestacks_instance_name} set to "
                f"{width}x{height} @ {dpi} DPI")
            return True

        except Exception as e:
            self.logger.error(f"Error updating bluestacks.conf: {e}")
            return False

    def stop_instance(self, wait_seconds=30):
        """Stop this BlueStacks instance (kill its HD-Player.exe process) and
        wait until the process is actually gone."""
        if sys.platform != "win32":
            self.logger.error("stop_instance() is only supported on Windows")
            return False

        try:
            if not self._is_instance_process_running():
                self.logger.info(
                    f"BlueStacks instance '{self.bluestacks_instance_name}' is not running")
                return True

            cmd = ["wmic", "process", "where",
                   f"name='HD-Player.exe' and commandline like '%{self.bluestacks_instance_name}%'",
                   "get", "processid"]
            info = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            for line in info.stdout.strip().splitlines()[1:]:
                pid = line.strip()
                if pid:
                    self.logger.info(f"Stopping BlueStacks instance process (PID {pid})")
                    subprocess.run(["taskkill", "/F", "/PID", pid],
                                   capture_output=True, timeout=10)

            deadline = time.time() + wait_seconds
            while time.time() < deadline:
                if not self._is_instance_process_running():
                    self.logger.info(
                        f"BlueStacks instance '{self.bluestacks_instance_name}' stopped")
                    return True
                time.sleep(timings.POLL_INTERVAL)

            self.logger.error(
                f"BlueStacks instance still running {wait_seconds}s after taskkill")
            return False

        except Exception as e:
            self.logger.error(f"Error stopping BlueStacks instance: {e}")
            return False

    def restart_instance(self):
        """Restart this BlueStacks instance and reconnect ADB."""
        if not self.stop_instance():
            return False
        if not self.start_bluestacks():
            return False
        return self.connect_adb()

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

            expected_w, expected_h = self.expected_width, self.expected_height
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

    def type_text(self, text):
        """Type text into the currently focused input field via ADB.

        `adb shell input text` requires spaces encoded as %s and treats
        several shell metacharacters specially, so they are escaped here.
        Used by the account switcher to enter email/password.
        """
        try:
            escaped = text.replace("\\", "\\\\")
            for ch in "()<>|;&*~\"'$`":
                escaped = escaped.replace(ch, "\\" + ch)
            escaped = escaped.replace(" ", "%s")

            text_cmd = [self.adb_path, "-s", self.adb_device, "shell", "input", "text", escaped]
            subprocess.run(text_cmd, capture_output=True)

            time.sleep(timings.MICRO_DELAY)
            return True

        except Exception as e:
            self.logger.error(f"Error typing text: {e}")
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
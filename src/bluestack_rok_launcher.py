import os
import subprocess
import time
import logging
import configparser
import sys
import cv2
import numpy as np
import pytesseract
from pathlib import Path
from PIL import Image
import io


class BlueStacksRoKLauncher:
    def __init__(self, config_path="config.ini"):
        # Set up logging
        self.package_name = 'com.lilithgame.roc.gp'
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("bluestacks_rok_launcher.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

        # Load configuration
        self.load_config(config_path)

        # ADB connection status
        self.adb_connected = False

        # Setup Tesseract path
        self.tesseract_path = self.config['OCR'].get('tesseract_path', r'C:\Program Files\Tesseract-OCR\tesseract.exe')
        pytesseract.pytesseract.tesseract_cmd = self.tesseract_path

        # Screen region to check for age text (top center of screen)
        self.text_region = {
            'x': int(self.config['OCR'].get('text_region_x', '200')),
            'y': int(self.config['OCR'].get('text_region_y', '20')),
            'width': int(self.config['OCR'].get('text_region_width', '600')),
            'height': int(self.config['OCR'].get('text_region_height', '150'))
        }

    def load_config(self, config_path):
        """Load configuration from ini file"""
        self.config = configparser.ConfigParser()

        # Default config values
        default_config = {
            'BlueStacks': {
                'bluestacks_exe_path': 'C:\\Program Files\\BlueStacks_nxt\\HD-Player.exe',
                'bluestacks_instance_name': 'Nougat32',
                'adb_path': 'C:\\Program Files\\BlueStacks_nxt\\HD-Adb.exe',
                'wait_for_startup_seconds': '30'
            },
            'RiseOfKingdoms': {
                'package_name': 'com.lilithgame.roc.gp',
                'activity_name': 'com.harry.engine.MainActivity'
            },
            'OCR': {
                'tesseract_path': 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe',
                'text_region_x': '200',
                'text_region_y': '20',
                'text_region_width': '600',
                'text_region_height': '150',
                'preprocess_image': 'True'
            }
        }

        # Create default config if not exists
        if not os.path.exists(config_path):
            self.logger.info(f"Creating default configuration at {config_path}")
            self.config.read_dict(default_config)
            with open(config_path, 'w') as configfile:
                self.config.write(configfile)
        else:
            self.config.read(config_path)

        # Load values from config
        bs_config = self.config['BlueStacks']
        rok_config = self.config['RiseOfKingdoms']



        self.bluestacks_exe_path = bs_config.get('bluestacks_exe_path')
        self.bluestacks_instance_name = bs_config.get('bluestacks_instance_name')
        self.adb_path = bs_config.get('adb_path')
        self.wait_for_startup_seconds = int(bs_config.get('wait_for_startup_seconds'))

        self.rok_version = rok_config.get('rok_version', 'global').lower()

        self.package_name = 'com.lilithgame.roc.gp'
        match self.rok_version:
            case 'global':
                self.package_name = 'com.lilithgame.roc.gp'
            case 'kr':
                self.package_name = 'com.lilithgames.rok.gpkr'
            case 'gamota':
                self.package_name = 'com.rok.gp.vn'

        self.rok_activity_name = rok_config.get('activity_name')

        # Validate paths
        if not os.path.exists(self.bluestacks_exe_path):
            self.logger.error(f"BlueStacks executable not found at: {self.bluestacks_exe_path}")
            self.logger.info("Please update the config.ini file with the correct path")
            sys.exit(1)

        if not os.path.exists(self.adb_path):
            self.logger.error(f"ADB executable not found at: {self.adb_path}")
            self.logger.info("Please update the config.ini file with the correct path")
            sys.exit(1)

    def start_bluestacks(self):
        """Start the BlueStacks instance"""
        self.logger.info(f"Starting BlueStacks instance: {self.bluestacks_instance_name}")

        try:
            # Start BlueStacks with specific instance
            cmd = f'"{self.bluestacks_exe_path}" --instance {self.bluestacks_instance_name}'
            subprocess.Popen(cmd, shell=True)

            self.logger.info(f"Waiting {self.wait_for_startup_seconds} seconds for BlueStacks to initialize...")
            time.sleep(self.wait_for_startup_seconds)

            return True
        except Exception as e:
            self.logger.error(f"Failed to start BlueStacks: {e}")
            return False

    def connect_adb(self):
        """Connect to BlueStacks instance via ADB"""
        self.logger.info("Connecting to BlueStacks via ADB...")

        try:
            # Get the ADB port of the BlueStacks instance
            cmd = f'"{self.adb_path}" devices'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if "emulator-5555" not in result.stdout:
                self.logger.info("Connecting to ADB on port 5555...")
                connect_cmd = f'"{self.adb_path}" connect 127.0.0.1:5555'
                connect_result = subprocess.run(connect_cmd, shell=True, capture_output=True, text=True)
                self.logger.info(f"ADB connect result: {connect_result.stdout.strip()}")

            # Verify connection
            verify_cmd = f'"{self.adb_path}" devices'
            verify_result = subprocess.run(verify_cmd, shell=True, capture_output=True, text=True)

            if "emulator-5555" in verify_result.stdout or "127.0.0.1:5555" in verify_result.stdout:
                self.logger.info("Successfully connected to BlueStacks via ADB")
                self.adb_connected = True
                return True
            else:
                self.logger.error("Failed to connect to BlueStacks via ADB")
                self.logger.debug(f"ADB devices output: {verify_result.stdout}")
                return False

        except Exception as e:
            self.logger.error(f"Error connecting to ADB: {e}")
            return False

    def start_rok(self):
        """Start Rise of Kingdoms app"""
        if not self.adb_connected:
            self.logger.error("Cannot start Rise of Kingdoms: Not connected to ADB")
            return False

        self.logger.info("Starting Rise of Kingdoms...")

        try:
            # Use ADB to start the Rise of Kingdoms app
            start_cmd = f'"{self.adb_path}" -s 127.0.0.1:5555 shell am start -n {self.package_name}/{self.rok_activity_name}'
            result = subprocess.run(start_cmd, shell=True, capture_output=True, text=True)

            if "Error" in result.stdout or "error" in result.stderr:
                self.logger.error(f"Failed to start Rise of Kingdoms: {result.stderr}")
                return False

            self.logger.info("Rise of Kingdoms started successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error starting Rise of Kingdoms: {e}")
            return False

    def check_rok_running(self):
        """Check if Rise of Kingdoms is running"""
        if not self.adb_connected:
            return False

        try:
            cmd = f'"{self.adb_path}" -s 127.0.0.1:5555 shell pidof {self.package_name}'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.stdout.strip():
                self.logger.info("Rise of Kingdoms is running")
                return True
            else:
                self.logger.info("Rise of Kingdoms is not running")
                return False

        except Exception as e:
            self.logger.error(f"Error checking if Rise of Kingdoms is running: {e}")
            return False

    def disconnect_adb(self):
        """Disconnect from ADB"""
        if self.adb_connected:
            try:
                cmd = f'"{self.adb_path}" disconnect'
                subprocess.run(cmd, shell=True, capture_output=True)
                self.logger.info("Disconnected from ADB")
                self.adb_connected = False
            except Exception as e:
                self.logger.error(f"Error disconnecting from ADB: {e}")

    def take_screenshot(self):
        """Take a screenshot of the BlueStacks window"""
        if not self.adb_connected:
            self.logger.error("Cannot take screenshot: Not connected to ADB")
            return None

        try:
            # Use ADB to take a screenshot
            temp_path = "/sdcard/screenshot.png"
            cmd_take = f'"{self.adb_path}" -s 127.0.0.1:5555 shell screencap -p {temp_path}'
            subprocess.run(cmd_take, shell=True, check=True)

            # Pull the screenshot to local machine
            local_path = "screenshot.png"
            cmd_pull = f'"{self.adb_path}" -s 127.0.0.1:5555 pull {temp_path} {local_path}'
            subprocess.run(cmd_pull, shell=True, check=True)

            # Remove the file from device
            cmd_rm = f'"{self.adb_path}" -s 127.0.0.1:5555 shell rm {temp_path}'
            subprocess.run(cmd_rm, shell=True)

            # Read the screenshot
            image = cv2.imread(local_path)
            if image is None:
                self.logger.error(f"Failed to read screenshot from {local_path}")
                return None

            return image

        except Exception as e:
            self.logger.error(f"Error taking screenshot: {e}")
            return None

    def crop_text_region(self, image):
        """Crop the image to focus on the region where age text appears"""
        if image is None:
            return None

        height, width = image.shape[:2]

        # Adjust region if it's larger than the image
        region_x = min(self.text_region['x'], width - 1)
        region_y = min(self.text_region['y'], height - 1)
        region_width = min(self.text_region['width'], width - region_x)
        region_height = min(self.text_region['height'], height - region_y)

        # Crop the image
        cropped = image[region_y:region_y + region_height, region_x:region_x + region_width]
        return cropped

    def preprocess_image_for_ocr(self, image):
        """Preprocess the image to improve OCR accuracy for black text on colored backgrounds"""
        if image is None:
            return None

        # Create a copy to avoid modifying the original
        processed = image.copy()

        # Convert to grayscale
        gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)

        # Apply adaptive thresholding to better handle varying backgrounds
        adaptive_thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Save the processed image after adaptive thresholding
        cv2.imwrite("ocr_adaptive_thresh.png", adaptive_thresh)

        # Also try Otsu's thresholding for comparison
        _, otsu_thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        cv2.imwrite("ocr_otsu_thresh.png", otsu_thresh)

        # Try inverting the image (sometimes helps with dark text)
        inverted = cv2.bitwise_not(gray)
        _, inverted_otsu = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        cv2.imwrite("ocr_inverted_otsu.png", inverted_otsu)

        # Increase contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast_enhanced = clahe.apply(gray)
        _, contrast_thresh = cv2.threshold(contrast_enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        cv2.imwrite("ocr_contrast_enhanced.png", contrast_thresh)

        # Return multiple processed versions so we can try OCR on all of them
        return {
            'adaptive': adaptive_thresh,
            'otsu': otsu_thresh,
            'inverted': inverted_otsu,
            'contrast': contrast_thresh,
            'original': gray
        }

    def is_in_home_village(self):
        """Check if the game is currently showing the home village by detecting age-related text"""
        try:
            # Take a screenshot
            screenshot = self.take_screenshot()
            if screenshot is None:
                return False

            # Crop the region where age text appears
            text_region = self.crop_text_region(screenshot)
            cv2.imwrite("text_region.png", text_region)

            # Preprocess the image for better OCR
            if self.config['OCR'].getboolean('preprocess_image', True):
                processed_images = self.preprocess_image_for_ocr(text_region)
            else:
                processed_images = {'original': text_region}

            # Check for age-related keywords
            age_keywords = ["Feudal Age", "Dark Age", "Iron Age", "Bronze Age", "Stone Age", "Feudal"]

            # Try different preprocessing methods
            for method_name, processed_image in processed_images.items():
                # Perform OCR with simplified configurations to avoid quotation errors
                custom_config = '--oem 3 --psm 6'
                text = pytesseract.image_to_string(processed_image, config=custom_config)
                self.logger.info(f"OCR detected text ({method_name}): {text}")

                # Check each keyword
                for keyword in age_keywords:
                    if keyword.lower() in text.lower():
                        self.logger.info(
                            f"Age keyword '{keyword}' detected with method {method_name} - Currently in home village")
                        return True

            # If no keywords found, we're not in home village
            self.logger.info("No age keywords detected in any preprocessing method - Not in home village")
            return False

        except Exception as e:
            self.logger.error(f"Error determining game location: {e}")
            self.logger.exception("Stack trace:")
            return False

    def run(self):
        """Run the full launch sequence"""
        # self.logger.info("Starting BlueStacks Rise of Kingdoms Launcher")
        #
        # # Start BlueStacks
        # if not self.start_bluestacks():
        #     self.logger.error("Failed to start BlueStacks. Exiting.")
        #     return False

        # Connect to ADB
        if not self.connect_adb():
            self.logger.error("Failed to connect to ADB. Exiting.")
            return False

        # Start Rise of Kingdoms
        # if not self.start_rok():
        #     self.logger.error("Failed to start Rise of Kingdoms. Exiting.")
        #     self.disconnect_adb()
        #     return False
        #
        # # Wait for game to fully load
        # self.logger.info("Waiting for Rise of Kingdoms to load...")
        # time.sleep(30)  # Allow time for the game to load

        # Check if we're in home village
        in_home_village = self.is_in_home_village()
        self.logger.info(f"In home village: {in_home_village}")

        self.logger.info("BlueStacks and Rise of Kingdoms started successfully")
        return True


if __name__ == "__main__":
    launcher = BlueStacksRoKLauncher()
    launcher.run()
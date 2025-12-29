#!/usr/bin/env python3
import time
import logging
import cv2
import numpy as np
import pytesseract
import subprocess

from pytesseract import Output
from coordinate_manager import CoordinateManager


class RoKGameController:
    """Controller for Rise of Kingdoms game operations"""

    def __init__(self, config_manager, bluestacks_controller):
        # Set up logging directly within the class
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.bluestacks = bluestacks_controller
        self.package_name = 'com.lilithgame.roc.gp'
        self.stop_check_callback = None  # Function to check if automation should stop

        # Load RoK configurations
        rok_config = config_manager.get_rok_config()
        self.rok_version = rok_config.get('rok_version', 'global').lower()

        # Load bluestacks configuration
        bluestacks_config = config_manager.get_bluestacks_config()
        self.game_load_wait_seconds = int(bluestacks_config.get('wait_for_startup_seconds', 30))
        self.debug_mode = bool(bluestacks_config.get('debug_mode', False))

        self.package_name = 'com.lilithgame.roc.gp'
        match self.rok_version:
            case 'global':
                self.package_name = 'com.lilithgame.roc.gp'
            case 'kr':
                self.package_name = 'com.lilithgames.rok.gpkr'
            case 'gamota':
                self.package_name = 'com.rok.gp.vn'
        self.activity_name = rok_config.get('activity_name')
        self.character_login_screen_loading_time = int(rok_config.get('character_login_screen_loading_time', 3))
        self.will_perform_build = config_manager.get_bool('RiseOfKingdoms', 'perform_build', True)
        self.will_perform_donation = config_manager.get_bool('RiseOfKingdoms', 'perform_donation', True)

        # Load OCR configurations
        ocr_config = config_manager.get_ocr_config()
        pytesseract.pytesseract.tesseract_cmd = ocr_config.get('tesseract_path')

        # Load coordinates from centralized JSON config
        self.coords = CoordinateManager()

        # Navigation coordinates (from coordinates.json)
        self.avatar_icon = self.coords.get_nav('avatar_icon')
        self.settings_icon = self.coords.get_nav('settings_icon')
        self.characters_icon = self.coords.get_nav('characters_icon')
        self.map_button = self.coords.get_nav('map_button')
        self.yes_button = self.coords.get_nav('yes_button')

        # Default text detection region
        self.text_region = self.coords.get_region('default_text')

        # Num Of Chars
        rok_config = config_manager.get_rok_config()
        self.num_of_chars = int(rok_config.get('num_of_characters', 1))
        self.march_preset = int(rok_config.get('march_preset', 1))

        # Character grid positions (from coordinates.json)
        self.character_click_positions_first_rotation = self.coords.get_character_grid('first_rotation')
        self.character_click_positions_after_first_rotation = self.coords.get_character_grid('after_scroll')

        # Click delay from config (timing, not coordinate)
        nav_config = config_manager.get_navigation_config()
        self.click_delay_ms = int(nav_config.get('click_delay_ms', 1000))

    def check_stop_requested(self):
        """Check if automation should stop"""
        if self.stop_check_callback and self.stop_check_callback():
            self.logger.info("Stop requested during RoK operation")
            return True
        return False

    def start_game(self):
        """Start Rise of Kingdoms app"""
        self.logger.info("Starting Rise of Kingdoms...")
        self.logger.info(f"package name: {self.package_name}")
        try:
            # Use ADB to start the Rise of Kingdoms app
            start_cmd = f'"{self.bluestacks.adb_path}" -s {self.bluestacks.adb_device} shell am start -n {self.package_name}/{self.activity_name}'
            result = subprocess.run(start_cmd, shell=True, capture_output=True, text=True)

            if "Error" in result.stdout or "error" in result.stderr:
                self.logger.error(f"Failed to start Rise of Kingdoms: {result.stderr}")
                return False

            self.logger.info("Rise of Kingdoms started successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error starting Rise of Kingdoms: {e}")
            return False

    def wait_for_game_load(self):
        """Wait for the game to load with stop check capability"""
        self.logger.info(f"Waiting {self.game_load_wait_seconds} seconds for game to load...")

        # Wait in smaller chunks to check for stop requests
        total_wait = self.game_load_wait_seconds
        interval = 2  # Check for stop every 2 seconds

        while total_wait > 0:
            if self.check_stop_requested():
                return False

            time.sleep(min(interval, total_wait))
            total_wait -= interval

        return True

    def click_mid_of_screen(self):
        """Click at center of screen to dismiss loading screen or select"""
        self.logger.info("Clicking at middle of game screen to select")
        center = self.coords.get_screen('center')
        if not self.bluestacks.click(center['x'], center['y'], self.click_delay_ms):
            self.logger.error("Failed to click middle of screen")
            return False
        return True

    def dismiss_loading_screen(self):
        """Click to dismiss loading screen"""
        self.logger.info("Clicking to dismiss loading screen")
        pos = self.coords.get_screen('loading_dismiss')
        if not self.bluestacks.click(pos['x'], pos['y'], self.click_delay_ms):
            self.logger.error("Failed to dismiss loading screen")
            return False
        return True

    def close_dialogs(self):
        """Close any open dialogs using escape key or X button"""
        if self.check_stop_requested():
            return False

        self.logger.info("Closing dialogs")

        # Try sending escape key first (more reliable method)
        if self.bluestacks.send_escape():
            self.logger.info("Sent escape key to close dialog")
            time.sleep(1)
            return True

        time.sleep(1)
        return True

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
        if self.debug_mode:
            cv2.imwrite("ocr_adaptive_thresh.png", adaptive_thresh)

        # Also try Otsu's thresholding for comparison
        _, otsu_thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if self.debug_mode:
            cv2.imwrite("ocr_otsu_thresh.png", otsu_thresh)

        # Try inverting the image (sometimes helps with dark text)
        inverted = cv2.bitwise_not(gray)
        _, inverted_otsu = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if self.debug_mode:
            cv2.imwrite("ocr_inverted_otsu.png", inverted_otsu)

        # Increase contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast_enhanced = clahe.apply(gray)
        _, contrast_thresh = cv2.threshold(contrast_enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if self.debug_mode:
            cv2.imwrite("ocr_contrast_enhanced.png", contrast_thresh)

        # Return multiple processed versions so we can try OCR on all of them
        return {
            'adaptive': adaptive_thresh,
            'otsu': otsu_thresh,
            'inverted': inverted_otsu,
            'contrast': contrast_thresh,
            'original': gray
        }

    def detect_text_in_region(self, keywords, text_region=None):
        """
        Detect if any of the keywords appear in the specified text region of the screen

        Args:
            keywords (list): List of keywords to search for
            text_region (dict, optional): Region to search in. Defaults to self.text_region.

        Returns:
            bool: True if any keyword is found, False otherwise
        """
        if self.check_stop_requested():
            return False

        try:
            # Use default text region if not specified
            if text_region is None:
                text_region = self.text_region

            # Take a screenshot
            screenshot = self.bluestacks.take_screenshot()
            if screenshot is None:
                return False

            # Crop the region
            height, width = screenshot.shape[:2]

            # Adjust region if it's larger than the image
            region_x = min(text_region['x'], width - 1)
            region_y = min(text_region['y'], height - 1)
            region_width = min(text_region['width'], width - region_x)
            region_height = min(text_region['height'], height - region_y)

            # Crop the image
            cropped = screenshot[region_y:region_y + region_height, region_x:region_x + region_width]
            cv2.imwrite("text_region.png", cropped)

            # Preprocess the image for better OCR
            if self.config.get_bool('OCR', 'preprocess_image', True):
                processed_images = self.preprocess_image_for_ocr(cropped)
            else:
                processed_images = {'original': cropped}

            # Try different preprocessing methods
            for method_name, processed_image in processed_images.items():
                # Check stop before potentially lengthy OCR
                if self.check_stop_requested():
                    return False

                # Perform OCR with simplified configurations to avoid quotation errors
                custom_config = '--oem 3 --psm 6'
                ocr_result = pytesseract.image_to_string(processed_image, config=custom_config, output_type=Output.DICT)

                # The OCR result is a dictionary with a 'text' key containing the detected text
                detected_text = ocr_result['text'].lower() if 'text' in ocr_result else ""
                self.logger.info(f"OCR detected text ({method_name}): {detected_text}")

                # Check each keyword
                for keyword in keywords:
                    if keyword.lower() in detected_text:
                        self.logger.info(f"Keyword '{keyword}' detected with method {method_name}")
                        return True

            # If no keywords found
            self.logger.info(f"No keywords detected in any preprocessing method")
            return False

        except Exception as e:
            self.logger.error(f"Error detecting text in region: {e}")
            self.logger.exception("Stack trace:")
            return False

    def detect_text_position(self, target_text, text_region=None, exact_match=False):
        """
        Detect the position of specific text in a region of the screen.
        Can accept a single text string or a list of keywords and returns the first match.

        Args:
            target_text (str or list): Text(s) to search for. Can be a single string or a list of strings.
            text_region (dict, optional): Region to search in. Defaults to self.text_region.
            exact_match (bool): Whether to only search for exact match

        Returns:
            dict: Position of text {x, y} if found, None if not found
        """
        if self.check_stop_requested():
            return None

        # Convert single text to list for unified processing
        target_texts = target_text if isinstance(target_text, list) else [target_text]

        try:
            # Use default text region if not specified
            if text_region is None:
                text_region = self.text_region

            # Take a screenshot
            screenshot = self.bluestacks.take_screenshot()
            if screenshot is None:
                return None

            # Crop the region
            height, width = screenshot.shape[:2]

            # Adjust region if it's larger than the image
            region_x = min(text_region['x'], width - 1)
            region_y = min(text_region['y'], height - 1)
            region_width = min(text_region['width'], width - region_x)
            region_height = min(text_region['height'], height - region_y)

            # Crop the image
            cropped = screenshot[region_y:region_y + region_height, region_x:region_x + region_width]
            if self.debug_mode:
                cv2.imwrite("text_search_region.png", cropped)

            # Preprocess the image for better OCR
            if self.config.get_bool('OCR', 'preprocess_image', True):
                processed_images = self.preprocess_image_for_ocr(cropped)
            else:
                processed_images = {'original': cropped}

            # Try different preprocessing methods
            for method_name, processed_image in processed_images.items():
                # Check stop before potentially lengthy OCR
                if self.check_stop_requested():
                    return None

                # Get detailed OCR data including text positions
                custom_config = '--oem 3 --psm 6'
                data = pytesseract.image_to_data(processed_image, config=custom_config,
                                                 output_type=pytesseract.Output.DICT)

                # Filter out empty strings and convert to lowercase
                filtered_texts = []
                filtered_indices = []
                for i, text in enumerate(data['text']):
                    if text.strip():
                        filtered_texts.append(text.lower())
                        filtered_indices.append(i)

                self.logger.info(f"OCR detected texts ({method_name}): {filtered_texts}")

                # If no text detected, try next method
                if not filtered_texts:
                    continue

                # Convert all target texts to lowercase
                target_texts_lower = [t.lower() for t in target_texts]

                # First pass: Check for exact matches for any of the target texts
                for target_text_lower in target_texts_lower:
                    for i, idx in enumerate(filtered_indices):
                        if target_text_lower in filtered_texts[i]:
                            # Calculate Y position correctly (center of text)
                            text_y = region_y + data['top'][idx] + (data['height'][idx] // 2)

                            # For X position, use left edge plus 20% of width instead of center
                            text_x = region_x + data['left'][idx] + int(data['width'][idx] * 0.2)

                            self.logger.info(
                                f"Found text '{target_texts[target_texts_lower.index(target_text_lower)]}' at position: ({text_x}, {text_y})")

                            return {'x': text_x, 'y': text_y}

                # if only allow exact match, skip to next preprocessing method
                if exact_match:
                    continue

                # Second pass: Check for individual words from each target text
                for target_idx, target_text_lower in enumerate(target_texts_lower):
                    target_words = target_text_lower.split()
                    for target_word in target_words:
                        for i, idx in enumerate(filtered_indices):
                            text = filtered_texts[i]
                            if target_word in text:
                                # Calculate Y position as before
                                text_y = region_y + data['top'][idx] + (data['height'][idx] // 2)

                                # For X position:
                                # Find the approximate position of the word within the text
                                # and offset from the left edge accordingly
                                word_index = text.find(target_word)
                                if word_index > 0:
                                    # Estimate the X position based on character position
                                    # Assuming an average character width proportional to total width
                                    char_width = data['width'][idx] / len(text)
                                    text_x = region_x + data['left'][idx] + int(word_index * char_width)
                                else:
                                    # If word is at the beginning, use left edge plus small offset
                                    text_x = region_x + data['left'][idx] + 5

                                self.logger.info(
                                    f"Found word '{target_word}' from '{target_texts[target_idx]}' at position: ({text_x}, {text_y})")

                                # Also save a debug image showing where we're clicking
                                if self.debug_mode:
                                    debug_img = screenshot.copy()
                                    cv2.circle(debug_img, (text_x, text_y), 10, (0, 255, 0), -1)
                                    cv2.imwrite("text_position_debug.png", debug_img)

                                return {'x': text_x, 'y': text_y}

                # Check for stop again before continuing with fallback approach
                if self.check_stop_requested():
                    return None

                # Third pass (fallback): Join all detected text and look for any target word
                joined_text = ' '.join(filtered_texts)
                for target_idx, target_text_lower in enumerate(target_texts_lower):
                    target_words = target_text_lower.split()
                    if any(word in joined_text for word in target_words):
                        # Pick the first detected text area that contains any target word
                        for i, idx in enumerate(filtered_indices):
                            text = filtered_texts[i]
                            # Check if any word from the current target text is in this detected text
                            matching_words = [word for word in target_words if word in text]
                            if matching_words:
                                # Calculate Y position
                                text_y = region_y + data['top'][idx] + (data['height'][idx] // 2)

                                # For X position, use a position 1/4 of the way into the text element
                                text_x = region_x + data['left'][idx] + (data['width'][idx] // 4)

                                self.logger.info(
                                    f"Found partial match for '{target_texts[target_idx]}' at position: ({text_x}, {text_y})")

                                # Save debug image
                                if self.debug_mode:
                                    debug_img = screenshot.copy()
                                    cv2.circle(debug_img, (text_x, text_y), 10, (0, 0, 255), -1)
                                    cv2.imwrite("text_position_fallback.png", debug_img)

                                return {'x': text_x, 'y': text_y}

            keywords_list = ", ".join(target_texts)
            self.logger.info(f"None of the keywords [{keywords_list}] found in region")
            return None

        except Exception as e:
            self.logger.error(f"Error detecting text position: {e}")
            self.logger.exception("Stack trace:")
            return None


    def navigate_to_bookmark(self):
        """Navigate to bookmark screen from home screen"""
        if self.check_stop_requested():
            return False

        self.logger.info("Navigating to bookmark screen")

        bookmark_button = self.coords.get_nav('bookmark_button')
        if not self.bluestacks.click(bookmark_button['x'], bookmark_button['y'], self.click_delay_ms):
            self.logger.error("Failed to click on bookmark button")
            return False

        time.sleep(2)
        return True

    def find_closest_value(self, x, array):
        """
        Returns the closest value to x from the provided array.

        Args:
            x: The target value to find the closest match for
            array: The list of values to search through

        Returns:
            The value from array that is closest to x
        """
        return min(array, key=lambda val: abs(val - x))


    def find_and_click_one_troop_button(self):
        """
        Locate "1 troop" button and click the corresponding Go button.

        Returns:
            bool: True if found and clicked, False otherwise
        """
        if self.check_stop_requested():
            return False

        one_troop_region = self.coords.get_region('one_troop')
        result = self.detect_text_position("troop", one_troop_region)
        if not result:
            self.logger.error("Could not find '1 troop' text")
            return False

        go_button_y_positions = self.coords.get_go_button_y_positions()
        go_button_y = self.find_closest_value(result['y'], go_button_y_positions)
        go_button_x = self.coords.get_go_button_x()

        if not self.bluestacks.click(go_button_x, go_button_y, self.click_delay_ms):
            self.logger.error("Failed to click on one troop button")
            return False

        time.sleep(3)
        self.click_mid_of_screen()
        time.sleep(1)
        return True

    def find_and_click_build_button(self):
        """
        Locate "building progress" button and click it.

        Returns:
            bool: True if found and clicked, False otherwise
        """
        if self.check_stop_requested():
            return False

        build_region = self.coords.get_region('build_button')
        result = self.detect_text_position(["remaining", "time"], build_region)
        if result:
            offset_y = self.coords.get_offset('build_button_offset_y')
            build_button_y = result['y'] + offset_y
            time.sleep(2)
            if not self.bluestacks.click(result['x'], build_button_y, self.click_delay_ms):
                self.logger.error("Failed to click on build button")
                return False
            self.logger.info("Clicking build button")
            time.sleep(2)
            return True
        else:
            self.logger.error("Build button not found")
            return False

    def find_and_click_tap_to_join_button(self):
        """
        Locate "tap to join" button and click it.

        Returns:
            bool: True if found and clicked, False otherwise
        """
        if self.check_stop_requested():
            return False

        tap_region = self.coords.get_region('tap_to_join')
        time.sleep(1)
        result = self.detect_text_position("tap", tap_region)
        if result:
            if not self.bluestacks.click(result['x'], result['y'], self.click_delay_ms):
                self.logger.error("Failed to click on tap to join button")
                return False
            return True
        else:
            self.logger.error("Tap to join button not found")
            return False

    def find_and_click_new_troop_button(self):
        """
        Locate "Dispatch" button for new troop and click it.

        Returns:
            bool: True if found and clicked, False otherwise
        """
        if self.check_stop_requested():
            return False

        new_troop_region = self.coords.get_region('new_troop')
        time.sleep(1)
        result = self.detect_text_position("Dispatch", new_troop_region)
        if result:
            # New troop button is 90px below the Dispatch text
            new_troop_button_y = result['y'] + 90
            if not self.bluestacks.click(result['x'], new_troop_button_y, self.click_delay_ms):
                self.logger.error("Failed to click on New Troop button")
                return False
            return True
        else:
            self.logger.error("New Troop Button not found. Not enough available marches")
            return False

    def dispatch_troop_to_join_build(self):
        """Dispatch troops using the configured march preset."""
        if self.check_stop_requested():
            return False

        self.logger.info("Dispatching troops")

        # Get preset button position from coordinates
        preset_button = self.coords.get_march_preset_position(self.march_preset)

        if not self.bluestacks.click(preset_button['x'], preset_button['y'], self.click_delay_ms):
            self.logger.error(f"Failed to click on preset {self.march_preset} button")
            return False

        time.sleep(2)

        if self.check_stop_requested():
            return False

        march_button = self.coords.get_nav('march_button')
        if not self.bluestacks.click(march_button['x'], march_button['y'], self.click_delay_ms):
            self.logger.error("Failed to click march button")
            return False

        time.sleep(2)
        return True

    def perform_build(self):
        """Perform the build automation sequence"""
        if self.check_stop_requested():
            return False

        self.logger.info("Starting build automation")

        # Navigate to map
        self.navigate_to_map()

        # Navigate to bookmark screen
        self.navigate_to_bookmark()

        # Find the word 1 troop on screen and click on Go button
        # Then click on middle to select the flag
        if self.find_and_click_one_troop_button():
            # Find the word Building Progress on screen and use it to click on Build Button
            # If the word Building Progress is not found, it means the flag is already finished or an invalid object
            if self.find_and_click_build_button():
                # Find the word Tap To Join on screen and click it
                if self.find_and_click_tap_to_join_button():
                    # Find and Click new troop button
                    if self.find_and_click_new_troop_button():
                        success = self.dispatch_troop_to_join_build()
                        if not success:
                            self.logger.warning("Failed to dispatch troops")
                    else:  # If the word Dispatch is not found, it means there are no available marches to send out
                        # Exit once
                        self.close_dialogs()
                else:  # If the word Tap To Join is not found, it means this account already fills the flag
                    # Exit once
                    self.close_dialogs()
        else:
            self.logger.warning("Cannot find 1 troop button")
            self.close_dialogs()

        self.logger.info("Build automation completed")
        return True

    def is_in_home_village(self, custom_region=None):
        """
        Check if the game is currently showing the home village

        Args:
            custom_keywords (list, optional): Custom keywords to look for. Defaults to age-related keywords.
            custom_region (dict, optional): Custom region to look in. Defaults to self.text_region.

        Returns:
            bool: True if in home village, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Default age-related keywords
        age_keywords = ["Feudal Age", "Dark Age", "Iron Age", "Bronze Age", "Stone Age"]

        # Check for the keywords
        result = self.detect_text_in_region(age_keywords, custom_region)

        if result:
            self.logger.info("Currently in home village")
        else:
            self.logger.info("Not in home village")

        return result

    def is_in_map_screen(self):
        """
        Check if the game is currently showing the map screen.

        Returns:
            bool: True if in map screen, False otherwise
        """
        if self.check_stop_requested():
            return False

        # Check for kingdom number
        keywords = ["3174", "1960"]
        region = self.coords.get_region('kingdom_check')

        result = self.detect_text_in_region(keywords, region)

        if result:
            self.logger.info("Currently in map screen")
        else:
            self.logger.info("Not in map screen")

        return result

    def is_in_character_login(self, custom_keywords=None):
        """
        Check if the game is currently showing the character login screen.

        Args:
            custom_keywords (list, optional): Custom keywords to look for.

        Returns:
            bool: True if in character login screen, False otherwise
        """
        if self.check_stop_requested():
            return False

        keywords = ["Character Login", "Log in"]
        keywords_to_check = custom_keywords if custom_keywords is not None else keywords

        region = self.coords.get_region('character_login')
        result = self.detect_text_in_region(keywords_to_check, region)

        if result:
            self.logger.info("Currently in Character Login Screen")
        else:
            self.logger.info("Not in Character Login Screen")

        return result

    def is_bottom_bar_expanded(self):
        """
        Check if the bottom navigation bar is expanded.

        Returns:
            bool: True if bottom bar is expanded, False otherwise
        """
        if self.check_stop_requested():
            return False

        keywords = ["Campaign", "Items", "Alliance", "Commander", "Mail"]
        region = self.coords.get_region('bottom_bar')

        result = self.detect_text_in_region(keywords, region)

        if result:
            self.logger.info("Bottom bar is already expanded")
        else:
            self.logger.info("Bottom bar is not expanded")

        return result

    def is_char_in_alliance(self):
        """
        Detect if this account is in an alliance.

        Returns:
            bool: True if in alliance, False otherwise
        """
        if self.check_stop_requested():
            return False

        keywords = ["Technology", "Territory"]
        region = self.coords.get_region('alliance_check')

        result = self.detect_text_in_region(keywords, region)

        if result:
            self.logger.info("Account is in an alliance")
        else:
            self.logger.info("Account is not in an alliance")

        return result

    def find_and_donate_recommended_technology(self):
        """
        Find Officer's Recommendation and donate to it.

        Returns:
            bool: True if successful, False otherwise
        """
        if self.check_stop_requested():
            return False

        region = self.coords.get_region('officer_recommendation')

        # Find the position of "Officer's Recommendation" text
        result = self.detect_text_position(
            ["Officer's Recommendation", "Officer", "Recommendation", "mendation"],
            region
        )
        if result:
            offset = self.coords.get_offset('officer_recommendation_click')
            click_x = result['x'] + offset['x']
            click_y = result['y'] + offset['y']

            if not self.bluestacks.click(click_x, click_y, self.click_delay_ms):
                self.logger.error("Failed to click on Recommended Tech")
                return False

            donate_button = self.coords.get_nav('donate_button')
            # Click Donate 20 times
            for i in range(20):
                self.bluestacks.click(donate_button['x'], donate_button['y'], 500)

            # Exit to home screen after donation completes
            for i in range(3):
                self.close_dialogs()
            return True
        else:
            self.logger.error("Recommended Tech not found")
            for i in range(2):
                self.close_dialogs()
            return False



    def navigate_to_map(self):
        """Click on map button and check if we're on the map view now"""
        if self.check_stop_requested():
            return False

        try:
            # Check if we are in home village
            # is_home_village = self.is_in_home_village()
            # # Click on the map button if screen is on home village
            # if is_home_village:
            #     if not self.bluestacks.click(self.map_button['x'], self.map_button['y'], self.click_delay_ms):
            #         self.logger.error("Failed to click on map button")
            #         return False
            #     # Wait a moment for the transition
            #     self.logger.info("Clicked on map button because screen was on home village")
            #     time.sleep(2)

            # Check again to see if we're now on the map (NOT in home village)
            is_on_map = self.is_in_map_screen()

            # Go to map again if not in map
            if not is_on_map:
                if not self.bluestacks.click(self.map_button['x'], self.map_button['y'], self.click_delay_ms):
                    self.logger.error("Failed to click on map button")
                    return False
                # Wait a moment for the transition
                self.logger.info("Clicked on map button because screen was on home village")
                time.sleep(2)

            return True

        except Exception as e:
            self.logger.error(f"Error navigating to map: {e}")
            self.logger.exception("Stack trace:")
            return False

    def scroll_down(self):
        """Scroll down in the character list"""
        if self.check_stop_requested():
            return False

        self.logger.info("Scrolling down character list")

        scroll = self.coords.get_scroll('character_list')
        start = scroll['start']
        end = scroll['end']
        duration = scroll['duration_ms']

        if not self.bluestacks.swipe(start['x'], start['y'], end['x'], end['y'], duration):
            self.logger.error("Failed to scroll down")
            return False

        time.sleep(1.5)
        return True

    def expand_bottom_bar(self):
        """Expand bottom bar if it's not expanded yet"""
        if not self.is_bottom_bar_expanded():
            expand_button = self.coords.get_nav('expand_button')
            if not self.bluestacks.click(expand_button['x'], expand_button['y'], self.click_delay_ms):
                self.logger.error('Failed to expand bottom bar')
                return False

        self.logger.info("Bottom bar is expanded")
        time.sleep(1)
        return True

    def perform_recommended_tech_donation(self):
        """Open the alliance tech screen, find officer's recommendation and donate.
        Exit to home screen if Officer's recommendation is not found."""
        if not self.expand_bottom_bar():
            self.logger.error("Bottom bar is not expanded")
            return False

        if self.check_stop_requested():
            return False

        alliance_button = self.coords.get_nav('alliance_button')
        if not self.bluestacks.click(alliance_button['x'], alliance_button['y'], self.click_delay_ms):
            self.logger.error("Failed to open alliance screen")
            return False

        self.logger.info("Alliance screen opened")
        time.sleep(2)

        if not self.is_char_in_alliance():
            self.close_dialogs()
            self.logger.error("Character is not in alliance")
            return False

        technology_button = self.coords.get_nav('technology_button')
        if not self.bluestacks.click(technology_button['x'], technology_button['y'], self.click_delay_ms):
            self.logger.error("Failed to open technology screen")
            return True

        self.logger.info("Tech screen opened")
        time.sleep(6)

        if not self.find_and_donate_recommended_technology():
            self.logger.error("Failed to find and donate recommended technology")
            return False

        self.logger.info("Donate recommended technology completed")
        time.sleep(1)
        return True

    def open_character_selection(self):
        """Open the character selection screen"""
        if self.check_stop_requested():
            return False

        self.logger.info("Opening character selection screen")

        # Click avatar icon in top left
        self.logger.info("Clicking avatar icon")
        if not self.bluestacks.click(self.avatar_icon['x'], self.avatar_icon['y'], self.click_delay_ms):
            self.logger.error("Failed to click avatar icon")
            return False

        # Wait for profile screen to appear
        time.sleep(2)

        if self.check_stop_requested():
            return False

        # Click settings icon
        self.logger.info("Clicking settings icon")
        if not self.bluestacks.click(self.settings_icon['x'], self.settings_icon['y'], self.click_delay_ms):
            self.logger.error("Failed to click settings icon")
            return False

        # Wait for settings screen to appear
        time.sleep(2)

        if self.check_stop_requested():
            return False

        # Click characters icon
        self.logger.info("Clicking characters icon")
        if not self.bluestacks.click(self.characters_icon['x'], self.characters_icon['y'], self.click_delay_ms):
            self.logger.error("Failed to click characters icon")
            return False

        # Wait for character selection screen to appear
        time.sleep(6)

        self.logger.info("Character selection screen opened")
        return True

    def switch_character(self):
        """Main function to switch through all star characters"""
        self.logger.info("Starting character"
                         " switching process")

        # Set starting character index - you may want to make this configurable
        start_idx = 0

        for i in range(start_idx, self.num_of_chars):
            if self.check_stop_requested():
                self.logger.info("Automation stopped during character switching")
                return False

            self.logger.info(f"Processing character {i + 1} of {self.num_of_chars}")

            if not self.open_character_selection():
                self.logger.error("Failed to open character selection screen")
                return False

            # Get the current rotation
            current_rotation = int(np.ceil((i + 1) / 6))
            self.logger.info(f"Current character index: {i}")
            self.logger.info(f"Current rotation: {current_rotation}")

            # Perform necessary scrolls to reach the right screen
            for j in range(1, current_rotation):
                if self.check_stop_requested():
                    return False

                self.scroll_down()
                # Wait for scroll to finish
                time.sleep(2)

            # Calculate position index in the current grid (0-5)
            pos_idx = i % 6

            # Choose position based on rotation
            if current_rotation == 1:
                pos = self.character_click_positions_first_rotation[pos_idx]
            else:
                pos = self.character_click_positions_after_first_rotation[pos_idx]

            # Click on the character portrait
            if not self.bluestacks.click(pos['x'], pos['y'], self.click_delay_ms):
                self.logger.error(f"Failed to click character at position {pos}")
                return False

            # Wait for character login screen to load
            time.sleep(self.character_login_screen_loading_time)

            if self.check_stop_requested():
                return False

            # Check if this screen is now character login screen
            if self.is_in_character_login():
                # Click the "Yes" button to confirm character switch
                if not self.bluestacks.click(self.yes_button['x'], self.yes_button['y'], self.click_delay_ms):
                    self.logger.error(f"Failed to click Yes to character login")
                    return False

                # Wait for character load
                self.logger.info("Waiting for character to load...")
                self.wait_for_game_load()

                if self.check_stop_requested():
                    return False

            else:
                # This means that the character being selected is already the current one
                self.logger.info("Character already selected, returning to main screen")
                # Escape to main screen
                for x in range(3):
                    if self.check_stop_requested():
                        return False
                    self.close_dialogs()
                    time.sleep(1)

            if self.check_stop_requested():
                return False

            # Perform configured actions for this character
            if self.will_perform_build:
                self.logger.info("Performing build for this character")
                self.perform_build()

            if self.check_stop_requested():
                return False

            if self.will_perform_donation:
                # Alliance donation not yet implemented
                self.logger.info("Perform Alliance Donation for this character")
                time.sleep(1)
                self.perform_recommended_tech_donation()

            self.logger.info(f"Completed processing character at position {pos}")

        self.logger.info("Character switching automation completed successfully")
        return True


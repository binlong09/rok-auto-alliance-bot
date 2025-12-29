#!/usr/bin/env python3
"""
OCR Helper - Centralized text detection and image processing for OCR.

This module handles all OCR-related operations including image preprocessing,
text detection, and text position finding.
"""
import logging
import cv2
import numpy as np
import pytesseract
from pytesseract import Output


class OCRHelper:
    """Helper class for OCR operations and text detection."""

    def __init__(self, bluestacks, coords, config, stop_check_callback=None, debug_mode=False):
        """
        Initialize the OCR helper.

        Args:
            bluestacks: BlueStacksController instance for screenshots
            coords: CoordinateManager instance for regions
            config: ConfigManager instance for OCR settings
            stop_check_callback: Optional callback to check if automation should stop
            debug_mode: Whether to save debug images
        """
        self.logger = logging.getLogger(__name__)
        self.bluestacks = bluestacks
        self.coords = coords
        self.config = config
        self.stop_check = stop_check_callback
        self.debug_mode = debug_mode

        # Default text detection region
        self.default_region = coords.get_region('default_text')

        # Configure tesseract path
        ocr_config = config.get_ocr_config()
        pytesseract.pytesseract.tesseract_cmd = ocr_config.get('tesseract_path')

    def check_stop_requested(self):
        """Check if automation should stop."""
        if self.stop_check and self.stop_check():
            self.logger.info("Stop requested during OCR operation")
            return True
        return False

    def preprocess_image_for_ocr(self, image):
        """
        Preprocess the image to improve OCR accuracy for black text on colored backgrounds.

        Args:
            image: Input image (numpy array)

        Returns:
            dict: Dictionary of preprocessed images using different methods
        """
        if image is None:
            return None

        processed = image.copy()
        gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)

        # Adaptive thresholding
        adaptive_thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        if self.debug_mode:
            cv2.imwrite("ocr_adaptive_thresh.png", adaptive_thresh)

        # Otsu's thresholding
        _, otsu_thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if self.debug_mode:
            cv2.imwrite("ocr_otsu_thresh.png", otsu_thresh)

        # Inverted Otsu's
        inverted = cv2.bitwise_not(gray)
        _, inverted_otsu = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if self.debug_mode:
            cv2.imwrite("ocr_inverted_otsu.png", inverted_otsu)

        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast_enhanced = clahe.apply(gray)
        _, contrast_thresh = cv2.threshold(contrast_enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if self.debug_mode:
            cv2.imwrite("ocr_contrast_enhanced.png", contrast_thresh)

        return {
            'adaptive': adaptive_thresh,
            'otsu': otsu_thresh,
            'inverted': inverted_otsu,
            'contrast': contrast_thresh,
            'original': gray
        }

    def detect_text_in_region(self, keywords, text_region=None):
        """
        Detect if any of the keywords appear in the specified text region of the screen.

        Args:
            keywords (list): List of keywords to search for
            text_region (dict, optional): Region to search in {x, y, width, height}

        Returns:
            bool: True if any keyword is found, False otherwise
        """
        if self.check_stop_requested():
            return False

        try:
            if text_region is None:
                text_region = self.default_region

            screenshot = self.bluestacks.take_screenshot()
            if screenshot is None:
                return False

            height, width = screenshot.shape[:2]

            # Adjust region bounds
            region_x = min(text_region['x'], width - 1)
            region_y = min(text_region['y'], height - 1)
            region_width = min(text_region['width'], width - region_x)
            region_height = min(text_region['height'], height - region_y)

            cropped = screenshot[region_y:region_y + region_height, region_x:region_x + region_width]
            cv2.imwrite("text_region.png", cropped)

            # Preprocess
            if self.config.get_bool('OCR', 'preprocess_image', True):
                processed_images = self.preprocess_image_for_ocr(cropped)
            else:
                processed_images = {'original': cropped}

            # Try different preprocessing methods
            for method_name, processed_image in processed_images.items():
                if self.check_stop_requested():
                    return False

                custom_config = '--oem 3 --psm 6'
                ocr_result = pytesseract.image_to_string(processed_image, config=custom_config, output_type=Output.DICT)

                detected_text = ocr_result['text'].lower() if 'text' in ocr_result else ""
                self.logger.info(f"OCR detected text ({method_name}): {detected_text}")

                for keyword in keywords:
                    if keyword.lower() in detected_text:
                        self.logger.info(f"Keyword '{keyword}' detected with method {method_name}")
                        return True

            self.logger.info("No keywords detected in any preprocessing method")
            return False

        except Exception as e:
            self.logger.error(f"Error detecting text in region: {e}")
            self.logger.exception("Stack trace:")
            return False

    def detect_text_position(self, target_text, text_region=None, exact_match=False):
        """
        Detect the position of specific text in a region of the screen.

        Args:
            target_text (str or list): Text(s) to search for
            text_region (dict, optional): Region to search in {x, y, width, height}
            exact_match (bool): Whether to only search for exact match

        Returns:
            dict: Position of text {x, y} if found, None if not found
        """
        if self.check_stop_requested():
            return None

        target_texts = target_text if isinstance(target_text, list) else [target_text]

        try:
            if text_region is None:
                text_region = self.default_region

            screenshot = self.bluestacks.take_screenshot()
            if screenshot is None:
                return None

            height, width = screenshot.shape[:2]

            region_x = min(text_region['x'], width - 1)
            region_y = min(text_region['y'], height - 1)
            region_width = min(text_region['width'], width - region_x)
            region_height = min(text_region['height'], height - region_y)

            cropped = screenshot[region_y:region_y + region_height, region_x:region_x + region_width]
            if self.debug_mode:
                cv2.imwrite("text_search_region.png", cropped)

            if self.config.get_bool('OCR', 'preprocess_image', True):
                processed_images = self.preprocess_image_for_ocr(cropped)
            else:
                processed_images = {'original': cropped}

            for method_name, processed_image in processed_images.items():
                if self.check_stop_requested():
                    return None

                custom_config = '--oem 3 --psm 6'
                data = pytesseract.image_to_data(processed_image, config=custom_config,
                                                 output_type=pytesseract.Output.DICT)

                filtered_texts = []
                filtered_indices = []
                for i, text in enumerate(data['text']):
                    if text.strip():
                        filtered_texts.append(text.lower())
                        filtered_indices.append(i)

                self.logger.info(f"OCR detected texts ({method_name}): {filtered_texts}")

                if not filtered_texts:
                    continue

                target_texts_lower = [t.lower() for t in target_texts]

                # First pass: exact matches
                for target_text_lower in target_texts_lower:
                    for i, idx in enumerate(filtered_indices):
                        if target_text_lower in filtered_texts[i]:
                            text_y = region_y + data['top'][idx] + (data['height'][idx] // 2)
                            text_x = region_x + data['left'][idx] + int(data['width'][idx] * 0.2)
                            self.logger.info(f"Found text '{target_texts[target_texts_lower.index(target_text_lower)]}' at position: ({text_x}, {text_y})")
                            return {'x': text_x, 'y': text_y}

                if exact_match:
                    continue

                # Second pass: individual words
                for target_idx, target_text_lower in enumerate(target_texts_lower):
                    target_words = target_text_lower.split()
                    for target_word in target_words:
                        for i, idx in enumerate(filtered_indices):
                            text = filtered_texts[i]
                            if target_word in text:
                                text_y = region_y + data['top'][idx] + (data['height'][idx] // 2)
                                word_index = text.find(target_word)
                                if word_index > 0:
                                    char_width = data['width'][idx] / len(text)
                                    text_x = region_x + data['left'][idx] + int(word_index * char_width)
                                else:
                                    text_x = region_x + data['left'][idx] + 5

                                self.logger.info(f"Found word '{target_word}' from '{target_texts[target_idx]}' at position: ({text_x}, {text_y})")

                                if self.debug_mode:
                                    debug_img = screenshot.copy()
                                    cv2.circle(debug_img, (text_x, text_y), 10, (0, 255, 0), -1)
                                    cv2.imwrite("text_position_debug.png", debug_img)

                                return {'x': text_x, 'y': text_y}

                if self.check_stop_requested():
                    return None

                # Third pass: joined text fallback
                joined_text = ' '.join(filtered_texts)
                for target_idx, target_text_lower in enumerate(target_texts_lower):
                    target_words = target_text_lower.split()
                    if any(word in joined_text for word in target_words):
                        for i, idx in enumerate(filtered_indices):
                            text = filtered_texts[i]
                            matching_words = [word for word in target_words if word in text]
                            if matching_words:
                                text_y = region_y + data['top'][idx] + (data['height'][idx] // 2)
                                text_x = region_x + data['left'][idx] + (data['width'][idx] // 4)

                                self.logger.info(f"Found partial match for '{target_texts[target_idx]}' at position: ({text_x}, {text_y})")

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

    @staticmethod
    def find_closest_value(x, array):
        """
        Returns the closest value to x from the provided array.

        Args:
            x: The target value to find the closest match for
            array: The list of values to search through

        Returns:
            The value from array that is closest to x
        """
        return min(array, key=lambda val: abs(val - x))

    def detect_red_banner_position(self, search_region=None):
        """
        Detect the position of the red "Officer's Recommendation" banner using color detection.

        This is more reliable than OCR for white text on red background.
        Red in HSV wraps around 0/180, so we check both ranges.

        Args:
            search_region (dict, optional): Region to search in {x, y, width, height}

        Returns:
            dict: Position of banner center {x, y} if found, None if not found
        """
        if self.check_stop_requested():
            return None

        try:
            if search_region is None:
                search_region = self.coords.get_region('officer_recommendation')

            screenshot = self.bluestacks.take_screenshot()
            if screenshot is None:
                self.logger.error("Failed to take screenshot for red banner detection")
                return None

            height, width = screenshot.shape[:2]

            # Crop to search region
            region_x = min(search_region['x'], width - 1)
            region_y = min(search_region['y'], height - 1)
            region_width = min(search_region['width'], width - region_x)
            region_height = min(search_region['height'], height - region_y)

            cropped = screenshot[region_y:region_y + region_height, region_x:region_x + region_width]

            if self.debug_mode:
                cv2.imwrite("red_banner_search_region.png", cropped)

            # Convert to HSV
            hsv = cv2.cvtColor(cropped, cv2.COLOR_BGR2HSV)

            # Get color detection config
            color_config = self.coords.get_color_detection('officer_recommendation_banner')

            # Red wraps around in HSV, so we need two ranges
            lower1 = np.array(color_config['hsv_lower'])
            upper1 = np.array(color_config['hsv_upper'])
            lower2 = np.array(color_config['hsv_lower_wrap'])
            upper2 = np.array(color_config['hsv_upper_wrap'])
            min_area = color_config.get('min_contour_area', 500)

            # Create masks for both red ranges
            mask1 = cv2.inRange(hsv, lower1, upper1)
            mask2 = cv2.inRange(hsv, lower2, upper2)
            mask = cv2.bitwise_or(mask1, mask2)

            if self.debug_mode:
                cv2.imwrite("red_banner_mask.png", mask)

            # Find contours
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                self.logger.info("No red regions found in search area")
                return None

            # Find the largest contour that meets minimum area
            valid_contours = [c for c in contours if cv2.contourArea(c) >= min_area]

            if not valid_contours:
                self.logger.info(f"No red regions large enough (min area: {min_area})")
                return None

            # Get the largest valid contour (likely the banner)
            largest_contour = max(valid_contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)

            # Get bounding box and center
            x, y, w, h = cv2.boundingRect(largest_contour)

            # Calculate center position in original screenshot coordinates
            center_x = region_x + x + (w // 2)
            center_y = region_y + y + (h // 2)

            self.logger.info(f"Red banner detected at ({center_x}, {center_y}), size: {w}x{h}, area: {area}")

            if self.debug_mode:
                debug_img = screenshot.copy()
                # Draw the detected region
                cv2.rectangle(debug_img,
                              (region_x + x, region_y + y),
                              (region_x + x + w, region_y + y + h),
                              (0, 255, 0), 2)
                cv2.circle(debug_img, (center_x, center_y), 5, (0, 0, 255), -1)
                cv2.imwrite("red_banner_detected.png", debug_img)

            return {'x': center_x, 'y': center_y, 'width': w, 'height': h}

        except Exception as e:
            self.logger.error(f"Error detecting red banner: {e}")
            self.logger.exception("Stack trace:")
            return None

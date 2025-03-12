#!/usr/bin/env python3
import sys
import time
import logging
import cv2
import numpy as np
import pytesseract
import subprocess
from config_manager import ConfigManager
from bluestacks_controller import BlueStacksController


class RoKCharacterSwitcher:
    """Controller for switching between characters in Rise of Kingdoms"""

    def __init__(self, config_manager, bluestacks_controller):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.bluestacks = bluestacks_controller

        # Navigation coordinates
        self.avatar_icon = {'x': 50, 'y': 50}
        self.settings_icon = {'x': 1109, 'y': 581}
        self.characters_icon = {'x': 350, 'y': 370}
        self.close_button = {'x': 1212, 'y': 126}  # X button in top right of dialogs

        # Character detection regions
        self.star_detection_region = {
            'x': 1170,
            'y': 300,
            'width': 70,
            'height': 400
        }

        self.normal_characters_text_region = {
            'x': 200,
            'y': 500,
            'width': 800,
            'height': 100
        }

        self.character_click_positions = [
            # Left column characters
            {'x': 450, 'y': 330},  # First row
            {'x': 450, 'y': 480},  # Second row
            {'x': 450, 'y': 630},  # Third row
            {'x': 450, 'y': 780},  # Fourth row (if visible)

            # Right column characters
            {'x': 970, 'y': 330},  # First row
            {'x': 970, 'y': 480},  # Second row
            {'x': 970, 'y': 630},  # Third row
            {'x': 970, 'y': 780},  # Fourth row (if visible)
        ]

        # Green check mark detection for selected character
        self.check_mark_region = {
            'x': 720,
            'y': 250,
            'width': 100,
            'height': 400
        }

        # Delay between actions
        self.click_delay = 1000  # ms

    def open_character_selection(self):
        """Open the character selection screen"""
        self.logger.info("Opening character selection screen")

        # Click avatar icon in top left
        self.logger.info("Clicking avatar icon")
        if not self.bluestacks.click(self.avatar_icon['x'], self.avatar_icon['y'], self.click_delay):
            self.logger.error("Failed to click avatar icon")
            return False

        # Wait for profile screen to appear
        time.sleep(2)

        # Click settings icon
        self.logger.info("Clicking settings icon")
        if not self.bluestacks.click(self.settings_icon['x'], self.settings_icon['y'], self.click_delay):
            self.logger.error("Failed to click settings icon")
            return False

        # Wait for settings screen to appear
        time.sleep(2)

        # Click characters icon
        self.logger.info("Clicking characters icon")
        if not self.bluestacks.click(self.characters_icon['x'], self.characters_icon['y'], self.click_delay):
            self.logger.error("Failed to click characters icon")
            return False

        # Wait for character selection screen to appear
        time.sleep(2)

        self.logger.info("Character selection screen opened")
        return True

    def detect_star_characters(self):
        """Detect which character slots have a star next to them"""
        self.logger.info("Looking for star characters")

        # Take a screenshot
        screenshot = self.bluestacks.take_screenshot()
        if screenshot is None:
            self.logger.error("Failed to take screenshot")
            return []

        # Convert screenshot to HSV
        hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)

        # Define yellow star color range in HSV
        lower_yellow = np.array([20, 100, 100])
        upper_yellow = np.array([40, 255, 255])

        # Create a mask for yellow stars
        mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

        # Save the mask for debugging
        cv2.imwrite("star_mask.png", mask)

        # Detect stars in each character position
        stars_found = []

        for idx, pos in enumerate(self.character_click_positions):
            # Define region around the character position where a star would be
            star_x_offset = 100  # Approximate x-offset from character position to star
            region_x = pos['x'] + star_x_offset
            region_y = pos['y'] - 20  # Slightly above character center
            region_width = 50
            region_height = 50

            # Ensure region is within screenshot bounds
            if (region_x + region_width <= screenshot.shape[1] and
                    region_y + region_height <= screenshot.shape[0]):

                # Extract region and check for yellow pixels
                region = mask[region_y:region_y + region_height, region_x:region_x + region_width]

                # If the region contains white pixels in the mask (yellow in original), it's a star
                if np.sum(region) > 1000:  # Threshold for detection
                    stars_found.append(idx)
                    self.logger.info(f"Star detected at character position {idx}")

        self.logger.info(f"Found {len(stars_found)} star characters")
        return stars_found

    def detect_normal_characters_divider(self):
        """Detect if 'NORMAL CHARACTERS' text is visible, indicating end of star characters"""
        self.logger.info("Looking for 'NORMAL CHARACTERS' divider")

        # Take a screenshot
        screenshot = self.bluestacks.take_screenshot()
        if screenshot is None:
            self.logger.error("Failed to take screenshot")
            return False

        # Crop the region
        region = screenshot[
                 self.normal_characters_text_region['y']:
                 self.normal_characters_text_region['y'] + self.normal_characters_text_region['height'],
                 self.normal_characters_text_region['x']:
                 self.normal_characters_text_region['x'] + self.normal_characters_text_region['width']
                 ]

        # Save region for debugging
        cv2.imwrite("normal_characters_region.png", region)

        # Preprocess the image
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

        # Perform OCR
        try:
            text = pytesseract.image_to_string(thresh)
            self.logger.info(f"OCR detected text: {text}")

            # Check if "NORMAL CHARACTERS" is in the text
            if "NORMAL CHARACTERS" in text.upper():
                self.logger.info("'NORMAL CHARACTERS' divider detected")
                return True

            return False
        except Exception as e:
            self.logger.error(f"Error performing OCR: {e}")
            return False

    def scroll_down(self):
        """Scroll down in the character list"""
        self.logger.info("Scrolling down character list")

        # Define scroll parameters
        start_x = 700  # Middle of screen horizontally
        start_y = 700  # Lower part of character list
        end_x = 700  # Same x position
        end_y = 300  # Upper part of character list

        # Scroll from bottom to top to move list down
        if not self.bluestacks.swipe(start_x, start_y, end_x, end_y, 800):
            self.logger.error("Failed to scroll down")
            return False

        # Wait for scrolling animation to complete
        time.sleep(1.5)
        return True

    def click_character(self, position_idx):
        """Click on a character at the specified position index"""
        if position_idx < 0 or position_idx >= len(self.character_click_positions):
            self.logger.error(f"Invalid character position index: {position_idx}")
            return False

        pos = self.character_click_positions[position_idx]
        self.logger.info(f"Clicking character at position {position_idx}: ({pos['x']}, {pos['y']})")

        if not self.bluestacks.click(pos['x'], pos['y'], self.click_delay):
            self.logger.error(f"Failed to click character at position {position_idx}")
            return False

        # Wait for character load
        time.sleep(3)
        return True

    def detect_green_check_mark(self, position_idx):
        """Detect if a green check mark is present next to a character (indicating selection)"""
        if position_idx < 0 or position_idx >= len(self.character_click_positions):
            self.logger.error(f"Invalid character position index: {position_idx}")
            return False

        # Take a screenshot
        screenshot = self.bluestacks.take_screenshot()
        if screenshot is None:
            self.logger.error("Failed to take screenshot")
            return False

        # Get character position
        pos = self.character_click_positions[position_idx]

        # Define region to check for green checkmark
        check_x = pos['x'] + 30  # Offset from character position
        check_y = pos['y'] - 10
        check_width = 40
        check_height = 40

        # Ensure region is within screenshot bounds
        if (check_x + check_width > screenshot.shape[1] or
                check_y + check_height > screenshot.shape[0] or
                check_x < 0 or check_y < 0):
            self.logger.error("Check mark region is out of bounds")
            return False

        # Extract region
        region = screenshot[check_y:check_y + check_height, check_x:check_x + check_width]

        # Convert to HSV for better color detection
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        # Define green check mark color range
        lower_green = np.array([40, 100, 100])
        upper_green = np.array([80, 255, 255])

        # Create mask
        mask = cv2.inRange(hsv, lower_green, upper_green)

        # Check if there are enough green pixels
        green_pixels = np.sum(mask) / 255

        # Save for debugging
        cv2.imwrite(f"check_mark_region_{position_idx}.png", region)
        cv2.imwrite(f"check_mark_mask_{position_idx}.png", mask)

        self.logger.info(f"Green pixels in check mark region: {green_pixels}")

        # Return True if enough green pixels are found
        return green_pixels > 100

    def close_dialogs(self):
        """Close any open dialogs by clicking X button"""
        self.logger.info("Closing dialogs")
        if not self.bluestacks.click(self.close_button['x'], self.close_button['y'], self.click_delay):
            self.logger.error("Failed to click close button")
            return False

        time.sleep(1)
        return True

    def switch_characters(self):
        """Main function to switch through all star characters"""
        self.logger.info("Starting character switching process")

        # Open character selection screen
        if not self.open_character_selection():
            self.logger.error("Failed to open character selection screen")
            return False

        # Track visited characters to avoid duplicates
        visited_positions = set()

        # Process until we see the "NORMAL CHARACTERS" divider
        reached_end = False
        scroll_count = 0
        max_scrolls = 10  # Safety limit

        while not reached_end and scroll_count < max_scrolls:
            # Check if we've reached normal characters section
            if self.detect_normal_characters_divider():
                self.logger.info("Reached end of star characters")
                reached_end = True
                break

            # Get star characters on current view
            star_positions = self.detect_star_characters()

            if not star_positions:
                self.logger.info("No star characters visible, scrolling down")
                self.scroll_down()
                scroll_count += 1
                continue

            # Click on star characters that haven't been visited
            for pos_idx in star_positions:
                if pos_idx not in visited_positions:
                    self.logger.info(f"Switching to character at position {pos_idx}")

                    # Click on character
                    if not self.click_character(pos_idx):
                        continue

                    # Verify selection with green check mark
                    if self.detect_green_check_mark(pos_idx):
                        self.logger.info(f"Successfully selected character at position {pos_idx}")
                        visited_positions.add(pos_idx)
                    else:
                        self.logger.warning(f"Could not verify selection of character at position {pos_idx}")

                    # Return to character selection screen
                    if not self.open_character_selection():
                        self.logger.error("Failed to return to character selection")
                        return False

            # If we've processed all visible star characters, scroll down
            self.logger.info("Scrolling down to see more characters")
            self.scroll_down()
            scroll_count += 1

        # Close character selection screen
        self.close_dialogs()

        self.logger.info(f"Character switching complete. Visited {len(visited_positions)} characters.")
        return True


def main():
    """Main entry point for the character switcher"""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("character_switcher.log"),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)

    try:
        # Initialize controllers
        config = ConfigManager("config.ini")
        bluestacks = BlueStacksController(config)
        character_switcher = RoKCharacterSwitcher(config, bluestacks)

        # Connect to ADB
        if not bluestacks.connect_adb():
            logger.error("Failed to connect to ADB. Exiting.")
            return False

        # Run character switcher
        result = character_switcher.switch_characters()

        # Disconnect from ADB
        bluestacks.disconnect_adb()

        return result

    except Exception as e:
        logger.error(f"Error in character switcher: {e}")
        logger.exception("Stack trace:")
        return False


if __name__ == "__main__":
    success = main()
    print(f"Character switching {'succeeded' if success else 'failed'}")
    sys.exit(0 if success else 1)
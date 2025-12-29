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
from coordinate_manager import CoordinateManager


class RoKCharacterSwitcher:
    """Controller for switching between characters in Rise of Kingdoms"""

    def __init__(self, config_manager, bluestacks_controller):
        self.logger = logging.getLogger(__name__)
        self.config = config_manager
        self.bluestacks = bluestacks_controller

        # Load coordinates from centralized JSON config
        self.coords = CoordinateManager()

        # Navigation coordinates
        self.avatar_icon = self.coords.get_nav('avatar_icon')
        self.settings_icon = self.coords.get_nav('settings_icon')
        self.characters_icon = self.coords.get_nav('characters_icon')
        self.close_button = self.coords.get_nav('close_button')

        # Character detection regions
        self.star_detection_region = self.coords.get_region('star_detection')
        self.normal_characters_text_region = self.coords.get_region('normal_characters_text')
        self.check_mark_region = self.coords.get_region('check_mark')

        # Character click positions
        self.character_click_positions = self.coords.get_character_switcher_grid()

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

        screenshot = self.bluestacks.take_screenshot()
        if screenshot is None:
            self.logger.error("Failed to take screenshot")
            return []

        hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)

        # Get color detection config for yellow stars
        star_config = self.coords.get_color_detection('yellow_star')
        lower_yellow = np.array(star_config['hsv_lower'])
        upper_yellow = np.array(star_config['hsv_upper'])
        pixel_threshold = star_config['pixel_threshold']

        mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
        cv2.imwrite("star_mask.png", mask)

        stars_found = []
        star_offset = self.coords.get_offset('star_from_character')

        for idx, pos in enumerate(self.character_click_positions):
            region_x = pos['x'] + star_offset['x']
            region_y = pos['y'] + star_offset['y']
            region_width = 50
            region_height = 50

            if (region_x + region_width <= screenshot.shape[1] and
                    region_y + region_height <= screenshot.shape[0] and
                    region_x >= 0 and region_y >= 0):

                region = mask[region_y:region_y + region_height, region_x:region_x + region_width]

                if np.sum(region) > pixel_threshold:
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

        scroll = self.coords.get_scroll('character_switcher')
        start = scroll['start']
        end = scroll['end']
        duration = scroll['duration_ms']

        if not self.bluestacks.swipe(start['x'], start['y'], end['x'], end['y'], duration):
            self.logger.error("Failed to scroll down")
            return False

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

        screenshot = self.bluestacks.take_screenshot()
        if screenshot is None:
            self.logger.error("Failed to take screenshot")
            return False

        pos = self.character_click_positions[position_idx]
        check_offset = self.coords.get_offset('check_mark_from_character')

        check_x = pos['x'] + check_offset['x']
        check_y = pos['y'] + check_offset['y']
        check_width = 40
        check_height = 40

        if (check_x + check_width > screenshot.shape[1] or
                check_y + check_height > screenshot.shape[0] or
                check_x < 0 or check_y < 0):
            self.logger.error("Check mark region is out of bounds")
            return False

        region = screenshot[check_y:check_y + check_height, check_x:check_x + check_width]
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

        # Get color detection config for green checkmark
        check_config = self.coords.get_color_detection('green_checkmark')
        lower_green = np.array(check_config['hsv_lower'])
        upper_green = np.array(check_config['hsv_upper'])
        pixel_threshold = check_config['pixel_threshold']

        mask = cv2.inRange(hsv, lower_green, upper_green)
        green_pixels = np.sum(mask) / 255

        cv2.imwrite(f"check_mark_region_{position_idx}.png", region)
        cv2.imwrite(f"check_mark_mask_{position_idx}.png", mask)

        self.logger.info(f"Green pixels in check mark region: {green_pixels}")

        return green_pixels > pixel_threshold

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
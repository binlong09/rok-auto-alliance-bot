#!/usr/bin/env python3
"""
OCR Debug Tool - Visualize what OCR detects on the current screen.

This tool helps you:
1. See all text detected by OCR
2. View bounding boxes and coordinates for each word
3. Test different preprocessing methods
4. Define and test custom regions

Usage:
    python ocr_debug_tool.py                    # Full screen OCR
    python ocr_debug_tool.py --region 100,200,500,300   # Custom region (x,y,width,height)
    python ocr_debug_tool.py --interactive      # Interactive mode with GUI
"""

import os
import sys
import cv2
import pytesseract
from pytesseract import Output
import argparse
import logging
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bluestacks_controller import BlueStacksController
from config_manager import ConfigManager
from coordinate_manager import CoordinateManager


class OCRDebugTool:
    """Debug tool for visualizing OCR results."""

    def __init__(self, config_path="config.ini"):
        """Initialize the debug tool."""
        self.logger = logging.getLogger(__name__)

        # Load config
        if os.path.exists(config_path):
            self.config = ConfigManager(config_path)
        else:
            # Try to find config in common locations
            for path in ["src/config.ini", "../config.ini", "config.ini"]:
                if os.path.exists(path):
                    self.config = ConfigManager(path)
                    break
            else:
                print("Warning: config.ini not found, using defaults")
                self.config = None

        # Configure tesseract
        if self.config:
            ocr_config = self.config.get_ocr_config()
            pytesseract.pytesseract.tesseract_cmd = ocr_config.get('tesseract_path')

        # Initialize BlueStacks controller
        self.bluestacks = BlueStacksController(self.config)
        self.coords = CoordinateManager()

        # Colors for visualization (BGR format)
        self.colors = {
            'box': (0, 255, 0),      # Green for bounding boxes
            'text': (255, 0, 0),      # Blue for text labels
            'region': (0, 0, 255),    # Red for region outline
            'center': (255, 255, 0),  # Cyan for center points
        }

    def preprocess_image(self, image):
        """Apply different preprocessing methods."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        results = {'original': gray}

        # Adaptive thresholding
        results['adaptive'] = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Otsu's thresholding
        _, results['otsu'] = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Inverted Otsu's
        inverted = cv2.bitwise_not(gray)
        _, results['inverted'] = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # CLAHE contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast_enhanced = clahe.apply(gray)
        _, results['contrast'] = cv2.threshold(contrast_enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return results

    def run_ocr(self, image, method_name="original"):
        """Run OCR on an image and return detailed results."""
        custom_config = '--oem 3 --psm 6'
        data = pytesseract.image_to_data(image, config=custom_config, output_type=Output.DICT)

        results = []
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            if text:  # Only include non-empty text
                results.append({
                    'text': text,
                    'x': data['left'][i],
                    'y': data['top'][i],
                    'width': data['width'][i],
                    'height': data['height'][i],
                    'confidence': data['conf'][i],
                    'method': method_name
                })

        return results

    def annotate_image(self, image, ocr_results, region_offset=(0, 0)):
        """Draw bounding boxes and labels on the image."""
        annotated = image.copy()
        offset_x, offset_y = region_offset

        for result in ocr_results:
            x = result['x']
            y = result['y']
            w = result['width']
            h = result['height']
            text = result['text']
            conf = result['confidence']

            # Draw bounding box
            cv2.rectangle(annotated, (x, y), (x + w, y + h), self.colors['box'], 2)

            # Draw center point
            center_x = x + w // 2
            center_y = y + h // 2
            cv2.circle(annotated, (center_x, center_y), 4, self.colors['center'], -1)

            # Draw label with absolute coordinates
            abs_x = offset_x + center_x
            abs_y = offset_y + center_y
            label = f"{text} ({abs_x},{abs_y})"

            # Background for text
            (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated, (x, y - label_h - 5), (x + label_w, y), (0, 0, 0), -1)
            cv2.putText(annotated, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['text'], 1)

        return annotated

    def analyze_screen(self, region=None, save_output=True):
        """
        Analyze the current screen and return OCR results.

        Args:
            region: Optional dict with {x, y, width, height} or tuple (x, y, width, height)
            save_output: Whether to save annotated images

        Returns:
            dict: Results from all preprocessing methods
        """
        print("\n" + "=" * 60)
        print("  OCR Debug Tool - Screen Analysis")
        print("=" * 60)

        # Take screenshot
        print("\n[1/4] Taking screenshot...")
        screenshot = self.bluestacks.take_screenshot()
        if screenshot is None:
            print("ERROR: Failed to take screenshot. Is BlueStacks running?")
            return None

        print(f"      Screenshot size: {screenshot.shape[1]}x{screenshot.shape[0]}")

        # Handle region
        offset_x, offset_y = 0, 0
        if region:
            if isinstance(region, dict):
                x, y, w, h = region['x'], region['y'], region['width'], region['height']
            else:
                x, y, w, h = region

            print(f"\n[2/4] Cropping to region: x={x}, y={y}, w={w}, h={h}")
            image = screenshot[y:y+h, x:x+w]
            offset_x, offset_y = x, y
        else:
            print("\n[2/4] Using full screen")
            image = screenshot

        # Preprocess
        print("\n[3/4] Running OCR with different preprocessing methods...")
        processed_images = self.preprocess_image(image)

        all_results = {}
        best_method = None
        best_count = 0

        for method_name, processed_image in processed_images.items():
            results = self.run_ocr(processed_image, method_name)
            all_results[method_name] = results

            if len(results) > best_count:
                best_count = len(results)
                best_method = method_name

            print(f"      {method_name}: {len(results)} words detected")

        # Print detailed results
        print("\n[4/4] Detailed Results")
        print("-" * 60)

        if best_method and all_results[best_method]:
            print(f"\nBest method: {best_method} ({best_count} words)")
            print("\nDetected text with coordinates:")
            print(f"{'Text':<20} {'X':>6} {'Y':>6} {'Width':>6} {'Height':>6} {'Conf':>5}")
            print("-" * 60)

            for result in all_results[best_method]:
                abs_x = offset_x + result['x'] + result['width'] // 2
                abs_y = offset_y + result['y'] + result['height'] // 2
                print(f"{result['text']:<20} {abs_x:>6} {abs_y:>6} {result['width']:>6} {result['height']:>6} {result['confidence']:>5}")
        else:
            print("\nNo text detected!")

        # Save output images
        if save_output:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = "ocr_debug_output"
            os.makedirs(output_dir, exist_ok=True)

            # Save original screenshot
            cv2.imwrite(f"{output_dir}/screenshot_{timestamp}.png", screenshot)

            # Save cropped region if applicable
            if region:
                cv2.imwrite(f"{output_dir}/region_{timestamp}.png", image)

            # Save annotated image for best method
            if best_method:
                annotated = self.annotate_image(image, all_results[best_method], (offset_x, offset_y))
                cv2.imwrite(f"{output_dir}/annotated_{timestamp}.png", annotated)

                # Save annotated on full screenshot
                if region:
                    full_annotated = screenshot.copy()
                    # Draw region rectangle
                    cv2.rectangle(full_annotated, (offset_x, offset_y),
                                (offset_x + image.shape[1], offset_y + image.shape[0]),
                                self.colors['region'], 2)
                    # Draw detected text boxes
                    for result in all_results[best_method]:
                        x = offset_x + result['x']
                        y = offset_y + result['y']
                        w = result['width']
                        h = result['height']
                        cv2.rectangle(full_annotated, (x, y), (x + w, y + h), self.colors['box'], 2)
                        center_x = x + w // 2
                        center_y = y + h // 2
                        cv2.circle(full_annotated, (center_x, center_y), 4, self.colors['center'], -1)
                    cv2.imwrite(f"{output_dir}/full_annotated_{timestamp}.png", full_annotated)

            # Save all preprocessing results
            for method_name, processed_image in processed_images.items():
                cv2.imwrite(f"{output_dir}/preprocess_{method_name}_{timestamp}.png", processed_image)

            print(f"\nOutput saved to: {output_dir}/")
            print(f"  - screenshot_{timestamp}.png (original)")
            print(f"  - annotated_{timestamp}.png (with bounding boxes)")
            print(f"  - preprocess_*_{timestamp}.png (preprocessing methods)")

        return all_results

    def interactive_mode(self):
        """Run in interactive mode with live region selection."""
        print("\n" + "=" * 60)
        print("  OCR Debug Tool - Interactive Mode")
        print("=" * 60)
        print("\nCommands:")
        print("  full          - Analyze full screen")
        print("  region X,Y,W,H - Analyze specific region")
        print("  predefined NAME - Use predefined region from coordinates.json")
        print("  list          - List predefined regions")
        print("  quit          - Exit")
        print("-" * 60)

        while True:
            try:
                cmd = input("\n> ").strip().lower()

                if cmd == 'quit' or cmd == 'exit' or cmd == 'q':
                    break
                elif cmd == 'full':
                    self.analyze_screen()
                elif cmd.startswith('region '):
                    try:
                        parts = cmd[7:].split(',')
                        region = tuple(int(p.strip()) for p in parts)
                        if len(region) == 4:
                            self.analyze_screen(region=region)
                        else:
                            print("Error: Region must be X,Y,WIDTH,HEIGHT")
                    except ValueError:
                        print("Error: Invalid region format. Use: region X,Y,WIDTH,HEIGHT")
                elif cmd.startswith('predefined ') or cmd.startswith('p '):
                    name = cmd.split(' ', 1)[1].strip()
                    try:
                        region = self.coords.get_region(name)
                        print(f"Using region '{name}': {region}")
                        self.analyze_screen(region=region)
                    except Exception as e:
                        print(f"Error: Region '{name}' not found. Use 'list' to see available regions.")
                elif cmd == 'list':
                    print("\nPredefined regions from coordinates.json:")
                    # Load and display regions
                    try:
                        import json
                        coords_path = os.path.join(os.path.dirname(__file__), 'coordinates.json')
                        with open(coords_path, 'r') as f:
                            coords = json.load(f)
                        if 'regions' in coords:
                            for name, region in coords['regions'].items():
                                print(f"  {name}: {region}")
                    except Exception as e:
                        print(f"Error loading regions: {e}")
                else:
                    print("Unknown command. Type 'quit' to exit.")

            except KeyboardInterrupt:
                print("\nExiting...")
                break


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="OCR Debug Tool for RoK Automation")
    parser.add_argument('--region', '-r', type=str, help='Region to analyze: X,Y,WIDTH,HEIGHT')
    parser.add_argument('--interactive', '-i', action='store_true', help='Run in interactive mode')
    parser.add_argument('--config', '-c', type=str, default='config.ini', help='Path to config.ini')
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.WARNING)  # Suppress debug logs

    # Initialize tool
    tool = OCRDebugTool(args.config)

    if args.interactive:
        tool.interactive_mode()
    elif args.region:
        try:
            parts = args.region.split(',')
            region = tuple(int(p.strip()) for p in parts)
            if len(region) == 4:
                tool.analyze_screen(region=region)
            else:
                print("Error: Region must be X,Y,WIDTH,HEIGHT")
        except ValueError:
            print("Error: Invalid region format")
    else:
        tool.analyze_screen()


if __name__ == "__main__":
    main()

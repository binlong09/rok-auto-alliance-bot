#!/usr/bin/env python3
"""
Template Matcher - Image-based UI element detection.

Finds UI elements (icons, buttons) on screen by matching small template
images against a screenshot with OpenCV's matchTemplate. This is far more
reliable than fixed coordinates for icon-only buttons (avatar, settings,
bookmark, chests...) that OCR cannot read.

Templates are plain PNG crops stored in src/templates/. A missing template
is never an error: find() simply returns None so callers can fall back to
OCR or fixed coordinates. This keeps the bot working out of the box while
letting each install add templates to become more accurate.

Creating templates
------------------
Run this module as a script while the game is on the target screen:

    python template_matcher.py capture <name> <x> <y> <width> <height>

e.g. capture the bookmark icon shown around (477, 20):

    python template_matcher.py capture bookmark_icon 455 5 45 35

It takes a screenshot through the configured BlueStacks/ADB connection and
saves the crop to src/templates/<name>.png. You can also crop any full
screenshot manually in an image editor - anything that produces a small,
tight PNG of the element works.

Well-known template names used by the automation modules (all optional):
    avatar_icon, settings_icon, characters_icon, bookmark_icon,
    map_button, alliance_icon, technology_icon, donate_button,
    campaign_icon, expedition_banner, expedition_chest,
    march_button, account_button, switch_account_button
"""
import glob
import logging
import os

import cv2

_DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_output")


class TemplateMatcher:
    """Finds template images inside screenshots using cv2.matchTemplate."""

    #: Scales tried when matching. The game renders at a fixed 1280x720 so
    #: 1.0 should normally hit, but small UI scale differences between
    #: BlueStacks versions are covered by the neighbors.
    SCALES = (1.0, 0.95, 1.05, 0.9, 1.1)

    def __init__(self, templates_dir=None, default_threshold=0.85, debug_mode=False):
        """
        Args:
            templates_dir: Directory containing <name>.png templates.
                Defaults to src/templates/ next to this file.
            default_threshold: Minimum normalized correlation (0-1) for a match.
            debug_mode: Save annotated debug images on successful matches.
        """
        self.logger = logging.getLogger(__name__)
        if templates_dir is None:
            templates_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "templates"
            )
        self.templates_dir = templates_dir
        self.default_threshold = default_threshold
        self.debug_mode = debug_mode
        self._cache = {}

        if os.path.isdir(self.templates_dir):
            available = [os.path.splitext(os.path.basename(p))[0]
                         for p in glob.glob(os.path.join(self.templates_dir, "*.png"))]
            if available:
                self.logger.info(f"Template matcher loaded, available templates: {sorted(available)}")
        else:
            self.logger.info(
                f"No templates directory at {self.templates_dir} - "
                "template matching disabled until templates are added"
            )

    def has_template(self, name):
        """Return True if a template image exists for the given name."""
        return self._load(name) is not None

    def _load(self, name):
        """Load (and cache) a template image by name. Returns None if missing."""
        if name in self._cache:
            return self._cache[name]

        path = os.path.join(self.templates_dir, f"{name}.png")
        template = cv2.imread(path) if os.path.exists(path) else None
        if template is not None and (template.shape[0] == 0 or template.shape[1] == 0):
            template = None

        self._cache[name] = template
        return template

    def find(self, screenshot, name, region=None, threshold=None):
        """
        Find a template in a screenshot.

        Args:
            screenshot: Full screenshot (BGR numpy array).
            name: Template name (file src/templates/<name>.png).
            region: Optional {x, y, width, height} dict restricting the search.
            threshold: Minimum match confidence; default_threshold if None.

        Returns:
            dict {x, y, confidence, width, height} with x/y at the CENTER of
            the match in full-screenshot coordinates, or None if not found
            (including when the template file does not exist).
        """
        if screenshot is None:
            return None

        template = self._load(name)
        if template is None:
            self.logger.debug(f"Template '{name}' not available")
            return None

        if threshold is None:
            threshold = self.default_threshold

        # Crop to search region (clamped to screenshot bounds)
        img_h, img_w = screenshot.shape[:2]
        off_x, off_y = 0, 0
        search = screenshot
        if region:
            off_x = max(0, min(int(region['x']), img_w - 1))
            off_y = max(0, min(int(region['y']), img_h - 1))
            r_w = min(int(region['width']), img_w - off_x)
            r_h = min(int(region['height']), img_h - off_y)
            search = screenshot[off_y:off_y + r_h, off_x:off_x + r_w]

        best = None
        for scale in self.SCALES:
            t = template
            if scale != 1.0:
                t = cv2.resize(template, None, fx=scale, fy=scale,
                               interpolation=cv2.INTER_AREA)

            t_h, t_w = t.shape[:2]
            if t_h > search.shape[0] or t_w > search.shape[1]:
                continue

            result = cv2.matchTemplate(search, t, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if best is None or max_val > best['confidence']:
                best = {
                    'confidence': float(max_val),
                    'x': off_x + max_loc[0] + t_w // 2,
                    'y': off_y + max_loc[1] + t_h // 2,
                    'width': t_w,
                    'height': t_h,
                }
            # A very strong hit at native scale doesn't need more scales
            if max_val >= max(threshold, 0.95) and scale == 1.0:
                break

        if best is None or best['confidence'] < threshold:
            found = f"{best['confidence']:.2f}" if best else "n/a"
            self.logger.debug(
                f"Template '{name}' not matched (best confidence {found}, "
                f"threshold {threshold})"
            )
            return None

        self.logger.info(
            f"Template '{name}' matched at ({best['x']}, {best['y']}) "
            f"confidence {best['confidence']:.2f}"
        )

        if self.debug_mode:
            debug_img = screenshot.copy()
            half_w, half_h = best['width'] // 2, best['height'] // 2
            cv2.rectangle(debug_img,
                          (best['x'] - half_w, best['y'] - half_h),
                          (best['x'] + half_w, best['y'] + half_h),
                          (0, 255, 0), 2)
            os.makedirs(_DEBUG_DIR, exist_ok=True)
            cv2.imwrite(os.path.join(_DEBUG_DIR, f"template_match_{name}.png"), debug_img)

        return best


def _capture_template(name, x, y, width, height):
    """Capture a template from the live BlueStacks screen (CLI helper)."""
    from bluestacks_controller import BlueStacksController
    from config_manager import ConfigManager

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    config = ConfigManager()
    bluestacks = BlueStacksController(config)
    if not bluestacks.connect_adb():
        logger.error("Could not connect to BlueStacks over ADB. Is the instance running?")
        return 1

    screenshot = bluestacks.take_screenshot()
    if screenshot is None:
        logger.error("Failed to take screenshot")
        return 1

    img_h, img_w = screenshot.shape[:2]
    x = max(0, min(x, img_w - 1))
    y = max(0, min(y, img_h - 1))
    width = min(width, img_w - x)
    height = min(height, img_h - y)

    crop = screenshot[y:y + height, x:x + width]

    templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    os.makedirs(templates_dir, exist_ok=True)
    out_path = os.path.join(templates_dir, f"{name}.png")
    cv2.imwrite(out_path, crop)
    logger.info(f"Saved template '{name}' ({width}x{height}) to {out_path}")
    return 0


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 7 and sys.argv[1] == "capture":
        sys.exit(_capture_template(
            sys.argv[2], int(sys.argv[3]), int(sys.argv[4]),
            int(sys.argv[5]), int(sys.argv[6])
        ))

    print(__doc__)
    sys.exit(1)

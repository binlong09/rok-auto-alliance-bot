import os
import sys
import logging
import configparser
import string


def find_bluestacks_path():
    """Auto-detect BlueStacks installation path across different drives."""
    bluestacks_relative = "Program Files\\BlueStacks_nxt\\HD-Player.exe"
    adb_relative = "Program Files\\BlueStacks_nxt\\HD-Adb.exe"

    # Get all available drives on Windows
    if sys.platform == "win32":
        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    else:
        drives = ["/"]

    # Check each drive for BlueStacks
    for drive in drives:
        bs_path = os.path.join(drive, bluestacks_relative)
        adb_path = os.path.join(drive, adb_relative)
        if os.path.exists(bs_path):
            return bs_path, adb_path

    # Default fallback
    return "C:\\Program Files\\BlueStacks_nxt\\HD-Player.exe", "C:\\Program Files\\BlueStacks_nxt\\HD-Adb.exe"


def find_tesseract_path():
    """Auto-detect Tesseract installation path across different drives."""
    tesseract_relative = "Program Files\\Tesseract-OCR\\tesseract.exe"

    if sys.platform == "win32":
        drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    else:
        return "/usr/bin/tesseract"

    for drive in drives:
        tess_path = os.path.join(drive, tesseract_relative)
        if os.path.exists(tess_path):
            return tess_path

    return "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"


_SCAN_SKIP_DIRS = {
    "windows", "$recycle.bin", "system volume information",
    "programdata", "recovery", "config.msi", "msocache",
}


def _scan_search_roots():
    """Directories to search, most likely locations first."""
    if sys.platform != "win32":
        return ["/"]

    drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    roots = []

    for drive in drives:
        for sub in ("Program Files", "Program Files (x86)"):
            path = os.path.join(drive, sub)
            if os.path.exists(path):
                roots.append(path)

    roots.extend(drives)
    return roots


def scan_for_files(filenames, max_depth=4, roots=None):
    """Walk the filesystem looking for any of the given filenames (case-insensitive).

    Returns full paths found (no duplicates), searched in order of most-likely-first roots.
    """
    targets = {name.lower() for name in filenames}
    found = []
    seen = set()
    walked = set()

    for root in roots if roots is not None else _scan_search_roots():
        root = os.path.normpath(root)
        base_depth = root.rstrip("\\/").count(os.sep)

        for dirpath, dirnames, files in os.walk(root):
            if dirpath in walked:
                dirnames[:] = []
                continue
            walked.add(dirpath)

            depth = dirpath.rstrip("\\/").count(os.sep) - base_depth
            if depth >= max_depth:
                dirnames[:] = []
                continue

            dirnames[:] = [d for d in dirnames if d.lower() not in _SCAN_SKIP_DIRS]
            if depth == 0:
                dirnames[:] = [d for d in dirnames if d.lower() not in ("program files", "program files (x86)")]

            for f in files:
                if f.lower() in targets:
                    full_path = os.path.join(dirpath, f)
                    if full_path not in seen:
                        seen.add(full_path)
                        found.append(full_path)

    return found


def scan_for_bluestacks_installations():
    """Scan the machine for BlueStacks player executables and their matching adb.

    Returns a list of (player_exe_path, adb_exe_path) tuples. adb_exe_path is
    None if no adb executable was found next to that particular installation.
    """
    player_names = ["HD-Player.exe", "Bluestacks.exe", "BlueStacks.exe"]
    adb_names = ["HD-Adb.exe", "adb.exe"]

    results = []
    for player_path in scan_for_files(player_names):
        install_dir = os.path.dirname(player_path)
        adb_path = None
        for name in adb_names:
            candidate = os.path.join(install_dir, name)
            if os.path.exists(candidate):
                adb_path = candidate
                break
        results.append((player_path, adb_path))

    return results


def scan_for_adb_executables():
    """Scan the machine for adb executables (HD-Adb.exe or plain adb.exe)."""
    return scan_for_files(["HD-Adb.exe", "adb.exe"])


class ConfigManager:
    """Configuration manager for the application"""

    def __init__(self, config_path="config.ini"):
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path
        self.config = self.load_config()

        # Load and validate BlueStacks paths
        self.validate_paths()

    def load_config(self):
        """Load configuration from ini file"""
        config = configparser.ConfigParser()

        # Auto-detect installation paths
        bs_path, adb_path = find_bluestacks_path()
        tess_path = find_tesseract_path()

        # Default config values
        # Note: UI coordinates are now in coordinates.json
        default_config = {
            'BlueStacks': {
                'bluestacks_exe_path': bs_path,
                'bluestacks_instance_name': 'Nougat32',
                'adb_path': adb_path,
                'wait_for_startup_seconds': '30'
            },
            'RiseOfKingdoms': {
                'package_name': 'com.lilithgame.roc.gp',
                'activity_name': 'com.harry.engine.MainActivity',
                'game_load_wait_seconds': '30'
            },
            'OCR': {
                'tesseract_path': tess_path,
                'preprocess_image': 'True'
            },
            'Timing': {
                'click_delay_ms': '1000'
            }
        }

        # Create default config if not exists
        if not os.path.exists(self.config_path):
            self.logger.info(f"Creating default configuration at {self.config_path}")
            config.read_dict(default_config)
            with open(self.config_path, 'w') as configfile:
                config.write(configfile)
        else:
            config.read(self.config_path)

        return config

    def validate_paths(self):
        """Validate that required paths exist, auto-detect if missing"""
        bs_config = self.config['BlueStacks']

        bluestacks_exe_path = bs_config.get('bluestacks_exe_path')
        adb_path = bs_config.get('adb_path')

        # Try to auto-detect if BlueStacks path is invalid
        if not os.path.exists(bluestacks_exe_path):
            self.logger.warning(f"BlueStacks not found at: {bluestacks_exe_path}")
            self.logger.info("Attempting to auto-detect BlueStacks installation...")

            detected_bs, detected_adb = find_bluestacks_path()

            if os.path.exists(detected_bs):
                self.logger.info(f"Found BlueStacks at: {detected_bs}")
                self.config['BlueStacks']['bluestacks_exe_path'] = detected_bs
                self.config['BlueStacks']['adb_path'] = detected_adb
                bluestacks_exe_path = detected_bs
                adb_path = detected_adb

                # Save the corrected config
                with open(self.config_path, 'w') as configfile:
                    self.config.write(configfile)
                self.logger.info("Config updated with detected paths")
            else:
                self.logger.error("Could not auto-detect BlueStacks installation")
                self.logger.info("Please install BlueStacks or update config.ini with correct path")
                # Don't exit - let the UI show so user can fix it

        # Validate ADB path
        if not os.path.exists(adb_path):
            self.logger.warning(f"ADB not found at: {adb_path}")
            # Don't exit - let the UI show so user can fix it

    def get_bluestacks_config(self):
        """Get BlueStacks configuration"""
        return self.config['BlueStacks']

    def get_rok_config(self):
        """Get Rise of Kingdoms configuration"""
        return self.config['RiseOfKingdoms']

    def get_ocr_config(self):
        """Get OCR configuration"""
        return self.config['OCR']

    def get_navigation_config(self):
        """Get timing/navigation configuration (for backwards compatibility)"""
        # Navigation coordinates moved to coordinates.json
        # This now returns Timing section for click_delay_ms
        if 'Timing' in self.config:
            return self.config['Timing']
        elif 'Navigation' in self.config:
            return self.config['Navigation']
        else:
            return {'click_delay_ms': '1000'}

    def get_config(self, section, key, default=None):
        """Get a specific configuration value"""
        try:
            return self.config[section][key]
        except (KeyError, configparser.NoSectionError):
            return default

    def get_int(self, section, key, default=0):
        """Get configuration value as integer"""
        try:
            return int(self.config[section][key])
        except (KeyError, ValueError, configparser.NoSectionError):
            return default

    def get_float(self, section, key, default=0.0):
        """Get configuration value as float"""
        try:
            return float(self.config[section][key])
        except (KeyError, ValueError, configparser.NoSectionError):
            return default

    def get_bool(self, section, key, default=False):
        """Get configuration value as boolean"""
        try:
            return self.config.getboolean(section, key)
        except (KeyError, ValueError, configparser.NoSectionError, configparser.NoOptionError):
            return default
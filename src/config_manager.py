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
        """Validate that required paths exist"""
        bs_config = self.config['BlueStacks']

        bluestacks_exe_path = bs_config.get('bluestacks_exe_path')
        adb_path = bs_config.get('adb_path')

        if not os.path.exists(bluestacks_exe_path):
            self.logger.error(f"BlueStacks executable not found at: {bluestacks_exe_path}")
            self.logger.info("Please update the config.ini file with the correct path")
            sys.exit(1)

        if not os.path.exists(adb_path):
            self.logger.error(f"ADB executable not found at: {adb_path}")
            self.logger.info("Please update the config.ini file with the correct path")
            sys.exit(1)

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
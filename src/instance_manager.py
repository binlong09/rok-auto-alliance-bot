#!/usr/bin/env python3
import os
import sys
import json
import logging
import uuid
import shutil
from config_manager import ConfigManager

# Application name for AppData folder
APP_NAME = "RoK Automation"


def get_appdata_dir():
    """Get the appropriate application data directory for the current OS."""
    if sys.platform == "win32":
        # Windows: Use %APPDATA%/RoK Automation
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        # macOS: Use ~/Library/Application Support/RoK Automation
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        # Linux/other: Use ~/.config/RoK Automation
        base = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))

    return os.path.join(base, APP_NAME)


class InstanceManager:
    """Manager for multiple BlueStacks instances with separate configurations"""

    def __init__(self, instances_dir=None, portable=False):
        """
        Initialize the instance manager.

        Args:
            instances_dir: Custom directory for instances (optional)
            portable: If True, use local 'instances' folder instead of AppData
        """
        self.logger = logging.getLogger(__name__)
        self.instances = {}
        self.current_instance_id = None

        # Determine instances directory
        if instances_dir:
            # Custom directory specified
            self.instances_dir = instances_dir
        elif portable or os.path.exists("portable.txt"):
            # Portable mode: use local instances folder
            self.instances_dir = "instances"
            self.logger.info("Running in portable mode - using local instances folder")
        else:
            # Standard mode: use AppData
            self.instances_dir = os.path.join(get_appdata_dir(), "instances")
            self.logger.info(f"Using AppData for instances: {self.instances_dir}")

        # Check for migration from old local instances folder
        self._migrate_from_local()

        # Create instances directory if it doesn't exist
        if not os.path.exists(self.instances_dir):
            os.makedirs(self.instances_dir)

        # Create index file if it doesn't exist
        self.index_file = os.path.join(self.instances_dir, "index.json")
        if not os.path.exists(self.index_file):
            self._create_default_index()

        # Load instance index
        self._load_instances()

    def _migrate_from_local(self):
        """Migrate instances from old local folder to AppData if needed."""
        local_instances = "instances"
        local_index = os.path.join(local_instances, "index.json")

        # Only migrate if:
        # 1. We're using AppData (not the local folder)
        # 2. Local instances folder exists with data
        # 3. AppData instances folder doesn't exist yet
        if (self.instances_dir != local_instances and
            os.path.exists(local_index) and
            not os.path.exists(self.instances_dir)):

            self.logger.info("Migrating instances from local folder to AppData...")
            try:
                # Create parent directory
                os.makedirs(os.path.dirname(self.instances_dir), exist_ok=True)

                # Copy entire instances folder to AppData
                shutil.copytree(local_instances, self.instances_dir)

                # Rename old folder to indicate migration completed
                backup_name = f"{local_instances}_migrated_backup"
                if os.path.exists(backup_name):
                    shutil.rmtree(backup_name)
                os.rename(local_instances, backup_name)

                self.logger.info(f"Migration complete. Old folder renamed to: {backup_name}")
            except Exception as e:
                self.logger.error(f"Migration failed: {e}. Using local instances folder.")
                self.instances_dir = local_instances

    def _create_default_index(self):
        """Create a default index file with a single instance"""
        default_instance = {
            "id": "default",
            "name": "Default Instance",
            "config_file": "default.ini",
            "description": "Default BlueStacks instance",
            "bluestacks_instance": "Nougat64",
            "adb_port": "5555"
        }

        index_data = {
            "instances": [default_instance],
            "current": "default"
        }

        # Create default config.ini in instances directory
        default_config_path = os.path.join(self.instances_dir, "default.ini")
        if os.path.exists("config.ini"):
            # Copy existing config.ini to instances directory
            shutil.copy("config.ini", default_config_path)
        else:
            # Create a new default config
            config_manager = ConfigManager(default_config_path)
            # The constructor will create a default config file

        # Save index
        with open(self.index_file, 'w') as f:
            json.dump(index_data, f, indent=4)

    def _load_instances(self):
        """Load instance information from index file"""
        try:
            with open(self.index_file, 'r') as f:
                index_data = json.load(f)

            # Convert to dictionary for easier access
            self.instances = {instance["id"]: instance for instance in index_data.get("instances", [])}
            self.current_instance_id = index_data.get("current", None)

            if not self.instances:
                self.logger.warning("No instances found in index file")
                self._create_default_index()
                self._load_instances()  # Reload after creating default

            self.logger.info(f"Loaded {len(self.instances)} instance(s)")

        except Exception as e:
            self.logger.error(f"Error loading instances: {e}")
            self._create_default_index()
            self._load_instances()  # Reload after creating default

    def _save_index(self):
        """Save instance information to index file"""
        try:
            index_data = {
                "instances": list(self.instances.values()),
                "current": self.current_instance_id
            }

            with open(self.index_file, 'w') as f:
                json.dump(index_data, f, indent=4)

            self.logger.info("Instance index saved")

        except Exception as e:
            self.logger.error(f"Error saving instance index: {e}")

    def get_all_instances(self):
        """Get a list of all available instances"""
        return list(self.instances.values())

    def get_instance(self, instance_id):
        """Get instance by ID"""
        return self.instances.get(instance_id)

    def get_current_instance(self):
        """Get the current active instance"""
        if not self.current_instance_id or self.current_instance_id not in self.instances:
            # If current is not set or invalid, use the first instance
            if self.instances:
                self.current_instance_id = next(iter(self.instances))
            else:
                return None

        return self.instances.get(self.current_instance_id)

    def set_current_instance(self, instance_id):
        """Set the current active instance"""
        if instance_id in self.instances:
            self.current_instance_id = instance_id
            self._save_index()
            return True
        return False

    def create_instance(self, name, bluestacks_instance, adb_port, description=""):
        """Create a new instance configuration"""
        # Generate a unique ID
        instance_id = str(uuid.uuid4())[:8]

        # Create config file name
        config_file = f"{instance_id}.ini"
        config_path = os.path.join(self.instances_dir, config_file)

        # Create a new instance entry
        instance = {
            "id": instance_id,
            "name": name,
            "config_file": config_file,
            "description": description,
            "bluestacks_instance": bluestacks_instance,
            "adb_port": adb_port
        }

        # Create config file by copying from template or default
        template_path = os.path.join(self.instances_dir, "default.ini")
        if not os.path.exists(template_path):
            # If no template, use the main config.ini if it exists
            template_path = "config.ini"

        if os.path.exists(template_path):
            shutil.copy(template_path, config_path)

        # Update the new config with instance-specific settings
        config_manager = ConfigManager(config_path)
        config = config_manager.config
        config['BlueStacks']['bluestacks_instance_name'] = bluestacks_instance
        config['BlueStacks']['adb_port'] = adb_port

        with open(config_path, 'w') as f:
            config.write(f)

        # Add to instances dictionary
        self.instances[instance_id] = instance

        # Save index
        self._save_index()

        return instance_id

    def update_instance(self, instance_id, name=None, bluestacks_instance=None, adb_port=None, description=None):
        """Update an existing instance configuration"""
        if instance_id not in self.instances:
            return False

        instance = self.instances[instance_id]

        # Update instance properties
        if name is not None:
            instance["name"] = name
        if description is not None:
            instance["description"] = description
        if bluestacks_instance is not None:
            instance["bluestacks_instance"] = bluestacks_instance
        if adb_port is not None:
            instance["adb_port"] = adb_port

        # Update config file if BS instance or port changed
        if bluestacks_instance is not None or adb_port is not None:
            config_path = os.path.join(self.instances_dir, instance["config_file"])
            if os.path.exists(config_path):
                config_manager = ConfigManager(config_path)
                config = config_manager.config

                if bluestacks_instance is not None:
                    config['BlueStacks']['bluestacks_instance_name'] = bluestacks_instance
                if adb_port is not None:
                    config['BlueStacks']['adb_port'] = adb_port

                with open(config_path, 'w') as f:
                    config.write(f)

        # Save index
        self._save_index()

        return True

    def delete_instance(self, instance_id):
        """Delete an instance configuration"""
        if instance_id not in self.instances:
            return False

        instance = self.instances[instance_id]

        # Delete config file
        config_path = os.path.join(self.instances_dir, instance["config_file"])
        if os.path.exists(config_path):
            try:
                os.remove(config_path)
            except Exception as e:
                self.logger.error(f"Error deleting config file: {e}")

        # Remove from instances dictionary
        del self.instances[instance_id]

        # If this was the current instance, reset current
        if self.current_instance_id == instance_id:
            if self.instances:
                self.current_instance_id = next(iter(self.instances))
            else:
                self.current_instance_id = None

        # Save index
        self._save_index()

        return True

    def duplicate_instance(self, instance_id, new_name):
        """Create a duplicate of an existing instance with a new name"""
        if instance_id not in self.instances:
            return False

        source_instance = self.instances[instance_id]

        # Create a new instance with the same settings
        return self.create_instance(
            name=new_name,
            bluestacks_instance=source_instance["bluestacks_instance"],
            adb_port=source_instance["adb_port"],
            description=f"Copy of {source_instance['name']}"
        )

    def get_config_manager(self, instance_id=None):
        """Get a ConfigManager for the specified instance or current instance"""
        if instance_id is None:
            instance = self.get_current_instance()
        else:
            instance = self.get_instance(instance_id)

        if not instance:
            return None

        config_path = os.path.join(self.instances_dir, instance["config_file"])
        return ConfigManager(config_path)
import os
import sys
import subprocess
import time
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from threading import Thread


class StopAutomationException(Exception):
    """Exception raised when automation is stopped by user"""
    pass


# Import our controllers
from config_manager import ConfigManager
from bluestacks_controller import BlueStacksController
from rok_game_controller import RoKGameController


class RiseOfKingdomsManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Rise of Kingdoms Automation")
        self.root.geometry("600x900")
        self.root.resizable(True, True)

        # Set up logging
        self.setup_logging()

        # Initialize configuration manager
        self.config_manager = ConfigManager()

        # Variables
        self.bluestacks_path = tk.StringVar(value=self.config_manager.get_config('BlueStacks', 'bluestacks_exe_path'))
        self.adb_path = tk.StringVar(value=self.config_manager.get_config('BlueStacks', 'adb_path'))
        self.instance_name = tk.StringVar(
            value=self.config_manager.get_config('BlueStacks', 'bluestacks_instance_name'))
        self.adb_port = tk.StringVar(value="5555")
        self.start_delay = tk.IntVar(
            value=int(self.config_manager.get_config('BlueStacks', 'wait_for_startup_seconds')))
        self.character_count = tk.IntVar(
            value=int(self.config_manager.get_config('RiseOfKingdoms', 'num_of_characters', 1)))
        self.march_preset = tk.IntVar(value=int(self.config_manager.get_config('RiseOfKingdoms', 'march_preset', 1)))

        # RoK Version selection
        self.rok_version = tk.StringVar(
            value=self.config_manager.get_config('RiseOfKingdoms', 'rok_version', 'global').capitalize())
        self.rok_packages = {
            "Global": "com.lilithgame.roc.gp",
            "Gamota": "com.rok.gp.vn",
            "KR": "com.lilithgames.rok.gpkr"
        }

        # Feature checkboxes
        self.enable_tech_donation = tk.BooleanVar(
            value=self.config_manager.get_bool('RiseOfKingdoms', 'perform_donation', True))
        self.enable_troop_build = tk.BooleanVar(
            value=self.config_manager.get_bool('RiseOfKingdoms', 'perform_build', True))

        # Status variables
        self.status_text = tk.StringVar(value="Ready")
        self.is_connected = False
        self.is_running = False
        self.stop_requested = False

        # Controllers
        self.bluestacks_controller = None
        self.rok_controller = None

        # Create UI elements
        self.create_widgets()

        # Initialize session
        self.initialize_defaults()

    def setup_logging(self):
        """Set up logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("rok_automation.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def initialize_defaults(self):
        """Load default values and check environment"""
        # Check if paths exist
        bs_path = self.bluestacks_path.get()
        adb_path = self.adb_path.get()

        if not os.path.exists(bs_path):
            self.logger.warning(f"BlueStacks path not found: {bs_path}")
            self.status_text.set("BlueStacks path not found. Please select the correct path.")

        if not os.path.exists(adb_path):
            self.logger.warning(f"ADB path not found: {adb_path}")
            self.status_text.set("ADB path not found. Please select the correct path.")

    def create_widgets(self):
        """Create UI widgets"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Instance settings section
        instance_frame = ttk.LabelFrame(main_frame, text="BlueStacks Settings", padding="10")
        instance_frame.pack(fill=tk.X, padx=5, pady=5)

        # Grid layout for settings
        ttk.Label(instance_frame, text="BlueStacks Path:").grid(column=0, row=0, sticky=tk.W, pady=2)
        ttk.Entry(instance_frame, textvariable=self.bluestacks_path, width=40).grid(column=1, row=0, sticky=tk.W,
                                                                                    pady=2)
        ttk.Button(instance_frame, text="Browse", command=self.browse_bluestacks).grid(column=2, row=0, sticky=tk.W,
                                                                                       pady=2, padx=5)

        ttk.Label(instance_frame, text="ADB Path:").grid(column=0, row=1, sticky=tk.W, pady=2)
        ttk.Entry(instance_frame, textvariable=self.adb_path, width=40).grid(column=1, row=1, sticky=tk.W, pady=2)
        ttk.Button(instance_frame, text="Browse", command=self.browse_adb).grid(column=2, row=1, sticky=tk.W, pady=2,
                                                                                padx=5)

        ttk.Label(instance_frame, text="Instance Name:").grid(column=0, row=2, sticky=tk.W, pady=2)
        ttk.Entry(instance_frame, textvariable=self.instance_name, width=15).grid(column=1, row=2, sticky=tk.W, pady=2)

        ttk.Label(instance_frame, text="ADB Port:").grid(column=0, row=3, sticky=tk.W, pady=2)
        ttk.Entry(instance_frame, textvariable=self.adb_port, width=15).grid(column=1, row=3, sticky=tk.W, pady=2)

        ttk.Label(instance_frame, text="Startup Wait (sec):").grid(column=0, row=4, sticky=tk.W, pady=2)
        ttk.Spinbox(instance_frame, from_=5, to=60, increment=5, textvariable=self.start_delay, width=13).grid(column=1,
                                                                                                               row=4,
                                                                                                               sticky=tk.W,
                                                                                                               pady=2)

        # Game settings section
        game_frame = ttk.LabelFrame(main_frame, text="Rise of Kingdoms Settings", padding="10")
        game_frame.pack(fill=tk.X, padx=5, pady=5)

        # RoK Version dropdown
        ttk.Label(game_frame, text="RoK Version:").grid(column=0, row=0, sticky=tk.W, pady=2)
        rok_dropdown = ttk.Combobox(game_frame, textvariable=self.rok_version, state="readonly", width=15)
        rok_dropdown['values'] = list(self.rok_packages.keys())
        rok_dropdown.grid(column=1, row=0, sticky=tk.W, pady=2)
        rok_dropdown.bind("<<ComboboxSelected>>", self.on_version_change)

        # Character count and march preset settings
        ttk.Label(game_frame, text="Character Count:").grid(column=0, row=1, sticky=tk.W, pady=2)
        ttk.Spinbox(game_frame, from_=1, to=22, textvariable=self.character_count, width=13).grid(column=1, row=1,
                                                                                                  sticky=tk.W, pady=2)

        ttk.Label(game_frame, text="March Preset:").grid(column=0, row=2, sticky=tk.W, pady=2)
        ttk.Spinbox(game_frame, from_=1, to=7, textvariable=self.march_preset, width=13).grid(column=1, row=2,
                                                                                              sticky=tk.W, pady=2)

        # Feature selection frame
        feature_frame = ttk.LabelFrame(main_frame, text="Automation Features", padding="10")
        feature_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Checkbutton(feature_frame, text="Enable Technology Donation", variable=self.enable_tech_donation).pack(
            anchor=tk.W, pady=5)
        ttk.Checkbutton(feature_frame, text="Enable 1 Troop Build", variable=self.enable_troop_build).pack(anchor=tk.W,
                                                                                                           pady=5)

        # Launch button frame
        launch_frame = ttk.Frame(main_frame, padding="10")
        launch_frame.pack(fill=tk.X, padx=5, pady=5)

        # Package name display (read-only)
        package_frame = ttk.Frame(launch_frame)
        package_frame.pack(fill=tk.X, pady=5)
        ttk.Label(package_frame, text="Package Name:").pack(side=tk.LEFT)
        self.package_display = ttk.Label(package_frame, text=self.rok_packages.get(self.rok_version.get(),
                                                                                   self.rok_packages["Global"]))
        self.package_display.pack(side=tk.LEFT, padx=5)

        # Launch buttons
        buttons_frame = ttk.Frame(launch_frame)
        buttons_frame.pack(fill=tk.X, pady=5)

        # Save config button
        save_button = ttk.Button(
            buttons_frame,
            text="Save Configuration",
            command=self.save_configuration
        )
        save_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        # Launch button
        self.launch_button = ttk.Button(
            buttons_frame,
            text="LAUNCH AUTOMATION",
            command=self.launch_everything,
            style="Launch.TButton"
        )
        self.launch_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # Stop button (initially disabled)
        self.stop_button = ttk.Button(
            buttons_frame,
            text="STOP AUTOMATION",
            command=self.stop_automation,
            style="Stop.TButton",
            state="disabled"
        )
        self.stop_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        # Status bar
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=5)

        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT, padx=5)
        ttk.Label(status_frame, textvariable=self.status_text).pack(side=tk.LEFT, padx=5)

        # Log display
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.log_text = tk.Text(log_frame, height=10, width=60, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(fill=tk.Y, side=tk.RIGHT)
        self.log_text.config(yscrollcommand=scrollbar.set)

        # Apply some styling
        style = ttk.Style()
        style.configure('Launch.TButton', font=('Helvetica', 12, 'bold'))
        style.configure('Stop.TButton', font=('Helvetica', 12, 'bold'), foreground='red')

    def save_configuration(self):
        """Save current configuration to config.ini"""
        try:
            config = self.config_manager.config

            # Update BlueStacks settings
            config['BlueStacks']['bluestacks_exe_path'] = self.bluestacks_path.get()
            config['BlueStacks']['bluestacks_instance_name'] = self.instance_name.get()
            config['BlueStacks']['adb_path'] = self.adb_path.get()
            config['BlueStacks']['wait_for_startup_seconds'] = str(self.start_delay.get())
            config['BlueStacks']['adb_port'] = self.adb_port.get()

            # Update RoK settings
            version = self.rok_version.get()
            config['RiseOfKingdoms']['rok_version'] = version.lower()
            config['RiseOfKingdoms']['package_name'] = self.rok_packages.get(version, self.rok_packages["Global"])
            config['RiseOfKingdoms']['num_of_characters'] = str(self.character_count.get())
            config['RiseOfKingdoms']['march_preset'] = str(self.march_preset.get())
            config['RiseOfKingdoms']['perform_build'] = str(self.enable_troop_build.get())
            config['RiseOfKingdoms']['perform_donation'] = str(self.enable_tech_donation.get())

            # Save to file
            with open(self.config_manager.config_path, 'w') as configfile:
                config.write(configfile)

            self.log("Configuration saved successfully")
            # messagebox.showinfo("Configuration Saved", "Settings have been saved to config.ini")

        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            messagebox.showerror("Error", f"Failed to save configuration: {e}")

    def on_version_change(self, event):
        """Update package name display when version changes"""
        version = self.rok_version.get()
        package_name = self.rok_packages.get(version, self.rok_packages["Global"])
        self.package_display.config(text=package_name)
        self.log(f"Selected RoK version: {version} (Package: {package_name})")

    def browse_bluestacks(self):
        """Browse for BlueStacks executable"""
        path = filedialog.askopenfilename(
            title="Select BlueStacks Executable",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if path:
            self.bluestacks_path.set(path)
            self.log(f"BlueStacks path set to: {path}")

    def browse_adb(self):
        """Browse for ADB executable"""
        path = filedialog.askopenfilename(
            title="Select ADB Executable",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if path:
            self.adb_path.set(path)
            self.log(f"ADB path set to: {path}")

    def launch_everything(self):
        """Launch the complete automation sequence"""
        if self.is_running:
            messagebox.showinfo("Already Running", "Automation is already running.")
            return

        # Save the configuration first
        self.save_configuration()

        self.log("Starting automation sequence...")
        self.status_text.set("Starting automation...")
        self.is_running = True
        self.stop_requested = False

        # Update button states
        self.launch_button.config(state="disabled")
        self.stop_button.config(state="normal")

        # Run in a separate thread to keep UI responsive
        Thread(target=self._run_automation, daemon=True).start()

    def stop_automation(self):
        """Request to stop the running automation"""
        if not self.is_running:
            return

        self.log("Stopping automation... Please wait")
        self.status_text.set("Stopping automation...")
        self.stop_requested = True
        self.stop_button.config(state="disabled")

    def _run_automation(self):
        """Run the complete automation sequence in a separate thread"""
        try:
            # 1. Initialize controllers with current configuration
            self.config_manager = ConfigManager()  # Reload config from file
            self.bluestacks_controller = BlueStacksController(self.config_manager)

            # Update ADB device with current port
            adb_device = f"127.0.0.1:{self.adb_port.get()}"
            self.bluestacks_controller.set_adb_device(adb_device)

            # Initialize RoK controller
            self.rok_controller = RoKGameController(self.config_manager, self.bluestacks_controller)

            # 2. Start BlueStacks
            self.log(f"Starting BlueStacks instance: {self.instance_name.get()}")
            self.status_text.set("Starting BlueStacks...")

            if self.stop_requested:
                raise StopAutomationException("Automation stopped by user")

            # if not self.bluestacks_controller.start_bluestacks():
            #     self.log("Failed to start BlueStacks")
            #     self.status_text.set("Failed to start BlueStacks")
            #     return

            # 3. Connect to ADB
            if self.stop_requested:
                raise StopAutomationException("Automation stopped by user")

            self.log(f"Connecting to ADB on port {self.adb_port.get()}...")
            self.status_text.set("Connecting to ADB...")

            if not self.bluestacks_controller.connect_adb():
                self.log("Failed to connect to ADB")
                self.status_text.set("Failed to connect to ADB")
                return

            self.is_connected = True

            # 4. Start Rise of Kingdoms
            # if self.stop_requested:
            #     raise StopAutomationException("Automation stopped by user")
            #
            # self.log("Starting Rise of Kingdoms...")
            # self.status_text.set("Starting Rise of Kingdoms...")
            #
            # if not self.rok_controller.start_game():
            #     self.log("Failed to start Rise of Kingdoms")
            #     self.status_text.set("Failed to start Rise of Kingdoms")
            #     return
            #
            # # 5. Wait for game to load
            # self.log("Waiting for Rise of Kingdoms to load...")
            # self.status_text.set("Waiting for Rise of Kingdoms...")

            # Wait in smaller intervals to allow for stopping
            total_wait = self.rok_controller.game_load_wait_seconds
            interval = 2  # Check for stop every 2 seconds
            for _ in range(0, total_wait, interval):
                if self.stop_requested:
                    raise StopAutomationException("Automation stopped by user")
                time.sleep(min(interval, total_wait))
                total_wait -= interval

            # 6. Click to dismiss any loading screens
            if self.stop_requested:
                raise StopAutomationException("Automation stopped by user")

            self.rok_controller.click_mid_of_screen()

            # 7. Start character switching automation
            self.log("Starting character switching automation...")
            self.status_text.set("Running character automation...")

            # Pass the stop check function to the controller
            self.rok_controller.stop_check_callback = self.check_if_stop_requested

            # The main automation flow - switch characters and perform actions
            if self.rok_controller.switch_character():
                self.log("Character automation completed successfully")
                self.status_text.set("Automation completed")
            else:
                if self.stop_requested:
                    self.log("Character automation stopped by user")
                    self.status_text.set("Automation stopped")
                else:
                    self.log("Character automation encountered issues")
                    self.status_text.set("Automation partially completed")

        except StopAutomationException as e:
            self.log(f"Automation stopped: {str(e)}")
            self.status_text.set("Automation stopped")
        except Exception as e:
            self.logger.error(f"Error in automation: {e}")
            self.logger.exception("Stack trace:")
            self.status_text.set("Error in automation")
            messagebox.showerror("Automation Error", f"An error occurred during automation: {str(e)}")

        finally:
            self.is_running = False
            # Reset UI
            self.root.after(0, self.reset_ui_after_automation)

    def check_if_stop_requested(self):
        """Callback function to check if stop was requested"""
        if self.stop_requested:
            raise StopAutomationException("Automation stopped by user")
        return self.stop_requested

    def reset_ui_after_automation(self):
        """Reset UI elements after automation completes or stops"""
        self.launch_button.config(state="normal")
        self.stop_button.config(state="disabled")

    def log(self, message):
        """Add message to log display"""
        self.logger.info(message)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)  # Scroll to the end


if __name__ == "__main__":
    root = tk.Tk()
    app = RiseOfKingdomsManagerGUI(root)
    root.mainloop()
#!/usr/bin/env python3
"""
Rise of Kingdoms Automation - Modern Single Instance GUI

A cleaner, more user-friendly interface with:
- Status card with progress indicator
- Collapsible settings sections
- Modern styling
"""
import os
import sys
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
from instance_manager import InstanceManager
from instance_manager_gui import InstanceManagerDialog


class CollapsibleFrame(ttk.Frame):
    """A frame that can be collapsed/expanded"""

    def __init__(self, parent, title="", collapsed=False, **kwargs):
        super().__init__(parent, **kwargs)

        self.is_collapsed = collapsed
        self.title = title

        # Header frame with toggle button
        self.header = ttk.Frame(self)
        self.header.pack(fill=tk.X)

        # Toggle button
        self.toggle_btn = ttk.Label(
            self.header,
            text=f"{'▶' if collapsed else '▼'} {title}",
            cursor="hand2",
            font=("Segoe UI", 10, "bold")
        )
        self.toggle_btn.pack(side=tk.LEFT, padx=5, pady=5)
        self.toggle_btn.bind("<Button-1>", self.toggle)

        # Content frame
        self.content = ttk.Frame(self)
        if not collapsed:
            self.content.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))

    def toggle(self, event=None):
        """Toggle collapsed state"""
        self.is_collapsed = not self.is_collapsed
        self.toggle_btn.config(text=f"{'▶' if self.is_collapsed else '▼'} {self.title}")

        if self.is_collapsed:
            self.content.pack_forget()
        else:
            self.content.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))


class RiseOfKingdomsManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("RoK Auto Bot")
        self.root.geometry("550x750")
        self.root.resizable(True, True)
        self.root.minsize(450, 600)

        # Set up logging
        self.setup_logging()

        # Initialize instance manager
        self.instance_manager = InstanceManager()

        # Get current instance
        self.current_instance = self.instance_manager.get_current_instance()

        # Initialize configuration manager
        if self.current_instance:
            self.config_manager = self.instance_manager.get_config_manager()
        else:
            self.config_manager = ConfigManager()

        # Initialize variables
        self.init_variables()

        # Apply modern styling
        self.setup_styles()

        # Create UI
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

    def init_variables(self):
        """Initialize all tkinter variables"""
        # BlueStacks settings
        self.bluestacks_path = tk.StringVar(value=self.config_manager.get_config('BlueStacks', 'bluestacks_exe_path'))
        self.adb_path = tk.StringVar(value=self.config_manager.get_config('BlueStacks', 'adb_path'))
        self.instance_name = tk.StringVar(value=self.config_manager.get_config('BlueStacks', 'bluestacks_instance_name'))
        self.adb_port = tk.StringVar(value=self.config_manager.get_config('BlueStacks', 'adb_port'))
        self.start_delay = tk.IntVar(value=int(self.config_manager.get_config('BlueStacks', 'wait_for_startup_seconds')))

        # Game settings
        self.character_count = tk.IntVar(value=int(self.config_manager.get_config('RiseOfKingdoms', 'num_of_characters', 1)))
        self.march_preset = tk.IntVar(value=int(self.config_manager.get_config('RiseOfKingdoms', 'march_preset', 1)))

        # Current instance name
        self.selected_instance_name = tk.StringVar(
            value=self.current_instance["name"] if self.current_instance else "Default"
        )

        # RoK Version
        self.rok_version = tk.StringVar(
            value=self.config_manager.get_config('RiseOfKingdoms', 'rok_version', 'global').capitalize()
        )
        self.rok_packages = {
            "Global": "com.lilithgame.roc.gp",
            "Gamota": "com.rok.gp.vn",
            "KR": "com.lilithgames.rok.gpkr"
        }

        # Feature toggles
        self.enable_tech_donation = tk.BooleanVar(
            value=self.config_manager.get_bool('RiseOfKingdoms', 'perform_donation', True)
        )
        self.enable_troop_build = tk.BooleanVar(
            value=self.config_manager.get_bool('RiseOfKingdoms', 'perform_build', True)
        )

        # Status variables
        self.status_text = tk.StringVar(value="Ready to start")
        self.status_color = "ready"  # ready, running, error, success
        self.is_running = False
        self.stop_requested = False

        # Progress tracking
        self.current_character = tk.IntVar(value=0)
        self.total_characters = tk.IntVar(value=self.character_count.get())

        # Controllers
        self.bluestacks_controller = None
        self.rok_controller = None

    def setup_styles(self):
        """Configure ttk styles for modern look"""
        style = ttk.Style()

        # Use clam theme as base (works well on Windows)
        style.theme_use('clam')

        # Colors
        self.colors = {
            'bg': '#f5f5f5',
            'card': '#ffffff',
            'primary': '#2196F3',
            'success': '#4CAF50',
            'error': '#f44336',
            'warning': '#FF9800',
            'text': '#212121',
            'text_secondary': '#757575',
            'border': '#e0e0e0'
        }

        # Configure root background
        self.root.configure(bg=self.colors['bg'])

        # Frame styles
        style.configure('Card.TFrame', background=self.colors['card'])
        style.configure('TFrame', background=self.colors['bg'])

        # Label styles
        style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['text'])
        style.configure('Card.TLabel', background=self.colors['card'], foreground=self.colors['text'])
        style.configure('Title.TLabel', font=('Segoe UI', 16, 'bold'), background=self.colors['bg'])
        style.configure('Subtitle.TLabel', font=('Segoe UI', 10), foreground=self.colors['text_secondary'])
        style.configure('Status.TLabel', font=('Segoe UI', 12, 'bold'), background=self.colors['card'])

        # Button styles
        style.configure('TButton', font=('Segoe UI', 10), padding=10)
        style.configure('Start.TButton', font=('Segoe UI', 12, 'bold'))
        style.configure('Stop.TButton', font=('Segoe UI', 12, 'bold'))

        style.map('Start.TButton',
                  background=[('active', '#1976D2'), ('!disabled', self.colors['primary'])],
                  foreground=[('!disabled', 'white')])

        style.map('Stop.TButton',
                  background=[('active', '#D32F2F'), ('!disabled', self.colors['error'])],
                  foreground=[('!disabled', 'white')])

        # Progress bar
        style.configure('Custom.Horizontal.TProgressbar',
                        troughcolor=self.colors['border'],
                        background=self.colors['primary'])

    def create_widgets(self):
        """Create all UI widgets"""
        # Main container with padding
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # === HEADER ===
        self.create_header(main)

        # === STATUS CARD ===
        self.create_status_card(main)

        # === ACTION BUTTONS ===
        self.create_action_buttons(main)

        # === SETTINGS (Collapsible) ===
        self.create_settings_section(main)

        # === ADVANCED SETTINGS (Collapsible) ===
        self.create_advanced_settings(main)

        # === LOG SECTION ===
        self.create_log_section(main)

    def create_header(self, parent):
        """Create header with title and instance selector"""
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 15))

        # Title
        title_frame = ttk.Frame(header)
        title_frame.pack(side=tk.LEFT)

        ttk.Label(title_frame, text="RoK Auto Bot", style='Title.TLabel').pack(anchor=tk.W)
        ttk.Label(title_frame, text="Automate builds and donations", style='Subtitle.TLabel').pack(anchor=tk.W)

        # Instance selector
        instance_frame = ttk.Frame(header)
        instance_frame.pack(side=tk.RIGHT)

        ttk.Label(instance_frame, text="Instance:", style='Subtitle.TLabel').pack(side=tk.LEFT, padx=(0, 5))

        instance_btn = ttk.Menubutton(instance_frame, textvariable=self.selected_instance_name, width=15)
        instance_btn.pack(side=tk.LEFT)

        # Instance dropdown menu
        self.instance_menu = tk.Menu(instance_btn, tearoff=0)
        instance_btn["menu"] = self.instance_menu
        self.update_instance_menu()

        ttk.Button(instance_frame, text="Manage", command=self.open_instance_manager, width=8).pack(side=tk.LEFT, padx=(5, 0))

    def update_instance_menu(self):
        """Update the instance dropdown menu"""
        self.instance_menu.delete(0, tk.END)
        instances = self.instance_manager.get_all_instances()

        for instance in instances:
            self.instance_menu.add_command(
                label=instance["name"],
                command=lambda i=instance["id"]: self.on_instance_selected(i)
            )

    def create_status_card(self, parent):
        """Create status card with progress indicator"""
        # Card frame with border effect
        card_outer = ttk.Frame(parent, style='TFrame')
        card_outer.pack(fill=tk.X, pady=(0, 15))

        card = tk.Frame(card_outer, bg=self.colors['card'], highlightbackground=self.colors['border'],
                        highlightthickness=1)
        card.pack(fill=tk.X, ipady=15, ipadx=15)

        # Status indicator row
        status_row = tk.Frame(card, bg=self.colors['card'])
        status_row.pack(fill=tk.X, pady=(0, 10))

        # Status dot
        self.status_dot = tk.Label(status_row, text="●", font=('Segoe UI', 16),
                                   fg=self.colors['success'], bg=self.colors['card'])
        self.status_dot.pack(side=tk.LEFT)

        # Status text
        self.status_label = tk.Label(status_row, textvariable=self.status_text,
                                     font=('Segoe UI', 12, 'bold'), bg=self.colors['card'])
        self.status_label.pack(side=tk.LEFT, padx=(5, 0))

        # Progress section
        progress_frame = tk.Frame(card, bg=self.colors['card'])
        progress_frame.pack(fill=tk.X, pady=(5, 0))

        # Progress label
        self.progress_label = tk.Label(progress_frame, text="Character Progress",
                                       font=('Segoe UI', 9), fg=self.colors['text_secondary'],
                                       bg=self.colors['card'])
        self.progress_label.pack(anchor=tk.W)

        # Progress bar
        self.progress_bar = ttk.Progressbar(progress_frame, style='Custom.Horizontal.TProgressbar',
                                            length=300, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(3, 0))
        self.progress_bar['maximum'] = self.character_count.get()
        self.progress_bar['value'] = 0

        # Progress text
        self.progress_text = tk.Label(progress_frame, text="0 / {} characters".format(self.character_count.get()),
                                      font=('Segoe UI', 9), fg=self.colors['text_secondary'],
                                      bg=self.colors['card'])
        self.progress_text.pack(anchor=tk.E, pady=(3, 0))

    def create_action_buttons(self, parent):
        """Create start/stop action buttons"""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(0, 15))

        # Start button
        self.start_btn = tk.Button(
            btn_frame, text="▶  START", font=('Segoe UI', 12, 'bold'),
            bg=self.colors['primary'], fg='white', activebackground='#1976D2',
            activeforeground='white', relief=tk.FLAT, cursor='hand2',
            command=self.launch_everything
        )
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=10, padx=(0, 5))

        # Stop button
        self.stop_btn = tk.Button(
            btn_frame, text="■  STOP", font=('Segoe UI', 12, 'bold'),
            bg=self.colors['error'], fg='white', activebackground='#D32F2F',
            activeforeground='white', relief=tk.FLAT, cursor='hand2',
            state=tk.DISABLED, command=self.stop_automation
        )
        self.stop_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=10, padx=(5, 0))

    def create_settings_section(self, parent):
        """Create main settings section"""
        settings = CollapsibleFrame(parent, title="Settings", collapsed=False)
        settings.pack(fill=tk.X, pady=(0, 10))

        content = settings.content

        # Grid layout for settings
        row = 0

        # Characters
        ttk.Label(content, text="Characters:").grid(row=row, column=0, sticky=tk.W, pady=5)
        char_spin = ttk.Spinbox(content, from_=1, to=22, textvariable=self.character_count, width=8,
                                command=self.on_character_count_change)
        char_spin.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 20))
        char_spin.bind('<FocusOut>', lambda e: self.on_character_count_change())

        # March Preset
        ttk.Label(content, text="March Preset:").grid(row=row, column=2, sticky=tk.W, pady=5)
        ttk.Spinbox(content, from_=1, to=7, textvariable=self.march_preset, width=8).grid(
            row=row, column=3, sticky=tk.W, pady=5, padx=(10, 0))

        row += 1

        # RoK Version
        ttk.Label(content, text="Game Version:").grid(row=row, column=0, sticky=tk.W, pady=5)
        rok_dropdown = ttk.Combobox(content, textvariable=self.rok_version, state="readonly", width=10)
        rok_dropdown['values'] = list(self.rok_packages.keys())
        rok_dropdown.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))

        row += 1

        # Feature toggles
        ttk.Checkbutton(content, text="Enable 1 Troop Build", variable=self.enable_troop_build).grid(
            row=row, column=0, columnspan=2, sticky=tk.W, pady=5)
        ttk.Checkbutton(content, text="Enable Tech Donation", variable=self.enable_tech_donation).grid(
            row=row, column=2, columnspan=2, sticky=tk.W, pady=5)

    def create_advanced_settings(self, parent):
        """Create advanced settings section (collapsed by default)"""
        advanced = CollapsibleFrame(parent, title="Advanced Settings", collapsed=True)
        advanced.pack(fill=tk.X, pady=(0, 10))

        content = advanced.content

        # BlueStacks Path
        row = 0
        ttk.Label(content, text="BlueStacks Path:").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Entry(content, textvariable=self.bluestacks_path, width=35).grid(row=row, column=1, sticky=tk.W, pady=3, padx=5)
        ttk.Button(content, text="Browse", command=self.browse_bluestacks, width=8).grid(row=row, column=2, pady=3)

        row += 1
        ttk.Label(content, text="ADB Path:").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Entry(content, textvariable=self.adb_path, width=35).grid(row=row, column=1, sticky=tk.W, pady=3, padx=5)
        ttk.Button(content, text="Browse", command=self.browse_adb, width=8).grid(row=row, column=2, pady=3)

        row += 1
        ttk.Label(content, text="Instance Name:").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Entry(content, textvariable=self.instance_name, width=20).grid(row=row, column=1, sticky=tk.W, pady=3, padx=5)

        row += 1
        ttk.Label(content, text="ADB Port:").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Entry(content, textvariable=self.adb_port, width=10).grid(row=row, column=1, sticky=tk.W, pady=3, padx=5)

        row += 1
        ttk.Label(content, text="Startup Wait (sec):").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Spinbox(content, from_=5, to=60, increment=5, textvariable=self.start_delay, width=8).grid(
            row=row, column=1, sticky=tk.W, pady=3, padx=5)

        row += 1
        ttk.Button(content, text="Save Configuration", command=self.save_configuration).grid(
            row=row, column=0, columnspan=3, pady=(10, 0))

    def create_log_section(self, parent):
        """Create log output section"""
        log_frame = ttk.LabelFrame(parent, text="Log Output", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)

        # Log text widget with custom styling
        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD,
                                font=('Consolas', 9), bg='#1e1e1e', fg='#d4d4d4',
                                insertbackground='white', selectbackground='#264f78')
        self.log_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # Scrollbar
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(fill=tk.Y, side=tk.RIGHT)
        self.log_text.config(yscrollcommand=scrollbar.set)

        # Configure log colors
        self.log_text.tag_configure('info', foreground='#d4d4d4')
        self.log_text.tag_configure('success', foreground='#4ec9b0')
        self.log_text.tag_configure('warning', foreground='#dcdcaa')
        self.log_text.tag_configure('error', foreground='#f14c4c')

    def on_character_count_change(self):
        """Handle character count change"""
        count = self.character_count.get()
        self.total_characters.set(count)
        self.progress_bar['maximum'] = count
        self.progress_text.config(text=f"0 / {count} characters")

    def update_status(self, status, color="ready"):
        """Update status display"""
        self.status_text.set(status)

        colors_map = {
            "ready": self.colors['success'],
            "running": self.colors['primary'],
            "error": self.colors['error'],
            "warning": self.colors['warning']
        }
        self.status_dot.config(fg=colors_map.get(color, self.colors['success']))

    def update_progress(self, current, total=None):
        """Update progress bar and text"""
        if total:
            self.progress_bar['maximum'] = total
        self.progress_bar['value'] = current
        total_val = total or self.character_count.get()
        self.progress_text.config(text=f"{current} / {total_val} characters")

    def initialize_defaults(self):
        """Load default values and check environment"""
        bs_path = self.bluestacks_path.get()
        adb_path = self.adb_path.get()

        if not os.path.exists(bs_path):
            self.logger.warning(f"BlueStacks path not found: {bs_path}")
            self.update_status("BlueStacks path not found", "warning")

        if not os.path.exists(adb_path):
            self.logger.warning(f"ADB path not found: {adb_path}")
            self.update_status("ADB path not found", "warning")

    # === Instance Management ===

    def open_instance_manager(self):
        """Open the instance manager dialog"""
        dialog = InstanceManagerDialog(self.root, self.instance_manager, self.on_instance_selected)
        self.root.wait_window(dialog.dialog)
        self.update_instance_menu()

    def on_instance_selected(self, instance_id):
        """Handle when a different instance is selected"""
        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            return

        self.selected_instance_name.set(instance["name"])
        self.config_manager = self.instance_manager.get_config_manager(instance_id)
        self.load_config_to_ui()
        self.log(f"Switched to instance: {instance['name']}", "info")

    def load_config_to_ui(self):
        """Load configuration values into UI elements"""
        self.bluestacks_path.set(self.config_manager.get_config('BlueStacks', 'bluestacks_exe_path'))
        self.adb_path.set(self.config_manager.get_config('BlueStacks', 'adb_path'))
        self.instance_name.set(self.config_manager.get_config('BlueStacks', 'bluestacks_instance_name'))
        self.adb_port.set(self.config_manager.get_config('BlueStacks', 'adb_port'))
        self.start_delay.set(int(self.config_manager.get_config('BlueStacks', 'wait_for_startup_seconds')))

        self.rok_version.set(self.config_manager.get_config('RiseOfKingdoms', 'rok_version', 'global').capitalize())
        self.character_count.set(int(self.config_manager.get_config('RiseOfKingdoms', 'num_of_characters', 1)))
        self.march_preset.set(int(self.config_manager.get_config('RiseOfKingdoms', 'march_preset', 1)))

        self.enable_tech_donation.set(self.config_manager.get_bool('RiseOfKingdoms', 'perform_donation', True))
        self.enable_troop_build.set(self.config_manager.get_bool('RiseOfKingdoms', 'perform_build', True))

        self.on_character_count_change()

    def save_configuration(self):
        """Save current configuration to config.ini"""
        try:
            config = self.config_manager.config

            config['BlueStacks']['bluestacks_exe_path'] = self.bluestacks_path.get()
            config['BlueStacks']['bluestacks_instance_name'] = self.instance_name.get()
            config['BlueStacks']['adb_path'] = self.adb_path.get()
            config['BlueStacks']['wait_for_startup_seconds'] = str(self.start_delay.get())
            config['BlueStacks']['adb_port'] = self.adb_port.get()

            version = self.rok_version.get()
            config['RiseOfKingdoms']['rok_version'] = version.lower()
            config['RiseOfKingdoms']['package_name'] = self.rok_packages.get(version, self.rok_packages["Global"])
            config['RiseOfKingdoms']['num_of_characters'] = str(self.character_count.get())
            config['RiseOfKingdoms']['march_preset'] = str(self.march_preset.get())
            config['RiseOfKingdoms']['perform_build'] = str(self.enable_troop_build.get())
            config['RiseOfKingdoms']['perform_donation'] = str(self.enable_tech_donation.get())

            with open(self.config_manager.config_path, 'w') as configfile:
                config.write(configfile)

            self.log("Configuration saved", "success")

        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            messagebox.showerror("Error", f"Failed to save configuration: {e}")

    # === File Browsing ===

    def browse_bluestacks(self):
        """Browse for BlueStacks executable"""
        path = filedialog.askopenfilename(
            title="Select BlueStacks Executable",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if path:
            self.bluestacks_path.set(path)
            self.log(f"BlueStacks path: {path}", "info")

    def browse_adb(self):
        """Browse for ADB executable"""
        path = filedialog.askopenfilename(
            title="Select ADB Executable",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if path:
            self.adb_path.set(path)
            self.log(f"ADB path: {path}", "info")

    # === Automation Control ===

    def launch_everything(self):
        """Launch the complete automation sequence"""
        if self.is_running:
            messagebox.showinfo("Already Running", "Automation is already running.")
            return

        self.save_configuration()

        self.log("Starting automation...", "info")
        self.update_status("Starting...", "running")
        self.update_progress(0)

        self.is_running = True
        self.stop_requested = False

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)

        Thread(target=self._run_automation, daemon=True).start()

    def stop_automation(self):
        """Request to stop the running automation"""
        if not self.is_running:
            return

        self.log("Stopping automation...", "warning")
        self.update_status("Stopping...", "warning")
        self.stop_requested = True
        self.stop_btn.config(state=tk.DISABLED)

    def wait_in_intervals(self):
        """Wait in smaller intervals to allow for stopping"""
        total_wait = self.rok_controller.game_load_wait_seconds
        interval = 2
        for _ in range(0, total_wait, interval):
            if self.stop_requested:
                raise StopAutomationException("Automation stopped by user")
            time.sleep(min(interval, total_wait))
            total_wait -= interval

    def _run_automation(self):
        """Run the complete automation sequence in a separate thread"""
        try:
            current_instance = self.instance_manager.get_current_instance()
            instance_name = current_instance["name"] if current_instance else "Default"

            self.log(f"Instance: {instance_name}", "info")

            self.config_manager = self.instance_manager.get_config_manager()
            self.bluestacks_controller = BlueStacksController(self.config_manager)

            adb_device = f"127.0.0.1:{self.adb_port.get()}"
            self.bluestacks_controller.set_adb_device(adb_device)

            self.rok_controller = RoKGameController(self.config_manager, self.bluestacks_controller)

            # Start BlueStacks
            self.log(f"Starting BlueStacks: {self.instance_name.get()}", "info")
            self.update_status("Starting BlueStacks...", "running")

            if self.stop_requested:
                raise StopAutomationException("Automation stopped by user")

            if not self.bluestacks_controller.start_bluestacks():
                self.log("Failed to start BlueStacks", "error")
                self.update_status("Failed to start BlueStacks", "error")
                return

            # Connect ADB
            if self.stop_requested:
                raise StopAutomationException("Automation stopped by user")

            self.log(f"Connecting ADB on port {self.adb_port.get()}...", "info")
            self.update_status("Connecting ADB...", "running")

            if not self.bluestacks_controller.connect_adb():
                self.log("Failed to connect ADB", "error")
                self.update_status("Failed to connect ADB", "error")
                return

            # Start game
            if self.stop_requested:
                raise StopAutomationException("Automation stopped by user")

            self.log("Starting Rise of Kingdoms...", "info")
            self.update_status("Starting game...", "running")

            if not self.rok_controller.start_game():
                self.log("Failed to start game", "error")
                self.update_status("Failed to start game", "error")
                return

            # Wait for game
            self.log("Waiting for game to load...", "info")
            self.update_status("Loading game...", "running")
            self.wait_in_intervals()

            if self.stop_requested:
                raise StopAutomationException("Automation stopped by user")

            self.rok_controller.wait_for_game_load()

            # Start character automation
            self.log("Starting character automation...", "info")
            self.update_status("Running automation...", "running")

            self.rok_controller.stop_check_callback = self.check_if_stop_requested

            self.wait_in_intervals()

            if self.rok_controller.switch_character():
                self.log("Automation completed successfully!", "success")
                self.update_status("Completed", "ready")
                self.update_progress(self.character_count.get())
            else:
                if self.stop_requested:
                    self.log("Automation stopped by user", "warning")
                    self.update_status("Stopped", "warning")
                else:
                    self.log("Automation completed with some issues", "warning")
                    self.update_status("Partially completed", "warning")

        except StopAutomationException as e:
            self.log(f"Stopped: {str(e)}", "warning")
            self.update_status("Stopped", "warning")
        except Exception as e:
            self.logger.error(f"Error in automation: {e}")
            self.logger.exception("Stack trace:")
            self.log(f"Error: {str(e)}", "error")
            self.update_status("Error occurred", "error")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")

        finally:
            self.is_running = False
            self.root.after(0, self.reset_ui_after_automation)

    def check_if_stop_requested(self):
        """Callback function to check if stop was requested"""
        if self.stop_requested:
            raise StopAutomationException("Automation stopped by user")
        return self.stop_requested

    def reset_ui_after_automation(self):
        """Reset UI elements after automation completes or stops"""
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def log(self, message, level="info"):
        """Add message to log display with color coding"""
        self.logger.info(message)
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", level)
        self.log_text.see(tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    app = RiseOfKingdomsManagerGUI(root)
    root.mainloop()

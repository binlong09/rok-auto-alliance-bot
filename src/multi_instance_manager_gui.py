#!/usr/bin/env python3
"""
Rise of Kingdoms - Multi-Instance Manager GUI

Modern, sleek interface for managing multiple BlueStacks instances.
"""
import os
import sys
import logging
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time

from instance_manager import InstanceManager
from instance_manager_gui import InstanceManagerDialog
from multi_instance_launcher import MultiInstanceLauncher
from daily_task_tracker import DailyTaskTracker, get_tracker_path_for_instance


class ModernButton(tk.Canvas):
    """Custom modern button with hover effects and rounded corners"""

    def __init__(self, parent, text="", command=None, bg="#2196F3", fg="white",
                 hover_bg="#1976D2", width=120, height=36, icon="", **kwargs):
        super().__init__(parent, width=width, height=height, bg=parent.cget('bg'),
                        highlightthickness=0, **kwargs)

        self.command = command
        self.bg_color = bg
        self.fg_color = fg
        self.hover_bg = hover_bg
        self.text = text
        self.icon = icon
        self.width = width
        self.height = height
        self.is_hovered = False
        self.is_disabled = False

        self._draw()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _draw(self):
        self.delete("all")
        color = self.hover_bg if self.is_hovered and not self.is_disabled else self.bg_color
        if self.is_disabled:
            color = "#cccccc"

        # Draw rounded rectangle
        r = 6
        self.create_oval(0, 0, r*2, r*2, fill=color, outline="")
        self.create_oval(self.width-r*2, 0, self.width, r*2, fill=color, outline="")
        self.create_oval(0, self.height-r*2, r*2, self.height, fill=color, outline="")
        self.create_oval(self.width-r*2, self.height-r*2, self.width, self.height, fill=color, outline="")
        self.create_rectangle(r, 0, self.width-r, self.height, fill=color, outline="")
        self.create_rectangle(0, r, self.width, self.height-r, fill=color, outline="")

        # Draw text
        display_text = f"{self.icon}  {self.text}" if self.icon else self.text
        text_color = self.fg_color if not self.is_disabled else "#888888"
        self.create_text(self.width/2, self.height/2, text=display_text,
                        fill=text_color, font=('Segoe UI', 10, 'bold'))

    def _on_enter(self, event):
        if not self.is_disabled:
            self.is_hovered = True
            self._draw()
            self.config(cursor="hand2")

    def _on_leave(self, event):
        self.is_hovered = False
        self._draw()
        self.config(cursor="")

    def _on_click(self, event):
        if self.command and not self.is_disabled:
            self.command()

    def set_disabled(self, disabled):
        self.is_disabled = disabled
        self._draw()


class StatusBadge(tk.Canvas):
    """Modern status badge with colored background"""

    def __init__(self, parent, text="", status="default", **kwargs):
        super().__init__(parent, width=80, height=24, highlightthickness=0, **kwargs)
        self.configure(bg=parent.cget('bg'))

        self.colors = {
            'running': ('#e8f5e9', '#2e7d32'),
            'stopped': ('#fafafa', '#757575'),
            'starting': ('#fff3e0', '#ef6c00'),
            'error': ('#ffebee', '#c62828'),
            'default': ('#f5f5f5', '#424242')
        }

        self.update_status(text, status)

    def update_status(self, text, status):
        self.delete("all")
        bg_color, text_color = self.colors.get(status, self.colors['default'])

        # Draw rounded background
        r = 12
        w, h = 80, 24
        self.create_oval(0, 0, r*2, h, fill=bg_color, outline="")
        self.create_oval(w-r*2, 0, w, h, fill=bg_color, outline="")
        self.create_rectangle(r, 0, w-r, h, fill=bg_color, outline="")

        # Draw text
        self.create_text(w/2, h/2, text=text, fill=text_color, font=('Segoe UI', 9, 'bold'))


class MultiInstanceManagerGUI:
    """Modern GUI for managing and running multiple BlueStacks instances"""

    def __init__(self, root):
        self.root = root
        self.root.title("RoK Multi-Instance Manager")
        self.root.geometry("1150x900")
        self.root.resizable(True, True)
        self.root.minsize(950, 850)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Setup logging
        self.setup_logging()

        # Initialize managers
        self.instance_manager = InstanceManager()
        self.launcher = MultiInstanceLauncher(self.instance_manager)

        # Set callbacks
        self.launcher.set_callbacks(
            log_callback=self.on_instance_log,
            status_callback=self.on_instance_status_update
        )

        # Track state
        self.is_closing = False
        self.auto_exit_var = tk.BooleanVar(value=True)
        self.force_daily_tasks_var = tk.BooleanVar(value=False)

        # Apply styling
        self.setup_styles()

        # Create UI
        self.create_widgets()

        # Load instances
        self.load_instances()

        # Status update thread
        self.status_thread = threading.Thread(target=self.update_status_thread, daemon=True)
        self.status_thread.start()

    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("multi_instance.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def setup_styles(self):
        """Configure modern ttk styles"""
        style = ttk.Style()
        style.theme_use('clam')

        # Modern color palette
        self.colors = {
            'bg': '#f0f2f5',
            'card': '#ffffff',
            'header': '#1a237e',
            'header_light': '#3949ab',
            'primary': '#3f51b5',
            'primary_dark': '#303f9f',
            'success': '#43a047',
            'error': '#e53935',
            'warning': '#fb8c00',
            'text': '#1a1a2e',
            'text_secondary': '#64748b',
            'text_light': '#94a3b8',
            'border': '#e2e8f0',
            'divider': '#f1f5f9',
            'shadow': '#cbd5e1'
        }

        # Configure root
        self.root.configure(bg=self.colors['bg'])

        # Frame styles
        style.configure('TFrame', background=self.colors['bg'])
        style.configure('Card.TFrame', background=self.colors['card'])
        style.configure('Header.TFrame', background=self.colors['header'])

        # Label styles
        style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['text'])
        style.configure('Card.TLabel', background=self.colors['card'], foreground=self.colors['text'])
        style.configure('Header.TLabel', background=self.colors['header'], foreground='white')
        style.configure('HeaderTitle.TLabel', background=self.colors['header'], foreground='white',
                       font=('Segoe UI', 20, 'bold'))
        style.configure('HeaderSub.TLabel', background=self.colors['header'], foreground='#b3e5fc',
                       font=('Segoe UI', 10))
        style.configure('SectionTitle.TLabel', background=self.colors['card'],
                       foreground=self.colors['text'], font=('Segoe UI', 13, 'bold'))
        style.configure('Stat.TLabel', background=self.colors['card'],
                       foreground=self.colors['primary'], font=('Segoe UI', 24, 'bold'))
        style.configure('StatLabel.TLabel', background=self.colors['card'],
                       foreground=self.colors['text_secondary'], font=('Segoe UI', 9))

        # Button styles
        style.configure('TButton', font=('Segoe UI', 10), padding=8)
        style.configure('Secondary.TButton', font=('Segoe UI', 9), padding=6)
        style.map('TButton',
                 background=[('active', self.colors['primary_dark'])],
                 foreground=[('active', 'white')])

        # Treeview styles
        style.configure('Custom.Treeview', font=('Segoe UI', 10), rowheight=45,
                       background=self.colors['card'], fieldbackground=self.colors['card'],
                       borderwidth=0)
        style.configure('Custom.Treeview.Heading', font=('Segoe UI', 10, 'bold'),
                       background=self.colors['divider'], foreground=self.colors['text'],
                       borderwidth=0, relief='flat')
        style.map('Custom.Treeview',
                  background=[('selected', '#e8eaf6')],
                  foreground=[('selected', self.colors['text'])])
        style.map('Custom.Treeview.Heading',
                  background=[('active', self.colors['border'])])

        # Checkbutton styles
        style.configure('Card.TCheckbutton', background=self.colors['card'],
                       foreground=self.colors['text'], font=('Segoe UI', 10))

    def create_widgets(self):
        """Create all UI widgets"""
        # Main container
        main = tk.Frame(self.root, bg=self.colors['bg'])
        main.pack(fill=tk.BOTH, expand=True)

        # === HEADER ===
        self.create_header(main)

        # === STATS BAR ===
        self.create_stats_bar(main)

        # === CONTENT ===
        content = tk.Frame(main, bg=self.colors['bg'])
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        # Left panel - Instance list
        self.create_instance_panel(content)

        # Right panel - Details & Logs
        self.create_detail_panel(content)

    def create_header(self, parent):
        """Create modern header with gradient effect"""
        # Header container
        header = tk.Frame(parent, bg=self.colors['header'], height=90)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        # Add accent bar at bottom
        accent = tk.Frame(header, bg=self.colors['primary'], height=4)
        accent.pack(side=tk.BOTTOM, fill=tk.X)

        # Header content
        content = tk.Frame(header, bg=self.colors['header'])
        content.pack(fill=tk.BOTH, expand=True, padx=25, pady=15)

        # Left side - Title
        title_frame = tk.Frame(content, bg=self.colors['header'])
        title_frame.pack(side=tk.LEFT, fill=tk.Y)

        # App icon (using unicode)
        icon_label = tk.Label(title_frame, text="⚔", font=('Segoe UI', 28),
                             bg=self.colors['header'], fg='white')
        icon_label.pack(side=tk.LEFT, padx=(0, 15))

        # Title text
        text_frame = tk.Frame(title_frame, bg=self.colors['header'])
        text_frame.pack(side=tk.LEFT)

        tk.Label(text_frame, text="RoK Multi-Instance Manager",
                font=('Segoe UI', 18, 'bold'), bg=self.colors['header'],
                fg='white').pack(anchor=tk.W)
        tk.Label(text_frame, text="Automate multiple Rise of Kingdoms accounts",
                font=('Segoe UI', 10), bg=self.colors['header'],
                fg='#90caf9').pack(anchor=tk.W)

        # Right side - Main actions
        actions = tk.Frame(content, bg=self.colors['header'])
        actions.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = tk.Frame(actions, bg=self.colors['header'])
        btn_frame.pack(expand=True)

        self.launch_all_btn = ModernButton(
            btn_frame, text="Launch All", icon="▶",
            bg="#4caf50", hover_bg="#388e3c", width=130, height=40,
            command=self.launch_all_instances
        )
        self.launch_all_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_all_btn = ModernButton(
            btn_frame, text="Stop All", icon="■",
            bg=self.colors['error'], hover_bg="#c62828", width=120, height=40,
            command=self.stop_all_instances
        )
        self.stop_all_btn.pack(side=tk.LEFT)

    def create_stats_bar(self, parent):
        """Create stats bar with key metrics"""
        # Container
        stats_frame = tk.Frame(parent, bg=self.colors['bg'])
        stats_frame.pack(fill=tk.X, padx=20, pady=20)

        # Stats cards
        self.create_stat_card(stats_frame, "running_stat", "0", "Running", self.colors['success'])
        self.create_stat_card(stats_frame, "total_stat", "0", "Total Instances", self.colors['primary'])
        self.create_stat_card(stats_frame, "completed_stat", "0", "Completed Today", self.colors['text_secondary'])

    def create_stat_card(self, parent, attr_name, value, label, color):
        """Create a single stat card"""
        # Card with shadow effect
        shadow = tk.Frame(parent, bg=self.colors['shadow'])
        shadow.pack(side=tk.LEFT, padx=(0, 15))

        card = tk.Frame(shadow, bg=self.colors['card'])
        card.pack(padx=2, pady=2)

        inner = tk.Frame(card, bg=self.colors['card'])
        inner.pack(padx=25, pady=15)

        # Color accent
        accent = tk.Frame(inner, bg=color, width=4, height=40)
        accent.pack(side=tk.LEFT, padx=(0, 15))

        # Text
        text_frame = tk.Frame(inner, bg=self.colors['card'])
        text_frame.pack(side=tk.LEFT)

        value_label = tk.Label(text_frame, text=value, font=('Segoe UI', 22, 'bold'),
                              bg=self.colors['card'], fg=color)
        value_label.pack(anchor=tk.W)

        tk.Label(text_frame, text=label, font=('Segoe UI', 9),
                bg=self.colors['card'], fg=self.colors['text_secondary']).pack(anchor=tk.W)

        setattr(self, attr_name, value_label)

    def create_instance_panel(self, parent):
        """Create left panel with instance list"""
        # Card with shadow
        shadow = tk.Frame(parent, bg=self.colors['shadow'])
        shadow.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 10))

        card = tk.Frame(shadow, bg=self.colors['card'])
        card.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Card content
        inner = tk.Frame(card, bg=self.colors['card'])
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Header row
        header = tk.Frame(inner, bg=self.colors['card'])
        header.pack(fill=tk.X, pady=(0, 10))

        tk.Label(header, text="Instances", font=('Segoe UI', 14, 'bold'),
                bg=self.colors['card'], fg=self.colors['text']).pack(side=tk.LEFT)

        # Management buttons (right side of header)
        mgmt_frame = tk.Frame(header, bg=self.colors['card'])
        mgmt_frame.pack(side=tk.RIGHT)

        manage_btn = ModernButton(mgmt_frame, text="Manage", bg=self.colors['primary'],
                                 hover_bg=self.colors['primary_dark'], width=90, height=32,
                                 command=self.open_instance_manager)
        manage_btn.pack(side=tk.LEFT, padx=(0, 8))

        refresh_btn = ModernButton(mgmt_frame, text="Refresh", bg="#78909c",
                                  hover_bg="#546e7a", width=90, height=32,
                                  command=self.load_instances)
        refresh_btn.pack(side=tk.LEFT)

        # Action buttons row (Launch, Stop, Edit)
        actions = tk.Frame(inner, bg=self.colors['card'])
        actions.pack(fill=tk.X, pady=(0, 10))

        self.launch_selected_btn = ModernButton(
            actions, text="Launch", icon="▶", bg=self.colors['success'],
            hover_bg="#2e7d32", width=100, height=32
        )
        self.launch_selected_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.launch_selected_btn.set_disabled(True)
        self.launch_selected_btn.command = self.launch_selected_instances

        self.stop_btn = ModernButton(
            actions, text="Stop", icon="■", bg=self.colors['error'],
            hover_bg="#c62828", width=85, height=32
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_btn.set_disabled(True)
        self.stop_btn.command = self.stop_selected_instance

        self.edit_btn = ModernButton(
            actions, text="Edit", icon="✎", bg="#78909c",
            hover_bg="#546e7a", width=80, height=32
        )
        self.edit_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.edit_btn.set_disabled(True)
        self.edit_btn.command = self.edit_selected_instance

        # Options frame (right side of actions row)
        options_frame = tk.Frame(actions, bg=self.colors['card'])
        options_frame.pack(side=tk.RIGHT)

        # Reset Daily Tasks button
        self.reset_daily_btn = ModernButton(
            options_frame, text="Reset Daily", bg="#ff9800",
            hover_bg="#f57c00", width=100, height=32,
            command=self.reset_daily_tasks
        )
        self.reset_daily_btn.pack(side=tk.RIGHT, padx=(10, 0))
        self.reset_daily_btn.set_disabled(True)

        # Force daily tasks checkbox
        ttk.Checkbutton(options_frame, text="Force daily tasks",
                       variable=self.force_daily_tasks_var,
                       style='Card.TCheckbutton').pack(side=tk.RIGHT, padx=(10, 0))

        # Auto-exit checkbox
        ttk.Checkbutton(options_frame, text="Auto-exit after done",
                       variable=self.auto_exit_var, command=self.toggle_auto_exit,
                       style='Card.TCheckbutton').pack(side=tk.RIGHT)

        # Divider
        tk.Frame(inner, bg=self.colors['border'], height=1).pack(fill=tk.X, pady=(0, 15))

        # Instance list
        list_frame = tk.Frame(inner, bg=self.colors['card'])
        list_frame.pack(fill=tk.BOTH, expand=True)

        # Treeview with custom styling
        columns = ("name", "instance", "status")
        self.instances_tree = ttk.Treeview(list_frame, columns=columns, show="headings",
                                           selectmode="extended", height=12, style='Custom.Treeview')

        self.instances_tree.heading("name", text="  Name", anchor=tk.W)
        self.instances_tree.heading("instance", text="  BlueStacks Instance", anchor=tk.W)
        self.instances_tree.heading("status", text="  Status", anchor=tk.W)

        self.instances_tree.column("name", width=150, minwidth=120)
        self.instances_tree.column("instance", width=160, minwidth=120)
        self.instances_tree.column("status", width=100, minwidth=80)

        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.instances_tree.yview)
        self.instances_tree.configure(yscrollcommand=scrollbar.set)

        self.instances_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.instances_tree.bind("<<TreeviewSelect>>", self.on_instance_select)

    def create_detail_panel(self, parent):
        """Create right panel with details and logs"""
        # Card with shadow
        shadow = tk.Frame(parent, bg=self.colors['shadow'])
        shadow.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        card = tk.Frame(shadow, bg=self.colors['card'])
        card.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        inner = tk.Frame(card, bg=self.colors['card'])
        inner.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Selected instance info
        info_header = tk.Frame(inner, bg=self.colors['card'])
        info_header.pack(fill=tk.X, pady=(0, 10))

        tk.Label(info_header, text="Instance Details", font=('Segoe UI', 14, 'bold'),
                bg=self.colors['card'], fg=self.colors['text']).pack(side=tk.LEFT)

        # Instance info cards
        info_row = tk.Frame(inner, bg=self.colors['card'])
        info_row.pack(fill=tk.X, pady=(0, 15))

        # Selected instance
        self.selected_frame = tk.Frame(info_row, bg=self.colors['divider'])
        self.selected_frame.pack(side=tk.LEFT, padx=(0, 15))

        sel_inner = tk.Frame(self.selected_frame, bg=self.colors['divider'])
        sel_inner.pack(padx=15, pady=10)

        tk.Label(sel_inner, text="SELECTED", font=('Segoe UI', 8, 'bold'),
                bg=self.colors['divider'], fg=self.colors['text_light']).pack(anchor=tk.W)
        self.selected_label = tk.Label(sel_inner, text="None", font=('Segoe UI', 12, 'bold'),
                                       bg=self.colors['divider'], fg=self.colors['text'])
        self.selected_label.pack(anchor=tk.W)

        # Status
        status_frame = tk.Frame(info_row, bg=self.colors['divider'])
        status_frame.pack(side=tk.LEFT)

        stat_inner = tk.Frame(status_frame, bg=self.colors['divider'])
        stat_inner.pack(padx=15, pady=10)

        tk.Label(stat_inner, text="STATUS", font=('Segoe UI', 8, 'bold'),
                bg=self.colors['divider'], fg=self.colors['text_light']).pack(anchor=tk.W)

        status_row = tk.Frame(stat_inner, bg=self.colors['divider'])
        status_row.pack(anchor=tk.W)

        self.status_dot = tk.Label(status_row, text="●", font=('Segoe UI', 12),
                                   bg=self.colors['divider'], fg=self.colors['text_secondary'])
        self.status_dot.pack(side=tk.LEFT)

        self.status_label = tk.Label(status_row, text="Not Running", font=('Segoe UI', 12, 'bold'),
                                     bg=self.colors['divider'], fg=self.colors['text'])
        self.status_label.pack(side=tk.LEFT, padx=(5, 0))

        # Divider
        tk.Frame(inner, bg=self.colors['border'], height=1).pack(fill=tk.X, pady=(0, 15))

        # Log header
        log_header = tk.Frame(inner, bg=self.colors['card'])
        log_header.pack(fill=tk.X, pady=(0, 10))

        tk.Label(log_header, text="Automation Logs", font=('Segoe UI', 12, 'bold'),
                bg=self.colors['card'], fg=self.colors['text']).pack(side=tk.LEFT)

        # Clear button
        clear_btn = ModernButton(log_header, text="Clear", bg="#78909c",
                                hover_bg="#546e7a", width=70, height=28,
                                command=self.clear_logs)
        clear_btn.pack(side=tk.RIGHT)

        # Log text area with modern styling
        log_container = tk.Frame(inner, bg='#0d1117', bd=0)
        log_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_container, wrap=tk.WORD, font=('JetBrains Mono', 9),
                                bg='#0d1117', fg='#c9d1d9', insertbackground='white',
                                selectbackground='#388bfd', selectforeground='white',
                                relief=tk.FLAT, padx=15, pady=15, spacing1=2, spacing3=2)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_container, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure log colors (GitHub dark theme inspired)
        self.log_text.tag_configure('info', foreground='#c9d1d9')
        self.log_text.tag_configure('success', foreground='#3fb950')
        self.log_text.tag_configure('warning', foreground='#d29922')
        self.log_text.tag_configure('error', foreground='#f85149')
        self.log_text.tag_configure('header', foreground='#58a6ff', font=('JetBrains Mono', 9, 'bold'))
        self.log_text.tag_configure('timestamp', foreground='#6e7681')

    def clear_logs(self):
        """Clear the log text area"""
        self.log_text.delete(1.0, tk.END)

    # === Instance Management ===

    def load_instances(self):
        """Load instances into treeview"""
        for item in self.instances_tree.get_children():
            self.instances_tree.delete(item)

        instances = self.instance_manager.get_all_instances()
        running_instances = self.launcher.get_running_instances()

        for instance in instances:
            status = "● Running" if instance["id"] in running_instances else "○ Stopped"
            values = (f"  {instance['name']}", f"  {instance['bluestacks_instance']}", f"  {status}")
            tag = 'running' if instance["id"] in running_instances else 'stopped'
            self.instances_tree.insert("", tk.END, instance["id"], values=values, tags=(tag,))

        # Color-code status
        self.instances_tree.tag_configure('running', foreground=self.colors['success'])
        self.instances_tree.tag_configure('stopped', foreground=self.colors['text_secondary'])

        # Update stats
        self.running_stat.config(text=str(len(running_instances)))
        self.total_stat.config(text=str(len(instances)))

        self.logger.info(f"Loaded {len(instances)} instances, {len(running_instances)} running")

    def on_instance_select(self, event):
        """Handle instance selection"""
        selection = self.instances_tree.selection()

        if not selection:
            self.launch_selected_btn.set_disabled(True)
            self.stop_btn.set_disabled(True)
            self.edit_btn.set_disabled(True)
            self.reset_daily_btn.set_disabled(True)
            self.selected_label.config(text="None")
            self.status_label.config(text="Not Running")
            self.status_dot.config(fg=self.colors['text_secondary'])
            self.log_text.delete(1.0, tk.END)
            return

        running_instances = self.launcher.get_running_instances()

        if len(selection) > 1:
            # Multiple selection
            self.selected_label.config(text=f"{len(selection)} instances")
            self.status_label.config(text="Multiple")
            self.status_dot.config(fg=self.colors['warning'])

            can_launch = any(item_id not in running_instances for item_id in selection)
            self.launch_selected_btn.set_disabled(not can_launch)
            self.stop_btn.set_disabled(True)
            self.edit_btn.set_disabled(True)
            self.reset_daily_btn.set_disabled(True)  # Disable for multiple selection

            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, f"Selected {len(selection)} instances\n\n", 'header')
            for item_id in selection:
                instance = self.instance_manager.get_instance(item_id)
                if instance:
                    status = "Running" if item_id in running_instances else "Stopped"
                    tag = 'success' if status == "Running" else 'info'
                    self.log_text.insert(tk.END, f"  • {instance['name']} ", tag)
                    self.log_text.insert(tk.END, f"({status})\n", 'timestamp')
            return

        # Single selection
        instance_id = selection[0]
        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            return

        is_running = instance_id in running_instances
        status = "Running" if is_running else "Stopped"

        self.selected_label.config(text=instance["name"])
        self.status_label.config(text=status)
        self.status_dot.config(fg=self.colors['success'] if is_running else self.colors['text_secondary'])

        self.launch_selected_btn.set_disabled(is_running)
        self.stop_btn.set_disabled(not is_running)
        self.edit_btn.set_disabled(is_running)
        self.reset_daily_btn.set_disabled(False)  # Enable for single selection

        # Show instance info in log
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, f"Instance: {instance['name']}\n", 'header')
        self.log_text.insert(tk.END, f"BlueStacks: ", 'timestamp')
        self.log_text.insert(tk.END, f"{instance['bluestacks_instance']}\n", 'info')
        self.log_text.insert(tk.END, f"ADB Port: ", 'timestamp')
        self.log_text.insert(tk.END, f"{instance['adb_port']}\n", 'info')
        self.log_text.insert(tk.END, f"Status: ", 'timestamp')
        self.log_text.insert(tk.END, f"{status}\n\n", 'success' if is_running else 'info')

        if is_running:
            self.log_text.insert(tk.END, "─" * 40 + "\n", 'timestamp')
            self.log_text.insert(tk.END, "Automation Logs\n", 'header')
            self.log_text.insert(tk.END, "─" * 40 + "\n\n", 'timestamp')
        else:
            self.log_text.insert(tk.END, "Click ", 'info')
            self.log_text.insert(tk.END, "Launch", 'success')
            self.log_text.insert(tk.END, " to start automation.\n", 'info')

    def update_instance_status(self, instance_id, status):
        """Update instance status in treeview"""
        if not self.instances_tree.exists(instance_id):
            return

        current_values = self.instances_tree.item(instance_id, "values")
        if current_values and len(current_values) >= 3:
            # Determine if instance is actively running based on status
            stopped_statuses = ["Stopped", "Completed", "Partial completion"]
            failed_statuses = ["Failed to start BlueStacks", "Failed to connect to ADB",
                             "Failed to start RoK"]

            is_stopped = status in stopped_statuses or status.startswith("Error:")
            is_failed = status in failed_statuses

            if is_stopped:
                status_display = "○ Stopped"
                tag = 'stopped'
            elif is_failed:
                status_display = "✗ Failed"
                tag = 'stopped'
            else:
                # Any other status means it's running/active
                status_display = f"● {status}"
                tag = 'running'

            new_values = (current_values[0], current_values[1], f"  {status_display}")
            self.instances_tree.item(instance_id, values=new_values, tags=(tag,))

        # Update selected instance status
        selection = self.instances_tree.selection()
        if selection and len(selection) == 1 and selection[0] == instance_id:
            is_running = status == "Running"
            self.status_label.config(text=status)
            self.status_dot.config(fg=self.colors['success'] if is_running else self.colors['text_secondary'])

        # Update running count
        running_instances = self.launcher.get_running_instances()
        self.running_stat.config(text=str(len(running_instances)))

    # === Callbacks ===

    def on_instance_log(self, instance_id, message):
        """Handle log messages from automation"""
        selection = self.instances_tree.selection()
        if selection and len(selection) == 1 and selection[0] == instance_id:
            timestamp = time.strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] ", 'timestamp')
            self.log_text.insert(tk.END, f"{message}\n", 'info')
            self.log_text.see(tk.END)

    def on_instance_status_update(self, instance_id, status):
        """Handle status updates from automation"""
        self.update_instance_status(instance_id, status)

        selection = self.instances_tree.selection()
        if selection and len(selection) == 1 and selection[0] == instance_id:
            is_running = self.launcher.is_instance_running(instance_id)
            self.launch_selected_btn.set_disabled(is_running)
            self.stop_btn.set_disabled(not is_running)
            self.edit_btn.set_disabled(is_running)

    def toggle_auto_exit(self):
        """Toggle auto-exit setting"""
        self.launcher.set_exit_after_complete(self.auto_exit_var.get())
        self.logger.info(f"Auto-exit: {self.auto_exit_var.get()}")

    def reset_daily_tasks(self):
        """Reset daily task tracking for selected instance"""
        selection = self.instances_tree.selection()
        if not selection or len(selection) != 1:
            messagebox.showwarning("Selection Required", "Please select a single instance to reset.")
            return

        instance_id = selection[0]
        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            return

        if not messagebox.askyesno("Confirm Reset",
                                   f"Reset daily task tracking for '{instance['name']}'?\n\n"
                                   "This will allow all daily tasks (build, expedition) to run again."):
            return

        try:
            tracker_path = get_tracker_path_for_instance(
                self.instance_manager.instances_dir, instance_id
            )
            tracker = DailyTaskTracker(tracker_path)
            tracker.reset_all_tasks()

            self.log_text.insert(tk.END, f"\n✓ Daily tasks reset for {instance['name']}\n", 'success')
            self.log_text.see(tk.END)
            self.logger.info(f"Reset daily tasks for instance: {instance['name']}")
            messagebox.showinfo("Reset Complete", f"Daily tasks reset for '{instance['name']}'.")

        except Exception as e:
            self.logger.error(f"Error resetting daily tasks: {e}")
            messagebox.showerror("Error", f"Failed to reset daily tasks: {str(e)}")

    # === Actions ===

    def open_instance_manager(self):
        """Open instance manager dialog"""
        dialog = InstanceManagerDialog(self.root, self.instance_manager, self.on_instances_changed)
        self.root.wait_window(dialog.dialog)

    def on_instances_changed(self, instance_id):
        """Handle changes from instance manager"""
        self.load_instances()
        if instance_id and self.instances_tree.exists(instance_id):
            self.instances_tree.selection_set(instance_id)
            self.on_instance_select(None)

    def launch_selected_instances(self):
        """Launch selected instances"""
        selected = self.instances_tree.selection()
        if not selected:
            return

        running = self.launcher.get_running_instances()
        to_launch = [i for i in selected if i not in running]

        if not to_launch:
            messagebox.showinfo("Already Running", "All selected instances are already running.")
            return

        names = []
        for instance_id in to_launch[:5]:
            instance = self.instance_manager.get_instance(instance_id)
            if instance:
                names.append(instance["name"])
        if len(to_launch) > 5:
            names.append(f"...and {len(to_launch) - 5} more")

        if not messagebox.askyesno("Confirm Launch",
                                   f"Launch {len(to_launch)} instance(s)?\n\n" + "\n".join(f"• {n}" for n in names)):
            return

        self._launch_with_progress(to_launch)

    def _launch_with_progress(self, instance_ids):
        """Launch instances with progress dialog"""
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Launching...")
        progress_win.geometry("450x220")
        progress_win.transient(self.root)
        progress_win.grab_set()
        progress_win.configure(bg=self.colors['card'])
        progress_win.resizable(False, False)

        # Center the window
        progress_win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 450) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 220) // 2
        progress_win.geometry(f"+{x}+{y}")

        # Content
        content = tk.Frame(progress_win, bg=self.colors['card'])
        content.pack(fill=tk.BOTH, expand=True, padx=30, pady=25)

        tk.Label(content, text="🚀 Launching Instances", font=('Segoe UI', 14, 'bold'),
                bg=self.colors['card'], fg=self.colors['text']).pack(anchor=tk.W)

        tk.Label(content, text=f"Starting {len(instance_ids)} instance(s)...",
                font=('Segoe UI', 10), bg=self.colors['card'],
                fg=self.colors['text_secondary']).pack(anchor=tk.W, pady=(5, 20))

        # Progress bar
        progress = ttk.Progressbar(content, length=390, mode='determinate')
        progress.pack(fill=tk.X)
        progress['maximum'] = len(instance_ids)

        status_var = tk.StringVar(value="Initializing...")
        status_label = tk.Label(content, textvariable=status_var, font=('Segoe UI', 10),
                               bg=self.colors['card'], fg=self.colors['text_secondary'])
        status_label.pack(anchor=tk.W, pady=(15, 0))

        def launch():
            force_daily = self.force_daily_tasks_var.get()
            for i, instance_id in enumerate(instance_ids):
                instance = self.instance_manager.get_instance(instance_id)
                name = instance["name"] if instance else instance_id

                self.root.after_idle(lambda n=name: status_var.set(f"Launching {n}..."))
                self.root.after_idle(lambda v=i: progress.config(value=v))

                success = self.launcher.launch_instance(instance_id, force_daily_tasks=force_daily)
                if success:
                    self.root.after_idle(lambda id=instance_id: self.update_instance_status(id, "Starting"))

                if i < len(instance_ids) - 1:
                    time.sleep(5)

            self.root.after_idle(lambda: progress.config(value=len(instance_ids)))
            self.root.after_idle(lambda: status_var.set("✓ Complete!"))
            time.sleep(1)
            self.root.after_idle(self.load_instances)
            self.root.after_idle(progress_win.destroy)

        threading.Thread(target=launch, daemon=True).start()

    def stop_selected_instance(self):
        """Stop selected instance"""
        selection = self.instances_tree.selection()
        if not selection or len(selection) != 1:
            return

        instance_id = selection[0]
        if not self.launcher.is_instance_running(instance_id):
            return

        if self.launcher.stop_instance(instance_id):
            self.update_instance_status(instance_id, "Stopping")

    def edit_selected_instance(self):
        """Edit selected instance configuration"""
        selection = self.instances_tree.selection()
        if not selection or len(selection) != 1:
            return

        instance_id = selection[0]
        if self.launcher.is_instance_running(instance_id):
            messagebox.showinfo("Running", "Cannot edit while instance is running.")
            return

        from bluestacks_manager_gui import RiseOfKingdomsManagerGUI

        instance = self.instance_manager.get_instance(instance_id)
        edit_win = tk.Toplevel(self.root)
        edit_win.title(f"Edit: {instance['name']}")

        self.instance_manager.set_current_instance(instance_id)
        RiseOfKingdomsManagerGUI(edit_win)

        self.root.wait_window(edit_win)
        self.load_instances()

    def launch_all_instances(self):
        """Launch all non-running instances"""
        instances = self.instance_manager.get_all_instances()
        running = self.launcher.get_running_instances()
        to_launch = [i for i in instances if i["id"] not in running]

        if not to_launch:
            messagebox.showinfo("All Running", "All instances are already running.")
            return

        if not messagebox.askyesno("Launch All",
                                   f"Launch {len(to_launch)} instances?\n\n"
                                   "This may impact system performance."):
            return

        self._launch_with_progress([i["id"] for i in to_launch])

    def stop_all_instances(self):
        """Stop all running instances"""
        running = self.launcher.get_running_instances()
        if not running:
            messagebox.showinfo("None Running", "No instances are running.")
            return

        if not messagebox.askyesno("Stop All", f"Stop {len(running)} running instance(s)?"):
            return

        self.launcher.stop_all_instances()

        for instance_id in running:
            self.update_instance_status(instance_id, "Stopping")

        self.load_instances()

    def update_status_thread(self):
        """Background thread to update statuses"""
        while not self.is_closing:
            try:
                running = self.launcher.get_running_instances()
                self.root.after(0, lambda r=running: self.running_stat.config(text=str(len(r))))
                time.sleep(2)
            except Exception as e:
                self.logger.error(f"Status thread error: {e}")
                time.sleep(5)

    def on_closing(self):
        """Handle window close"""
        running = self.launcher.get_running_instances()

        if running:
            if not messagebox.askyesno("Confirm Exit",
                                       f"{len(running)} instance(s) running.\nStop all and exit?"):
                return
            self.launcher.stop_all_instances()
            time.sleep(0.5)

        self.is_closing = True
        self.launcher.shutdown()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = MultiInstanceManagerGUI(root)
    root.mainloop()

#!/usr/bin/env python3
"""
Rise of Kingdoms — Unified GUI

Single-window interface with sidebar instance list and tabbed main content.
Replaces both multi_instance_manager_gui.py and bluestacks_manager_gui.py.
"""
import os
import sys
import time
import logging
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading

from instance_manager import InstanceManager
from instance_manager_gui import InstanceManagerDialog
from multi_instance_launcher import MultiInstanceLauncher
from daily_task_tracker import DailyTaskTracker, get_tracker_path_for_instance
from config_manager import ConfigManager, scan_for_bluestacks_installations, scan_for_adb_executables
from schedule_manager import ScheduleManager


class UnifiedGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("RoK Auto Alliance Bot")
        self.root.geometry("1060x680")
        self.root.minsize(860, 540)
        self.root.configure(bg='#f3f4f6')
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._setup_logging()

        self.instance_manager = InstanceManager()
        self.launcher = MultiInstanceLauncher(self.instance_manager)
        self.schedule_manager = ScheduleManager(self.instance_manager.instances_dir)
        self.launcher.set_callbacks(
            log_callback=self._on_instance_log,
            status_callback=self._on_instance_status,
        )

        self.is_closing = False
        self.selected_instance_id = None
        self.auto_exit_var = tk.BooleanVar(value=True)
        self.force_daily_var = tk.BooleanVar(value=False)
        self.log_buffers = {}
        self.instance_statuses = {}

        self._setup_styles()
        self._build_ui()
        self._load_sidebar()

        self._poll_thread = threading.Thread(target=self._status_poll, daemon=True)
        self._poll_thread.start()

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler("rok_automation.log"), logging.StreamHandler()],
        )
        self.logger = logging.getLogger(__name__)

    # ── styles ──────────────────────────────────────────────────

    def _setup_styles(self):
        s = ttk.Style()
        s.theme_use('clam')

        CARD = '#ffffff'
        BG   = '#f3f4f6'
        BORDER = '#e0e3e8'
        TEXT = '#1e293b'
        TEXT2 = '#64748b'
        PRIMARY = '#4f46e5'

        s.configure('.', font=('Segoe UI', 10), background=BG, foreground=TEXT)
        s.configure('TFrame', background=BG)
        s.configure('Card.TFrame', background=CARD)

        s.configure('TLabel', background=BG, foreground=TEXT)
        s.configure('Card.TLabel', background=CARD, foreground=TEXT)
        s.configure('Dim.TLabel', background=CARD, foreground=TEXT2, font=('Segoe UI', 9))
        s.configure('Section.TLabel', background=CARD, foreground=TEXT2,
                     font=('Segoe UI', 9, 'bold'))
        s.configure('TabActive.TLabel', foreground=PRIMARY, font=('Segoe UI', 10, 'bold'),
                     background=CARD)
        s.configure('TabInactive.TLabel', foreground=TEXT2, font=('Segoe UI', 10),
                     background='#f8f9fa')

        s.configure('TCheckbutton', background=CARD, foreground=TEXT, font=('Segoe UI', 10))
        s.map('TCheckbutton', background=[('active', CARD)])

        s.configure('TSpinbox', arrowsize=14)
        s.configure('TCombobox', arrowsize=14)
        s.map('TCombobox', fieldbackground=[('readonly', 'white')],
              selectbackground=[('readonly', 'white')],
              selectforeground=[('readonly', TEXT)])

        s.configure('Sidebar.TFrame', background='#1e293b')
        s.configure('Sidebar.TLabel', background='#1e293b', foreground='#e2e8f0',
                     font=('Segoe UI', 10))
        s.configure('SidebarTitle.TLabel', background='#1e293b', foreground='#ffffff',
                     font=('Segoe UI', 13, 'bold'))
        s.configure('SidebarDim.TLabel', background='#1e293b', foreground='#94a3b8',
                     font=('Segoe UI', 9))

    # ── build ui ────────────────────────────────────────────────

    def _build_ui(self):
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()

    # ── sidebar ─────────────────────────────────────────────────

    SIDEBAR_BG = '#1e293b'
    SIDEBAR_HOVER = '#334155'
    SIDEBAR_SELECTED = '#4f46e5'
    SIDEBAR_TEXT = '#e2e8f0'
    SIDEBAR_DIM = '#94a3b8'

    def _build_sidebar(self):
        sb = tk.Frame(self.root, bg=self.SIDEBAR_BG, width=230)
        sb.grid(row=0, column=0, sticky='nsew')
        sb.grid_propagate(False)
        sb.grid_rowconfigure(1, weight=1)
        sb.grid_columnconfigure(0, weight=1)

        # header
        hdr = tk.Frame(sb, bg=self.SIDEBAR_BG)
        hdr.grid(row=0, column=0, sticky='ew', padx=16, pady=(18, 12))

        tk.Label(hdr, text="RoK Alliance Bot", font=('Segoe UI', 14, 'bold'),
                 bg=self.SIDEBAR_BG, fg='#ffffff').pack(anchor='w')
        self._sidebar_sub = tk.Label(hdr, text="", font=('Segoe UI', 9),
                                      bg=self.SIDEBAR_BG, fg=self.SIDEBAR_DIM)
        self._sidebar_sub.pack(anchor='w', pady=(2, 0))

        tk.Frame(sb, bg='#334155', height=1).grid(row=0, column=0, sticky='sew')

        # scrollable list
        list_outer = tk.Frame(sb, bg=self.SIDEBAR_BG)
        list_outer.grid(row=1, column=0, sticky='nsew')
        list_outer.grid_rowconfigure(0, weight=1)
        list_outer.grid_columnconfigure(0, weight=1)

        self._sb_canvas = tk.Canvas(list_outer, bg=self.SIDEBAR_BG,
                                     highlightthickness=0, bd=0)
        self._sb_canvas.grid(row=0, column=0, sticky='nsew')

        self._sb_inner = tk.Frame(self._sb_canvas, bg=self.SIDEBAR_BG)
        self._sb_win = self._sb_canvas.create_window((0, 0), window=self._sb_inner, anchor='nw')

        self._sb_inner.bind('<Configure>',
            lambda e: self._sb_canvas.configure(scrollregion=self._sb_canvas.bbox('all')))
        self._sb_canvas.bind('<Configure>',
            lambda e: self._sb_canvas.itemconfig(self._sb_win, width=e.width))
        self._sb_canvas.bind('<Enter>',
            lambda e: self._sb_canvas.bind_all('<MouseWheel>',
                lambda ev: self._sb_canvas.yview_scroll(int(-1*(ev.delta/120)), 'units')))
        self._sb_canvas.bind('<Leave>',
            lambda e: self._sb_canvas.unbind_all('<MouseWheel>'))

        # footer
        tk.Frame(sb, bg='#334155', height=1).grid(row=2, column=0, sticky='ew')

        footer = tk.Frame(sb, bg=self.SIDEBAR_BG)
        footer.grid(row=3, column=0, sticky='ew', padx=10, pady=10)

        tk.Button(footer, text="▶ Launch All", font=('Segoe UI', 9, 'bold'),
                  bg='#22c55e', fg='white', activebackground='#16a34a', activeforeground='white',
                  relief='flat', bd=0, padx=10, pady=4, cursor='hand2',
                  command=self._launch_all).pack(side='left', padx=(0, 4))

        tk.Button(footer, text="■ Stop All", font=('Segoe UI', 9, 'bold'),
                  bg='#ef4444', fg='white', activebackground='#dc2626', activeforeground='white',
                  relief='flat', bd=0, padx=10, pady=4, cursor='hand2',
                  command=self._stop_all).pack(side='left', padx=(0, 4))

        tk.Button(footer, text="Manage", font=('Segoe UI', 9),
                  bg='#334155', fg='#cbd5e1', activebackground='#475569', activeforeground='white',
                  relief='flat', bd=0, padx=10, pady=4, cursor='hand2',
                  command=self._open_manager).pack(side='right')

    # ── sidebar items ───────────────────────────────────────────

    def _load_sidebar(self):
        for w in self._sb_inner.winfo_children():
            w.destroy()

        instances = self.instance_manager.get_all_instances()
        running = self.launcher.get_running_instances()
        self._sidebar_sub.config(text=f"{len(instances)} instance{'s' if len(instances) != 1 else ''} · {len(running)} running")

        for inst in instances:
            self._sidebar_item(inst, inst['id'] in running)

        if not self.selected_instance_id and instances:
            self._select_instance(instances[0]['id'])

    def _sidebar_item(self, inst, is_running):
        iid = inst['id']
        selected = iid == self.selected_instance_id
        bg = self.SIDEBAR_SELECTED if selected else self.SIDEBAR_BG

        frame = tk.Frame(self._sb_inner, bg=bg, cursor='hand2')
        frame.pack(fill='x', padx=6, pady=1)

        inner = tk.Frame(frame, bg=bg)
        inner.pack(fill='x', padx=10, pady=7)

        # dot
        status_text = self.instance_statuses.get(iid, '')
        is_error = 'error' in status_text.lower() or 'fail' in status_text.lower()
        dot_fg = '#ef4444' if is_error else ('#22c55e' if is_running else '#64748b')
        tk.Label(inner, text="●", font=('Segoe UI', 7), bg=bg, fg=dot_fg
                 ).pack(side='left', padx=(0, 8))

        info = tk.Frame(inner, bg=bg)
        info.pack(side='left', fill='x', expand=True)

        name_fg = '#ffffff' if selected else self.SIDEBAR_TEXT
        tk.Label(info, text=inst['name'], font=('Segoe UI', 10, 'bold' if selected else ''),
                 bg=bg, fg=name_fg, anchor='w').pack(anchor='w')

        sub = f"{inst.get('bluestacks_instance', '')} · :{inst.get('adb_port', '')}"
        tk.Label(info, text=sub, font=('Segoe UI', 8),
                 bg=bg, fg='#94a3b8' if not selected else '#c7d2fe', anchor='w').pack(anchor='w')

        progress = self._get_daily_progress(iid)
        pfg = '#a5b4fc' if selected else self.SIDEBAR_DIM
        tk.Label(inner, text=progress, font=('Segoe UI', 9), bg=bg, fg=pfg
                 ).pack(side='right')

        # bind click on everything
        def click(e, i=iid):
            self._select_instance(i)
        for w in [frame, inner] + list(inner.winfo_children()) + list(info.winfo_children()):
            w.bind('<Button-1>', click)

        if not selected:
            def enter(e, f=frame, inn=inner, inf=info):
                for w in [f, inn, inf] + list(inn.winfo_children()) + list(inf.winfo_children()):
                    try: w.configure(bg=self.SIDEBAR_HOVER)
                    except: pass
            def leave(e, f=frame, inn=inner, inf=info):
                for w in [f, inn, inf] + list(inn.winfo_children()) + list(inf.winfo_children()):
                    try: w.configure(bg=self.SIDEBAR_BG)
                    except: pass
            frame.bind('<Enter>', enter)
            frame.bind('<Leave>', leave)

    # ── main area ───────────────────────────────────────────────

    def _build_main(self):
        main = tk.Frame(self.root, bg='#f3f4f6')
        main.grid(row=0, column=1, sticky='nsew')
        main.grid_rowconfigure(2, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # toolbar
        toolbar = tk.Frame(main, bg='white', height=52)
        toolbar.grid(row=0, column=0, sticky='ew')
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(1, weight=1)

        self._tb_title = tk.Label(toolbar, text="Select an instance",
                                   font=('Segoe UI', 14, 'bold'), bg='white', fg='#1e293b')
        self._tb_title.grid(row=0, column=0, padx=(20, 0), pady=13, sticky='w')

        self._tb_status = tk.Label(toolbar, text="", font=('Segoe UI', 10),
                                    bg='white', fg='#94a3b8')
        self._tb_status.grid(row=0, column=1, padx=(8, 0), sticky='w')

        btn_frame = tk.Frame(toolbar, bg='white')
        btn_frame.grid(row=0, column=2, padx=(0, 16), sticky='e')

        self._launch_btn = tk.Button(
            btn_frame, text="▶ Launch", font=('Segoe UI', 10, 'bold'),
            bg='#4f46e5', fg='white', activebackground='#4338ca', activeforeground='white',
            relief='flat', bd=0, padx=14, pady=5, cursor='hand2',
            command=self._launch_selected)
        self._launch_btn.pack(side='left', padx=(0, 6))

        self._stop_btn = tk.Button(
            btn_frame, text="■ Stop", font=('Segoe UI', 10, 'bold'),
            bg='#ef4444', fg='white', activebackground='#dc2626', activeforeground='white',
            relief='flat', bd=0, padx=14, pady=5, cursor='hand2',
            command=self._stop_selected)
        self._stop_btn.pack(side='left')

        tk.Frame(main, bg='#e5e7eb', height=1).grid(row=0, column=0, sticky='sew')

        # tab bar
        tab_bar = tk.Frame(main, bg='#f8f9fa')
        tab_bar.grid(row=1, column=0, sticky='ew')

        self._current_tab = 'tasks'
        self._tab_btns = {}
        for name in ('Tasks', 'Config', 'Logs'):
            key = name.lower()
            lbl = tk.Label(tab_bar, text=name, font=('Segoe UI', 10),
                           bg='#f8f9fa', fg='#94a3b8', padx=18, pady=8, cursor='hand2')
            lbl.pack(side='left')
            lbl.bind('<Button-1>', lambda e, k=key: self._switch_tab(k))
            self._tab_btns[key] = lbl

        tk.Frame(main, bg='#e5e7eb', height=1).grid(row=1, column=0, sticky='sew')

        # content
        self._content = tk.Frame(main, bg='#f3f4f6')
        self._content.grid(row=2, column=0, sticky='nsew')
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._tab_frames = {}
        self._build_tasks_tab()
        self._build_config_tab()
        self._build_logs_tab()

        self._switch_tab('tasks')

    # ── tab switching ───────────────────────────────────────────

    def _switch_tab(self, key):
        self._current_tab = key
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.configure(fg='#4f46e5', font=('Segoe UI', 10, 'bold'), bg='white')
            else:
                btn.configure(fg='#94a3b8', font=('Segoe UI', 10), bg='#f8f9fa')

        for k, f in self._tab_frames.items():
            if k == key:
                f.grid(row=0, column=0, sticky='nsew')
            else:
                f.grid_forget()

        if key == 'logs':
            self._render_logs()

    # ── tasks tab ───────────────────────────────────────────────

    def _build_tasks_tab(self):
        outer = tk.Frame(self._content, bg='#f3f4f6')
        self._tab_frames['tasks'] = outer
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg='#f3f4f6', highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky='nsew')
        sb = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)

        inner = tk.Frame(canvas, bg='#f3f4f6')
        cw = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(cw, width=e.width))
        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>',
            lambda ev: canvas.yview_scroll(int(-1*(ev.delta/120)), 'units')))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

        pad = tk.Frame(inner, bg='#f3f4f6')
        pad.pack(fill='x', padx=20, pady=16)

        # ── card
        card = tk.Frame(pad, bg='white', highlightbackground='#e5e7eb', highlightthickness=1)
        card.pack(fill='x')

        card_inner = tk.Frame(card, bg='white')
        card_inner.pack(fill='x', padx=20, pady=16)

        # daily tasks
        tk.Label(card_inner, text="DAILY TASKS", font=('Segoe UI', 9, 'bold'),
                 bg='white', fg='#94a3b8').pack(anchor='w', pady=(0, 8))

        self.build_var = tk.BooleanVar(value=True)
        self.build_row = self._task_row(card_inner, "1 Troop Build",
            "Join alliance building via bookmarked marker", self.build_var)

        self.expedition_var = tk.BooleanVar(value=True)
        self.expedition_row = self._task_row(card_inner, "Expedition Collection",
            "Collect expedition chest rewards", self.expedition_var)

        # separator
        tk.Frame(card_inner, bg='#f1f5f9', height=1).pack(fill='x', pady=12)

        # recurring tasks
        tk.Label(card_inner, text="RECURRING TASKS", font=('Segoe UI', 9, 'bold'),
                 bg='white', fg='#94a3b8').pack(anchor='w', pady=(0, 8))

        self.donation_var = tk.BooleanVar(value=True)
        self.donation_row = self._task_row(card_inner, "Tech Donation",
            "Donate to Officer's recommended technology", self.donation_var)

        # separator
        tk.Frame(card_inner, bg='#f1f5f9', height=1).pack(fill='x', pady=12)

        # run options
        tk.Label(card_inner, text="RUN OPTIONS", font=('Segoe UI', 9, 'bold'),
                 bg='white', fg='#94a3b8').pack(anchor='w', pady=(0, 8))

        opts = tk.Frame(card_inner, bg='white')
        opts.pack(fill='x')
        opts.grid_columnconfigure(0, weight=1, uniform='opt')
        opts.grid_columnconfigure(1, weight=1, uniform='opt')
        opts.grid_columnconfigure(2, weight=1, uniform='opt')

        self.characters_var = tk.IntVar(value=10)
        self._opt_field(opts, "Characters", self.characters_var, 0, spinbox=(1, 22))

        self.march_var = tk.IntVar(value=1)
        self._opt_field(opts, "March Preset", self.march_var, 1, spinbox=(1, 7))

        self.version_var = tk.StringVar(value='Global')
        self._opt_field(opts, "Game Version", self.version_var, 2,
                        combo=['Global', 'Gamota', 'KR'])

        # save
        save_frame = tk.Frame(card_inner, bg='white')
        save_frame.pack(fill='x', pady=(16, 0))

        tk.Button(save_frame, text="Save Changes", font=('Segoe UI', 10, 'bold'),
                  bg='#4f46e5', fg='white', activebackground='#4338ca', activeforeground='white',
                  relief='flat', bd=0, padx=20, pady=6, cursor='hand2',
                  command=self._save_tasks).pack(side='right')

    def _task_row(self, parent, title, desc, var):
        row = tk.Frame(parent, bg='#f8fafc', highlightbackground='#e2e8f0', highlightthickness=1)
        row.pack(fill='x', pady=(0, 6))

        inner = tk.Frame(row, bg='#f8fafc')
        inner.pack(fill='x', padx=12, pady=10)

        cb = ttk.Checkbutton(inner, variable=var)
        cb.configure(style='TCheckbutton')
        cb.pack(side='left', padx=(0, 10))
        # override checkbutton bg to match row
        ttk.Style().configure('TCheckbutton', background='#f8fafc')

        info = tk.Frame(inner, bg='#f8fafc')
        info.pack(side='left', fill='x', expand=True)
        tk.Label(info, text=title, font=('Segoe UI', 11), bg='#f8fafc', fg='#1e293b'
                 ).pack(anchor='w')
        tk.Label(info, text=desc, font=('Segoe UI', 9), bg='#f8fafc', fg='#94a3b8'
                 ).pack(anchor='w')

        status_lbl = tk.Label(inner, text="", font=('Segoe UI', 10, 'bold'),
                              bg='#f8fafc', fg='#94a3b8')
        status_lbl.pack(side='right', padx=(8, 0))

        row._status = status_lbl
        return row

    def _opt_field(self, parent, label, var, col, spinbox=None, combo=None):
        frame = tk.Frame(parent, bg='white')
        frame.grid(row=0, column=col, sticky='ew', padx=(0, 16) if col < 2 else 0)

        tk.Label(frame, text=label, font=('Segoe UI', 9), bg='white', fg='#64748b'
                 ).pack(anchor='w')

        if spinbox:
            lo, hi = spinbox
            ttk.Spinbox(frame, from_=lo, to=hi, textvariable=var, width=8
                        ).pack(anchor='w', pady=(3, 0))
        elif combo:
            ttk.Combobox(frame, textvariable=var, values=combo, state='readonly', width=12
                         ).pack(anchor='w', pady=(3, 0))

    # ── config tab ──────────────────────────────────────────────

    def _build_config_tab(self):
        outer = tk.Frame(self._content, bg='#f3f4f6')
        self._tab_frames['config'] = outer
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg='#f3f4f6', highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky='nsew')
        sb = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)

        inner = tk.Frame(canvas, bg='#f3f4f6')
        cw = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(cw, width=e.width))
        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>',
            lambda ev: canvas.yview_scroll(int(-1*(ev.delta/120)), 'units')))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

        pad = tk.Frame(inner, bg='#f3f4f6')
        pad.pack(fill='x', padx=20, pady=16)

        # ── paths card
        card1 = self._card(pad, "BLUESTACKS PATHS")

        self.bs_path_var = tk.StringVar()
        self._path_row(card1, "BlueStacks Path", self.bs_path_var,
                        self._browse_bs, self._scan_bs)
        self.adb_path_var = tk.StringVar()
        self._path_row(card1, "ADB Path", self.adb_path_var,
                        self._browse_adb, self._scan_adb)

        # ── instance card
        card2 = self._card(pad, "INSTANCE SETTINGS")

        grid = tk.Frame(card2, bg='white')
        grid.pack(fill='x')
        grid.grid_columnconfigure(1, weight=1)

        self.bs_instance_var = tk.StringVar()
        self._cfg_row(grid, "BlueStacks Instance", self.bs_instance_var, 0)

        self.adb_port_var = tk.StringVar()
        self._cfg_row(grid, "ADB Port", self.adb_port_var, 1, width=10)

        self.startup_wait_var = tk.IntVar(value=20)
        self._cfg_row(grid, "Startup Wait (sec)", self.startup_wait_var, 2, spinbox=(5, 60, 5))

        # ── options card
        card3 = self._card(pad, "OPTIONS")

        ttk.Checkbutton(card3, text="Auto-exit BlueStacks after done",
                         variable=self.auto_exit_var,
                         command=self._on_auto_exit).pack(anchor='w', pady=2)
        ttk.Checkbutton(card3, text="Force daily tasks (run even if completed today)",
                         variable=self.force_daily_var).pack(anchor='w', pady=2)

        # ── actions
        actions = tk.Frame(pad, bg='#f3f4f6')
        actions.pack(fill='x', pady=(12, 0))

        tk.Button(actions, text="Reset Daily Tasks", font=('Segoe UI', 10),
                  bg='#f59e0b', fg='white', activebackground='#d97706', activeforeground='white',
                  relief='flat', bd=0, padx=14, pady=5, cursor='hand2',
                  command=self._reset_daily).pack(side='left', padx=(0, 8))

        tk.Button(actions, text="Save Config", font=('Segoe UI', 10, 'bold'),
                  bg='#4f46e5', fg='white', activebackground='#4338ca', activeforeground='white',
                  relief='flat', bd=0, padx=20, pady=5, cursor='hand2',
                  command=self._save_config).pack(side='right')

    def _card(self, parent, title):
        wrapper = tk.Frame(parent, bg='white', highlightbackground='#e5e7eb',
                           highlightthickness=1)
        wrapper.pack(fill='x', pady=(0, 12))
        inner = tk.Frame(wrapper, bg='white')
        inner.pack(fill='x', padx=20, pady=16)
        tk.Label(inner, text=title, font=('Segoe UI', 9, 'bold'), bg='white', fg='#94a3b8'
                 ).pack(anchor='w', pady=(0, 10))
        return inner

    def _path_row(self, parent, label, var, browse_cmd, scan_cmd):
        tk.Label(parent, text=label, font=('Segoe UI', 9), bg='white', fg='#64748b'
                 ).pack(anchor='w', pady=(0, 2))

        row = tk.Frame(parent, bg='white')
        row.pack(fill='x', pady=(0, 10))

        ttk.Entry(row, textvariable=var, width=50).pack(side='left', fill='x', expand=True)

        tk.Button(row, text="Browse", font=('Segoe UI', 9),
                  bg='#e5e7eb', fg='#374151', activebackground='#d1d5db',
                  relief='flat', bd=0, padx=8, pady=2, cursor='hand2',
                  command=browse_cmd).pack(side='left', padx=(6, 0))
        tk.Button(row, text="Scan", font=('Segoe UI', 9),
                  bg='#e5e7eb', fg='#374151', activebackground='#d1d5db',
                  relief='flat', bd=0, padx=8, pady=2, cursor='hand2',
                  command=scan_cmd).pack(side='left', padx=(4, 0))

    def _cfg_row(self, parent, label, var, row, width=25, spinbox=None):
        tk.Label(parent, text=label, font=('Segoe UI', 10), bg='white', fg='#374151'
                 ).grid(row=row, column=0, sticky='w', pady=5)

        if spinbox:
            lo, hi, step = spinbox
            ttk.Spinbox(parent, from_=lo, to=hi, increment=step,
                        textvariable=var, width=8).grid(
                row=row, column=1, sticky='w', padx=(12, 0), pady=5)
        else:
            ttk.Entry(parent, textvariable=var, width=width).grid(
                row=row, column=1, sticky='w', padx=(12, 0), pady=5)

    # ── logs tab ────────────────────────────────────────────────

    def _build_logs_tab(self):
        outer = tk.Frame(self._content, bg='#f3f4f6')
        self._tab_frames['logs'] = outer
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        wrapper = tk.Frame(outer, bg='white', highlightbackground='#e5e7eb',
                           highlightthickness=1)
        wrapper.grid(row=0, column=0, sticky='nsew', padx=20, pady=16)
        wrapper.grid_rowconfigure(1, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        # header
        hdr = tk.Frame(wrapper, bg='white')
        hdr.grid(row=0, column=0, sticky='ew', padx=16, pady=(12, 0))

        tk.Label(hdr, text="AUTOMATION LOGS", font=('Segoe UI', 9, 'bold'),
                 bg='white', fg='#94a3b8').pack(side='left')

        tk.Button(hdr, text="Clear", font=('Segoe UI', 9),
                  bg='#e5e7eb', fg='#374151', activebackground='#d1d5db',
                  relief='flat', bd=0, padx=8, pady=2, cursor='hand2',
                  command=self._clear_logs).pack(side='right')

        # text
        log_frame = tk.Frame(wrapper, bg='#0f172a')
        log_frame.grid(row=1, column=0, sticky='nsew', padx=12, pady=12)
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self._log_text = tk.Text(
            log_frame, wrap='word', font=('Consolas', 10),
            bg='#0f172a', fg='#cbd5e1', insertbackground='white',
            selectbackground='#334155', relief='flat', padx=12, pady=10,
            spacing1=1, spacing3=1)
        self._log_text.grid(row=0, column=0, sticky='nsew')

        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky='ns')

        self._log_text.tag_configure('ts', foreground='#475569', font=('Consolas', 9))
        self._log_text.tag_configure('info', foreground='#cbd5e1')
        self._log_text.tag_configure('ok', foreground='#4ade80')
        self._log_text.tag_configure('warn', foreground='#fbbf24')
        self._log_text.tag_configure('err', foreground='#f87171')

    def _render_logs(self):
        self._log_text.delete('1.0', 'end')
        iid = self.selected_instance_id
        if not iid:
            self._log_text.insert('end', "Select an instance to view logs.\n", 'info')
            return
        buf = self.log_buffers.get(iid, [])
        if not buf:
            self._log_text.insert('end', "No logs yet. Launch the instance to start.\n", 'info')
            return
        for ts, msg, tag in buf:
            self._log_text.insert('end', f"[{ts}] ", 'ts')
            self._log_text.insert('end', f"{msg}\n", tag)
        self._log_text.see('end')

    def _clear_logs(self):
        iid = self.selected_instance_id
        if iid:
            self.log_buffers[iid] = []
        self._log_text.delete('1.0', 'end')

    # ── select instance ─────────────────────────────────────────

    def _select_instance(self, instance_id):
        self.selected_instance_id = instance_id
        inst = self.instance_manager.get_instance(instance_id)
        if not inst:
            return

        is_running = self.launcher.is_instance_running(instance_id)
        status = self.instance_statuses.get(instance_id, '')

        self._tb_title.config(text=inst['name'])
        if is_running:
            self._tb_status.config(text=f"· {status or 'Running'}", fg='#22c55e')
        else:
            self._tb_status.config(text="· Idle", fg='#94a3b8')

        self._load_instance_ui(instance_id)
        self._load_sidebar()

        if self._current_tab == 'logs':
            self._render_logs()

    def _load_instance_ui(self, iid):
        cm = self.instance_manager.get_config_manager(iid)
        if not cm:
            return

        self.build_var.set(cm.get_bool('RiseOfKingdoms', 'perform_build', True))
        self.expedition_var.set(cm.get_bool('RiseOfKingdoms', 'perform_expedition', True))
        self.donation_var.set(cm.get_bool('RiseOfKingdoms', 'perform_donation', True))
        self.characters_var.set(cm.get_int('RiseOfKingdoms', 'num_of_characters', 10))
        self.march_var.set(cm.get_int('RiseOfKingdoms', 'march_preset', 1))
        self.version_var.set(
            cm.get_config('RiseOfKingdoms', 'rok_version', 'global').capitalize())

        self.bs_path_var.set(cm.get_config('BlueStacks', 'bluestacks_exe_path', ''))
        self.adb_path_var.set(cm.get_config('BlueStacks', 'adb_path', ''))
        self.bs_instance_var.set(cm.get_config('BlueStacks', 'bluestacks_instance_name', ''))
        self.adb_port_var.set(cm.get_config('BlueStacks', 'adb_port', '5555'))
        self.startup_wait_var.set(cm.get_int('BlueStacks', 'wait_for_startup_seconds', 20))

        self._update_task_status(iid)

    def _update_task_status(self, iid):
        cm = self.instance_manager.get_config_manager(iid)
        if not cm:
            return

        num = cm.get_int('RiseOfKingdoms', 'num_of_characters', 1)
        path = get_tracker_path_for_instance(self.instance_manager.instances_dir, iid)

        if not os.path.exists(path):
            for r in (self.build_row, self.expedition_row):
                r._status.config(text=f"0/{num}", fg='#94a3b8')
            self.donation_row._status.config(text="every cycle", fg='#94a3b8')
            return

        tracker = DailyTaskTracker(path)
        st = tracker.get_completion_status()
        today = st['today_utc']

        for key, row in [('build', self.build_row), ('expedition', self.expedition_row)]:
            done = sum(1 for ci in range(num)
                       if st['characters'].get(str(ci), {}).get(key) == today)
            color = '#22c55e' if done == num else '#64748b'
            row._status.config(text=f"{done}/{num}", fg=color)

        self.donation_row._status.config(text="every cycle", fg='#94a3b8')

    # ── actions ─────────────────────────────────────────────────

    def _launch_selected(self):
        iid = self.selected_instance_id
        if not iid:
            return
        if self.launcher.is_instance_running(iid):
            messagebox.showinfo("Running", "This instance is already running.")
            return
        self._save_tasks(silent=True)
        if self.launcher.launch_instance(iid, force_daily_tasks=self.force_daily_var.get()):
            self.instance_statuses[iid] = 'Starting'
            self._select_instance(iid)

    def _stop_selected(self):
        iid = self.selected_instance_id
        if not iid:
            return
        if self.launcher.is_instance_running(iid):
            self.launcher.stop_instance(iid)
            self.instance_statuses[iid] = 'Stopping'
            self._load_sidebar()

    def _launch_all(self):
        instances = self.instance_manager.get_all_instances()
        running = self.launcher.get_running_instances()
        to_launch = [i for i in instances if i['id'] not in running]
        if not to_launch:
            messagebox.showinfo("All Running", "All instances are already running.")
            return
        names = [i['name'] for i in to_launch[:5]]
        if len(to_launch) > 5:
            names.append(f"...and {len(to_launch)-5} more")
        if not messagebox.askyesno("Launch All",
            f"Launch {len(to_launch)} instance(s)?\n\n" +
            "\n".join(f"  • {n}" for n in names)):
            return
        force = self.force_daily_var.get()
        def do():
            for i, inst in enumerate(to_launch):
                self.launcher.launch_instance(inst['id'], force_daily_tasks=force)
                self.instance_statuses[inst['id']] = 'Starting'
                if i < len(to_launch) - 1:
                    time.sleep(5)
            self.root.after(0, self._load_sidebar)
        threading.Thread(target=do, daemon=True).start()

    def _stop_all(self):
        running = self.launcher.get_running_instances()
        if not running:
            messagebox.showinfo("None Running", "No instances are running.")
            return
        if not messagebox.askyesno("Stop All", f"Stop {len(running)} running instance(s)?"):
            return
        self.launcher.stop_all_instances()
        for iid in running:
            self.instance_statuses[iid] = 'Stopping'
        self._load_sidebar()

    def _open_manager(self):
        dialog = InstanceManagerDialog(self.root, self.instance_manager, self._on_mgr_done)
        self.root.wait_window(dialog.dialog)

    def _on_mgr_done(self, instance_id):
        self._load_sidebar()
        if instance_id:
            self._select_instance(instance_id)

    def _reset_daily(self):
        iid = self.selected_instance_id
        if not iid:
            messagebox.showwarning("No Instance", "Select an instance first.")
            return
        inst = self.instance_manager.get_instance(iid)
        if not inst:
            return
        if not messagebox.askyesno("Confirm Reset",
            f"Reset daily task tracking for '{inst['name']}'?\n"
            "All daily tasks will run again on next launch."):
            return
        path = get_tracker_path_for_instance(self.instance_manager.instances_dir, iid)
        DailyTaskTracker(path).reset_all_tasks()
        self._update_task_status(iid)
        self._load_sidebar()
        messagebox.showinfo("Done", f"Daily tasks reset for '{inst['name']}'.")

    def _on_auto_exit(self):
        self.launcher.set_exit_after_complete(self.auto_exit_var.get())

    # ── save ────────────────────────────────────────────────────

    ROK_PACKAGES = {
        'Global': 'com.lilithgame.roc.gp',
        'Gamota': 'com.rok.gp.vn',
        'KR': 'com.lilithgames.rok.gpkr',
    }

    def _save_tasks(self, silent=False):
        iid = self.selected_instance_id
        if not iid:
            return
        cm = self.instance_manager.get_config_manager(iid)
        if not cm:
            return
        c = cm.config
        c['RiseOfKingdoms']['perform_build'] = str(self.build_var.get())
        c['RiseOfKingdoms']['perform_expedition'] = str(self.expedition_var.get())
        c['RiseOfKingdoms']['perform_donation'] = str(self.donation_var.get())
        c['RiseOfKingdoms']['num_of_characters'] = str(self.characters_var.get())
        c['RiseOfKingdoms']['march_preset'] = str(self.march_var.get())
        ver = self.version_var.get()
        c['RiseOfKingdoms']['rok_version'] = ver.lower()
        c['RiseOfKingdoms']['package_name'] = self.ROK_PACKAGES.get(ver, self.ROK_PACKAGES['Global'])
        with open(cm.config_path, 'w') as f:
            c.write(f)
        self._update_task_status(iid)
        if not silent:
            messagebox.showinfo("Saved", "Task settings saved.")

    def _save_config(self):
        iid = self.selected_instance_id
        if not iid:
            return
        cm = self.instance_manager.get_config_manager(iid)
        if not cm:
            return
        c = cm.config
        c['BlueStacks']['bluestacks_exe_path'] = self.bs_path_var.get()
        c['BlueStacks']['adb_path'] = self.adb_path_var.get()
        c['BlueStacks']['bluestacks_instance_name'] = self.bs_instance_var.get()
        c['BlueStacks']['adb_port'] = self.adb_port_var.get()
        c['BlueStacks']['wait_for_startup_seconds'] = str(self.startup_wait_var.get())
        with open(cm.config_path, 'w') as f:
            c.write(f)
        self.instance_manager.update_instance(iid,
            bluestacks_instance=self.bs_instance_var.get(),
            adb_port=self.adb_port_var.get())
        self._save_tasks(silent=True)
        self._load_sidebar()
        messagebox.showinfo("Saved", "Configuration saved.")

    # ── browse / scan ───────────────────────────────────────────

    def _browse_bs(self):
        p = filedialog.askopenfilename(title="Select BlueStacks",
            filetypes=[("Executable", "*.exe"), ("All", "*.*")])
        if p:
            self.bs_path_var.set(p)

    def _browse_adb(self):
        p = filedialog.askopenfilename(title="Select ADB",
            filetypes=[("Executable", "*.exe"), ("All", "*.*")])
        if p:
            self.adb_path_var.set(p)

    def _scan_bs(self):
        def w():
            r = scan_for_bluestacks_installations()
            self.root.after(0, lambda: self._on_bs_scan(r))
        threading.Thread(target=w, daemon=True).start()

    def _on_bs_scan(self, results):
        if not results:
            messagebox.showwarning("Scan", "No BlueStacks installation found.")
            return
        player, adb = results[0]
        self.bs_path_var.set(player)
        if adb:
            self.adb_path_var.set(adb)
        messagebox.showinfo("Found", f"BlueStacks: {player}")

    def _scan_adb(self):
        def w():
            r = scan_for_adb_executables()
            self.root.after(0, lambda: self._on_adb_scan(r))
        threading.Thread(target=w, daemon=True).start()

    def _on_adb_scan(self, paths):
        if not paths:
            messagebox.showwarning("Scan", "No ADB executable found.")
            return
        self.adb_path_var.set(paths[0])
        messagebox.showinfo("Found", f"ADB: {paths[0]}")

    # ── callbacks ───────────────────────────────────────────────

    def _on_instance_log(self, instance_id, message):
        ts = time.strftime('%H:%M:%S')
        tag = 'info'
        ml = message.lower()
        if 'error' in ml or 'failed' in ml:
            tag = 'err'
        elif 'warning' in ml or 'not found' in ml or 'fallback' in ml:
            tag = 'warn'
        elif 'success' in ml or 'completed' in ml or 'confirmed' in ml or 'detected' in ml:
            tag = 'ok'

        buf = self.log_buffers.setdefault(instance_id, [])
        buf.append((ts, message, tag))
        if len(buf) > 2000:
            self.log_buffers[instance_id] = buf[-1500:]

        if self.selected_instance_id == instance_id and self._current_tab == 'logs':
            self._log_text.insert('end', f"[{ts}] ", 'ts')
            self._log_text.insert('end', f"{message}\n", tag)
            self._log_text.see('end')

    def _on_instance_status(self, instance_id, status):
        self.instance_statuses[instance_id] = status
        self.root.after(0, self._load_sidebar)
        if self.selected_instance_id == instance_id:
            is_running = self.launcher.is_instance_running(instance_id)
            if is_running:
                self.root.after(0, lambda: self._tb_status.config(
                    text=f"· {status}", fg='#22c55e'))
            else:
                self.root.after(0, lambda: self._tb_status.config(
                    text="· Idle", fg='#94a3b8'))
                self.root.after(0, lambda: self._update_task_status(instance_id))

    # ── status poll ─────────────────────────────────────────────

    def _status_poll(self):
        while not self.is_closing:
            try:
                self.root.after(0, self._load_sidebar)
            except Exception:
                pass
            time.sleep(3)

    # ── helpers ──────────────────────────────────────────────────

    def _get_daily_progress(self, iid):
        try:
            cm = self.instance_manager.get_config_manager(iid)
            if not cm:
                return '—'
            num = cm.get_int('RiseOfKingdoms', 'num_of_characters', 1)
            path = get_tracker_path_for_instance(self.instance_manager.instances_dir, iid)
            if not os.path.exists(path):
                return f"0/{num}"
            tracker = DailyTaskTracker(path)
            st = tracker.get_completion_status()
            today = st['today_utc']
            done = sum(1 for ci in range(num)
                       if any(d == today for d in st['characters'].get(str(ci), {}).values()))
            return f"{done}/{num}"
        except Exception:
            return '?'

    def _on_closing(self):
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


if __name__ == '__main__':
    root = tk.Tk()
    app = UnifiedGUI(root)
    root.mainloop()

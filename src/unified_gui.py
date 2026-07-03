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

import timings
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

    # ── design tokens ───────────────────────────────────────────
    # One place for the spacing rhythm, type scale, and color palette so the
    # rest of the class reads from these instead of scattering literals.

    FONT_FAMILY = 'Segoe UI'
    FONT_TITLE   = (FONT_FAMILY, 14, 'bold')   # window / toolbar title
    FONT_SUB     = (FONT_FAMILY, 13, 'bold')   # sidebar app name
    FONT_SECTION = (FONT_FAMILY, 9, 'bold')    # ALL-CAPS section headers
    FONT_BODY    = (FONT_FAMILY, 10)           # standard body text / controls
    FONT_BODY_BD = (FONT_FAMILY, 10, 'bold')   # bold body text / primary buttons
    FONT_ROW     = (FONT_FAMILY, 11)           # task-row titles
    FONT_LABEL   = (FONT_FAMILY, 9)            # field captions / secondary buttons
    FONT_SMALL   = (FONT_FAMILY, 8)            # sidebar meta text
    FONT_DOT     = (FONT_FAMILY, 7)            # status dot glyph
    FONT_MONO    = ('Consolas', 10)            # log console

    # Spacing scale (base-4). Everything in the UI should pad/pack to one of
    # these instead of an ad hoc pixel count.
    PAD_XS = 4
    PAD_SM = 8
    PAD_MD = 12
    PAD_LG = 16
    PAD_XL = 20

    # One status palette, used identically by the sidebar dots, the toolbar
    # status label, and the schedule indicator.
    STATUS_RUNNING   = '#22c55e'
    STATUS_STOPPED   = '#64748b'
    STATUS_IDLE      = '#94a3b8'
    STATUS_ERROR     = '#ef4444'
    STATUS_SCHEDULED = '#f59e0b'

    CARD           = '#ffffff'
    BG             = '#f3f4f6'
    BORDER         = '#e5e7eb'
    TEXT           = '#1e293b'
    TEXT2          = '#94a3b8'
    PRIMARY        = '#4f46e5'
    PRIMARY_ACTIVE = '#4338ca'
    DANGER         = '#ef4444'
    DANGER_ACTIVE  = '#dc2626'
    DISABLED_BG    = '#e5e7eb'
    DISABLED_FG    = '#94a3b8'

    # A single content-width cap so form fields (entries/combos/spinboxes)
    # don't stretch edge-to-edge on wide windows - see _capped().
    CONTENT_MAX_WIDTH = 640

    # Consistent Entry/Spinbox width "scale" (in characters) so fields read
    # as an intentional system instead of ad hoc numbers per row.
    FIELD_W_NUM   = 8    # short numeric spinboxes (characters, march preset, wait secs)
    FIELD_W_SHORT = 10   # short text fields (adb port)
    FIELD_W_MED   = 25   # medium text fields (instance name)
    FIELD_W_LONG  = 50   # full file paths

    # ── styles ──────────────────────────────────────────────────

    def _setup_styles(self):
        s = ttk.Style()
        # 'vista' gives native Windows checkbox/combobox/spinbox rendering -
        # a real checkmark tick and properly-sized spin arrows - instead of
        # clam's ambiguous boxed "X" indicator and tiny arrows. Falls back to
        # 'clam' (full manual color control) on non-Windows so this never
        # hard-fails in a dev/test environment.
        try:
            s.theme_use('vista')
        except tk.TclError:
            s.theme_use('clam')

        CARD = self.CARD
        BG   = self.BG
        BORDER = self.BORDER
        TEXT = self.TEXT
        TEXT2 = self.TEXT2
        PRIMARY = self.PRIMARY

        s.configure('.', font=self.FONT_BODY, background=BG, foreground=TEXT)
        s.configure('TFrame', background=BG)
        s.configure('Card.TFrame', background=CARD)

        s.configure('TLabel', background=BG, foreground=TEXT)
        s.configure('Card.TLabel', background=CARD, foreground=TEXT)
        s.configure('Dim.TLabel', background=CARD, foreground=TEXT2, font=self.FONT_LABEL)
        s.configure('Section.TLabel', background=CARD, foreground=TEXT2,
                     font=self.FONT_SECTION)
        s.configure('TabActive.TLabel', foreground=PRIMARY, font=self.FONT_BODY_BD,
                     background=CARD)
        s.configure('TabInactive.TLabel', foreground=TEXT2, font=self.FONT_BODY,
                     background='#f8f9fa')

        s.configure('TCheckbutton', background=CARD, foreground=TEXT, font=self.FONT_BODY)
        s.map('TCheckbutton', background=[('active', CARD)])

        s.configure('TSpinbox', arrowsize=14)
        s.configure('TCombobox', arrowsize=14)
        s.map('TCombobox', fieldbackground=[('readonly', 'white')],
              selectbackground=[('readonly', 'white')],
              selectforeground=[('readonly', TEXT)])

        s.configure('Sidebar.TFrame', background='#1e293b')
        s.configure('Sidebar.TLabel', background='#1e293b', foreground='#e2e8f0',
                     font=self.FONT_BODY)
        s.configure('SidebarTitle.TLabel', background='#1e293b', foreground='#ffffff',
                     font=self.FONT_SUB)
        s.configure('SidebarDim.TLabel', background='#1e293b', foreground='#94a3b8',
                     font=self.FONT_LABEL)

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
        hdr.grid(row=0, column=0, sticky='ew', padx=self.PAD_LG, pady=(self.PAD_LG + 2, self.PAD_MD))

        tk.Label(hdr, text="RoK Alliance Bot", font=self.FONT_TITLE,
                 bg=self.SIDEBAR_BG, fg='#ffffff').pack(anchor='w')
        self._sidebar_sub = tk.Label(hdr, text="", font=self.FONT_LABEL,
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

        # footer - two rows so "Manage Instances" always has room to render
        # in full (it used to be squeezed onto the same row as Launch/Stop
        # All and got clipped to "lanag"). Row 1: Launch/Stop All as equal
        # halves. Row 2: Manage Instances, full width, secondary style.
        tk.Frame(sb, bg='#334155', height=1).grid(row=2, column=0, sticky='ew')

        footer = tk.Frame(sb, bg=self.SIDEBAR_BG)
        footer.grid(row=3, column=0, sticky='ew', padx=self.PAD_SM + 2, pady=self.PAD_SM + 2)
        footer.grid_columnconfigure(0, weight=1, uniform='footerbtn')
        footer.grid_columnconfigure(1, weight=1, uniform='footerbtn')

        tk.Button(footer, text="▶ Launch All", font=self.FONT_LABEL + ('bold',),
                  bg=self.STATUS_RUNNING, fg='white', activebackground='#16a34a', activeforeground='white',
                  relief='flat', bd=0, padx=self.PAD_XS, pady=self.PAD_XS, cursor='hand2',
                  command=self._launch_all).grid(row=0, column=0, sticky='ew', padx=(0, 3))

        tk.Button(footer, text="■ Stop All", font=self.FONT_LABEL + ('bold',),
                  bg=self.DANGER, fg='white', activebackground=self.DANGER_ACTIVE, activeforeground='white',
                  relief='flat', bd=0, padx=self.PAD_XS, pady=self.PAD_XS, cursor='hand2',
                  command=self._stop_all).grid(row=0, column=1, sticky='ew', padx=(3, 0))

        tk.Button(footer, text="⚙ Manage Instances", font=self.FONT_LABEL,
                  bg='#334155', fg='#cbd5e1', activebackground='#475569', activeforeground='white',
                  relief='flat', bd=0, padx=self.PAD_XS, pady=self.PAD_XS, cursor='hand2',
                  command=self._open_manager).grid(row=1, column=0, columnspan=2, sticky='ew', pady=(6, 0))

    # ── sidebar items ───────────────────────────────────────────

    def _load_sidebar(self):
        for w in self._sb_inner.winfo_children():
            w.destroy()

        instances = self.instance_manager.get_all_instances()
        running = self.launcher.get_running_instances()
        self._sidebar_sub.config(text=f"{len(instances)} instance{'s' if len(instances) != 1 else ''} · {len(running)} running")

        if not instances:
            self._sidebar_empty_state()

        for inst in instances:
            self._sidebar_item(inst, inst['id'] in running)

        self._sidebar_add_button()

        if not self.selected_instance_id and instances:
            self._select_instance(instances[0]['id'])

    def _sidebar_empty_state(self):
        tk.Label(self._sb_inner, text="No instances yet", font=self.FONT_LABEL,
                 bg=self.SIDEBAR_BG, fg=self.SIDEBAR_DIM
                 ).pack(pady=(self.PAD_LG, self.PAD_SM))

    def _sidebar_add_button(self):
        """A subtle dashed-outline '+ Add Instance' affordance under the
        instance list, discoverable without opening the Manage dialog first.
        Drawn on a Canvas since plain tk widgets can't do a dashed border."""
        h = 32
        c = tk.Canvas(self._sb_inner, bg=self.SIDEBAR_BG, height=h,
                      highlightthickness=0, bd=0, cursor='hand2')
        c.pack(fill='x', padx=self.PAD_SM + 2, pady=(self.PAD_XS, self.PAD_SM))

        def redraw(event=None):
            c.delete('all')
            w = c.winfo_width()
            if w < 10:
                return
            c.create_rectangle(1, 1, w - 2, h - 2, outline=self.SIDEBAR_DIM,
                                dash=(3, 2), width=1)
            c.create_text(w // 2, h // 2, text="＋ Add Instance",
                          fill=self.SIDEBAR_DIM, font=self.FONT_LABEL)

        c.bind('<Configure>', redraw)
        c.bind('<Button-1>', lambda e: self._open_manager())
        c.bind('<Enter>', lambda e: c.configure(bg=self.SIDEBAR_HOVER))
        c.bind('<Leave>', lambda e: c.configure(bg=self.SIDEBAR_BG))

    def _sidebar_item(self, inst, is_running):
        iid = inst['id']
        selected = iid == self.selected_instance_id
        bg = self.SIDEBAR_SELECTED if selected else self.SIDEBAR_BG

        try:
            is_scheduled = self.schedule_manager.is_enabled(iid)
        except Exception:
            is_scheduled = False

        frame = tk.Frame(self._sb_inner, bg=bg, cursor='hand2')
        frame.pack(fill='x', padx=6, pady=1)

        inner = tk.Frame(frame, bg=bg)
        inner.pack(fill='x', padx=self.PAD_SM + 2, pady=7)

        # dot
        status_text = self.instance_statuses.get(iid, '')
        is_error = 'error' in status_text.lower() or 'fail' in status_text.lower()
        dot_fg = self.STATUS_ERROR if is_error else (self.STATUS_RUNNING if is_running else self.STATUS_STOPPED)
        tk.Label(inner, text="●", font=self.FONT_DOT, bg=bg, fg=dot_fg
                 ).pack(side='left', padx=(0, self.PAD_SM))

        info = tk.Frame(inner, bg=bg)
        info.pack(side='left', fill='x', expand=True)

        name_fg = '#ffffff' if selected else self.SIDEBAR_TEXT
        tk.Label(info, text=inst['name'], font=(self.FONT_FAMILY, 10, 'bold' if selected else ''),
                 bg=bg, fg=name_fg, anchor='w').pack(anchor='w')

        sub = f"{inst.get('bluestacks_instance', '')} · :{inst.get('adb_port', '')}"
        tk.Label(info, text=sub, font=self.FONT_SMALL,
                 bg=bg, fg='#94a3b8' if not selected else '#c7d2fe', anchor='w').pack(anchor='w')

        progress = self._get_daily_progress(iid)
        pfg = '#a5b4fc' if selected else self.SIDEBAR_DIM
        tk.Label(inner, text=progress, font=self.FONT_LABEL, bg=bg, fg=pfg
                 ).pack(side='right')

        if is_scheduled:
            tk.Label(inner, text="⏱", font=self.FONT_LABEL, bg=bg, fg=self.STATUS_SCHEDULED
                     ).pack(side='right', padx=(0, self.PAD_SM - 2))

        # bind click on everything
        def click(e, i=iid):
            self._select_instance(i)
        for w in [frame, inner] + list(inner.winfo_children()) + list(info.winfo_children()):
            w.bind('<Button-1>', click)

        if not selected:
            def enter(e, f=frame, inn=inner, inf=info):
                for w in [f, inn, inf] + list(inn.winfo_children()) + list(inf.winfo_children()):
                    try: w.configure(bg=self.SIDEBAR_HOVER)
                    except tk.TclError: pass
            def leave(e, f=frame, inn=inner, inf=info):
                for w in [f, inn, inf] + list(inn.winfo_children()) + list(inf.winfo_children()):
                    try: w.configure(bg=self.SIDEBAR_BG)
                    except tk.TclError: pass
            frame.bind('<Enter>', enter)
            frame.bind('<Leave>', leave)

    # ── main area ───────────────────────────────────────────────

    def _build_main(self):
        main = tk.Frame(self.root, bg=self.BG)
        main.grid(row=0, column=1, sticky='nsew')
        main.grid_rowconfigure(2, weight=1)
        main.grid_columnconfigure(0, weight=1)

        # toolbar
        toolbar = tk.Frame(main, bg='white', height=52)
        toolbar.grid(row=0, column=0, sticky='ew')
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(1, weight=1)

        self._tb_title = tk.Label(toolbar, text="Select an instance",
                                   font=self.FONT_TITLE, bg='white', fg=self.TEXT)
        self._tb_title.grid(row=0, column=0, padx=(self.PAD_XL, 0), pady=13, sticky='w')

        status_wrap = tk.Frame(toolbar, bg='white')
        status_wrap.grid(row=0, column=1, padx=(self.PAD_SM, 0), sticky='w')

        # emulator (BlueStacks instance) name + ADB port of the selected
        # profile, same format as the sidebar rows.
        self._tb_sub = tk.Label(status_wrap, text="", font=self.FONT_BODY,
                                 bg='white', fg=self.TEXT2)
        self._tb_sub.pack(side='left', padx=(0, self.PAD_SM))

        # status badge: colored dot + label, replaces the old dim "· Idle"
        # text so running/error/scheduled states are readable at a glance.
        self._tb_badge_dot = tk.Label(status_wrap, text="●", font=self.FONT_DOT,
                                       bg='white', fg=self.STATUS_IDLE)
        self._tb_badge_dot.pack(side='left', padx=(0, 4))
        self._tb_badge_text = tk.Label(status_wrap, text="", font=self.FONT_BODY,
                                        bg='white', fg=self.STATUS_IDLE)
        self._tb_badge_text.pack(side='left')

        # transient "✓ Saved" indicator shown next to the status badge after
        # an autosave; fades out on its own (see _flash_saved).
        self._saved_lbl = tk.Label(status_wrap, text="", font=self.FONT_LABEL,
                                    bg='white', fg=self.STATUS_RUNNING)
        self._saved_lbl.pack(side='left', padx=(self.PAD_SM, 0))
        self._saved_after_id = None

        btn_frame = tk.Frame(toolbar, bg='white')
        btn_frame.grid(row=0, column=2, padx=(0, self.PAD_LG), sticky='e')

        self._launch_btn = tk.Button(
            btn_frame, text="▶ Launch", font=self.FONT_BODY_BD,
            bg=self.PRIMARY, fg='white', activebackground=self.PRIMARY_ACTIVE, activeforeground='white',
            disabledforeground=self.DISABLED_FG,
            relief='flat', bd=0, padx=14, pady=5, cursor='hand2',
            command=self._launch_selected)
        self._launch_btn.pack(side='left', padx=(0, self.PAD_SM - 2))

        self._stop_btn = tk.Button(
            btn_frame, text="■ Stop", font=self.FONT_BODY_BD,
            bg=self.DANGER, fg='white', activebackground=self.DANGER_ACTIVE, activeforeground='white',
            disabledforeground=self.DISABLED_FG,
            relief='flat', bd=0, padx=14, pady=5, cursor='hand2',
            command=self._stop_selected)
        self._stop_btn.pack(side='left')

        tk.Frame(main, bg='#e5e7eb', height=1).grid(row=0, column=0, sticky='sew')

        # tab bar
        tab_bar = tk.Frame(main, bg='#f8f9fa')
        tab_bar.grid(row=1, column=0, sticky='ew')

        self._current_tab = 'tasks'
        self._tab_btns = {}
        for name in ('Tasks', 'Config', 'Schedule', 'Logs'):
            key = name.lower()
            lbl = tk.Label(tab_bar, text=name, font=self.FONT_BODY,
                           bg='#f8f9fa', fg=self.STATUS_IDLE, padx=18, pady=self.PAD_SM, cursor='hand2')
            lbl.pack(side='left')
            lbl.bind('<Button-1>', lambda e, k=key: self._switch_tab(k))
            self._tab_btns[key] = lbl

        tk.Frame(main, bg='#e5e7eb', height=1).grid(row=1, column=0, sticky='sew')

        # content
        self._content = tk.Frame(main, bg=self.BG)
        self._content.grid(row=2, column=0, sticky='nsew')
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        self._tab_frames = {}
        self._build_tasks_tab()
        self._build_config_tab()
        self._build_schedule_tab()
        self._build_logs_tab()

        self._switch_tab('tasks')

    # ── tab switching ───────────────────────────────────────────

    def _switch_tab(self, key):
        self._current_tab = key
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.configure(fg=self.PRIMARY, font=self.FONT_BODY_BD, bg='white')
            else:
                btn.configure(fg=self.STATUS_IDLE, font=self.FONT_BODY, bg='#f8f9fa')

        for k, f in self._tab_frames.items():
            if k == key:
                f.grid(row=0, column=0, sticky='nsew')
            else:
                f.grid_forget()

        if key == 'logs':
            self._render_logs()
        elif key == 'schedule':
            self._refresh_schedule_status()

    # ── tasks tab ───────────────────────────────────────────────

    def _build_tasks_tab(self):
        outer = tk.Frame(self._content, bg=self.BG)
        self._tab_frames['tasks'] = outer
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg=self.BG, highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky='nsew')
        sb = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)

        inner = tk.Frame(canvas, bg=self.BG)
        cw = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(cw, width=e.width))
        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>',
            lambda ev: canvas.yview_scroll(int(-1*(ev.delta/120)), 'units')))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

        pad = tk.Frame(inner, bg=self.BG)
        pad.pack(fill='x', padx=self.PAD_XL, pady=self.PAD_LG)

        # ── card
        card = tk.Frame(pad, bg='white', highlightbackground=self.BORDER, highlightthickness=1)
        card.pack(fill='x')

        card_outer = tk.Frame(card, bg='white')
        card_outer.pack(fill='x', padx=self.PAD_LG, pady=self.PAD_MD)
        card_inner = self._capped(card_outer, 'white')

        # daily tasks
        tk.Label(card_inner, text="DAILY TASKS", font=self.FONT_SECTION,
                 bg='white', fg=self.TEXT2).pack(anchor='w', pady=(0, self.PAD_SM))

        self.build_var = tk.BooleanVar(value=True)
        self.build_row = self._task_row(card_inner, "1 Troop Build",
            "Join alliance building via bookmarked marker", self.build_var,
            command=self._autosave_tasks)

        self.expedition_var = tk.BooleanVar(value=True)
        self.expedition_row = self._task_row(card_inner, "Expedition Collection",
            "Collect expedition chest rewards", self.expedition_var,
            command=self._autosave_tasks)

        # separator
        tk.Frame(card_inner, bg='#f1f5f9', height=1).pack(fill='x', pady=self.PAD_SM)

        # recurring tasks
        tk.Label(card_inner, text="RECURRING TASKS", font=self.FONT_SECTION,
                 bg='white', fg=self.TEXT2).pack(anchor='w', pady=(0, self.PAD_SM))

        self.donation_var = tk.BooleanVar(value=True)
        self.donation_row = self._task_row(card_inner, "Tech Donation",
            "Donate to Officer's recommended technology", self.donation_var,
            command=self._autosave_tasks)

        # separator
        tk.Frame(card_inner, bg='#f1f5f9', height=1).pack(fill='x', pady=self.PAD_SM)

        # run options
        tk.Label(card_inner, text="RUN OPTIONS", font=self.FONT_SECTION,
                 bg='white', fg=self.TEXT2).pack(anchor='w', pady=(0, self.PAD_SM))

        opts = tk.Frame(card_inner, bg='white')
        opts.pack(fill='x')

        self.characters_var = tk.IntVar(value=10)
        self._opt_field(opts, "Characters", self.characters_var, 0,
                        spinbox=(1, 22), save_cb=self._autosave_tasks)

        self.march_var = tk.IntVar(value=1)
        self._opt_field(opts, "March Preset", self.march_var, 1,
                        spinbox=(1, 7), save_cb=self._autosave_tasks)

        self.version_var = tk.StringVar(value='Global')
        self._opt_field(opts, "Game Version", self.version_var, 2,
                        combo=['Global', 'Gamota', 'KR'], save_cb=self._autosave_tasks)

        # separator
        tk.Frame(card_inner, bg='#f1f5f9', height=1).pack(fill='x', pady=self.PAD_SM)

        # account rotation
        tk.Label(card_inner, text="ACCOUNT ROTATION (OPTIONAL)", font=self.FONT_SECTION,
                 bg='white', fg=self.TEXT2).pack(anchor='w', pady=(0, self.PAD_XS))

        tk.Label(card_inner,
                 text="One account per line as email:password. The bot logs into each account in\n"
                      "turn and runs all tasks for every one. Leave empty to use the current login only.",
                 font=self.FONT_LABEL, bg='white', fg=self.TEXT2, justify='left'
                 ).pack(anchor='w', pady=(0, self.PAD_XS))

        accounts_wrap = tk.Frame(card_inner, bg='white', highlightbackground='#e2e8f0',
                                 highlightthickness=1)
        accounts_wrap.pack(fill='x', pady=(0, self.PAD_XS))

        self.accounts_text = tk.Text(accounts_wrap, height=4, font=self.FONT_MONO,
                                     relief='flat', bd=0, padx=self.PAD_SM, pady=self.PAD_XS,
                                     bg='#f8fafc', fg=self.TEXT, insertbackground=self.TEXT,
                                     wrap='none', undo=True)
        self.accounts_text.pack(fill='x')
        self.accounts_text.bind('<FocusOut>', lambda e: self._autosave_tasks())

        self._accounts_status = tk.Label(card_inner, text="Account rotation disabled",
                                         font=self.FONT_LABEL, bg='white', fg=self.TEXT2)
        self._accounts_status.pack(anchor='w')

    def _task_row(self, parent, title, desc, var, command=None):
        row = tk.Frame(parent, bg='#f8fafc', highlightbackground='#e2e8f0', highlightthickness=1)
        row.pack(fill='x', pady=(0, self.PAD_XS))

        inner = tk.Frame(row, bg='#f8fafc')
        inner.pack(fill='x', padx=self.PAD_MD, pady=self.PAD_SM)

        cb = ttk.Checkbutton(inner, variable=var, command=command)
        cb.configure(style='TCheckbutton')
        cb.pack(side='left', padx=(0, self.PAD_SM + 2))
        # override checkbutton bg to match row
        ttk.Style().configure('TCheckbutton', background='#f8fafc')

        info = tk.Frame(inner, bg='#f8fafc')
        info.pack(side='left', fill='x', expand=True)
        tk.Label(info, text=title, font=self.FONT_ROW, bg='#f8fafc', fg=self.TEXT
                 ).pack(anchor='w')
        tk.Label(info, text=desc, font=self.FONT_LABEL, bg='#f8fafc', fg=self.TEXT2
                 ).pack(anchor='w')

        status_lbl = tk.Label(inner, text="", font=self.FONT_BODY_BD,
                              bg='#f8fafc', fg=self.TEXT2)
        status_lbl.pack(side='right', padx=(self.PAD_SM, 0))

        row._status = status_lbl
        return row

    def _opt_field(self, parent, label, var, col, spinbox=None, combo=None, save_cb=None):
        frame = tk.Frame(parent, bg='white')
        frame.grid(row=0, column=col, sticky='w', padx=(0, self.PAD_XL))

        tk.Label(frame, text=label, font=self.FONT_LABEL, bg='white', fg='#64748b'
                 ).pack(anchor='w')

        if spinbox:
            lo, hi = spinbox
            sp = ttk.Spinbox(frame, from_=lo, to=hi, textvariable=var,
                              width=self.FIELD_W_NUM, command=save_cb)
            sp.pack(anchor='w', pady=(3, 0))
            if save_cb:
                sp.bind('<Return>', lambda e: save_cb())
                sp.bind('<FocusOut>', lambda e: save_cb())
        elif combo:
            cb = ttk.Combobox(frame, textvariable=var, values=combo, state='readonly',
                              width=self.FIELD_W_SHORT + 2)
            cb.pack(anchor='w', pady=(3, 0))
            if save_cb:
                cb.bind('<<ComboboxSelected>>', lambda e: save_cb())

    # ── config tab ──────────────────────────────────────────────

    def _build_config_tab(self):
        outer = tk.Frame(self._content, bg=self.BG)
        self._tab_frames['config'] = outer
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg=self.BG, highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky='nsew')
        sb = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)

        inner = tk.Frame(canvas, bg=self.BG)
        cw = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(cw, width=e.width))
        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>',
            lambda ev: canvas.yview_scroll(int(-1*(ev.delta/120)), 'units')))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

        pad = tk.Frame(inner, bg=self.BG)
        pad.pack(fill='x', padx=self.PAD_XL, pady=self.PAD_LG)

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
        self._cfg_row(grid, "BlueStacks Instance", self.bs_instance_var, 0,
                      width=self.FIELD_W_MED, save_cb=self._autosave_config)

        self.adb_port_var = tk.StringVar()
        self._cfg_row(grid, "ADB Port", self.adb_port_var, 1,
                      width=self.FIELD_W_SHORT, save_cb=self._autosave_config)

        self.startup_wait_var = tk.IntVar(value=20)
        self._cfg_row(grid, "Startup Wait (sec)", self.startup_wait_var, 2,
                      spinbox=(5, 60, 5), save_cb=self._autosave_config)

        # ── options card
        card3 = self._card(pad, "OPTIONS")

        ttk.Checkbutton(card3, text="Auto-exit BlueStacks after done",
                         variable=self.auto_exit_var,
                         command=self._on_auto_exit).pack(anchor='w', pady=2)
        ttk.Checkbutton(card3, text="Force daily tasks (run even if completed today)",
                         variable=self.force_daily_var,
                         command=self._autosave_config).pack(anchor='w', pady=2)

        # ── actions (only Reset Daily Tasks remains a button - everything
        # else on this tab autosaves; see _autosave_config)
        actions = tk.Frame(pad, bg=self.BG)
        actions.pack(fill='x', pady=(self.PAD_SM, 0))

        tk.Button(actions, text="Reset Daily Tasks", font=self.FONT_BODY,
                  bg='#f59e0b', fg='white', activebackground='#d97706', activeforeground='white',
                  relief='flat', bd=0, padx=14, pady=5, cursor='hand2',
                  command=self._reset_daily).pack(side='left')

    def _capped(self, parent, bg, maxwidth=None):
        """Wrap children in a column that never grows wider than `maxwidth`
        px; any extra horizontal space in `parent` is left as plain
        background instead of stretching fields edge-to-edge. Height still
        auto-fits its content: an inner frame forwards its own height onto
        the fixed-width shell via <Configure>, so callers just pack/grid
        into the returned frame like any other container."""
        maxwidth = maxwidth or self.CONTENT_MAX_WIDTH
        shell = tk.Frame(parent, bg=bg)
        shell.pack(fill='x')
        fixed = tk.Frame(shell, bg=bg, width=maxwidth)
        fixed.pack(side='left', fill='y')
        fixed.pack_propagate(False)
        content = tk.Frame(fixed, bg=bg)
        # fill='x' only: the content's height must come from its own children
        # (its requested height), not from the fixed shell - with fill='both'
        # the two heights depend on each other and collapse to ~0.
        content.pack(side='top', fill='x')

        def _sync_height(_event=None):
            h = content.winfo_reqheight()
            if h > 1 and fixed.winfo_reqheight() != h:
                fixed.configure(height=h)

        content.bind('<Configure>', _sync_height)
        return content

    def _card(self, parent, title):
        wrapper = tk.Frame(parent, bg='white', highlightbackground=self.BORDER,
                           highlightthickness=1)
        wrapper.pack(fill='x', pady=(0, self.PAD_SM))
        outer = tk.Frame(wrapper, bg='white')
        outer.pack(fill='x', padx=self.PAD_LG, pady=self.PAD_MD)
        inner = self._capped(outer, 'white')
        tk.Label(inner, text=title, font=self.FONT_SECTION, bg='white', fg=self.TEXT2
                 ).pack(anchor='w', pady=(0, self.PAD_SM))
        return inner

    def _path_row(self, parent, label, var, browse_cmd, scan_cmd):
        tk.Label(parent, text=label, font=self.FONT_LABEL, bg='white', fg='#64748b'
                 ).pack(anchor='w', pady=(0, 2))

        row = tk.Frame(parent, bg='white')
        row.pack(fill='x', pady=(0, self.PAD_SM))

        entry = ttk.Entry(row, textvariable=var, width=self.FIELD_W_LONG)
        entry.pack(side='left', fill='x', expand=True)
        entry.bind('<Return>', lambda e: self._autosave_config())
        entry.bind('<FocusOut>', lambda e: self._autosave_config())

        tk.Button(row, text="Browse", font=self.FONT_LABEL,
                  bg='#e5e7eb', fg='#374151', activebackground='#d1d5db',
                  relief='flat', bd=0, padx=self.PAD_SM, pady=2, cursor='hand2',
                  command=browse_cmd).pack(side='left', padx=(6, 0))
        tk.Button(row, text="Scan", font=self.FONT_LABEL,
                  bg='#e5e7eb', fg='#374151', activebackground='#d1d5db',
                  relief='flat', bd=0, padx=self.PAD_SM, pady=2, cursor='hand2',
                  command=scan_cmd).pack(side='left', padx=(4, 0))

    def _cfg_row(self, parent, label, var, row, width=None, spinbox=None, save_cb=None):
        width = width or self.FIELD_W_MED
        tk.Label(parent, text=label, font=self.FONT_BODY, bg='white', fg='#374151'
                 ).grid(row=row, column=0, sticky='w', pady=5)

        if spinbox:
            lo, hi, step = spinbox
            sp = ttk.Spinbox(parent, from_=lo, to=hi, increment=step,
                        textvariable=var, width=self.FIELD_W_NUM, command=save_cb)
            sp.grid(row=row, column=1, sticky='w', padx=(self.PAD_MD, 0), pady=5)
            if save_cb:
                sp.bind('<Return>', lambda e: save_cb())
                sp.bind('<FocusOut>', lambda e: save_cb())
        else:
            entry = ttk.Entry(parent, textvariable=var, width=width)
            entry.grid(row=row, column=1, sticky='w', padx=(self.PAD_MD, 0), pady=5)
            if save_cb:
                entry.bind('<Return>', lambda e: save_cb())
                entry.bind('<FocusOut>', lambda e: save_cb())

    # ── schedule tab ────────────────────────────────────────────

    def _build_schedule_tab(self):
        outer = tk.Frame(self._content, bg=self.BG)
        self._tab_frames['schedule'] = outer
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg=self.BG, highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky='nsew')
        sb = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)

        inner = tk.Frame(canvas, bg=self.BG)
        cw = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(cw, width=e.width))
        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>',
            lambda ev: canvas.yview_scroll(int(-1*(ev.delta/120)), 'units')))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

        pad = tk.Frame(inner, bg=self.BG)
        pad.pack(fill='x', padx=self.PAD_XL, pady=self.PAD_LG)

        # ── auto-schedule card
        card1 = self._card(pad, "AUTO-SCHEDULE")

        self.schedule_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(card1, text="Enable automatic scheduled runs",
                         variable=self.schedule_enabled_var,
                         command=self._on_schedule_toggle).pack(anchor='w', pady=(0, self.PAD_SM))

        interval_row = tk.Frame(card1, bg='white')
        interval_row.pack(anchor='w', fill='x', pady=(self.PAD_XS, 0))

        tk.Label(interval_row, text="Run every", font=self.FONT_BODY, bg='white', fg='#374151'
                 ).pack(side='left')

        self.schedule_interval_var = tk.IntVar(value=ScheduleManager.DEFAULT_INTERVAL_HOURS)
        interval_spin = ttk.Spinbox(interval_row, from_=1, to=48, width=6,
                                     textvariable=self.schedule_interval_var,
                                     command=self._on_schedule_interval_change)
        interval_spin.pack(side='left', padx=(self.PAD_SM, self.PAD_XS))
        interval_spin.bind('<Return>', lambda e: self._on_schedule_interval_change())
        interval_spin.bind('<FocusOut>', lambda e: self._on_schedule_interval_change())

        tk.Label(interval_row, text="hours (1-48)", font=self.FONT_BODY, bg='white', fg='#374151'
                 ).pack(side='left')

        # ── status card (Run Now lives here now, right-aligned within the
        # card itself instead of floating in its own row below - the tab
        # was sparse enough that a separate action block read as an
        # afterthought)
        card2 = self._card(pad, "STATUS")

        self.sched_last_var = tk.StringVar(value="Never")
        self.sched_next_var = tk.StringVar(value="Not scheduled")
        self.sched_remaining_var = tk.StringVar(value="Not scheduled")

        self._status_line(card2, "Last run", self.sched_last_var)
        self._status_line(card2, "Next run", self.sched_next_var)
        self._status_line(card2, "Time remaining", self.sched_remaining_var)

        tk.Frame(card2, bg='#f1f5f9', height=1).pack(fill='x', pady=self.PAD_SM)

        run_now_row = tk.Frame(card2, bg='white')
        run_now_row.pack(fill='x')

        self._run_now_btn = tk.Button(
            run_now_row, text="Run Now", font=self.FONT_BODY_BD,
            bg=self.PRIMARY, fg='white', activebackground=self.PRIMARY_ACTIVE, activeforeground='white',
            relief='flat', bd=0, padx=self.PAD_XL, pady=self.PAD_SM - 2, cursor='hand2',
            command=self._on_schedule_run_now)
        self._run_now_btn.pack(side='right')

        tk.Label(card2, text="Run Now launches this instance immediately and resets its schedule.",
                 font=self.FONT_LABEL, bg='white', fg=self.TEXT2, anchor='e', justify='right'
                 ).pack(fill='x', pady=(self.PAD_XS, 0))

    def _status_line(self, parent, label, var):
        row = tk.Frame(parent, bg='white')
        row.pack(fill='x', pady=(0, self.PAD_XS))
        tk.Label(row, text=label, font=self.FONT_BODY, bg='white', fg=self.TEXT2,
                 width=15, anchor='w').pack(side='left')
        tk.Label(row, textvariable=var, font=self.FONT_BODY_BD, bg='white', fg=self.TEXT
                 ).pack(side='left')

    # ── logs tab ────────────────────────────────────────────────

    def _build_logs_tab(self):
        outer = tk.Frame(self._content, bg=self.BG)
        self._tab_frames['logs'] = outer
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        wrapper = tk.Frame(outer, bg='white', highlightbackground=self.BORDER,
                           highlightthickness=1)
        wrapper.grid(row=0, column=0, sticky='nsew', padx=self.PAD_XL, pady=self.PAD_LG)
        wrapper.grid_rowconfigure(1, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        # header
        hdr = tk.Frame(wrapper, bg='white')
        hdr.grid(row=0, column=0, sticky='ew', padx=self.PAD_LG, pady=(self.PAD_MD, 0))

        tk.Label(hdr, text="AUTOMATION LOGS", font=self.FONT_SECTION,
                 bg='white', fg=self.TEXT2).pack(side='left')

        tk.Button(hdr, text="Clear", font=self.FONT_LABEL,
                  bg='#e5e7eb', fg='#374151', activebackground='#d1d5db',
                  relief='flat', bd=0, padx=self.PAD_SM, pady=2, cursor='hand2',
                  command=self._clear_logs).pack(side='right')

        # text
        log_frame = tk.Frame(wrapper, bg='#0f172a')
        log_frame.grid(row=1, column=0, sticky='nsew', padx=self.PAD_MD, pady=self.PAD_MD)
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self._log_text = tk.Text(
            log_frame, wrap='word', font=self.FONT_MONO,
            bg='#0f172a', fg='#cbd5e1', insertbackground='white',
            selectbackground='#334155', relief='flat', padx=self.PAD_MD, pady=self.PAD_SM + 2,
            spacing1=1, spacing3=1)
        self._log_text.grid(row=0, column=0, sticky='nsew')

        # A plain tk.Scrollbar (not ttk) so it can be fully recolored to
        # match the dark log panel - the native/ttk-themed scrollbar used
        # elsewhere renders light gray and clashes here.
        scrollbar = tk.Scrollbar(
            log_frame, orient='vertical', command=self._log_text.yview,
            bg='#334155', troughcolor='#0f172a', activebackground='#475569',
            highlightthickness=0, bd=0, width=10, elementborderwidth=0)
        self._log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky='ns')

        self._log_text.tag_configure('ts', foreground='#475569', font=(self.FONT_MONO[0], 9))
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
        self._tb_sub.config(
            text=f"{inst.get('bluestacks_instance', '')} · :{inst.get('adb_port', '')}")
        color, text = self._status_badge_for(instance_id, is_running, status)
        self._set_status_badge(color, text)
        self._update_toolbar_buttons(is_running)

        self._load_instance_ui(instance_id)
        self._load_sidebar()

        if self._current_tab == 'logs':
            self._render_logs()
        elif self._current_tab == 'schedule':
            self._refresh_schedule_status(instance_id)

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

        accounts_raw = cm.get_config('Accounts', 'accounts', '') or ''
        self.accounts_text.delete('1.0', 'end')
        if accounts_raw.strip():
            lines = [e.strip() for e in accounts_raw.split(',') if e.strip()]
            self.accounts_text.insert('1.0', '\n'.join(lines))
        self._update_accounts_status()

        self.bs_path_var.set(cm.get_config('BlueStacks', 'bluestacks_exe_path', ''))
        self.adb_path_var.set(cm.get_config('BlueStacks', 'adb_path', ''))
        self.bs_instance_var.set(cm.get_config('BlueStacks', 'bluestacks_instance_name', ''))
        self.adb_port_var.set(cm.get_config('BlueStacks', 'adb_port', '5555'))
        self.startup_wait_var.set(cm.get_int('BlueStacks', 'wait_for_startup_seconds', 20))

        self._update_task_status(iid)
        self._load_schedule_ui(iid)

    def _update_task_status(self, iid):
        cm = self.instance_manager.get_config_manager(iid)
        if not cm:
            return

        num = cm.get_int('RiseOfKingdoms', 'num_of_characters', 1)
        path = get_tracker_path_for_instance(self.instance_manager.instances_dir, iid)

        if not os.path.exists(path):
            for r in (self.build_row, self.expedition_row):
                r._status.config(text=f"0/{num}", fg=self.STATUS_IDLE)
            self.donation_row._status.config(text="every cycle", fg=self.STATUS_IDLE)
            return

        tracker = DailyTaskTracker(path)
        st = tracker.get_completion_status()
        today = st['today_utc']

        for key, row in [('build', self.build_row), ('expedition', self.expedition_row)]:
            done = sum(1 for ci in range(num)
                       if st['characters'].get(str(ci), {}).get(key) == today)
            color = self.STATUS_RUNNING if done == num else self.STATUS_STOPPED
            row._status.config(text=f"{done}/{num}", fg=color)

        self.donation_row._status.config(text="every cycle", fg=self.STATUS_IDLE)

    # ── schedule tab logic ──────────────────────────────────────

    def _load_schedule_ui(self, iid):
        """(Re)load the Schedule tab's fields for the given instance. Called on
        instance selection so switching instances always reflects that
        instance's own schedule, not whatever was last shown."""
        if not hasattr(self, 'schedule_enabled_var'):
            return
        schedule = self.schedule_manager.get_schedule(iid)
        self.schedule_enabled_var.set(schedule.get('enabled', False))
        self.schedule_interval_var.set(
            schedule.get('interval_hours', ScheduleManager.DEFAULT_INTERVAL_HOURS))
        self._refresh_schedule_status(iid)

    def _refresh_schedule_status(self, iid=None):
        """Refresh the read-only last/next/remaining labels. Safe to call from
        the status-poll tick (via root.after) or directly from the main
        thread (tab switch, instance selection, after an action)."""
        if self.is_closing or not hasattr(self, 'sched_last_var'):
            return
        iid = iid or self.selected_instance_id
        if not iid:
            return
        try:
            self.sched_last_var.set(self.schedule_manager.format_last_run_datetime(iid))
            self.sched_next_var.set(self.schedule_manager.format_next_run_datetime(iid))
            self.sched_remaining_var.set(self.schedule_manager.format_time_remaining(iid))
        except tk.TclError:
            pass

    def _on_schedule_toggle(self):
        iid = self.selected_instance_id
        if not iid:
            return
        self.schedule_manager.enable_schedule(iid, self.schedule_enabled_var.get())
        self._refresh_schedule_status(iid)
        self._load_sidebar()
        if not self.launcher.is_instance_running(iid):
            color, text = self._status_badge_for(iid, False, '')
            self._set_status_badge(color, text)

    def _on_schedule_interval_change(self):
        iid = self.selected_instance_id
        if not iid:
            return
        try:
            hours = int(self.schedule_interval_var.get())
        except (tk.TclError, ValueError):
            return
        hours = max(1, min(48, hours))
        self.schedule_interval_var.set(hours)
        self.schedule_manager.set_interval(iid, hours)
        self._refresh_schedule_status(iid)

    def _on_schedule_run_now(self):
        iid = self.selected_instance_id
        if not iid:
            return
        if self.launcher.is_instance_running(iid):
            messagebox.showinfo("Running", "This instance is already running.")
            return
        if not self.schedule_enabled_var.get():
            # trigger_immediate_run() is a no-op on a disabled schedule; arm it
            # first so it has something to reset, keeping schedule state
            # consistent with what Run Now is about to do.
            self.schedule_manager.enable_schedule(iid, True)
            self.schedule_enabled_var.set(True)
        self.schedule_manager.trigger_immediate_run(iid)
        self._save_tasks(silent=True)
        if self._launch_instance_now(iid):
            # Same "mark complete at launch-start" rule as the automatic
            # scheduler (see _launch_scheduled) so Run Now also pushes
            # next_run into the future instead of leaving it "due".
            self.schedule_manager.mark_run_complete(iid)
            self._on_instance_log(iid, "Manual 'Run Now' triggered from Schedule tab")
            self._refresh_schedule_status(iid)
            self._select_instance(iid)

    # ── actions ─────────────────────────────────────────────────

    def _launch_instance_now(self, iid, force_daily=None):
        """Single shared launch path: dispatches automation for `iid` via the
        launcher. Used by the manual Launch button, Run Now, Launch All, and
        the automatic scheduler so there is exactly one place that calls
        launcher.launch_instance().

        Only touches the launcher and the plain instance_statuses dict (both
        already safe to mutate off the main thread in the existing code) -
        any Tkinter widget update must be done by the caller.
        """
        if not iid or self.launcher.is_instance_running(iid):
            return False
        force = self.force_daily_var.get() if force_daily is None else force_daily
        if self.launcher.launch_instance(iid, force_daily_tasks=force):
            self.instance_statuses[iid] = 'Starting'
            return True
        return False

    def _launch_selected(self):
        iid = self.selected_instance_id
        if not iid:
            return
        if self.launcher.is_instance_running(iid):
            messagebox.showinfo("Running", "This instance is already running.")
            return
        self._save_tasks(silent=True)
        if self._launch_instance_now(iid):
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
        # Read the Tk variable on the main thread; the worker below must not
        # touch Tk state.
        force = self.force_daily_var.get()

        def do():
            for i, inst in enumerate(to_launch):
                self._launch_instance_now(inst['id'], force_daily=force)
                if i < len(to_launch) - 1:
                    time.sleep(timings.LAUNCH_STAGGER_WAIT)
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
        self._autosave_config()

    # ── save ────────────────────────────────────────────────────
    #
    # One save model: there is no explicit "Save" button on Tasks or Config
    # anymore. Checkbox/combobox changes save immediately (ttk `command=` /
    # <<ComboboxSelected>>); entries and spinboxes save on <FocusOut> and
    # <Return> (see _task_row/_opt_field/_path_row/_cfg_row). Both autosave
    # wrappers below reuse the existing silent _save_tasks/_save_config and
    # just add the "✓ Saved" header flash. Launch/Run Now still call
    # _save_tasks(silent=True) directly beforehand, unchanged.

    ROK_PACKAGES = {
        'Global': 'com.lilithgame.roc.gp',
        'Gamota': 'com.rok.gp.vn',
        'KR': 'com.lilithgames.rok.gpkr',
    }

    def _autosave_tasks(self):
        self._save_tasks(silent=True)
        self._flash_saved()

    def _autosave_config(self):
        self._save_config(silent=True)
        self._flash_saved()

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
        if 'Accounts' not in c:
            c['Accounts'] = {}
        c['Accounts']['accounts'] = ', '.join(self._get_account_lines())
        self._update_accounts_status()
        with open(cm.config_path, 'w') as f:
            c.write(f)
        self._update_task_status(iid)
        if not silent:
            messagebox.showinfo("Saved", "Task settings saved.")

    def _save_config(self, silent=False):
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
        self._tb_sub.config(
            text=f"{self.bs_instance_var.get()} · :{self.adb_port_var.get()}")
        self._save_tasks(silent=True)
        self._load_sidebar()
        if not silent:
            messagebox.showinfo("Saved", "Configuration saved.")

    # ── account rotation helpers ────────────────────────────────

    def _get_account_lines(self):
        """Read the accounts Text widget as a cleaned list of non-empty lines."""
        if not hasattr(self, 'accounts_text'):
            return []
        raw = self.accounts_text.get('1.0', 'end')
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _update_accounts_status(self):
        """Reflect how many valid/invalid account entries are configured."""
        if not hasattr(self, '_accounts_status'):
            return
        lines = self._get_account_lines()
        valid = [l for l in lines if ':' in l and l.split(':', 1)[0].strip()
                 and l.split(':', 1)[1].strip()]
        invalid = len(lines) - len(valid)
        if not lines:
            self._accounts_status.config(text="Account rotation disabled", fg=self.TEXT2)
        elif invalid:
            self._accounts_status.config(
                text=f"{len(valid)} account(s) configured · {invalid} invalid line(s) "
                     "(expected email:password)",
                fg=self.STATUS_ERROR)
        else:
            self._accounts_status.config(
                text=f"Account rotation enabled: {len(valid)} account(s)",
                fg=self.STATUS_RUNNING)

    # ── browse / scan ───────────────────────────────────────────

    def _browse_bs(self):
        p = filedialog.askopenfilename(title="Select BlueStacks",
            filetypes=[("Executable", "*.exe"), ("All", "*.*")])
        if p:
            self.bs_path_var.set(p)
            self._autosave_config()

    def _browse_adb(self):
        p = filedialog.askopenfilename(title="Select ADB",
            filetypes=[("Executable", "*.exe"), ("All", "*.*")])
        if p:
            self.adb_path_var.set(p)
            self._autosave_config()

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
        self._autosave_config()
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
        self._autosave_config()
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
            self.root.after(0, self._append_log_line, instance_id, ts, message, tag)

    def _append_log_line(self, instance_id, ts, message, tag):
        # Guard against the callback firing after the window/widget is gone,
        # or after the selection/tab changed while this was queued.
        if self.is_closing:
            return
        if self.selected_instance_id != instance_id or self._current_tab != 'logs':
            return
        try:
            self._log_text.insert('end', f"[{ts}] ", 'ts')
            self._log_text.insert('end', f"{message}\n", tag)
            self._log_text.see('end')
        except tk.TclError:
            pass

    def _on_instance_status(self, instance_id, status):
        self.instance_statuses[instance_id] = status
        self.root.after(0, self._load_sidebar)
        if self.selected_instance_id == instance_id:
            is_running = self.launcher.is_instance_running(instance_id)
            color, text = self._status_badge_for(instance_id, is_running, status)
            self.root.after(0, lambda c=color, t=text: self._set_status_badge(c, t))
            if not is_running:
                self.root.after(0, lambda: self._update_task_status(instance_id))
            self.root.after(0, lambda: self._update_toolbar_buttons(is_running))

    # ── status badge ─────────────────────────────────────────────

    def _status_badge_for(self, iid, is_running, status_text):
        """Maps run/schedule state to a (color, text) pair for the header
        badge: gray Idle, green Running, red Error, or amber "⏱ Scheduled"
        for an idle instance with auto-scheduling enabled - so the badge
        communicates more than a single flat "Idle"."""
        if is_running:
            ml = (status_text or '').lower()
            if 'error' in ml or 'fail' in ml:
                return (self.STATUS_ERROR, status_text or 'Error')
            return (self.STATUS_RUNNING, status_text or 'Running')
        try:
            if self.schedule_manager.is_enabled(iid):
                return (self.STATUS_SCHEDULED, '⏱ Scheduled')
        except Exception:
            pass
        return (self.STATUS_IDLE, 'Idle')

    def _set_status_badge(self, color, text):
        if self.is_closing:
            return
        try:
            self._tb_badge_dot.config(fg=color)
            self._tb_badge_text.config(text=text, fg=color)
        except tk.TclError:
            pass

    # ── autosave feedback ────────────────────────────────────────

    def _flash_saved(self):
        """Show '✓ Saved' next to the status badge for ~1.5s. Reschedules
        (rather than stacking) the hide timer so rapid-fire autosaves (e.g.
        typing then blurring several fields) don't cause it to flicker."""
        if self.is_closing:
            return
        try:
            self._saved_lbl.config(text="✓ Saved")
            if self._saved_after_id is not None:
                self.root.after_cancel(self._saved_after_id)
            self._saved_after_id = self.root.after(1500, self._hide_saved_indicator)
        except tk.TclError:
            pass

    def _hide_saved_indicator(self):
        self._saved_after_id = None
        if self.is_closing:
            return
        try:
            self._saved_lbl.config(text="")
        except tk.TclError:
            pass

    # ── toolbar button state ────────────────────────────────────

    def _update_toolbar_buttons(self, is_running):
        """Launch/Stop visually reflect the current run state: whichever
        action isn't available right now is disabled and dimmed, so the
        primary action (Launch, indigo) vs. the destructive one (Stop, red)
        is never ambiguous."""
        if self.is_closing:
            return
        try:
            if is_running:
                self._launch_btn.configure(state='disabled', bg=self.DISABLED_BG,
                                            fg=self.DISABLED_FG, cursor='arrow')
                self._stop_btn.configure(state='normal', bg=self.DANGER,
                                          fg='white', cursor='hand2')
            else:
                self._launch_btn.configure(state='normal', bg=self.PRIMARY,
                                            fg='white', cursor='hand2')
                self._stop_btn.configure(state='disabled', bg=self.DISABLED_BG,
                                          fg=self.DISABLED_FG, cursor='arrow')
        except tk.TclError:
            pass

    # ── status poll ─────────────────────────────────────────────

    def _status_poll(self):
        while not self.is_closing:
            try:
                self.root.after(0, self._load_sidebar)
            except Exception:
                self.logger.exception("Status poll failed")
            try:
                self._check_schedules()
            except Exception:
                self.logger.exception("Schedule check failed")
            try:
                self.root.after(0, self._refresh_schedule_status)
            except Exception:
                self.logger.exception("Schedule status refresh failed")
            time.sleep(3)

    # ── scheduler engine ────────────────────────────────────────

    def _check_schedules(self):
        """Runs on the background poll thread once per tick. For every
        instance whose schedule is enabled and due, and which isn't already
        running, dispatch a launch on the main thread. Never raises -
        anything unexpected here is logged, not propagated, so a single bad
        instance config can't kill the poll loop."""
        if self.is_closing:
            return
        try:
            instances = self.instance_manager.get_all_instances()
        except Exception:
            self.logger.exception("Schedule check: failed to list instances")
            return

        for inst in instances:
            iid = inst.get('id')
            if not iid:
                continue
            try:
                if not self.schedule_manager.is_enabled(iid):
                    continue
                if not self.schedule_manager.is_due(iid):
                    continue
                if self.launcher.is_instance_running(iid):
                    continue
                self.root.after(0, self._launch_scheduled, iid)
            except Exception:
                self.logger.exception(f"Schedule check failed for instance {iid}")

    def _launch_scheduled(self, iid):
        """Main-thread dispatch for an auto-scheduled launch. Re-checks
        is_closing/is_instance_running here (not just in _check_schedules)
        to close the race between the background check and this callback
        actually running.

        mark_run_complete() is called *before* launching rather than when
        the automation finishes. is_due() only looks at next_run_utc, so if
        we waited until completion, every poll tick between "became due" and
        "finished running" would still see is_due()==True; the
        is_instance_running guard would happen to block a double-launch
        during that window, but marking complete at launch-start makes the
        loop-safety explicit (next_run_utc is pushed into the future
        immediately) instead of relying on that timing coincidence.
        """
        if self.is_closing:
            return
        if self.launcher.is_instance_running(iid):
            return

        inst = self.instance_manager.get_instance(iid)
        name = inst['name'] if inst else iid

        self.schedule_manager.mark_run_complete(iid)
        self._on_instance_log(iid, f"Scheduled run starting for '{name}' (interval reached)")

        if self._launch_instance_now(iid):
            self._load_sidebar()
            if self.selected_instance_id == iid:
                self._refresh_schedule_status(iid)

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
            self.is_closing = True
            self.root.after(500, self._finish_closing)
            return
        self.is_closing = True
        self._finish_closing()

    def _finish_closing(self):
        self.launcher.shutdown()
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    app = UnifiedGUI(root)
    root.mainloop()

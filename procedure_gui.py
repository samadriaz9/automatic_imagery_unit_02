#!/usr/bin/env python3
"""
Automation procedure GUI — fullscreen, six steps, incubation + imagery settings.

Run: python procedure_gui.py
Escape toggles fullscreen.
"""

import math
import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

from device_config import (
    DEFAULT_ROUND_ENABLED,
    DEFAULT_ROUND_TEMPS,
    DEFAULT_ROUND_TIMES_MIN,
    INCUBATION_HOUR_STEP,
    INCUBATION_MIN_MAX,
    INCUBATION_MIN_MIN,
    INCUBATION_MIN_STEP,
    INCUBATION_TEMP_MAX,
    INCUBATION_TEMP_MIN,
    INCUBATION_TEMP_STEP,
    MAX_PETRI_DISHES,
    NUM_STUDY_ROUNDS,
    STEP_INCUBATION_MINUTES,
    STEP_INCUBATION_TEMP_C,
)
from incubation_module import Start_incubation
from workflow_steps import (
    capture_petri_dishes,
    run_incubation_imaging_study,
    step_01_all_home,
    step_02_insert_petri_dishes,
    step_03_shift_for_incubation,
    step_05_post_imaging_cleanup,
    step_05_prepare_imaging,
    step_06_sterilize,
)

try:
    from main import shutdown_all
except ImportError:
    def shutdown_all():
        pass


BG = "#1a1f2e"
PANEL = "#252b3d"
CARD = "#2f3649"
ACCENT = "#5b9bd5"
ACCENT2 = "#7ec8a4"
ACCENT3 = "#c9a55c"
SELECTED = "#3d6ea8"
ROUND_ACTIVE = "#2ecc71"
ROUND_ENABLED = "#1a5c3a"
STUDY_BTN_COLOR = "#8e44ad"
STUDY_BTN_HOVER = "#a569bd"
TEXT = "#eef2f8"
TEXT_ON_COLOR = "#ffffff"
STUDY_BTN_TITLE = "Incubation and Imaging"
MUTED = "#9aa5b8"
WARN = "#e8a87c"
CLOSE_BTN = "#b85450"
BTN_FONT = ("Segoe UI", 11, "bold")
LEFT_BTN_FONT = ("Segoe UI", int(round(11 * 1.5)), "bold")
ADJ_FONT = ("Segoe UI", 10, "bold")
PRESET_FONT = ("Segoe UI", 8)
SMALL_FONT = ("Segoe UI", 8)
VALUE_FONT = ("Segoe UI", 10, "bold")
BTN_RADIUS = 8
LEFT_BTN_HEIGHT = int(round(40 * 1.3 * 1.3))  # left step buttons (height ×1.3 twice)
LEFT_BTN_WIDTH_SCALE = 1.4
LEFT_PANEL_MIN_WIDTH = int(round(180 * LEFT_BTN_WIDTH_SCALE))
CENTER_PANEL_WIDTH = 400
RIGHT_PANEL_MIN_WIDTH = 380
STUDY_BTN_HEIGHT = int(round(40 * 1.3 * 1.1))
STUDY_BTN_MIN_WIDTH = int(round(140 * 2))
STUDY_BTN_FONT = ("Segoe UI", 14, "bold")
STUDY_BTN_RADIUS = 12
ROUND_SCALE = round(0.52 * 0.9, 3)
ROUND_ADJ_BTN_HEIGHT = int(round(80 * ROUND_SCALE))
ROUND_ADJ_BTN_WIDTH = int(round(104 * ROUND_SCALE))
ROUND_ADJ_BTN_FONT = ("Segoe UI", int(round(22 * ROUND_SCALE)), "bold")
ROUND_ADJ_BTN_RADIUS = int(round(16 * ROUND_SCALE))
ROUND_VALUE_FONT = ("Segoe UI", int(round(20 * ROUND_SCALE * 1.5)), "bold")
ROUND_UNIT_FONT = ("Segoe UI", int(round(16 * ROUND_SCALE)))
ROUND_BLOCK_PAD = 6
ROUND_BLOCK_RADIUS = 10
ROUND_ROW_GAP = 5
ROUND_CONTROLS_SHIFT = 14
ROUND_ON_INDICATOR = ("Segoe UI", 13)
ROUND_BADGE_SIZE = int(round(56 * ROUND_SCALE * 2.2))
ROUND_BADGE_GAP = int(round(20 * ROUND_SCALE))
ROUND_BADGE_EDGE = 6
ROUND_BADGE_OUTLINE = 2
ROUND_RAINBOW = (
    "#e74c3c",
    "#e67e22",
    "#f1c40f",
    "#2ecc71",
    "#3498db",
    "#9b59b6",
    "#1abc9c",
)
ROUND_BLINK_MS = 180
ROUND_TEMP_BTN_COLOR = "#2980b9"
ROUND_TEMP_BTN_HOVER = "#3498db"
ROUND_TIME_BTN_COLOR = "#d35400"
ROUND_TIME_BTN_HOVER = "#e67e22"
MAIN_BTN_HEIGHT = 40
SMALL_BTN_HEIGHT = 26
PETRI_STEPPER_BTN_HEIGHT = 38
PETRI_STEPPER_BTN_WIDTH = int(round(44 * 1.5))
PETRI_STEPPER_BTN_FONT = ("Segoe UI", 12, "bold")
PETRI_LABEL_FONT = ("Segoe UI", 10, "bold")
LEFT_BTN_GAP = 4


class ProcedureGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Automation Imagery")
        self.root.configure(bg=BG)

        self._busy = False
        self._fullscreen = True
        self._temp_display = tk.StringVar(value="--.- °C")
        self._target_display = tk.StringVar(value="Target 37 °C")
        self._time_display = tk.StringVar(value="Ready")
        self._status_display = tk.StringVar(value="Idle")

        self._petri_count = tk.IntVar(value=10)
        self._round_temps = [
            tk.DoubleVar(value=DEFAULT_ROUND_TEMPS[i]) for i in range(NUM_STUDY_ROUNDS)
        ]
        self._round_times = [
            tk.DoubleVar(value=DEFAULT_ROUND_TIMES_MIN[i]) for i in range(NUM_STUDY_ROUNDS)
        ]
        self._round_enabled = [
            tk.BooleanVar(value=DEFAULT_ROUND_ENABLED[i]) for i in range(NUM_STUDY_ROUNDS)
        ]
        self._round_time_hours = [
            tk.BooleanVar(value=False) for _ in range(NUM_STUDY_ROUNDS)
        ]
        self._round_time_displays = [
            tk.StringVar(value=str(DEFAULT_ROUND_TIMES_MIN[i]))
            for i in range(NUM_STUDY_ROUNDS)
        ]
        self._round_time_unit_labels = []
        self._round_row_frames = []
        self._round_badges = []
        self._study_blinking = False
        self._badge_blink_phase = 0
        self._badge_blink_id = None
        self._active_round = 0

        self._canvas = None
        self._gauge_cx = 200
        self._gauge_cy = 120
        self._gauge_r = 90

        self._ui_queue = queue.Queue()
        self._build_ui()
        self._go_fullscreen()
        self.root.bind("<Escape>", self._on_escape)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._drain_ui_queue)

    def _go_fullscreen(self):
        self._fullscreen = True
        try:
            self.root.attributes("-fullscreen", True)
        except tk.TclError:
            w, h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            self.root.geometry(f"{w}x{h}+0+0")
        self.root.update_idletasks()

    def _on_escape(self, _event=None):
        if self._fullscreen:
            self._fullscreen = False
            self.root.attributes("-fullscreen", False)
        else:
            self._go_fullscreen()

    def _section(self, parent, title):
        frame = tk.LabelFrame(
            parent,
            text=f"  {title}  ",
            bg=PANEL,
            fg=ACCENT,
            font=("Segoe UI", 10, "bold"),
            labelanchor="n",
            padx=4,
            pady=3,
        )
        frame.pack(fill=tk.X, pady=(0, 6))
        inner = tk.Frame(frame, bg=PANEL)
        inner.pack(fill=tk.X)
        return inner

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        outer = tk.Frame(self.root, bg=BG, padx=12, pady=10)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, minsize=LEFT_PANEL_MIN_WIDTH, weight=0)
        outer.columnconfigure(1, weight=0)
        outer.columnconfigure(2, minsize=RIGHT_PANEL_MIN_WIDTH, weight=1)
        outer.rowconfigure(0, weight=1)

        # --- Left: steps (top) + Close (bottom) ---
        left = tk.Frame(outer, bg=PANEL, padx=10, pady=10, width=LEFT_PANEL_MIN_WIDTH)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)

        left_steps = tk.Frame(left, bg=PANEL)
        left_steps.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        for label, fn in [
            ("All Home", step_01_all_home),
            ("Insert Petri Dishes", step_02_insert_petri_dishes),
            ("Shift for Incubation", step_03_shift_for_incubation),
            ("Start Incubation", None),
        ]:
            self._mk_left_btn(left_steps, label, fn).pack(fill=tk.X, pady=LEFT_BTN_GAP)

        self._petri_stepper_row(left_steps)

        for label, fn in [
            ("Take Pictures", None),
            ("Sterilize", step_06_sterilize),
        ]:
            self._mk_left_btn(left_steps, label, fn).pack(fill=tk.X, pady=LEFT_BTN_GAP)

        self._mk_round_btn(
            left,
            "Close",
            self._on_close,
            color=CLOSE_BTN,
            fg=TEXT,
            hover="#d46a66",
            height=LEFT_BTN_HEIGHT,
            font=LEFT_BTN_FONT,
            stretch=True,
        ).pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        # --- Center (fixed width) ---
        center = tk.Frame(outer, bg=BG, padx=8, width=CENTER_PANEL_WIDTH)
        center.grid(row=0, column=1, sticky="ns")
        center.grid_propagate(False)
        center.columnconfigure(0, weight=1)
        center.rowconfigure(3, weight=1)

        tk.Label(
            center, textvariable=self._status_display, bg=BG, fg=ACCENT, font=("Segoe UI", 11)
        ).grid(row=0, column=0, sticky="w")

        viz = tk.Frame(center, bg=PANEL, padx=6, pady=6)
        viz.grid(row=1, column=0, sticky="nsew", pady=6)
        center.rowconfigure(1, weight=1)
        self._canvas = tk.Canvas(viz, height=260, bg=PANEL, highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        tk.Label(center, text="Log", bg=BG, fg=MUTED, font=("Segoe UI", 9)).grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        self._log = scrolledtext.ScrolledText(
            center, bg="#12161f", fg=TEXT, insertbackground=TEXT, font=("Consolas", 9), relief=tk.FLAT
        )
        self._log.grid(row=3, column=0, sticky="nsew")

        # --- Right: incubation + imaging rounds (wider column) ---
        right_outer = tk.Frame(
            outer, bg=PANEL, padx=10, pady=8, width=RIGHT_PANEL_MIN_WIDTH
        )
        right_outer.grid(row=0, column=2, sticky="nsew")
        right_outer.grid_propagate(False)
        right_outer.columnconfigure(0, weight=1)

        self._mk_round_btn(
            right_outer,
            STUDY_BTN_TITLE,
            lambda: self._run_action(STUDY_BTN_TITLE, None),
            color=STUDY_BTN_COLOR,
            hover=STUDY_BTN_HOVER,
            fg=TEXT_ON_COLOR,
            height=STUDY_BTN_HEIGHT,
            font=STUDY_BTN_FONT,
            radius=STUDY_BTN_RADIUS,
            stretch=True,
            min_width=STUDY_BTN_MIN_WIDTH,
        ).pack(fill=tk.X, pady=(0, 6))

        scroll_host = tk.Frame(right_outer, bg=PANEL)
        scroll_host.pack(fill=tk.BOTH, expand=True)
        scroll_host.columnconfigure(0, weight=1)
        scroll_host.rowconfigure(0, weight=1)

        rounds_canvas = tk.Canvas(
            scroll_host, bg=PANEL, highlightthickness=0, bd=0
        )
        rounds_scroll = tk.Scrollbar(
            scroll_host,
            orient=tk.VERTICAL,
            command=rounds_canvas.yview,
            bg=CARD,
            troughcolor="#12161f",
            activebackground=ACCENT,
            highlightthickness=0,
            bd=0,
            width=16,
        )
        rounds_canvas.configure(yscrollcommand=rounds_scroll.set)
        rounds_canvas.grid(row=0, column=0, sticky="nsew")
        rounds_scroll.grid(row=0, column=1, sticky="ns")

        rounds_box = tk.Frame(rounds_canvas, bg=PANEL)
        rounds_win = rounds_canvas.create_window((0, 0), window=rounds_box, anchor="nw")

        def _sync_scroll_region(_event=None):
            rounds_canvas.configure(scrollregion=rounds_canvas.bbox("all") or (0, 0, 0, 0))

        def _sync_inner_width(event):
            rounds_canvas.itemconfigure(rounds_win, width=event.width)
            _sync_scroll_region()

        rounds_box.bind("<Configure>", _sync_scroll_region)
        rounds_canvas.bind("<Configure>", _sync_inner_width)

        def _wheel_units(event):
            if getattr(event, "delta", 0):
                return int(-event.delta / 120)
            if getattr(event, "num", None) == 4:
                return -1
            if getattr(event, "num", None) == 5:
                return 1
            return 0

        def _on_mousewheel(event):
            steps = _wheel_units(event)
            if steps:
                rounds_canvas.yview_scroll(steps, "units")
            return "break"

        def _bind_wheel(_event=None):
            rounds_canvas.bind_all("<MouseWheel>", _on_mousewheel)
            rounds_canvas.bind_all("<Button-4>", _on_mousewheel)
            rounds_canvas.bind_all("<Button-5>", _on_mousewheel)

        def _unbind_wheel(_event=None):
            rounds_canvas.unbind_all("<MouseWheel>")
            rounds_canvas.unbind_all("<Button-4>")
            rounds_canvas.unbind_all("<Button-5>")

        scroll_host.bind("<Enter>", _bind_wheel)
        scroll_host.bind("<Leave>", _unbind_wheel)

        self._rounds_canvas = rounds_canvas
        self._rounds_inner = rounds_box

        for i in range(NUM_STUDY_ROUNDS):
            self._study_round_row(
                rounds_box,
                i,
                self._round_temps[i],
                self._round_times[i],
                self._round_enabled[i],
            )

        self._refresh_round_highlight()

    def _adj_btn(
        self,
        parent,
        text,
        command,
        width=3,
        height=None,
        font=None,
        min_width=0,
        color=CARD,
        hover=SELECTED,
        fg=TEXT,
    ):
        return self._mk_round_btn(
            parent,
            text,
            command,
            color=color,
            fg=fg,
            hover=hover,
            height=height or SMALL_BTN_HEIGHT,
            font=font or ADJ_FONT,
            radius=8,
            stretch=False,
            min_width=min_width,
        )

    def _round_temp_btn(self, parent, text, command):
        return self._mk_round_btn(
            parent,
            text,
            command,
            color=ROUND_TEMP_BTN_COLOR,
            hover=ROUND_TEMP_BTN_HOVER,
            fg=TEXT_ON_COLOR,
            height=ROUND_ADJ_BTN_HEIGHT,
            font=ROUND_ADJ_BTN_FONT,
            radius=ROUND_ADJ_BTN_RADIUS,
            stretch=False,
            min_width=ROUND_ADJ_BTN_WIDTH,
        )

    def _round_time_btn(self, parent, text, command):
        return self._mk_round_btn(
            parent,
            text,
            command,
            color=ROUND_TIME_BTN_COLOR,
            hover=ROUND_TIME_BTN_HOVER,
            fg=TEXT_ON_COLOR,
            height=ROUND_ADJ_BTN_HEIGHT,
            font=ROUND_ADJ_BTN_FONT,
            radius=ROUND_ADJ_BTN_RADIUS,
            stretch=False,
            min_width=ROUND_ADJ_BTN_WIDTH,
        )

    def _widget_bg(self, parent):
        try:
            return parent.cget("bg")
        except tk.TclError:
            return PANEL

    def _paint_round_rect(self, canvas, x1, y1, x2, y2, r, fill, tag=None):
        r = max(1, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
        opts = {"fill": fill, "outline": fill}
        if tag:
            opts["tags"] = (tag,)
        canvas.create_rectangle(x1 + r, y1, x2 - r, y2, **opts)
        canvas.create_rectangle(x1, y1 + r, x2, y2 - r, **opts)
        canvas.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, **opts)
        canvas.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, **opts)
        canvas.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, **opts)
        canvas.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, **opts)

    def _mk_round_btn(
        self,
        parent,
        text,
        command,
        color=ACCENT,
        fg="#0d1520",
        hover=None,
        height=LEFT_BTN_HEIGHT,
        font=BTN_FONT,
        radius=BTN_RADIUS,
        stretch=False,
        min_width=0,
    ):
        """Canvas button with rounded corners."""
        bg = self._widget_bg(parent)
        hover = hover or color
        wrap = tk.Frame(parent, bg=bg)
        compact_w = min_width or max(28, len(text) * 8 + 14)
        canvas = tk.Canvas(
            wrap,
            height=height,
            width=compact_w if not stretch else 1,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        if stretch:
            canvas.pack(fill=tk.X)
        else:
            canvas.pack()
            wrap.pack_propagate(False)
            wrap.configure(width=compact_w, height=height)
        state = {"fill": color}

        def redraw(_event=None):
            canvas.delete("all")
            w = canvas.winfo_width() if stretch else compact_w
            if stretch and min_width:
                w = max(w, min_width)
            if w < 4:
                w = compact_w
            h = height
            self._paint_round_rect(canvas, 1, 1, w - 1, h - 1, radius, state["fill"])
            canvas.create_text(w / 2, h / 2, text=text, fill=fg, font=font)

        def on_click(_event):
            command()

        def on_enter(_event):
            state["fill"] = hover
            redraw()

        def on_leave(_event):
            state["fill"] = color
            redraw()

        canvas.bind("<Configure>", redraw)
        canvas.bind("<Button-1>", on_click)
        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)
        redraw()
        return wrap

    def _mk_btn(
        self,
        parent,
        text,
        command,
        color=ACCENT,
        width=20,
        height=LEFT_BTN_HEIGHT,
        stretch=True,
        font=BTN_FONT,
        min_width=0,
    ):
        return self._mk_round_btn(
            parent,
            text,
            lambda t=text, f=command: self._run_action(t, f),
            color=color,
            height=height,
            font=font,
            stretch=stretch,
            min_width=min_width,
        )

    def _mk_left_btn(self, parent, text, command, color=ACCENT):
        """Left column action button (taller and wider than default)."""
        return self._mk_btn(
            parent,
            text,
            command,
            color=color,
            height=LEFT_BTN_HEIGHT,
            stretch=True,
            font=LEFT_BTN_FONT,
        )

    def _study_round_row(self, parent, index, temp_var, time_var, enabled_var):
        block_shell = tk.Frame(parent, bg=PANEL)
        block_shell.pack(fill=tk.X, pady=ROUND_ROW_GAP)
        self._round_row_frames.append(block_shell)

        canvas = tk.Canvas(block_shell, bg=PANEL, highlightthickness=0, bd=0)
        canvas.pack(fill=tk.X)

        block = tk.Frame(canvas, bg=PANEL, padx=ROUND_BLOCK_PAD, pady=4)
        block_shell._round_canvas = canvas
        block_shell._round_inner = block
        block_shell._round_bg = PANEL
        win_id = canvas.create_window(
            ROUND_BLOCK_PAD, ROUND_BLOCK_PAD, window=block, anchor="nw"
        )
        cfg_after = [None]

        def _redraw_round_shell(bg=None):
            if bg is not None:
                block_shell._round_bg = bg
            bg = block_shell._round_bg
            block.update_idletasks()
            ih = block.winfo_reqheight()
            shell_w = max(
                block_shell.winfo_width(),
                block.winfo_reqwidth() + 2 * ROUND_BLOCK_PAD,
                1,
            )
            ch = max(ih + 2 * ROUND_BLOCK_PAD, 1)
            canvas.config(height=ch)
            canvas.coords(win_id, ROUND_BLOCK_PAD, ROUND_BLOCK_PAD)
            canvas.delete("round_bg")
            self._paint_round_rect(
                canvas,
                2,
                2,
                shell_w - 2,
                ch - 2,
                ROUND_BLOCK_RADIUS,
                bg,
                tag="round_bg",
            )
            canvas.tag_lower("round_bg")

        def _schedule_redraw(_event=None):
            if cfg_after[0] is not None:
                try:
                    canvas.after_cancel(cfg_after[0])
                except tk.TclError:
                    pass
            cfg_after[0] = canvas.after(80, _redraw_round_shell)

        block_shell._round_redraw = _redraw_round_shell
        block_shell.bind("<Configure>", _schedule_redraw)

        ctrl_box = tk.Frame(block, bg=PANEL)
        ctrl_box.pack(fill=tk.X, pady=(2, 0))

        gap = int(round(8 * ROUND_SCALE))
        hours_var = self._round_time_hours[index]
        time_display = self._round_time_displays[index]

        center_wrap = tk.Frame(ctrl_box, bg=PANEL)
        center_wrap.pack(side=tk.LEFT, expand=True, fill=tk.X)

        round_row = tk.Frame(center_wrap, bg=PANEL)
        round_row.pack(anchor="center")

        checks_col = tk.Frame(round_row, bg=PANEL)
        checks_col.pack(side=tk.LEFT, padx=(0, gap), anchor="center")
        tk.Checkbutton(
            checks_col,
            text="",
            variable=enabled_var,
            bg=PANEL,
            fg=TEXT,
            selectcolor=ROUND_ACTIVE,
            activebackground=PANEL,
            activeforeground=TEXT,
            font=ROUND_ON_INDICATOR,
            command=self._refresh_round_highlight,
        ).pack(anchor="w", pady=(2, 0))
        tk.Checkbutton(
            checks_col,
            text="",
            variable=hours_var,
            bg=PANEL,
            fg=TEXT,
            selectcolor=ROUND_ACTIVE,
            activebackground=PANEL,
            activeforeground=TEXT,
            font=ROUND_ON_INDICATOR,
            command=lambda idx=index: self._toggle_time_unit(idx),
        ).pack(anchor="w", pady=(2, 0))

        controls_col = tk.Frame(round_row, bg=PANEL)
        controls_col.pack(
            side=tk.LEFT, anchor="center", padx=(ROUND_CONTROLS_SHIFT, 0)
        )

        trow = tk.Frame(controls_col, bg=PANEL)
        trow.pack(anchor="center", pady=(0, 3))
        self._round_temp_btn(trow, "−T", lambda v=temp_var: self._bump_temp(v, -1)).pack(
            side=tk.LEFT, padx=(0, gap)
        )
        tk.Label(
            trow, textvariable=temp_var, bg=PANEL, fg=ACCENT, font=ROUND_VALUE_FONT, width=4
        ).pack(side=tk.LEFT, padx=gap)
        tk.Label(trow, text="°C", bg=PANEL, fg=MUTED, font=ROUND_UNIT_FONT).pack(side=tk.LEFT)
        self._round_temp_btn(trow, "T+", lambda v=temp_var: self._bump_temp(v, 1)).pack(
            side=tk.LEFT, padx=(gap, 0)
        )

        mrow = tk.Frame(controls_col, bg=PANEL)
        mrow.pack(anchor="center")
        self._round_time_btn(
            mrow, "−t", lambda idx=index: self._bump_incub_time(idx, -1)
        ).pack(side=tk.LEFT, padx=(0, gap))
        tk.Label(
            mrow,
            textvariable=time_display,
            bg=PANEL,
            fg=ACCENT2,
            font=ROUND_VALUE_FONT,
            width=4,
        ).pack(side=tk.LEFT, padx=gap)
        unit_lbl = tk.Label(mrow, text="min", bg=PANEL, fg=MUTED, font=ROUND_UNIT_FONT)
        unit_lbl.pack(side=tk.LEFT)
        self._round_time_unit_labels.append(unit_lbl)
        self._round_time_btn(
            mrow, "t+", lambda idx=index: self._bump_incub_time(idx, 1)
        ).pack(side=tk.LEFT, padx=(gap, 0))
        self._round_badges.append(self._create_round_badge(ctrl_box, index))
        self._sync_round_time_display(index)
        _redraw_round_shell(PANEL)

    def _round_row_bg(self, round_index):
        """Background for round index 1..NUM_STUDY_ROUNDS."""
        if round_index == self._active_round and self._busy:
            return ROUND_ACTIVE
        if self._round_enabled[round_index - 1].get():
            return ROUND_ENABLED
        return PANEL

    @staticmethod
    def _badge_label_color(fill):
        fill = fill.lstrip("#")
        if len(fill) != 6:
            return TEXT
        r, g, b = (int(fill[i : i + 2], 16) for i in (0, 2, 4))
        return "#0d1520" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else TEXT

    def _create_round_badge(self, parent, index):
        size = ROUND_BADGE_SIZE
        pad = 2
        canvas = tk.Canvas(
            parent,
            width=size,
            height=size,
            bg=PANEL,
            highlightthickness=0,
            bd=0,
        )
        canvas.pack(
            side=tk.RIGHT, padx=(ROUND_BADGE_GAP, ROUND_BADGE_EDGE), anchor="center"
        )
        r = size // 2
        oval_id = canvas.create_oval(
            pad,
            pad,
            size - pad,
            size - pad,
            fill=CARD,
            outline=TEXT,
            width=ROUND_BADGE_OUTLINE,
        )
        text_id = canvas.create_text(
            r,
            r,
            text=f"R{index + 1}",
            fill=TEXT,
            font=ROUND_VALUE_FONT,
        )
        badge = {
            "canvas": canvas,
            "oval": oval_id,
            "text": text_id,
            "index": index,
        }
        self._update_round_badge_idle(badge)
        return badge

    def _update_round_badge_idle(self, badge, force=False):
        if self._study_blinking and not force:
            return
        idx = badge["index"]
        row_bg = self._round_row_bg(idx + 1)
        fill = ROUND_ACTIVE if idx + 1 == self._active_round and self._busy else CARD
        if self._round_enabled[idx].get() and fill == CARD:
            fill = ROUND_ENABLED
        outline = ROUND_ACTIVE if idx + 1 == self._active_round and self._busy else TEXT
        canvas = badge["canvas"]
        canvas.configure(bg=row_bg)
        canvas.itemconfig(badge["oval"], fill=fill, outline=outline)
        canvas.itemconfig(badge["text"], fill=self._badge_label_color(fill))

    def _start_round_badge_blink(self):
        if self._study_blinking:
            return
        self._study_blinking = True
        self._badge_blink_phase = 0
        self._tick_round_badge_blink()

    def _stop_round_badge_blink(self):
        self._study_blinking = False
        if self._badge_blink_id is not None:
            try:
                self.root.after_cancel(self._badge_blink_id)
            except tk.TclError:
                pass
            self._badge_blink_id = None
        for badge in self._round_badges:
            self._update_round_badge_idle(badge)

    def _tick_round_badge_blink(self):
        if not self._study_blinking:
            return
        phase = self._badge_blink_phase
        active = self._active_round
        for badge in self._round_badges:
            idx = badge["index"]
            if idx + 1 == active and active > 0:
                row_bg = self._round_row_bg(idx + 1)
                color = ROUND_RAINBOW[phase % len(ROUND_RAINBOW)]
                canvas = badge["canvas"]
                canvas.configure(bg=row_bg)
                canvas.itemconfig(badge["oval"], fill=color, outline=color)
                canvas.itemconfig(badge["text"], fill=self._badge_label_color(color))
            else:
                self._update_round_badge_idle(badge, force=True)
        self._badge_blink_phase = (phase + 1) % len(ROUND_RAINBOW)
        self._badge_blink_id = self.root.after(ROUND_BLINK_MS, self._tick_round_badge_blink)

    def _set_frame_bg(self, widget, bg):
        try:
            widget.configure(bg=bg)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._set_frame_bg(child, bg)

    def _refresh_round_highlight(self):
        active = self._active_round
        for i, shell in enumerate(self._round_row_frames, start=1):
            if i == active and self._busy:
                bg = ROUND_ACTIVE
            elif self._round_enabled[i - 1].get():
                bg = ROUND_ENABLED
            else:
                bg = PANEL
            shell.configure(bg=PANEL)
            inner = shell._round_inner
            inner.configure(bg=bg)
            self._set_frame_bg(inner, bg)
            shell._round_canvas.configure(bg=PANEL)
            shell._round_redraw(bg)
        for badge in self._round_badges:
            if not self._study_blinking or badge["index"] + 1 != active:
                self._update_round_badge_idle(badge, force=self._study_blinking)

    def _highlight_round(self, round_index):
        self._active_round = round_index
        self._status_display.set(f"Round {round_index} — Incubating")
        self._refresh_round_highlight()
        self._scroll_round_into_view(round_index)

    def _scroll_round_into_view(self, round_index):
        canvas = getattr(self, "_rounds_canvas", None)
        frames = self._round_row_frames
        if canvas is None or not frames:
            return
        idx = max(0, min(len(frames) - 1, int(round_index) - 1))
        frame = frames[idx]
        canvas.update_idletasks()
        bbox = canvas.bbox("all")
        if not bbox:
            return
        total = max(1, bbox[3])
        view_h = max(1, canvas.winfo_height())
        y = frame.winfo_y()
        h = frame.winfo_height()
        top = canvas.canvasy(0)
        bottom = top + view_h
        if y < top:
            canvas.yview_moveto(y / total)
        elif y + h > bottom:
            canvas.yview_moveto(max(0.0, (y + h - view_h) / total))

    def _clear_round_highlight(self):
        self._active_round = 0
        self._refresh_round_highlight()

    def _petri_stepper_row(self, parent):
        """Petri dish count for Take Pictures (default 10)."""
        tk.Label(
            parent,
            text="Petri dishes",
            bg=PANEL,
            fg=TEXT,
            font=PETRI_LABEL_FONT,
        ).pack(anchor="w", pady=(6, 2))
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill=tk.X, pady=(0, 4))
        self._adj_btn(
            row,
            "−",
            lambda: self._petri_count.set(max(1, int(self._petri_count.get()) - 1)),
            height=PETRI_STEPPER_BTN_HEIGHT,
            font=PETRI_STEPPER_BTN_FONT,
            min_width=PETRI_STEPPER_BTN_WIDTH,
        ).pack(side=tk.LEFT, padx=(0, 4))
        tk.Label(
            row,
            textvariable=self._petri_count,
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 14, "bold"),
            width=4,
        ).pack(side=tk.LEFT, expand=True)
        tk.Label(row, text=f"/ {MAX_PETRI_DISHES}", bg=PANEL, fg=MUTED, font=SMALL_FONT).pack(
            side=tk.LEFT
        )
        self._adj_btn(
            row,
            "+",
            lambda: self._petri_count.set(
                min(MAX_PETRI_DISHES, int(self._petri_count.get()) + 1)
            ),
            height=PETRI_STEPPER_BTN_HEIGHT,
            font=PETRI_STEPPER_BTN_FONT,
            min_width=PETRI_STEPPER_BTN_WIDTH,
        ).pack(side=tk.LEFT, padx=(4, 0))

    @staticmethod
    def _format_time_display(minutes, in_hours):
        if in_hours:
            value = minutes / 60.0
        else:
            value = float(minutes)
        if abs(value - round(value)) < 0.05:
            return str(int(round(value)))
        text = f"{value:.1f}".rstrip("0").rstrip(".")
        return text

    def _sync_round_time_display(self, index):
        minutes = float(self._round_times[index].get())
        in_hours = self._round_time_hours[index].get()
        self._round_time_displays[index].set(
            self._format_time_display(minutes, in_hours)
        )
        if index < len(self._round_time_unit_labels):
            self._round_time_unit_labels[index].configure(
                text="hr" if in_hours else "min"
            )

    def _toggle_time_unit(self, index):
        self._sync_round_time_display(index)

    def _bump_temp(self, var, direction):
        v = float(var.get()) + direction * INCUBATION_TEMP_STEP
        v = max(INCUBATION_TEMP_MIN, min(INCUBATION_TEMP_MAX, v))
        if abs(v - round(v)) < 0.05:
            var.set(int(round(v)))
        else:
            var.set(round(v, 1))
        self._target_display.set(f"Target {var.get()} °C")

    def _bump_incub_time(self, index, direction):
        if self._round_time_hours[index].get():
            step = INCUBATION_HOUR_STEP * 60.0
        else:
            step = INCUBATION_MIN_STEP
        var = self._round_times[index]
        v = max(INCUBATION_MIN_MIN, float(var.get()) + direction * step)
        var.set(round(min(INCUBATION_MIN_MAX, v), 1))
        self._sync_round_time_display(index)

    def _on_canvas_resize(self, event):
        self._gauge_cx = max(80, event.width // 2)
        self._gauge_cy = max(60, event.height // 2)
        self._gauge_r = min(event.width, event.height) // 2 - 12
        if not self._busy:
            self._draw_idle_gauge()

    def _run_on_ui(self, fn):
        """Schedule GUI work on the Tk main thread (safe from worker threads)."""
        self._ui_queue.put(fn)

    def _drain_ui_queue(self):
        while True:
            try:
                fn = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as exc:
                self._log_msg_unsafe(f"UI error: {exc}")
        self.root.after(50, self._drain_ui_queue)

    def _log_msg_unsafe(self, msg):
        self._log.insert(tk.END, msg + "\n")
        self._log.see(tk.END)

    def _log_msg(self, msg):
        self._run_on_ui(lambda m=msg: self._log_msg_unsafe(m))

    def _enabled_flags(self, vars_list):
        return [bool(v.get()) for v in vars_list]

    def _validate_study_settings(self):
        if not any(self._enabled_flags(self._round_enabled)):
            raise ValueError("Enable at least one round")

    def _run_action(self, title, fn):
        if self._busy:
            return
        if title == STUDY_BTN_TITLE:
            try:
                self._validate_study_settings()
            except ValueError as exc:
                messagebox.showerror("Invalid settings", str(exc))
                return

        def worker():
            self._set_busy(True, title)
            try:
                if title == "Start Incubation":
                    self._do_incubation()
                    self._log_msg(f"Done: {title}")
                elif title == "Take Pictures":
                    self._do_pictures()
                    self._log_msg(f"Done: {title}")
                elif title == STUDY_BTN_TITLE:
                    self._do_incubation_imaging()
                    self._log_msg(f"Done: {title}")
                elif fn is not None:
                    fn()
                    self._log_msg(f"Done: {title}")
                else:
                    raise RuntimeError(f"No handler for step: {title}")
            except Exception as exc:
                self._log_msg(f"ERROR: {exc}")
                self._run_on_ui(lambda e=str(exc): messagebox.showerror("Error", e))
            finally:
                self._set_busy(False, "Idle")
                self._run_on_ui(lambda: (self._clear_round_highlight(), self._set_center_readout(idle=True)))

        threading.Thread(target=worker, daemon=True).start()

    def _set_busy(self, busy, status):
        self._busy = busy

        def _apply(s=status):
            self._status_display.set(s)
            if busy and s == STUDY_BTN_TITLE:
                self._start_round_badge_blink()
            elif not busy:
                self._stop_round_badge_blink()
            self._refresh_round_highlight()

        self._run_on_ui(_apply)

    def _format_remaining(self, remaining_s):
        mins, secs = divmod(int(max(0, remaining_s)), 60)
        return f"{mins:02d}:{secs:02d}"

    def _temp_text(self, temp_c):
        if temp_c is None or (isinstance(temp_c, float) and math.isnan(temp_c)):
            return "--.- °C"
        return f"{temp_c:.1f} °C"

    def _set_center_readout(self, temp_c=None, target_c=None, remaining_s=None, idle=False):
        if idle:
            self._temp_display.set("--.- °C")
            self._target_display.set("Target -- °C")
            self._time_display.set("Ready")
            self._draw_idle_gauge()
            return
        self._temp_display.set(self._temp_text(temp_c))
        self._target_display.set(f"Target {target_c:.0f} °C")
        self._time_display.set(self._format_remaining(remaining_s))

    def _incubation_tick(self, elapsed, remaining, temp_c, target_c):
        bar_temp = 0.0 if (
            temp_c is None or (isinstance(temp_c, float) and math.isnan(temp_c))
        ) else float(temp_c)

        def _ui(e=elapsed, r=remaining, t=temp_c, g=target_c, b=bar_temp):
            self._set_center_readout(t, g, r)
            self._draw_gauge(b, g, r, e)

        self._run_on_ui(_ui)

    def _do_incubation(self):
        target = float(STEP_INCUBATION_TEMP_C)
        minutes = float(STEP_INCUBATION_MINUTES)
        duration_s = minutes * 60.0
        self._log_msg(f"Incubation: {target:g}°C for {minutes:g} min")

        shown = threading.Event()

        def _show_start():
            self._set_center_readout(None, target, duration_s)
            self._draw_gauge(0, target, duration_s, 0)
            shown.set()

        self._run_on_ui(_show_start)
        if not shown.wait(timeout=2.0):
            self._log_msg("Warning: UI did not update before incubation start")

        Start_incubation(target, minutes, on_tick=self._incubation_tick)

    def _do_pictures(self):
        n = max(1, min(MAX_PETRI_DISHES, int(self._petri_count.get())))
        self._log_msg(f"Take Pictures: {n} petri dish(es)")
        step_05_prepare_imaging()
        exp = capture_petri_dishes(
            n,
            on_tick=self._incubation_tick,
            on_log=self._log_msg,
        )
        step_05_post_imaging_cleanup()
        self._log_msg(f"Saved: {exp}")

    def _do_incubation_imaging(self):
        self._validate_study_settings()
        n = max(1, min(MAX_PETRI_DISHES, int(self._petri_count.get())))
        temps = [float(self._round_temps[i].get()) for i in range(NUM_STUDY_ROUNDS)]
        times = [float(self._round_times[i].get()) for i in range(NUM_STUDY_ROUNDS)]
        rnd_on = self._enabled_flags(self._round_enabled)
        self._log_msg(f"{STUDY_BTN_TITLE}: {n} petri dish(es)")
        self._log_msg(f"  Rounds on: {rnd_on}")

        def on_log(msg):
            self._log_msg(msg)

        def on_round_start(rnd):
            self._run_on_ui(lambda r=rnd: self._highlight_round(r))

        exp = run_incubation_imaging_study(
            num_petri_dishes=n,
            round_temps=temps,
            round_times_min=times,
            rounds_enabled=rnd_on,
            on_tick=self._incubation_tick,
            on_log=on_log,
            on_round_start=on_round_start,
        )
        self._log_msg(f"Experiment: {exp}")

    def _draw_center_text(self, c, cx, cy):
        """Temperature and countdown centered on the main panel."""
        temp = self._temp_display.get()
        target = self._target_display.get()
        remaining = self._time_display.get()
        y0 = cy - 42
        c.create_text(cx, y0 + 10, text=temp, fill=TEXT, font=("Segoe UI", 34, "bold"))
        c.create_text(cx, cy + 4, text=target, fill=MUTED, font=("Segoe UI", 12))
        c.create_text(cx, cy + 40, text=remaining, fill=ACCENT2, font=("Segoe UI", 22, "bold"))

    def _draw_idle_gauge(self):
        if not self._canvas:
            return
        c = self._canvas
        c.delete("all")
        cx, cy, r = self._gauge_cx, self._gauge_cy, self._gauge_r
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#3d465c", width=10)
        self._draw_center_text(c, cx, cy)

    def _draw_gauge(self, temp_c, target_c, remaining_s, elapsed_s):
        if not self._canvas:
            return
        c = self._canvas
        c.delete("all")
        cx, cy, r = self._gauge_cx, self._gauge_cy, self._gauge_r
        total = max(1.0, elapsed_s + remaining_s)
        frac = min(1.0, elapsed_s / total)
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#3d465c", width=10)
        if frac > 0:
            c.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=90, extent=-360 * frac,
                outline=ACCENT2, width=10, style=tk.ARC,
            )
        self._draw_center_text(c, cx, cy)

    def _on_close(self):
        if self._busy:
            if not messagebox.askyesno(
                "Busy",
                "A step is running. Close anyway?\nGPIO will be released.",
            ):
                return
        self._log_msg("Closing: releasing GPIO...")
        try:
            shutdown_all()
        except Exception as exc:
            self._log_msg(f"Shutdown warning: {exc}")
        self.root.destroy()


def main():
    root = tk.Tk()
    ProcedureGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

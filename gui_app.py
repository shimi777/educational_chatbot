#!/usr/bin/env python3
"""
Educational Chatbot - Generic GUI Application

5-Step Teaching Flow:
1. Setup: Teacher pastes learning material → system generates topic
2. Settings: Configure preparation and teaching session times
3. Lesson: Student-teacher reads preparation material (configurable timer)
4. Chat: Student-teacher explains to struggling student + mentor (configurable timer)
5. Evaluation: Performance scores and feedback

Supports English / Hebrew toggle with full RTL layout.

Usage: python gui_app.py
"""

import sys
import os
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox, ttk
import tkinter.font as tkfont
import threading
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.conversation_manager import ConversationManager
from backend.topic_config import TopicConfig
from backend.topic_generator import TopicGenerator
from backend.llm_client import LLMClient
from backend.config import config
from backend.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

COLORS = {
    "dark_bg": "#2c3e50",
    "blue_btn": "#3498db",
    "green_btn": "#4CAF50",
    "orange_btn": "#FF9800",
    "pink_btn": "#E91E63",
    "purple_btn": "#9C27B0",
    "gray_btn": "#607D8B",
    "timer_green": "#2ecc71",
    "timer_orange": "#f39c12",
    "timer_red": "#e74c3c",
}

THEMES = {
    "light": {
        # App surfaces
        "app_bg": "#F6F8FC",
        "panel_bg": "#FFFFFF",
        "fg": "#0F172A",
        "muted_fg": "#475569",
        "border": "#E2E8F0",
        "focus": "#2563EB",

        # Top bar
        "topbar_bg": "#0F172A",
        "topbar_fg": "#F8FAFC",
        "topbar_btn_bg": "#1F2937",
        "topbar_btn_active_bg": "#334155",
        "topbar_btn_fg": "#F8FAFC",

        # Text / inputs
        "text_bg": "#FFFFFF",
        "text_fg": "#0F172A",
        "input_bg": "#FFFFFF",
        "input_fg": "#0F172A",
        "selection_bg": "#DBEAFE",

        # Buttons (semantic)
        "btn_primary_bg": "#2563EB",
        "btn_primary_hover_bg": "#1D4ED8",
        "btn_primary_fg": "#FFFFFF",

        "btn_secondary_bg": "#E2E8F0",
        "btn_secondary_hover_bg": "#CBD5E1",
        "btn_secondary_fg": "#0F172A",

        "btn_destructive_bg": "#DC2626",
        "btn_destructive_hover_bg": "#B91C1C",
        "btn_destructive_fg": "#FFFFFF",

        # Scrollbars
        "scroll_trough": "#E2E8F0",
        "scroll_thumb": "#94A3B8",
        "scroll_thumb_hover": "#64748B",
    },

    "dark": {
        # App surfaces
        "app_bg": "#0B1220",
        "panel_bg": "#111827",
        "fg": "#E5E7EB",
        "muted_fg": "#94A3B8",
        "border": "#334155",
        "focus": "#60A5FA",

        # Top bar
        "topbar_bg": "#0F172A",
        "topbar_fg": "#F8FAFC",
        "topbar_btn_bg": "#1F2937",
        "topbar_btn_active_bg": "#334155",
        "topbar_btn_fg": "#F8FAFC",

        # Text / inputs
        "text_bg": "#0B1220",
        "text_fg": "#E5E7EB",
        "input_bg": "#0B1220",
        "input_fg": "#E5E7EB",
        "selection_bg": "#1D4ED8",

        # Buttons (semantic)
        "btn_primary_bg": "#60A5FA",
        "btn_primary_hover_bg": "#3B82F6",
        "btn_primary_fg": "#0B1220",

        "btn_secondary_bg": "#1F2937",
        "btn_secondary_hover_bg": "#334155",
        "btn_secondary_fg": "#E5E7EB",

        "btn_destructive_bg": "#F87171",
        "btn_destructive_hover_bg": "#EF4444",
        "btn_destructive_fg": "#0B1220",

        # Scrollbars
        "scroll_trough": "#0F172A",
        "scroll_thumb": "#334155",
        "scroll_thumb_hover": "#475569",
    },
}
# Unicode bidi marks for mixed Hebrew/English text
RLM = "\u200F"  # Right-to-Left Mark
LRM = "\u200E"  # Left-to-Right Mark


# ============================================================================
# ANIMATED STATUS BAR  (Sprint 3)
# ============================================================================

class AnimatedStatusBar:
    """
    A reusable progress widget that shows an animated dots message while
    an LLM call is in progress, with an optional Cancel button.

    IMPORTANT — geometry manager compatibility:
        All screens in this app use grid().  AnimatedStatusBar therefore
        uses grid()/grid_remove() internally, NOT pack/pack_forget, so it
        can safely live inside any grid-managed parent frame.

    Usage:
        bar = AnimatedStatusBar(parent_frame, grid_row=5,
                                on_cancel=self._cancel_fn)
        bar.show("Generating topic")   # makes the row visible + starts dots
        bar.hide()                     # stops animation, hides the row

    The widget manages its own Tkinter 'after' loop so it never blocks the
    main thread.  Call hide() from any callback — safe even if already hidden.
    """

    _DOT_INTERVAL_MS = 500   # milliseconds between dot updates
    _MAX_DOTS = 4

    def __init__(self, parent: tk.Frame, grid_row: int = 0, on_cancel=None):
        """
        Args:
            parent:    The grid-managed frame that owns this bar.
            grid_row:  The grid row to place the bar in (must not conflict
                       with other widgets in that parent).
            on_cancel: Optional callable invoked when the user clicks Cancel.
                       The bar hides itself first, then calls on_cancel().
        """
        self._parent = parent
        self._on_cancel = on_cancel
        self._after_id = None
        self._message = ""
        self._dot_count = 0
        self._grid_row = grid_row

        # Outer frame — placed in the grid but hidden via grid_remove() initially
        self._frame = tk.Frame(parent, bg="#f0f0f0", relief=tk.SUNKEN, bd=1)
        self._frame.grid(row=grid_row, column=0, sticky="ew", pady=(2, 0))
        self._frame.grid_remove()   # hidden by default; show() calls grid() again

        self._label = tk.Label(
            self._frame,
            text="",
            font=("Arial", 9),
            fg="#444444",
            bg="#f0f0f0",
            anchor="w",
            padx=8,
        )
        self._label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._pb = ttk.Progressbar(self._frame, mode="indeterminate", length=140)
        self._pb.pack(side=tk.RIGHT, padx=6, pady=2)

        if on_cancel is not None:
            self._cancel_btn = tk.Button(
                self._frame,
                text="✕ Cancel",
                font=("Arial", 8),
                fg="white",
                bg=COLORS["gray_btn"],
                relief=tk.FLAT,
                padx=6,
                command=self._handle_cancel,
            )
            self._cancel_btn.pack(side=tk.RIGHT, padx=4, pady=2)
            self._cancel_btn._btn_role = "topbar"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self, message: str):
        """
        Make the bar visible and start the animated dots.

        Args:
            message: Base status text, e.g. "Generating topic".
                     Dots are appended automatically by the animation loop.
        """
        self._message = message
        self._dot_count = 0
        self._frame.grid()   # restore the previously grid_remove()'d frame
        self._pb.start(10)
        self._tick()

    def hide(self):
        """Stop the animation and hide the bar."""
        if self._after_id is not None:
            self._frame.after_cancel(self._after_id)
            self._after_id = None
        self._pb.stop()
        self._frame.grid_remove()

    @property
    def is_visible(self) -> bool:
        return self._frame.winfo_ismapped()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tick(self):
        dots = "." * (self._dot_count % (self._MAX_DOTS + 1))
        self._label.config(text=f"{self._message}{dots}")
        self._dot_count += 1
        self._after_id = self._frame.after(self._DOT_INTERVAL_MS, self._tick)

    def _handle_cancel(self):
        self.hide()
        logger.info("User cancelled operation: '%s'", self._message)
        if self._on_cancel is not None:
            self._on_cancel()


class ChatbotGUI:
    """Main GUI application with 5-screen flow and full RTL support."""

    def __init__(self, root):
        self.root = root
        self.root.title("Educational Chatbot")
        self.root.geometry("820x740")
        self.root.minsize(700, 600)

        # State
        self.topic_config = None
        self.manager = None
        self.lang = config.default_language
        self.is_processing = False
        self._generation_cancelled = False   # Sprint 3: soft-cancel for topic generation

        # Timer state
        self.chat_timer_running = False
        self.chat_seconds_left = 0
        self.chat_timer_after_id = None
        self.session_ended = False

        self.lesson_timer_running = False
        self.lesson_seconds_left = 0
        self.lesson_timer_after_id = None

        # Configurable durations — seeded from config, overridden by Settings screen
        self.lesson_minutes = config.default_prep_minutes
        self.teaching_minutes = config.default_teaching_minutes

        logger.info(
            "ChatbotGUI started | lang=%s | prep=%dm | teach=%dm",
            self.lang,
            self.lesson_minutes,
            self.teaching_minutes,
        )

        # Screens
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.screens = {}
        self.current_screen = None

        # Collect directional widgets for RTL/LTR toggling
        self._dir_labels = []      # [(label_widget, grid_row, grid_col, padx, pady), ...]
        self._dir_btn_frames = []  # [(frame, [btn1, btn2, ...], special_right_btn_or_None), ...]
        self._dir_top_bars = []    # [(lang_btn, timer_label_or_None), ...]

        # ---------------- Theme (Light/Dark) ----------------
        self.theme_name = "light"  # default
        self.theme_btn_text_var = tk.StringVar()
        self._theme_top_bars = []  # store refs to top bars widgets for styling
        self._update_theme_button_text()
        self._ttk_style = ttk.Style(self.root)

        self._hover_btn = None
        self.root.bind_all("<Motion>", self._hover_watchdog, add="+")
        self.root.bind_all("<ButtonRelease-1>", self._hover_watchdog, add="+")

        # --- Typography: make UI look like a product (best-effort) ---
        self._font_family = "Segoe UI"
        self._font_body_size = 10
        self._font_h1 = (self._font_family, 14, "bold")
        self._font_h2 = (self._font_family, 12, "bold")
        self._font_btn = (self._font_family, 10, "bold")
        self._font_small_btn = (self._font_family, 9, "bold")

        # Apply default fonts globally (some widgets still have explicit fonts; we will coerce them in theme pass too).
        try:
            for name in (
                "TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont",
                "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont",
                "TkIconFont", "TkTooltipFont"
            ):
                try:
                    tkfont.nametofont(name).configure(family=self._font_family, size=self._font_body_size)
                except Exception:
                    pass
            self.root.option_add("*Font", f"{{{self._font_family}}} {self._font_body_size}")
        except Exception:
            pass

        self._build_setup_screen()
        self._build_settings_screen()
        self._build_lesson_screen()
        self._build_chat_screen()
        self._build_evaluation_screen()

        self._show_screen("setup")
        self._apply_direction()
        self._apply_theme()

    def _apply_text_tag_theme(self, th):
        is_dark = (self.theme_name == "dark")

        # Subtle, professional accents
        accent_blue = "#2563EB" if not is_dark else "#60A5FA"
        accent_green = "#15803D" if not is_dark else "#34D399"
        accent_purple = "#6D28D9" if not is_dark else "#C4B5FD"
        danger = "#B91C1C" if not is_dark else "#F87171"
        warning = "#B45309" if not is_dark else "#FDBA74"

        # Lesson screen tags
        if hasattr(self, "lesson_display"):
            try:
                self.lesson_display.tag_configure("heading", foreground=accent_blue)
                self.lesson_display.tag_configure("item", foreground=th["fg"])
                self.lesson_display.tag_configure("warning", foreground=warning)
            except Exception:
                pass

        # Chat screen tags
        if hasattr(self, "chat_display"):
            try:
                self.chat_display.tag_configure("student", foreground=accent_blue)
                self.chat_display.tag_configure("teacher", foreground=accent_green)
                self.chat_display.tag_configure("label_student", foreground=accent_blue)
                self.chat_display.tag_configure("label_teacher", foreground=accent_green)
                self.chat_display.tag_configure("system", foreground=th["muted_fg"])
                self.chat_display.tag_configure("time_up", foreground=danger)
            except Exception:
                pass

        # Mentor panel tags
        if hasattr(self, "mentor_panel"):
            try:
                self.mentor_panel.tag_configure("mentor", foreground=warning)
                self.mentor_panel.tag_configure("summary", foreground=accent_purple)
                self.mentor_panel.tag_configure("error", foreground=danger)
            except Exception:
                pass

        # Evaluation screen tags
        if hasattr(self, "eval_display"):
            try:
                self.eval_display.tag_configure("heading", foreground=accent_purple)
                self.eval_display.tag_configure("score", foreground=accent_green)
                self.eval_display.tag_configure("feedback", foreground=th["fg"])
            except Exception:
                pass

    def _hover_watchdog(self, event=None):
        """
        Fix for Windows Tk: sometimes <Leave> doesn't fire and button keeps hover color.
        On any mouse motion / release we verify cursor is still inside the last-hovered button.
        """
        b = getattr(self, "_hover_btn", None)
        if not b:
            return

        try:
            if not b.winfo_exists():
                self._hover_btn = None
                return

            x = self.root.winfo_pointerx()
            y = self.root.winfo_pointery()

            bx = b.winfo_rootx()
            by = b.winfo_rooty()
            bw = b.winfo_width()
            bh = b.winfo_height()

            inside = (bx <= x < bx + bw) and (by <= y < by + bh)

            if not inside:
                # force reset to normal
                try:
                    b.configure(bg=b._ui_bg_normal, activebackground=b._ui_bg_normal)
                except Exception:
                    pass
                self._hover_btn = None
        except Exception:
            # don't crash UI because of theming helpers
            self._hover_btn = None

    def _coerce_font_family(self, widget):
        """Force Segoe UI across the app while preserving size/weight (best-effort)."""
        try:
            if getattr(widget, "_skip_theme_font", False):
                return

            f = widget.cget("font")
            if not f:
                return

            # Tuple font: ("Arial", 10, "bold") -> ("Segoe UI", 10, "bold")
            if isinstance(f, tuple) and len(f) >= 2:
                if str(f[0]) != self._font_family:
                    widget.configure(font=(self._font_family, *f[1:]))

            # String font name or "Arial 10": use tkfont to reconfigure
            else:
                try:
                    fo = tkfont.Font(font=f)
                    fo.configure(family=self._font_family)
                    widget.configure(font=fo)
                except Exception:
                    pass
        except Exception:
            pass

    def _infer_button_role(self, btn: tk.Button) -> str:
        """
        Infer a semantic role from the original hardcoded color.
        We cache the role on the widget so theme switching stays consistent.
        """
        try:
            # Topbar buttons are themed explicitly in _apply_theme()
            if getattr(btn, "_btn_role", None) == "topbar":
                return "topbar"

            bg = str(btn.cget("bg")).lower()

            # Primary actions were historically green/pink in this UI
            if bg == str(COLORS.get("green_btn", "")).lower() or bg == str(COLORS.get("pink_btn", "")).lower():
                return "primary"

            # Most utility actions were purple/blue/orange/gray -> treat as secondary for a clean product look
            if bg in (
                str(COLORS.get("purple_btn", "")).lower(),
                str(COLORS.get("blue_btn", "")).lower(),
                str(COLORS.get("orange_btn", "")).lower(),
                str(COLORS.get("gray_btn", "")).lower(),
            ):
                return "secondary"

            return "secondary"
        except Exception:
            return "secondary"

    def _style_button(self, btn: tk.Button, th: dict, role: str):
        """Apply a clean, unified button style with hover states (Tk best-effort)."""
        if role == "topbar":
            return

        if role == "destructive":
            bg = th["btn_destructive_bg"]
            hover = th["btn_destructive_hover_bg"]
            fg = th["btn_destructive_fg"]
            border = th["btn_destructive_bg"]
        elif role == "primary":
            bg = th["btn_primary_bg"]
            hover = th["btn_primary_hover_bg"]
            fg = th["btn_primary_fg"]
            border = th["btn_primary_bg"]
        else:
            bg = th["btn_secondary_bg"]
            hover = th["btn_secondary_hover_bg"]
            fg = th["btn_secondary_fg"]
            border = th["border"]

        try:
            btn.configure(
                bg=bg,
                fg=fg,
                activebackground=bg,
                activeforeground=fg,
                relief=tk.FLAT,
                bd=0,
                padx=12,
                pady=6,
                cursor="hand2",
                highlightthickness=1,
                highlightbackground=border,
                highlightcolor=th["focus"],
            )
        except Exception:
            pass

        # Hover bindings (bind once; update cached colors on every theme switch)
        try:
            btn._ui_bg_normal = bg
            btn._ui_bg_hover = hover

            def _reset_bg(b):
                # Always restore normal bg/activebackground (Windows can "stick" active colors in light theme)
                try:
                    b.configure(bg=b._ui_bg_normal, activebackground=b._ui_bg_normal)
                except Exception:
                    pass

                # if this was the hovered button, clear it
                if getattr(self, "_hover_btn", None) == b:
                    self._hover_btn = None

            if not getattr(btn, "_ui_hover_bound", False):
                def _on_enter(_e, b=btn):
                    try:
                        b.configure(bg=b._ui_bg_hover, activebackground=b._ui_bg_hover)
                    except Exception:
                        pass
                    self._hover_btn = b

                def _on_leave(_e, b=btn):
                    _reset_bg(b)

                def _on_release(_e, b=btn):
                    _reset_bg(b)

                def _on_focus_out(_e, b=btn):
                    _reset_bg(b)

                btn.bind("<Enter>", _on_enter)
                btn.bind("<Leave>", _on_leave)
                btn.bind("<ButtonRelease-1>", _on_release)
                btn.bind("<FocusOut>", _on_focus_out)

                btn._ui_hover_bound = True
        except Exception:
            pass

    def _style_topbar_button(self, btn: tk.Button, th: dict):
        """Topbar button styling with robust hover reset (prevents 'hover stuck' on Windows light theme)."""
        try:
            normal = th["topbar_btn_bg"]
            hover = th["topbar_btn_active_bg"]
            fg = th["topbar_btn_fg"]

            # Base style: IMPORTANT -> keep activebackground == normal to prevent Windows sticky active state.
            btn.configure(
                bg=normal,
                fg=fg,
                activebackground=normal,
                activeforeground=fg,
                relief=tk.FLAT,
                bd=0,
                cursor="hand2",
                highlightthickness=0,
            )

            # Cache colors for handlers
            btn._ui_bg_normal = normal
            btn._ui_bg_hover = hover

            def _reset_bg(b):
                # Always restore normal bg/activebackground (Windows can "stick" active colors in light theme)
                try:
                    b.configure(bg=b._ui_bg_normal, activebackground=b._ui_bg_normal)
                except Exception:
                    pass

            if not getattr(btn, "_ui_hover_bound_topbar", False):

                def _on_enter(_e, b=btn):
                    try:
                        b.configure(bg=b._ui_bg_hover, activebackground=b._ui_bg_hover)
                    except Exception:
                        pass

                def _on_leave(_e, b=btn):
                    _reset_bg(b)

                def _on_release(_e, b=btn):
                    _reset_bg(b)

                def _on_focus_out(_e, b=btn):
                    _reset_bg(b)

                btn.bind("<Enter>", _on_enter)
                btn.bind("<Leave>", _on_leave)
                btn.bind("<ButtonRelease-1>", _on_release)
                btn.bind("<FocusOut>", _on_focus_out)

                btn._ui_hover_bound_topbar = True

        except Exception:
            pass

    def _style_scrollbar(self, sb, th: dict):
        """Force scrollbar colors (some platforms ignore some options)."""
        try:
            sb.configure(
                bg=th["scroll_thumb"],
                troughcolor=th["scroll_trough"],
                activebackground=th["scroll_thumb_hover"],
                highlightbackground=th["scroll_trough"],
                highlightcolor=th["scroll_trough"],
                relief=tk.FLAT,
                bd=0,
                width=12,
            )
        except Exception:
            pass

    def _theme_scrolledtext_scrollbars(self, th: dict):
        """
        ScrolledText sometimes keeps a white scrollbar on Windows/theme combinations.
        Force-style known ScrolledText widgets (and their internal scrollbars).
        """
        candidates = []
        for name in ("material_input", "lesson_display", "chat_display", "mentor_panel", "eval_display"):
            w = getattr(self, name, None)
            if w is not None:
                candidates.append(w)

        for w in candidates:
            # Known attributes in tkinter.scrolledtext.ScrolledText
            for attr in ("vbar", "hbar"):
                sb = getattr(w, attr, None)
                if sb is not None:
                    self._style_scrollbar(sb, th)

            # Also walk children just in case
            try:
                for ch in w.winfo_children():
                    if isinstance(ch, tk.Scrollbar):
                        self._style_scrollbar(ch, th)
                    elif isinstance(ch, ttk.Scrollbar):
                        try:
                            ch.configure(style=getattr(self, "_ttk_scrollbar_style", "TScrollbar"))
                        except Exception:
                            pass
            except Exception:
                pass
    # ================================================================
    # SCREEN MANAGEMENT
    # ================================================================

    def _show_screen(self, name):
        for n, frame in self.screens.items():
            frame.grid_forget()
        self.screens[name].grid(row=0, column=0, sticky="nsew")
        self.current_screen = name

    def _make_top_bar(self, parent, title_var=None, timer_var=None):
        """Create a consistent top bar with language toggle, theme toggle, title, optional timer."""
        bar = tk.Frame(parent, bg=COLORS["dark_bg"], pady=6)

        # Layout: [timer] [title expands] [theme] [language]  (RTL)
        # Layout: [language] [title expands] [theme] [timer]  (LTR)
        bar.columnconfigure(1, weight=1)

        lang_var = tk.StringVar(value="English" if self.lang == "en" else "עברית")
        lang_btn = tk.Button(
            bar,
            textvariable=lang_var,
            font=("Segoe UI", 9, "bold"),
            bg=COLORS["blue_btn"],
            fg="white",
            width=10,
            command=lambda: self._toggle_language(lang_var),
        )
        # Semantic role for theming (topbar buttons are styled separately)
        lang_btn._btn_role = "topbar"
        lang_btn.grid(row=0, column=0, padx=10)

        title_lbl = None
        if title_var:
            title_lbl = tk.Label(
                bar,
                textvariable=title_var,
                font=self._font_h2,
                fg="white",
                bg=COLORS["dark_bg"],
            )
            title_lbl.grid(row=0, column=1)

        theme_btn = tk.Button(
            bar,
            textvariable=self.theme_btn_text_var,
            font=self._font_small_btn,
            bg=COLORS["gray_btn"],
            fg="white",
            width=10,
            command=self._toggle_theme,
        )
        theme_btn._btn_role = "topbar"
        theme_btn.grid(row=0, column=2, padx=10)

        timer_label = None
        if timer_var:
            timer_label = tk.Label(
                bar,
                textvariable=timer_var,
                font=("Consolas", 14, "bold"),
                fg=COLORS["timer_green"],
                bg=COLORS["dark_bg"],
                width=6,
            )
            timer_label.grid(row=0, column=3, padx=10)
            timer_label._skip_theme_fg = True
            timer_label._skip_theme_font = True  # Keep monospace digits for the timer
        # Register for directional swapping (support legacy tuples too)
        self._dir_top_bars.append((lang_btn, timer_label, theme_btn))

        # Store refs for theming
        self._theme_top_bars.append(
            {
                "bar": bar,
                "title": title_lbl,
                "timer": timer_label,
                "theme_btn": theme_btn,
                "lang_btn": lang_btn,
            }
        )

        return bar, lang_btn, timer_label

    def _toggle_language(self, lang_var):
        if self.lang == "en":
            self.lang = "he"
            lang_var.set("עברית")
        else:
            self.lang = "en"
            lang_var.set("English")
        if self.manager:
            self.manager.set_language(self.lang)
        self._update_theme_button_text()
        self._refresh_current_screen_labels()
        self._apply_direction()

    def _update_theme_button_text(self):
        if self.lang == "he":
            label = "☀ בהיר" if self.theme_name == "light" else "🌙 כהה"
        else:
            label = "☀ Light" if self.theme_name == "light" else "🌙 Dark"
        self.theme_btn_text_var.set(label)

    def _toggle_theme(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self._update_theme_button_text()
        self._apply_theme()

    def _apply_theme(self):
        """Apply theme colors to the whole UI."""
        th = THEMES[self.theme_name]
        # Style ttk widgets (Progressbar). Use a dedicated style name so we can reconfigure on theme switch.
        pb_style = "App.Horizontal.TProgressbar"
        try:
            # NOTE: ttk.Progressbar uses styles; colors are platform/theme dependent.
            self._ttk_style.configure(
                pb_style,
                troughcolor=th["panel_bg"],
                background=th["focus"],
                bordercolor=th["border"],
                lightcolor=th["focus"],
                darkcolor=th["focus"],
            )
        except Exception:
            pass

        # Style ttk Scrollbar (best-effort; some OS themes may override parts)
        self._ttk_scrollbar_style = "App.Vertical.TScrollbar"
        try:
            self._ttk_style.configure(
                self._ttk_scrollbar_style,
                troughcolor=th["scroll_trough"],
                background=th["scroll_thumb"],
                bordercolor=th["scroll_trough"],
                arrowcolor=th["muted_fg"],
                lightcolor=th["scroll_thumb"],
                darkcolor=th["scroll_thumb"],
            )
        except Exception:
            pass

        # Keep compatibility with existing code that uses COLORS["dark_bg"]
        COLORS["dark_bg"] = th["topbar_bg"]

        # Root + screens
        self.root.configure(bg=th["app_bg"])
        for frame in self.screens.values():
            try:
                frame.configure(bg=th["app_bg"])
            except tk.TclError:
                pass

        # Generic pass: recolor common widgets recursively
        self._apply_theme_recursive(self.root, th)

        # Top bars: force correct colors (white text etc.)
        for tb in getattr(self, "_theme_top_bars", []):
            bar = tb.get("bar")
            title_lbl = tb.get("title")
            timer_lbl = tb.get("timer")
            theme_btn = tb.get("theme_btn")
            lang_btn = tb.get("lang_btn")

            if bar:
                bar.configure(bg=th["topbar_bg"])
            if title_lbl:
                title_lbl.configure(bg=th["topbar_bg"], fg=th["topbar_fg"])
            if timer_lbl:
                timer_lbl.configure(bg=th["topbar_bg"])

            if theme_btn:
                self._style_topbar_button(theme_btn, th)
            if lang_btn:
                self._style_topbar_button(lang_btn, th)

        # Theme AnimatedStatusBar widgets (Setup + Chat)
        for bar in [getattr(self, "setup_progress", None), getattr(self, "chat_progress", None)]:
            if not bar:
                continue

            # Frame + label background/foreground
            try:
                bar._frame.configure(bg=th["panel_bg"])
            except Exception:
                pass
            try:
                bar._label.configure(bg=th["panel_bg"], fg=th["muted_fg"])
            except Exception:
                pass

            # Progressbar style
            try:
                bar._pb.configure(style=pb_style)
            except Exception:
                pass

            # Optional cancel button (exists only on setup_progress)
            try:
                if hasattr(bar, "_cancel_btn"):
                    bar._cancel_btn.configure(
                        bg=th["topbar_btn_bg"],
                        fg=th["topbar_btn_fg"],
                        activebackground=th["topbar_btn_active_bg"],
                        activeforeground=th["topbar_btn_fg"],
                        relief=tk.FLAT,
                        bd=0,
                        cursor="hand2",
                    )
            except Exception:
                pass
        # Ensure Text tag colors follow the active theme (and look more professional).
        self._theme_scrolledtext_scrollbars(th)
        self._apply_text_tag_theme(th)

    def _apply_theme_recursive(self, widget, th):
        """Best-effort theming for Tk widgets."""
        try:
            # Typography coercion (keep it early so widgets look consistent)
            self._coerce_font_family(widget)

            if isinstance(widget, tk.Frame):
                relief = str(widget.cget("relief")).lower()
                is_card = relief not in ("flat", "none", "")

                bg = th["panel_bg"] if is_card else th["app_bg"]
                widget.configure(bg=bg)

                # Card look: subtle border, no chunky 3D relief
                if is_card:
                    try:
                        widget.configure(
                            relief=tk.FLAT,
                            bd=0,
                            highlightthickness=1,
                            highlightbackground=th["border"],
                            highlightcolor=th["border"],
                        )
                    except Exception:
                        pass

            elif isinstance(widget, tk.Label):
                try:
                    parent_bg = widget.master.cget("bg")
                except Exception:
                    parent_bg = th["app_bg"]

                # Some labels (e.g., timers) use semantic colors; do not override their fg.
                if getattr(widget, "_skip_theme_fg", False):
                    widget.configure(bg=parent_bg)
                else:
                    old_fg = str(widget.cget("fg")).lower()
                    muted_candidates = {
                        "#888", "#777", "#999", "gray",
                        "#555", "#555555", "#666", "#666666",
                        "#757575", "#444", "#444444",
                    }
                    target_fg = th["muted_fg"] if old_fg in muted_candidates else th["fg"]
                    widget.configure(bg=parent_bg, fg=target_fg)

            elif isinstance(widget, tk.Text):
                widget.configure(
                    bg=th["text_bg"],
                    fg=th["text_fg"],
                    insertbackground=th["text_fg"],
                    selectbackground=th["selection_bg"],
                    selectforeground=th["text_bg"],
                )

            elif isinstance(widget, tk.Entry):
                widget.configure(
                    bg=th["input_bg"],
                    fg=th["input_fg"],
                    insertbackground=th["input_fg"],
                    relief=tk.FLAT,
                    highlightthickness=1,
                    highlightbackground=th["border"],
                    highlightcolor=th["focus"],
                )

            elif isinstance(widget, tk.Spinbox):
                widget.configure(
                    bg=th["input_bg"],
                    fg=th["input_fg"],
                    insertbackground=th["input_fg"],
                    relief=tk.FLAT,
                    highlightthickness=1,
                    highlightbackground=th["border"],
                    highlightcolor=th["focus"],
                    buttonbackground=th["panel_bg"],
                )

            elif isinstance(widget, tk.Scrollbar):
                self._style_scrollbar(widget, th)

            elif isinstance(widget, ttk.Scrollbar):
                # ttk scrollbars follow styles
                try:
                    widget.configure(style=getattr(self, "_ttk_scrollbar_style", "TScrollbar"))
                except Exception:
                    pass

            elif isinstance(widget, tk.Button):
                # Cache semantic role once, then theme-switch is consistent
                if getattr(widget, "_btn_role", None) is None:
                    widget._btn_role = self._infer_button_role(widget)

                # Skip topbar here (handled explicitly in _apply_theme)
                role = getattr(widget, "_btn_role", "secondary")
                if role != "topbar":
                    self._style_button(widget, th, role)

        except tk.TclError:
            pass

        for child in widget.winfo_children():
            self._apply_theme_recursive(child, th)
    def _refresh_current_screen_labels(self):
        """Update labels on current screen for language change."""
        if self.current_screen == "setup":
            self._update_setup_labels()
        elif self.current_screen == "settings":
            self._update_settings_labels()
        elif self.current_screen == "lesson":
            self._populate_lesson_screen()
        elif self.current_screen == "chat":
            self._update_chat_labels()
        elif self.current_screen == "evaluation":
            last_eval = getattr(self, "_last_evaluation_data", None)
            if last_eval is None:
                last_eval = getattr(self, "_last_evaluation", "")
            self._populate_evaluation_screen(last_eval)

    # ================================================================
    # RTL / LTR DIRECTION SUPPORT
    # ================================================================

    def _apply_direction(self):
        """Apply RTL or LTR layout direction based on current language."""
        is_rtl = (self.lang == "he")
        justify = "right" if is_rtl else "left"
        anchor = "e" if is_rtl else "w"
        sticky = "e" if is_rtl else "w"
        pack_side = tk.RIGHT if is_rtl else tk.LEFT

        # --- ScrolledText widgets: set justify on all tags ---
        text_widgets = [self.material_input, self.lesson_display,
                        self.chat_display, self.mentor_panel, self.eval_display]
        for tw in text_widgets:
            for tag_name in tw.tag_names():
                if tag_name != "sel":
                    tw.tag_configure(tag_name, justify=justify)

        # --- Entry widget ---
        self.input_field.config(justify=justify)

        # --- Labels: flip anchor and grid sticky ---
        for lbl, row, col, padx, pady in self._dir_labels:
            lbl.config(anchor=anchor)
            lbl.grid_configure(sticky=sticky)

        # --- Button frames: repack in correct direction ---
        for frame, buttons, special_btn in self._dir_btn_frames:
            for child in frame.winfo_children():
                child.pack_forget()
            for btn in buttons:
                px = (10, 0) if is_rtl else (0, 10)
                btn.pack(side=pack_side, padx=px)
            if special_btn:
                opposite = tk.LEFT if is_rtl else tk.RIGHT
                special_btn.pack(side=opposite)

        # --- Input row: swap entry/send button columns ---
        if is_rtl:
            self.input_field.grid_configure(row=0, column=1, sticky="ew", padx=(5, 0))
            self.send_btn.grid_configure(row=0, column=0, padx=(0, 0))
            self.input_field.master.columnconfigure(0, weight=0)
            self.input_field.master.columnconfigure(1, weight=1)
        else:
            self.input_field.grid_configure(row=0, column=0, sticky="ew", padx=(0, 5))
            self.send_btn.grid_configure(row=0, column=1, padx=(0, 0))
            self.input_field.master.columnconfigure(0, weight=1)
            self.input_field.master.columnconfigure(1, weight=0)

        # --- Top bars: swap lang button / timer positions ---
        lang_col = 3 if is_rtl else 0
        timer_col = 0 if is_rtl else 3
        theme_col = 2

        for item in self._dir_top_bars:
            lang_btn = item[0]
            timer_label = item[1] if len(item) > 1 else None
            theme_btn = item[2] if len(item) > 2 else None

            lang_btn.grid_configure(column=lang_col)
            if theme_btn:
                theme_btn.grid_configure(column=theme_col)
            if timer_label:
                timer_label.grid_configure(column=timer_col)
        # --- Settings screen: mirror label/spinner columns for RTL ---
        if hasattr(self, "settings_center_frame") and hasattr(self, "settings_prep_label") and hasattr(self, "settings_prep_spinner"):
            if is_rtl:
                    # RTL: column 0 expands (acts like spacer), column 1 is tight at the right
                    self.settings_center_frame.columnconfigure(0, weight=1)
                    self.settings_center_frame.columnconfigure(1, weight=0)

                    # Put label at far right (col 1), spinner just to its left (col 0, right-aligned)
                    self.settings_prep_label.grid_configure(column=1, sticky="e")
                    self.settings_prep_spinner.grid_configure(column=0, sticky="e")

                    self.settings_teach_label.grid_configure(column=1, sticky="e")
                    self.settings_teach_spinner.grid_configure(column=0, sticky="e")
            else:
                 # LTR: column 1 expands
                    self.settings_center_frame.columnconfigure(0, weight=0)
                    self.settings_center_frame.columnconfigure(1, weight=1)
            
                    # Normal layout: label left (col 0), spinner to the right (col 1)
                    self.settings_prep_label.grid_configure(column=0, sticky="w")
                    self.settings_prep_spinner.grid_configure(column=1, sticky="w")

                    self.settings_teach_label.grid_configure(column=0, sticky="w")
                    self.settings_teach_spinner.grid_configure(column=1, sticky="w")

    def _register_dir_label(self, label, row, col, padx=0, pady=0):
        """Register a label for directional flipping."""
        self._dir_labels.append((label, row, col, padx, pady))

    def _install_text_context_menu(self, widget: tk.Text):
        """Right-click context menu (Cut/Copy/Paste/Select All) for Text/ScrolledText."""
        def _popup(event):
            widget.focus_set()

            menu = tk.Menu(widget, tearoff=0)

            if getattr(self, "lang", "en") == "he":
                labels = {"cut": "גזור", "copy": "העתק", "paste": "הדבק", "all": "בחר הכל"}
            else:
                labels = {"cut": "Cut", "copy": "Copy", "paste": "Paste", "all": "Select All"}

            menu.add_command(label=labels["cut"], command=lambda: widget.event_generate("<<Cut>>"))
            menu.add_command(label=labels["copy"], command=lambda: widget.event_generate("<<Copy>>"))
            menu.add_command(label=labels["paste"], command=lambda: widget.event_generate("<<Paste>>"))
            menu.add_separator()
            menu.add_command(label=labels["all"], command=lambda: (widget.tag_add("sel", "1.0", "end-1c")))

            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        # Windows/Linux: Button-3, some mac/touchpads: Button-2
        widget.bind("<Button-3>", _popup)
        widget.bind("<Button-2>", _popup)

    def _install_clipboard_shortcuts(self, widget: tk.Text):
        """Make Ctrl+V work reliably (even with non-Latin keyboard layouts)."""
        def _paste(_e=None):
            widget.event_generate("<<Paste>>")
            return "break"

        def _copy(_e=None):
            widget.event_generate("<<Copy>>")
            return "break"

        def _cut(_e=None):
            widget.event_generate("<<Cut>>")
            return "break"

        def _select_all(_e=None):
            widget.tag_add("sel", "1.0", "end-1c")
            return "break"

        # Standard shortcuts
        widget.bind("<Control-v>", _paste)
        widget.bind("<Control-V>", _paste)
        widget.bind("<Shift-Insert>", _paste)

        widget.bind("<Control-c>", _copy)
        widget.bind("<Control-C>", _copy)
        widget.bind("<Control-Insert>", _copy)

        widget.bind("<Control-x>", _cut)
        widget.bind("<Control-X>", _cut)
        widget.bind("<Shift-Delete>", _cut)

        widget.bind("<Control-a>", _select_all)
        widget.bind("<Control-A>", _select_all)

        # Layout-independent: Ctrl+V often comes through as char '\x16'
        def _ctrl_keypress(e):
            if e.char == "\x16":  # SYN (Ctrl+V)
                return _paste(e)
            return None

        widget.bind("<Control-KeyPress>", _ctrl_keypress)

    def _install_entry_context_menu(self, widget: tk.Entry):
        def _select_all():
            widget.selection_range(0, tk.END)
            widget.icursor(tk.END)

        def _popup(event):
            widget.focus_set()

            menu = tk.Menu(widget, tearoff=0)

            if getattr(self, "lang", "en") == "he":
                labels = {"cut": "גזור", "copy": "העתק", "paste": "הדבק", "all": "בחר הכל"}
            else:
                labels = {"cut": "Cut", "copy": "Copy", "paste": "Paste", "all": "Select All"}

            menu.add_command(label=labels["cut"], command=lambda: widget.event_generate("<<Cut>>"))
            menu.add_command(label=labels["copy"], command=lambda: widget.event_generate("<<Copy>>"))
            menu.add_command(label=labels["paste"], command=lambda: widget.event_generate("<<Paste>>"))
            menu.add_separator()
            menu.add_command(label=labels["all"], command=_select_all)

            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

            return "break"

        # Windows/Linux: Button-3, some mac/touchpads: Button-2
        widget.bind("<Button-3>", _popup)
        widget.bind("<Button-2>", _popup)


    def _install_entry_clipboard_shortcuts(self, widget: tk.Entry):
        """Ctrl+V/C/X/A for Entry, including layout-independent control chars."""
        def _paste(_e=None):
            widget.event_generate("<<Paste>>")
            return "break"

        def _copy(_e=None):
            widget.event_generate("<<Copy>>")
            return "break"

        def _cut(_e=None):
            widget.event_generate("<<Cut>>")
            return "break"

        def _select_all(_e=None):
            widget.selection_range(0, tk.END)
            widget.icursor(tk.END)
            return "break"

        # Standard shortcuts
        widget.bind("<Control-v>", _paste)
        widget.bind("<Control-V>", _paste)
        widget.bind("<Shift-Insert>", _paste)

        widget.bind("<Control-c>", _copy)
        widget.bind("<Control-C>", _copy)
        widget.bind("<Control-Insert>", _copy)

        widget.bind("<Control-x>", _cut)
        widget.bind("<Control-X>", _cut)
        widget.bind("<Shift-Delete>", _cut)

        widget.bind("<Control-a>", _select_all)
        widget.bind("<Control-A>", _select_all)

        # Layout-independent control chars:
        #   Ctrl+V -> \x16, Ctrl+C -> \x03, Ctrl+X -> \x18, Ctrl+A -> \x01
        def _ctrl_keypress(e):
            if e.char == "\x16":
                return _paste(e)
            if e.char == "\x03":
                return _copy(e)
            if e.char == "\x18":
                return _cut(e)
            if e.char == "\x01":
                return _select_all(e)
            return None

        widget.bind("<Control-KeyPress>", _ctrl_keypress)
    def _register_dir_btn_frame(self, frame, buttons, special_right_btn=None):
        """Register a button frame for directional repack."""
        self._dir_btn_frames.append((frame, buttons, special_right_btn))

    # ================================================================
    # BIDI TEXT HELPERS
    # ================================================================

    def _bidi(self, he_template, *en_values):
        """
        Format a Hebrew string with embedded English values,
        using bidi marks for correct display.
        Example: self._bidi("שיעור: {}", topic) → "‏שיעור: ‎topic‏"
        """
        result = RLM + he_template
        for val in en_values:
            result = result.replace("{}", f"{LRM}{val}{RLM}", 1)
        return result

    # ================================================================
    # SCREEN 1: SETUP
    # ================================================================

    def _build_setup_screen(self):
        frame = tk.Frame(self.root)
        self.screens["setup"] = frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        # Top bar
        self.setup_title_var = tk.StringVar(value="Educational Chatbot — Setup")
        top_bar, self.setup_lang_btn, _ = self._make_top_bar(frame, self.setup_title_var)
        top_bar.grid(row=0, column=0, sticky="ew")

        # Instructions
        self.setup_instruction_var = tk.StringVar(value="Paste your learning material below:")
        self.setup_instruction_label = tk.Label(
            frame, textvariable=self.setup_instruction_var,
            font=("Arial", 11), anchor="w"
        )
        self.setup_instruction_label.grid(row=1, column=0, sticky="w", padx=12, pady=(10, 2))
        self._register_dir_label(self.setup_instruction_label, 1, 0, padx=12, pady=(10, 2))

        # Material input
        input_frame = tk.Frame(frame)
        input_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(0, weight=1)

        self.material_input = scrolledtext.ScrolledText(
            input_frame, wrap=tk.WORD, font=("Arial", 11),
            bg="#fafafa", relief=tk.GROOVE, borderwidth=2
        )
        self.material_input.grid(row=0, column=0, sticky="nsew")

        self._install_text_context_menu(self.material_input)
        self._install_clipboard_shortcuts(self.material_input)

        # Settings row (only age — time settings moved to Settings screen)
        self.setup_settings_frame = tk.Frame(frame)
        self.setup_settings_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=5)

        self.age_label = tk.Label(self.setup_settings_frame, text="Student age:",
                          font=("Arial", 10))
        self.age_label.pack(side=tk.LEFT, padx=(0, 5))

        # Fix: use IntVar + textvariable so arrows work
        default_age = int(config.default_student_age)
        default_age = max(8, min(18, default_age))
        self.age_var = tk.IntVar(value=default_age)

        self.age_spinner = tk.Spinbox(
            self.setup_settings_frame,
            from_=8, to=18, increment=1,
            textvariable=self.age_var,
            width=4,
            font=("Arial", 10),
            justify="center",
        )
        self.age_spinner.pack(side=tk.LEFT, padx=(0, 10))

        # Hint label (EN/HE)
        self.age_hint_var = tk.StringVar(value="Choose student age (8–18)")
        self.age_hint_label = tk.Label(
            self.setup_settings_frame,
            textvariable=self.age_hint_var,
            font=("Arial", 9),
            fg="#888",
        )
        self.age_hint_label.pack(side=tk.LEFT, padx=(0, 20))

        self._register_dir_btn_frame(
            self.setup_settings_frame,
            [self.age_label, self.age_spinner, self.age_hint_label]
        )

        # Buttons row
        self.setup_btn_frame = tk.Frame(frame)
        self.setup_btn_frame.grid(row=4, column=0, sticky="ew", padx=12, pady=10)

        self.generate_btn = tk.Button(
            self.setup_btn_frame, text="Generate Topic", font=("Arial", 11, "bold"),
            bg=COLORS["green_btn"], fg="white", width=16,
            command=self._on_generate_topic
        )
        self.generate_btn._btn_role = "primary"
        self.generate_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.load_btn = tk.Button(
            self.setup_btn_frame, text="Load Saved Topic", font=("Arial", 10),
            bg=COLORS["gray_btn"], fg="white", width=16,
            command=self._on_load_topic
        )
        self.load_btn._btn_role = "secondary"
        self.load_btn.pack(side=tk.LEFT)

        self._register_dir_btn_frame(
            self.setup_btn_frame,
            [self.generate_btn, self.load_btn]
        )

        # Animated progress bar — shown only during generation (Sprint 3)
        # grid_row=5: sits between the buttons row (4) and the status label (6)
        self.setup_progress = AnimatedStatusBar(
            frame, grid_row=5, on_cancel=self._on_cancel_generation
        )

        # Status label — always visible at the bottom (row 6)
        self.setup_status_var = tk.StringVar(value="Ready")
        self.setup_status_label = tk.Label(
            frame, textvariable=self.setup_status_var,
            font=("Arial", 9), fg="#555555", relief=tk.SUNKEN,
            anchor="w", padx=10, pady=3
        )
        self.setup_status_label.grid(row=6, column=0, sticky="ew")
        self._register_dir_label(self.setup_status_label, 6, 0)

    def _update_setup_labels(self):
        if self.lang == "he":
            self.setup_title_var.set("צ'אטבוט חינוכי — הגדרות")
            self.setup_instruction_var.set("הדבק את חומר הלימוד כאן:")
            self.generate_btn.config(text="צור נושא")
            self.load_btn.config(text="טען נושא שמור")
            self.age_label.config(text="גיל התלמיד:")
            self.age_hint_var.set("בחר גיל תלמיד (8–18)")
        else:
            self.setup_title_var.set("Educational Chatbot — Setup")
            self.setup_instruction_var.set("Paste your learning material below:")
            self.generate_btn.config(text="Generate Topic")
            self.load_btn.config(text="Load Saved Topic")
            self.age_label.config(text="Student age:")
            self.age_hint_var.set("Choose student age (8–18)")

    # Maximum characters accepted as learning material (~15k chars ≈ 3,750 tokens,
    # safely within gpt-4o-mini's context window after adding system prompts).
    _MAX_MATERIAL_CHARS = 15_000

    def _on_generate_topic(self):
        raw = self.material_input.get("1.0", tk.END).strip()
        if not raw:
            msg = "אנא הדבק חומר לימוד." if self.lang == "he" else "Please paste learning material first."
            messagebox.showwarning("Input Required", msg)
            return

        if len(raw) > self._MAX_MATERIAL_CHARS:
            if self.lang == "he":
                msg = (
                    f"החומר ארוך מדי ({len(raw):,} תווים).\n"
                    f"אנא קצר אותו ל-{self._MAX_MATERIAL_CHARS:,} תווים לכל היותר."
                )
            else:
                msg = (
                    f"Material is too long ({len(raw):,} characters).\n"
                    f"Please shorten it to under {self._MAX_MATERIAL_CHARS:,} characters."
                )
            messagebox.showwarning("Input Too Long", msg)
            logger.warning(
                "Material rejected: %d chars (limit %d)", len(raw), self._MAX_MATERIAL_CHARS
            )
            return

        logger.info("Generating topic | material=%d chars", len(raw))
        target_age = int(self.age_var.get())
        target_age = max(8, min(18, target_age))

        self._generation_cancelled = False
        self.generate_btn.config(state=tk.DISABLED)
        self.load_btn.config(state=tk.DISABLED)

        msg = "מייצר נושא" if self.lang == "he" else "Generating topic"
        self.setup_status_var.set("")          # clear static label while bar is shown
        self.setup_progress.show(msg)

        def generate():
            try:
                llm = LLMClient()
                generator = TopicGenerator(llm)
                cfg = generator.generate_topic_config(raw, target_age)
                # If user cancelled while LLM was running, silently discard result
                if self._generation_cancelled:
                    logger.info("Generation result discarded (cancelled by user)")
                    return
                self.root.after(0, lambda: self._on_topic_generated(cfg))
            except Exception as e:
                if not self._generation_cancelled:
                    err_msg = str(e)
                    self.root.after(0, lambda msg=err_msg: self._on_generation_error(msg))

        threading.Thread(target=generate, daemon=True).start()

    def _on_cancel_generation(self):
        """Called when user clicks Cancel on the setup progress bar."""
        self._generation_cancelled = True
        self.generate_btn.config(state=tk.NORMAL)
        self.load_btn.config(state=tk.NORMAL)
        self.setup_status_var.set(
            "בוטל." if self.lang == "he" else "Cancelled."
        )

    def _on_topic_generated(self, topic_config):
        self.topic_config = topic_config
        self.setup_progress.hide()
        self.generate_btn.config(state=tk.NORMAL)
        self.load_btn.config(state=tk.NORMAL)
        self.setup_status_var.set(f"Topic generated: {topic_config.topic_name_en}")
        logger.info("Topic generated: '%s'", topic_config.topic_name_en)

        # Save automatically
        save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_topic.json")
        try:
            topic_config.save_to_file(save_path)
            logger.debug("Auto-saved topic to %s", save_path)
        except Exception as e:
            logger.warning("Could not auto-save topic: %s", e)

        self._show_screen("settings")

    def _on_generation_error(self, error_msg):
        self.setup_progress.hide()
        self.generate_btn.config(state=tk.NORMAL)
        self.load_btn.config(state=tk.NORMAL)
        self.setup_status_var.set(f"Error: {error_msg[:80]}")
        logger.error("Topic generation failed: %s", error_msg)
        messagebox.showerror("Generation Failed", error_msg)

    def _on_load_topic(self):
        filepath = filedialog.askopenfilename(
            title="Load Topic Configuration",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not filepath:
            return
        try:
            loaded = TopicConfig.load_from_file(filepath)
            if not loaded.is_valid():
                messagebox.showerror("Invalid File", "The loaded file is missing required fields.")
                return
            self.topic_config = loaded
            self.setup_status_var.set(f"Loaded: {loaded.topic_name_en}")
            logger.info("Topic loaded from file: '%s'", loaded.topic_name_en)
            self._show_screen("settings")
        except Exception as e:
            logger.error("Failed to load topic from %s: %s", filepath, e)
            messagebox.showerror("Load Failed", str(e))

    # ================================================================
    # SCREEN 2: SETTINGS (Time Configuration)
    # ================================================================

    def _build_settings_screen(self):
        """Build the settings screen for configuring learning/teaching times."""
        frame = tk.Frame(self.root)
        self.screens["settings"] = frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        # Top bar
        self.settings_title_var = tk.StringVar(value="Learning Settings")
        top_bar, self.settings_lang_btn, _ = self._make_top_bar(frame, self.settings_title_var)
        top_bar.grid(row=0, column=0, sticky="ew")

        # Description
        self.settings_desc_var = tk.StringVar(
            value="Configure your preparation and teaching session times:"
        )
        self.settings_desc_label = tk.Label(
            frame, textvariable=self.settings_desc_var,
            font=("Arial", 12), anchor="w", pady=10
        )
        self.settings_desc_label.grid(row=1, column=0, sticky="w", padx=20, pady=(15, 5))
        self._register_dir_label(self.settings_desc_label, 1, 0, padx=20, pady=(15, 5))

        # Center panel with settings
        center_frame = tk.Frame(frame, bg="#f5f5f5", relief=tk.GROOVE, borderwidth=2)
        center_frame.grid(row=2, column=0, padx=40, pady=20, sticky="nsew")
        self.settings_center_frame = center_frame

        # LTR default: left column fixed (labels), right column expands (spinners/space)
        center_frame.columnconfigure(0, weight=0)
        center_frame.columnconfigure(1, weight=1)

        # --- Preparation Time ---
        self.settings_prep_label = tk.Label(
            center_frame, text="Preparation Time (minutes):",
            font=("Arial", 12), bg="#f5f5f5", anchor="w"
        )
        self.settings_prep_label.grid(row=0, column=0, sticky="w", padx=20, pady=(25, 10))
        self._register_dir_label(self.settings_prep_label, 0, 0, padx=20, pady=(25, 10))

        default_prep = int(config.default_prep_minutes)
        default_prep = max(1, min(20, default_prep))
        self.settings_prep_var = tk.IntVar(value=default_prep)

        self.settings_prep_spinner = tk.Spinbox(
            center_frame, from_=1, to=20, width=5,
            font=("Arial", 14),
            textvariable=self.settings_prep_var,
            justify="center",
        )
        self.settings_prep_spinner.grid(row=0, column=1, sticky="w", padx=20, pady=(25, 10))

        self.settings_prep_desc_var = tk.StringVar(
            value="How long you have to read and prepare before teaching (1–20 minutes)"
        )
        self.settings_prep_desc = tk.Label(
            center_frame, textvariable=self.settings_prep_desc_var,
            font=("Arial", 9), fg="#888", bg="#f5f5f5", anchor="w"
        )
        self.settings_prep_desc.grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 20))
        self._register_dir_label(self.settings_prep_desc, 1, 0, padx=20, pady=(0, 20))

        # --- Teaching Time ---
        self.settings_teach_label = tk.Label(
            center_frame, text="Teaching Session Time (minutes):",
            font=("Arial", 12), bg="#f5f5f5", anchor="w"
        )
        self.settings_teach_label.grid(row=2, column=0, sticky="w", padx=20, pady=(10, 10))
        self._register_dir_label(self.settings_teach_label, 2, 0, padx=20, pady=(10, 10))

        default_teach = int(config.default_teaching_minutes)
        default_teach = max(3, min(60, default_teach))
        self.settings_teach_var = tk.IntVar(value=default_teach)

        self.settings_teach_spinner = tk.Spinbox(
            center_frame, from_=3, to=60, width=5,
            font=("Arial", 14),
            textvariable=self.settings_teach_var,
            justify="center",
        )
        self.settings_teach_spinner.grid(row=2, column=1, sticky="w", padx=20, pady=(10, 10))

        self.settings_teach_desc_var = tk.StringVar(
            value="How long the teaching conversation lasts (3–60 minutes)"
        )
        self.settings_teach_desc = tk.Label(
            center_frame, textvariable=self.settings_teach_desc_var,
            font=("Arial", 9), fg="#888", bg="#f5f5f5", anchor="w"
        )
        self.settings_teach_desc.grid(row=3, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 25))
        self._register_dir_label(self.settings_teach_desc, 3, 0, padx=20, pady=(0, 25))

        # Topic info (shows which topic was generated/loaded)
        self.settings_topic_var = tk.StringVar(value="")
        self.settings_topic_label = tk.Label(
            frame, textvariable=self.settings_topic_var,
            font=("Arial", 10, "italic"), fg="#555", anchor="w"
        )
        self.settings_topic_label.grid(row=3, column=0, sticky="w", padx=20, pady=(0, 5))
        self._register_dir_label(self.settings_topic_label, 3, 0, padx=20, pady=(0, 5))

        # Buttons
        self.settings_btn_frame = tk.Frame(frame)
        self.settings_btn_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=15)

        self.settings_start_btn = tk.Button(
            self.settings_btn_frame, text="Start Learning", font=("Arial", 12, "bold"),
            bg=COLORS["green_btn"], fg="white", width=18,
            command=self._on_settings_start
        )
        # Semantic role for theming (fix hover stuck in light theme on Windows)
        self.settings_start_btn._btn_role = "primary"
        self.settings_start_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.settings_back_btn = tk.Button(
            self.settings_btn_frame, text="Back to Setup", font=("Arial", 10),
            bg=COLORS["gray_btn"], fg="white", width=14,
            command=lambda: self._show_screen("setup")
        )
        # Semantic role for theming (fix hover stuck in light theme on Windows)
        self.settings_back_btn._btn_role = "secondary"
        self.settings_back_btn.pack(side=tk.LEFT)

        self._register_dir_btn_frame(
            self.settings_btn_frame,
            [self.settings_start_btn, self.settings_back_btn]
        )

    def _update_settings_labels(self):
        """Update settings screen labels for language change."""
        if self.lang == "he":
            self.settings_title_var.set("הגדרות למידה")
            self.settings_desc_var.set("הגדר את זמני ההכנה וההוראה שלך:")
            self.settings_prep_label.config(text="זמן הכנה (דקות):")
            self.settings_prep_desc_var.set("(1-20 דקות) כמה זמן יש לך לקרוא ולהתכונן לפני ההוראה")
            self.settings_teach_label.config(text="זמן הוראה (דקות):")
            self.settings_teach_desc_var.set("(3-60 דקות) כמה זמן נמשכת שיחת ההוראה")
            self.settings_start_btn.config(text="התחל ללמוד")
            self.settings_back_btn.config(text="חזרה להגדרות")
        else:
            self.settings_title_var.set("Learning Settings")
            self.settings_desc_var.set("Configure your preparation and teaching session times:")
            self.settings_prep_label.config(text="Preparation Time (minutes):")
            self.settings_prep_desc_var.set("How long you have to read and prepare before teaching(1–20 minutes)")
            self.settings_teach_label.config(text="Teaching Session Time (minutes):")
            self.settings_teach_desc_var.set("How long the teaching conversation lasts (3–60 minutes)")
            self.settings_start_btn.config(text="Start Learning")
            self.settings_back_btn.config(text="Back to Setup")

        # Update topic info
        if self.topic_config:
            topic = self.topic_config.get_topic_name(self.lang) or self.topic_config.get_topic_name("en")
            if self.lang == "he":
                self.settings_topic_var.set(self._bidi("נושא: {}", topic))
            else:
                self.settings_topic_var.set(f"Topic: {topic}")

    def _on_settings_start(self):
        """Read settings values and proceed to lesson screen."""
        # --- 1) Read + validate (allow manual typing) ---
        try:
            if hasattr(self, "settings_prep_var"):
                prep = int(self.settings_prep_var.get())
            else:
                prep = int(self.settings_prep_spinner.get())

            if hasattr(self, "settings_teach_var"):
                teach = int(self.settings_teach_var.get())
            else:
                teach = int(self.settings_teach_spinner.get())
        except Exception:
            messagebox.showwarning("Invalid input", "Please enter valid numbers for times.")
            return

        # --- 2) Clamp to allowed ranges ---
        prep = max(1, min(20, prep))      # preparation: 1–20
        teach = max(3, min(60, teach))    # teaching: 3–60

        # --- 3) Write clamped values back into UI ---
        if hasattr(self, "settings_prep_var"):
            self.settings_prep_var.set(prep)
        else:
            self.settings_prep_spinner.delete(0, tk.END)
            self.settings_prep_spinner.insert(0, str(prep))

        if hasattr(self, "settings_teach_var"):
            self.settings_teach_var.set(teach)
        else:
            self.settings_teach_spinner.delete(0, tk.END)
            self.settings_teach_spinner.insert(0, str(teach))

        # --- 4) Save into app state ---
        self.lesson_minutes = prep
        self.teaching_minutes = teach

        # --- 5) Update topic info before moving on  ---
        if self.topic_config:
            topic = self.topic_config.get_topic_name(self.lang) or self.topic_config.get_topic_name("en")
            if self.lang == "he":
                self.settings_topic_var.set(self._bidi("נושא: {}", topic))
            else:
                self.settings_topic_var.set(f"Topic: {topic}")

        # --- 6) Move to lesson screen  ---
        self._populate_lesson_screen()
        self._show_screen("lesson")

        # ================================================================
        # SCREEN 3: LESSON (Preparation)
        # ================================================================

    def _build_lesson_screen(self):
        frame = tk.Frame(self.root)
        self.screens["lesson"] = frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        # Top bar
        self.lesson_title_var = tk.StringVar(value="Preparation")
        self.lesson_timer_var = tk.StringVar(value="03:00")
        top_bar, self.lesson_lang_btn, self.lesson_timer_label = self._make_top_bar(
            frame, self.lesson_title_var, self.lesson_timer_var
        )
        top_bar.grid(row=0, column=0, sticky="ew")

        # Info label
        self.lesson_info_var = tk.StringVar(value="Read the material below before teaching")
        self.lesson_info_label = tk.Label(
            frame, textvariable=self.lesson_info_var,
            font=("Arial", 9), fg="#888", anchor="w"
        )
        self.lesson_info_label.grid(row=1, column=0, sticky="w", padx=12, pady=(2, 0))
        self._register_dir_label(self.lesson_info_label, 1, 0, padx=12, pady=(2, 0))

        # Content area
        content_frame = tk.Frame(frame)
        content_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)

        self.lesson_display = scrolledtext.ScrolledText(
            content_frame, wrap=tk.WORD, font=("Arial", 11),
            state=tk.DISABLED, bg="#f0f8ff", relief=tk.GROOVE, borderwidth=2
        )
        self.lesson_display.grid(row=0, column=0, sticky="nsew")
        self.lesson_display.tag_configure("heading", font=("Arial", 12, "bold"), foreground="#1a237e")
        self.lesson_display.tag_configure("item", font=("Arial", 11), foreground="#333333")
        self.lesson_display.tag_configure("warning", font=("Arial", 11), foreground="#c62828")

        # Buttons
        self.lesson_btn_frame = tk.Frame(frame)
        self.lesson_btn_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=10)

        self.start_teaching_btn = tk.Button(
            self.lesson_btn_frame, text="Start Teaching", font=("Arial", 11, "bold"),
            bg=COLORS["green_btn"], fg="white", width=16, state=tk.NORMAL,
            command=self._on_start_teaching
        )
        self.start_teaching_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.back_to_settings_btn = tk.Button(
            self.lesson_btn_frame, text="Back to Settings", font=("Arial", 10),
            bg=COLORS["gray_btn"], fg="white", width=14,
            command=lambda: self._show_screen("settings")
        )
        self.back_to_settings_btn.pack(side=tk.LEFT)

        # Save topic button (floats to opposite side)
        self.save_topic_btn = tk.Button(
            self.lesson_btn_frame, text="Save Topic", font=("Arial", 10),
            bg=COLORS["purple_btn"], fg="white", width=12,
            command=self._on_save_topic
        )
        self.save_topic_btn.pack(side=tk.RIGHT)

        self._register_dir_btn_frame(
            self.lesson_btn_frame,
            [self.start_teaching_btn, self.back_to_settings_btn],
            special_right_btn=self.save_topic_btn
        )

    def _populate_lesson_screen(self):
        if not self.topic_config:
            return

        tc = self.topic_config
        lang = self.lang

        topic = tc.get_topic_name(lang) or tc.get_topic_name("en")
        if lang == "he":
            self.lesson_title_var.set(self._bidi("הכנה: {}", topic))
            self.start_teaching_btn.config(text="התחל ללמד")
            self.back_to_settings_btn.config(text="חזרה להגדרות")
            self.save_topic_btn.config(text="שמור נושא")
        else:
            self.lesson_title_var.set(f"Preparation: {topic}")
            self.start_teaching_btn.config(text="Start Teaching")
            self.back_to_settings_btn.config(text="Back to Settings")
            self.save_topic_btn.config(text="Save Topic")

        self.lesson_display.config(state=tk.NORMAL)
        self.lesson_display.delete("1.0", tk.END)

        # Key Concepts
        heading = "מושגי מפתח:" if lang == "he" else "KEY CONCEPTS:"
        self.lesson_display.insert(tk.END, f"{heading}\n", "heading")
        for c in tc.get_key_concepts(lang) or tc.get_key_concepts("en"):
            self.lesson_display.insert(tk.END, f"  • {c}\n", "item")

        # Key Terms
        heading = "\nמונחים חשובים:" if lang == "he" else "\nKEY TERMS:"
        self.lesson_display.insert(tk.END, f"{heading}\n", "heading")
        for t in tc.get_key_terms(lang) or tc.get_key_terms("en"):
            self.lesson_display.insert(tk.END, f"  • {t}\n", "item")

        # Misconceptions
        heading = "\nתפיסות שגויות נפוצות — שימו לב!" if lang == "he" else "\nCOMMON MISCONCEPTIONS — Watch For:"
        self.lesson_display.insert(tk.END, f"{heading}\n", "heading")
        for m in tc.get_misconceptions(lang) or tc.get_misconceptions("en"):
            self.lesson_display.insert(tk.END, f"  ⚠ {m}\n", "warning")

        # Lesson summary
        heading = "\nסיכום:" if lang == "he" else "\nLESSON SUMMARY:"
        self.lesson_display.insert(tk.END, f"{heading}\n", "heading")
        summary = tc.get_lesson_summary(lang) or tc.get_lesson_summary("en")
        self.lesson_display.insert(tk.END, f"{summary}\n", "item")

        self.lesson_display.config(state=tk.DISABLED)

        # Apply direction to newly inserted text
        self._apply_direction()

        # Start lesson timer
        self._start_lesson_timer()

    def _start_lesson_timer(self):
        self._stop_lesson_timer()
        self.lesson_seconds_left = self.lesson_minutes * 60
        self.lesson_timer_running = True
        self.lesson_timer_label.config(fg=COLORS["timer_green"])
        self._tick_lesson_timer()

    def _tick_lesson_timer(self):
        if not self.lesson_timer_running:
            return
        m, s = divmod(self.lesson_seconds_left, 60)
        self.lesson_timer_var.set(f"{m:02d}:{s:02d}")
        if self.lesson_seconds_left <= 0:
            self.lesson_timer_running = False
            self.lesson_timer_var.set("00:00")
            self.lesson_info_var.set(
                "הזמן נגמר — עוברים ללימוד..." if self.lang == "he"
                else "Time is up — starting teaching..."
            )
            self.root.after(200, self._auto_start_teaching)
            return
        if self.lesson_seconds_left <= 30:
            self.lesson_timer_label.config(fg=COLORS["timer_orange"])
        self.lesson_seconds_left -= 1
        self.lesson_timer_after_id = self.root.after(1000, self._tick_lesson_timer)


    def _auto_start_teaching(self):
        if getattr(self, "current_screen", None) != "lesson":
            return
        self._on_start_teaching()

    def _stop_lesson_timer(self):
        self.lesson_timer_running = False
        if self.lesson_timer_after_id:
            self.root.after_cancel(self.lesson_timer_after_id)
            self.lesson_timer_after_id = None

    def _on_start_teaching(self):
        self._stop_lesson_timer()
        self._initialize_chat()
        self._show_screen("chat")

    def _on_save_topic(self):
        if not self.topic_config:
            return
        filepath = filedialog.asksaveasfilename(
            title="Save Topic Configuration",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile=f"topic_{self.topic_config.topic_name_en.replace(' ', '_').lower()}.json"
        )
        if filepath:
            self.topic_config.save_to_file(filepath)
            messagebox.showinfo("Saved", f"Topic saved to {filepath}")

    # ================================================================
    # SCREEN 4: CHAT (Teaching Session)
    # ================================================================

    def _build_chat_screen(self):
        frame = tk.Frame(self.root)
        self.screens["chat"] = frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=3)
        frame.rowconfigure(7, weight=1)

        # Top bar
        self.chat_title_var = tk.StringVar(value="Teaching Session")
        self.chat_timer_var = tk.StringVar(value="10:00")
        top_bar, self.chat_lang_btn, self.chat_timer_label = self._make_top_bar(
            frame, self.chat_title_var, self.chat_timer_var
        )
        top_bar.grid(row=0, column=0, sticky="ew")

        # Timer info
        self.chat_info_var = tk.StringVar(value="Timer starts when you send your first message")
        self.chat_info_label = tk.Label(
            frame, textvariable=self.chat_info_var,
            font=("Arial", 9), fg="#888", anchor="w"
        )
        self.chat_info_label.grid(row=1, column=0, sticky="w", padx=12, pady=(2, 0))
        self._register_dir_label(self.chat_info_label, 1, 0, padx=12, pady=(2, 0))

        # Chat display
        chat_frame = tk.Frame(frame)
        chat_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(5, 5))
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)

        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, wrap=tk.WORD, font=("Arial", 11),
            state=tk.DISABLED, bg="#fafafa", relief=tk.GROOVE, borderwidth=2
        )
        self.chat_display.grid(row=0, column=0, sticky="nsew")
        self.chat_display.tag_configure("student", foreground="#1565C0", font=("Arial", 11))
        self.chat_display.tag_configure("teacher", foreground="#2E7D32", font=("Arial", 11))
        self.chat_display.tag_configure("label_student", foreground="#1565C0", font=("Arial", 11, "bold"))
        self.chat_display.tag_configure("label_teacher", foreground="#2E7D32", font=("Arial", 11, "bold"))
        self.chat_display.tag_configure("system", foreground="#757575", font=("Arial", 10, "italic"))
        self.chat_display.tag_configure("time_up", foreground="#C62828", font=("Arial", 12, "bold"))
        self._install_text_context_menu(self.chat_display)
        self._install_clipboard_shortcuts(self.chat_display)

        # Input area
        input_frame = tk.Frame(frame)
        input_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        input_frame.columnconfigure(0, weight=1)

        self.input_field = tk.Entry(input_frame, font=("Arial", 12), relief=tk.GROOVE, borderwidth=2)
        self.input_field.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.input_field.bind("<Return>", self._on_send)

        self._install_entry_context_menu(self.input_field)
        self._install_entry_clipboard_shortcuts(self.input_field)

        self.send_btn = tk.Button(
            input_frame, text="Send", font=("Arial", 11, "bold"),
            bg=COLORS["green_btn"], fg="white", width=8, command=self._on_send
        )
        self.send_btn._btn_role = "primary"
        self.send_btn.grid(row=0, column=1)

        # Action buttons
        self.chat_btn_frame = tk.Frame(frame)
        self.chat_btn_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=5)

        self.mentor_btn = tk.Button(self.chat_btn_frame, text="Ask Mentor", font=("Arial", 10),
                                     bg=COLORS["orange_btn"], fg="white", width=13, command=self._on_ask_mentor)
        self.mentor_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.eval_btn = tk.Button(self.chat_btn_frame, text="Get Evaluation", font=("Arial", 10),
                                   bg=COLORS["pink_btn"], fg="white", width=13, command=self._on_evaluate)
        self.eval_btn._btn_role = "secondary"
        self.eval_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.summary_btn = tk.Button(self.chat_btn_frame, text="Summary", font=("Arial", 10),
                                      bg=COLORS["purple_btn"], fg="white", width=10, command=self._on_show_summary)
        self.summary_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.new_conv_btn = tk.Button(self.chat_btn_frame, text="Restart", font=("Arial", 10),
                                       bg=COLORS["gray_btn"], fg="white", width=10, command=self._on_restart_chat)
        self.new_conv_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.back_setup_btn2 = tk.Button(self.chat_btn_frame, text="New Topic", font=("Arial", 10),
                                          bg="#455A64", fg="white", width=10,
                                          command=self._on_back_to_setup)
        self.back_setup_btn2.pack(side=tk.LEFT)

        self.copy_chat_btn = tk.Button(
            self.chat_btn_frame, text="Copy Chat", font=("Arial", 10),
            bg="#546E7A", fg="white", width=10, command=self._on_copy_chat
        )
        self.copy_chat_btn.pack(side=tk.LEFT, padx=(5, 0))

        self._register_dir_btn_frame(
            self.chat_btn_frame,
            [self.mentor_btn, self.eval_btn, self.summary_btn, self.new_conv_btn, self.back_setup_btn2, self.copy_chat_btn]
        )

        # Animated progress bar for chat LLM calls (Sprint 3)
        # grid_row=6: sits between the mentor label (row 5) and mentor panel (row 7)
        # No cancel button — mid-chat cancellation would corrupt conversation history
        self.chat_progress = AnimatedStatusBar(frame, grid_row=6)

        # Mentor panel label
        self.mentor_label_var = tk.StringVar(value="Mentor / Summary:")
        self.mentor_label = tk.Label(
            frame, textvariable=self.mentor_label_var,
            font=("Arial", 10, "bold"), anchor="w"
        )
        self.mentor_label.grid(row=5, column=0, sticky="w", padx=12, pady=(5, 0))
        self._register_dir_label(self.mentor_label, 5, 0, padx=12, pady=(5, 0))

        # Mentor panel
        mentor_frame = tk.Frame(frame)
        mentor_frame.grid(row=7, column=0, sticky="nsew", padx=10, pady=(0, 5))
        mentor_frame.columnconfigure(0, weight=1)
        mentor_frame.rowconfigure(0, weight=1)

        self.mentor_panel = scrolledtext.ScrolledText(
            mentor_frame, wrap=tk.WORD, font=("Arial", 10),
            state=tk.DISABLED, bg="#FFF8E1", height=5, relief=tk.GROOVE, borderwidth=2
        )
        self.mentor_panel.grid(row=0, column=0, sticky="nsew")
        self.mentor_panel.tag_configure("mentor", foreground="#E65100")
        self.mentor_panel.tag_configure("summary", foreground="#4A148C")
        self.mentor_panel.tag_configure("error", foreground="#C62828")

        # Status bar
        self.chat_status_var = tk.StringVar(value="Ready")
        self.chat_status_label = tk.Label(
            frame, textvariable=self.chat_status_var,
            font=("Arial", 9), fg="#555555", relief=tk.SUNKEN,
            anchor="w", padx=10, pady=3
        )
        self.chat_status_label.grid(row=8, column=0, sticky="ew")
        self._register_dir_label(self.chat_status_label, 8, 0)

    # ================================================================
    # CHAT HELPERS
    # ================================================================

    def _append_chat(self, sender: str, text: str, tag: str = "system"):
        """Append a message to the chat display."""
        self.chat_display.config(state=tk.NORMAL)
        if sender:
            label_tag = f"label_{tag}" if f"label_{tag}" in self.chat_display.tag_names() else tag
            self.chat_display.insert(tk.END, f"{sender}: ", label_tag)
            self.chat_display.insert(tk.END, f"{text}\n\n", tag)
        else:
            self.chat_display.insert(tk.END, f"{text}\n\n", tag)
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def _set_mentor_panel(self, text: str, tag: str = "mentor"):
        """Set the content of the mentor/summary panel."""
        self.mentor_panel.config(state=tk.NORMAL)
        self.mentor_panel.delete("1.0", tk.END)
        self.mentor_panel.insert(tk.END, text, tag)
        self.mentor_panel.config(state=tk.DISABLED)

    def _set_input_enabled(self, enabled: bool):
        """Enable or disable chat input controls."""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.input_field.config(state=state)
        self.send_btn.config(state=state)
        self.mentor_btn.config(state=state)

    def _initialize_chat(self):
        """Initialize the ConversationManager and start a new chat session."""
        self.manager = ConversationManager(lang=self.lang, topic_config=self.topic_config)
        self.session_ended = False
        self.chat_timer_running = False
        self.chat_seconds_left = self.teaching_minutes * 60

        # Reset displays
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.config(state=tk.DISABLED)
        self._set_mentor_panel("")

        # Update timer display
        m, s = divmod(self.chat_seconds_left, 60)
        self.chat_timer_var.set(f"{m:02d}:{s:02d}")
        if self.chat_timer_label:
            self.chat_timer_label.config(fg=COLORS["timer_green"])

        # Enable input
        self._set_input_enabled(True)
        self.eval_btn.config(state=tk.NORMAL)

        # Update title
        topic = self.topic_config.get_topic_name(self.lang) or self.topic_config.get_topic_name("en")
        if self.lang == "he":
            self.chat_title_var.set(self._bidi("שיעור: {}", topic))
        else:
            self.chat_title_var.set(f"Teaching: {topic}")

        self.chat_info_var.set(
            "הטיימר מתחיל כשתשלח את ההודעה הראשונה" if self.lang == "he"
            else "Timer starts when you send your first message"
        )

        # Apply direction for the fresh chat
        self._apply_direction()

        # Start conversation — get student's opening message
        try:
            initial_msg = self.manager.start_conversation()
            student_label = "תלמיד" if self.lang == "he" else "Student"
            self._append_chat(student_label, initial_msg, "student")
            self._update_chat_status()
        except Exception as e:
            self._append_chat("", f"Error starting conversation: {e}", "system")

    def _update_chat_status(self):
        """Update the status bar with current conversation stats."""
        if self.manager:
            summary = self.manager.get_conversation_summary()
            lang = self.lang
            if lang == "he":
                self.chat_status_var.set(
                    f"[{lang.upper()}] {RLM}תור {summary['turns']} | "
                    f"הסברים: {summary['student_messages']} | "
                    f"ייעוץ מנטור: {summary['mentor_consultations']}"
                )
            else:
                self.chat_status_var.set(
                    f"[{lang.upper()}] Turn {summary['turns']} | "
                    f"Explanations: {summary['student_messages']} | "
                    f"Mentor consultations: {summary['mentor_consultations']}"
                )

    # ================================================================
    # CHAT ACTIONS
    # ================================================================

    def _on_send(self, event=None):
        """Handle sending a message to the struggling student."""
        if self.is_processing or self.session_ended:
            return

        text = self.input_field.get().strip()
        if not text:
            return

        # Clear input
        self.input_field.delete(0, tk.END)

        # Start timer on first message
        if not self.chat_timer_running and self.chat_seconds_left > 0:
            self._start_chat_timer()

        # Show teacher message
        teacher_label = "אתה" if self.lang == "he" else "You"
        self._append_chat(teacher_label, text, "teacher")

        # Disable input while waiting and show progress (Sprint 3)
        self.is_processing = True
        self._set_input_enabled(False)
        self.mentor_btn.config(state=tk.DISABLED)
        msg = "התלמיד חושב" if self.lang == "he" else "Student is thinking"
        self.chat_progress.show(msg)
        self.chat_status_var.set("")

        def api_call():
            try:
                response = self.manager.send_to_student(text)
                self.root.after(0, lambda: self._on_student_response(response))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda msg=err_msg: self._on_api_error(msg))

        threading.Thread(target=api_call, daemon=True).start()

    def _on_student_response(self, response: str):
        """Handle response from the struggling student."""
        self.chat_progress.hide()
        student_label = "תלמיד" if self.lang == "he" else "Student"
        self._append_chat(student_label, response, "student")
        self.is_processing = False
        if not self.session_ended:
            self._set_input_enabled(True)
            self.mentor_btn.config(state=tk.NORMAL)
            self.input_field.focus_set()
        self._update_chat_status()

    def _on_api_error(self, error_msg: str):
        """Handle API errors."""
        self.chat_progress.hide()
        logger.error("API error during chat: %s", error_msg)
        self._append_chat("", f"Error: {error_msg}", "system")
        self._set_mentor_panel(f"Error: {error_msg}", "error")
        self.is_processing = False
        if not self.session_ended:
            self._set_input_enabled(True)
            self.mentor_btn.config(state=tk.NORMAL)

    def _on_ask_mentor(self):
        """Get coaching advice from the mentor agent."""
        if self.is_processing or not self.manager:
            return

        # Get context
        last_student_msg = self.manager.get_last_student_message()
        history = self.manager.get_student_history()
        last_teacher_msg = ""
        for msg in reversed(history):
            if msg["role"] == "user":
                last_teacher_msg = msg["content"]
                break

        if not last_teacher_msg:
            no_msg = "שלח הודעה אחת לפחות לפני שתתייעץ עם המנטור." if self.lang == "he" \
                else "Send at least one message before consulting the mentor."
            self._set_mentor_panel(no_msg, "error")
            return

        self.is_processing = True
        self.mentor_btn.config(state=tk.DISABLED)
        self.send_btn.config(state=tk.DISABLED)
        msg = "מתייעץ עם המנטור" if self.lang == "he" else "Consulting mentor"
        self.chat_progress.show(msg)
        self._set_mentor_panel("", "mentor")

        def api_call():
            try:
                advice = self.manager.consult_mentor(last_teacher_msg, last_student_msg)
                self.root.after(0, lambda: self._on_mentor_response(advice))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda msg=err_msg: self._on_mentor_error(msg))

        threading.Thread(target=api_call, daemon=True).start()

    def _on_mentor_response(self, advice: str):
        """Handle response from the mentor."""
        self.chat_progress.hide()
        self._set_mentor_panel(advice, "mentor")
        self.is_processing = False
        if not self.session_ended:
            self.mentor_btn.config(state=tk.NORMAL)
            self.send_btn.config(state=tk.NORMAL)
        self._update_chat_status()

    def _on_mentor_error(self, error_msg: str):
        """Handle mentor API errors."""
        self.chat_progress.hide()
        logger.error("Mentor API error: %s", error_msg)
        self._set_mentor_panel(f"Mentor error: {error_msg}", "error")
        self.is_processing = False
        if not self.session_ended:
            self.mentor_btn.config(state=tk.NORMAL)
            self.send_btn.config(state=tk.NORMAL)

    def _on_evaluate(self):
        """Trigger performance evaluation."""
        if self.is_processing or not self.manager:
            return

        self.is_processing = True
        self.eval_btn.config(state=tk.DISABLED)
        self.mentor_btn.config(state=tk.DISABLED)
        self._set_input_enabled(False)

        msg = "מבצע הערכה" if self.lang == "he" else "Evaluating performance"
        self.chat_progress.show(msg)
        self.chat_status_var.set("")

        def api_call():
            try:
                evaluation = self.manager.evaluate_performance()
                self.root.after(0, lambda: self._on_evaluation_result(evaluation))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda msg=err_msg: self._on_evaluation_error(msg))

        threading.Thread(target=api_call, daemon=True).start()

    def _on_evaluation_result(self, evaluation):
        """Handle evaluation result — show on evaluation screen."""
        self.chat_progress.hide()
        self.is_processing = False
        self.session_ended = True
        self._stop_chat_timer()

        # Populate and show evaluation screen
        self._populate_evaluation_screen(evaluation)
        self._show_screen("evaluation")

    def _on_evaluation_error(self, error_msg: str):
        """Handle evaluation API errors."""
        self.chat_progress.hide()
        logger.error("Evaluation API error: %s", error_msg)
        self._set_mentor_panel(f"Evaluation error: {error_msg}", "error")
        self.is_processing = False
        self.eval_btn.config(state=tk.NORMAL)
        self.mentor_btn.config(state=tk.NORMAL)
        if not self.session_ended:
            self._set_input_enabled(True)

    def _on_show_summary(self):
        """Show conversation summary in the mentor panel."""
        if not self.manager:
            return
        summary = self.manager.get_conversation_summary()
        if self.lang == "he":
            text = (
                f"{RLM}📊 סיכום שיחה:\n"
                f"  • תורות: {summary['turns']}\n"
                f"  • הסברים שנשלחו: {summary['student_messages']}\n"
                f"  • ייעוצי מנטור: {summary['mentor_consultations']}\n"
                f"  • סטטוס: {'פעיל' if summary['is_active'] else 'לא פעיל'}"
            )
        else:
            text = (
                f"📊 Conversation Summary:\n"
                f"  • Turns: {summary['turns']}\n"
                f"  • Explanations sent: {summary['student_messages']}\n"
                f"  • Mentor consultations: {summary['mentor_consultations']}\n"
                f"  • Status: {'Active' if summary['is_active'] else 'Inactive'}"
            )
        self._set_mentor_panel(text, "summary")

    def _on_copy_chat(self):
        """Copy the visible chat transcript to the clipboard."""
        transcript = self.chat_display.get("1.0", "end-1c").strip()
        if not transcript:
            self.chat_status_var.set("Nothing to copy")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(transcript)
            self.root.update_idletasks()
            self.chat_status_var.set("Chat copied to clipboard")
        except Exception as e:
            logger.error("Failed to copy chat transcript: %s", e)
            self.chat_status_var.set("Copy failed")

    def _on_restart_chat(self):
        """Restart the chat session with the same topic."""
        if self.is_processing:
            return
        self._stop_chat_timer()
        self._initialize_chat()

    def _on_back_to_setup(self):
        """Go back to the setup screen for a new topic."""
        if self.is_processing:
            return
        self._stop_chat_timer()
        self.session_ended = False
        self.manager = None
        self._show_screen("setup")

    # ================================================================
    # CHAT TIMER
    # ================================================================

    def _start_chat_timer(self):
        """Start the teaching session countdown timer."""
        self.chat_timer_running = True
        self.chat_info_var.set(
            "הטיימר פועל!" if self.lang == "he" else "Timer is running!"
        )
        if self.chat_timer_label:
            self.chat_timer_label.config(fg=COLORS["timer_green"])
        self._tick_chat_timer()

    def _tick_chat_timer(self):
        """Update the timer every second."""
        if not self.chat_timer_running:
            return

        m, s = divmod(self.chat_seconds_left, 60)
        self.chat_timer_var.set(f"{m:02d}:{s:02d}")

        if self.chat_seconds_left <= 0:
            self.chat_timer_running = False
            self._on_chat_time_up()
            return

        # Color changes based on time remaining
        if self.chat_seconds_left <= 60:
            if self.chat_timer_label:
                self.chat_timer_label.config(fg=COLORS["timer_red"])
        elif self.chat_seconds_left <= self.teaching_minutes * 60 * 0.3:
            if self.chat_timer_label:
                self.chat_timer_label.config(fg=COLORS["timer_orange"])

        self.chat_seconds_left -= 1
        self.chat_timer_after_id = self.root.after(1000, self._tick_chat_timer)

    def _stop_chat_timer(self):
        """Stop the chat timer."""
        self.chat_timer_running = False
        if self.chat_timer_after_id:
            self.root.after_cancel(self.chat_timer_after_id)
            self.chat_timer_after_id = None

    def _on_chat_time_up(self):
        """Handle time expiration — lock input and auto-evaluate."""
        self.session_ended = True
        self._set_input_enabled(False)

        time_up_msg = "⏰ הזמן נגמר!" if self.lang == "he" else "⏰ Time is up!"
        self._append_chat("", time_up_msg, "time_up")
        self.chat_info_var.set(
            "הזמן נגמר — מבצע הערכה..." if self.lang == "he"
            else "Time's up — evaluating performance..."
        )

        # Auto-trigger evaluation
        self._on_evaluate()

    # ================================================================
    # CHAT LABELS UPDATE (language toggle)
    # ================================================================

    def _update_chat_labels(self):
        """Update chat screen labels for language change."""
        if self.lang == "he":
            self.send_btn.config(text="שלח")
            self.mentor_btn.config(text="שאל מנטור")
            self.eval_btn.config(text="קבל הערכה")
            self.summary_btn.config(text="סיכום")
            self.new_conv_btn.config(text="התחל מחדש")
            self.back_setup_btn2.config(text="נושא חדש")
            self.mentor_label_var.set("מנטור / סיכום:")
            if not self.chat_timer_running and not self.session_ended:
                self.chat_info_var.set("הטיימר מתחיל כשתשלח את ההודעה הראשונה")
            if self.topic_config:
                topic = self.topic_config.get_topic_name("he") or self.topic_config.get_topic_name("en")
                self.chat_title_var.set(self._bidi("שיעור: {}", topic))
        else:
            self.send_btn.config(text="Send")
            self.mentor_btn.config(text="Ask Mentor")
            self.eval_btn.config(text="Get Evaluation")
            self.summary_btn.config(text="Summary")
            self.new_conv_btn.config(text="Restart")
            self.back_setup_btn2.config(text="New Topic")
            self.mentor_label_var.set("Mentor / Summary:")
            if not self.chat_timer_running and not self.session_ended:
                self.chat_info_var.set("Timer starts when you send your first message")
            if self.topic_config:
                topic = self.topic_config.get_topic_name("en")
                self.chat_title_var.set(f"Teaching: {topic}")
        self._update_chat_status()

    # ================================================================
    # SCREEN 5: EVALUATION
    # ================================================================

    def _build_evaluation_screen(self):
        """Build the evaluation results screen."""
        frame = tk.Frame(self.root)
        self.screens["evaluation"] = frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        # Top bar
        self.eval_title_var = tk.StringVar(value="Performance Evaluation")
        top_bar, self.eval_lang_btn, _ = self._make_top_bar(frame, self.eval_title_var)
        top_bar.grid(row=0, column=0, sticky="ew")

        # Summary info
        self.eval_info_var = tk.StringVar(value="")
        self.eval_info_label = tk.Label(
            frame, textvariable=self.eval_info_var,
            font=("Arial", 10), fg="#555", anchor="w"
        )
        self.eval_info_label.grid(row=1, column=0, sticky="w", padx=12, pady=(5, 0))
        self._register_dir_label(self.eval_info_label, 1, 0, padx=12, pady=(5, 0))

        # Evaluation content
        eval_frame = tk.Frame(frame)
        eval_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        eval_frame.columnconfigure(0, weight=1)
        eval_frame.rowconfigure(0, weight=1)

        self.eval_display = scrolledtext.ScrolledText(
            eval_frame, wrap=tk.WORD, font=("Arial", 11),
            state=tk.DISABLED, bg="#F3E5F5", relief=tk.GROOVE, borderwidth=2
        )
        self.eval_display.grid(row=0, column=0, sticky="nsew")
        self.eval_display.tag_configure("heading", font=("Arial", 13, "bold"), foreground="#4A148C")
        self.eval_display.tag_configure("score", font=("Consolas", 12, "bold"), foreground="#1B5E20")
        self.eval_display.tag_configure("feedback", font=("Arial", 11), foreground="#333333")

        # Buttons
        self.eval_btn_frame = tk.Frame(frame)
        self.eval_btn_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=10)

        self.eval_retry_btn = tk.Button(
            self.eval_btn_frame, text="Try Again (Same Topic)", font=("Arial", 11, "bold"),
            bg=COLORS["green_btn"], fg="white", width=22,
            command=self._on_eval_retry
        )
        self.eval_retry_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.eval_new_btn = tk.Button(
            self.eval_btn_frame, text="New Topic", font=("Arial", 10),
            bg=COLORS["blue_btn"], fg="white", width=14,
            command=self._on_eval_new_topic
        )
        self.eval_new_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.eval_save_btn = tk.Button(
            self.eval_btn_frame, text="Save Results", font=("Arial", 10),
            bg=COLORS["purple_btn"], fg="white", width=14,
            command=self._on_save_evaluation
        )
        self.eval_save_btn.pack(side=tk.LEFT)

        self._register_dir_btn_frame(
            self.eval_btn_frame,
            [self.eval_retry_btn, self.eval_new_btn, self.eval_save_btn]
        )

    def _format_component_label(self, key: str) -> str:
        """Turn component keys into readable labels for display."""
        return key.replace("_", " ").title()

    def _format_evaluation_text(self, evaluation_result) -> str:
        """Format structured evaluation data into readable text for UI/save."""
        if isinstance(evaluation_result, str):
            return evaluation_result
        if not isinstance(evaluation_result, dict):
            return "No evaluation available."

        lines = []
        total = evaluation_result.get("total_score", 0)
        max_score = evaluation_result.get("max_score", 0)
        level = evaluation_result.get("performance_level", "Unclassified")
        lines.append(f"Total Score: {total}/{max_score}")
        lines.append(f"Performance Level: {level}")
        lines.append("")
        lines.append("Component Scores:")

        component_scores = evaluation_result.get("component_scores", {})
        if isinstance(component_scores, dict) and component_scores:
            for key, value in component_scores.items():
                lines.append(f"- {self._format_component_label(key)}: {value}/2")
        else:
            lines.append("- No component scores available")

        lines.append("")
        lines.append(f"Correct Components: {evaluation_result.get('components_correct_count', 0)}")
        lines.append(f"Misconceptions Count: {evaluation_result.get('misconceptions_count', 0)}")

        comparison = evaluation_result.get("comparison", {})
        if isinstance(comparison, dict):
            lines.append("")
            lines.append("Improvement Analysis:")
            improvement = comparison.get("improvement")
            if isinstance(improvement, dict):
                lines.append(f"- Score Delta: {improvement.get('score_delta', 0)}")
                lines.append(
                    f"- Correct Components Delta: {improvement.get('correct_components_delta', 0)}"
                )
                lines.append(f"- Misconceptions Delta: {improvement.get('misconceptions_delta', 0)}")
            else:
                reason = comparison.get("reason") or "Not enough data for comparison."
                lines.append(f"- {reason}")

        notes = evaluation_result.get("notes", "")
        if notes:
            lines.append("")
            lines.append(f"Notes: {notes}")

        return "\n".join(lines)

    def _populate_evaluation_screen(self, evaluation_result):
        """Fill the evaluation screen with results."""
        # Update title
        if self.lang == "he":
            self.eval_title_var.set("הערכת ביצועים")
            self.eval_retry_btn.config(text="נסה שוב (אותו נושא)")
            self.eval_new_btn.config(text="נושא חדש")
            self.eval_save_btn.config(text="שמור תוצאות")
        else:
            self.eval_title_var.set("Performance Evaluation")
            self.eval_retry_btn.config(text="Try Again (Same Topic)")
            self.eval_new_btn.config(text="New Topic")
            self.eval_save_btn.config(text="Save Results")

        # Summary info
        if self.manager:
            summary = self.manager.get_conversation_summary()
            if self.lang == "he":
                topic = self.topic_config.get_topic_name('he') or self.topic_config.get_topic_name('en')
                self.eval_info_var.set(
                    self._bidi("נושא: {} | ", topic) +
                    f"{RLM}תורות: {summary['turns']} | ייעוצי מנטור: {summary['mentor_consultations']}"
                )
            else:
                self.eval_info_var.set(
                    f"Topic: {self.topic_config.get_topic_name('en')} | "
                    f"Turns: {summary['turns']} | Mentor consultations: {summary['mentor_consultations']}"
                )

        # Display evaluation
        self.eval_display.config(state=tk.NORMAL)
        self.eval_display.delete("1.0", tk.END)

        heading = f"{RLM}📋 תוצאות הערכה\n\n" if self.lang == "he" else "📋 Evaluation Results\n\n"
        self.eval_display.insert(tk.END, heading, "heading")
        evaluation_text = self._format_evaluation_text(evaluation_result)
        self.eval_display.insert(tk.END, evaluation_text + "\n", "feedback")

        self.eval_display.config(state=tk.DISABLED)

        # Apply direction to newly inserted content
        self._apply_direction()

        # Store for saving
        self._last_evaluation_data = evaluation_result
        self._last_evaluation = evaluation_text

    def _on_eval_retry(self):
        """Restart with the same topic."""
        self._initialize_chat()
        self._show_screen("chat")

    def _on_eval_new_topic(self):
        """Go back to setup for a new topic."""
        self.session_ended = False
        self.manager = None
        self._show_screen("setup")

    def _on_save_evaluation(self):
        """Save evaluation results to a text file."""
        filepath = filedialog.asksaveasfilename(
            title="Save Evaluation Results",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"evaluation_{self.topic_config.topic_name_en.replace(' ', '_').lower()}.txt"
        )
        if not filepath:
            return

        try:
            summary = self.manager.get_conversation_summary() if self.manager else {}
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("EDUCATIONAL CHATBOT — EVALUATION RESULTS\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"Topic: {self.topic_config.get_topic_name(self.lang)}\n")
                f.write(f"Language: {self.lang.upper()}\n")
                f.write(f"Turns: {summary.get('turns', 'N/A')}\n")
                f.write(f"Mentor consultations: {summary.get('mentor_consultations', 'N/A')}\n")
                f.write("\n" + "-" * 60 + "\n\n")
                f.write("EVALUATION:\n\n")
                f.write(getattr(self, '_last_evaluation', 'No evaluation available.'))
                f.write("\n\n" + "-" * 60 + "\n\n")
                last_eval_data = getattr(self, "_last_evaluation_data", None)
                if isinstance(last_eval_data, dict):
                    f.write("STRUCTURED EVALUATION JSON:\n\n")
                    f.write(json.dumps(last_eval_data, ensure_ascii=False, indent=2))
                    f.write("\n\n" + "-" * 60 + "\n\n")

                # Save conversation transcript
                if self.manager:
                    f.write("FULL CONVERSATION TRANSCRIPT:\n\n")
                    for msg in self.manager.get_student_history():
                        role = "Student-Teacher" if msg["role"] == "user" else "Student"
                        f.write(f"{role}: {msg['content']}\n\n")

                f.write("=" * 60 + "\n")

            messagebox.showinfo(
                "שמירה הצליחה" if self.lang == "he" else "Saved",
                f"Results saved to {filepath}"
            )
        except Exception as e:
            messagebox.showerror("Save Failed", str(e))


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Launch the Educational Chatbot GUI."""
    root = tk.Tk()
    app = ChatbotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

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
from tkinter import scrolledtext, filedialog, messagebox
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

    Usage:
        bar = AnimatedStatusBar(parent_frame, on_cancel=self._cancel_fn)
        bar.show("Generating topic")   # starts animation in the parent frame
        bar.hide()                     # stops animation and hides the frame

    The widget manages its own Tkinter 'after' loop so it never blocks the
    main thread.  Call hide() from any callback — it is safe to call even
    if already hidden.
    """

    _DOT_INTERVAL_MS = 500   # milliseconds between dot updates
    _MAX_DOTS = 4

    def __init__(self, parent: tk.Frame, on_cancel=None):
        """
        Args:
            parent:    The frame inside which the bar will be packed.
            on_cancel: Optional callable invoked when the user clicks Cancel.
                       The bar hides itself first, then calls on_cancel().
        """
        self._parent = parent
        self._on_cancel = on_cancel
        self._after_id = None
        self._message = ""
        self._dot_count = 0

        # Outer frame — hidden until show() is called
        self._frame = tk.Frame(parent, bg="#f0f0f0", relief=tk.SUNKEN, bd=1)

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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self, message: str):
        """
        Pack the bar inside its parent and start the animated dots.

        Args:
            message: The base status text, e.g. "Generating topic".
                     Dots ("...") are appended automatically.
        """
        self._message = message
        self._dot_count = 0
        self._frame.pack(fill=tk.X, pady=(2, 0))
        self._tick()

    def hide(self):
        """Stop the animation and hide the bar."""
        if self._after_id is not None:
            self._frame.after_cancel(self._after_id)
            self._after_id = None
        self._frame.pack_forget()

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

        self._build_setup_screen()
        self._build_settings_screen()
        self._build_lesson_screen()
        self._build_chat_screen()
        self._build_evaluation_screen()

        self._show_screen("setup")
        self._apply_direction()

    # ================================================================
    # SCREEN MANAGEMENT
    # ================================================================

    def _show_screen(self, name):
        for n, frame in self.screens.items():
            frame.grid_forget()
        self.screens[name].grid(row=0, column=0, sticky="nsew")
        self.current_screen = name

    def _make_top_bar(self, parent, title_var=None, timer_var=None):
        """Create a consistent top bar with language toggle, title, optional timer."""
        bar = tk.Frame(parent, bg=COLORS["dark_bg"], pady=6)
        bar.columnconfigure(1, weight=1)

        lang_var = tk.StringVar(value="English" if self.lang == "en" else "עברית")
        lang_btn = tk.Button(
            bar, textvariable=lang_var, font=("Arial", 9, "bold"),
            bg=COLORS["blue_btn"], fg="white", width=10,
            command=lambda: self._toggle_language(lang_var)
        )
        lang_btn.grid(row=0, column=0, padx=10)

        if title_var:
            tk.Label(bar, textvariable=title_var, font=("Arial", 13, "bold"),
                     fg="white", bg=COLORS["dark_bg"]).grid(row=0, column=1)

        timer_label = None
        if timer_var:
            timer_label = tk.Label(bar, textvariable=timer_var,
                                   font=("Consolas", 14, "bold"),
                                   fg=COLORS["timer_green"], bg=COLORS["dark_bg"], width=6)
            timer_label.grid(row=0, column=2, padx=10)

        # Register for directional swapping
        self._dir_top_bars.append((lang_btn, timer_label))

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
        self._refresh_current_screen_labels()
        self._apply_direction()

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
            self._populate_evaluation_screen(getattr(self, '_last_evaluation', ''))

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
        lang_col = 2 if is_rtl else 0
        timer_col = 0 if is_rtl else 2
        for lang_btn, timer_label in self._dir_top_bars:
            lang_btn.grid_configure(column=lang_col)
            if timer_label:
                timer_label.grid_configure(column=timer_col)

    def _register_dir_label(self, label, row, col, padx=0, pady=0):
        """Register a label for directional flipping."""
        self._dir_labels.append((label, row, col, padx, pady))

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

        # Settings row (only age — time settings moved to Settings screen)
        self.setup_settings_frame = tk.Frame(frame)
        self.setup_settings_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=5)

        self.age_label = tk.Label(self.setup_settings_frame, text="Student age:",
                                   font=("Arial", 10))
        self.age_label.pack(side=tk.LEFT, padx=(0, 5))
        self.age_spinner = tk.Spinbox(self.setup_settings_frame, from_=8, to=18, width=4,
                                       font=("Arial", 10), value=config.default_student_age)
        self.age_spinner.pack(side=tk.LEFT, padx=(0, 20))

        self._register_dir_btn_frame(
            self.setup_settings_frame,
            [self.age_label, self.age_spinner]
        )

        # Buttons row
        self.setup_btn_frame = tk.Frame(frame)
        self.setup_btn_frame.grid(row=4, column=0, sticky="ew", padx=12, pady=10)

        self.generate_btn = tk.Button(
            self.setup_btn_frame, text="Generate Topic", font=("Arial", 11, "bold"),
            bg=COLORS["green_btn"], fg="white", width=16,
            command=self._on_generate_topic
        )
        self.generate_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.load_btn = tk.Button(
            self.setup_btn_frame, text="Load Saved Topic", font=("Arial", 10),
            bg=COLORS["gray_btn"], fg="white", width=16,
            command=self._on_load_topic
        )
        self.load_btn.pack(side=tk.LEFT)

        self._register_dir_btn_frame(
            self.setup_btn_frame,
            [self.generate_btn, self.load_btn]
        )

        # Animated progress bar — shown only during generation (Sprint 3)
        self.setup_progress = AnimatedStatusBar(frame, on_cancel=self._on_cancel_generation)
        # (it packs/unpacks itself inside `frame`; no grid needed here)

        # Status label — always visible at the bottom
        self.setup_status_var = tk.StringVar(value="Ready")
        self.setup_status_label = tk.Label(
            frame, textvariable=self.setup_status_var,
            font=("Arial", 9), fg="#555555", relief=tk.SUNKEN,
            anchor="w", padx=10, pady=3
        )
        self.setup_status_label.grid(row=5, column=0, sticky="ew")
        self._register_dir_label(self.setup_status_label, 5, 0)

    def _update_setup_labels(self):
        if self.lang == "he":
            self.setup_title_var.set("צ'אטבוט חינוכי — הגדרות")
            self.setup_instruction_var.set("הדבק את חומר הלימוד כאן:")
            self.generate_btn.config(text="צור נושא")
            self.load_btn.config(text="טען נושא שמור")
            self.age_label.config(text="גיל התלמיד:")
        else:
            self.setup_title_var.set("Educational Chatbot — Setup")
            self.setup_instruction_var.set("Paste your learning material below:")
            self.generate_btn.config(text="Generate Topic")
            self.load_btn.config(text="Load Saved Topic")
            self.age_label.config(text="Student age:")

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
        target_age = int(self.age_spinner.get())

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
                    self.root.after(0, lambda: self._on_generation_error(str(e)))

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
        center_frame.columnconfigure(1, weight=1)

        # --- Preparation Time ---
        self.settings_prep_label = tk.Label(
            center_frame, text="Preparation Time (minutes):",
            font=("Arial", 12), bg="#f5f5f5", anchor="w"
        )
        self.settings_prep_label.grid(row=0, column=0, sticky="w", padx=20, pady=(25, 10))
        self._register_dir_label(self.settings_prep_label, 0, 0, padx=20, pady=(25, 10))

        self.settings_prep_spinner = tk.Spinbox(
            center_frame, from_=1, to=10, width=5,
            font=("Arial", 14), value=config.default_prep_minutes
        )
        self.settings_prep_spinner.grid(row=0, column=1, sticky="w", padx=20, pady=(25, 10))

        self.settings_prep_desc_var = tk.StringVar(
            value="How long you have to read and prepare before teaching"
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

        self.settings_teach_spinner = tk.Spinbox(
            center_frame, from_=3, to=30, width=5,
            font=("Arial", 14), value=config.default_teaching_minutes
        )
        self.settings_teach_spinner.grid(row=2, column=1, sticky="w", padx=20, pady=(10, 10))

        self.settings_teach_desc_var = tk.StringVar(
            value="How long the teaching conversation lasts"
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
        self.settings_start_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.settings_back_btn = tk.Button(
            self.settings_btn_frame, text="Back to Setup", font=("Arial", 10),
            bg=COLORS["gray_btn"], fg="white", width=14,
            command=lambda: self._show_screen("setup")
        )
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
            self.settings_prep_desc_var.set("כמה זמן יש לך לקרוא ולהתכונן לפני ההוראה")
            self.settings_teach_label.config(text="זמן הוראה (דקות):")
            self.settings_teach_desc_var.set("כמה זמן נמשכת שיחת ההוראה")
            self.settings_start_btn.config(text="התחל ללמוד")
            self.settings_back_btn.config(text="חזרה להגדרות")
        else:
            self.settings_title_var.set("Learning Settings")
            self.settings_desc_var.set("Configure your preparation and teaching session times:")
            self.settings_prep_label.config(text="Preparation Time (minutes):")
            self.settings_prep_desc_var.set("How long you have to read and prepare before teaching")
            self.settings_teach_label.config(text="Teaching Session Time (minutes):")
            self.settings_teach_desc_var.set("How long the teaching conversation lasts")
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
        self.lesson_minutes = int(self.settings_prep_spinner.get())
        self.teaching_minutes = int(self.settings_teach_spinner.get())

        # Update topic info before moving on
        if self.topic_config:
            topic = self.topic_config.get_topic_name(self.lang) or self.topic_config.get_topic_name("en")
            if self.lang == "he":
                self.settings_topic_var.set(self._bidi("נושא: {}", topic))
            else:
                self.settings_topic_var.set(f"Topic: {topic}")

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
            bg=COLORS["green_btn"], fg="white", width=16, state=tk.DISABLED,
            command=self._on_start_teaching
        )
        self.start_teaching_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.skip_timer_btn = tk.Button(
            self.lesson_btn_frame, text="I'm Ready — Skip", font=("Arial", 10),
            bg=COLORS["orange_btn"], fg="white", width=16,
            command=self._on_skip_lesson_timer
        )
        self.skip_timer_btn.pack(side=tk.LEFT, padx=(0, 10))

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
            [self.start_teaching_btn, self.skip_timer_btn, self.back_to_settings_btn],
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
            self.skip_timer_btn.config(text="אני מוכן — דלג")
            self.back_to_settings_btn.config(text="חזרה להגדרות")
            self.save_topic_btn.config(text="שמור נושא")
        else:
            self.lesson_title_var.set(f"Preparation: {topic}")
            self.start_teaching_btn.config(text="Start Teaching")
            self.skip_timer_btn.config(text="I'm Ready — Skip")
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
        self.start_teaching_btn.config(state=tk.DISABLED)
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
            self.start_teaching_btn.config(state=tk.NORMAL)
            self.lesson_info_var.set(
                "אתה מוכן! לחץ 'התחל ללמד'" if self.lang == "he"
                else "You're ready! Click 'Start Teaching'"
            )
            return
        if self.lesson_seconds_left <= 30:
            self.lesson_timer_label.config(fg=COLORS["timer_orange"])
        self.lesson_seconds_left -= 1
        self.lesson_timer_after_id = self.root.after(1000, self._tick_lesson_timer)

    def _stop_lesson_timer(self):
        self.lesson_timer_running = False
        if self.lesson_timer_after_id:
            self.root.after_cancel(self.lesson_timer_after_id)
            self.lesson_timer_after_id = None

    def _on_skip_lesson_timer(self):
        self._stop_lesson_timer()
        self.lesson_timer_var.set("00:00")
        self.start_teaching_btn.config(state=tk.NORMAL)
        self.lesson_info_var.set(
            "אתה מוכן! לחץ 'התחל ללמד'" if self.lang == "he"
            else "You're ready! Click 'Start Teaching'"
        )

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

        # Input area
        input_frame = tk.Frame(frame)
        input_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        input_frame.columnconfigure(0, weight=1)

        self.input_field = tk.Entry(input_frame, font=("Arial", 12), relief=tk.GROOVE, borderwidth=2)
        self.input_field.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.input_field.bind("<Return>", self._on_send)

        self.send_btn = tk.Button(
            input_frame, text="Send", font=("Arial", 11, "bold"),
            bg=COLORS["green_btn"], fg="white", width=8, command=self._on_send
        )
        self.send_btn.grid(row=0, column=1)

        # Action buttons
        self.chat_btn_frame = tk.Frame(frame)
        self.chat_btn_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=5)

        self.mentor_btn = tk.Button(self.chat_btn_frame, text="Ask Mentor", font=("Arial", 10),
                                     bg=COLORS["orange_btn"], fg="white", width=13, command=self._on_ask_mentor)
        self.mentor_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.eval_btn = tk.Button(self.chat_btn_frame, text="Get Evaluation", font=("Arial", 10),
                                   bg=COLORS["pink_btn"], fg="white", width=13, command=self._on_evaluate)
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

        self._register_dir_btn_frame(
            self.chat_btn_frame,
            [self.mentor_btn, self.eval_btn, self.summary_btn, self.new_conv_btn, self.back_setup_btn2]
        )

        # Animated progress bar for chat LLM calls (Sprint 3)
        # No cancel button — mid-chat cancellation would corrupt conversation history
        self.chat_progress = AnimatedStatusBar(frame)

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
                self.root.after(0, lambda: self._on_api_error(str(e)))

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
                self.root.after(0, lambda: self._on_mentor_error(str(e)))

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
                self.root.after(0, lambda: self._on_evaluation_error(str(e)))

        threading.Thread(target=api_call, daemon=True).start()

    def _on_evaluation_result(self, evaluation: str):
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

    def _populate_evaluation_screen(self, evaluation_text: str):
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
        self.eval_display.insert(tk.END, evaluation_text + "\n", "feedback")

        self.eval_display.config(state=tk.DISABLED)

        # Apply direction to newly inserted content
        self._apply_direction()

        # Store for saving
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

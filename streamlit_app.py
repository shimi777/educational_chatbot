#!/usr/bin/env python3
"""
Educational Chatbot — Streamlit Frontend
=========================================
5-screen single-page app:
  Setup  →  Settings  →  Lesson  →  Chat  →  Evaluation

All LLM work is delegated to the backend package.
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Make sure the project root is on sys.path so `backend.*` imports work
# regardless of where the process is launched from.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

# ---------------------------------------------------------------------------
# MUST be the very first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Educational Chatbot",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Backend imports (after sys.path fix)
# ---------------------------------------------------------------------------
from backend.config import config as app_config
from backend.llm_client import LLMClient
from backend.topic_config import TopicConfig
from backend.topic_generator import TopicGenerator
from backend.conversation_manager import ConversationManager
from backend.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MAX_MATERIAL_CHARS = 15_000
_SCREENS = ("setup", "settings", "lesson", "chat", "evaluation")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def t(en: str, he: str) -> str:
    """Return the English or Hebrew string based on current language."""
    return he if st.session_state.get("lang", "en") == "he" else en


def _nav(screen: str) -> None:
    """Navigate to a named screen."""
    st.session_state.current_screen = screen
    st.rerun()


def _inject_rtl_css() -> None:
    """Inject RTL CSS when the language is Hebrew."""
    if st.session_state.get("lang") != "he":
        return
    st.markdown(
        """
        <style>
        /* Main container */
        .main .block-container {
            direction: rtl;
            text-align: right;
        }
        /* Chat messages */
        [data-testid="stChatMessage"] {
            direction: rtl;
            text-align: right;
        }
        /* Text areas */
        textarea {
            direction: rtl;
            text-align: right;
        }
        /* Sidebar */
        [data-testid="stSidebar"] .block-container {
            direction: rtl;
            text-align: right;
        }
        /* Selectbox / radio labels */
        .stRadio label, .stSelectbox label {
            direction: rtl;
        }
        /* Metric labels */
        [data-testid="stMetricLabel"] {
            direction: rtl;
            text-align: right;
        }
        /* Headers */
        h1, h2, h3, h4, h5, h6, p, li {
            direction: rtl;
            text-align: right;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _format_time(seconds: int) -> str:
    """Format seconds as MM:SS."""
    m, s = divmod(max(0, seconds), 60)
    return f"{m:02d}:{s:02d}"


def _elapsed_seconds(start_ts: float) -> int:
    """Return whole seconds elapsed since start_ts."""
    return int(time.time() - start_ts)


def _remaining_seconds(start_ts: float, total_seconds: int) -> int:
    """Return seconds remaining (clamped to 0)."""
    return max(0, total_seconds - _elapsed_seconds(start_ts))


# ---------------------------------------------------------------------------
# Session State Initialisation
# ---------------------------------------------------------------------------

def _init_session_state() -> None:
    defaults = {
        "current_screen": "setup",
        "lang": app_config.default_language,
        "topic_config": None,
        "material_text": "",
        "student_age": app_config.default_student_age,
        "prep_minutes": app_config.default_prep_minutes,
        "teaching_minutes": app_config.default_teaching_minutes,
        "lesson_timer_start": None,
        "lesson_timer_seconds": app_config.default_prep_minutes * 60,
        "lesson_auto_advanced": False,
        "manager": None,
        "chat_messages": [],          # [{role, content}]  displayed in chat
        "mentor_messages": [],        # [str]  advice history
        "chat_timer_start": None,
        "chat_timer_seconds": app_config.default_teaching_minutes * 60,
        "session_ended": False,
        "evaluation_result": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar() -> None:
    with st.sidebar:
        st.title(t("Educational Chatbot", "צ'אטבוט חינוכי"))
        st.divider()

        # Language selection
        lang_choice = st.radio(
            t("Language", "שפה"),
            options=["English", "עברית"],
            index=0 if st.session_state.lang == "en" else 1,
            key="lang_radio",
        )
        new_lang = "en" if lang_choice == "English" else "he"
        if new_lang != st.session_state.lang:
            st.session_state.lang = new_lang
            st.rerun()

        st.divider()

        # Current screen
        screen_labels = {
            "setup": t("Setup", "הגדרה"),
            "settings": t("Settings", "הגדרות"),
            "lesson": t("Lesson Prep", "הכנה"),
            "chat": t("Teaching", "הוראה"),
            "evaluation": t("Evaluation", "הערכה"),
        }
        current = st.session_state.current_screen
        st.caption(t("Current screen:", "מסך נוכחי:"))
        st.markdown(f"**{screen_labels.get(current, current)}**")

        # Topic name
        tc: Optional[TopicConfig] = st.session_state.topic_config
        if tc:
            st.caption(t("Topic:", "נושא:"))
            st.markdown(f"**{tc.get_topic_name(st.session_state.lang)}**")

        st.divider()

        # Quick-navigation (debug-friendly)
        st.caption(t("Quick navigation", "ניווט מהיר"))
        for screen, label in screen_labels.items():
            if st.button(label, key=f"nav_{screen}", use_container_width=True):
                st.session_state.current_screen = screen
                st.rerun()


# ---------------------------------------------------------------------------
# Screen 1: Setup
# ---------------------------------------------------------------------------

def _screen_setup() -> None:
    st.title(t("Educational Chatbot — Setup", "צ'אטבוט חינוכי — הגדרה"))
    st.markdown(
        t(
            "Paste your learning material below, set the student age, then generate the topic.",
            "הדבק את חומר הלמידה למטה, הגדר את גיל התלמיד, ולאחר מכן צור את הנושא.",
        )
    )

    # ------------------------------------------------------------------ #
    # File uploader (fills the material text area)
    # ------------------------------------------------------------------ #
    uploaded = st.file_uploader(
        t("Upload a text / markdown file", "העלה קובץ טקסט / מרקדאון"),
        type=["txt", "md"],
        key="material_uploader",
    )
    if uploaded is not None:
        try:
            content = uploaded.read().decode("utf-8")
            st.session_state.material_text = content
        except Exception as exc:
            st.error(t(f"Could not read file: {exc}", f"לא ניתן לקרוא קובץ: {exc}"))

    # ------------------------------------------------------------------ #
    # Material text area
    # ------------------------------------------------------------------ #
    material = st.text_area(
        t("Learning material", "חומר לימוד"),
        value=st.session_state.material_text,
        height=280,
        max_chars=_MAX_MATERIAL_CHARS,
        placeholder=t(
            "Paste your lesson content here (max 15,000 characters)...",
            "הדבק כאן את תוכן השיעור (עד 15,000 תווים)...",
        ),
        key="material_input",
    )
    st.session_state.material_text = material

    char_count = len(material)
    color = "red" if char_count > _MAX_MATERIAL_CHARS else "gray"
    st.markdown(
        f'<small style="color:{color}">'
        + t(f"{char_count:,} / {_MAX_MATERIAL_CHARS:,} characters", f"{char_count:,} / {_MAX_MATERIAL_CHARS:,} תווים")
        + "</small>",
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------ #
    # Student age
    # ------------------------------------------------------------------ #
    st.session_state.student_age = st.number_input(
        t("Student age", "גיל התלמיד"),
        min_value=8,
        max_value=18,
        value=st.session_state.student_age,
        step=1,
        key="age_input",
    )

    st.divider()

    col1, col2 = st.columns(2)

    # ------------------------------------------------------------------ #
    # Generate Topic button
    # ------------------------------------------------------------------ #
    with col1:
        if st.button(
            t("Generate Topic", "צור נושא"),
            type="primary",
            use_container_width=True,
            key="btn_generate",
        ):
            material_val = st.session_state.material_text.strip()
            if not material_val:
                st.error(t("Please enter learning material first.", "אנא הכנס חומר לימוד תחילה."))
            elif len(material_val) > _MAX_MATERIAL_CHARS:
                st.error(
                    t(
                        f"Material exceeds {_MAX_MATERIAL_CHARS:,} characters. Please shorten it.",
                        f"החומר עולה על {_MAX_MATERIAL_CHARS:,} תווים. אנא קצר אותו.",
                    )
                )
            else:
                with st.spinner(t("Generating topic configuration (2 LLM calls)...", "יוצר הגדרת נושא (2 קריאות LLM)...")):
                    try:
                        generator = TopicGenerator(LLMClient())
                        tc = generator.generate_topic_config(
                            material_val,
                            target_age=int(st.session_state.student_age),
                        )
                        st.session_state.topic_config = tc
                        # Auto-save
                        save_path = os.path.join(
                            os.path.dirname(os.path.abspath(__file__)), "last_topic.json"
                        )
                        tc.save_to_file(save_path)
                        st.success(
                            t(
                                f"Topic generated: {tc.get_topic_name('en')}",
                                f"נושא נוצר: {tc.get_topic_name('he')}",
                            )
                        )
                        logger.info("Topic generated: %s", tc.topic_name_en)
                        time.sleep(0.8)
                        _nav("settings")
                    except Exception as exc:
                        logger.error("Topic generation failed: %s", exc)
                        st.error(
                            t(
                                f"Generation failed: {exc}",
                                f"יצירת הנושא נכשלה: {exc}",
                            )
                        )

    # ------------------------------------------------------------------ #
    # Load saved topic
    # ------------------------------------------------------------------ #
    with col2:
        json_upload = st.file_uploader(
            t("Load saved topic (JSON)", "טען נושא שמור (JSON)"),
            type=["json"],
            key="json_uploader",
        )
        if json_upload is not None:
            try:
                data = json.load(json_upload)
                tc = TopicConfig.from_dict(data)
                if not tc.is_valid():
                    st.error(t("Loaded topic is invalid or incomplete.", "הנושא שנטען אינו תקין או שלם."))
                else:
                    st.session_state.topic_config = tc
                    st.success(
                        t(
                            f"Loaded: {tc.get_topic_name('en')}",
                            f"נטען: {tc.get_topic_name('he')}",
                        )
                    )
                    time.sleep(0.5)
                    _nav("settings")
            except Exception as exc:
                st.error(t(f"Failed to load topic: {exc}", f"טעינת הנושא נכשלה: {exc}"))

    # Quick-load last_topic.json if it exists
    last_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_topic.json")
    if os.path.isfile(last_path):
        if st.button(
            t("Load Last Auto-Saved Topic", "טען נושא אחרון שנשמר אוטומטית"),
            key="btn_load_last",
            use_container_width=True,
        ):
            try:
                tc = TopicConfig.load_from_file(last_path)
                if tc.is_valid():
                    st.session_state.topic_config = tc
                    st.success(t(f"Loaded: {tc.get_topic_name('en')}", f"נטען: {tc.get_topic_name('he')}"))
                    time.sleep(0.5)
                    _nav("settings")
                else:
                    st.error(t("Saved topic is invalid.", "הנושא השמור אינו תקין."))
            except Exception as exc:
                st.error(t(f"Load failed: {exc}", f"הטעינה נכשלה: {exc}"))


# ---------------------------------------------------------------------------
# Screen 2: Settings
# ---------------------------------------------------------------------------

def _screen_settings() -> None:
    tc: Optional[TopicConfig] = st.session_state.topic_config
    if tc is None:
        st.error(t("No topic loaded. Please go back to Setup.", "לא נטען נושא. אנא חזור להגדרה."))
        if st.button(t("Back to Setup", "חזרה להגדרה"), key="settings_back_err"):
            _nav("setup")
        return

    lang = st.session_state.lang
    topic_name = tc.get_topic_name(lang)

    st.title(t("Learning Settings", "הגדרות למידה"))
    st.subheader(t(f"Topic: {topic_name}", f"נושא: {topic_name}"))

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.session_state.prep_minutes = st.number_input(
            t("Preparation time (minutes)", "זמן הכנה (דקות)"),
            min_value=1,
            max_value=20,
            value=st.session_state.prep_minutes,
            step=1,
            help=t(
                "Time to review the lesson material before teaching.",
                "זמן לסקירת חומר הלמידה לפני ההוראה.",
            ),
            key="prep_min_input",
        )

    with col2:
        st.session_state.teaching_minutes = st.number_input(
            t("Teaching time (minutes)", "זמן הוראה (דקות)"),
            min_value=3,
            max_value=60,
            value=st.session_state.teaching_minutes,
            step=1,
            help=t(
                "How long you have to teach the struggling student.",
                "כמה זמן יש לך ללמד את התלמיד המתקשה.",
            ),
            key="teach_min_input",
        )

    st.divider()

    # Subject area preview
    subject = tc.get_subject_area(lang)
    if subject:
        st.info(t(f"Subject area: {subject}", f"תחום: {subject}"))

    # Show key concepts preview
    concepts = tc.get_key_concepts(lang)
    if concepts:
        with st.expander(t("Key concepts preview", "תצוגה מקדימה של מושגים מרכזיים")):
            for c in concepts:
                st.markdown(f"- {c}")

    st.divider()

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button(t("Back to Setup", "חזרה להגדרה"), use_container_width=True, key="settings_back"):
            _nav("setup")

    with col_b:
        if st.button(
            t("Start Learning", "התחל ללמוד"),
            type="primary",
            use_container_width=True,
            key="settings_start",
        ):
            # Reset lesson timer
            st.session_state.lesson_timer_start = None
            st.session_state.lesson_timer_seconds = st.session_state.prep_minutes * 60
            st.session_state.lesson_auto_advanced = False
            _nav("lesson")


# ---------------------------------------------------------------------------
# Screen 3: Lesson (Preparation)
# ---------------------------------------------------------------------------

def _screen_lesson() -> None:
    tc: Optional[TopicConfig] = st.session_state.topic_config
    if tc is None:
        st.error(t("No topic loaded.", "לא נטען נושא."))
        if st.button(t("Back to Setup", "חזרה להגדרה"), key="lesson_back_err"):
            _nav("setup")
        return

    lang = st.session_state.lang
    topic_name = tc.get_topic_name(lang)
    total_seconds = st.session_state.prep_minutes * 60

    st.title(t(f"Preparation: {topic_name}", f"הכנה: {topic_name}"))

    # ------------------------------------------------------------------ #
    # Countdown timer
    # ------------------------------------------------------------------ #
    if st.session_state.lesson_timer_start is None:
        st.session_state.lesson_timer_start = time.time()

    remaining = _remaining_seconds(st.session_state.lesson_timer_start, total_seconds)
    pct = remaining / total_seconds if total_seconds > 0 else 0.0

    timer_col, info_col = st.columns([1, 3])
    with timer_col:
        timer_ph = st.empty()
        progress_ph = st.empty()
        timer_ph.metric(
            t("Time remaining", "זמן שנותר"),
            _format_time(remaining),
        )
        progress_ph.progress(pct)

    with info_col:
        if remaining > 0:
            st.info(
                t(
                    "Read the material carefully. Teaching starts when the timer expires or you click 'Start Teaching'.",
                    "קרא את החומר בעיון. ההוראה תתחיל כאשר השעון יסתיים או כשתלחץ על 'התחל הוראה'.",
                )
            )
        else:
            st.warning(
                t(
                    "Preparation time is up! Start teaching now.",
                    "זמן ההכנה הסתיים! התחל ללמד עכשיו.",
                )
            )

    st.divider()

    # ------------------------------------------------------------------ #
    # Lesson content
    # ------------------------------------------------------------------ #
    col1, col2 = st.columns(2)

    with col1:
        st.subheader(t("Key Concepts", "מושגים מרכזיים"))
        for concept in tc.get_key_concepts(lang):
            st.markdown(f"- {concept}")

        st.subheader(t("Key Terms", "מונחים מרכזיים"))
        for term in tc.get_key_terms(lang):
            st.markdown(f"- {term}")

    with col2:
        st.subheader(t("Common Misconceptions", "תפיסות שגויות נפוצות"))
        for misc in tc.get_misconceptions(lang):
            st.warning(misc)

        st.subheader(t("Good Examples & Analogies", "דוגמאות ואנלוגיות טובות"))
        for ex in tc.get_good_examples(lang):
            st.markdown(f"- {ex}")

    st.divider()

    st.subheader(t("Lesson Summary", "סיכום השיעור"))
    st.markdown(tc.get_lesson_summary(lang))

    st.divider()

    # ------------------------------------------------------------------ #
    # Buttons
    # ------------------------------------------------------------------ #
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        # Save topic as JSON download
        tc_json = json.dumps(tc.to_dict(), ensure_ascii=False, indent=2)
        st.download_button(
            label=t("Save Topic (JSON)", "שמור נושא (JSON)"),
            data=tc_json.encode("utf-8"),
            file_name=f"topic_{tc.topic_name_en.replace(' ', '_')}.json",
            mime="application/json",
            use_container_width=True,
            key="lesson_download",
        )

    with btn_col2:
        if st.button(
            t("Start Teaching", "התחל הוראה"),
            type="primary",
            use_container_width=True,
            key="lesson_start_teach",
        ):
            _start_chat_session(tc, lang)

    # ------------------------------------------------------------------ #
    # Auto-advance on timer expiry
    # ------------------------------------------------------------------ #
    if remaining <= 0 and not st.session_state.lesson_auto_advanced:
        st.session_state.lesson_auto_advanced = True
        _start_chat_session(tc, lang)
    elif remaining > 0:
        # Rerun every second to update countdown
        time.sleep(1)
        st.rerun()


def _start_chat_session(tc: TopicConfig, lang: str) -> None:
    """Create ConversationManager, start conversation, navigate to chat."""
    try:
        manager = ConversationManager(lang=lang, topic_config=tc)
        initial_msg = manager.start_conversation()
        st.session_state.manager = manager
        # The initial message comes from the student
        st.session_state.chat_messages = [
            {"role": "student", "content": initial_msg}
        ]
        st.session_state.mentor_messages = []
        st.session_state.chat_timer_start = None  # starts on first teacher message
        st.session_state.chat_timer_seconds = st.session_state.teaching_minutes * 60
        st.session_state.session_ended = False
        st.session_state.evaluation_result = None
        _nav("chat")
    except Exception as exc:
        logger.error("Failed to start chat session: %s", exc)
        st.error(t(f"Failed to start session: {exc}", f"הפעלת הסשן נכשלה: {exc}"))


# ---------------------------------------------------------------------------
# Screen 4: Chat
# ---------------------------------------------------------------------------

def _screen_chat() -> None:
    tc: Optional[TopicConfig] = st.session_state.topic_config
    manager: Optional[ConversationManager] = st.session_state.manager

    if tc is None or manager is None:
        st.error(t("Session not initialised.", "הסשן לא אותחל."))
        if st.button(t("Back to Setup", "חזרה להגדרה"), key="chat_back_err"):
            _nav("setup")
        return

    lang = st.session_state.lang
    topic_name = tc.get_topic_name(lang)
    total_secs = st.session_state.chat_timer_seconds
    session_ended = st.session_state.session_ended

    st.title(t(f"Teaching: {topic_name}", f"מלמד: {topic_name}"))

    # ------------------------------------------------------------------ #
    # Timer (starts on first teacher message)
    # ------------------------------------------------------------------ #
    timer_start = st.session_state.chat_timer_start
    if timer_start is not None:
        remaining = _remaining_seconds(timer_start, total_secs)
        pct = remaining / total_secs if total_secs > 0 else 0.0
        timer_color = "red" if remaining < 60 else "orange" if remaining < 120 else "green"

        st.markdown(
            f'<p style="font-size:1.1rem;color:{timer_color};">'
            + t(f"Time remaining: {_format_time(remaining)}", f"זמן שנותר: {_format_time(remaining)}")
            + "</p>",
            unsafe_allow_html=True,
        )
        st.progress(pct)
    else:
        st.info(t("Timer starts on your first message.", "השעון מתחיל עם הודעתך הראשונה."))

    # ------------------------------------------------------------------ #
    # Status caption
    # ------------------------------------------------------------------ #
    summary = manager.get_conversation_summary()
    st.caption(
        t(
            f"Turns: {summary['turns']} | Your messages: {summary['student_messages']} | Mentor consultations: {summary['mentor_consultations']}",
            f"תורות: {summary['turns']} | ההודעות שלך: {summary['student_messages']} | התייעצויות עם מנטור: {summary['mentor_consultations']}",
        )
    )

    st.divider()

    # ------------------------------------------------------------------ #
    # Main layout: 70% chat | 30% mentor panel
    # ------------------------------------------------------------------ #
    chat_col, mentor_col = st.columns([7, 3])

    # ------------------------------------------------------------------ #
    # LEFT: Chat
    # ------------------------------------------------------------------ #
    with chat_col:
        st.subheader(t("Conversation", "שיחה"))

        # Render chat history
        for msg in st.session_state.chat_messages:
            role = msg["role"]
            content = msg["content"]
            if role == "student":
                with st.chat_message("user", avatar="🧑‍🎓"):
                    st.markdown(content)
            elif role == "teacher":
                with st.chat_message("assistant", avatar="👨‍🏫"):
                    st.markdown(content)

        # Chat input (disabled if session ended)
        if not session_ended:
            teacher_input = st.chat_input(
                placeholder=t(
                    "Type your explanation here...",
                    "כתוב את הסברך כאן...",
                ),
                key="chat_input_box",
            )

            if teacher_input and teacher_input.strip():
                # Start timer on first teacher message
                if st.session_state.chat_timer_start is None:
                    st.session_state.chat_timer_start = time.time()

                # Append teacher message
                st.session_state.chat_messages.append(
                    {"role": "teacher", "content": teacher_input.strip()}
                )

                # Call LLM for student response
                with st.spinner(t("Student is thinking...", "התלמיד חושב...")):
                    try:
                        student_reply = manager.send_to_student(teacher_input.strip())
                        st.session_state.chat_messages.append(
                            {"role": "student", "content": student_reply}
                        )
                    except Exception as exc:
                        logger.error("send_to_student failed: %s", exc)
                        st.error(t(f"Error: {exc}", f"שגיאה: {exc}"))

                st.rerun()
        else:
            st.info(t("Session has ended. See evaluation below.", "הסשן הסתיים. ראה הערכה למטה."))

    # ------------------------------------------------------------------ #
    # RIGHT: Mentor panel
    # ------------------------------------------------------------------ #
    with mentor_col:
        st.subheader(t("Mentor", "מנטור"))

        if st.session_state.mentor_messages:
            for i, advice in enumerate(st.session_state.mentor_messages, 1):
                with st.expander(t(f"Advice #{i}", f"עצה #{i}"), expanded=(i == len(st.session_state.mentor_messages))):
                    st.markdown(advice)
        else:
            st.caption(t("No mentor advice yet.", "עדיין אין עצות מנטור."))

        st.divider()

        # Ask Mentor
        if not session_ended:
            if st.button(t("Ask Mentor", "שאל מנטור"), use_container_width=True, key="btn_mentor"):
                last_teacher = _get_last_teacher_msg()
                last_student = manager.get_last_student_message()
                if not last_teacher:
                    st.warning(t("Send at least one message first.", "שלח לפחות הודעה אחת תחילה."))
                else:
                    with st.spinner(t("Consulting mentor...", "מתייעץ עם מנטור...")):
                        try:
                            advice = manager.consult_mentor(
                                teacher_explanation=last_teacher,
                                student_context=last_student,
                            )
                            st.session_state.mentor_messages.append(advice)
                        except Exception as exc:
                            logger.error("consult_mentor failed: %s", exc)
                            st.error(t(f"Mentor error: {exc}", f"שגיאת מנטור: {exc}"))
                    st.rerun()

        # Get Evaluation
        if st.button(
            t("Get Evaluation", "קבל הערכה"),
            type="primary",
            use_container_width=True,
            key="btn_evaluate",
        ):
            with st.spinner(t("Evaluating performance...", "מעריך ביצועים...")):
                try:
                    result = manager.evaluate_performance()
                    st.session_state.evaluation_result = result
                    st.session_state.session_ended = True
                except Exception as exc:
                    logger.error("evaluate_performance failed: %s", exc)
                    st.error(t(f"Evaluation error: {exc}", f"שגיאת הערכה: {exc}"))
            if st.session_state.evaluation_result:
                _nav("evaluation")

        # Summary
        if st.button(t("Conversation Summary", "סיכום שיחה"), use_container_width=True, key="btn_summary"):
            s = manager.get_conversation_summary()
            st.info(
                t(
                    f"Turns: {s['turns']} | Your msgs: {s['student_messages']} | Mentor: {s['mentor_consultations']}",
                    f"תורות: {s['turns']} | הודעות שלך: {s['student_messages']} | מנטור: {s['mentor_consultations']}",
                )
            )

        st.divider()

        # Restart
        if st.button(t("Restart Conversation", "התחל שיחה מחדש"), use_container_width=True, key="btn_restart"):
            _start_chat_session(tc, lang)

        # New Topic
        if st.button(t("New Topic", "נושא חדש"), use_container_width=True, key="btn_new_topic"):
            _reset_to_setup()

    # ------------------------------------------------------------------ #
    # Auto-evaluate on timer expiry
    # ------------------------------------------------------------------ #
    if (
        timer_start is not None
        and not session_ended
        and _remaining_seconds(timer_start, total_secs) <= 0
    ):
        st.warning(t("Teaching time is up! Auto-evaluating...", "זמן ההוראה הסתיים! מעריך אוטומטית..."))
        with st.spinner(t("Evaluating...", "מעריך...")):
            try:
                result = manager.evaluate_performance()
                st.session_state.evaluation_result = result
                st.session_state.session_ended = True
            except Exception as exc:
                logger.error("Auto-evaluation failed: %s", exc)
                st.error(t(f"Auto-evaluation failed: {exc}", f"הערכה אוטומטית נכשלה: {exc}"))
        if st.session_state.evaluation_result:
            time.sleep(1)
            _nav("evaluation")

    # Keep updating timer every second while active
    if (
        timer_start is not None
        and not session_ended
        and _remaining_seconds(timer_start, total_secs) > 0
    ):
        time.sleep(1)
        st.rerun()


def _get_last_teacher_msg() -> str:
    """Return the most recent teacher message from chat_messages."""
    for msg in reversed(st.session_state.chat_messages):
        if msg["role"] == "teacher":
            return msg["content"]
    return ""


def _reset_to_setup() -> None:
    """Clear all conversation and topic state and navigate to setup."""
    st.session_state.topic_config = None
    st.session_state.material_text = ""
    st.session_state.manager = None
    st.session_state.chat_messages = []
    st.session_state.mentor_messages = []
    st.session_state.evaluation_result = None
    st.session_state.session_ended = False
    st.session_state.lesson_timer_start = None
    st.session_state.chat_timer_start = None
    st.session_state.lesson_auto_advanced = False
    _nav("setup")


# ---------------------------------------------------------------------------
# Screen 5: Evaluation
# ---------------------------------------------------------------------------

def _screen_evaluation() -> None:
    result = st.session_state.evaluation_result
    tc: Optional[TopicConfig] = st.session_state.topic_config
    manager: Optional[ConversationManager] = st.session_state.manager

    if result is None:
        st.error(t("No evaluation result found.", "לא נמצאה תוצאת הערכה."))
        if st.button(t("Back to Setup", "חזרה להגדרה"), key="eval_back_err"):
            _nav("setup")
        return

    lang = st.session_state.lang
    topic_name = tc.get_topic_name(lang) if tc else t("Unknown", "לא ידוע")

    st.title(t("Performance Evaluation", "הערכת ביצועים"))
    st.subheader(t(f"Topic: {topic_name}", f"נושא: {topic_name}"))

    total_score = result.get("total_score", 0)
    max_score = result.get("max_score", 0)
    perf_level = result.get("performance_level", t("Unknown", "לא ידוע"))
    component_scores = result.get("component_scores", {})
    misconceptions_count = result.get("misconceptions_count", 0)
    notes = result.get("notes", "")
    comparison = result.get("comparison", {})
    improvement = comparison.get("improvement") if comparison else None

    st.divider()

    # ------------------------------------------------------------------ #
    # Top metrics
    # ------------------------------------------------------------------ #
    m1, m2, m3 = st.columns(3)

    with m1:
        st.metric(
            label=t("Total Score", "ציון כולל"),
            value=f"{total_score} / {max_score}",
            delta=(
                f"+{improvement['score_delta']}" if improvement and improvement["score_delta"] > 0
                else (str(improvement["score_delta"]) if improvement else None)
            ),
        )

    with m2:
        st.metric(
            label=t("Performance Level", "רמת ביצועים"),
            value=perf_level,
        )

    with m3:
        st.metric(
            label=t("Misconceptions Detected", "תפיסות שגויות שזוהו"),
            value=misconceptions_count,
            delta=(
                improvement["misconceptions_delta"] if improvement else None
            ),
            delta_color="inverse",  # lower is better
        )

    st.divider()

    # ------------------------------------------------------------------ #
    # Component scores with progress bars
    # ------------------------------------------------------------------ #
    if component_scores:
        st.subheader(t("Component Scores", "ציוני רכיבים"))

        for comp_key, score in component_scores.items():
            # Label: prettify the key
            label = comp_key.replace("_", " ").title()
            pct = score / 2.0  # scores are 0-2

            col_label, col_bar, col_score = st.columns([2, 4, 1])
            with col_label:
                st.markdown(f"**{label}**")
            with col_bar:
                st.progress(pct)
            with col_score:
                score_color = "green" if score == 2 else "orange" if score == 1 else "red"
                st.markdown(
                    f'<span style="color:{score_color};font-weight:bold;">{score}/2</span>',
                    unsafe_allow_html=True,
                )

        # Improvement comparison
        if improvement:
            st.divider()
            st.subheader(t("Improvement vs First Explanation", "שיפור לעומת ההסבר הראשון"))
            delta_score = improvement.get("score_delta", 0)
            delta_correct = improvement.get("correct_components_delta", 0)
            delta_misc = improvement.get("misconceptions_delta", 0)

            ic1, ic2, ic3 = st.columns(3)
            with ic1:
                st.metric(
                    t("Score change", "שינוי ציון"),
                    value=f"{'+' if delta_score >= 0 else ''}{delta_score}",
                    delta=delta_score,
                )
            with ic2:
                st.metric(
                    t("Correct components change", "שינוי ברכיבים נכונים"),
                    value=f"{'+' if delta_correct >= 0 else ''}{delta_correct}",
                    delta=delta_correct,
                )
            with ic3:
                st.metric(
                    t("Misconceptions change", "שינוי בתפיסות שגויות"),
                    value=f"{'+' if delta_misc >= 0 else ''}{delta_misc}",
                    delta=delta_misc,
                    delta_color="inverse",
                )
        elif comparison and comparison.get("reason"):
            st.info(comparison["reason"])

    # ------------------------------------------------------------------ #
    # Notes / feedback
    # ------------------------------------------------------------------ #
    if notes:
        st.divider()
        st.subheader(t("Feedback", "משוב"))
        st.markdown(notes)

    st.divider()

    # ------------------------------------------------------------------ #
    # Action buttons
    # ------------------------------------------------------------------ #
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        if st.button(
            t("Try Again", "נסה שוב"),
            type="primary",
            use_container_width=True,
            key="eval_retry",
        ):
            if tc is not None:
                _start_chat_session(tc, lang)
            else:
                _nav("setup")

    with btn_col2:
        if st.button(
            t("New Topic", "נושא חדש"),
            use_container_width=True,
            key="eval_new_topic",
        ):
            _reset_to_setup()

    with btn_col3:
        # Build downloadable results
        transcript = _build_transcript(result, tc, lang)
        st.download_button(
            label=t("Save Results", "שמור תוצאות"),
            data=transcript.encode("utf-8"),
            file_name=f"evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=True,
            key="eval_download",
        )


def _build_transcript(result: dict, tc: Optional[TopicConfig], lang: str) -> str:
    """Build a plain-text report with evaluation scores and full conversation."""
    lines = []
    topic_name = tc.get_topic_name(lang) if tc else "Unknown Topic"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("=" * 60)
    lines.append(t("EDUCATIONAL CHATBOT — EVALUATION REPORT", "צ'אטבוט חינוכי — דוח הערכה"))
    lines.append(f"{t('Generated', 'נוצר')}: {ts}")
    lines.append(f"{t('Topic', 'נושא')}: {topic_name}")
    lines.append("=" * 60)
    lines.append("")

    # Scores
    lines.append(t("SCORES", "ציונים"))
    lines.append("-" * 40)
    total = result.get("total_score", 0)
    max_s = result.get("max_score", 0)
    level = result.get("performance_level", "")
    lines.append(f"{t('Total Score', 'ציון כולל')}: {total} / {max_s}")
    lines.append(f"{t('Performance Level', 'רמת ביצועים')}: {level}")
    lines.append(f"{t('Misconceptions Detected', 'תפיסות שגויות')}: {result.get('misconceptions_count', 0)}")
    lines.append("")

    # Component scores
    comp_scores = result.get("component_scores", {})
    if comp_scores:
        lines.append(t("COMPONENT SCORES", "ציוני רכיבים"))
        lines.append("-" * 40)
        for key, score in comp_scores.items():
            label = key.replace("_", " ").title()
            lines.append(f"  {label}: {score}/2")
        lines.append("")

    # Notes
    notes = result.get("notes", "")
    if notes:
        lines.append(t("FEEDBACK", "משוב"))
        lines.append("-" * 40)
        lines.append(notes)
        lines.append("")

    # Improvement
    comp = result.get("comparison", {})
    imp = comp.get("improvement") if comp else None
    if imp:
        lines.append(t("IMPROVEMENT VS FIRST EXPLANATION", "שיפור לעומת ההסבר הראשון"))
        lines.append("-" * 40)
        lines.append(f"  {t('Score delta', 'שינוי ציון')}: {imp.get('score_delta', 0):+d}")
        lines.append(f"  {t('Correct components delta', 'שינוי ברכיבים נכונים')}: {imp.get('correct_components_delta', 0):+d}")
        lines.append(f"  {t('Misconceptions delta', 'שינוי בתפיסות שגויות')}: {imp.get('misconceptions_delta', 0):+d}")
        lines.append("")

    # Conversation transcript
    chat_msgs = st.session_state.get("chat_messages", [])
    if chat_msgs:
        lines.append(t("CONVERSATION TRANSCRIPT", "תמלול השיחה"))
        lines.append("=" * 60)
        for i, msg in enumerate(chat_msgs, 1):
            role = msg["role"]
            content = msg["content"]
            if role == "student":
                role_label = t("Student", "תלמיד")
            elif role == "teacher":
                role_label = t("Teacher (You)", "מורה (אתה)")
            else:
                role_label = role.title()
            lines.append(f"[{i}] {role_label}:")
            lines.append(content)
            lines.append("")

    # Mentor advice
    mentor_msgs = st.session_state.get("mentor_messages", [])
    if mentor_msgs:
        lines.append(t("MENTOR ADVICE HISTORY", "היסטוריית עצות מנטור"))
        lines.append("=" * 60)
        for i, advice in enumerate(mentor_msgs, 1):
            lines.append(f"[{i}] {t('Mentor', 'מנטור')}:")
            lines.append(advice)
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    _init_session_state()
    _inject_rtl_css()
    _render_sidebar()

    screen = st.session_state.current_screen

    if screen == "setup":
        _screen_setup()
    elif screen == "settings":
        _screen_settings()
    elif screen == "lesson":
        _screen_lesson()
    elif screen == "chat":
        _screen_chat()
    elif screen == "evaluation":
        _screen_evaluation()
    else:
        st.error(t(f"Unknown screen: {screen}", f"מסך לא ידוע: {screen}"))
        if st.button(t("Reset to Setup", "אפס להגדרה"), key="unknown_reset"):
            _nav("setup")


if __name__ == "__main__":
    main()

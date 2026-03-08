#!/usr/bin/env python3
"""
Teacher App — Streamlit Frontend (teacher side)
================================================
3-screen app:
  Setup  →  Settings  →  Share

The teacher pastes learning material, generates a topic, configures
session settings, and shares a session ID with the student.
"""

import json
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

st.set_page_config(
    page_title="Teacher — Educational Chatbot",
    page_icon="👨‍🏫",
    layout="wide",
    initial_sidebar_state="expanded",
)

from backend.config import config as app_config
from backend.llm_client import LLMClient
from backend.topic_config import TopicConfig
from backend.topic_generator import TopicGenerator
from backend.logger import get_logger
from session_manager import generate_session_id, save_session
from ui_helpers import t, inject_rtl_css, nav

logger = get_logger(__name__)

_MAX_MATERIAL_CHARS = 15_000
_SCREENS = ("setup", "settings", "share")

# ---------------------------------------------------------------------------
# Session state
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
        "session_id": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar() -> None:
    with st.sidebar:
        st.title(t("Teacher Panel", "פאנל המורה"))
        st.divider()

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

        screen_labels = {
            "setup": t("Setup", "הגדרה"),
            "settings": t("Settings", "הגדרות"),
            "share": t("Share", "שיתוף"),
        }

        st.caption(t("Navigation", "ניווט"))

        tc_ready = st.session_state.topic_config is not None
        session_ready = st.session_state.session_id is not None

        _unlock = {
            "setup": True,
            "settings": tc_ready,
            "share": session_ready,
        }
        for screen, label in screen_labels.items():
            unlocked = _unlock.get(screen, True)
            icon = "" if unlocked else "🔒 "
            if st.button(
                f"{icon}{label}",
                key=f"nav_{screen}",
                use_container_width=True,
                disabled=not unlocked,
            ):
                st.session_state.current_screen = screen
                st.rerun()


# ---------------------------------------------------------------------------
# Screen 1: Setup
# ---------------------------------------------------------------------------

def _screen_setup() -> None:
    st.title(t("Teacher — Setup", "מורה — הגדרה"))

    with st.expander(t("ℹ️ How does this work?", "ℹ️ איך זה עובד?"), expanded=False):
        st.markdown(t(
            """
**The Protégé Effect** — students learn best by teaching.

1. **Paste** learning material (textbook excerpt, article, notes).
2. **Generate** — the AI creates a lesson plan and a virtual struggling student.
3. **Configure** timers and share a session ID with your student.
4. The **student** opens their app, enters the session ID, and starts learning by teaching.
""",
            """
**אפקט הפרוטז'ה** — תלמידים לומדים הכי טוב כשמלמדים.

1. **הדבק** חומר לימוד (קטע מספר, מאמר, הערות).
2. **צור נושא** — הבינה המלאכותית בונה תכנית שיעור ותלמיד וירטואלי.
3. **הגדר** טיימרים ושתף מזהה מפגש עם התלמיד שלך.
4. ה**תלמיד** פותח את האפליקציה שלו, מזין את מזהה המפגש ומתחיל ללמוד דרך הוראה.
""",
        ))

    st.divider()

    tab_gen, tab_load = st.tabs([
        t("✨ Generate New Topic", "✨ צור נושא חדש"),
        t("📂 Load Saved Topic", "📂 טען נושא שמור"),
    ])

    # --- TAB 1: Generate ---
    with tab_gen:
        uploaded = st.file_uploader(
            t("Upload a .txt or .md file (optional)", "העלה קובץ .txt או .md (אופציונלי)"),
            type=["txt", "md"],
            key="material_uploader",
        )
        if uploaded is not None:
            try:
                st.session_state.material_text = uploaded.read().decode("utf-8")
            except Exception as exc:
                st.error(t(f"Could not read file: {exc}", f"לא ניתן לקרוא קובץ: {exc}"))

        material = st.text_area(
            t("Learning material", "חומר לימוד"),
            value=st.session_state.material_text,
            height=280,
            max_chars=_MAX_MATERIAL_CHARS,
            placeholder=t(
                "Paste your lesson content here — textbook excerpt, lecture notes, article…",
                "הדבק כאן את תוכן השיעור — קטע מספר לימוד, הערות הרצאה, מאמר…",
            ),
            key="material_input",
        )
        st.session_state.material_text = material

        char_count = len(material)
        color = "red" if char_count > _MAX_MATERIAL_CHARS else "gray"
        st.markdown(
            f'<small style="color:{color}">'
            + t(f"{char_count:,} / {_MAX_MATERIAL_CHARS:,} characters",
                f"{char_count:,} / {_MAX_MATERIAL_CHARS:,} תווים")
            + "</small>",
            unsafe_allow_html=True,
        )

        st.session_state.student_age = st.number_input(
            t("Student age", "גיל התלמיד"),
            min_value=8, max_value=18,
            value=st.session_state.student_age,
            step=1, key="age_input",
            help=t(
                "The AI tailors vocabulary, examples and difficulty to this age group.",
                "הבינה המלאכותית מתאימה את אוצר המילים, הדוגמאות ורמת הקושי לגיל זה.",
            ),
        )

        if st.button(t("Generate Topic", "צור נושא"), type="primary",
                     use_container_width=True, key="btn_generate"):
            material_val = st.session_state.material_text.strip()
            if not material_val:
                st.error(t("Please enter learning material first.",
                           "אנא הכנס חומר לימוד תחילה."))
            elif len(material_val) > _MAX_MATERIAL_CHARS:
                st.error(t(
                    f"Material exceeds {_MAX_MATERIAL_CHARS:,} characters.",
                    f"החומר עולה על {_MAX_MATERIAL_CHARS:,} תווים.",
                ))
            else:
                with st.spinner(t("Generating topic configuration (2 LLM calls)…",
                                  "יוצר הגדרת נושא (2 קריאות LLM)…")):
                    try:
                        generator = TopicGenerator(LLMClient())
                        tc = generator.generate_topic_config(
                            material_val,
                            target_age=int(st.session_state.student_age),
                        )
                        st.session_state.topic_config = tc
                        save_path = os.path.join(
                            os.path.dirname(os.path.abspath(__file__)), "last_topic.json",
                        )
                        tc.save_to_file(save_path)
                        st.success(t(
                            f"Topic generated: {tc.get_topic_name('en')}",
                            f"נושא נוצר: {tc.get_topic_name('he')}",
                        ))
                        logger.info("Topic generated: %s", tc.topic_name_en)
                        time.sleep(0.8)
                        nav("settings")
                    except Exception as exc:
                        logger.error("Topic generation failed: %s", exc)
                        st.error(t(f"Generation failed: {exc}",
                                   f"יצירת הנושא נכשלה: {exc}"))

    # --- TAB 2: Load saved ---
    with tab_load:
        last_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_topic.json")
        if os.path.isfile(last_path):
            st.info(t(
                "A previously auto-saved topic was found.",
                "נמצא נושא שנשמר אוטומטית.",
            ))
            if st.button(t("⚡ Load Last Auto-Saved Topic", "⚡ טען נושא אחרון שנשמר"),
                         key="btn_load_last", type="primary", use_container_width=True):
                try:
                    tc = TopicConfig.load_from_file(last_path)
                    if tc.is_valid():
                        st.session_state.topic_config = tc
                        st.success(t(f"Loaded: {tc.get_topic_name('en')}",
                                     f"נטען: {tc.get_topic_name('he')}"))
                        time.sleep(0.5)
                        nav("settings")
                    else:
                        st.error(t("Saved topic is invalid.", "הנושא השמור אינו תקין."))
                except Exception as exc:
                    st.error(t(f"Load failed: {exc}", f"הטעינה נכשלה: {exc}"))
            st.divider()

        st.markdown(t("Or upload a topic JSON file:",
                      "או העלה קובץ JSON של נושא:"))
        json_upload = st.file_uploader(
            t("Topic JSON file", "קובץ JSON של נושא"),
            type=["json"], key="json_uploader",
        )
        if json_upload is not None:
            try:
                data = json.load(json_upload)
                tc = TopicConfig.from_dict(data)
                if not tc.is_valid():
                    st.error(t("Loaded topic is invalid.", "הנושא שנטען אינו תקין."))
                else:
                    st.session_state.topic_config = tc
                    st.success(t(f"Loaded: {tc.get_topic_name('en')}",
                                 f"נטען: {tc.get_topic_name('he')}"))
                    time.sleep(0.5)
                    nav("settings")
            except Exception as exc:
                st.error(t(f"Failed to load topic: {exc}",
                           f"טעינת הנושא נכשלה: {exc}"))


# ---------------------------------------------------------------------------
# Screen 2: Settings
# ---------------------------------------------------------------------------

def _list_to_text(items: list[str]) -> str:
    """Join a list of strings into a newline-separated block for text_area."""
    return "\n".join(items)


def _text_to_list(text: str) -> list[str]:
    """Split a text_area value back into a list (one item per non-empty line)."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _screen_settings() -> None:
    tc: Optional[TopicConfig] = st.session_state.topic_config
    if tc is None:
        st.error(t("No topic loaded. Please go back to Setup.",
                    "לא נטען נושא. אנא חזור להגדרה."))
        if st.button(t("Back to Setup", "חזרה להגדרה"), key="settings_back_err"):
            nav("setup")
        return

    lang = st.session_state.lang
    topic_name = tc.get_topic_name(lang)

    st.title(t("Session Settings", "הגדרות מפגש"))
    st.subheader(t(f"Topic: {topic_name}", f"נושא: {topic_name}"))
    st.divider()

    # ---- Timers ----
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.prep_minutes = st.number_input(
            t("Preparation time (minutes)", "זמן הכנה (דקות)"),
            min_value=1, max_value=20,
            value=st.session_state.prep_minutes,
            step=1, key="prep_min_input",
            help=t("Time for the student to review material before teaching.",
                   "זמן לסקירת חומר הלמידה לפני ההוראה."),
        )
    with col2:
        st.session_state.teaching_minutes = st.number_input(
            t("Teaching time (minutes)", "זמן הוראה (דקות)"),
            min_value=3, max_value=60,
            value=st.session_state.teaching_minutes,
            step=1, key="teach_min_input",
            help=t("How long the student has to teach the struggling bot.",
                   "כמה זמן יש לתלמיד ללמד את הבוט המתקשה."),
        )

    subject = tc.get_subject_area(lang)
    if subject:
        st.info(t(f"Subject area: {subject}", f"תחום: {subject}"))

    st.divider()

    # ---- Editable preparation content ----
    st.subheader(t("📝 Student Preparation Content",
                    "📝 תוכן ההכנה לתלמיד"))
    st.caption(t(
        "Review and edit what the student will see during the preparation screen. One item per line for list fields.",
        "סקור וערוך את מה שהתלמיד יראה במסך ההכנה. פריט אחד לכל שורה בשדות רשימה.",
    ))

    edited_concepts = st.text_area(
        t("Key Concepts", "מושגים מרכזיים"),
        value=_list_to_text(tc.get_key_concepts(lang)),
        height=140,
        key="edit_concepts",
    )

    edited_terms = st.text_area(
        t("Key Terms", "מונחים מרכזיים"),
        value=_list_to_text(tc.get_key_terms(lang)),
        height=140,
        key="edit_terms",
    )

    edited_misconceptions = st.text_area(
        t("Common Misconceptions", "תפיסות שגויות נפוצות"),
        value=_list_to_text(tc.get_misconceptions(lang)),
        height=140,
        key="edit_misconceptions",
    )

    edited_examples = st.text_area(
        t("Good Examples & Analogies", "דוגמאות ואנלוגיות טובות"),
        value=_list_to_text(tc.get_good_examples(lang)),
        height=140,
        key="edit_examples",
    )

    edited_summary = st.text_area(
        t("Lesson Summary", "סיכום השיעור"),
        value=tc.get_lesson_summary(lang),
        height=200,
        key="edit_summary",
    )

    st.divider()

    # ---- Buttons ----
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(t("Back to Setup", "חזרה להגדרה"),
                     use_container_width=True, key="settings_back"):
            nav("setup")
    with col_b:
        if st.button(t("Create Session", "צור מפגש"), type="primary",
                     use_container_width=True, key="settings_create"):
            # Apply edits back into the TopicConfig
            if lang == "he":
                tc.key_concepts_he = _text_to_list(edited_concepts)
                tc.key_terms_he = _text_to_list(edited_terms)
                tc.common_misconceptions_he = _text_to_list(edited_misconceptions)
                tc.good_examples_he = _text_to_list(edited_examples)
                tc.lesson_summary_he = edited_summary.strip()
            else:
                tc.key_concepts_en = _text_to_list(edited_concepts)
                tc.key_terms_en = _text_to_list(edited_terms)
                tc.common_misconceptions_en = _text_to_list(edited_misconceptions)
                tc.good_examples_en = _text_to_list(edited_examples)
                tc.lesson_summary_en = edited_summary.strip()
            st.session_state.topic_config = tc

            sid = generate_session_id()
            settings_dict = {
                "prep_minutes": st.session_state.prep_minutes,
                "teaching_minutes": st.session_state.teaching_minutes,
                "student_age": st.session_state.student_age,
                "lang": st.session_state.lang,
            }
            try:
                save_session(sid, tc, settings_dict)
                st.session_state.session_id = sid
                logger.info("Session created: %s", sid)
                nav("share")
            except Exception as exc:
                logger.error("Failed to save session: %s", exc)
                st.error(t(f"Failed to create session: {exc}",
                           f"יצירת המפגש נכשלה: {exc}"))


# ---------------------------------------------------------------------------
# Screen 3: Share
# ---------------------------------------------------------------------------

def _screen_share() -> None:
    sid = st.session_state.session_id
    tc: Optional[TopicConfig] = st.session_state.topic_config

    if sid is None or tc is None:
        st.error(t("No session created yet.", "עדיין לא נוצר מפגש."))
        if st.button(t("Back to Setup", "חזרה להגדרה"), key="share_back_err"):
            nav("setup")
        return

    lang = st.session_state.lang
    topic_name = tc.get_topic_name(lang)

    st.title(t("Share Session", "שתף מפגש"))
    st.divider()

    st.subheader(t("Session ID", "מזהה מפגש"))
    st.code(sid, language=None)

    placeholder_link = f"http://your-server/student?session={sid}"
    st.text_input(
        t("Student link (placeholder)", "קישור לתלמיד (מציין מיקום)"),
        value=placeholder_link,
        disabled=True,
        key="share_link",
    )

    st.divider()
    st.subheader(t("Session Summary", "סיכום מפגש"))

    st.markdown(f"**{t('Topic', 'נושא')}:** {topic_name}")

    m1, m2 = st.columns(2)
    with m1:
        st.metric(t("Prep Time", "זמן הכנה"),
                  t(f"{st.session_state.prep_minutes} min",
                    f"{st.session_state.prep_minutes} דק'"))
    with m2:
        st.metric(t("Teaching Time", "זמן הוראה"),
                  t(f"{st.session_state.teaching_minutes} min",
                    f"{st.session_state.teaching_minutes} דק'"))

    st.divider()

    st.info(t(
        "Give the Session ID to your student. They will enter it in the Student App to start.",
        "תן את מזהה המפגש לתלמיד שלך. הוא יזין אותו באפליקציית התלמיד כדי להתחיל.",
    ))

    col1, col2 = st.columns(2)
    with col1:
        tc_json = json.dumps(tc.to_dict(), ensure_ascii=False, indent=2)
        st.download_button(
            label=t("Download Topic (JSON)", "הורד נושא (JSON)"),
            data=tc_json.encode("utf-8"),
            file_name=f"topic_{tc.topic_name_en.replace(' ', '_')}.json",
            mime="application/json",
            use_container_width=True,
            key="share_download",
        )
    with col2:
        if st.button(t("Create Another Session", "צור מפגש נוסף"),
                     use_container_width=True, key="share_new"):
            st.session_state.topic_config = None
            st.session_state.material_text = ""
            st.session_state.session_id = None
            nav("setup")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _init_session_state()
    inject_rtl_css()
    _render_sidebar()

    screen = st.session_state.current_screen
    if screen == "setup":
        _screen_setup()
    elif screen == "settings":
        _screen_settings()
    elif screen == "share":
        _screen_share()
    else:
        st.error(t(f"Unknown screen: {screen}", f"מסך לא ידוע: {screen}"))
        if st.button(t("Reset", "אפס"), key="unknown_reset"):
            nav("setup")


if __name__ == "__main__":
    main()

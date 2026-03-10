#!/usr/bin/env python3
"""
Student App — Streamlit Frontend (student side)
================================================
Session-ID entry  →  Lesson Prep  →  Chat  →  Evaluation  →  Retrospective

The student enters a session ID provided by the teacher, then proceeds
through the learning-by-teaching flow.
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cloud_helpers import sync_secrets_to_env
sync_secrets_to_env()

import streamlit as st

st.set_page_config(
    page_title="Student — Educational Chatbot",
    page_icon="🧑‍🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

from backend.config import config as app_config
from backend.llm_client import LLMClient
from backend.topic_config import TopicConfig
from backend.conversation_manager import ConversationManager
from backend.logger import get_logger
from backend.prompts import get_retrospective_system_prompt, get_retrospective_opening_message
from backend.response_validator import sanitize_response
from session_manager import load_session
from ui_helpers import (
    t, inject_rtl_css, nav,
    format_time, remaining_seconds,
    component_label, performance_level_label,
    verbal_score_label,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _init_session_state() -> None:
    defaults = {
        "current_screen": "join",
        "lang": app_config.default_language,
        "topic_config": None,
        "student_age": app_config.default_student_age,
        "prep_minutes": app_config.default_prep_minutes,
        "teaching_minutes": app_config.default_teaching_minutes,
        "session_loaded": False,
        "session_id_input": "",
        "student_name": "",
        # lesson
        "lesson_timer_start": None,
        "lesson_timer_seconds": app_config.default_prep_minutes * 60,
        "lesson_auto_advanced": False,
        # chat
        "manager": None,
        "chat_messages": [],
        "mentor_messages": [],
        "chat_timer_start": None,
        "chat_timer_seconds": app_config.default_teaching_minutes * 60,
        "session_ended": False,
        "evaluation_result": None,
        "confirm_eval_pending": False,
        # retrospective
        "retro_messages": [],
        "retro_llm_history": [],
        "retro_initialized": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar() -> None:
    with st.sidebar:
        st.title(t("Student Panel", "פאנל התלמיד"))
        st.divider()

        if st.session_state.session_loaded:
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
            "join": t("Join Session", "הצטרף למפגש"),
            "lesson": t("Lesson Prep", "הכנה"),
            "chat": t("Teaching", "הוראה"),
            "evaluation": t("Evaluation", "הערכה"),
            "retrospective": t("Retrospective", "רטרוספקטיבה"),
        }

        st.caption(t("Navigation", "ניווט"))

        loaded = st.session_state.session_loaded
        manager_ready = st.session_state.manager is not None
        eval_ready = st.session_state.evaluation_result is not None

        _unlock = {
            "join": True,
            "lesson": loaded,
            "chat": manager_ready,
            "evaluation": eval_ready,
            "retrospective": eval_ready,
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
# Join screen (session ID entry)
# ---------------------------------------------------------------------------

def _screen_join() -> None:
    st.title(t("Join a Teaching Session", "הצטרף למפגש הוראה"))

    # Auto-fill session ID from URL query parameter
    query_session = st.query_params.get("session", "")
    if query_session and not st.session_state.session_loaded:
        st.session_state.session_id_input = query_session

    st.info(t(
        "Enter the session ID your teacher gave you.",
        "הזן את מזהה המפגש שהמורה שלך נתן לך.",
    ))

    sid = st.text_input(
        t("Session ID", "מזהה מפגש"),
        value=st.session_state.session_id_input,
        max_chars=20,
        placeholder="e.g. a1b2c3d4",
        key="sid_input",
    )
    st.session_state.session_id_input = sid

    st.session_state.student_name = st.text_input(
        t("Your name (optional)", "השם שלך (אופציונלי)"),
        value=st.session_state.student_name,
        max_chars=50,
        placeholder=t("e.g. Dan", "לדוגמה: דן"),
        key="name_input",
    )

    if st.button(t("Join", "הצטרף"), type="primary",
                 use_container_width=True, key="btn_join"):
        sid_val = sid.strip()
        if not sid_val:
            st.error(t("Please enter a session ID.", "אנא הזן מזהה מפגש."))
            return
        try:
            data = load_session(sid_val)
        except FileNotFoundError:
            st.error(t(f"Session '{sid_val}' not found.",
                       f"מפגש '{sid_val}' לא נמצא."))
            return
        except Exception as exc:
            st.error(t(f"Error loading session: {exc}",
                       f"שגיאה בטעינת מפגש: {exc}"))
            return

        tc = TopicConfig.from_dict(data.get("topic_config", {}))
        if not tc.is_valid():
            st.error(t("Session data is invalid.", "נתוני המפגש אינם תקינים."))
            return

        settings = data.get("settings", {})
        st.session_state.topic_config = tc
        st.session_state.prep_minutes = settings.get("prep_minutes", app_config.default_prep_minutes)
        st.session_state.teaching_minutes = settings.get("teaching_minutes", app_config.default_teaching_minutes)
        st.session_state.student_age = settings.get("student_age", app_config.default_student_age)
        if settings.get("lang"):
            st.session_state.lang = settings["lang"]
        st.session_state.lesson_timer_seconds = st.session_state.prep_minutes * 60
        st.session_state.chat_timer_seconds = st.session_state.teaching_minutes * 60
        st.session_state.session_loaded = True

        logger.info("Student joined session %s | topic='%s'", sid_val, tc.topic_name_en)
        st.success(t(f"Joined session! Topic: {tc.get_topic_name('en')}",
                     f"הצטרפת למפגש! נושא: {tc.get_topic_name('he')}"))
        time.sleep(0.5)
        nav("lesson")


# ---------------------------------------------------------------------------
# Screen 1: Lesson Prep
# ---------------------------------------------------------------------------

def _screen_lesson() -> None:
    tc: Optional[TopicConfig] = st.session_state.topic_config
    if tc is None:
        st.error(t("No topic loaded.", "לא נטען נושא."))
        if st.button(t("Back to Join", "חזרה להצטרפות"), key="lesson_back_err"):
            nav("join")
        return

    lang = st.session_state.lang
    topic_name = tc.get_topic_name(lang)
    total_seconds = st.session_state.prep_minutes * 60

    st.title(t(f"Preparation: {topic_name}", f"הכנה: {topic_name}"))

    # Timer
    if st.session_state.lesson_timer_start is None:
        st.session_state.lesson_timer_start = time.time()

    remaining = remaining_seconds(st.session_state.lesson_timer_start, total_seconds)
    pct = remaining / total_seconds if total_seconds > 0 else 0.0

    timer_col, info_col = st.columns([1, 3])
    with timer_col:
        st.metric(t("Time remaining", "זמן שנותר"), format_time(remaining))
        st.progress(pct)
    with info_col:
        if remaining > 0:
            st.info(t(
                "Read the material carefully. Teaching starts when the timer expires or you click 'Start Teaching'.",
                "קרא את החומר בעיון. ההוראה תתחיל כאשר השעון יסתיים או כשתלחץ על 'התחל הוראה'.",
            ))
        else:
            st.warning(t("Preparation time is up! Start teaching now.",
                         "זמן ההכנה הסתיים! התחל ללמד עכשיו."))

    st.divider()

    # 1. Lesson Summary (first thing student sees)
    st.subheader(t("Lesson Summary", "סיכום השיעור"))
    st.markdown(tc.get_lesson_summary(lang))
    st.divider()

    # 2. Key Concepts & Terms (merged)
    st.subheader(t("Key Concepts & Terms", "מושגים ומונחי מפתח"))
    for concept in tc.get_key_concepts(lang):
        st.markdown(f"- {concept}")
    for term in tc.get_key_terms(lang):
        st.markdown(f"- {term}")
    st.divider()

    # 3. Examples & Analogies
    examples = tc.get_good_examples(lang)
    if examples:
        st.subheader(t("Examples & Analogies", "דוגמאות ואנלוגיות"))
        for ex in examples:
            st.info(ex)
        st.divider()

    # 4. Common Misconceptions (last)
    misconceptions = tc.get_misconceptions(lang)
    if misconceptions:
        st.subheader(t("Common Misconceptions — Watch For", "תפיסות שגויות נפוצות — שימו לב"))
        for misc in misconceptions:
            st.warning(misc)
        st.divider()

    if st.button(t("Start Teaching", "התחל הוראה"), type="primary",
                 use_container_width=True, key="lesson_start_teach"):
        _start_chat_session(tc, lang)

    # Auto-advance
    if remaining <= 0 and not st.session_state.lesson_auto_advanced:
        st.session_state.lesson_auto_advanced = True
        _start_chat_session(tc, lang)
    elif remaining > 0:
        time.sleep(1)
        st.rerun()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _start_chat_session(tc: TopicConfig, lang: str) -> None:
    try:
        manager = ConversationManager(lang=lang, topic_config=tc)
        initial_msg = manager.start_conversation()
        st.session_state.manager = manager
        st.session_state.chat_messages = [{"role": "student", "content": initial_msg}]
        st.session_state.mentor_messages = []
        st.session_state.chat_timer_start = None
        st.session_state.chat_timer_seconds = st.session_state.teaching_minutes * 60
        st.session_state.session_ended = False
        st.session_state.evaluation_result = None
        st.session_state.confirm_eval_pending = False
        nav("chat")
    except Exception as exc:
        logger.error("Failed to start chat session: %s", exc)
        st.error(t(f"Failed to start session: {exc}", f"הפעלת הסשן נכשלה: {exc}"))


def _get_last_teacher_msg() -> str:
    for msg in reversed(st.session_state.chat_messages):
        if msg["role"] == "teacher":
            return msg["content"]
    return ""


def _reset_to_join() -> None:
    for key in [
        "topic_config", "manager", "chat_messages", "mentor_messages",
        "evaluation_result", "session_ended", "lesson_timer_start",
        "chat_timer_start", "lesson_auto_advanced", "retro_messages",
        "retro_llm_history", "retro_initialized", "confirm_eval_pending",
        "session_loaded", "session_id_input",
    ]:
        if key in ("session_loaded", "session_id_input"):
            st.session_state[key] = False if key == "session_loaded" else ""
        elif key in ("chat_messages", "mentor_messages", "retro_messages", "retro_llm_history"):
            st.session_state[key] = []
        elif key in ("session_ended", "lesson_auto_advanced", "retro_initialized", "confirm_eval_pending"):
            st.session_state[key] = False
        else:
            st.session_state[key] = None
    nav("join")


def _save_to_cloud(evaluation_result: dict, manager) -> None:
    """Save evaluation scores to Google Sheets and transcript to Google Drive."""
    from backend.config import config as app_config
    if not app_config.google_spreadsheet_id:
        return  # Cloud storage not configured

    try:
        from backend.google_storage import get_google_storage
        gs = get_google_storage()
        lang = st.session_state.lang
        tc = st.session_state.topic_config

        # Save evaluation scores to Sheets
        gs.save_evaluation(
            session_id=st.session_state.session_id_input,
            student_name=st.session_state.get("student_name", "") or "anonymous",
            evaluation_result=evaluation_result,
            conversation_summary=manager.get_conversation_summary(),
            lang=lang,
        )

        # Save transcript to Google Drive
        transcript = _build_transcript(evaluation_result, tc, lang)
        gs.save_transcript(
            session_id=st.session_state.session_id_input,
            student_name=st.session_state.get("student_name", "") or "anonymous",
            transcript_text=transcript,
        )
        logger.info("Cloud save completed for session %s", st.session_state.session_id_input)
    except Exception as exc:
        logger.error("Cloud save failed (non-blocking): %s", exc)


# ---------------------------------------------------------------------------
# Screen 2: Chat
# ---------------------------------------------------------------------------

def _screen_chat() -> None:
    tc: Optional[TopicConfig] = st.session_state.topic_config
    manager: Optional[ConversationManager] = st.session_state.manager

    if tc is None or manager is None:
        st.error(t("Session not initialised.", "הסשן לא אותחל."))
        if st.button(t("Back to Join", "חזרה להצטרפות"), key="chat_back_err"):
            nav("join")
        return

    lang = st.session_state.lang
    topic_name = tc.get_topic_name(lang)
    total_secs = st.session_state.chat_timer_seconds
    session_ended = st.session_state.session_ended

    st.title(t(f"Teaching: {topic_name}", f"מלמד: {topic_name}"))

    # Timer
    timer_start = st.session_state.chat_timer_start
    if timer_start is not None:
        remaining = remaining_seconds(timer_start, total_secs)
        pct = remaining / total_secs if total_secs > 0 else 0.0
        if remaining < 60:
            timer_color, urgency = "red", t("⛔ Under 1 minute!", "⛔ פחות מדקה!")
        elif remaining < 120:
            timer_color, urgency = "orange", t("⚠️ Almost out of time!", "⚠️ הזמן כמעט נגמר!")
        else:
            timer_color, urgency = "green", ""

        timer_text = t(f"Time remaining: {format_time(remaining)}",
                       f"זמן שנותר: {format_time(remaining)}")
        suffix = f" &nbsp; <strong>{urgency}</strong>" if urgency else ""
        st.markdown(
            f'<p style="font-size:1.1rem;color:{timer_color};">{timer_text}{suffix}</p>',
            unsafe_allow_html=True,
        )
        st.progress(pct)
    else:
        st.info(t("Timer starts on your first message.",
                   "השעון מתחיל עם הודעתך הראשונה."))

    summary = manager.get_conversation_summary()
    st.caption(t(
        f"Turns: {summary['turns']} | Your messages: {summary['student_messages']} | Mentor consultations: {summary['mentor_consultations']}",
        f"תורות: {summary['turns']} | ההודעות שלך: {summary['student_messages']} | התייעצויות עם מנטור: {summary['mentor_consultations']}",
    ))
    st.divider()

    # Layout
    if lang == "he":
        mentor_col, chat_col = st.columns([3, 7])
    else:
        chat_col, mentor_col = st.columns([7, 3])

    # Chat column
    with chat_col:
        st.subheader(t("Conversation", "שיחה"))
        for msg in st.session_state.chat_messages:
            role, content = msg["role"], msg["content"]
            if role == "student":
                with st.chat_message("user", avatar="🧑‍🎓"):
                    st.markdown(content)
            elif role == "teacher":
                with st.chat_message("assistant", avatar="👨‍🏫"):
                    st.markdown(content)

        if not session_ended:
            teacher_input = st.chat_input(
                placeholder=t("Type your explanation here…", "כתוב את הסברך כאן…"),
                key="chat_input_box",
            )
            if teacher_input and teacher_input.strip():
                if st.session_state.chat_timer_start is None:
                    st.session_state.chat_timer_start = time.time()
                st.session_state.chat_messages.append(
                    {"role": "teacher", "content": teacher_input.strip()})
                with st.spinner(t("Student is thinking…", "התלמיד חושב…")):
                    try:
                        student_reply = manager.send_to_student(teacher_input.strip())
                        st.session_state.chat_messages.append(
                            {"role": "student", "content": student_reply})
                    except Exception as exc:
                        logger.error("send_to_student failed: %s", exc)
                        st.error(t(f"Error: {exc}", f"שגיאה: {exc}"))
                st.rerun()
        else:
            st.info(t("Session has ended. See evaluation below.",
                       "הסשן הסתיים. ראה הערכה למטה."))

    # Mentor column
    with mentor_col:
        st.subheader(t("Mentor", "מנטור"))
        if st.session_state.mentor_messages:
            for i, advice in enumerate(st.session_state.mentor_messages, 1):
                with st.expander(t(f"Advice #{i}", f"עצה #{i}"),
                                 expanded=(i == len(st.session_state.mentor_messages))):
                    st.markdown(advice)
        else:
            st.caption(t("No mentor advice yet.", "עדיין אין עצות מנטור."))

        st.divider()

        if not session_ended:
            if st.button(t("Ask Mentor", "שאל מנטור"),
                         use_container_width=True, key="btn_mentor"):
                last_teacher = _get_last_teacher_msg()
                last_student = manager.get_last_student_message()
                if not last_teacher:
                    st.warning(t("Send at least one message first.",
                                 "שלח לפחות הודעה אחת תחילה."))
                else:
                    with st.spinner(t("Consulting mentor…", "מתייעץ עם מנטור…")):
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

        # Evaluation trigger (two-step)
        if not st.session_state.confirm_eval_pending:
            if st.button(t("Get Evaluation", "קבל הערכה"), type="primary",
                         use_container_width=True, key="btn_evaluate"):
                st.session_state.confirm_eval_pending = True
                st.rerun()
        else:
            st.warning(t("⚠️ This will end your session. Are you sure?",
                         "⚠️ פעולה זו תסיים את הסשן. האם אתה בטוח?"))
            c1, c2 = st.columns(2)
            with c1:
                if st.button(t("✅ Confirm", "✅ אישור"), type="primary",
                             use_container_width=True, key="btn_eval_confirm"):
                    st.session_state.confirm_eval_pending = False
                    with st.spinner(t("Evaluating performance…", "מעריך ביצועים…")):
                        try:
                            result = manager.evaluate_performance()
                            st.session_state.evaluation_result = result
                            st.session_state.session_ended = True
                            _save_to_cloud(result, manager)
                        except Exception as exc:
                            logger.error("evaluate_performance failed: %s", exc)
                            st.error(t(f"Evaluation error: {exc}",
                                       f"שגיאת הערכה: {exc}"))
                    if st.session_state.evaluation_result:
                        nav("evaluation")
            with c2:
                if st.button(t("❌ Cancel", "❌ ביטול"),
                             use_container_width=True, key="btn_eval_cancel"):
                    st.session_state.confirm_eval_pending = False
                    st.rerun()

        if st.button(t("Conversation Summary", "סיכום שיחה"),
                     use_container_width=True, key="btn_summary"):
            s = manager.get_conversation_summary()
            st.info(t(
                f"Turns: {s['turns']} | Your msgs: {s['student_messages']} | Mentor: {s['mentor_consultations']}",
                f"תורות: {s['turns']} | הודעות שלך: {s['student_messages']} | מנטור: {s['mentor_consultations']}",
            ))

        st.divider()
        if st.button(t("Restart Conversation", "התחל שיחה מחדש"),
                     use_container_width=True, key="btn_restart"):
            _start_chat_session(tc, lang)

    # Auto-evaluate on timer expiry
    if (timer_start is not None and not session_ended
            and remaining_seconds(timer_start, total_secs) <= 0):
        st.warning(t("Teaching time is up! Auto-evaluating…",
                     "זמן ההוראה הסתיים! מעריך אוטומטית…"))
        with st.spinner(t("Evaluating…", "מעריך…")):
            try:
                result = manager.evaluate_performance()
                st.session_state.evaluation_result = result
                st.session_state.session_ended = True
                _save_to_cloud(result, manager)
            except Exception as exc:
                logger.error("Auto-evaluation failed: %s", exc)
                st.error(t(f"Auto-evaluation failed: {exc}",
                           f"הערכה אוטומטית נכשלה: {exc}"))
        if st.session_state.evaluation_result:
            time.sleep(1)
            nav("evaluation")

    if (timer_start is not None and not session_ended
            and remaining_seconds(timer_start, total_secs) > 0):
        time.sleep(1)
        st.rerun()


# ---------------------------------------------------------------------------
# Screen 3: Evaluation
# ---------------------------------------------------------------------------

def _screen_evaluation() -> None:
    result = st.session_state.evaluation_result
    tc: Optional[TopicConfig] = st.session_state.topic_config

    if result is None:
        st.error(t("No evaluation result found.", "לא נמצאה תוצאת הערכה."))
        if st.button(t("Back to Join", "חזרה להצטרפות"), key="eval_back_err"):
            nav("join")
        return

    lang = st.session_state.lang
    topic_name = tc.get_topic_name(lang) if tc else t("Unknown", "לא ידוע")

    st.title(t("Performance Evaluation", "הערכת ביצועים"))
    st.subheader(t(f"Topic: {topic_name}", f"נושא: {topic_name}"))

    total_score = result.get("total_score", 0)
    max_score = result.get("max_score", 0)
    perf_level = performance_level_label(
        result.get("performance_level", t("Unknown", "לא ידוע")))
    component_scores = result.get("component_scores", {})
    misconceptions_count = result.get("misconceptions_count", 0)
    notes = result.get("notes", "")
    comparison = result.get("comparison", {})
    improvement = comparison.get("improvement") if comparison else None

    st.divider()

    # Score percentage (needed for color logic below)
    score_pct = (total_score / max_score) if max_score else 0.0

    # Performance level — verbal only
    st.markdown(
        f'<h3 style="color:{"green" if score_pct >= 0.7 else "orange" if score_pct >= 0.4 else "red"};">'
        f'{perf_level}</h3>',
        unsafe_allow_html=True,
    )
    st.divider()

    # Per-component verbal feedback
    if component_scores:
        st.subheader(t("Evaluation by Category", "הערכה לפי קטגוריה"))
        for comp_key, score in component_scores.items():
            label = component_label(comp_key)
            verbal = verbal_score_label(score)
            if score == 2:
                icon, color = "✅", "green"
            elif score == 1:
                icon, color = "🔶", "orange"
            else:
                icon, color = "🔴", "red"
            st.markdown(
                f'<p><strong>{label}</strong> — '
                f'<span style="color:{color};">{icon} {verbal}</span></p>',
                unsafe_allow_html=True,
            )

    if notes:
        st.divider()
        st.subheader(t("Feedback", "משוב"))
        st.markdown(notes)

    st.divider()

    # Retrospective CTA
    if st.button(t("Reflect on Your Performance", "חשוב לאחור על הביצועים שלך"),
                 type="primary", use_container_width=True, key="eval_retrospective"):
        st.session_state.retro_messages = []
        st.session_state.retro_llm_history = []
        st.session_state.retro_initialized = False
        nav("retrospective")

    st.divider()

    btn1, btn2, btn3 = st.columns(3)
    with btn1:
        if st.button(t("Try Again", "נסה שוב"), use_container_width=True, key="eval_retry"):
            if tc is not None:
                _start_chat_session(tc, lang)
            else:
                nav("join")
    with btn2:
        if st.button(t("New Session", "מפגש חדש"), use_container_width=True, key="eval_new"):
            _reset_to_join()
    with btn3:
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
    lines: list[str] = []
    topic_name = tc.get_topic_name(lang) if tc else "Unknown Topic"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines.append("=" * 60)
    lines.append(t("EDUCATIONAL CHATBOT — EVALUATION REPORT", "צ'אטבוט חינוכי — דוח הערכה"))
    lines.append(f"{t('Generated', 'נוצר')}: {ts}")
    lines.append(f"{t('Topic', 'נושא')}: {topic_name}")
    lines.append("=" * 60)
    lines.append("")

    total = result.get("total_score", 0)
    max_s = result.get("max_score", 0)
    level = performance_level_label(result.get("performance_level", ""))
    lines.append(t("SCORES", "ציונים"))
    lines.append("-" * 40)
    lines.append(f"{t('Total Score', 'ציון כולל')}: {total} / {max_s}")
    lines.append(f"{t('Performance Level', 'רמת ביצועים')}: {level}")
    lines.append(f"{t('Misconceptions Detected', 'תפיסות שגויות')}: {result.get('misconceptions_count', 0)}")
    lines.append("")

    comp_scores = result.get("component_scores", {})
    if comp_scores:
        lines.append(t("COMPONENT SCORES", "ציוני רכיבים"))
        lines.append("-" * 40)
        for key, score in comp_scores.items():
            lines.append(f"  {component_label(key)}: {score}/2")
        lines.append("")

    notes = result.get("notes", "")
    if notes:
        lines.append(t("FEEDBACK", "משוב"))
        lines.append("-" * 40)
        lines.append(notes)
        lines.append("")

    chat_msgs = st.session_state.get("chat_messages", [])
    if chat_msgs:
        lines.append(t("CONVERSATION TRANSCRIPT", "תמלול השיחה"))
        lines.append("=" * 60)
        for i, msg in enumerate(chat_msgs, 1):
            role_label = (t("Student", "תלמיד") if msg["role"] == "student"
                          else t("Teacher (You)", "מורה (אתה)") if msg["role"] == "teacher"
                          else msg["role"].title())
            lines.append(f"[{i}] {role_label}:")
            lines.append(msg["content"])
            lines.append("")

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
# Screen 4: Retrospective
# ---------------------------------------------------------------------------

def _screen_retrospective() -> None:
    result = st.session_state.evaluation_result
    tc: Optional[TopicConfig] = st.session_state.topic_config
    manager: Optional[ConversationManager] = st.session_state.manager

    if result is None:
        st.error(t("No evaluation result found.", "לא נמצאה תוצאת הערכה."))
        if st.button(t("Back to Join", "חזרה להצטרפות"), key="retro_back_err"):
            nav("join")
        return

    lang = st.session_state.lang
    topic_name = tc.get_topic_name(lang) if tc else t("Unknown", "לא ידוע")

    st.title(t("Retrospective", "רטרוספקטיבה"))
    st.caption(t("Reflect on your teaching session with the help of an AI coach.",
                  "חשוב לאחור על מפגש ההוראה שלך בעזרת מאמן AI."))

    # Initialize
    if not st.session_state.retro_initialized:
        student_history = manager.get_student_history() if manager else []
        mentor_history = manager.get_mentor_history() if manager else []
        conversation_summary = manager.get_conversation_summary() if manager else {}

        system_prompt = get_retrospective_system_prompt(
            lang=lang, evaluation_result=result,
            student_history=student_history, mentor_history=mentor_history,
            topic_name=topic_name, conversation_summary=conversation_summary,
        )
        st.session_state.retro_llm_history = [
            {"role": "system", "content": system_prompt},
        ]
        opening_msg = get_retrospective_opening_message(lang)
        st.session_state.retro_llm_history.append(
            {"role": "user", "content": opening_msg})

        with st.spinner(t("Starting retrospective…", "מתחיל רטרוספקטיבה…")):
            try:
                llm = LLMClient()
                bot_response = llm.chat(
                    messages=st.session_state.retro_llm_history,
                    temperature=0.7, max_tokens=400,
                )
                bot_response = sanitize_response(bot_response, lang)
                st.session_state.retro_llm_history.append(
                    {"role": "assistant", "content": bot_response})
                st.session_state.retro_messages = [
                    {"role": "bot", "content": bot_response}]
                st.session_state.retro_initialized = True
            except Exception as exc:
                logger.error("Retrospective init failed: %s", exc)
                st.error(t(f"Failed to start retrospective: {exc}",
                           f"התחלת הרטרוספקטיבה נכשלה: {exc}"))
                return

    # Score summary
    total_score = result.get("total_score", 0)
    max_score = result.get("max_score", 0)
    perf_level = performance_level_label(result.get("performance_level", ""))
    st.info(t(f"Your performance level: {perf_level}",
              f"רמת הביצועים שלך: {perf_level}"))

    chat_msgs = st.session_state.get("chat_messages", [])
    if chat_msgs:
        with st.expander(t("📜 View teaching session transcript",
                           "📜 צפה בתמליל מפגש ההוראה"), expanded=False):
            for msg in chat_msgs:
                if msg["role"] == "teacher":
                    with st.chat_message("assistant", avatar="👨‍🏫"):
                        st.markdown(msg["content"])
                elif msg["role"] == "student":
                    with st.chat_message("user", avatar="🧑‍🎓"):
                        st.markdown(msg["content"])

    st.divider()

    # Chat display
    for msg in st.session_state.retro_messages:
        if msg["role"] == "user":
            with st.chat_message("user", avatar="👨‍🏫"):
                st.markdown(msg["content"])
        elif msg["role"] == "bot":
            with st.chat_message("assistant", avatar="🪞"):
                st.markdown(msg["content"])

    # User input
    user_input = st.chat_input(
        placeholder=t("Share your thoughts…", "שתף את מחשבותיך…"),
        key="retro_chat_input",
    )
    if user_input and user_input.strip():
        st.session_state.retro_messages.append(
            {"role": "user", "content": user_input.strip()})
        st.session_state.retro_llm_history.append(
            {"role": "user", "content": user_input.strip()})
        with st.spinner(t("Thinking…", "חושב…")):
            try:
                llm = LLMClient()
                bot_response = llm.chat(
                    messages=st.session_state.retro_llm_history,
                    temperature=0.7, max_tokens=400,
                )
                bot_response = sanitize_response(bot_response, lang)
                st.session_state.retro_llm_history.append(
                    {"role": "assistant", "content": bot_response})
                st.session_state.retro_messages.append(
                    {"role": "bot", "content": bot_response})
            except Exception as exc:
                logger.error("Retrospective chat failed: %s", exc)
                st.error(t(f"Error: {exc}", f"שגיאה: {exc}"))
        st.rerun()

    st.divider()
    btn1, btn2, btn3 = st.columns(3)
    with btn1:
        if st.button(t("Back to Evaluation", "חזרה להערכה"),
                     use_container_width=True, key="retro_back_eval"):
            nav("evaluation")
    with btn2:
        if st.button(t("Try Again", "נסה שוב"), type="primary",
                     use_container_width=True, key="retro_retry"):
            if tc is not None:
                _start_chat_session(tc, lang)
            else:
                nav("join")
    with btn3:
        if st.button(t("New Session", "מפגש חדש"),
                     use_container_width=True, key="retro_new"):
            _reset_to_join()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _init_session_state()
    inject_rtl_css()
    _render_sidebar()

    screen = st.session_state.current_screen
    if screen == "join":
        _screen_join()
    elif screen == "lesson":
        _screen_lesson()
    elif screen == "chat":
        _screen_chat()
    elif screen == "evaluation":
        _screen_evaluation()
    elif screen == "retrospective":
        _screen_retrospective()
    else:
        st.error(t(f"Unknown screen: {screen}", f"מסך לא ידוע: {screen}"))
        if st.button(t("Reset", "אפס"), key="unknown_reset"):
            nav("join")


if __name__ == "__main__":
    main()

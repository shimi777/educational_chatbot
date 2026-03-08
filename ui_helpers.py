"""
Shared Streamlit UI helpers used by both teacher_app.py and student_app.py.

Extracted from the original streamlit_app.py to avoid duplication.
"""

import time
import streamlit as st

# ---------------------------------------------------------------------------
# Bilingual helper
# ---------------------------------------------------------------------------

def t(en: str, he: str) -> str:
    """Return the English or Hebrew string based on current language."""
    return he if st.session_state.get("lang", "en") == "he" else en


# ---------------------------------------------------------------------------
# Hebrew label translations
# ---------------------------------------------------------------------------

COMPONENT_LABELS_HE: dict[str, str] = {
    "core_statement": "הצהרת ליבה",
    "formal_form": "צורה פורמלית / מדויקת",
    "conditions": "תנאים / הנחות",
    "mechanism": "מנגנון / סיבה-תוצאה",
    "distinctions": "הבחנות מושגיות",
    "example": "דוגמה / יישום",
    "misconceptions": "טיפול בתפיסות שגויות",
}

PERFORMANCE_LEVELS_HE: dict[str, str] = {
    "Limited Understanding": "הבנה מוגבלת",
    "Developing Understanding": "הבנה מתפתחת",
    "Strong Understanding": "הבנה חזקה",
}


def component_label(key: str) -> str:
    """Return a display label for a component key, respecting language."""
    if st.session_state.get("lang") == "he":
        return COMPONENT_LABELS_HE.get(key, key.replace("_", " ").title())
    return key.replace("_", " ").title()


def performance_level_label(level: str) -> str:
    """Return a translated performance level name, respecting language."""
    if st.session_state.get("lang") == "he":
        return PERFORMANCE_LEVELS_HE.get(level, level)
    return level


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def nav(screen: str) -> None:
    """Navigate to a named screen."""
    st.session_state.current_screen = screen
    st.rerun()


# ---------------------------------------------------------------------------
# RTL CSS injection
# ---------------------------------------------------------------------------

def inject_rtl_css() -> None:
    """Inject RTL CSS when the language is Hebrew."""
    if st.session_state.get("lang") != "he":
        return
    st.markdown(
        """
        <style>
        .main .block-container { direction: rtl; text-align: right; }
        [data-testid="stChatMessage"] { direction: rtl; text-align: right; }
        textarea { direction: rtl; text-align: right; }
        [data-testid="stSidebar"] .block-container { direction: rtl; text-align: right; }
        .stRadio label, .stSelectbox label { direction: rtl; }
        [data-testid="stMetricLabel"] { direction: rtl; text-align: right; }
        h1, h2, h3, h4, h5, h6, p, li { direction: rtl; text-align: right; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Timer utilities
# ---------------------------------------------------------------------------

def format_time(seconds: int) -> str:
    """Format seconds as MM:SS."""
    m, s = divmod(max(0, seconds), 60)
    return f"{m:02d}:{s:02d}"


def elapsed_seconds(start_ts: float) -> int:
    """Return whole seconds elapsed since *start_ts*."""
    return int(time.time() - start_ts)


def remaining_seconds(start_ts: float, total_seconds: int) -> int:
    """Return seconds remaining (clamped to 0)."""
    return max(0, total_seconds - elapsed_seconds(start_ts))

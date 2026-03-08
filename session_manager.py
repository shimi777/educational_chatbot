"""
Session Manager — save / load teaching sessions as JSON files.

Used by teacher_app.py (save) and student_app.py (load) to share
a TopicConfig + settings between the two apps.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from backend.topic_config import TopicConfig

_SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"


def _ensure_sessions_dir() -> Path:
    _SESSIONS_DIR.mkdir(exist_ok=True)
    return _SESSIONS_DIR


def generate_session_id() -> str:
    """Return a short, human-friendly session ID (8 hex chars)."""
    return uuid.uuid4().hex[:8]


def save_session(
    session_id: str,
    topic_config: TopicConfig,
    settings: Dict[str, Any],
) -> Path:
    """
    Persist a teaching session to ``sessions/{session_id}.json``.

    Returns the path to the saved file.
    """
    directory = _ensure_sessions_dir()
    payload = {
        "session_id": session_id,
        "created_at": datetime.now().isoformat(),
        "settings": settings,
        "topic_config": topic_config.to_dict(),
    }
    path = directory / f"{session_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_session(session_id: str) -> Dict[str, Any]:
    """
    Load a previously saved session.

    Raises ``FileNotFoundError`` when the session ID does not exist.
    """
    path = _SESSIONS_DIR / f"{session_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Session '{session_id}' not found.")
    return json.loads(path.read_text(encoding="utf-8"))

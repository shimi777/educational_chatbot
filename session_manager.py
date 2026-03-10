"""
Session Manager — cloud-first, local-fallback session storage.

Uses Google Sheets (via GoogleStorage) when GOOGLE_SPREADSHEET_ID is
configured; otherwise falls back to local JSON files in sessions/ for
offline development.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from backend.logger import get_logger

logger = get_logger(__name__)

_SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"


def _use_cloud() -> bool:
    """Return True if Google Sheets storage is configured."""
    from backend.config import config
    return bool(config.google_spreadsheet_id)


def generate_session_id() -> str:
    """Generate a short, unique session identifier."""
    return uuid.uuid4().hex[:8]


def save_session(
    session_id: str,
    topic_config,          # TopicConfig instance
    settings: Dict[str, Any],
) -> None:
    """Persist a teaching session (cloud or local)."""
    if _use_cloud():
        from backend.google_storage import get_google_storage
        gs = get_google_storage()
        lang = settings.get("lang", "en")
        gs.save_session(
            session_id=session_id,
            topic_config_dict=topic_config.to_dict(),
            settings=settings,
            topic_name=topic_config.get_topic_name(lang),
        )
        return

    # ---- Local JSON fallback ----
    _SESSIONS_DIR.mkdir(exist_ok=True)
    payload = {
        "session_id": session_id,
        "created_at": datetime.now().isoformat(),
        "settings": settings,
        "topic_config": topic_config.to_dict(),
    }
    path = _SESSIONS_DIR / f"{session_id}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Session saved locally: %s", path)


def load_session(session_id: str) -> Dict[str, Any]:
    """Load a session by ID (cloud or local). Raises FileNotFoundError."""
    if _use_cloud():
        from backend.google_storage import get_google_storage
        gs = get_google_storage()
        return gs.load_session(session_id)

    # ---- Local JSON fallback ----
    path = _SESSIONS_DIR / f"{session_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Session '{session_id}' not found.")
    return json.loads(path.read_text(encoding="utf-8"))

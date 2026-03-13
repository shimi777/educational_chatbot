"""
Session Manager — cloud-first, local-fallback session storage.

Uses Google Sheets (via GoogleStorage) when GOOGLE_SPREADSHEET_ID is
configured; otherwise falls back to local JSON files in sessions/ for
offline development.
"""
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from backend.logger import get_logger

logger = get_logger(__name__)

_SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"


def _use_cloud() -> bool:
    """Return True if Google Sheets storage is configured AND accessible."""
    from backend.config import config
    if not config.google_spreadsheet_id:
        return False
    try:
        import gspread  # noqa: F401
    except ModuleNotFoundError:
        logger.warning("gspread not installed — falling back to local session storage.")
        return False
    # Also verify credentials are reachable before committing to cloud mode
    try:
        from backend.google_storage import GoogleStorage
        GoogleStorage._get_credentials()
        return True
    except Exception as exc:
        logger.warning("Google credentials unavailable (%s) — falling back to local storage.", exc)
        return False


def generate_session_id(
    topic_name: str = "",
    bot_knowledge_level: int = 1,
) -> str:
    """Generate a descriptive session identifier.

    Format: ``<topic>_L<level>_<YYYYMMDD>_<short-uuid>``
    Example: ``photosynthesis_L2_20260313_a3f1``
    """
    # Sanitise topic: keep only letters, digits, spaces; collapse to slug
    slug = re.sub(r"[^a-zA-Z0-9\u0590-\u05FF ]+", "", topic_name)
    slug = "_".join(slug.split())[:30]  # max 30 chars, underscored
    if not slug:
        slug = "session"
    date_str = datetime.now().strftime("%Y%m%d")
    short_uid = uuid.uuid4().hex[:4]
    return f"{slug}_L{bot_knowledge_level}_{date_str}_{short_uid}"


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

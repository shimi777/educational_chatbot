"""
Google Sheets + Drive storage layer for the educational chatbot.

Replaces local JSON session storage with cloud-backed persistence
so teacher and student apps can share data across Streamlit Cloud instances.

Google Sheet structure:
  - "Sessions" worksheet: session metadata + serialized TopicConfig
  - "Evaluations" worksheet: per-student evaluation scores

Google Drive:
  - Transcript .txt files uploaded to a shared folder
"""
import json
from datetime import datetime
from typing import Any, Dict, Optional

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

from backend.logger import get_logger

logger = get_logger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

_WS_SESSIONS = "Sessions"
_WS_EVALUATIONS = "Evaluations"
_WS_TRANSCRIPTS = "Transcripts"


class GoogleStorage:
    """Unified Google Sheets + Drive client."""

    def __init__(self, spreadsheet_id: str, drive_folder_id: str = ""):
        self._creds = self._get_credentials()
        self._gc = gspread.authorize(self._creds)
        self._spreadsheet = self._gc.open_by_key(spreadsheet_id)
        self._sessions_ws = self._spreadsheet.worksheet(_WS_SESSIONS)
        self._evaluations_ws = self._spreadsheet.worksheet(_WS_EVALUATIONS)
        self._transcripts_ws = self._spreadsheet.worksheet(_WS_TRANSCRIPTS)
        self._drive_folder_id = drive_folder_id
        self._drive_service = None  # Service accounts lack Drive quota; transcripts go to Sheets
        logger.info(
            "GoogleStorage initialized | spreadsheet=%s drive_folder=%s",
            spreadsheet_id,
            drive_folder_id or "(none)",
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    @staticmethod
    def _get_credentials() -> Credentials:
        """Load Google credentials from st.secrets or local JSON file."""
        # 1. Try st.secrets (Streamlit Cloud)
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            return Credentials.from_service_account_info(creds_dict, scopes=_SCOPES)
        except (KeyError, FileNotFoundError):
            pass

        # 2. Try local JSON file (development)
        from backend.config import config
        from pathlib import Path

        creds_file = config.google_credentials_file
        if creds_file and Path(creds_file).exists():
            return Credentials.from_service_account_file(
                str(creds_file), scopes=_SCOPES
            )

        raise ValueError(
            "No Google credentials found. "
            "Set st.secrets['gcp_service_account'] or GOOGLE_CREDENTIALS_FILE env var."
        )

    # ------------------------------------------------------------------
    # Session operations (replaces session_manager local JSON)
    # ------------------------------------------------------------------

    def save_session(
        self,
        session_id: str,
        topic_config_dict: Dict[str, Any],
        settings: Dict[str, Any],
        topic_name: str = "",
    ) -> None:
        """Append a new session row to the Sessions worksheet."""
        row = [
            session_id,
            datetime.now().isoformat(),
            topic_name,
            json.dumps(settings, ensure_ascii=False),
            json.dumps(topic_config_dict, ensure_ascii=False),
            settings.get("lang", "en"),
            "active",
        ]
        self._sessions_ws.append_row(row, value_input_option="RAW")
        logger.info("Session saved to Sheets: %s", session_id)

    def load_session(self, session_id: str) -> Dict[str, Any]:
        """
        Load a session by ID from the Sessions worksheet.

        Returns dict with keys: session_id, created_at, settings, topic_config.
        Raises FileNotFoundError if not found (mirrors local fallback API).
        """
        cell = self._sessions_ws.find(session_id, in_column=1)
        if cell is None:
            raise FileNotFoundError(f"Session '{session_id}' not found.")

        row = self._sessions_ws.row_values(cell.row)
        # Columns: session_id(0), created_at(1), topic_name(2),
        #          settings_json(3), topic_config_json(4), lang(5), status(6)
        return {
            "session_id": row[0],
            "created_at": row[1] if len(row) > 1 else "",
            "settings": json.loads(row[3]) if len(row) > 3 and row[3] else {},
            "topic_config": json.loads(row[4]) if len(row) > 4 and row[4] else {},
        }

    def session_exists(self, session_id: str) -> bool:
        """Check whether a session ID exists (quick lookup)."""
        return self._sessions_ws.find(session_id, in_column=1) is not None

    # ------------------------------------------------------------------
    # Evaluation operations
    # ------------------------------------------------------------------

    def save_evaluation(
        self,
        session_id: str,
        student_name: str,
        evaluation_result: Dict[str, Any],
        conversation_summary: Dict[str, Any],
        lang: str,
    ) -> None:
        """Append an evaluation row to the Evaluations worksheet."""
        cs = evaluation_result.get("component_scores", {})
        row = [
            session_id,
            student_name,
            datetime.now().isoformat(),
            evaluation_result.get("total_score", 0),
            evaluation_result.get("max_score", 0),
            evaluation_result.get("performance_level", ""),
            cs.get("core_statement", 0),
            cs.get("formal_form", 0),
            cs.get("conditions", 0),
            cs.get("mechanism", 0),
            cs.get("distinctions", 0),
            cs.get("example", 0),
            cs.get("misconceptions", 0),
            evaluation_result.get("misconceptions_count", 0),
            evaluation_result.get("notes", ""),
            conversation_summary.get("turns", 0),
            conversation_summary.get("mentor_consultations", 0),
            lang,
        ]
        self._evaluations_ws.append_row(row, value_input_option="RAW")
        logger.info(
            "Evaluation saved | session=%s student=%s score=%s/%s",
            session_id,
            student_name,
            evaluation_result.get("total_score", "?"),
            evaluation_result.get("max_score", "?"),
        )

    # ------------------------------------------------------------------
    # Transcript operations (Google Drive)
    # ------------------------------------------------------------------

    def save_transcript(
        self,
        session_id: str,
        student_name: str,
        transcript_text: str,
    ) -> Optional[str]:
        """
        Save transcript text to the Transcripts worksheet in Google Sheets.

        Service accounts lack Drive storage quota, so we store transcripts
        in a dedicated Sheets tab instead of Google Drive.

        Returns a placeholder string on success, or None on failure.
        """
        safe_name = (
            student_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{session_id}_{safe_name}_{timestamp}.txt"

        row = [
            session_id,
            student_name,
            datetime.now().isoformat(),
            file_name,
            transcript_text,
        ]
        self._transcripts_ws.append_row(row, value_input_option="RAW")
        logger.info("Transcript saved to Sheets: %s", file_name)
        return file_name


# ---------------------------------------------------------------------------
# Singleton factory (cached per Streamlit session to avoid re-auth)
# ---------------------------------------------------------------------------

@st.cache_resource
def get_google_storage() -> GoogleStorage:
    """Return a cached GoogleStorage instance using config values."""
    from backend.config import config

    return GoogleStorage(
        spreadsheet_id=config.google_spreadsheet_id,
        drive_folder_id=config.google_drive_folder_id,
    )

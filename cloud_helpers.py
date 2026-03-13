"""Helpers for Streamlit Cloud deployment."""
import os


def sync_secrets_to_env():
    """
    Copy st.secrets values to environment variables so that
    Pydantic AppConfig (which reads os.environ) picks them up.

    Must be called BEFORE importing backend.config.
    """
    try:
        import streamlit as st
        _keys = [
            "OPENAI_API_KEY", "MODEL_NAME", "USE_OLLAMA",
            "TEACHER_PASSWORD", "STUDENT_APP_URL",
            "GOOGLE_SPREADSHEET_ID", "GOOGLE_DRIVE_FOLDER_ID",
        ]
        for key in _keys:
            if key in st.secrets and key not in os.environ:
                os.environ[key] = str(st.secrets[key])
    except Exception:
        pass  # Not running in Streamlit or secrets not configured

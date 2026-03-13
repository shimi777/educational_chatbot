#!/usr/bin/env python3
"""
Centralized application configuration using Pydantic Settings.

All configuration is read from environment variables / .env file.
Import the singleton 'config' object anywhere in the project:

    from backend.config import config
    print(config.model_name)
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

# Always resolve .env relative to the project root (one level above this file),
# regardless of where the process is launched from.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class AppConfig(BaseSettings):
    """
    All application configuration in one place.
    Values are read from environment variables (case-insensitive)
    and from a .env file in the project root.
    """

    # ------------------------------------------------------------------ #
    # LLM — Provider selection
    # ------------------------------------------------------------------ #
    use_ollama: bool = Field(False, alias="USE_OLLAMA")

    # ------------------------------------------------------------------ #
    # LLM — OpenAI
    # ------------------------------------------------------------------ #
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    model_name: str = Field("gpt-4o-mini", alias="MODEL_NAME")

    # ------------------------------------------------------------------ #
    # LLM — Ollama (local)
    # ------------------------------------------------------------------ #
    ollama_model: str = Field("llama3.1:8b", alias="OLLAMA_MODEL")
    ollama_base_url: str = Field("http://localhost:11434/v1", alias="OLLAMA_BASE_URL")

    # ------------------------------------------------------------------ #
    # LLM — Resilience
    # ------------------------------------------------------------------ #
    llm_max_retries: int = Field(3, alias="LLM_MAX_RETRIES")
    llm_timeout_seconds: int = Field(60, alias="LLM_TIMEOUT_SECONDS")

    # ------------------------------------------------------------------ #
    # UI defaults (can be overridden via .env for testing)
    # ------------------------------------------------------------------ #
    default_prep_minutes: int = Field(3, alias="DEFAULT_PREP_MINUTES")
    default_teaching_minutes: int = Field(10, alias="DEFAULT_TEACHING_MINUTES")
    default_language: str = Field("en", alias="DEFAULT_LANGUAGE")
    default_student_age: int = Field(10, alias="DEFAULT_STUDENT_AGE")

    # ------------------------------------------------------------------ #
    # Google Cloud Integration
    # ------------------------------------------------------------------ #
    google_spreadsheet_id: str = Field("", alias="GOOGLE_SPREADSHEET_ID")
    google_drive_folder_id: str = Field("", alias="GOOGLE_DRIVE_FOLDER_ID")
    google_credentials_file: str = Field("", alias="GOOGLE_CREDENTIALS_FILE")

    # ------------------------------------------------------------------ #
    # Teacher app security
    # ------------------------------------------------------------------ #
    teacher_password: str = Field("", alias="TEACHER_PASSWORD")

    # ------------------------------------------------------------------ #
    # Deployment
    # ------------------------------------------------------------------ #
    student_app_url: str = Field("http://localhost:8502", alias="STUDENT_APP_URL")

    model_config = {
        "env_file": str(_ENV_FILE),
        "env_file_encoding": "utf-8",
        # Allow both the alias and the Python attribute name
        "populate_by_name": True,
        # Silently ignore extra env vars we don't know about
        "extra": "ignore",
    }


# ---------------------------------------------------------------------------
# Singleton — import this in every module that needs configuration
# ---------------------------------------------------------------------------
config = AppConfig()

#!/usr/bin/env python3
"""
Centralized logging setup for Educational Chatbot.

Usage in any module:
    from backend.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Something happened")
    logger.error("Something went wrong")
"""

import logging
import os
from logging.handlers import RotatingFileHandler

# Log file sits next to the project root (one level up from backend/)
_LOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "chatbot.log"
)

_LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Track whether the root logger has been configured so we don't add
# duplicate handlers when get_logger() is called from multiple modules.
_configured = False


def _configure_root_logger():
    """Configure the root 'chatbot' logger once."""
    global _configured
    if _configured:
        return

    root = logging.getLogger("chatbot")
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # --- Console handler: INFO and above ---
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    root.addHandler(ch)

    # --- Rotating file handler: DEBUG and above ---
    try:
        fh = RotatingFileHandler(
            _LOG_FILE,
            maxBytes=5_000_000,   # 5 MB per file
            backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        root.addHandler(fh)
    except OSError as e:
        # If the file can't be created (e.g. permission error), warn but continue.
        root.warning(f"Could not create log file at {_LOG_FILE}: {e}")

    # Silence overly verbose third-party loggers
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger namespaced under 'chatbot.<name>'.

    Args:
        name: Typically __name__ from the calling module.

    Returns:
        A configured Logger instance.
    """
    _configure_root_logger()
    # Strip the package prefix so names stay short in log output:
    # "backend.llm_client" → "chatbot.llm_client"
    short_name = name.replace("backend.", "").replace("__main__", "main")
    return logging.getLogger(f"chatbot.{short_name}")

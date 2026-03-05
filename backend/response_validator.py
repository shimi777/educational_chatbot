#!/usr/bin/env python3
"""
Response Validator — post-LLM sanitisation for bot output.

Two responsibilities:
1. Profanity filter  — masks offensive Hebrew & English words with '***'.
2. Markdown cleanup  — strips stray markdown artefacts (###, **, ```)
   that LLMs sometimes inject into plain-text chat responses.

No external packages required — pure stdlib + regex.
"""

import re
from backend.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Profanity blocklists
# ---------------------------------------------------------------------------
# Words are stored lowercase; matching is case-insensitive.
# Hebrew words are matched as whole tokens (\b doesn't work reliably with
# Hebrew characters, so we use a Unicode-aware word-boundary approach).

_HEBREW_PROFANITY: set[str] = {
    # Common Hebrew profanity / slurs
    "זונה", "שרמוטה", "מניאק", "מטומטם", "מטומטמת",
    "אידיוט", "אידיוטית", "טמבל", "טמבלית",
    "חרא", "חארה", "לעזאזל", "כוס", "כוסית",
    "זין", "תחת", "חמור", "מפגר", "מפגרת",
    "דביל", "דבילית", "טיפש", "טיפשה",
    "בן זונה", "בת זונה", "יא מניאק", "יא אידיוט",
    "יא טמבל", "יא חמור", "יא מפגר",
    "קללה", "לך מפה", "סתום", "סתמי",
    "כלבה", "חזיר", "חזירה",
}

_ENGLISH_PROFANITY: set[str] = {
    "fuck", "fucking", "fucker", "shit", "shitty",
    "asshole", "bitch", "bastard", "damn", "dammit",
    "crap", "dick", "dickhead", "piss", "slut",
    "whore", "moron", "idiot", "stupid", "retard",
    "retarded", "dumb", "dumbass",
}

# Pre-compile a single regex per language for performance.
# Hebrew: match any blocklist token surrounded by whitespace / punctuation / boundaries.
_HE_PATTERN: re.Pattern | None = None
_EN_PATTERN: re.Pattern | None = None


def _build_patterns() -> None:
    """Compile the profanity regexes once on first use."""
    global _HE_PATTERN, _EN_PATTERN  # noqa: PLW0603

    if _HE_PATTERN is None and _HEBREW_PROFANITY:
        # Sort by length descending so longer phrases match first ("בן זונה" before "זונה")
        sorted_he = sorted(_HEBREW_PROFANITY, key=len, reverse=True)
        escaped = [re.escape(w) for w in sorted_he]
        _HE_PATTERN = re.compile(
            r"(?<!\w)(" + "|".join(escaped) + r")(?!\w)",
            re.IGNORECASE,
        )

    if _EN_PATTERN is None and _ENGLISH_PROFANITY:
        sorted_en = sorted(_ENGLISH_PROFANITY, key=len, reverse=True)
        escaped = [re.escape(w) for w in sorted_en]
        _EN_PATTERN = re.compile(
            r"\b(" + "|".join(escaped) + r")\b",
            re.IGNORECASE,
        )


# ---------------------------------------------------------------------------
# Markdown cleanup
# ---------------------------------------------------------------------------

# Matches heading markers (### …), bold markers (**…**), and code fences (```)
_MD_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_BOLD = re.compile(r"\*{1,2}(.+?)\*{1,2}")
_MD_CODE_FENCE = re.compile(r"```[a-z]*\n?|```")


def _strip_markdown(text: str) -> str:
    """Remove common markdown artefacts from plain-text chat output."""
    text = _MD_CODE_FENCE.sub("", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_BOLD.sub(r"\1", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sanitize_response(text: str, lang: str = "en") -> str:
    """
    Clean an LLM response before it reaches the user.

    Steps:
    1. Strip stray markdown formatting.
    2. Mask profanity (Hebrew + English, regardless of ``lang``).

    Args:
        text: Raw LLM output.
        lang: Current UI language ("en" / "he").  Both blocklists are
              always applied because bilingual mixing can occur.

    Returns:
        Sanitised text, safe for display.
    """
    if not text:
        return text

    _build_patterns()

    cleaned = _strip_markdown(text)

    masked = False
    if _HE_PATTERN:
        cleaned, n = _HE_PATTERN.subn("***", cleaned)
        if n:
            masked = True
    if _EN_PATTERN:
        cleaned, n = _EN_PATTERN.subn("***", cleaned)
        if n:
            masked = True

    if masked:
        logger.warning("Profanity masked in LLM response (lang=%s)", lang)

    return cleaned

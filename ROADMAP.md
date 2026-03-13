# Production-Readiness Roadmap: Educational Chatbot

> **Audience:** Junior-to-mid developer
> **Codebase:** Python Tkinter GUI + OpenAI/Ollama backend
> **Current state:** Working prototype (~2,500 LOC across 6 files)
> **Goal:** Robust, resilient, production-grade application

---

## Current Architecture Overview

```
gui_app.py (1,450 lines — monolithic GUI, all 5 screens)
backend/
├── llm_client.py          (LLM abstraction — no retries, no timeouts)
├── conversation_manager.py (dual-agent orchestration)
├── topic_generator.py     (2-stage EN→HE generation, fragile JSON parsing)
├── topic_config.py        (dataclass with basic validation)
└── prompts.py             (prompt template helpers)
```

**What already works well:**
- Clean separation between GUI and backend logic
- Fully generic TopicConfig (no hardcoded subjects)
- Bilingual EN/HE with full RTL layout support
- Threaded API calls in the GUI (basic non-blocking)
- Topic save/load to JSON

**What's missing:**
- No retry logic, no timeouts on API calls
- No structured logging (only `print()`)
- No LLM output validation (trusts JSON blindly)
- No state persistence for crash recovery
- No unit tests
- GUI is a single 1,450-line file

---

## Sprint 1: Logging, Configuration & LLM Resilience

### Objective
Make the LLM layer reliable. Right now, a single API timeout or rate-limit error crashes the session with no recovery. Fix this first because every other sprint depends on stable LLM calls.

### Technical Requirements

#### 1.1 — Replace all `print()` with structured logging

**File:** Every file in the project
**Library:** Python built-in `logging`

```python
# Add to a new file: backend/logger.py
import logging
import os

def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level))

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    ))
    logger.addHandler(ch)

    # File handler (rotating)
    from logging.handlers import RotatingFileHandler
    fh = RotatingFileHandler(
        "chatbot.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    ))
    logger.addHandler(fh)

    return logger
```

**Action items:**
1. Create `backend/logger.py` with the code above.
2. In every file, replace `print(...)` with `logger.info(...)` / `logger.error(...)`.
3. Use logger names that match the module: `logger = setup_logger("llm_client")`.

#### 1.2 — Add retry logic with exponential backoff to LLMClient

**File:** `backend/llm_client.py`
**Library:** `tenacity` (add to `requirements.txt`)

```python
# requirements.txt — add:
tenacity>=8.2.0
```

Replace the `chat()` method in `LLMClient`:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import RateLimitError, APITimeoutError, APIConnectionError

class LLMClient:
    # ... existing __init__ ...

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError)),
        before_sleep=lambda retry_state: logger.warning(
            f"LLM call failed, retrying in {retry_state.next_action.sleep}s... "
            f"(attempt {retry_state.attempt_number}/3)"
        ),
    )
    def chat(self, messages, temperature=0.7, max_tokens=500) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=60,  # 60-second hard timeout
        )
        return response.choices[0].message.content
```

**What this does:**
- Retries up to 3 times on rate-limit (429), timeout, or connection errors.
- Waits 2s → 4s → 8s between retries (exponential backoff).
- Logs each retry attempt.
- Adds a 60-second timeout so calls never hang forever.
- Non-retryable errors (auth failures, invalid requests) still fail immediately.

#### 1.3 — Centralize configuration with Pydantic

**File:** New file `backend/config.py`
**Library:** `pydantic-settings` (add to `requirements.txt`)

```python
# requirements.txt — add:
pydantic>=2.0
pydantic-settings>=2.0
```

```python
# backend/config.py
from pydantic_settings import BaseSettings
from pydantic import Field

class AppConfig(BaseSettings):
    """All app configuration in one place. Reads from .env automatically."""

    # LLM settings
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    model_name: str = Field("gpt-4o-mini", alias="MODEL_NAME")
    use_ollama: bool = Field(False, alias="USE_OLLAMA")
    ollama_model: str = Field("llama3.1:8b", alias="OLLAMA_MODEL")
    ollama_base_url: str = Field("http://localhost:11434/v1", alias="OLLAMA_BASE_URL")

    # Retry settings
    llm_max_retries: int = 3
    llm_timeout_seconds: int = 60

    # UI defaults
    default_prep_minutes: int = 3
    default_teaching_minutes: int = 10
    default_language: str = "en"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Singleton instance
config = AppConfig()
```

**Action items:**
1. Create `backend/config.py`.
2. Update `llm_client.py` to read from `config` instead of calling `os.getenv()` directly.
3. Update `gui_app.py` to read UI defaults from `config`.

#### 1.4 — Update `.env.example`

```env
# Required for OpenAI mode
OPENAI_API_KEY=sk-your-key-here

# Optional: switch to local Ollama
USE_OLLAMA=false
OLLAMA_MODEL=llama3.1:8b

# Optional: model override
MODEL_NAME=gpt-4o-mini
```

### Validation Checklist — Sprint 1

- [ ] Run the app: `python gui_app.py` — all 5 screens still render correctly.
- [ ] Generate a topic — verify logs appear in `chatbot.log` instead of console-only prints.
- [ ] Simulate a network error (disconnect WiFi mid-generation) — verify the app retries and either recovers or shows a clean error message (not a traceback).
- [ ] Toggle language to Hebrew — verify RTL layout still works.
- [ ] Check that `.env` values are correctly picked up by `AppConfig`.

### Files Changed
| File | Action |
|------|--------|
| `backend/logger.py` | **NEW** — logging setup |
| `backend/config.py` | **NEW** — Pydantic settings |
| `backend/llm_client.py` | **EDIT** — add retry, timeout, use config/logger |
| `backend/conversation_manager.py` | **EDIT** — replace print with logger |
| `backend/topic_generator.py` | **EDIT** — replace print with logger |
| `gui_app.py` | **EDIT** — replace print with logger, use config for defaults |
| `requirements.txt` | **EDIT** — add tenacity, pydantic, pydantic-settings |
| `.env.example` | **EDIT** — document all variables |

---

## Sprint 2: LLM Output Validation & Safe JSON Parsing

### Objective
The LLM returns free-text that we parse as JSON. LLMs hallucinate, truncate output, or return partial JSON. This sprint makes the app survive bad LLM output gracefully.

### Technical Requirements

#### 2.1 — Validate LLM-generated JSON with Pydantic models

**File:** New file `backend/schemas.py`

Define strict Pydantic models for the JSON the LLM is expected to return:

```python
# backend/schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import List

class EvaluationCriterion(BaseModel):
    name: str
    description: str
    weight: float = Field(ge=0, le=1)
    indicators: List[str] = Field(min_length=1)

class TopicGenerationResponse(BaseModel):
    """Schema for the English-generation LLM response."""
    topic_name: str = Field(min_length=1, max_length=200)
    subject_area: str = Field(min_length=1)
    key_concepts: List[str] = Field(min_length=2)
    key_terms: List[str] = Field(min_length=2)
    common_misconceptions: List[str] = Field(min_length=1)
    good_examples: List[str] = Field(min_length=1)
    student_specific_struggles: List[str] = Field(min_length=1)
    student_example_responses: List[str] = Field(min_length=1)
    student_initial_message: str = Field(min_length=20)
    good_explanation_indicators: List[str] = Field(min_length=1)
    bad_explanation_indicators: List[str] = Field(min_length=1)
    evaluation_criteria: List[EvaluationCriterion] = Field(min_length=1)
    lesson_summary: str = Field(min_length=20)

    @field_validator("evaluation_criteria")
    @classmethod
    def weights_must_sum_to_one(cls, criteria):
        total = sum(c.weight for c in criteria)
        if not (0.9 <= total <= 1.1):  # Allow small floating-point drift
            raise ValueError(f"Evaluation weights sum to {total}, expected ~1.0")
        return criteria

class HebrewTranslationResponse(BaseModel):
    """Schema for the Hebrew-translation LLM response."""
    topic_name: str = Field(min_length=1)
    subject_area: str = Field(min_length=1)
    key_concepts: List[str] = Field(min_length=2)
    key_terms: List[str] = Field(min_length=2)
    common_misconceptions: List[str] = Field(min_length=1)
    good_examples: List[str] = Field(min_length=1)
    student_specific_struggles: List[str] = Field(min_length=1)
    student_example_responses: List[str] = Field(min_length=1)
    student_initial_message: str = Field(min_length=10)
    good_explanation_indicators: List[str] = Field(min_length=1)
    bad_explanation_indicators: List[str] = Field(min_length=1)
    evaluation_criteria: List[EvaluationCriterion] = Field(min_length=1)
    lesson_summary: str = Field(min_length=10)
```

#### 2.2 — Robust JSON extraction from LLM output

**File:** `backend/topic_generator.py` — replace `_parse_json_response()`

```python
import re

def _parse_json_response(self, response: str, context: str) -> dict:
    """
    Extract and validate JSON from LLM response.
    Handles: markdown fences, leading/trailing text, truncated JSON.
    """
    text = response.strip()

    # Strategy 1: Extract from markdown code fence
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    # Strategy 2: Find the first { and last } (skip preamble/postamble)
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]

    # Strategy 3: Try to fix truncated JSON (missing closing braces)
    for attempt in range(3):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            text += "}" if text.count("{") > text.count("}") else ""
            text += "]" if text.count("[") > text.count("]") else ""

    raise ValueError(
        f"Failed to parse JSON from LLM ({context}). "
        f"Preview: {response[:300]}..."
    )
```

#### 2.3 — Wire validation into TopicGenerator

**File:** `backend/topic_generator.py`

```python
from backend.schemas import TopicGenerationResponse, HebrewTranslationResponse

def _generate_english_content(self, raw_material, target_age) -> dict:
    # ... existing LLM call ...
    raw_data = self._parse_json_response(response, "English generation")

    # Validate with Pydantic
    try:
        validated = TopicGenerationResponse(**raw_data)
        return validated.model_dump()
    except ValidationError as e:
        logger.error(f"English generation validation failed: {e}")
        raise ValueError(f"LLM returned invalid topic structure: {e}")

def _generate_hebrew_content(self, en_data, target_age) -> dict:
    # ... existing LLM call ...
    raw_data = self._parse_json_response(response, "Hebrew translation")

    try:
        validated = HebrewTranslationResponse(**raw_data)
        return validated.model_dump()
    except ValidationError as e:
        logger.warning(f"Hebrew validation failed, falling back to English: {e}")
        return en_data  # Graceful fallback: use English if Hebrew fails
```

#### 2.4 — Input validation: limit material size

**File:** `gui_app.py` — in `_on_generate_topic()`

```python
MAX_MATERIAL_CHARS = 15_000  # ~3,750 tokens, safe for most models

def _on_generate_topic(self):
    raw_material = self.material_input.get("1.0", tk.END).strip()
    if not raw_material:
        messagebox.showwarning("Warning", "Please paste learning material first.")
        return
    if len(raw_material) > MAX_MATERIAL_CHARS:
        messagebox.showwarning(
            "Warning",
            f"Material is too long ({len(raw_material):,} chars). "
            f"Please shorten to under {MAX_MATERIAL_CHARS:,} characters."
        )
        return
    # ... proceed with generation ...
```

### Validation Checklist — Sprint 2

- [ ] Generate a topic with valid material — works as before.
- [ ] Paste extremely long text (20,000+ chars) — shows a warning, does not send to API.
- [ ] Check `chatbot.log` — validation errors are logged clearly.
- [ ] Hebrew toggle still works — lesson screen shows Hebrew content.
- [ ] If Hebrew generation fails, the app falls back to English content (test by temporarily corrupting the Hebrew prompt).

### Files Changed
| File | Action |
|------|--------|
| `backend/schemas.py` | **NEW** — Pydantic validation models |
| `backend/topic_generator.py` | **EDIT** — robust JSON parsing, validation |
| `gui_app.py` | **EDIT** — input length validation |

---

## Sprint 3: UI Responsiveness & Progress Feedback

### Objective
LLM calls take 5–30 seconds. The current threading prevents full freezes, but the user sees no progress and can't cancel. This sprint adds proper progress indication, cancel support, and prevents accidental double-submissions.

### Technical Requirements

#### 3.1 — Add a progress/status bar component

**File:** `gui_app.py`

Create a reusable status indicator that shows during LLM operations:

```python
class StatusIndicator:
    """Shows animated progress during LLM calls."""

    def __init__(self, parent: tk.Frame, lang: str = "en"):
        self.frame = tk.Frame(parent)
        self.label = tk.Label(self.frame, text="", font=("Segoe UI", 10))
        self.label.pack(side=tk.LEFT, padx=5)
        self.cancel_btn = tk.Button(
            self.frame, text="Cancel", command=self._on_cancel
        )
        self._animation_id = None
        self._cancelled = False

    def show(self, message: str):
        """Show status with animated dots."""
        self._cancelled = False
        self.frame.pack(fill=tk.X, pady=2)
        self.cancel_btn.pack(side=tk.RIGHT, padx=5)
        self._animate(message, 0)

    def hide(self):
        """Hide the status bar."""
        if self._animation_id:
            self.frame.after_cancel(self._animation_id)
        self.frame.pack_forget()

    def _animate(self, message, dots):
        if self._cancelled:
            return
        self.label.config(text=f"{message}{'.' * (dots % 4)}")
        self._animation_id = self.frame.after(
            500, self._animate, message, dots + 1
        )

    def _on_cancel(self):
        self._cancelled = True
        self.hide()

    @property
    def is_cancelled(self):
        return self._cancelled
```

#### 3.2 — Prevent double-clicks and double-submissions

**File:** `gui_app.py` — wrap every button that triggers an API call

```python
def _on_send(self):
    # Disable button immediately
    self.send_btn.config(state=tk.DISABLED)
    self.status.show("Thinking")

    def api_call():
        try:
            response = self.manager.send_to_student(text)
            self.root.after(0, lambda: self._on_student_response(response))
        except Exception as e:
            self.root.after(0, lambda: self._on_api_error(str(e)))
        finally:
            # Always re-enable, even on error
            self.root.after(0, lambda: self.send_btn.config(state=tk.NORMAL))
            self.root.after(0, self.status.hide)

    threading.Thread(target=api_call, daemon=True).start()
```

**Apply this pattern to ALL buttons that trigger LLM calls:**
- `_on_generate_topic()` — "Generate Topic" button
- `_on_send()` — "Send" button in chat
- `_on_ask_mentor()` — "Ask Mentor" button
- `_on_evaluate()` — "Get Evaluation" button

#### 3.3 — Add cancel support to long-running operations

**File:** `backend/llm_client.py`

```python
import threading

class LLMClient:
    def __init__(self, ...):
        # ... existing init ...
        self._cancel_event = threading.Event()

    def cancel(self):
        """Signal cancellation of any in-progress call."""
        self._cancel_event.set()

    def reset_cancel(self):
        """Reset cancellation flag."""
        self._cancel_event.clear()

    def chat(self, messages, temperature=0.7, max_tokens=500) -> str:
        self.reset_cancel()
        # ... existing retry-wrapped call ...
        if self._cancel_event.is_set():
            raise CancellationError("Operation cancelled by user")
        # ... proceed with API call ...
```

#### 3.4 — Thread-safe GUI updates

**File:** `gui_app.py`

Create a helper to ensure all GUI updates happen on the main thread:

```python
def _safe_update(self, callback, *args):
    """Schedule a callback on the main (Tkinter) thread."""
    self.root.after(0, lambda: callback(*args))
```

Use this everywhere instead of raw `self.root.after(0, lambda: ...)`.

### Validation Checklist — Sprint 3

- [ ] Click "Generate Topic" — animated status appears ("Generating topic...").
- [ ] Click "Send" in chat — button grays out until response arrives.
- [ ] Rapidly double-click "Send" — only one message is sent.
- [ ] Click "Cancel" during topic generation — operation stops, no crash.
- [ ] All 5 screens still render. RTL still works.
- [ ] Switch language while a status bar is visible — no crash.

### Files Changed
| File | Action |
|------|--------|
| `gui_app.py` | **EDIT** — StatusIndicator, button disable/enable, cancel support |
| `backend/llm_client.py` | **EDIT** — cancel event threading |

---

## Sprint 4: State Management & Crash Recovery

### Objective
Currently, if the app crashes mid-conversation, all progress is lost. This sprint adds automatic state persistence so users can resume sessions, and introduces a clean state machine for screen transitions.

### Technical Requirements

#### 4.1 — Define an application state model

**File:** New file `backend/app_state.py`

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime

class Screen(str, Enum):
    SETUP = "setup"
    SETTINGS = "settings"
    LESSON = "lesson"
    CHAT = "chat"
    EVALUATION = "evaluation"

class SessionState(BaseModel):
    """Complete snapshot of the application state. JSON-serializable."""

    # Navigation
    current_screen: Screen = Screen.SETUP
    language: str = "en"

    # Topic (serialized TopicConfig)
    topic_config_dict: Optional[dict] = None

    # Settings
    lesson_minutes: int = 3
    teaching_minutes: int = 10

    # Chat state
    student_history: List[Dict[str, str]] = Field(default_factory=list)
    mentor_history: List[Dict] = Field(default_factory=list)
    turn_count: int = 0
    chat_started: bool = False
    remaining_seconds: Optional[int] = None

    # Evaluation
    evaluation_text: Optional[str] = None

    # Metadata
    session_id: str = ""
    last_saved: Optional[str] = None
```

#### 4.2 — Auto-save state on every screen transition

**File:** `gui_app.py`

```python
import uuid

SESSION_FILE = "session_state.json"

class ChatbotGUI:
    def __init__(self, root):
        # ... existing init ...
        self.session_id = str(uuid.uuid4())[:8]
        self._try_restore_session()

    def _save_session(self):
        """Auto-save current state to disk."""
        state = SessionState(
            current_screen=self._current_screen_name(),
            language=self.lang,
            topic_config_dict=self.topic_config.to_dict() if self.topic_config else None,
            lesson_minutes=self.lesson_minutes,
            teaching_minutes=self.teaching_minutes,
            student_history=self.manager.student_history if self.manager else [],
            mentor_history=self.manager.mentor_history if self.manager else [],
            turn_count=self.manager.turn_count if self.manager else 0,
            chat_started=getattr(self, 'chat_started', False),
            remaining_seconds=getattr(self, '_remaining_seconds', None),
            session_id=self.session_id,
            last_saved=datetime.now().isoformat(),
        )
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            f.write(state.model_dump_json(indent=2))

    def _try_restore_session(self):
        """On startup, ask user if they want to resume."""
        if not os.path.exists(SESSION_FILE):
            return
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                state = SessionState.model_validate_json(f.read())
            if state.topic_config_dict:
                resume = messagebox.askyesno(
                    "Resume Session",
                    f"Found a saved session (topic: "
                    f"{state.topic_config_dict.get('topic_name_en', '?')}). "
                    f"Resume?"
                )
                if resume:
                    self._restore_from_state(state)
        except Exception as e:
            logger.warning(f"Could not restore session: {e}")
```

#### 4.3 — Screen transition guard

**File:** `gui_app.py`

Add a method that validates transitions and auto-saves:

```python
# Valid transitions map
VALID_TRANSITIONS = {
    Screen.SETUP: {Screen.SETTINGS},
    Screen.SETTINGS: {Screen.LESSON, Screen.SETUP},
    Screen.LESSON: {Screen.CHAT, Screen.SETUP},
    Screen.CHAT: {Screen.EVALUATION, Screen.SETUP},
    Screen.EVALUATION: {Screen.SETUP, Screen.CHAT},
}

def _navigate_to(self, target: Screen):
    """Central navigation with validation and auto-save."""
    current = self._current_screen_name()
    if target not in VALID_TRANSITIONS.get(current, set()):
        logger.error(f"Invalid transition: {current} → {target}")
        return
    self._save_session()
    self._show_screen(target)
```

#### 4.4 — Conversation history backup

**File:** `backend/conversation_manager.py`

Add a method to export/import conversation state:

```python
def export_state(self) -> dict:
    """Export conversation state for persistence."""
    return {
        "student_history": self.student_history,
        "mentor_history": self.mentor_history,
        "turn_count": self.turn_count,
        "is_initialized": self.is_initialized,
        "lang": self.lang,
    }

def import_state(self, state: dict):
    """Restore conversation state from persistence."""
    self.student_history = state.get("student_history", [])
    self.mentor_history = state.get("mentor_history", [])
    self.turn_count = state.get("turn_count", 0)
    self.is_initialized = state.get("is_initialized", False)
    self.lang = state.get("lang", "en")
```

### Validation Checklist — Sprint 4

- [ ] Start a session, navigate to the Chat screen, close the app.
- [ ] Reopen the app — dialog asks "Resume session?" — click Yes — app restores to Chat screen with conversation history intact.
- [ ] Click No — app starts fresh on Setup screen.
- [ ] Navigate through all 5 screens in order — no crashes, each transition auto-saves.
- [ ] Try an invalid transition (e.g., jump from Setup to Chat) — nothing happens, logged as error.
- [ ] RTL layout still works after session restore.
- [ ] `session_state.json` is valid JSON and can be inspected manually.

### Files Changed
| File | Action |
|------|--------|
| `backend/app_state.py` | **NEW** — SessionState model, Screen enum |
| `gui_app.py` | **EDIT** — save/restore session, navigation guards |
| `backend/conversation_manager.py` | **EDIT** — export/import state |

---

## Sprint 5: Provider Failover & Graceful Degradation

### Objective
If OpenAI is down, the app should try Ollama (or vice versa). If both are down, the app should degrade gracefully — letting the user save their work and retry later — instead of crashing.

### Technical Requirements

#### 5.1 — Multi-provider LLM client with automatic failover

**File:** `backend/llm_client.py` — refactor into provider pattern

```python
class LLMProvider:
    """Base class for LLM providers."""
    def __init__(self, name: str, client: OpenAI, model: str):
        self.name = name
        self.client = client
        self.model = model
        self.is_healthy = True
        self.last_error_time = None

class LLMClient:
    def __init__(self):
        self.providers: List[LLMProvider] = []
        self._init_providers()

    def _init_providers(self):
        """Initialize all configured providers."""
        # Primary: OpenAI
        if config.openai_api_key:
            self.providers.append(LLMProvider(
                name="openai",
                client=OpenAI(api_key=config.openai_api_key),
                model=config.model_name,
            ))

        # Fallback: Ollama (local)
        try:
            ollama_client = OpenAI(
                base_url=config.ollama_base_url, api_key="ollama"
            )
            self.providers.append(LLMProvider(
                name="ollama",
                client=ollama_client,
                model=config.ollama_model,
            ))
        except Exception:
            logger.info("Ollama not available as fallback")

    def chat(self, messages, temperature=0.7, max_tokens=500) -> str:
        """Try each provider in order until one succeeds."""
        errors = []
        for provider in self.providers:
            if not provider.is_healthy:
                # Check if enough time passed to retry unhealthy provider
                if (provider.last_error_time and
                    (time.time() - provider.last_error_time) < 60):
                    continue  # Skip for 60 seconds after failure

            try:
                response = provider.client.chat.completions.create(
                    model=provider.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=config.llm_timeout_seconds,
                )
                provider.is_healthy = True
                return response.choices[0].message.content
            except Exception as e:
                provider.is_healthy = False
                provider.last_error_time = time.time()
                errors.append(f"{provider.name}: {e}")
                logger.warning(f"Provider {provider.name} failed: {e}")

        raise AllProvidersFailedError(
            f"All LLM providers failed:\n" +
            "\n".join(f"  - {e}" for e in errors)
        )
```

#### 5.2 — User-facing error recovery

**File:** `gui_app.py`

When all providers fail, show a recovery dialog instead of crashing:

```python
def _on_api_error(self, error_msg: str):
    """Handle API errors with user recovery options."""
    self.status.hide()
    self._re_enable_buttons()

    result = messagebox.askretrycancel(
        "Connection Error",
        f"Could not reach the AI service.\n\n"
        f"Error: {error_msg[:200]}\n\n"
        f"Retry: Try again\n"
        f"Cancel: Return to current screen (your work is saved)"
    )
    if result:  # Retry
        self._retry_last_action()
    else:
        self._save_session()  # Ensure state is saved
```

#### 5.3 — Health check on startup

**File:** `gui_app.py` — add to `__init__`

```python
def _check_provider_health(self):
    """Quick health check on startup to warn user early."""
    try:
        test_client = LLMClient()
        test_client.chat(
            [{"role": "user", "content": "Hi"}],
            max_tokens=5, temperature=0
        )
        logger.info("LLM provider health check passed")
    except Exception as e:
        messagebox.showwarning(
            "Connection Warning",
            f"Could not connect to AI service: {e}\n\n"
            "You can still load saved topics and review past evaluations."
        )
```

#### 5.4 — Custom exception hierarchy

**File:** New file `backend/exceptions.py`

```python
class ChatbotError(Exception):
    """Base exception for the educational chatbot."""
    pass

class LLMError(ChatbotError):
    """Error related to LLM calls."""
    pass

class AllProvidersFailedError(LLMError):
    """All LLM providers are unavailable."""
    pass

class CancellationError(ChatbotError):
    """User cancelled the operation."""
    pass

class ValidationError(ChatbotError):
    """LLM returned invalid/unparseable output."""
    pass

class SessionError(ChatbotError):
    """Error saving or restoring session state."""
    pass
```

### Validation Checklist — Sprint 5

- [ ] With a valid OpenAI key — app works normally (OpenAI is primary).
- [ ] Set an invalid OpenAI key + valid Ollama running — app automatically falls back to Ollama, logs the failover.
- [ ] Set both invalid — app shows "Connection Error" dialog with Retry/Cancel options.
- [ ] Click Retry after fixing the key — operation succeeds.
- [ ] Click Cancel — app stays on current screen, state is saved.
- [ ] Startup health check: with no valid providers — warning dialog appears but app still launches (offline mode for viewing saved topics).
- [ ] RTL and all 5 screens still work.

### Files Changed
| File | Action |
|------|--------|
| `backend/exceptions.py` | **NEW** — exception hierarchy |
| `backend/llm_client.py` | **EDIT** — multi-provider failover |
| `gui_app.py` | **EDIT** — error recovery dialogs, health check |

---

## Sprint 6: Testing & GUI Modularization

### Objective
The monolithic 1,450-line `gui_app.py` is hard to maintain and impossible to test. This sprint extracts each screen into its own module, adds unit tests for the backend, and adds integration smoke tests for the GUI.

### Technical Requirements

#### 6.1 — Extract screens into separate modules

**New directory structure:**

```
gui/
├── __init__.py
├── app.py                 # Main application class (navigation only)
├── base_screen.py         # Abstract base class for all screens
├── setup_screen.py        # Screen 1: Material input + topic generation
├── settings_screen.py     # Screen 2: Timer configuration
├── lesson_screen.py       # Screen 3: Preparation with countdown
├── chat_screen.py         # Screen 4: Teaching conversation
├── evaluation_screen.py   # Screen 5: Performance results
├── components/
│   ├── __init__.py
│   ├── status_indicator.py  # Reusable progress/cancel widget
│   ├── bidi_text.py         # RTL/LTR text helpers
│   └── timer_widget.py      # Countdown timer widget
```

**Base screen pattern:**

```python
# gui/base_screen.py
import tkinter as tk
from abc import ABC, abstractmethod

class BaseScreen(ABC):
    """Base class for all application screens."""

    def __init__(self, parent: tk.Frame, app: "ChatbotApp"):
        self.parent = parent
        self.app = app  # Reference to main app for navigation & shared state
        self.frame = tk.Frame(parent)

    @abstractmethod
    def build(self):
        """Create all widgets for this screen."""
        pass

    @abstractmethod
    def on_enter(self, **kwargs):
        """Called when navigating TO this screen. Populate data."""
        pass

    @abstractmethod
    def on_leave(self):
        """Called when navigating AWAY from this screen. Cleanup."""
        pass

    @abstractmethod
    def update_language(self, lang: str):
        """Update all text for the given language."""
        pass

    def show(self):
        self.frame.pack(fill=tk.BOTH, expand=True)

    def hide(self):
        self.frame.pack_forget()
```

#### 6.2 — Unit tests for backend

**File:** New directory `tests/`

```
tests/
├── __init__.py
├── conftest.py            # Shared fixtures (mock LLM, sample TopicConfig)
├── test_llm_client.py     # Test retry logic, failover, timeouts
├── test_topic_generator.py # Test JSON parsing, validation, edge cases
├── test_conversation.py   # Test conversation flow, state export/import
├── test_schemas.py        # Test Pydantic validation accepts/rejects correctly
├── test_app_state.py      # Test session save/restore
```

**Libraries:** Add to `requirements.txt`:
```
pytest>=7.4.0
pytest-mock>=3.12.0
```

**Example test — JSON parsing edge cases:**

```python
# tests/test_topic_generator.py
import pytest
from backend.topic_generator import TopicGenerator

class TestJsonParsing:
    def setup_method(self):
        self.gen = TopicGenerator.__new__(TopicGenerator)

    def test_clean_json(self):
        raw = '{"topic_name": "test", "subject_area": "math"}'
        result = self.gen._parse_json_response(raw, "test")
        assert result["topic_name"] == "test"

    def test_json_with_markdown_fence(self):
        raw = '```json\n{"topic_name": "test"}\n```'
        result = self.gen._parse_json_response(raw, "test")
        assert result["topic_name"] == "test"

    def test_json_with_preamble(self):
        raw = 'Here is the JSON:\n{"topic_name": "test"}'
        result = self.gen._parse_json_response(raw, "test")
        assert result["topic_name"] == "test"

    def test_truncated_json_raises(self):
        raw = '{"topic_name": "test", "key_concepts": ['
        with pytest.raises(ValueError, match="Failed to parse"):
            self.gen._parse_json_response(raw, "test")

    def test_empty_response_raises(self):
        with pytest.raises(ValueError):
            self.gen._parse_json_response("", "test")
```

**Example test — LLM retry logic:**

```python
# tests/test_llm_client.py
from unittest.mock import MagicMock, patch
from openai import RateLimitError
from backend.llm_client import LLMClient

def test_retries_on_rate_limit(mock_openai):
    """Verify LLMClient retries on 429 and succeeds on second attempt."""
    client = LLMClient()

    # First call raises RateLimitError, second succeeds
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Hello"
    client.client.chat.completions.create = MagicMock(
        side_effect=[RateLimitError("rate limited", response=MagicMock(), body=None), mock_response]
    )

    result = client.chat([{"role": "user", "content": "test"}])
    assert result == "Hello"
    assert client.client.chat.completions.create.call_count == 2
```

**Example test — Pydantic schema validation:**

```python
# tests/test_schemas.py
import pytest
from backend.schemas import TopicGenerationResponse

def test_valid_response_passes():
    data = {
        "topic_name": "Photosynthesis",
        "subject_area": "Biology",
        "key_concepts": ["Light energy", "Chloroplasts"],
        "key_terms": ["Chlorophyll", "Stomata"],
        "common_misconceptions": ["Plants eat soil"],
        "good_examples": ["Like a solar panel"],
        "student_specific_struggles": ["Confuses with respiration"],
        "student_example_responses": ["Wait, so leaves are like batteries?"],
        "student_initial_message": "I don't understand how plants make food from sunlight...",
        "good_explanation_indicators": ["Uses concrete examples"],
        "bad_explanation_indicators": ["Too much jargon"],
        "evaluation_criteria": [{
            "name": "Clarity", "description": "How clear",
            "weight": 1.0, "indicators": ["Logical"]
        }],
        "lesson_summary": "Plants convert light energy into chemical energy via photosynthesis..."
    }
    result = TopicGenerationResponse(**data)
    assert result.topic_name == "Photosynthesis"

def test_empty_topic_name_fails():
    with pytest.raises(Exception):
        TopicGenerationResponse(topic_name="", subject_area="Biology", ...)

def test_weights_not_summing_to_one_fails():
    with pytest.raises(Exception):
        TopicGenerationResponse(
            ...,
            evaluation_criteria=[
                {"name": "A", "description": "d", "weight": 0.2, "indicators": ["x"]},
                {"name": "B", "description": "d", "weight": 0.2, "indicators": ["x"]},
            ]
        )
```

#### 6.3 — Run tests

```bash
# From project root
python -m pytest tests/ -v --tb=short
```

### Validation Checklist — Sprint 6

- [ ] `python -m pytest tests/ -v` — all tests pass.
- [ ] `python gui_app.py` (or `python -m gui.app`) — app launches, all 5 screens work.
- [ ] RTL/LTR toggle works on every screen.
- [ ] Generate a topic, go through full flow, save evaluation — same behavior as before.
- [ ] Each screen file is under 300 lines.
- [ ] No circular imports between `gui/` and `backend/`.

### Files Changed
| File | Action |
|------|--------|
| `gui/` directory | **NEW** — 8 new files (screens + components) |
| `tests/` directory | **NEW** — 6 test files |
| `gui_app.py` | **DELETE** or keep as thin launcher: `from gui.app import main; main()` |
| `requirements.txt` | **EDIT** — add pytest, pytest-mock |

---

## Summary: Sprint Dependency Graph

```
Sprint 1 ─── Logging, Config, LLM Retries
   │
   ▼
Sprint 2 ─── LLM Output Validation (Pydantic schemas)
   │
   ▼
Sprint 3 ─── UI Progress, Cancel, Button Guards
   │
   ▼
Sprint 4 ─── State Persistence, Crash Recovery
   │
   ▼
Sprint 5 ─── Provider Failover, Graceful Degradation
   │
   ▼
Sprint 6 ─── Testing & GUI Modularization
```

**Sprints must be done in order.** Each builds on the infrastructure from the previous one. Do not skip ahead.

## Updated `requirements.txt` (Final)

```
# Core
openai>=1.12.0
python-dotenv>=1.0.0

# Configuration & Validation (Sprint 1-2)
pydantic>=2.0
pydantic-settings>=2.0

# Retry Logic (Sprint 1)
tenacity>=8.2.0

# Testing (Sprint 6)
pytest>=7.4.0
pytest-mock>=3.12.0
```

## Quick Reference: What Goes Where

| Concern | File(s) | Sprint |
|---------|---------|--------|
| Logging | `backend/logger.py` | 1 |
| Config | `backend/config.py` | 1 |
| LLM retries + timeout | `backend/llm_client.py` | 1 |
| JSON validation schemas | `backend/schemas.py` | 2 |
| Robust JSON parsing | `backend/topic_generator.py` | 2 |
| Input length limits | `gui_app.py` | 2 |
| Progress indicator | `gui/components/status_indicator.py` | 3 |
| Button disable/enable | `gui_app.py` (all screens) | 3 |
| Cancel support | `backend/llm_client.py` + GUI | 3 |
| Session state model | `backend/app_state.py` | 4 |
| Auto-save/restore | `gui_app.py` | 4 |
| Navigation guards | `gui_app.py` | 4 |
| Multi-provider failover | `backend/llm_client.py` | 5 |
| Error recovery dialogs | `gui_app.py` | 5 |
| Custom exceptions | `backend/exceptions.py` | 5 |
| Screen extraction | `gui/*.py` | 6 |
| Unit tests | `tests/*.py` | 6 |

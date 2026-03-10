#!/usr/bin/env python3
"""
LLM Client - Abstraction layer for OpenAI / Ollama.

Improvements over the prototype:
- Configuration via AppConfig (no raw os.getenv() calls)
- Structured logging (no print statements)
- Automatic retry with exponential backoff via tenacity
  (retries on: RateLimitError, APITimeoutError, APIConnectionError)
- Hard timeout on every API call (default 60 s)
"""

from typing import List, Dict, Optional

from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from backend.config import config
from backend.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Exceptions that are safe to retry
# ---------------------------------------------------------------------------
_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError)


class LLMClient:
    """
    Unified interface for LLM calls.
    Supports both OpenAI API and Ollama (local).
    """

    def __init__(self, use_ollama: bool | None = None):
        """
        Initialize LLM client.

        Args:
            use_ollama: Override the config value.  Pass None (default) to
                        read from AppConfig / environment.
        """
        # Allow explicit override; otherwise fall back to config
        self.use_ollama = use_ollama if use_ollama is not None else config.use_ollama

        if self.use_ollama:
            self._init_ollama()
        else:
            self._init_openai()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _init_openai(self):
        """Initialize OpenAI client."""
        if not config.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Add it to your .env file or environment variables."
            )
        self.client = OpenAI(api_key=config.openai_api_key)
        self.model = config.model_name
        logger.info("LLM provider: OpenAI | model: %s", self.model)

    def _init_ollama(self):
        """Initialize Ollama client (local server, OpenAI-compatible API)."""
        self.client = OpenAI(
            base_url=config.ollama_base_url,
            api_key="ollama",  # Ollama does not require a real key
        )
        self.model = config.ollama_model
        logger.info(
            "LLM provider: Ollama | model: %s | url: %s",
            self.model,
            config.ollama_base_url,
        )

    # ------------------------------------------------------------------
    # Core chat method — with retry + timeout
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """
        Send chat messages to the LLM and return the response text.

        Retries automatically on transient errors (rate limits, timeouts,
        connection drops) up to LLM_MAX_RETRIES times with exponential
        backoff.  A hard per-call timeout (LLM_TIMEOUT_SECONDS) prevents
        indefinite hangs.

        Args:
            messages:    List of {"role": ..., "content": ...} dicts.
            temperature: Sampling temperature (0 = deterministic, 1 = creative).
            max_tokens:  Maximum number of tokens in the response.

        Returns:
            The model's response as a plain string.

        Raises:
            Any non-retryable OpenAI exception (e.g. AuthenticationError,
            InvalidRequestError) or the last retryable exception after all
            attempts are exhausted.
        """
        return self._chat_with_retry(messages, temperature, max_tokens, json_mode)

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(config.llm_max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, log_level=20),  # 20 == logging.INFO
        reraise=True,
    )
    def _chat_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        json_mode: bool = False,
    ) -> str:
        """Internal method decorated with retry logic."""
        logger.debug(
            "LLM call | model=%s | msgs=%d | temp=%.2f | max_tokens=%s",
            self.model,
            len(messages),
            temperature,
            max_tokens if max_tokens is not None else "unlimited",
        )
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            timeout=config.llm_timeout_seconds,
        )
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        logger.debug(
            "LLM response | %d chars received",
            len(content) if content else 0,
        )
        return content

    # ------------------------------------------------------------------
    # Usage statistics
    # ------------------------------------------------------------------

    def get_usage_stats(self, response) -> Dict:
        """
        Extract token usage and estimated cost from a raw API response.
        Only meaningful for OpenAI; returns a stub for Ollama.
        """
        if self.use_ollama:
            return {"note": "Usage stats not available for Ollama"}

        try:
            stats = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                # gpt-4o-mini pricing as of early 2025
                "estimated_cost_usd": response.usage.total_tokens * 0.00000015,
            }
            logger.debug("Token usage: %s", stats)
            return stats
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# Quick smoke-test (run directly: python -m backend.llm_client)
# ---------------------------------------------------------------------------

def _test_client():
    """Minimal test: send one message and print the response."""
    logger.info("Running LLMClient smoke test...")
    client = LLMClient()
    messages = [
        {"role": "system", "content": "You are a helpful math tutor."},
        {"role": "user", "content": "Explain what 2+2 equals in one sentence."},
    ]
    response = client.chat(messages, temperature=0.5, max_tokens=60)
    logger.info("Response: %s", response)


if __name__ == "__main__":
    _test_client()

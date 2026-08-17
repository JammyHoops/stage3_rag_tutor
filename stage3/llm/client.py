"""Provider-neutral LLM client.

PROVENANCE — pattern KEPT from AI_IT_Helpdesk (the retry-with-backoff loop
and "vendor specifics stay inside the wrapper" rule); the concrete Gemini
binding was not carried over — the helpdesk had two parallel LLM call
paths using two different Google SDKs, collapsed here to one abstract
interface.

``NullLLM`` exists so the whole pipeline can be exercised offline — wiring
tests, prompt inspection, expert-review dry runs — without an API key or
any network call.

Provider: Google AI Studio / Gemini (``GeminiLLM`` below), via the current
``google-genai`` SDK. Model is configurable (``LLM_MODEL``, default
``gemini-flash-latest``) rather than hard-coded.

On a hard failure, ``generate`` raises ``LLMGenerationError`` instead of
returning ``""`` — see docs/design/FINDINGS_AND_DECISIONS.md §7 for why.
Temperature is 0.2 (``config.py``); see the same section for the
reasoning. See docs/TODO.md for known operational gotchas: free-tier rate
limits, pinned-model-ID 404s, and token-count accounting.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

from ..config import CONFIG

logger = logging.getLogger(__name__)


class LLMGenerationError(RuntimeError):
    """Raised by ``LLMClient.generate`` when every retry attempt failed.

    Deliberately a hard failure, not a silent "". Callers should let this
    propagate past any persistence step (storing a message, advancing
    diagnostic progress, logging an interaction) so a failed turn never
    gets recorded as if it succeeded. ``api/chat.py`` is where it's
    finally caught and turned into a client-facing error response.
    """


class LLMClient(ABC):
    """All agents call ``generate``; vendor specifics stay in subclasses."""

    @abstractmethod
    def _call(self, prompt: str, system: Optional[str]) -> str:
        """Single un-retried provider call. Implement per provider."""
        raise NotImplementedError

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Retry wrapper. Raises ``LLMGenerationError`` on hard failure
        after retries."""
        cfg = CONFIG.llm
        last_error: Optional[Exception] = None

        for attempt in range(cfg.max_retries + 1):
            try:
                logger.info("LLM call attempt %s | provider=%s", attempt + 1, cfg.provider)
                result = self._call(prompt, system)
                if result:
                    return result
                # A call that raised nothing but still came back empty is
                # just as unusable as one that raised — treat it the same
                # way (retry, then eventually raise), not as quiet success.
                last_error = None
                logger.warning(
                    "LLM call returned an empty response with no error (attempt %s)",
                    attempt + 1,
                )
            except Exception as e:  # pragma: no cover
                last_error = e
                logger.warning("LLM call failed (attempt %s): %r", attempt + 1, e)

            if attempt >= cfg.max_retries:
                break
            time.sleep(cfg.retry_backoff_seconds * (2**attempt))

        logger.error("LLM call failed after retries: %r", last_error)
        raise LLMGenerationError(
            f"LLM provider {cfg.provider!r} failed after {cfg.max_retries + 1} attempts."
        ) from last_error


class NullLLM(LLMClient):
    """Offline stand-in: echoes a canned response. No network, no key."""

    def _call(self, prompt: str, system: Optional[str]) -> str:
        return (
            "[NullLLM] No provider configured. Prompt received "
            f"({len(prompt)} chars). Set LLM_PROVIDER in .env and implement "
            "a concrete client in stage3/llm/client.py."
        )


class GeminiLLM(LLMClient):
    """Google AI Studio (Gemini API) client, via the ``google-genai`` SDK.

    Import is lazy (inside __init__, not module-level) so that the
    NullLLM/offline path — used by tests and anyone without a key — never
    requires ``google-genai`` to be installed at all.
    """

    def __init__(self) -> None:
        if not CONFIG.llm.api_key:
            raise ValueError(
                "LLM_API_KEY not set — required for provider='gemini'. "
                "Get a free key at https://aistudio.google.com/apikey and "
                "put it in .env (never commit it)."
            )
        from google import genai
        from google.genai import types as genai_types

        self._types = genai_types
        self._client = genai.Client(api_key=CONFIG.llm.api_key)
        self._model = CONFIG.llm.model or "gemini-flash-latest"

    def _call(self, prompt: str, system: Optional[str]) -> str:
        cfg = CONFIG.llm
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                system_instruction=system,
                temperature=cfg.temperature,
                max_output_tokens=cfg.max_output_tokens,
            ),
        )

        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            logger.info(
                "Gemini call token usage | model=%s prompt=%s completion=%s total=%s",
                self._model,
                usage.prompt_token_count,
                usage.candidates_token_count,
                usage.total_token_count,
            )

        return response.text or ""


def get_client() -> LLMClient:
    """Factory keyed on config. Extend as concrete clients are added."""
    provider = CONFIG.llm.provider.lower()
    if provider in ("", "null", "none"):
        return NullLLM()
    if provider in ("gemini", "google"):
        return GeminiLLM()
    raise ValueError(f"No client implemented for provider {provider!r} yet.")

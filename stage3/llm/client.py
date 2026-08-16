"""Provider-neutral LLM client.

PROVENANCE — pattern KEPT from AI_IT_Helpdesk
``services/llm_agent/gemini_client.py`` (the retry-with-exponential-backoff
loop and the "vendor specifics stay inside the wrapper" rule); the concrete
Gemini binding was NOT carried over.

WHY: the helpdesk repo contained TWO parallel LLM call paths using two
different Google SDKs (the current ``google-genai`` and the deprecated
``google.generativeai``). Collapsing to one abstract interface removes that
duplication and defers the provider decision — the proposal budgets for an
OpenAI or Anthropic account, and the choice should be made once, here, and
justified briefly in Chapter 3 (cost, UK data-processing terms, model
capability for tutoring-style dialogue).

``NullLLM`` exists so the whole pipeline can be exercised offline — wiring
tests, prompt inspection, expert-review dry runs — without an API key and
without transmitting anything.

PROVIDER DECISION — Google AI Studio / Gemini (``GeminiLLM`` below), via the
current ``google-genai`` SDK, not the deprecated ``google.generativeai`` the
helpdesk had a dead duplicate of (see WHY above). Free tier via a personal
Google AI Studio key; model is configurable (``LLM_MODEL``, default
``gemini-flash-latest``) rather than hard-coded, so the choice can be revisited
without touching this class.

DONE (2026-08-14): ``generate`` now RAISES ``LLMGenerationError`` on hard
failure instead of returning ``""``. It used to return an empty string
with a docstring note that "callers must treat an empty string as a
failed turn" — but none of the four call sites (``tutor/chat_session.py``
x3, ``tutor/session.py``) actually checked for it, so a hard failure
silently produced a blank tutor message that got persisted and shown as
if it were a real answer. Caught directly during live verification of
the explanation-method feature (see memory) — not hypothetical. Raising
here, once, structurally prevents every current AND future caller from
repeating that mistake, rather than requiring each call site to
remember an "if answer == \"\":" check. Callers don't need to change:
an exception naturally skips whatever persistence code would have run
after the (now never-returned) empty string.

DONE (2026-08-16): temperature decided — 0.2 (``config.py``'s
``LLMConfig.temperature``), lower than the helpdesk's 0.3. Justification
for Chapter 3: the helpdesk's 0.3 was tuned for open-ended IT-support
chat, where some answer variety across near-duplicate tickets is
harmless. A tutoring turn is grounded in retrieved curriculum extracts and
should stay close to that grounding rather than drift toward
free-generation — lower temperature favours the more literal, reproducible
reading of the source material a defensible dissertation transcript needs,
at some cost to phrasing variety across repeated runs of the same
scenario (an acceptable trade-off here). Left as a plain constant (not
env-overridable) for consistency with ``max_output_tokens``/retry fields
right above it in ``config.py`` — revisit if a real need for per-deployment
tuning appears.

TODO:
    [ ] Free-tier rate limits: Gemini's free Google AI Studio tier has
        per-minute/per-day request caps that can change — if `generate`
        starts failing after retries during real use, check quota first,
        not just network/prompt issues. CONFIRMED directly, TWO separate
        caps on this key for `gemini-3.7-flash`:
          - `GenerateRequestsPerDayPerProjectPerModel-FreeTier`: 20/day
            (2026-08-14 — exhausted by one heavy manual-testing session).
          - `GenerateRequestsPerMinutePerProjectPerModel-FreeTier`: 5/min
            (2026-08-15 — tripped immediately by `evaluation/
            run_scenarios.py` firing 6 calls back-to-back with no
            pacing; fixed there with an inter-scenario delay, NOT here,
            since a real single tutoring turn should still fail fast
            rather than wait out a whole minute — see that module's
            docstring). Worth a paid tier or a second key before any
            evaluation session that needs many real turns quickly.
    [ ] Pinned model IDs (e.g. ``gemini-2.5-flash``) can 404 for specific
        accounts even while still listed by ``client.models.list()`` —
        seen directly during setup ("no longer available to new users").
        Defaulting to the ``-latest`` alias avoids re-hitting this, but if
        that alias itself is ever deprecated, re-run
        ``client.models.list()`` against the real key rather than guessing
        a replacement ID.
    [ ] ``total_token_count`` observed noticeably larger than
        prompt+completion alone (seen directly: prompt=12, completion=1,
        total=125) — current Gemini models bill internal "thinking"
        tokens into the total that aren't broken out separately here. If
        the Chapter 3 budget account needs a prompt/completion/thinking
        breakdown, check ``usage_metadata`` for a thoughts-token field on
        the SDK version in use; don't assume total == prompt + completion.
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

    Deliberately a hard failure, not a silent "" — see module docstring
    "DONE (2026-08-14)". Callers should let this propagate past any
    persistence step (storing a message, advancing diagnostic progress,
    logging an explanation-method interaction) rather than catching it
    early, so a failed turn never gets recorded as if it succeeded. The
    API layer (``api/chat.py``) is where it's finally caught and turned
    into a client-facing error response.
    """


class LLMClient(ABC):
    """All agents call ``generate``; vendor specifics stay in subclasses."""

    @abstractmethod
    def _call(self, prompt: str, system: Optional[str]) -> str:
        """Single un-retried provider call. Implement per provider."""
        raise NotImplementedError

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Retry wrapper (pattern kept from the helpdesk Gemini client).

        Raises ``LLMGenerationError`` on hard failure after retries — see
        that class's docstring for why this is a raise, not a "" return.
        """
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
            # Token-count evidence for the API-budget account (see module
            # docstring) — logged even on the free tier, since Chapter 3
            # still wants real numbers, not just "it was free."
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
    # TODO: elif provider == "openai": return OpenAIClient()
    # TODO: elif provider == "anthropic": return AnthropicClient()
    raise ValueError(f"No client implemented for provider {provider!r} yet.")

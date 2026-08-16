"""Offline tests for llm/client.py's retry-then-raise contract.

Covers the 2026-08-14 fix: LLMClient.generate() raises LLMGenerationError
on hard failure (after retries) or on a call that keeps succeeding with
no exception but empty content — instead of silently returning "" for
callers to (not) check. See that module's docstring for why this
changed: real call sites weren't checking the old "" contract, so a
failed LLM call was producing a blank tutor message that got persisted
and shown to the student as if it were a real answer.
"""

from __future__ import annotations

import unittest

from stage3.config import CONFIG
from stage3.llm.client import LLMClient, LLMGenerationError, NullLLM


class _ScriptedClient(LLMClient):
    """Returns/raises a scripted sequence of outcomes, one per call —
    either a string (returned) or an Exception INSTANCE (raised)."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def _call(self, prompt, system):
        outcome = self._outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _RetryConfigTestCase(unittest.TestCase):
    """Keeps retries fast and deterministic; restores CONFIG afterward —
    same mutate-then-restore pattern as TestGeminiClientFailsFast in
    test_smoke.py."""

    def setUp(self):
        self._orig_max_retries = CONFIG.llm.max_retries
        self._orig_backoff = CONFIG.llm.retry_backoff_seconds
        CONFIG.llm.max_retries = 2
        CONFIG.llm.retry_backoff_seconds = 0.0

    def tearDown(self):
        CONFIG.llm.max_retries = self._orig_max_retries
        CONFIG.llm.retry_backoff_seconds = self._orig_backoff


class TestNullLLMNeverFails(unittest.TestCase):
    def test_offline_generate_never_raises(self):
        out = NullLLM().generate("hello", system="sys")
        self.assertIn("NullLLM", out)


class TestRetryThenRaiseOnException(_RetryConfigTestCase):
    def test_all_attempts_raising_ends_in_generation_error(self):
        client = _ScriptedClient([ValueError("a"), ValueError("b"), ValueError("c")])
        with self.assertRaises(LLMGenerationError):
            client.generate("prompt")
        self.assertEqual(client.calls, 3)  # max_retries=2 -> 3 total attempts

    def test_generation_error_chains_the_last_real_exception(self):
        last = ValueError("the real cause")
        client = _ScriptedClient([ValueError("a"), ValueError("b"), last])
        try:
            client.generate("prompt")
            self.fail("expected LLMGenerationError")
        except LLMGenerationError as e:
            self.assertIs(e.__cause__, last)

    def test_success_after_earlier_failures_returns_the_result(self):
        client = _ScriptedClient([ValueError("a"), "a real answer"])
        result = client.generate("prompt")
        self.assertEqual(result, "a real answer")
        self.assertEqual(client.calls, 2)


class TestRetryThenRaiseOnEmptyNoException(_RetryConfigTestCase):
    def test_empty_string_every_attempt_raises_not_returns(self):
        client = _ScriptedClient(["", "", ""])
        with self.assertRaises(LLMGenerationError):
            client.generate("prompt")
        self.assertEqual(client.calls, 3)

    def test_empty_then_real_content_recovers(self):
        client = _ScriptedClient(["", "finally, real content"])
        result = client.generate("prompt")
        self.assertEqual(result, "finally, real content")

    def test_none_treated_the_same_as_empty_string(self):
        client = _ScriptedClient([None, None, None])
        with self.assertRaises(LLMGenerationError):
            client.generate("prompt")


if __name__ == "__main__":
    unittest.main()

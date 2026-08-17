"""Regression coverage for tutor/chat_session.py's run_chat_turn.

Added 2026-08-17 after finding this path was broken: the normal-tutoring
branch called `bundle.profile_note`, a ContextBundle field removed during
the Stage 1 refactor, so every real tutoring turn past the diagnostic
would have raised AttributeError. Nothing caught it because this module
had no test coverage at all. `search_kb` and the LLM client are stubbed
so this stays a fast, offline test; conversations/student-state DBs are
redirected to a temp file per test via CONFIG, matching the db_path
pattern used elsewhere, since chat_session.py doesn't expose one itself.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stage3.config import CONFIG
from stage3.conversations.store import get_or_create_conversation, init_db as init_conversations_db
from stage3.llm.client import LLMClient
from stage3.student_state.explanation_method import init_db as init_explanation_method_db
from stage3.student_state.store import init_db as init_student_state_db


class _ScriptedLLM(LLMClient):
    def __init__(self, response: str):
        self._response = response

    def _call(self, prompt, system):
        return self._response


class RunChatTurnNormalTurnTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self._tmpdir.name)
        self._orig_conversations_db = CONFIG.paths.conversations_db
        self._orig_student_db = CONFIG.paths.student_db
        CONFIG.paths.conversations_db = tmp / "conversations.db"
        CONFIG.paths.student_db = tmp / "student_state.db"
        init_conversations_db()
        init_student_state_db()
        init_explanation_method_db()

    def tearDown(self):
        CONFIG.paths.conversations_db = self._orig_conversations_db
        CONFIG.paths.student_db = self._orig_student_db
        try:
            self._tmpdir.cleanup()
        except OSError:
            pass  # sqlite can briefly hold a file handle open on Windows

    def test_normal_turn_does_not_crash_and_returns_answer(self):
        from stage3.tutor.chat_session import run_chat_turn

        conversation_id, _ = get_or_create_conversation("SYN-TEST", "biology", "biochemistry")

        with patch(
            "stage3.tutor.chat_session.search_kb",
            return_value=[
                {
                    "doc_id": "isaac_science:cb_carbohydrates__0#0",
                    "content": "Carbohydrates are made of carbon, hydrogen and oxygen.",
                    "provenance_tier": "third_party_education_platform",
                    "source": "isaac_science",
                    "source_url": "https://isaacscience.org/concepts/cb_carbohydrates",
                    "section_title": "Carbohydrates",
                }
            ],
        ):
            result = run_chat_turn(
                student_id="SYN-TEST",
                subject="biology",
                topic="biochemistry",
                conversation_id=conversation_id,
                student_message="What is a carbohydrate made of?",
                diagnostic_status="done",
                diagnostic_questions_asked=3,
                llm=_ScriptedLLM("Carbohydrates contain carbon, hydrogen and oxygen."),
            )

        self.assertEqual(result.answer, "Carbohydrates contain carbon, hydrogen and oxygen.")
        self.assertEqual(result.conversation_id, conversation_id)


if __name__ == "__main__":
    unittest.main()

"""Offline tests for conversation/message persistence — no vectordb/retriever imports."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path


class TestConversationsStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "conversations.db"

        from stage3.conversations.store import init_db

        init_db(self.db_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_create_and_get_conversation(self):
        from stage3.conversations.store import create_conversation, get_conversation

        cid = create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        row = get_conversation(cid, self.db_path)
        self.assertEqual(row["student_id"], "stu-1")
        self.assertEqual(row["subject"], "mathematics")
        self.assertEqual(row["topic"], "algebra")

    def test_unknown_conversation_returns_none(self):
        from stage3.conversations.store import get_conversation

        self.assertIsNone(get_conversation(999, self.db_path))

    def test_list_conversations_filters_by_subject_and_student(self):
        from stage3.conversations.store import create_conversation, list_conversations

        create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        create_conversation("stu-1", "english", "grammar", self.db_path)
        create_conversation("stu-2", "mathematics", "algebra", self.db_path)

        all_for_stu1 = list_conversations("stu-1", db_path=self.db_path)
        self.assertEqual(len(all_for_stu1), 2)

        maths_for_stu1 = list_conversations("stu-1", subject="mathematics", db_path=self.db_path)
        self.assertEqual(len(maths_for_stu1), 1)

    def test_list_student_ids_empty_db(self):
        from stage3.conversations.store import list_student_ids

        self.assertEqual(list_student_ids(self.db_path), [])

    def test_list_student_ids_distinct_and_sorted(self):
        from stage3.conversations.store import create_conversation, list_student_ids

        create_conversation("stu-2", "mathematics", "algebra", self.db_path)
        create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        # Second conversation for stu-1 (different topic) must not duplicate
        # it in the id list.
        create_conversation("stu-1", "english", "grammar", self.db_path)

        self.assertEqual(list_student_ids(self.db_path), ["stu-1", "stu-2"])

    def test_add_and_list_messages_ordering_and_chunk_doc_ids(self):
        from stage3.conversations.store import (
            add_message,
            create_conversation,
            list_messages,
        )

        cid = create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        add_message(cid, "student", "What is x?", db_path=self.db_path)
        add_message(
            cid,
            "tutor",
            "x is the unknown.",
            chunk_doc_ids=["curriculum_docs:maths/spec.md#0"],
            db_path=self.db_path,
        )

        messages = list_messages(cid, self.db_path)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "student")
        self.assertIsNone(messages[0]["chunk_doc_ids"])
        self.assertEqual(messages[1]["role"], "tutor")
        self.assertEqual(messages[1]["chunk_doc_ids"], ["curriculum_docs:maths/spec.md#0"])

    def test_add_and_list_messages_round_trips_attributions(self):
        from stage3.conversations.store import (
            add_message,
            create_conversation,
            list_messages,
        )

        cid = create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        add_message(cid, "student", "What is x?", db_path=self.db_path)
        add_message(
            cid,
            "tutor",
            "x is the unknown.",
            chunk_doc_ids=["isaac_science:cb_carbohydrates__0#0"],
            attributions=[
                {
                    "title": "Carbohydrates",
                    "source_name": "Isaac Science",
                    "source_url": "https://isaacscience.org/concepts/cb_carbohydrates",
                    "licence": "CC BY 4.0",
                    "licence_url": "https://creativecommons.org/licenses/by/4.0/",
                }
            ],
            db_path=self.db_path,
        )

        messages = list_messages(cid, self.db_path)
        self.assertIsNone(messages[0]["attributions"])
        self.assertEqual(len(messages[1]["attributions"]), 1)
        self.assertEqual(messages[1]["attributions"][0]["title"], "Carbohydrates")

    def test_add_message_without_attributions_stores_none(self):
        from stage3.conversations.store import (
            add_message,
            create_conversation,
            list_messages,
        )

        cid = create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        add_message(cid, "tutor", "No sources for this one.", db_path=self.db_path)

        messages = list_messages(cid, self.db_path)
        self.assertIsNone(messages[0]["attributions"])

    def test_recent_messages_bounded_and_chronological(self):
        from stage3.conversations.store import (
            add_message,
            create_conversation,
            recent_messages,
        )

        cid = create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        for i in range(5):
            add_message(cid, "student", f"turn {i}", db_path=self.db_path)

        recent = recent_messages(cid, limit=2, db_path=self.db_path)
        self.assertEqual([m["content"] for m in recent], ["turn 3", "turn 4"])

    def test_add_message_rejects_invalid_role(self):
        from stage3.conversations.store import add_message, create_conversation

        cid = create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        with self.assertRaises(ValueError):
            add_message(cid, "teacher", "not allowed", db_path=self.db_path)

    def test_touch_conversation_updates_timestamp(self):
        from stage3.conversations.store import (
            create_conversation,
            get_conversation,
            touch_conversation,
        )

        cid = create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        before = get_conversation(cid, self.db_path)["updated_at"]
        touch_conversation(cid, self.db_path)
        after = get_conversation(cid, self.db_path)["updated_at"]
        self.assertGreaterEqual(after, before)

    def test_duplicate_create_conversation_rejected_by_unique_constraint(self):
        from stage3.conversations.store import create_conversation

        create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        with self.assertRaises(sqlite3.IntegrityError):
            create_conversation("stu-1", "mathematics", "algebra", self.db_path)

    def test_get_or_create_conversation_returns_same_id_on_repeat_calls(self):
        from stage3.conversations.store import get_or_create_conversation

        first_id, first_created = get_or_create_conversation(
            "stu-1", "mathematics", "algebra", self.db_path
        )
        second_id, second_created = get_or_create_conversation(
            "stu-1", "mathematics", "algebra", self.db_path
        )
        self.assertEqual(first_id, second_id)
        self.assertTrue(first_created)
        self.assertFalse(second_created)

    def test_get_or_create_conversation_creates_when_absent(self):
        from stage3.conversations.store import get_conversation, get_or_create_conversation

        cid, created = get_or_create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        self.assertTrue(created)
        row = get_conversation(cid, self.db_path)
        self.assertEqual(row["student_id"], "stu-1")
        self.assertEqual(row["subject"], "mathematics")
        self.assertEqual(row["topic"], "algebra")
        self.assertEqual(row["diagnostic_status"], "pending")
        self.assertEqual(row["diagnostic_questions_asked"], 0)

    def test_get_or_create_conversation_scoped_per_topic(self):
        from stage3.conversations.store import get_or_create_conversation

        algebra_id, _ = get_or_create_conversation(
            "stu-1", "mathematics", "algebra", self.db_path
        )
        geometry_id, _ = get_or_create_conversation(
            "stu-1", "mathematics", "geometry", self.db_path
        )
        self.assertNotEqual(algebra_id, geometry_id)

    def test_set_diagnostic_progress_updates_fields(self):
        from stage3.conversations.store import (
            create_conversation,
            get_conversation,
            set_diagnostic_progress,
        )

        cid = create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        set_diagnostic_progress(cid, questions_asked=2, status="pending", db_path=self.db_path)
        row = get_conversation(cid, self.db_path)
        self.assertEqual(row["diagnostic_questions_asked"], 2)
        self.assertEqual(row["diagnostic_status"], "pending")

        set_diagnostic_progress(cid, questions_asked=3, status="done", db_path=self.db_path)
        row = get_conversation(cid, self.db_path)
        self.assertEqual(row["diagnostic_questions_asked"], 3)
        self.assertEqual(row["diagnostic_status"], "done")

    def test_set_diagnostic_progress_rejects_invalid_status(self):
        from stage3.conversations.store import create_conversation, set_diagnostic_progress

        cid = create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        with self.assertRaises(ValueError):
            set_diagnostic_progress(cid, questions_asked=1, status="bogus", db_path=self.db_path)

    def test_reset_diagnostic_reverts_to_pending_and_zero(self):
        from stage3.conversations.store import (
            create_conversation,
            get_conversation,
            reset_diagnostic,
            set_diagnostic_progress,
        )

        cid = create_conversation("stu-1", "mathematics", "algebra", self.db_path)
        set_diagnostic_progress(cid, questions_asked=3, status="done", db_path=self.db_path)
        reset_diagnostic(cid, db_path=self.db_path)
        row = get_conversation(cid, self.db_path)
        self.assertEqual(row["diagnostic_status"], "pending")
        self.assertEqual(row["diagnostic_questions_asked"], 0)


if __name__ == "__main__":
    unittest.main()

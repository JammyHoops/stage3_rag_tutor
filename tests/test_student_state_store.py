"""Offline tests for the mastery update rule (EWMA) — no LLM/network."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class TestRecordObservation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "student_state.db"

        from stage3.student_state.store import init_db

        init_db(self.db_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_rejects_invalid_outcome(self):
        from stage3.student_state.store import record_observation

        with self.assertRaises(ValueError):
            record_observation(
                "stu-1", "biology", "biochemistry", 0.7, "diagnostic", self.db_path
            )

    def test_cold_start_estimate_equals_first_outcome(self):
        from stage3.student_state.store import record_observation

        estimate = record_observation(
            "stu-1", "biology", "biochemistry", 1.0, "diagnostic", self.db_path
        )
        self.assertEqual(estimate, 1.0)

    def test_mastery_row_created_with_n_obs_one(self):
        from stage3.student_state.store import get_knowledge_state, record_observation

        record_observation("stu-1", "biology", "biochemistry", 0.5, "diagnostic", self.db_path)
        rows = get_knowledge_state("stu-1", subject="biology", db_path=self.db_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["estimate"], 0.5)
        self.assertEqual(rows[0]["n_obs"], 1)

    def test_ewma_blends_toward_new_outcome_not_replaces(self):
        from stage3.student_state.store import record_observation

        record_observation("stu-1", "biology", "biochemistry", 0.0, "diagnostic", self.db_path)
        second = record_observation(
            "stu-1", "biology", "biochemistry", 1.0, "diagnostic", self.db_path
        )
        # EWMA with alpha=0.35: 0.35*1.0 + 0.65*0.0 = 0.35 — moved toward
        # the new outcome, but not all the way (not a simple overwrite).
        self.assertAlmostEqual(second, 0.35)
        self.assertGreater(second, 0.0)
        self.assertLess(second, 1.0)

    def test_repeated_correct_answers_converge_upward(self):
        from stage3.student_state.store import record_observation

        estimate = 0.0
        for _ in range(20):
            estimate = record_observation(
                "stu-1", "biology", "biochemistry", 1.0, "diagnostic", self.db_path
            )
        self.assertGreater(estimate, 0.95)

    def test_n_obs_increments_across_calls(self):
        from stage3.student_state.store import get_knowledge_state, record_observation

        for outcome in (1.0, 0.5, 0.0):
            record_observation(
                "stu-1", "biology", "biochemistry", outcome, "diagnostic", self.db_path
            )
        rows = get_knowledge_state("stu-1", subject="biology", db_path=self.db_path)
        self.assertEqual(rows[0]["n_obs"], 3)

    def test_separate_topics_tracked_independently(self):
        from stage3.student_state.store import get_knowledge_state, record_observation

        record_observation("stu-1", "biology", "biochemistry", 1.0, "diagnostic", self.db_path)
        record_observation("stu-1", "biology", "genetics", 0.0, "diagnostic", self.db_path)

        rows = {
            r["topic"]: r for r in get_knowledge_state("stu-1", subject="biology", db_path=self.db_path)
        }
        self.assertEqual(rows["biochemistry"]["estimate"], 1.0)
        self.assertEqual(rows["genetics"]["estimate"], 0.0)

    def test_unseen_topic_returns_no_rows(self):
        from stage3.student_state.store import get_knowledge_state

        rows = get_knowledge_state("stu-1", subject="biology", db_path=self.db_path)
        self.assertEqual(rows, [])


class TestSeedMasteryPrior(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "student_state.db"

        from stage3.student_state.store import init_db

        init_db(self.db_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_row_with_n_obs_zero(self):
        from stage3.student_state.store import get_knowledge_state, seed_mastery_prior

        seed_mastery_prior("stu-1", "biology", "biochemistry", 0.15, self.db_path)
        rows = get_knowledge_state("stu-1", subject="biology", db_path=self.db_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["estimate"], 0.15)
        self.assertEqual(rows[0]["n_obs"], 0)

    def test_never_overwrites_an_existing_row(self):
        from stage3.student_state.store import (
            get_knowledge_state,
            record_observation,
            seed_mastery_prior,
        )

        record_observation("stu-1", "biology", "biochemistry", 1.0, "diagnostic", self.db_path)
        seed_mastery_prior("stu-1", "biology", "biochemistry", 0.15, self.db_path)
        rows = get_knowledge_state("stu-1", subject="biology", db_path=self.db_path)
        # Real observation must survive untouched — the seed is a no-op
        # once real data exists.
        self.assertEqual(rows[0]["estimate"], 1.0)
        self.assertEqual(rows[0]["n_obs"], 1)

    def test_first_real_observation_blends_into_the_seed(self):
        from stage3.student_state.store import (
            get_knowledge_state,
            record_observation,
            seed_mastery_prior,
        )

        seed_mastery_prior("stu-1", "biology", "biochemistry", 0.15, self.db_path)
        estimate = record_observation(
            "stu-1", "biology", "biochemistry", 1.0, "diagnostic", self.db_path
        )
        # EWMA branch (row already existed), NOT the cold-start
        # new_estimate=outcome branch — alpha=0.35:
        # 0.35*1.0 + 0.65*0.15 = 0.4475, not a fresh 1.0.
        self.assertAlmostEqual(estimate, 0.4475)
        rows = get_knowledge_state("stu-1", subject="biology", db_path=self.db_path)
        # n_obs counts only the real observation, not the seed.
        self.assertEqual(rows[0]["n_obs"], 1)


if __name__ == "__main__":
    unittest.main()

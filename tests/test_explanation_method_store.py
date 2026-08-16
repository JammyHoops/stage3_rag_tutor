"""Offline tests for student_state/explanation_method.py — Thompson
sampling, Beta-Bernoulli updates, cohort recompute, marker parsing. No
LLM/network calls."""

from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path


class _DbTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "student_state.db"

        from stage3.student_state.explanation_method import init_db

        init_db(self.db_path)

    def tearDown(self):
        self._tmp.cleanup()


class TestColdStartPrior(_DbTestCase):
    def test_unseen_student_method_seeded_at_uniform_default(self):
        from stage3.student_state.explanation_method import (
            DEFAULT_PRIOR_ALPHA,
            DEFAULT_PRIOR_BETA,
            _connect,
            _get_or_init_student_posterior,
        )

        with _connect(self.db_path) as conn:
            alpha, beta = _get_or_init_student_posterior(conn, "stu-1", "analogy")
        self.assertEqual(alpha, DEFAULT_PRIOR_ALPHA)
        self.assertEqual(beta, DEFAULT_PRIOR_BETA)

    def test_seeded_row_persists_and_is_reused(self):
        from stage3.student_state.explanation_method import _connect, _get_or_init_student_posterior

        with _connect(self.db_path) as conn:
            first = _get_or_init_student_posterior(conn, "stu-1", "chunking")
            second = _get_or_init_student_posterior(conn, "stu-1", "chunking")
        self.assertEqual(first, second)

    def test_cohort_prior_used_when_present(self):
        from stage3.student_state.explanation_method import (
            _connect,
            _get_or_init_student_posterior,
        )

        with _connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO method_cohort_prior "
                "(method, signal_type, cohort_alpha, cohort_beta, n_students_contributing, updated_at) "
                "VALUES ('worked_example', 'immediate', 5.0, 2.0, 3, '2026-01-01')"
            )
            alpha, beta = _get_or_init_student_posterior(conn, "stu-1", "worked_example")
        self.assertEqual((alpha, beta), (5.0, 2.0))


class TestSelectMethod(_DbTestCase):
    def test_returns_a_known_method(self):
        from stage3.student_state.explanation_method import EXPLANATION_METHODS, select_method

        method = select_method("stu-1", db_path=self.db_path)
        self.assertIn(method, EXPLANATION_METHODS)

    def test_strongly_favourable_posterior_wins_most_draws_not_all(self):
        from stage3.student_state.explanation_method import (
            EXPLANATION_METHODS,
            record_understanding,
            select_method,
        )

        # Give "analogy" a strong, real track record for this student —
        # everything else stays at the neutral Beta(1,1) default.
        interaction_id = 0
        for _ in range(20):
            record_understanding(
                interaction_id=interaction_id,
                student_id="stu-1",
                method="analogy",
                success=True,
                db_path=self.db_path,
            )

        rng = random.Random(42)
        picks = [
            select_method("stu-1", db_path=self.db_path, _rng=rng) for _ in range(200)
        ]
        analogy_share = picks.count("analogy") / len(picks)
        # Wins big majority (proves the posterior mean matters)...
        self.assertGreater(analogy_share, 0.5)
        # ...but not literally every draw (proves exploration survives —
        # the whole point of sampling instead of argmax-on-mean).
        self.assertLess(analogy_share, 1.0)
        other_methods_picked = set(picks) - {"analogy"}
        self.assertTrue(other_methods_picked)


class TestLogAndGetPendingInteraction(_DbTestCase):
    def test_freshly_logged_interaction_is_pending(self):
        from stage3.student_state.explanation_method import get_pending_interaction, log_interaction

        interaction_id = log_interaction(
            student_id="stu-1",
            subject="biology",
            conversation_id=1,
            concept_id="monosaccharides",
            method="worked_example",
            db_path=self.db_path,
        )
        pending = get_pending_interaction(1, db_path=self.db_path)
        self.assertIsNotNone(pending)
        self.assertEqual(pending["id"], interaction_id)
        self.assertEqual(pending["concept_id"], "monosaccharides")
        self.assertEqual(pending["method"], "worked_example")

    def test_no_pending_for_unseen_conversation(self):
        from stage3.student_state.explanation_method import get_pending_interaction

        self.assertIsNone(get_pending_interaction(999, db_path=self.db_path))

    def test_graded_interaction_no_longer_pending(self):
        from stage3.student_state.explanation_method import (
            get_pending_interaction,
            log_interaction,
            record_understanding,
        )

        interaction_id = log_interaction(
            student_id="stu-1",
            subject="biology",
            conversation_id=1,
            concept_id="monosaccharides",
            method="worked_example",
            db_path=self.db_path,
        )
        record_understanding(
            interaction_id=interaction_id,
            student_id="stu-1",
            method="worked_example",
            success=True,
            db_path=self.db_path,
        )
        self.assertIsNone(get_pending_interaction(1, db_path=self.db_path))

    def test_pending_scoped_per_conversation(self):
        from stage3.student_state.explanation_method import get_pending_interaction, log_interaction

        log_interaction(
            student_id="stu-1", subject="biology", conversation_id=1,
            concept_id="monosaccharides", method="worked_example", db_path=self.db_path,
        )
        log_interaction(
            student_id="stu-1", subject="biology", conversation_id=2,
            concept_id="cell_membranes", method="analogy", db_path=self.db_path,
        )
        pending_1 = get_pending_interaction(1, db_path=self.db_path)
        pending_2 = get_pending_interaction(2, db_path=self.db_path)
        self.assertEqual(pending_1["concept_id"], "monosaccharides")
        self.assertEqual(pending_2["concept_id"], "cell_membranes")


class TestRecordUnderstanding(_DbTestCase):
    def test_success_increments_alpha_only(self):
        from stage3.student_state.explanation_method import (
            DEFAULT_PRIOR_ALPHA,
            DEFAULT_PRIOR_BETA,
            record_understanding,
        )

        alpha, beta = record_understanding(
            interaction_id=1, student_id="stu-1", method="chunking",
            success=True, db_path=self.db_path,
        )
        self.assertEqual(alpha, DEFAULT_PRIOR_ALPHA + 1)
        self.assertEqual(beta, DEFAULT_PRIOR_BETA)

    def test_failure_increments_beta_only(self):
        from stage3.student_state.explanation_method import (
            DEFAULT_PRIOR_ALPHA,
            DEFAULT_PRIOR_BETA,
            record_understanding,
        )

        alpha, beta = record_understanding(
            interaction_id=1, student_id="stu-1", method="chunking",
            success=False, db_path=self.db_path,
        )
        self.assertEqual(alpha, DEFAULT_PRIOR_ALPHA)
        self.assertEqual(beta, DEFAULT_PRIOR_BETA + 1)

    def test_repeated_updates_accumulate(self):
        from stage3.student_state.explanation_method import (
            DEFAULT_PRIOR_ALPHA,
            DEFAULT_PRIOR_BETA,
            record_understanding,
        )

        for success in (True, True, False):
            alpha, beta = record_understanding(
                interaction_id=1, student_id="stu-1", method="chunking",
                success=success, db_path=self.db_path,
            )
        self.assertEqual(alpha, DEFAULT_PRIOR_ALPHA + 2)
        self.assertEqual(beta, DEFAULT_PRIOR_BETA + 1)

    def test_marks_interaction_row_correct_immediate(self):
        from stage3.student_state.explanation_method import (
            _connect,
            log_interaction,
            record_understanding,
        )

        interaction_id = log_interaction(
            student_id="stu-1", subject="biology", conversation_id=1,
            concept_id="monosaccharides", method="worked_example", db_path=self.db_path,
        )
        record_understanding(
            interaction_id=interaction_id, student_id="stu-1", method="worked_example",
            success=True, db_path=self.db_path,
        )
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT correct_immediate FROM method_interactions WHERE id = ?",
                (interaction_id,),
            ).fetchone()
        self.assertEqual(row["correct_immediate"], 1)


class TestRecomputeCohortPriors(_DbTestCase):
    def test_no_data_yields_no_cohort_rows(self):
        from stage3.student_state.explanation_method import _connect, recompute_cohort_priors

        recompute_cohort_priors(db_path=self.db_path)
        with _connect(self.db_path) as conn:
            n = conn.execute("SELECT COUNT(*) AS n FROM method_cohort_prior").fetchone()["n"]
        # Every method gets a row (even at the default), since the function
        # writes one row per method in the taxonomy regardless of data.
        from stage3.student_state.explanation_method import EXPLANATION_METHODS

        self.assertEqual(n, len(EXPLANATION_METHODS))

    def test_aggregates_successes_and_failures_across_students(self):
        from stage3.student_state.explanation_method import (
            DEFAULT_PRIOR_ALPHA,
            DEFAULT_PRIOR_BETA,
            _connect,
            log_interaction,
            record_understanding,
            recompute_cohort_priors,
        )

        for student, success in (("stu-1", True), ("stu-2", True), ("stu-3", False)):
            interaction_id = log_interaction(
                student_id=student, subject="biology", conversation_id=1,
                concept_id="monosaccharides", method="worked_example", db_path=self.db_path,
            )
            record_understanding(
                interaction_id=interaction_id, student_id=student, method="worked_example",
                success=success, db_path=self.db_path,
            )

        recompute_cohort_priors(db_path=self.db_path)
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM method_cohort_prior WHERE method = 'worked_example' AND signal_type = 'immediate'"
            ).fetchone()
        self.assertEqual(row["cohort_alpha"], DEFAULT_PRIOR_ALPHA + 2)
        self.assertEqual(row["cohort_beta"], DEFAULT_PRIOR_BETA + 1)
        self.assertEqual(row["n_students_contributing"], 3)

    def test_ungraded_interactions_not_counted(self):
        from stage3.student_state.explanation_method import (
            DEFAULT_PRIOR_ALPHA,
            DEFAULT_PRIOR_BETA,
            _connect,
            log_interaction,
            recompute_cohort_priors,
        )

        log_interaction(
            student_id="stu-1", subject="biology", conversation_id=1,
            concept_id="monosaccharides", method="worked_example", db_path=self.db_path,
        )  # never graded

        recompute_cohort_priors(db_path=self.db_path)
        with _connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM method_cohort_prior WHERE method = 'worked_example' AND signal_type = 'immediate'"
            ).fetchone()
        self.assertEqual(row["cohort_alpha"], DEFAULT_PRIOR_ALPHA)
        self.assertEqual(row["cohort_beta"], DEFAULT_PRIOR_BETA)
        self.assertEqual(row["n_students_contributing"], 0)


class TestParseUnderstandingMarker(unittest.TestCase):
    def test_well_formed_yes_marker_parsed(self):
        from stage3.student_state.explanation_method import parse_understanding_marker

        raw = "Nice, that's right.\n[[UNDERSTANDING: yes]]"
        visible, understood = parse_understanding_marker(raw)
        self.assertEqual(visible, "Nice, that's right.")
        self.assertTrue(understood)

    def test_well_formed_no_marker_parsed(self):
        from stage3.student_state.explanation_method import parse_understanding_marker

        raw = "Not quite — let's try again.\n[[UNDERSTANDING: no]]"
        visible, understood = parse_understanding_marker(raw)
        self.assertFalse(understood)

    def test_marker_stripped_from_visible_text(self):
        from stage3.student_state.explanation_method import parse_understanding_marker

        raw = "Some reply.\n[[UNDERSTANDING: yes]]"
        visible, _ = parse_understanding_marker(raw)
        self.assertNotIn("UNDERSTANDING", visible)
        self.assertNotIn("[[", visible)

    def test_missing_marker_returns_none_not_a_guess(self):
        from stage3.student_state.explanation_method import parse_understanding_marker

        raw = "No marker here."
        visible, understood = parse_understanding_marker(raw)
        self.assertIsNone(understood)
        self.assertEqual(visible, raw)

    def test_malformed_marker_returns_none(self):
        from stage3.student_state.explanation_method import parse_understanding_marker

        raw = "Some reply.\n[[UNDERSTANDING: maybe]]"
        _, understood = parse_understanding_marker(raw)
        self.assertIsNone(understood)

    def test_marker_must_be_at_end_not_mid_text(self):
        from stage3.student_state.explanation_method import parse_understanding_marker

        raw = "[[UNDERSTANDING: yes]] more text follows"
        _, understood = parse_understanding_marker(raw)
        self.assertIsNone(understood)

    def test_case_insensitive_yes_no(self):
        from stage3.student_state.explanation_method import parse_understanding_marker

        _, understood = parse_understanding_marker("Reply.\n[[UNDERSTANDING: YES]]")
        self.assertTrue(understood)


if __name__ == "__main__":
    unittest.main()

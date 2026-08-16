"""Unit tests for the pure reranking/filter helpers in retriever/search.py.

Deliberately scoped to the pure, module-level functions only —
``build_metadata_filter``, ``_decay_multiplier``, ``_feedback_bonus``, and
``_adjusted_rank_score`` need no Chroma store and no network access.
``Retriever.search`` itself (which does need a live store) is exercised by
live/manual verification instead, matching this project's existing pattern
of unit-testing pure logic and leaving DB-backed paths to real runs — see
the 2026-08-16 cleanup-pass weight sanity-check recorded in this module's
docstring for that live evidence.

Run:  python -m pytest tests/test_retriever_search.py
  or: python -m unittest tests.test_retriever_search
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from stage3.retriever.search import (
    _adjusted_rank_score,
    _decay_multiplier,
    _feedback_bonus,
    build_metadata_filter,
)


class TestBuildMetadataFilter(unittest.TestCase):
    def test_no_args_returns_none(self):
        self.assertIsNone(build_metadata_filter())

    def test_single_subject_returns_plain_dict(self):
        self.assertEqual(build_metadata_filter(subject="biology"), {"subject": "biology"})

    def test_single_topic_returns_plain_dict(self):
        self.assertEqual(build_metadata_filter(topic="genetics"), {"topic": "genetics"})

    def test_single_difficulty_tier_returns_plain_dict(self):
        self.assertEqual(
            build_metadata_filter(difficulty_tier="foundation"),
            {"difficulty_tier": "foundation"},
        )

    def test_subject_and_topic_combine_with_and(self):
        result = build_metadata_filter(subject="biology", topic="genetics")
        self.assertEqual(
            result,
            {"$and": [{"subject": "biology"}, {"topic": "genetics"}]},
        )

    def test_subject_and_difficulty_tier_combine_with_and(self):
        result = build_metadata_filter(subject="computer_science", difficulty_tier="core")
        self.assertEqual(
            result,
            {"$and": [{"subject": "computer_science"}, {"difficulty_tier": "core"}]},
        )

    def test_all_three_combine_with_and_in_order(self):
        result = build_metadata_filter(
            subject="chemistry", topic="organic", difficulty_tier="foundation"
        )
        self.assertEqual(
            result,
            {
                "$and": [
                    {"subject": "chemistry"},
                    {"topic": "organic"},
                    {"difficulty_tier": "foundation"},
                ]
            },
        )


class TestDecayMultiplier(unittest.TestCase):
    def test_no_last_feedback_at_is_full_strength(self):
        self.assertEqual(_decay_multiplier({}), 1.0)

    def test_recent_feedback_is_close_to_full_strength(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        result = _decay_multiplier({"last_feedback_at": recent})
        self.assertAlmostEqual(result, 0.99, places=2)

    def test_old_feedback_hits_the_floor(self):
        old = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
        self.assertEqual(_decay_multiplier({"last_feedback_at": old}), 0.70)

    def test_malformed_timestamp_fails_closed_to_no_penalty(self):
        self.assertEqual(_decay_multiplier({"last_feedback_at": "not-a-date"}), 1.0)


class TestFeedbackBonus(unittest.TestCase):
    def test_zero_counts_is_zero(self):
        self.assertEqual(_feedback_bonus({}), 0.0)

    def test_positive_only(self):
        self.assertAlmostEqual(_feedback_bonus({"fb_pos": 3}), 0.24)

    def test_negative_only(self):
        self.assertAlmostEqual(_feedback_bonus({"fb_neg": 2}), -0.24)

    def test_negatives_weigh_more_than_positives(self):
        # Equal counts of each: positives contribute 0.08/each, negatives
        # 0.12/each — net should be negative, per the module's "conservative
        # by design" comment.
        result = _feedback_bonus({"fb_pos": 2, "fb_neg": 2})
        self.assertLess(result, 0.0)
        self.assertAlmostEqual(result, (2 * 0.08) - (2 * 0.12))


class TestAdjustedRankScore(unittest.TestCase):
    def test_known_inputs_match_hand_computed_blend(self):
        # distance 0.5 -> sim = 1 / 1.5 = 0.6667 (repeating)
        # kb_score 2.0, fb_pos=1 fb_neg=0 -> feedback bonus 0.08
        # no last_feedback_at -> decay 1.0
        meta = {"kb_score": 2.0, "fb_pos": 1, "fb_neg": 0}
        expected = ((1.0 / 1.5) * 0.70 + 2.0 * 0.25 + 0.08 * 0.05) * 1.0
        self.assertAlmostEqual(_adjusted_rank_score(0.5, meta), expected)

    def test_missing_kb_score_defaults_to_zero_not_a_crash(self):
        result = _adjusted_rank_score(1.0, {})
        self.assertAlmostEqual(result, (1.0 / 2.0) * 0.70)

    def test_non_numeric_score_falls_back_to_large_distance(self):
        # _safe_float's default (9999.0) makes an unparseable raw score
        # rank near the bottom rather than crashing or ranking first.
        result = _adjusted_rank_score("not-a-number", {})
        self.assertAlmostEqual(result, (1.0 / 10000.0) * 0.70, places=6)


if __name__ == "__main__":
    unittest.main()

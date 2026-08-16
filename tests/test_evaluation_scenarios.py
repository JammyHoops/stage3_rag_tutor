"""Offline tests for evaluation/scenarios.py — the fixed scenario set.
No LLM/network/vectordb calls."""

from __future__ import annotations

import unittest

from evaluation.scenarios import load_scenarios
from stage3.taxonomy.topics import get_topic


class TestScenarioSet(unittest.TestCase):
    def setUp(self):
        self.scenarios = load_scenarios()

    def test_at_least_one_scenario_loads(self):
        self.assertGreater(len(self.scenarios), 0)

    def test_ids_are_unique(self):
        ids = [s.id for s in self.scenarios]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_scenario_has_required_text_fields(self):
        for s in self.scenarios:
            self.assertTrue(s.id)
            self.assertTrue(s.subject)
            self.assertTrue(s.topic)
            self.assertTrue(s.student_message)

    def test_every_subject_topic_pair_is_real(self):
        # Catches drift if data/topics/<subject>.json ever changes ids.
        for s in self.scenarios:
            topic = get_topic(s.subject, s.topic)
            self.assertIsNotNone(
                topic, f"{s.id}: {s.subject}/{s.topic} is not a real topic"
            )

    def test_mastery_rows_shape_matches_summarise_state_expectations(self):
        from stage3.tutor.context_builder import summarise_state

        for s in self.scenarios:
            # Should not raise — same call run_scenarios.py makes for real.
            summarise_state(s.mastery_rows)

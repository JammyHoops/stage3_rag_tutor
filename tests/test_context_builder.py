"""Offline tests for context_builder.summarise_state — no retriever/LLM imports."""

from __future__ import annotations

import unittest

from stage3.tutor.context_builder import summarise_state


class TestSummariseState(unittest.TestCase):
    def test_empty_rows_returns_empty_string(self):
        self.assertEqual(summarise_state([]), "")

    def test_high_estimate_bucketed_secure(self):
        rows = [{"topic": "biochemistry", "estimate": 0.9, "n_obs": 3}]
        summary = summarise_state(rows)
        self.assertIn("secure on biochemistry", summary)

    def test_mid_estimate_bucketed_developing(self):
        rows = [{"topic": "biochemistry", "estimate": 0.5, "n_obs": 2}]
        summary = summarise_state(rows)
        self.assertIn("developing understanding of biochemistry", summary)

    def test_low_estimate_bucketed_still_building(self):
        rows = [{"topic": "biochemistry", "estimate": 0.1, "n_obs": 1}]
        summary = summarise_state(rows)
        self.assertIn("still building the basics of biochemistry", summary)

    def test_bucket_boundaries_are_inclusive_of_lower_bound(self):
        self.assertIn("secure on", summarise_state([{"topic": "x", "estimate": 0.75, "n_obs": 1}]))
        self.assertIn(
            "developing understanding of",
            summarise_state([{"topic": "x", "estimate": 0.4, "n_obs": 1}]),
        )

    def test_multiple_topics_joined(self):
        rows = [
            {"topic": "biochemistry", "estimate": 0.9, "n_obs": 3},
            {"topic": "genetics", "estimate": 0.1, "n_obs": 1},
        ]
        summary = summarise_state(rows)
        self.assertIn("biochemistry", summary)
        self.assertIn("genetics", summary)
        self.assertIn(";", summary)

    def test_n_obs_included_in_output(self):
        rows = [{"topic": "biochemistry", "estimate": 0.9, "n_obs": 3}]
        self.assertIn("3 observation", summarise_state(rows))


if __name__ == "__main__":
    unittest.main()

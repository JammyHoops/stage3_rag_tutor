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


class TestProfileToNote(unittest.TestCase):
    def test_none_profile_returns_empty(self):
        from stage3.tutor.context_builder import profile_to_note

        self.assertEqual(profile_to_note(None), {})

    def test_flag_status_none_returns_empty(self):
        from stage3.tutor.context_builder import profile_to_note

        self.assertEqual(profile_to_note({"flag_status": "none"}), {})

    def test_unrecognised_flag_status_fails_closed_to_empty(self):
        from stage3.tutor.context_builder import profile_to_note

        self.assertEqual(profile_to_note({"flag_status": "made_up"}), {})

    def test_provisional_and_confirmed_produce_distinct_notes(self):
        from stage3.tutor.context_builder import profile_to_note

        provisional = profile_to_note({"flag_status": "provisional"})
        confirmed = profile_to_note({"flag_status": "confirmed"})
        self.assertIn("scaffolding_note", provisional)
        self.assertIn("scaffolding_note", confirmed)
        self.assertNotEqual(provisional["scaffolding_note"], confirmed["scaffolding_note"])


class TestAttainmentBandToPrior(unittest.TestCase):
    def test_none_profile_returns_none(self):
        from stage3.tutor.context_builder import attainment_band_to_prior

        self.assertIsNone(attainment_band_to_prior(None))

    def test_unrecognised_band_returns_none(self):
        from stage3.tutor.context_builder import attainment_band_to_prior

        self.assertIsNone(attainment_band_to_prior({"attainment_band": "made_up"}))

    def test_all_four_bands_map_to_expected_priors(self):
        from stage3.tutor.context_builder import attainment_band_to_prior

        expected = {
            "well_below": 0.15,
            "below": 0.3,
            "in_line": 0.55,
            "above": 0.8,
        }
        for band, value in expected.items():
            with self.subTest(band=band):
                self.assertEqual(
                    attainment_band_to_prior({"attainment_band": band}), value
                )

    def test_independent_of_flag_status(self):
        from stage3.tutor.context_builder import attainment_band_to_prior

        # A "none" flag still has a usable attainment_band — the two
        # fields are deliberately independent (see module docstring).
        profile = {"flag_status": "none", "attainment_band": "above"}
        self.assertEqual(attainment_band_to_prior(profile), 0.8)


if __name__ == "__main__":
    unittest.main()

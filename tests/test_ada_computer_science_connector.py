"""Offline tests for the Ada Computer Science connector's parsing logic.

No network calls — feeds a trimmed-down fixture shaped like the real
"Binary arithmetic" (`number_arithmetic`) concept captured during
connector development (see connectors/ada_computer_science.py's module
docstring). Live behavior (the actual HTTP calls) is verified manually,
not here — same policy as tests/test_isaac_science_connector.py.
"""

from __future__ import annotations

import unittest

# Trimmed but structurally real: a top-level intro (a_level+gcse audience,
# same as the real concept), one accordion with an a_level-only section, a
# gcse-only section, a dual-tagged section, and a Scotland-only section
# (must be dropped, not guessed at).
FIXTURE_CONCEPT = {
    "id": "number_arithmetic",
    "type": "isaacConceptPage",
    "tags": ["computer_science", "computer_systems", "number_representation"],
    "title": "Binary arithmetic (whole numbers)",
    "audience": [
        {"stage": ["a_level"], "examBoard": ["aqa", "ocr"]},
        {"stage": ["gcse"], "examBoard": ["aqa", "edexcel"]},
        {"stage": ["core"], "examBoard": ["ada"]},
    ],
    "children": [
        {
            "type": "content",
            "children": [],
            "value": "Binary arithmetic follows rules similar to decimal arithmetic.",
        },
        {
            "type": "content",
            "layout": "accordion",
            "children": [
                {
                    "title": "Binary subtraction (whole numbers)",
                    "type": "content",
                    "audience": [
                        {"stage": ["a_level"], "examBoard": ["aqa"]},
                        {"stage": ["advanced"], "examBoard": ["ada"]},
                    ],
                    "children": [
                        {
                            "type": "content",
                            "children": [],
                            "value": "Subtraction uses two's complement addition.",
                        }
                    ],
                },
                {
                    "title": "Binary multiplication (left shift)",
                    "type": "content",
                    "audience": [
                        {"stage": ["gcse"], "examBoard": ["aqa", "edexcel"]},
                        {"stage": ["core"], "examBoard": ["ada"]},
                    ],
                    "children": [
                        {
                            "type": "content",
                            "children": [],
                            "value": "Multiplying by two is a left shift.",
                        }
                    ],
                },
                {
                    "title": "Binary addition (whole numbers)",
                    "type": "content",
                    "audience": [
                        {"stage": ["a_level"], "examBoard": ["aqa"]},
                        {"stage": ["gcse"], "examBoard": ["aqa"]},
                    ],
                    "children": [
                        {
                            "type": "content",
                            "children": [],
                            "value": "Addition works column by column, carrying overflow.",
                        }
                    ],
                },
                {
                    "title": "Scotland-only section",
                    "type": "content",
                    "audience": [
                        {"stage": ["scotland_national_5"], "examBoard": ["sqa"]},
                    ],
                    "children": [
                        {
                            "type": "content",
                            "children": [],
                            "value": "This should never surface — no a_level/gcse tag.",
                        }
                    ],
                },
            ],
        },
    ],
}


class TestSectionDifficultyTier(unittest.TestCase):
    def test_a_level_maps_to_core(self):
        from stage3.connectors.ada_computer_science import _section_difficulty_tier

        self.assertEqual(_section_difficulty_tier({"a_level"}), "core")

    def test_gcse_only_maps_to_foundation(self):
        from stage3.connectors.ada_computer_science import _section_difficulty_tier

        self.assertEqual(_section_difficulty_tier({"gcse"}), "foundation")

    def test_a_level_takes_priority_over_gcse(self):
        from stage3.connectors.ada_computer_science import _section_difficulty_tier

        self.assertEqual(_section_difficulty_tier({"a_level", "gcse"}), "core")

    def test_neither_stage_returns_none(self):
        from stage3.connectors.ada_computer_science import _section_difficulty_tier

        self.assertIsNone(_section_difficulty_tier({"scotland_national_5"}))
        self.assertIsNone(_section_difficulty_tier({"advanced"}))


class TestExtractTieredSections(unittest.TestCase):
    def test_yields_both_core_and_foundation_sections(self):
        from stage3.connectors.ada_computer_science import _extract_tiered_sections

        sections = _extract_tiered_sections(FIXTURE_CONCEPT)
        tiers = {s["difficulty_tier"] for s in sections}
        self.assertEqual(tiers, {"core", "foundation"})

    def test_scotland_only_section_dropped(self):
        from stage3.connectors.ada_computer_science import _extract_tiered_sections

        sections = _extract_tiered_sections(FIXTURE_CONCEPT)
        titles = [s["title"] for s in sections]
        self.assertFalse(any("Scotland-only" in t for t in titles))

    def test_dual_tagged_section_resolves_to_core(self):
        from stage3.connectors.ada_computer_science import _extract_tiered_sections

        sections = _extract_tiered_sections(FIXTURE_CONCEPT)
        addition = next(s for s in sections if "Binary addition" in s["title"])
        self.assertEqual(addition["difficulty_tier"], "core")

    def test_intro_included_with_concept_level_tier(self):
        from stage3.connectors.ada_computer_science import _extract_tiered_sections

        sections = _extract_tiered_sections(FIXTURE_CONCEPT)
        intro = next(s for s in sections if s["title"] == "Binary arithmetic (whole numbers)")
        self.assertEqual(intro["difficulty_tier"], "core")  # concept audience includes a_level


class TestTopicMapping(unittest.TestCase):
    def test_maps_known_tag(self):
        from stage3.connectors.ada_computer_science import AdaComputerScienceConnector

        connector = AdaComputerScienceConnector()
        self.assertEqual(
            connector._map_topic(["computer_science", "number_representation"]),
            "computer_systems",
        )

    def test_unmapped_tag_returns_none(self):
        from stage3.connectors.ada_computer_science import AdaComputerScienceConnector

        connector = AdaComputerScienceConnector()
        self.assertIsNone(connector._map_topic(["projects", "web_project"]))


class TestConceptToDocuments(unittest.TestCase):
    def test_concept_id_consistent_across_tiers(self):
        from stage3.connectors.ada_computer_science import AdaComputerScienceConnector

        connector = AdaComputerScienceConnector()
        docs = connector._concept_to_documents(FIXTURE_CONCEPT)

        concept_ids = {d["metadata"]["concept_id"] for d in docs}
        self.assertEqual(concept_ids, {"number_arithmetic"})

    def test_both_tiers_present_with_expected_level(self):
        from stage3.connectors.ada_computer_science import AdaComputerScienceConnector

        connector = AdaComputerScienceConnector()
        docs = connector._concept_to_documents(FIXTURE_CONCEPT)

        by_tier = {d["metadata"]["difficulty_tier"] for d in docs}
        self.assertEqual(by_tier, {"core", "foundation"})

        for d in docs:
            if d["metadata"]["difficulty_tier"] == "core":
                self.assertEqual(d["metadata"]["level"], "a_level")
            else:
                self.assertEqual(d["metadata"]["level"], "gcse")

    def test_prerequisites_is_none(self):
        from stage3.connectors.ada_computer_science import AdaComputerScienceConnector

        connector = AdaComputerScienceConnector()
        docs = connector._concept_to_documents(FIXTURE_CONCEPT)

        for d in docs:
            self.assertIsNone(d["metadata"]["prerequisites"])

    def test_common_metadata_fields(self):
        from stage3.connectors.ada_computer_science import AdaComputerScienceConnector

        connector = AdaComputerScienceConnector()
        docs = connector._concept_to_documents(FIXTURE_CONCEPT)

        for d in docs:
            self.assertEqual(d["metadata"]["subject"], "computer_science")
            self.assertEqual(d["metadata"]["source"], "ada_computer_science")
            self.assertEqual(d["metadata"]["provenance_tier"], "third_party_education_platform")
            # CC BY-NC-SA 4.0 confirmed directly via headless-browser
            # render 2026-08-16 — see connector docstring "CORRECTED" note.
            self.assertEqual(d["metadata"]["licence"], "CC-BY-NC-SA-4.0")
            self.assertEqual(d["metadata"]["topic"], "computer_systems")


if __name__ == "__main__":
    unittest.main()

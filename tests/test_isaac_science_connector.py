"""Offline tests for the Isaac Science connector's parsing logic.

No network calls — feeds a trimmed-down fixture shaped like a real
response captured during development (see connectors/isaac_science.py's
module docstring for how that shape was confirmed). Live behavior (the
actual HTTP calls) is verified manually, not here — consistent with
tests/test_smoke.py's own "avoid heavy/networked deps" policy.
"""

from __future__ import annotations

import unittest

# A trimmed-down but structurally real fixture — mirrors the shape of the
# actual "Carbohydrates" A-level Biology concept captured during connector
# development (intro content block + one accordion sub-section + a figure).
FIXTURE_CONCEPT = {
    "id": "cb_carbohydrates",
    "type": "isaacConceptPage",
    "tags": ["carbohydrates", "biology", "biochemistry"],
    "audience": [{"stage": ["a_level"]}],
    "title": "Carbohydrates",
    "subtitle": "The structures and functions of carbohydrates",
    "children": [
        {
            "type": "content",
            "children": [],
            "value": "**Carbohydrates** are an important energy source, made up of "
            "[glossary-inline:glossarybio|monomer \"monomer\"]s.",
        },
        {
            "type": "content",
            "layout": "accordion",
            "children": [
                {
                    "id": "cb_carbohydrates|cb_carbohydrates_monosaccharides",
                    "title": "Monosaccharides",
                    "type": "content",
                    "children": [
                        {
                            "type": "content",
                            "children": [],
                            "value": "Monosaccharides are classified by carbon count.",
                        },
                        {
                            "id": "...|alpha_glucose_fig1",
                            "type": "figure",
                            "value": "The molecular structure of an alpha-glucose molecule",
                        },
                    ],
                }
            ],
        },
    ],
}

GCSE_ONLY_FIXTURE = {
    "id": "cb_gcse_only",
    "tags": ["biology"],
    "audience": [{"stage": ["gcse"]}],
    "title": "GCSE-only concept",
    "children": [],
}


class TestGlossaryStripping(unittest.TestCase):
    def test_strips_glossary_inline_markup(self):
        from stage3.connectors.isaac_science import _clean_markdown

        text = 'made up of [glossary-inline:glossarybio|monomer "monomer"]s'
        self.assertEqual(_clean_markdown(text), "made up of monomers")

    def test_leaves_plain_text_unchanged(self):
        from stage3.connectors.isaac_science import _clean_markdown

        text = "no glossary markup here"
        self.assertEqual(_clean_markdown(text), text)


class TestCollectTextFragments(unittest.TestCase):
    def test_figure_becomes_bracketed_caption(self):
        from stage3.connectors.isaac_science import _collect_text_fragments

        node = {"type": "figure", "value": "A caption"}
        self.assertEqual(_collect_text_fragments(node), ["[Figure: A caption]"])

    def test_recurses_into_children(self):
        from stage3.connectors.isaac_science import _collect_text_fragments

        node = {
            "type": "content",
            "value": "top",
            "children": [{"type": "content", "value": "nested", "children": []}],
        }
        self.assertEqual(_collect_text_fragments(node), ["top", "nested"])


class TestExtractSections(unittest.TestCase):
    def test_intro_and_accordion_sections_both_present(self):
        from stage3.connectors.isaac_science import _extract_sections

        sections = _extract_sections(FIXTURE_CONCEPT)
        titles = [s["title"] for s in sections]

        self.assertIn("Carbohydrates", titles)
        self.assertIn("Carbohydrates — Monosaccharides", titles)

    def test_glossary_markup_stripped_in_intro(self):
        from stage3.connectors.isaac_science import _extract_sections

        sections = _extract_sections(FIXTURE_CONCEPT)
        intro = next(s for s in sections if s["title"] == "Carbohydrates")
        self.assertIn("monomers", intro["text"])
        self.assertNotIn("glossary-inline", intro["text"])

    def test_figure_caption_present_in_accordion_section(self):
        from stage3.connectors.isaac_science import _extract_sections

        sections = _extract_sections(FIXTURE_CONCEPT)
        mono = next(s for s in sections if "Monosaccharides" in s["title"])
        self.assertIn("[Figure: The molecular structure", mono["text"])


class TestTopicMapping(unittest.TestCase):
    def test_maps_known_tag_to_topic(self):
        from stage3.connectors.isaac_science import IsaacScienceConnector

        connector = IsaacScienceConnector()
        self.assertEqual(
            connector._map_topic(["carbohydrates", "biology", "biochemistry"]),
            "biochemistry",
        )

    def test_unmapped_tags_return_none(self):
        from stage3.connectors.isaac_science import IsaacScienceConnector

        connector = IsaacScienceConnector()
        self.assertIsNone(connector._map_topic(["some_totally_unmapped_tag"]))


class TestConceptToDocuments(unittest.TestCase):
    def test_a_level_concept_produces_documents_with_expected_metadata(self):
        from stage3.connectors.isaac_science import IsaacScienceConnector

        connector = IsaacScienceConnector()
        docs = connector._concept_to_documents(FIXTURE_CONCEPT)

        self.assertEqual(len(docs), 2)  # intro + one accordion section
        for doc in docs:
            self.assertEqual(doc["metadata"]["subject"], "biology")
            self.assertEqual(doc["metadata"]["difficulty_tier"], "core")
            self.assertEqual(doc["metadata"]["level"], "a_level")
            self.assertEqual(doc["metadata"]["topic"], "biochemistry")
            self.assertEqual(doc["metadata"]["concept_id"], "cb_carbohydrates")
            self.assertIsNone(doc["metadata"]["prerequisites"])
            # CC BY 4.0 confirmed directly via headless-browser render
            # 2026-08-16 — see connector docstring "CORRECTED" note.
            self.assertEqual(doc["metadata"]["licence"], "CC-BY-4.0")
            self.assertEqual(
                doc["metadata"]["provenance_tier"], "third_party_education_platform"
            )
            self.assertTrue(doc["id"].startswith("cb_carbohydrates__"))

    def test_gcse_only_concept_skipped_this_pass(self):
        from stage3.connectors.isaac_science import IsaacScienceConnector

        connector = IsaacScienceConnector()
        docs = connector._concept_to_documents(GCSE_ONLY_FIXTURE)
        self.assertEqual(docs, [])


# A trimmed-down but structurally real fixture — mirrors the shape of the
# actual "Acids and Bases" A-level Chemistry concept confirmed live against
# the API during connector development.
CHEMISTRY_FIXTURE_CONCEPT = {
    "id": "cc_acids_bases",
    "type": "isaacConceptPage",
    "tags": ["chemistry", "acids_and_bases", "physical"],
    "audience": [{"stage": ["a_level"]}, {"stage": ["university"]}],
    "title": "Acids and Bases",
    "children": [
        {
            "type": "content",
            "children": [],
            "value": "An acid is a proton donor.",
        }
    ],
}


class TestChemistryConnector(unittest.TestCase):
    def test_defaults_to_chemistry_subject(self):
        from stage3.connectors.isaac_science import IsaacChemistryConnector

        connector = IsaacChemistryConnector()
        self.assertEqual(connector.subject, "chemistry")

    def test_maps_broad_and_specific_chemistry_tags(self):
        from stage3.connectors.isaac_science import IsaacChemistryConnector

        connector = IsaacChemistryConnector()
        self.assertEqual(
            connector._map_topic(["chemistry", "acids_and_bases", "physical"]),
            "physical_chemistry",
        )
        self.assertEqual(
            connector._map_topic(["chemistry", "organic", "isomerism"]),
            "organic_chemistry",
        )
        self.assertEqual(
            connector._map_topic(["chemistry", "bonding", "inorganic"]),
            "inorganic_chemistry",
        )
        self.assertEqual(
            connector._map_topic(["chemistry", "foundations", "atomic_structure"]),
            "foundations",
        )

    def test_biology_connector_unaffected_by_chemistry_tag_map(self):
        # Guards against the two subjects' tag maps bleeding into each
        # other after the refactor to a subject-keyed dict.
        from stage3.connectors.isaac_science import IsaacScienceConnector

        connector = IsaacScienceConnector()  # defaults to biology
        self.assertIsNone(connector._map_topic(["chemistry", "physical"]))

    def test_chemistry_concept_produces_documents_with_expected_metadata(self):
        from stage3.connectors.isaac_science import IsaacChemistryConnector

        connector = IsaacChemistryConnector()
        docs = connector._concept_to_documents(CHEMISTRY_FIXTURE_CONCEPT)

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["metadata"]["subject"], "chemistry")
        self.assertEqual(docs[0]["metadata"]["topic"], "physical_chemistry")
        self.assertEqual(docs[0]["metadata"]["difficulty_tier"], "core")
        self.assertEqual(docs[0]["metadata"]["source"], "isaac_science")


if __name__ == "__main__":
    unittest.main()

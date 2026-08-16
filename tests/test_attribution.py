"""Offline tests for tutor/attribution.py — human-readable CC citations.
No LLM/network calls; pure function over chunk dicts."""

from __future__ import annotations

import unittest

from stage3.tutor.attribution import SOURCE_ATTRIBUTION, build_attributions


def _chunk(source, source_url, section_title, concept_id="x"):
    return {
        "source": source,
        "source_url": source_url,
        "section_title": section_title,
        "concept_id": concept_id,
    }


class TestBuildAttributions(unittest.TestCase):
    def test_empty_input_yields_empty_output(self):
        self.assertEqual(build_attributions([]), [])

    def test_plain_concept_title_recovered(self):
        chunks = [_chunk("isaac_science", "https://isaacscience.org/concepts/cb_carbohydrates", "Carbohydrates")]
        result = build_attributions(chunks)
        self.assertEqual(result[0]["title"], "Carbohydrates")

    def test_subsection_title_split_to_plain_concept_title(self):
        chunks = [
            _chunk(
                "isaac_science",
                "https://isaacscience.org/concepts/cb_carbohydrates",
                "Carbohydrates — Monosaccharides",
            )
        ]
        result = build_attributions(chunks)
        self.assertEqual(result[0]["title"], "Carbohydrates")

    def test_isaac_science_licence_is_cc_by(self):
        chunks = [_chunk("isaac_science", "https://isaacscience.org/concepts/x", "X")]
        result = build_attributions(chunks)
        self.assertEqual(result[0]["source_name"], "Isaac Science")
        self.assertEqual(result[0]["licence"], "CC BY 4.0")
        self.assertEqual(
            result[0]["licence_url"], "https://creativecommons.org/licenses/by/4.0/"
        )

    def test_ada_computer_science_licence_is_cc_by_nc_sa(self):
        chunks = [_chunk("ada_computer_science", "https://adacomputerscience.org/concepts/x", "X")]
        result = build_attributions(chunks)
        self.assertEqual(result[0]["source_name"], "Ada Computer Science")
        self.assertEqual(result[0]["licence"], "CC BY-NC-SA 4.0")
        self.assertEqual(
            result[0]["licence_url"],
            "https://creativecommons.org/licenses/by-nc-sa/4.0",
        )

    def test_multiple_chunks_same_concept_deduped_to_one_citation(self):
        url = "https://isaacscience.org/concepts/cb_carbohydrates"
        chunks = [
            _chunk("isaac_science", url, "Carbohydrates"),
            _chunk("isaac_science", url, "Carbohydrates — Monosaccharides"),
            _chunk("isaac_science", url, "Carbohydrates — Disaccharides"),
        ]
        result = build_attributions(chunks)
        self.assertEqual(len(result), 1)

    def test_different_concepts_produce_separate_citations(self):
        chunks = [
            _chunk("isaac_science", "https://isaacscience.org/concepts/a", "A"),
            _chunk("isaac_science", "https://isaacscience.org/concepts/b", "B"),
        ]
        result = build_attributions(chunks)
        self.assertEqual(len(result), 2)

    def test_unknown_source_silently_skipped(self):
        chunks = [_chunk("some_future_source", "https://example.com/x", "X")]
        self.assertEqual(build_attributions(chunks), [])

    def test_missing_source_silently_skipped(self):
        chunks = [{"source_url": "https://example.com/x", "section_title": "X"}]
        self.assertEqual(build_attributions(chunks), [])

    def test_missing_source_url_skipped(self):
        chunks = [{"source": "isaac_science", "section_title": "X"}]
        self.assertEqual(build_attributions(chunks), [])

    def test_result_sorted_by_title(self):
        chunks = [
            _chunk("isaac_science", "https://isaacscience.org/concepts/z", "Zebra topic"),
            _chunk("isaac_science", "https://isaacscience.org/concepts/a", "Apple topic"),
        ]
        result = build_attributions(chunks)
        self.assertEqual([r["title"] for r in result], ["Apple topic", "Zebra topic"])

    def test_source_attribution_covers_both_real_connectors(self):
        # Guards against a future connector name change silently breaking
        # attribution instead of failing loudly somewhere obvious.
        self.assertIn("isaac_science", SOURCE_ATTRIBUTION)
        self.assertIn("ada_computer_science", SOURCE_ATTRIBUTION)


if __name__ == "__main__":
    unittest.main()

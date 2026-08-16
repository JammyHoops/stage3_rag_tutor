"""Offline tests for the subject/topic taxonomy — no vectordb/retriever imports."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class TestTaxonomy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.topics_dir = Path(self._tmp.name)
        (self.topics_dir / "mathematics.json").write_text(
            json.dumps(
                {
                    "subject": "mathematics",
                    "topics": [
                        {"id": "algebra", "label": "Algebra"},
                        {"id": "calculus", "label": "Calculus"},
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_list_subjects(self):
        from stage3.taxonomy.topics import list_subjects

        self.assertEqual(list_subjects(self.topics_dir), ["mathematics"])

    def test_list_topics(self):
        from stage3.taxonomy.topics import list_topics

        topics = list_topics("mathematics", self.topics_dir)
        self.assertEqual([t.id for t in topics], ["algebra", "calculus"])
        self.assertEqual(topics[0].label, "Algebra")

    def test_unknown_subject_returns_empty(self):
        from stage3.taxonomy.topics import list_topics

        self.assertEqual(list_topics("physics", self.topics_dir), [])

    def test_get_topic_found_and_not_found(self):
        from stage3.taxonomy.topics import get_topic

        self.assertEqual(get_topic("mathematics", "algebra", self.topics_dir).label, "Algebra")
        self.assertIsNone(get_topic("mathematics", "geometry", self.topics_dir))
        self.assertIsNone(get_topic("physics", "algebra", self.topics_dir))


if __name__ == "__main__":
    unittest.main()

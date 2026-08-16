"""Offline tests for evaluation/expert_review.py — rubric validation,
CSV export/import round-trip, descriptive report generation. No LLM/
network/vectordb calls; uses fake transcript fixtures in a temp dir."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.expert_review import (
    CRITERIA,
    ReviewRecord,
    export_review_csv,
    generate_report,
    import_review_csv,
    record_rating,
)

FAKE_TRANSCRIPTS = [
    {
        "scenario_id": "fake_scenario_1",
        "subject": "biology",
        "topic": "biochemistry",
        "notes": "cold start",
        "student_message": "What is a monosaccharide?",
        "knowledge_state_summary": "",
        "scaffolding_note": None,
        "answer": "A monosaccharide is a single sugar unit.",
        "grounding_chunks": ["Monosaccharides are simple sugars.", "Glucose is a hexose."],
        "tiers_used": ["core"],
    },
    {
        "scenario_id": "fake_scenario_2",
        "subject": "chemistry",
        "topic": "organic_chemistry",
        "notes": "established mastery",
        "student_message": "What is a skeletal structure?",
        "knowledge_state_summary": "secure on organic_chemistry (5 observation(s))",
        "scaffolding_note": "Use short sentences.",
        "answer": "A skeletal structure omits explicit C and H atoms.",
        "grounding_chunks": ["Skeletal structures simplify organic molecule drawings."],
        "tiers_used": ["core"],
    },
]


class _TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.transcripts_path = self.tmp_path / "transcripts.jsonl"
        with open(self.transcripts_path, "w", encoding="utf-8") as f:
            for t in FAKE_TRANSCRIPTS:
                f.write(json.dumps(t) + "\n")
        self.csv_path = self.tmp_path / "review_sheet.csv"
        self.results_path = self.tmp_path / "review_records.jsonl"

    def tearDown(self):
        self._tmp.cleanup()


class TestRecordRating(_TempDirTestCase):
    def test_rejects_unknown_criterion(self):
        with self.assertRaises(ValueError):
            record_rating(
                ReviewRecord("s1", "not_a_real_criterion", 3, "", "SENCO"),
                path=self.results_path,
            )

    def test_rejects_out_of_range_rating(self):
        with self.assertRaises(ValueError):
            record_rating(
                ReviewRecord("s1", CRITERIA[0], 6, "", "SENCO"), path=self.results_path
            )

    def test_valid_rating_appends_a_line(self):
        record_rating(
            ReviewRecord("s1", CRITERIA[0], 4, "good", "SENCO"), path=self.results_path
        )
        lines = self.results_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertEqual(row["rating"], 4)
        self.assertTrue(row["recorded_at"])


class TestExportReviewCsv(_TempDirTestCase):
    def test_row_count_is_criteria_times_scenarios(self):
        export_review_csv(transcripts_path=self.transcripts_path, out_path=self.csv_path)
        import csv

        with open(self.csv_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), len(CRITERIA) * len(FAKE_TRANSCRIPTS))

    def test_rating_and_comment_columns_start_blank(self):
        export_review_csv(transcripts_path=self.transcripts_path, out_path=self.csv_path)
        import csv

        with open(self.csv_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertTrue(all(r["rating"] == "" for r in rows))
        self.assertTrue(all(r["comment"] == "" for r in rows))

    def test_transcript_content_present_in_rows(self):
        export_review_csv(transcripts_path=self.transcripts_path, out_path=self.csv_path)
        content = self.csv_path.read_text(encoding="utf-8")
        self.assertIn("What is a monosaccharide?", content)
        self.assertIn("A skeletal structure omits explicit C and H atoms.", content)

    def test_grounding_chunks_flattened_into_one_cell(self):
        export_review_csv(transcripts_path=self.transcripts_path, out_path=self.csv_path)
        content = self.csv_path.read_text(encoding="utf-8")
        self.assertIn("Monosaccharides are simple sugars.", content)
        self.assertIn("Glucose is a hexose.", content)


class TestImportReviewCsv(_TempDirTestCase):
    def _export_and_fill(self, fill_rows: dict[tuple[str, str], tuple[str, str]]):
        """fill_rows: {(scenario_id, criterion): (rating, comment)}"""
        import csv

        export_review_csv(transcripts_path=self.transcripts_path, out_path=self.csv_path)
        with open(self.csv_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            key = (row["scenario_id"], row["criterion"])
            if key in fill_rows:
                rating, comment = fill_rows[key]
                row["rating"] = rating
                row["comment"] = comment
        with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def test_only_filled_rows_are_imported(self):
        self._export_and_fill(
            {("fake_scenario_1", CRITERIA[0]): ("4", "clear and accurate")}
        )
        imported = import_review_csv(path=self.csv_path, results_path=self.results_path)
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0].scenario_id, "fake_scenario_1")
        self.assertEqual(imported[0].rating, 4)
        self.assertEqual(imported[0].comment, "clear and accurate")

    def test_reviewer_role_is_fixed_not_a_name(self):
        self._export_and_fill({("fake_scenario_1", CRITERIA[0]): ("5", "")})
        imported = import_review_csv(path=self.csv_path, results_path=self.results_path)
        self.assertEqual(imported[0].reviewer_role, "SENCO")

    def test_imported_ratings_land_in_results_jsonl(self):
        self._export_and_fill(
            {
                ("fake_scenario_1", CRITERIA[0]): ("4", "a"),
                ("fake_scenario_2", CRITERIA[1]): ("2", "b"),
            }
        )
        import_review_csv(path=self.csv_path, results_path=self.results_path)
        lines = self.results_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)

    def test_invalid_rating_in_a_filled_row_raises(self):
        self._export_and_fill({("fake_scenario_1", CRITERIA[0]): ("9", "bad")})
        with self.assertRaises(ValueError):
            import_review_csv(path=self.csv_path, results_path=self.results_path)


class TestGenerateReport(_TempDirTestCase):
    def test_no_ratings_yet_reports_that_cleanly(self):
        report = generate_report(results_path=self.results_path)
        self.assertIn("No ratings recorded yet.", report)

    def test_report_contains_descriptive_stats_and_quoted_comments(self):
        record_rating(
            ReviewRecord("fake_scenario_1", CRITERIA[0], 4, "solid grounding", "SENCO"),
            path=self.results_path,
        )
        record_rating(
            ReviewRecord("fake_scenario_2", CRITERIA[0], 2, "missed a nuance", "SENCO"),
            path=self.results_path,
        )
        report = generate_report(results_path=self.results_path)
        self.assertIn("n=2, mean=3.00, range=2-4", report)
        self.assertIn("solid grounding", report)
        self.assertIn("missed a nuance", report)

    def test_report_never_uses_inferential_language(self):
        record_rating(
            ReviewRecord("fake_scenario_1", CRITERIA[0], 5, "", "SENCO"),
            path=self.results_path,
        )
        report = generate_report(results_path=self.results_path).lower()
        for banned in ("p <", "p=", "p =", "statistically significant"):
            self.assertNotIn(banned, report)


if __name__ == "__main__":
    unittest.main()

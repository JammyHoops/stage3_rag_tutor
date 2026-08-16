"""Offline tests for the Stage 1 profile loader — no network/DB imports."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class TestLoadProfiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.csv_path = Path(self._tmp.name) / "stage1_profiles.csv"

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, rows: list[str]) -> None:
        header = "student_id,subject,flag_status,attainment_band\n"
        self.csv_path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")

    def test_missing_file_returns_empty_dict(self):
        from stage3.profiles.stage1_loader import load_profiles

        missing = Path(self._tmp.name) / "does_not_exist.csv"
        self.assertEqual(load_profiles(missing), {})

    def test_multi_row_per_student_nests_by_subject(self):
        from stage3.profiles.stage1_loader import load_profiles

        self._write(
            [
                "SYN0001,biology,none,above",
                "SYN0001,chemistry,confirmed,well_below",
            ]
        )
        profiles = load_profiles(self.csv_path)
        self.assertEqual(set(profiles["SYN0001"].keys()), {"biology", "chemistry"})
        self.assertEqual(profiles["SYN0001"]["biology"]["flag_status"], "none")
        self.assertEqual(profiles["SYN0001"]["chemistry"]["flag_status"], "confirmed")
        self.assertEqual(profiles["SYN0001"]["chemistry"]["attainment_band"], "well_below")

    def test_two_students_independent(self):
        from stage3.profiles.stage1_loader import load_profiles

        self._write(
            [
                "SYN0001,biology,none,above",
                "SYN0002,biology,confirmed,below",
            ]
        )
        profiles = load_profiles(self.csv_path)
        self.assertEqual(len(profiles), 2)
        self.assertEqual(profiles["SYN0001"]["biology"]["flag_status"], "none")
        self.assertEqual(profiles["SYN0002"]["biology"]["flag_status"], "confirmed")


class TestGetProfile(unittest.TestCase):
    def setUp(self):
        self.profiles = {
            "SYN0001": {
                "biology": {"student_id": "SYN0001", "subject": "biology", "flag_status": "none", "attainment_band": "above"},
            },
        }

    def test_known_student_known_subject(self):
        from stage3.profiles.stage1_loader import get_profile

        row = get_profile("SYN0001", "biology", self.profiles)
        self.assertEqual(row["flag_status"], "none")

    def test_known_student_unknown_subject_returns_none(self):
        from stage3.profiles.stage1_loader import get_profile

        self.assertIsNone(get_profile("SYN0001", "chemistry", self.profiles))

    def test_unknown_student_returns_none(self):
        from stage3.profiles.stage1_loader import get_profile

        self.assertIsNone(get_profile("SYN9999", "biology", self.profiles))


if __name__ == "__main__":
    unittest.main()

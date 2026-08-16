"""Offline tests for tutor/diagnostic.py — prompt builders + score-marker
parsing. No LLM/network calls; prompt builders are pure string assembly."""

from __future__ import annotations

import unittest

from stage3.tutor.diagnostic import (
    DIAGNOSTIC_SYSTEM_PROMPT,
    QUESTION_COUNT,
    build_grading_prompt,
    build_opening_prompt,
    parse_graded_response,
)

CHUNKS = [
    {
        "doc_id": "isaac_science:cb_carbohydrates__0#0",
        "provenance_tier": "third_party_education_platform",
        "content": "Carbohydrates are made of carbon, hydrogen and oxygen.",
        "source": "isaac_science",
        "source_url": "https://isaacscience.org/concepts/cb_carbohydrates",
        "section_title": "Carbohydrates",
    },
]


class TestBuildOpeningPrompt(unittest.TestCase):
    def test_system_prompt_is_diagnostic_specific(self):
        prompt = build_opening_prompt("biology", "Biochemistry", CHUNKS)
        self.assertEqual(prompt.system, DIAGNOSTIC_SYSTEM_PROMPT)

    def test_user_prompt_includes_topic_and_context(self):
        prompt = build_opening_prompt("biology", "Biochemistry", CHUNKS)
        self.assertIn("Biochemistry", prompt.user)
        self.assertIn("carbon, hydrogen and oxygen", prompt.user)

    def test_chunk_doc_ids_collected(self):
        prompt = build_opening_prompt("biology", "Biochemistry", CHUNKS)
        self.assertEqual(prompt.chunk_doc_ids, ["isaac_science:cb_carbohydrates__0#0"])

    def test_no_chunks_still_produces_a_prompt(self):
        prompt = build_opening_prompt("biology", "Biochemistry", [])
        self.assertIn("no curriculum extracts available", prompt.user)
        self.assertEqual(prompt.chunk_doc_ids, [])
        self.assertEqual(prompt.attributions, [])

    def test_attributions_populated_from_chunks(self):
        prompt = build_opening_prompt("biology", "Biochemistry", CHUNKS)
        self.assertEqual(len(prompt.attributions), 1)
        self.assertEqual(prompt.attributions[0]["title"], "Carbohydrates")
        self.assertEqual(prompt.attributions[0]["source_name"], "Isaac Science")

    def test_no_profile_note_omits_teaching_note_line(self):
        prompt = build_opening_prompt("biology", "Biochemistry", CHUNKS)
        self.assertNotIn("TEACHING NOTE", prompt.user)

    def test_empty_profile_note_omits_teaching_note_line(self):
        prompt = build_opening_prompt("biology", "Biochemistry", CHUNKS, profile_note={})
        self.assertNotIn("TEACHING NOTE", prompt.user)

    def test_profile_note_with_scaffolding_note_renders_teaching_note_line(self):
        prompt = build_opening_prompt(
            "biology",
            "Biochemistry",
            CHUNKS,
            profile_note={"scaffolding_note": "Keep the opening question gentle."},
        )
        self.assertIn("TEACHING NOTE: Keep the opening question gentle.", prompt.user)

    def test_forbidden_key_in_profile_note_raises(self):
        with self.assertRaises(ValueError):
            build_opening_prompt(
                "biology",
                "Biochemistry",
                CHUNKS,
                profile_note={"support_need": "should never reach a prompt"},
            )

    def test_non_allowed_field_in_profile_note_raises(self):
        with self.assertRaises(ValueError):
            build_opening_prompt(
                "biology",
                "Biochemistry",
                CHUNKS,
                profile_note={"attainment_band": "above"},
            )


class TestBuildGradingPrompt(unittest.TestCase):
    def test_non_final_asks_for_next_question(self):
        prompt = build_grading_prompt(
            subject="biology",
            topic="Biochemistry",
            curriculum_chunks=CHUNKS,
            prior_questions=["What are carbohydrates made of?"],
            student_answer="Carbon and water",
            is_final=False,
        )
        self.assertIn("ask ONE new short question", prompt.user)
        self.assertNotIn("LAST diagnostic question", prompt.user)
        self.assertEqual(prompt.attributions[0]["source_name"], "Isaac Science")

    def test_final_asks_for_wrapup_not_another_question(self):
        prompt = build_grading_prompt(
            subject="biology",
            topic="Biochemistry",
            curriculum_chunks=CHUNKS,
            prior_questions=["Q1", "Q2", "Q3"],
            student_answer="An answer",
            is_final=True,
        )
        self.assertIn("LAST diagnostic question", prompt.user)
        self.assertIn("Do NOT ask another", prompt.user)

    def test_prior_questions_listed_to_avoid_repeats(self):
        prompt = build_grading_prompt(
            subject="biology",
            topic="Biochemistry",
            curriculum_chunks=CHUNKS,
            prior_questions=["What is a monosaccharide?"],
            student_answer="A sugar",
            is_final=False,
        )
        self.assertIn("What is a monosaccharide?", prompt.user)

    def test_student_answer_embedded_verbatim(self):
        prompt = build_grading_prompt(
            subject="biology",
            topic="Biochemistry",
            curriculum_chunks=CHUNKS,
            prior_questions=[],
            student_answer="Glucose is a monosaccharide",
            is_final=False,
        )
        self.assertIn("Glucose is a monosaccharide", prompt.user)

    def test_score_marker_format_instruction_present(self):
        prompt = build_grading_prompt(
            subject="biology",
            topic="Biochemistry",
            curriculum_chunks=CHUNKS,
            prior_questions=[],
            student_answer="An answer",
            is_final=False,
        )
        self.assertIn("[[MASTERY_SCORE: X]]", prompt.user)


class TestParseGradedResponse(unittest.TestCase):
    def test_well_formed_marker_parsed(self):
        raw = "Good answer! Now, what about lipids?\n[[MASTERY_SCORE: 1.0]]"
        visible, score = parse_graded_response(raw)
        self.assertEqual(visible, "Good answer! Now, what about lipids?")
        self.assertEqual(score, 1.0)

    def test_marker_stripped_from_visible_text(self):
        raw = "Partially right.\n[[MASTERY_SCORE: 0.5]]"
        visible, _ = parse_graded_response(raw)
        self.assertNotIn("MASTERY_SCORE", visible)
        self.assertNotIn("[[", visible)

    def test_all_three_valid_scores_parse(self):
        for expected in (0.0, 0.5, 1.0):
            raw = f"Some reply.\n[[MASTERY_SCORE: {expected}]]"
            _, score = parse_graded_response(raw)
            self.assertEqual(score, expected)

    def test_missing_marker_returns_none_score_not_a_guess(self):
        raw = "The tutor forgot to include a marker."
        visible, score = parse_graded_response(raw)
        self.assertIsNone(score)
        self.assertEqual(visible, raw)

    def test_malformed_marker_returns_none_score(self):
        raw = "Some reply.\n[[MASTERY_SCORE: excellent]]"
        visible, score = parse_graded_response(raw)
        self.assertIsNone(score)

    def test_marker_must_be_at_end_not_mid_text(self):
        raw = "[[MASTERY_SCORE: 1.0]] this text comes after the marker"
        visible, score = parse_graded_response(raw)
        self.assertIsNone(score)


class TestQuestionCount(unittest.TestCase):
    def test_question_count_is_small_and_positive(self):
        # "Quick" diagnostic — sanity bound, not a strict business rule.
        self.assertGreater(QUESTION_COUNT, 0)
        self.assertLessEqual(QUESTION_COUNT, 5)


if __name__ == "__main__":
    unittest.main()

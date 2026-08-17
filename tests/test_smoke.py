"""Smoke tests — wiring only, no vector store, no network, no API key.

Deliberately avoids importing vectordb/retriever modules (they pull in
langchain + sentence-transformers, and the embedding model download is not
something a smoke test should trigger). Those paths get exercised by real
ingest runs instead.

Run:  python -m pytest tests/  (or: python -m unittest discover tests)

Redaction: the register/regex/allowlist layers are covered here (no
spaCy needed); the full NER-backed pipeline is in tests/test_redaction.py.
"""

from __future__ import annotations

import unittest


class TestConfig(unittest.TestCase):
    def test_config_imports_and_instantiates(self):
        # The helpdesk config.py raised ValueError on import (mutable
        # dataclass defaults). This guards the fix.
        from stage3.config import CONFIG

        self.assertTrue(CONFIG.paths.curriculum_dir.name == "curriculum")


class TestChunkingPassthrough(unittest.TestCase):
    def test_single_chunk_with_stable_id(self):
        from stage3.chunking import chunk_document

        doc = {"id": "maths/spec.md", "text": "Some content.", "source": "s",
               "metadata": {"subject": "mathematics"}}
        chunks = chunk_document(doc)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["id"], "maths/spec.md#0")
        self.assertEqual(chunks[0]["metadata"]["chunking"], "passthrough_v0")

    def test_empty_doc_yields_nothing(self):
        from stage3.chunking import chunk_document

        self.assertEqual(chunk_document({"id": "x", "text": "  "}), [])


class TestPromptGuard(unittest.TestCase):
    def test_forbidden_profile_field_rejected(self):
        from stage3.tutor.prompt_template import build_prompt

        with self.assertRaises(ValueError):
            build_prompt(
                subject="mathematics",
                redacted_student_text="working shown",
                curriculum_chunks=[],
                profile_note={"sen_status": "K"},  # must be rejected
            )

    def test_allowed_note_passes_and_ids_collected(self):
        from stage3.tutor.prompt_template import build_prompt

        built = build_prompt(
            subject="mathematics",
            redacted_student_text="working shown",
            curriculum_chunks=[
                {"doc_id": "curriculum_docs:maths/spec.md#0",
                 "content": "Differentiate polynomials.",
                 "provenance_tier": "awarding_body_spec"},
            ],
            profile_note={"scaffolding_note": "Break problems into steps."},
        )
        self.assertIn("Differentiate polynomials.", built.user)
        self.assertEqual(built.chunk_doc_ids, ["curriculum_docs:maths/spec.md#0"])
        # This fixture chunk has no source/source_url (curriculum_docs.py
        # chunks predate the attribution feature) — build_attributions
        # should degrade cleanly to no citations, not crash.
        self.assertEqual(built.attributions, [])

    def test_attributions_populated_for_a_real_source_chunk(self):
        from stage3.tutor.prompt_template import build_prompt

        built = build_prompt(
            subject="biology",
            redacted_student_text="working shown",
            curriculum_chunks=[
                {
                    "doc_id": "isaac_science:cb_carbohydrates__0#0",
                    "content": "Carbohydrates are made of carbon, hydrogen and oxygen.",
                    "provenance_tier": "third_party_education_platform",
                    "source": "isaac_science",
                    "source_url": "https://isaacscience.org/concepts/cb_carbohydrates",
                    "section_title": "Carbohydrates",
                },
            ],
        )
        self.assertEqual(len(built.attributions), 1)
        self.assertEqual(built.attributions[0]["title"], "Carbohydrates")
        self.assertEqual(built.attributions[0]["licence"], "CC BY 4.0")

    def test_forbidden_field_in_history_rejected(self):
        from stage3.tutor.prompt_template import build_prompt

        with self.assertRaises(ValueError):
            build_prompt(
                subject="mathematics",
                redacted_student_text="working shown",
                curriculum_chunks=[],
                conversation_history=[{"role": "student", "student_id": "123"}],
            )

    def test_valid_history_renders_into_prompt(self):
        from stage3.tutor.prompt_template import build_prompt

        built = build_prompt(
            subject="mathematics",
            redacted_student_text="working shown",
            curriculum_chunks=[],
            conversation_history=[
                {"role": "student", "text": "What is a derivative?"},
                {"role": "tutor", "text": "A rate of change."},
            ],
        )
        self.assertIn("What is a derivative?", built.user)
        self.assertIn("A rate of change.", built.user)

    def test_unknown_explanation_method_rejected(self):
        from stage3.tutor.prompt_template import build_prompt

        with self.assertRaises(ValueError):
            build_prompt(
                subject="mathematics",
                redacted_student_text="working shown",
                curriculum_chunks=[],
                explanation_method="interpretive_dance",  # not in the taxonomy
            )

    def test_known_explanation_method_renders_into_prompt(self):
        from stage3.tutor.prompt_template import build_prompt

        built = build_prompt(
            subject="mathematics",
            redacted_student_text="working shown",
            curriculum_chunks=[],
            explanation_method="worked_example",
        )
        self.assertIn("EXPLANATION APPROACH", built.user)
        self.assertIn("worked example", built.user)

    def test_no_explanation_method_omits_the_line(self):
        from stage3.tutor.prompt_template import build_prompt

        built = build_prompt(
            subject="mathematics",
            redacted_student_text="working shown",
            curriculum_chunks=[],
        )
        self.assertNotIn("EXPLANATION APPROACH", built.user)

    def test_forbidden_field_in_understanding_check_rejected(self):
        from stage3.tutor.prompt_template import build_prompt

        with self.assertRaises(ValueError):
            build_prompt(
                subject="mathematics",
                redacted_student_text="working shown",
                curriculum_chunks=[],
                pending_understanding_check={"student_id": "123"},
            )

    def test_unexpected_understanding_check_field_rejected(self):
        from stage3.tutor.prompt_template import build_prompt

        with self.assertRaises(ValueError):
            build_prompt(
                subject="mathematics",
                redacted_student_text="working shown",
                curriculum_chunks=[],
                pending_understanding_check={"extra_field": "x"},
            )

    def test_pending_understanding_check_adds_marker_instruction(self):
        from stage3.tutor.prompt_template import build_prompt

        built = build_prompt(
            subject="mathematics",
            redacted_student_text="working shown",
            curriculum_chunks=[],
            pending_understanding_check={"concept_label": "Derivatives"},
        )
        self.assertIn("Derivatives", built.user)
        self.assertIn("[[UNDERSTANDING: yes]]", built.user)

    def test_no_pending_check_omits_marker_instruction(self):
        from stage3.tutor.prompt_template import build_prompt

        built = build_prompt(
            subject="mathematics",
            redacted_student_text="working shown",
            curriculum_chunks=[],
        )
        self.assertNotIn("UNDERSTANDING", built.user)

    def test_system_prompt_never_signals_a_level_drop(self):
        from stage3.tutor.prompt_template import SYSTEM_PROMPT

        self.assertIn("no meta-commentary about", SYSTEM_PROMPT)

    def test_system_prompt_defers_to_explanation_approach(self):
        from stage3.tutor.prompt_template import SYSTEM_PROMPT

        self.assertIn("EXPLANATION APPROACH", SYSTEM_PROMPT)

    def test_long_chunk_content_is_truncated(self):
        from stage3.tutor.prompt_template import MAX_CHUNK_CHARS, build_prompt

        built = build_prompt(
            subject="mathematics",
            redacted_student_text="working shown",
            curriculum_chunks=[
                {"doc_id": "x", "content": "a" * (MAX_CHUNK_CHARS + 500)},
            ],
        )
        self.assertIn("…[truncated]", built.user)
        # The rendered chunk text itself should not exceed the cap
        # (plus the small truncation marker's own length).
        content_line = [
            line for line in built.user.splitlines() if line.startswith("[1 |")
        ][0]
        self.assertLessEqual(len(content_line), MAX_CHUNK_CHARS + 50)

    def test_short_chunk_content_is_not_truncated(self):
        from stage3.tutor.prompt_template import build_prompt

        built = build_prompt(
            subject="mathematics",
            redacted_student_text="working shown",
            curriculum_chunks=[{"doc_id": "x", "content": "A short chunk."}],
        )
        self.assertIn("A short chunk.", built.user)
        self.assertNotIn("…[truncated]", built.user)


class TestRedactionRegexAndRegister(unittest.TestCase):
    """Fast, offline coverage of the non-spaCy layers of redaction.py.

    The full redact() pipeline (register + regex + NER + allowlist) needs
    the spaCy model loaded — that's tests/test_redaction.py, kept separate
    per this file's own no-heavy-deps policy (see module docstring).
    """

    def test_register_match_full_and_first_name(self):
        from stage3.redaction import _find_register_matches

        names = ["Priya Shah"]
        spans_full = _find_register_matches("Priya Shah helped me.", names)
        spans_first = _find_register_matches("Priya helped me.", names)
        self.assertTrue(spans_full)
        self.assertTrue(spans_first)

    def test_register_does_not_match_stem_vocabulary(self):
        from stage3.redaction import _find_register_matches

        names = ["Priya Shah"]
        spans = _find_register_matches("DNA carries genetic information.", names)
        self.assertEqual(spans, [])

    def test_email_and_phone_regex(self):
        from stage3.redaction import _find_structured_pii_matches

        spans = _find_structured_pii_matches(
            "email me at priya@example.com or call 07911 123456"
        )
        categories = sorted(s.category for s in spans)
        self.assertEqual(categories, ["EMAIL", "PHONE"])

    def test_allowlist_suppresses_matching_span(self):
        from stage3.redaction import _Span, _filter_allowed_spans

        text = "Newton's third law of motion."
        # Span over "Newton" (index 0-6), as NER would produce.
        spans = [_Span(0, 6, "NAME")]
        filtered = _filter_allowed_spans(spans, text, {"newton"})
        self.assertEqual(filtered, [])


class TestNullLLM(unittest.TestCase):
    def test_offline_generate(self):
        from stage3.llm.client import NullLLM

        out = NullLLM().generate("hello", system="sys")
        self.assertIn("NullLLM", out)


class TestGeminiClientFailsFast(unittest.TestCase):
    def test_missing_api_key_raises_before_importing_sdk(self):
        # Must fail on the missing key, not on a missing google-genai
        # install — the import is lazy specifically so this stays true.
        from stage3.config import CONFIG
        from stage3.llm.client import GeminiLLM

        original = CONFIG.llm.api_key
        CONFIG.llm.api_key = ""
        try:
            with self.assertRaises(ValueError):
                GeminiLLM()
        finally:
            CONFIG.llm.api_key = original


if __name__ == "__main__":
    unittest.main()

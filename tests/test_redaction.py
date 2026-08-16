"""Real, spaCy-backed redaction tests.

Deliberately kept OUT of tests/test_smoke.py, which documents itself as
avoiding heavy-dependency codepaths — this file exercises the full
redact() pipeline including the local NER model and requires
``python -m spacy download en_core_web_sm`` to have been run once.

Run:  python -m pytest tests/test_redaction.py
  or: python -m unittest tests.test_redaction
"""

from __future__ import annotations

import unittest


def _spacy_model_available() -> bool:
    try:
        import spacy

        spacy.load("en_core_web_sm")
        return True
    except Exception:
        return False


_SKIP_REASON = (
    "en_core_web_sm not installed — run: python -m spacy download en_core_web_sm"
)

TEST_NAMES = [
    "Priya Shah",
    "Tomasz Nowak",
    "Aaliyah Bennett",
    "Kwame Owusu",
    "Ffion Pritchard",
]


@unittest.skipUnless(_spacy_model_available(), _SKIP_REASON)
class TestRedactFullPipeline(unittest.TestCase):
    def test_register_name_redacted(self):
        from stage3.redaction import _apply_spans, _find_register_matches

        text = "Priya was stuck on question 3."
        spans = _find_register_matches(text, TEST_NAMES)
        self.assertIn("[NAME]", _apply_spans(text, spans))

    def test_non_register_name_caught_by_ner(self):
        from stage3.redaction import _find_ner_matches

        spans = _find_ner_matches("My friend Charlotte Bishop helped me revise.")
        self.assertTrue(any(s.category == "NAME" for s in spans))

    def test_email_and_phone_redacted(self):
        from stage3.redaction import _apply_spans, _find_structured_pii_matches

        text = "Contact me at priya.shah@example.com or 07911 123456."
        spans = _find_structured_pii_matches(text)
        out = _apply_spans(text, spans)
        self.assertIn("[EMAIL]", out)
        self.assertIn("[PHONE]", out)

    def test_overlapping_email_and_register_name_no_double_redaction(self):
        from stage3.redaction import (
            _apply_spans,
            _find_register_matches,
            _find_structured_pii_matches,
        )

        text = "email priya.shah@example.com please"
        spans = _find_register_matches(text, TEST_NAMES) + _find_structured_pii_matches(
            text
        )
        out = _apply_spans(text, spans)
        self.assertNotIn("[NAME]", out)  # fully absorbed into the EMAIL span
        self.assertEqual(out.count("["), 1)  # exactly one placeholder, no artifact

    def test_stem_text_with_eponym_unchanged_thanks_to_allowlist(self):
        # The load-bearing test: proves the Newton/eponym problem is
        # actually closed by the allowlist, regardless of whether this
        # spaCy model happens to tag "Newton" as PERSON or not.
        from stage3.redaction import redact

        text = (
            "Newton's third law states every action has an equal "
            "and opposite reaction."
        )
        self.assertEqual(redact(text), text)

    def test_redact_end_to_end(self):
        from stage3.redaction import redact

        out = redact(
            "Priya emailed priya.shah@example.com about Newton's laws."
        )
        self.assertIn("[NAME]", out)
        self.assertIn("[EMAIL]", out)
        self.assertIn("Newton", out)  # protected by the allowlist


if __name__ == "__main__":
    unittest.main()

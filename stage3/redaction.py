"""Shared redaction gate for any student-authored text reaching an LLM.

PROVENANCE — NEW (relocated from a Stage-2-only gate in
``stage2_bridge/intake.py``; generalised because typed chat input needs
the same privacy boundary as Stage 2 OCR output).

FAIL-CLOSED BY DESIGN: unredacted student text must never reach a cloud
LLM via any path. Three detection layers run independently against the
original text and are merged as spans (never sequentially, so one layer's
output can't confuse another — see ``_merge_spans``), plus one allowlist
override:

    A. Known-names register (exact match, ``data/redaction/known_names.txt``,
       gitignored) — avoids false-positiving on STEM vocabulary the way a
       blind "strip capitalised words" heuristic would.
    B. Structured PII regex: email addresses, UK phone numbers.
    C. Local spaCy NER (PERSON entities), offline — catches names not on
       the register (a friend, an unregistered sibling, an OCR-garbled
       name).
    Allowlist override (``data/redaction/allowed_terms.txt``, committed —
       curriculum vocabulary, not student data) — suppresses redaction of
       listed terms regardless of which layer matched them, so a
       scientist's eponym ("Newton's third law") isn't wrongly redacted by
       Layer C.

Matched spans are not outright deleted, but replaced with bracketed
category placeholders (``[NAME]``, ``[EMAIL]``, ``[PHONE]``) to preserve
sentence structure for the tutor LLM to parse.

See docs/design/FINDINGS_AND_DECISIONS.md §4 for the rationale behind this
design and its documented trade-offs, and docs/TODO.md for open items
(DOB detection, register collisions, phone/email validation).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import CONFIG

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Spans + merge/apply (shared by all layers)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Span:
    start: int
    end: int
    category: str  # "NAME" | "EMAIL" | "PHONE"


_PLACEHOLDER = {"NAME": "[NAME]", "EMAIL": "[EMAIL]", "PHONE": "[PHONE]"}
# Tiebreak for equal-start, equal-length spans. Arbitrary but deterministic.
_CATEGORY_PRIORITY = {"EMAIL": 0, "PHONE": 1, "NAME": 2}


def _merge_spans(spans: list[_Span]) -> list[_Span]:
    """Sort by (start, -length) and absorb fully-nested/overlapping spans.

    Sorting longest-first means a wider EMAIL span at the same start
    position absorbs any narrower NAME spans nested inside it (e.g. the
    two halves of an email's local part), instead of both being applied
    and corrupting the match.
    """
    if not spans:
        return []
    ordered = sorted(
        spans,
        key=lambda s: (s.start, -(s.end - s.start), _CATEGORY_PRIORITY[s.category]),
    )
    merged: list[_Span] = [ordered[0]]
    for nxt in ordered[1:]:
        current = merged[-1]
        if nxt.start < current.end:
            if nxt.end > current.end:
                merged[-1] = _Span(current.start, nxt.end, current.category)
            # else nxt is fully inside current: drop it
        else:
            merged.append(nxt)
    return merged


def _apply_spans(text: str, spans: list[_Span]) -> str:
    merged = _merge_spans(spans)
    out: list[str] = []
    cursor = 0
    for sp in merged:
        out.append(text[cursor : sp.start])
        out.append(_PLACEHOLDER[sp.category])
        cursor = sp.end
    out.append(text[cursor:])
    return "".join(out)


# ---------------------------------------------------------------------------
# Layer A — known-names register
# ---------------------------------------------------------------------------

MIN_TOKEN_LEN = 3  # drops initials / very short tokens to cut false positives

_REGISTER_PATTERN_CACHE: Optional[re.Pattern] = None


def _build_register_pattern(names: list[str]) -> Optional[re.Pattern]:
    phrases: set[str] = set()
    for name in names:
        cleaned = name.strip()
        if not cleaned:
            continue
        phrases.add(cleaned)
        for token in cleaned.split():
            if len(token) >= MIN_TOKEN_LEN:
                phrases.add(token)
    if not phrases:
        return None
    # Longest-first: re alternation is first-match-wins, so a full name
    # must precede its own component tokens at the same position.
    ordered = sorted(phrases, key=len, reverse=True)
    return re.compile(
        r"\b(?:" + "|".join(re.escape(p) for p in ordered) + r")\b",
        re.IGNORECASE,
    )


def _load_known_names(path: Path | None = None) -> list[str]:
    p = path or CONFIG.paths.known_names_file
    if not p.exists():
        # No register yet is a normal early-deployment state, not an
        # error; Layers B/C still run.
        logger.warning(
            "Known-names register not found at %s — register-based "
            "redaction will match nothing this run.", p,
        )
        return []
    names: list[str] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line:
                names.append(line)
    return names


def _find_register_matches(
    text: str, names: list[str] | None = None
) -> list[_Span]:
    """``names`` overrides the configured register file (used by tests)."""
    global _REGISTER_PATTERN_CACHE
    if names is not None:
        pattern = _build_register_pattern(names)
    else:
        if _REGISTER_PATTERN_CACHE is None:
            _REGISTER_PATTERN_CACHE = _build_register_pattern(_load_known_names())
        pattern = _REGISTER_PATTERN_CACHE
    if pattern is None:
        return []
    return [_Span(m.start(), m.end(), "NAME") for m in pattern.finditer(text)]


# ---------------------------------------------------------------------------
# Layer B — structured PII regex
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_UK_PHONE_RE = re.compile(
    r"(?:\+44\s?7\d{3}|\b07\d{3})[\s-]?\d{3}[\s-]?\d{3}"  # UK mobile
    r"|(?:\+44\s?|\b0)\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}\b"  # UK landline (loose)
)


def _find_structured_pii_matches(text: str) -> list[_Span]:
    spans = [_Span(m.start(), m.end(), "EMAIL") for m in _EMAIL_RE.finditer(text)]
    spans += [_Span(m.start(), m.end(), "PHONE") for m in _UK_PHONE_RE.finditer(text)]
    return spans


# ---------------------------------------------------------------------------
# Layer C — local spaCy NER (lazy-loaded)
# ---------------------------------------------------------------------------

_NLP = None  # module-level cache, populated on first real use


def _get_nlp():
    """Lazy import + load, so importing this module never forces a spaCy
    load for code paths that don't call redact()."""
    global _NLP
    if _NLP is None:
        import spacy

        try:
            _NLP = spacy.load("en_core_web_sm")
        except OSError as e:
            # Not caught by redact(): a missing model must fail loudly,
            # not silently degrade to register+regex-only.
            raise RuntimeError(
                "spaCy model 'en_core_web_sm' not found. Run: "
                "python -m spacy download en_core_web_sm"
            ) from e
    return _NLP


def _find_ner_matches(text: str) -> list[_Span]:
    doc = _get_nlp()(text)
    return [
        _Span(ent.start_char, ent.end_char, "NAME")
        for ent in doc.ents
        if ent.label_ == "PERSON"
    ]


# ---------------------------------------------------------------------------
# Allowlist override
# ---------------------------------------------------------------------------

_ALLOWED_TERMS_CACHE: Optional[set[str]] = None


def _load_allowed_terms(path: Path | None = None) -> set[str]:
    p = path or CONFIG.paths.allowed_terms_file
    if not p.exists():
        return set()
    terms: set[str] = set()
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line:
                terms.add(line.lower())
    return terms


def _filter_allowed_spans(
    spans: list[_Span], text: str, allowed: set[str]
) -> list[_Span]:
    """Drop any span whose matched text is on the allowlist. Applies to
    every layer, not just NER — protects against register false positives
    too."""
    if not allowed:
        return spans
    kept = []
    for sp in spans:
        matched = text[sp.start : sp.end].strip().lower()
        if matched in allowed:
            continue
        kept.append(sp)
    return kept


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def redact(text: str) -> str:
    """Redact personal identifiers from student text before any cloud call.

    FAIL-CLOSED BY DESIGN — see module docstring. Do not catch exceptions
    from any layer here (particularly the NER model-missing RuntimeError)
    and fall back to a partial pass; that would be a silent weakening of
    the guarantee this module exists to provide.
    """
    if not text:
        return text

    global _ALLOWED_TERMS_CACHE
    if _ALLOWED_TERMS_CACHE is None:
        _ALLOWED_TERMS_CACHE = _load_allowed_terms()

    spans = [
        *_find_register_matches(text),
        *_find_structured_pii_matches(text),
        *_find_ner_matches(text),
    ]
    spans = _filter_allowed_spans(spans, text, _ALLOWED_TERMS_CACHE)
    return _apply_spans(text, spans)

"""Shared redaction gate for any student-authored text reaching an LLM.

PROVENANCE — NEW (relocated). Originally lived only in
``stage2_bridge/intake.py`` as a Stage-2-specific gate. Generalised here
because the same privacy-boundary argument applies to typed chat input just
as much as to Stage 2 handwriting-recognition output: a student can type a
name into a chat box exactly as easily as they can write one on paper.

PRIVACY — THE POINT OF THIS MODULE (Chapter 2 / Chapter 3 argument):
``redact()`` is FAIL-CLOSED: unredacted student text must never reach a
cloud LLM via any path — Stage 2 or typed chat.

METHOD — three detection layers, run independently against the original
text and merged as spans (never sequentially, so one layer's output can't
confuse another — see ``_merge_spans``), plus one allowlist override:

    A. Known-names register (exact match, ``data/redaction/known_names.txt``,
       gitignored). A blind "strip capitalised words" heuristic — the
       original sketch for this module — would wrongly nuke legitimate
       STEM vocabulary (Newton, DNA, Pythagoras, Ohm); an exact-match
       register avoids that because it only touches names actually on the
       list. This is a legitimate closed-cohort assumption for a specific
       school's specific SEN tutoring deployment (unlike a general-purpose
       public tool), not a hack.
    B. Structured PII regex: email addresses, UK phone numbers. Pragmatic,
       not a validated phone-number library — see TODO.
    C. Local spaCy NER (PERSON entities), offline, no cloud call — catches
       names NOT on the register (a friend, an unregistered sibling, an
       OCR-garbled name). Added because the register alone doesn't satisfy
       this module's own guarantee: "unredacted text must never reach a
       cloud LLM" is unconditional, not "text with pre-registered names
       only" — closing that gap is the entire reason Layer C exists.
    Allowlist override (``data/redaction/allowed_terms.txt``, COMMITTED —
       curriculum vocabulary, not student data): Layer C can reintroduce a
       narrow version of the exact problem Layer A solves — a scientist's
       eponym (Newton, Faraday, Darwin, Curie) is grammatically identical
       to a person-possessive ("Newton's third law"), so generic NER may
       tag it PERSON. The allowlist suppresses redaction of listed terms
       regardless of which layer matched them. Documented trade-off: a
       student literally named e.g. "Newton" would have that name
       protected from redaction by mistake — narrow, real, and stated here
       honestly rather than pretended away.

Matched spans are replaced with bracketed category placeholders
(``[NAME]``, ``[EMAIL]``, ``[PHONE]``) rather than deleted outright, so
sentence structure and grammatical role stay intact for the tutor LLM to
still parse what the student was asking.

TODO:
    [ ] Date-of-birth / generic date detection deliberately deferred — a
        date regex would have poor precision in STEM problem text (dates
        appear legitimately in maths/science/history questions), and no
        reliable way to distinguish "DOB" from "a date in a word problem"
        was found without more context than is available here. A known
        limitation, not an oversight.
    [ ] Register token collisions with ordinary words (no stoplist is
        built for this — would need curriculum-vocabulary awareness, the
        exact problem the register exists to avoid on the NER side; not
        justified at this scale). If this bites in practice, prefer
        matching the full name only for that entry over a bespoke list.
    [ ] UK phone/email regex are pragmatic, not RFC/E.164-validated — no
        new heavy dependency (e.g. ``phonenumbers``) was added for this.
    [ ] Evaluate against real (redacted-for-review) sample scripts once
        Stage 2 produces real output; tune MIN_TOKEN_LEN and the allowlist
        from what expert review (the SENCO reviewer) actually flags.
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
# Tiebreak only (used when two spans start at the same position and are the
# same length) — arbitrary but deterministic, not a priority in any other sense.
_CATEGORY_PRIORITY = {"EMAIL": 0, "PHONE": 1, "NAME": 2}


def _merge_spans(spans: list[_Span]) -> list[_Span]:
    """Sort by (start, -length) and absorb fully-nested/overlapping spans.

    Longest-first matters concretely: for "email priya.shah@school.org
    please", the EMAIL span fully contains the register matches for
    "priya" and "shah" (word boundaries around "." / "@" still count) —
    sorting by descending length puts EMAIL first at that start position
    so both NAME spans get absorbed and dropped, giving one clean
    "[EMAIL]" rather than a "[NAME].[NAME]@..." artifact.
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
            # else: nxt fully inside current — drop it, nothing to do
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

MIN_TOKEN_LEN = 3  # drops initials / very short tokens — false-positive mitigation

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
    # Longest-first so full names take precedence over their component
    # tokens at the same text position (re alternation is first-match-wins).
    ordered = sorted(phrases, key=len, reverse=True)
    return re.compile(
        r"\b(?:" + "|".join(re.escape(p) for p in ordered) + r")\b",
        re.IGNORECASE,
    )


def _load_known_names(path: Path | None = None) -> list[str]:
    p = path or CONFIG.paths.known_names_file
    if not p.exists():
        # A school not having supplied a register yet is a legitimate
        # early-deployment state, not an error — Layers B/C still run.
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
# Layer C — local spaCy NER (lazy-loaded — see module docstring)
# ---------------------------------------------------------------------------

_NLP = None  # module-level cache, populated on first real use


def _get_nlp():
    """Lazy import + load, matching the GeminiLLM pattern in llm/client.py —
    so importing this module (e.g. via stage2_bridge.intake's re-export)
    never forces a spaCy load for code paths that don't call redact().
    """
    global _NLP
    if _NLP is None:
        import spacy

        try:
            _NLP = spacy.load("en_core_web_sm")
        except OSError as e:
            # Deliberately NOT caught by redact() — a missing model must
            # not silently degrade to register+regex-only. That would
            # reintroduce exactly the silent-passthrough risk this whole
            # module exists to prevent.
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
    """Drop any span whose matched text is on the allowlist — protects
    against register false-positives too, not just NER ones.
    """
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

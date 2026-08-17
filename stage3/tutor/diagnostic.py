"""LLM-graded diagnostic Q&A — the mastery-baseline mechanism.

PROVENANCE — NEW. Implements the mechanism behind
``student_state/store.py::record_observation``: each topic thread opens
with a short Q&A that seeds a real mastery estimate, rather than starting
cold. Kept as its own module rather than folded into
``prompt_template.py`` because it has a genuinely different prompt
contract: the LLM must emit a machine-parseable score marker alongside its
visible reply.

Questions are LLM-generated and LLM-graded, not drawn from real curriculum
question banks — see docs/design/FINDINGS_AND_DECISIONS.md §5 for why
(bespoke interactive widgets with no answer key in the public API).

MECHANISM: ``chat_session.py`` calls ``build_opening_prompt`` once when a
diagnostic round starts. For each of the next ``QUESTION_COUNT`` student
answers, it calls ``build_grading_prompt``, which asks the LLM to grade
the just-given answer and (unless this is the final question) ask the
next one, in a single call. The response ends with a machine-parseable
score marker on its own line, e.g.:

    Good, that's broadly right. Now, can you tell me...
    [[MASTERY_SCORE: 0.5]]

``parse_graded_response`` strips that marker before anything is shown to
the student and extracts the score. If the marker is missing or
malformed, the response is still shown but no score is returned — the
caller must not guess a value and must skip ``record_observation`` for
that turn.

``build_opening_prompt`` accepts an optional ``profile_note`` — the one
genuinely cold-start moment for Stage 1 data, reusing
``prompt_template.py``'s ``_guard``/``ALLOWED_PROFILE_FIELDS`` directly.
See ``tutor/context_builder.py``'s docstring for why it lives here and
not the normal-tutoring path. Not threaded into ``build_grading_prompt``
— the note frames the opening question's tone only.

See docs/TODO.md for open items (non-repeat guarantee, extract length cap).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from .attribution import build_attributions
from .prompt_template import ALLOWED_PROFILE_FIELDS, _guard

logger = logging.getLogger(__name__)

# How many questions make up one diagnostic round. Kept small — this is
# meant to be a "quick" baseline check, not a real assessment.
QUESTION_COUNT = 3

_SCORE_MARKER_RE = re.compile(
    r"\n?\[\[MASTERY_SCORE:\s*(0\.0|0\.5|1\.0)\]\]\s*$"
)

DIAGNOSTIC_SYSTEM_PROMPT = (
    "You are a patient subject tutor for a sixth-form student, currently "
    "running a SHORT diagnostic check-in before the main tutoring "
    "conversation begins. Ask ONE short, single-focus conceptual "
    "question at a time, grounded in the curriculum extracts provided. "
    "Never answer your own question. Keep your tone encouraging, never "
    "exam-like or intimidating — this is a quick, low-stakes check-in, "
    "not a test."
)


@dataclass
class DiagnosticPrompt:
    system: str
    user: str
    chunk_doc_ids: list[str]
    attributions: list[dict[str, str]]  # human-readable CC citations — see attribution.py


def _format_context(curriculum_chunks: Sequence[dict[str, Any]]) -> str:
    lines = []
    for i, chunk in enumerate(curriculum_chunks, start=1):
        tier = chunk.get("provenance_tier", "?")
        lines.append(f"[{i} | {tier}] {chunk.get('content', '')}")
    return "\n\n".join(lines) if lines else "(no curriculum extracts available)"


def _chunk_doc_ids(curriculum_chunks: Sequence[dict[str, Any]]) -> list[str]:
    return [
        str(c.get("doc_id") or c.get("id") or f"chunk-{i}")
        for i, c in enumerate(curriculum_chunks, start=1)
    ]


def build_opening_prompt(
    subject: str,
    topic: str,
    curriculum_chunks: Sequence[dict[str, Any]],
    profile_note: Mapping[str, Any] | None = None,
) -> DiagnosticPrompt:
    """The very first message of a diagnostic round — no prior answer to grade.

    ``profile_note``, when given, may contain only ALLOWED_PROFILE_FIELDS
    (same guard as prompt_template.py's normal-turn path) and renders as
    a TEACHING NOTE line — the one place Stage 1 data is allowed to
    influence a prompt, since this is the genuinely cold-start moment
    (see context_builder.py's module docstring).
    """
    profile_note = dict(profile_note or {})
    _guard(profile_note, "profile_note")
    unexpected = set(profile_note) - set(ALLOWED_PROFILE_FIELDS)
    if unexpected:
        raise ValueError(
            f"profile_note contains non-allowed fields {sorted(unexpected)}; "
            f"allowed: {ALLOWED_PROFILE_FIELDS}"
        )

    user = (
        f"SUBJECT: {subject}\nTOPIC: {topic}\n\n"
        f"CONTEXT (curriculum extracts):\n{_format_context(curriculum_chunks)}\n\n"
        + (
            f"TEACHING NOTE: {profile_note['scaffolding_note']}\n\n"
            if profile_note.get("scaffolding_note")
            else ""
        )
        + "Ask ONE short question to check the student's starting "
        f"understanding of {topic!r}. Output only the question — no "
        "preamble, no greeting, no answer."
    )
    return DiagnosticPrompt(
        system=DIAGNOSTIC_SYSTEM_PROMPT,
        user=user,
        chunk_doc_ids=_chunk_doc_ids(curriculum_chunks),
        attributions=build_attributions(curriculum_chunks),
    )


def build_grading_prompt(
    subject: str,
    topic: str,
    curriculum_chunks: Sequence[dict[str, Any]],
    prior_questions: Sequence[str],
    student_answer: str,
    is_final: bool,
) -> DiagnosticPrompt:
    """Grade the answer to the most recent question, then either ask the
    next one or (if ``is_final``) wrap up into normal tutoring.

    ``prior_questions`` is every diagnostic question asked so far this
    round (oldest first) — passed so the model doesn't repeat itself.
    ``student_answer`` must already be redaction.redact()-ed, same
    requirement as prompt_template.build_prompt's equivalent parameter.
    """
    prior_qs_block = "\n".join(f"- {q}" for q in prior_questions) or "(none yet)"
    if is_final:
        next_step = (
            "This was the LAST diagnostic question. Do NOT ask another "
            "question — instead, write one short, encouraging sentence "
            "transitioning into the main tutoring conversation on this topic."
        )
    else:
        next_step = (
            "Then ask ONE new short question to continue checking their "
            f"understanding of {topic!r} — different from the questions "
            "already asked in this round (listed below)."
        )

    user = (
        f"SUBJECT: {subject}\nTOPIC: {topic}\n\n"
        f"CONTEXT (curriculum extracts):\n{_format_context(curriculum_chunks)}\n\n"
        f"QUESTIONS ALREADY ASKED THIS ROUND:\n{prior_qs_block}\n\n"
        f"STUDENT'S ANSWER TO THE MOST RECENT QUESTION (redacted):\n{student_answer}\n\n"
        "First, using the curriculum extracts as reference, judge whether "
        "this answer is correct, partially correct, or incorrect. "
        f"{next_step}\n\n"
        "Respond in EXACTLY this format: your reply text (what the "
        "student sees) on one or more lines, followed by a final line "
        "with nothing else on it:\n"
        "[[MASTERY_SCORE: X]]\n"
        "where X is exactly one of 0.0 (incorrect), 0.5 (partially "
        "correct), or 1.0 (correct). That marker line must be the very "
        "last thing in your response."
    )
    return DiagnosticPrompt(
        system=DIAGNOSTIC_SYSTEM_PROMPT,
        user=user,
        chunk_doc_ids=_chunk_doc_ids(curriculum_chunks),
        attributions=build_attributions(curriculum_chunks),
    )


def parse_graded_response(raw: str) -> tuple[str, Optional[float]]:
    """Split an LLM diagnostic response into (visible_text, score).

    ``score`` is ``None`` if the marker is missing or malformed — callers
    must treat that as "don't record an observation", not as a 0.0.
    """
    match = _SCORE_MARKER_RE.search(raw)
    if not match:
        logger.warning(
            "[diagnostic] No MASTERY_SCORE marker found in LLM response — "
            "skipping mastery observation for this turn. Raw (truncated): %r",
            raw[:200],
        )
        return raw.strip(), None

    score = float(match.group(1))
    visible = raw[: match.start()].strip()
    return visible, score

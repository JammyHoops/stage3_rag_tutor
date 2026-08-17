"""Explicit, auditable prompt construction — the privacy boundary in code.

PROVENANCE — NEW, and a deliberate correction of the helpdesk pattern,
which f-stringed its entire raw context dict into the prompt. See
docs/design/FINDINGS_AND_DECISIONS.md §7 for why that was a real privacy
risk for Stage 3 specifically.

DESIGN RULE: every field that reaches the prompt is named in the function
signature below. Nothing is interpolated wholesale. ``_guard`` rejects any
value containing a forbidden key, so a future refactor can't quietly
reintroduce the helpdesk pattern.

``explanation_method`` and ``pending_understanding_check`` wire in
Thompson-sampled explanation-method selection (see
``student_state/explanation_method.py``); the latter asks the LLM to end
its reply with a trailing ``[[UNDERSTANDING: yes|no]]`` marker, parsed by
``student_state.explanation_method.parse_understanding_marker``.

The pedagogy instruction set (``SYSTEM_PROMPT``) and the chunk character
budget (``MAX_CHUNK_CHARS``) are grounded in VanLehn (2011) and calibrated
against real ingested chunk lengths — see FINDINGS_AND_DECISIONS.md §7.

``BuiltPrompt.attributions`` (populated by
``tutor/attribution.py::build_attributions``) carries human-readable CC
citations through to the frontend, replacing a raw dump of internal
``chunk_doc_ids``.

``ALLOWED_PROFILE_FIELDS`` is enforced here but no longer called from this
module's own ``build_prompt`` with a non-empty note — see
``tutor/context_builder.py``'s docstring for why the real Stage 1 signal
moved to ``diagnostic.py::build_opening_prompt`` instead (reusing this
module's ``_guard``/``ALLOWED_PROFILE_FIELDS`` directly).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..student_state.explanation_method import EXPLANATION_METHODS, METHOD_LABELS
from .attribution import build_attributions

# Fields that must never appear in prompt inputs. Checked
# case-insensitively as substrings of keys.
FORBIDDEN_KEY_FRAGMENTS = (
    "student_id",
    "name",
    "dob",
    "date_of_birth",
    "upn",
    "residual",        # raw Stage 1 model output
    "sen",             # any support-need field
    "support_need",
    "ehcp",
    "diagnosis",
)

# The only profile-derived content permitted into a prompt. Coarse
# category text, not model internals.
ALLOWED_PROFILE_FIELDS = ("scaffolding_note",)

# Conversation history: bounded turn window and the only allowed shape per
# turn, guarded the same way as profile_note/chunks (see DESIGN RULE above).
MAX_HISTORY_TURNS = 6
ALLOWED_HISTORY_FIELDS = ("role", "text")

ALLOWED_UNDERSTANDING_CHECK_FIELDS = ("concept_label",)

# Per-chunk character cap for CONTEXT. Calibrated against real ingested
# chunk lengths (observed range 222-6413 chars, median ~1163) so one long
# outlier chunk can't crowd out the rest of the top_k results.
MAX_CHUNK_CHARS = 2000

SYSTEM_PROMPT = (
    "You are a patient, encouraging subject tutor for a UK sixth-form "
    "student (roughly ages 16-18, studying towards A-level or "
    "equivalent). Ground every statement in the curriculum extracts "
    "provided in CONTEXT — if the extracts do not cover the question, "
    "say so rather than guessing or drawing on outside knowledge.\n\n"
    "How to explain:\n"
    "- Default to guiding the student toward the answer rather than "
    "stating it outright: offer a hint, a leading question, or just the "
    "first step, and give the full answer only if they are still stuck "
    "after that. If an EXPLANATION APPROACH is specified below, follow "
    "that instead — it takes priority over this default (it may "
    "deliberately ask for something else, e.g. a worked example shown "
    "up front).\n"
    "- For a question with more than one step or part, work through it "
    "step by step and check understanding after each one, rather than "
    "delivering the full answer in one block and stopping. For a single "
    "short factual question, a direct answer is fine — don't manufacture "
    "steps that aren't there.\n"
    "- Use plain, direct language a sixth-former will find natural. "
    "Don't oversimplify to the point of being inaccurate, but avoid "
    "unnecessary jargon — define a technical term the first time you use "
    "it rather than assuming it or dodging it.\n"
    "- If the curriculum extracts mix content written for different "
    "levels, blend it into ONE explanation with no meta-commentary about "
    "level — never say things like \"let's step back to GCSE basics\" or "
    "otherwise signal that easier material was folded in.\n"
)


@dataclass
class BuiltPrompt:
    system: str
    user: str
    chunk_doc_ids: list[str]  # provenance — flows to feedback + ShowSources
    attributions: list[dict[str, str]]  # human-readable CC citations — see attribution.py


def _guard(mapping: Mapping[str, Any], label: str) -> None:
    """Reject forbidden keys anywhere in a prompt-bound mapping."""
    for key in mapping:
        low = str(key).lower()
        for frag in FORBIDDEN_KEY_FRAGMENTS:
            if frag in low:
                raise ValueError(
                    f"Forbidden field {key!r} in {label} — this must not "
                    "reach the LLM. See prompt_template.py docstring."
                )


def _guard_history(history: Sequence[Mapping[str, Any]]) -> None:
    """Reject forbidden keys or non-allowed fields in any history turn."""
    for i, turn in enumerate(history):
        _guard(turn, f"conversation_history[{i}]")
        unexpected = set(turn) - set(ALLOWED_HISTORY_FIELDS)
        if unexpected:
            raise ValueError(
                f"conversation_history[{i}] contains non-allowed fields "
                f"{sorted(unexpected)}; allowed: {ALLOWED_HISTORY_FIELDS}"
            )


def build_prompt(
    *,
    subject: str,
    redacted_student_text: str,
    curriculum_chunks: Sequence[Mapping[str, Any]],
    knowledge_state_summary: str = "",
    profile_note: Mapping[str, Any] | None = None,
    conversation_history: Sequence[Mapping[str, Any]] = (),
    explanation_method: str | None = None,
    pending_understanding_check: Mapping[str, Any] | None = None,
) -> BuiltPrompt:
    """Assemble the tutoring prompt from named fields only.

    - ``redacted_student_text`` MUST have passed redaction.redact() —
      required for ALL student text, typed chat included, not just Stage 2
      OCR output.
    - ``profile_note`` may contain only ALLOWED_PROFILE_FIELDS.
    - ``conversation_history`` may contain only ALLOWED_HISTORY_FIELDS per
      turn (``role``, ``text``); truncated to the last MAX_HISTORY_TURNS.
    - ``explanation_method`` must be one of EXPLANATION_METHODS (see
      student_state/explanation_method.py) or None — renders as an
      EXPLANATION APPROACH instruction line.
    - ``pending_understanding_check``, when given, may contain only
      ALLOWED_UNDERSTANDING_CHECK_FIELDS (``concept_label``) and adds an
      instruction asking the LLM to end its reply with a trailing
      ``[[UNDERSTANDING: yes|no]]`` marker — omitted entirely when None,
      so no marker is ever requested on turns where it wouldn't mean
      anything.
    """
    if explanation_method is not None and explanation_method not in EXPLANATION_METHODS:
        raise ValueError(
            f"Unknown explanation_method {explanation_method!r}; "
            f"must be one of {EXPLANATION_METHODS} or None."
        )

    understanding_check = dict(pending_understanding_check or {})
    _guard(understanding_check, "pending_understanding_check")
    unexpected_uc = set(understanding_check) - set(ALLOWED_UNDERSTANDING_CHECK_FIELDS)
    if unexpected_uc:
        raise ValueError(
            f"pending_understanding_check contains non-allowed fields "
            f"{sorted(unexpected_uc)}; allowed: {ALLOWED_UNDERSTANDING_CHECK_FIELDS}"
        )
    profile_note = dict(profile_note or {})
    _guard(profile_note, "profile_note")
    unexpected = set(profile_note) - set(ALLOWED_PROFILE_FIELDS)
    if unexpected:
        raise ValueError(
            f"profile_note contains non-allowed fields {sorted(unexpected)}; "
            f"allowed: {ALLOWED_PROFILE_FIELDS}"
        )

    history = list(conversation_history)[-MAX_HISTORY_TURNS:]
    _guard_history(history)

    doc_ids: list[str] = []
    context_lines: list[str] = []
    for i, chunk in enumerate(curriculum_chunks, start=1):
        _guard(chunk, f"curriculum_chunk[{i}]")  # defensive — should be clean
        did = str(chunk.get("doc_id") or chunk.get("id") or f"chunk-{i}")
        doc_ids.append(did)
        tier = chunk.get("provenance_tier", "?")
        content = chunk.get("content", "")
        if len(content) > MAX_CHUNK_CHARS:
            content = content[:MAX_CHUNK_CHARS] + " …[truncated]"
        context_lines.append(f"[{i} | {tier}] {content}")

    history_lines = [f"[{turn['role']}]: {turn['text']}" for turn in history]

    user = (
        f"SUBJECT: {subject}\n\n"
        f"CONTEXT (curriculum extracts):\n" + "\n\n".join(context_lines) + "\n\n"
        f"STUDENT'S CURRENT STANDING (summary):\n"
        f"{knowledge_state_summary or 'No prior record for this topic.'}\n\n"
        + (
            f"TEACHING NOTE: {profile_note['scaffolding_note']}\n\n"
            if profile_note.get("scaffolding_note")
            else ""
        )
        + (
            f"EXPLANATION APPROACH: explain this using "
            f"{METHOD_LABELS[explanation_method]}.\n\n"
            if explanation_method is not None
            else ""
        )
        + (
            f"PRIOR CONVERSATION (most recent last):\n"
            + "\n".join(history_lines) + "\n\n"
            if history_lines
            else ""
        )
        + f"STUDENT'S WORK (transcribed, redacted):\n{redacted_student_text}\n"
        + (
            "\nAfter your reply, judge whether the student's work above "
            f"demonstrates correct understanding of {understanding_check['concept_label']!r} "
            "(the concept covered by the explanation you gave last turn). "
            "End your response with a final line containing nothing else:\n"
            "[[UNDERSTANDING: yes]] or [[UNDERSTANDING: no]]\n"
            "That marker line must be the very last thing in your response."
            if understanding_check.get("concept_label")
            else ""
        )
    )

    return BuiltPrompt(
        system=SYSTEM_PROMPT,
        user=user,
        chunk_doc_ids=doc_ids,
        attributions=build_attributions(curriculum_chunks),
    )

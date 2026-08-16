"""Explicit, auditable prompt construction — the privacy boundary in code.

PROVENANCE — NEW, and a deliberate CORRECTION of the helpdesk pattern.
The helpdesk orchestrator f-stringed its entire raw context dict into the
prompt (``Raw context: {context}``). Harmless for an IT ticket; for
Stage 3 that dict would carry the student identifier, Stage 1 residuals
and potentially support-need indicators straight to a cloud LLM —
contradicting the data-protection architecture argued in Chapter 2
(Stage 2 exists as a local privacy boundary so that only redacted
extracted text crosses to the cloud).

DESIGN RULE: every field that reaches the prompt is named in the function
signature below. Nothing is interpolated wholesale. ``_guard`` rejects any
value containing a forbidden key, so a future refactor cannot quietly
reintroduce the helpdesk pattern.

DONE (2026-08-14): explanation-method selection wired in — two new
optional, named, guarded fields, ``explanation_method`` and
``pending_understanding_check`` (see
``student_state/explanation_method.py`` and
``docs/design/stage3-explanation-method-design.md``). The latter asks
the LLM to end its reply with a trailing ``[[UNDERSTANDING: yes|no]]``
marker — same one-call, marker-then-strip pattern already used by
``tutor/diagnostic.py``'s ``[[MASTERY_SCORE: x]]``, chosen specifically
to avoid a second LLM call on every ordinary tutoring turn. Parsing that
marker back out is ``student_state.explanation_method.
parse_understanding_marker`` — a response-parsing concern kept with the
module that owns the outcome vocabulary, not here.

DONE (2026-08-15): the pedagogy instruction set, response-format
guidance, and a token/character budget for retrieved chunks are all
real now — see ``SYSTEM_PROMPT`` and ``MAX_CHUNK_CHARS`` below.
Grounded in VanLehn (2011), already cited in Chapter 2 as the
effectiveness benchmark: step-based tutoring (feedback/hints at each
step of a multi-step problem) outperforms answer-only tutoring, and
hint-before-answer outperforms stating the answer outright. Both are now
explicit instructions, not incidental LLM style — this matters for the
expert-review rubric (the SENCO reviewer needs a stated expectation to
score `clarity`/`curriculum_fit` against, not an arbitrary one). The
SYSTEM_PROMPT default (guide-before-tell) is worded to defer to a
per-turn ``explanation_method`` instruction when one is given — e.g.
``worked_example`` deliberately does the opposite (answer shown first)
and should win when Thompson sampling picked it. The
"never signal a level drop when foundation content is blended" rule
(see docs/design/stage3-curriculum-retrieval-design.md) is now baked
into SYSTEM_PROMPT too, even though the deliberate auto-trigger isn't
built yet — live evaluation on 2026-08-15 showed foundation chunks CAN
already surface via ordinary retrieval with no explicit filter (see
README's "Evaluation instrument" section), so this already matters
today, not just once the trigger exists.

DONE (2026-08-16): CC attribution — see ``BuiltPrompt.attributions``,
populated by ``tutor/attribution.py::build_attributions``. Real
human-readable citations (title, source, licence, both linked) now flow
``build_prompt`` -> ``chat_session.py`` -> stored per-message in
``conversations.db`` -> ``api/chat.py`` -> the frontend's `MessageBubble`
— replacing what used to be a raw dump of internal `chunk_doc_ids`. See
README's "CC attribution" section for the full story, including a real
licence-correction bug (both connectors had the wrong licence hardcoded)
found immediately before building this.

TODO:
    [ ] Finalise ALLOWED_PROFILE_FIELDS once the Stage 1 export schema and
        the granularity decision are settled (see profiles/stage1_loader.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..student_state.explanation_method import EXPLANATION_METHODS, METHOD_LABELS
from .attribution import build_attributions

# Fields that must NEVER appear in prompt inputs. Extend as the Stage 1
# schema firms up. Checked case-insensitively as substrings of keys.
FORBIDDEN_KEY_FRAGMENTS = (
    "student_id",
    "name",
    "dob",
    "date_of_birth",
    "upn",
    "residual",        # raw Stage 1 model output — category only, if anything
    "sen",             # any support-need field
    "support_need",
    "ehcp",
    "diagnosis",
)

# The only profile-derived content permitted into a prompt (placeholder —
# see TODO). Coarse category text, not model internals.
ALLOWED_PROFILE_FIELDS = ("scaffolding_note",)

# Conversation history: bounded turn window and the only allowed shape per
# turn, guarded the same way as profile_note/chunks (see DESIGN RULE above).
MAX_HISTORY_TURNS = 6
ALLOWED_HISTORY_FIELDS = ("role", "text")

# See DONE note above — explanation-method selection.
ALLOWED_UNDERSTANDING_CHECK_FIELDS = ("concept_label",)

# Per-chunk character cap for CONTEXT — see DONE note above. Calibrated
# against real ingested chunk lengths (Isaac Science / Ada CS sections),
# checked directly rather than guessed: observed range 222-6413 chars,
# median ~1163. 2000 keeps the large majority of real sections intact
# while reining in the small number of outliers (several observed over
# 3000, one at 6413) that would otherwise let one chunk crowd out the
# other top_k results in the prompt.
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

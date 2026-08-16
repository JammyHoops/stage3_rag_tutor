"""Typed-chat turn handler — parallel to, not a replacement for, session.py.

PROVENANCE — NEW. ``tutor/session.py::run_turn`` is file-handoff shaped (it
takes a ``Submission`` produced by the Stage 2 MATLAB bridge). It has no
notion of an ongoing conversation. This module adds that: a chat turn
belongs to a persistent ``conversations`` thread (see
``conversations/store.py``) keyed by (student, subject, topic) and carries a
bounded window of prior turns into the prompt as ``conversation_history``
(see ``tutor/prompt_template.py``).

Same fail-closed guarantee as ``run_turn``: ``redaction.redact()`` is called
on every student message before anything else happens, and is expected to
raise ``NotImplementedError`` until redaction is implemented — this module
does not work around that, it inherits it.

DONE (2026-08-13): the mastery update rule is chosen (see
student_state/store.py's DECISION note) and IS wired in here now, but
only through the diagnostic mechanism (``start_diagnostic`` /
``_run_diagnostic_answer_turn``) — normal tutoring turns still don't call
``record_observation`` (confirmed with the user: mastery is diagnostic-
seeded, not continuously re-graded during ordinary tutoring). See
``tutor/diagnostic.py`` for the question-asking/grading mechanism.

DONE (2026-08-14): explanation-method selection (see
``student_state/explanation_method.py`` and
``docs/design/stage3-explanation-method-design.md``) is wired into the
NORMAL-tutoring branch only (never the diagnostic branch — separate
concern: method selection is about *how* to explain, the diagnostic is a
baseline assessment). Each normal turn, IF the top retrieved curriculum
chunk carries a ``concept_id`` (i.e. real curriculum content exists for
this subject): a method is Thompson-sampled and logged as a pending
interaction, and — if last turn's pending interaction was about the SAME
concept_id — the single tutoring LLM call also grades whether the
student's just-submitted answer demonstrated understanding (trailing
``[[UNDERSTANDING: yes|no]]`` marker, stripped before display). Subjects
with no curriculum content (mathematics/english) never resolve a
concept_id, so this is a clean no-op there — same graceful degradation
as the rest of context_builder.py.

DONE (2026-08-14): the empty-answer failure path is resolved — see
``llm/client.py``'s ``LLMGenerationError``. ``generate`` now raises on
hard failure instead of returning ``""``, so a failed call here
propagates straight out of ``start_diagnostic`` /
``_run_diagnostic_answer_turn`` / ``run_chat_turn`` without this module
needing to check anything — no message gets persisted, no diagnostic
progress advances, no method interaction gets logged, for a turn that
never actually produced an answer. ``api/chat.py`` is where it's finally
caught and turned into a 503.

DONE (2026-08-16): CC attribution wired through — ``prompt.attributions``
(see ``tutor/attribution.py``) is now passed to every real
``add_message(role="tutor", ...)`` call site, including the diagnostic
ones (diagnostic questions are grounded in the same licensed content and
carry the same obligation, previously overlooked). Stored once per
message alongside ``chunk_doc_ids``, not re-derived on read.

DONE (2026-08-16): real Stage 1 wiring, cold-start only —
``start_diagnostic`` now optionally takes ``student_id``/``profiles`` and
uses them ONCE, at the one genuinely cold-start moment (see
``tutor/context_builder.py``'s module docstring for why that's here and
not the normal-tutoring path): a one-time diagnostic-opening TEACHING
NOTE (``profile_to_note``) and a one-time mastery prior written before
the first real observation (``attainment_band_to_prior`` +
``student_state/store.py::seed_mastery_prior``). ``run_chat_turn`` no
longer takes a ``profiles`` parameter at all — its only use was passing
through to ``build_context``, which no longer touches Stage 1 data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..conversations.store import (
    add_message,
    list_messages,
    recent_messages,
    set_diagnostic_progress,
    touch_conversation,
)
from ..llm.client import LLMClient, get_client
from ..profiles.stage1_loader import get_profile
from ..redaction import redact
from ..retriever.search import search_kb
from ..student_state.explanation_method import (
    get_pending_interaction,
    log_interaction,
    parse_understanding_marker,
    record_understanding,
    select_method,
)
from ..student_state.store import record_observation, seed_mastery_prior
from ..taxonomy.topics import get_topic
from .context_builder import attainment_band_to_prior, build_context, profile_to_note
from .diagnostic import (
    QUESTION_COUNT,
    build_grading_prompt,
    build_opening_prompt,
    parse_graded_response,
)
from .prompt_template import build_prompt


@dataclass
class ChatTurnResponse:
    answer: str
    chunk_doc_ids: list[str]
    attributions: list[dict[str, str]]
    subject: str
    conversation_id: int
    tutor_message_id: int


def _topic_label(subject: str, topic: str) -> str:
    """Best-effort human-readable label for prompt text — falls back to
    the raw topic id if the taxonomy lookup misses (should not happen for
    a topic already validated at conversation-creation time, but this is
    prompt text, not a security boundary, so degrade gracefully)."""
    topic_obj = get_topic(subject, topic)
    return topic_obj.label if topic_obj else topic


def start_diagnostic(
    conversation_id: int,
    subject: str,
    topic: str,
    student_id: str | None = None,
    profiles: dict[str, dict[str, Any]] | None = None,
    llm: LLMClient | None = None,
) -> None:
    """Generate and store the opening question of a diagnostic round.

    Called synchronously right after a conversation is created, or when a
    fresh round is explicitly requested (see api/chat.py's /reassess
    endpoint) — the tutor speaks first, with no preceding student message.

    ``student_id``/``profiles`` are optional and should ONLY be passed for
    a genuinely first-ever diagnostic round (api/chat.py's
    ``post_conversation`` — never ``/reassess``, deliberately, since a
    re-check means the student already has tutoring history and this is
    no longer "cold start" — see tutor/context_builder.py's module
    docstring). When given, this is the one place Stage 1 data is allowed
    to touch anything: a one-time TEACHING NOTE in the opening prompt
    (``profile_to_note``) and a one-time mastery prior written BEFORE the
    first real observation (``attainment_band_to_prior`` +
    ``seed_mastery_prior``). Omitted (the default) degrades cleanly to
    the prior no-Stage-1 behaviour — no note, no seed.
    """
    llm = llm or get_client()
    topic_label = _topic_label(subject, topic)
    chunks = search_kb(topic_label, subject=subject, topic=topic, top_k=4)

    profile = get_profile(student_id, subject, profiles) if student_id and profiles else None
    prior = attainment_band_to_prior(profile)
    if prior is not None:
        seed_mastery_prior(student_id, subject, topic, prior)

    prompt = build_opening_prompt(subject, topic_label, chunks, profile_note=profile_to_note(profile))

    answer = llm.generate(prompt.user, system=prompt.system)
    add_message(
        conversation_id,
        role="tutor",
        content=answer,
        chunk_doc_ids=prompt.chunk_doc_ids,
        attributions=prompt.attributions,
    )
    set_diagnostic_progress(conversation_id, questions_asked=1, status="pending")


def _run_diagnostic_answer_turn(
    student_id: str,
    subject: str,
    topic: str,
    conversation_id: int,
    safe_text: str,
    questions_asked: int,
    llm: LLMClient,
) -> ChatTurnResponse:
    """Grade the student's answer to the most recently asked diagnostic
    question, then either ask the next one or hand off to normal tutoring.
    See tutor/diagnostic.py's module docstring for the mechanism."""
    topic_label = _topic_label(subject, topic)

    # This round's questions are always the most recent `questions_asked`
    # tutor messages — a diagnostic round is contiguous at the tail of the
    # thread (never interleaved with normal tutoring), whether this is a
    # brand-new thread or a "Re-check my understanding" round appended
    # after older tutoring history.
    tutor_messages = [m for m in list_messages(conversation_id) if m["role"] == "tutor"]
    prior_questions = [m["content"] for m in tutor_messages[-questions_asked:]]

    is_final = questions_asked >= QUESTION_COUNT
    chunks = search_kb(topic_label, subject=subject, topic=topic, top_k=4)
    prompt = build_grading_prompt(
        subject=subject,
        topic=topic_label,
        curriculum_chunks=chunks,
        prior_questions=prior_questions,
        student_answer=safe_text,
        is_final=is_final,
    )

    raw = llm.generate(prompt.user, system=prompt.system)
    visible_text, score = parse_graded_response(raw)

    add_message(conversation_id, role="student", content=safe_text)
    tutor_message_id = add_message(
        conversation_id,
        role="tutor",
        content=visible_text,
        chunk_doc_ids=prompt.chunk_doc_ids,
        attributions=prompt.attributions,
    )
    touch_conversation(conversation_id)

    if score is not None:
        record_observation(
            student_id=student_id,
            subject=subject,
            topic=topic,
            outcome=score,
            source="diagnostic",
        )
    # else: marker was missing/malformed — deliberately not recording a
    # guessed observation, see tutor/diagnostic.py::parse_graded_response.

    if is_final:
        set_diagnostic_progress(conversation_id, questions_asked=questions_asked, status="done")
    else:
        set_diagnostic_progress(
            conversation_id, questions_asked=questions_asked + 1, status="pending"
        )

    return ChatTurnResponse(
        answer=visible_text,
        chunk_doc_ids=prompt.chunk_doc_ids,
        attributions=prompt.attributions,
        subject=subject,
        conversation_id=conversation_id,
        tutor_message_id=tutor_message_id,
    )


def run_chat_turn(
    student_id: str,
    subject: str,
    topic: str,
    conversation_id: int,
    student_message: str,
    diagnostic_status: str = "done",
    diagnostic_questions_asked: int = 0,
    llm: LLMClient | None = None,
    history_window: int = 6,
) -> ChatTurnResponse:
    """One chat turn: typed student message in → grounded response out.

    Pipeline: redact → branch on diagnostic phase → (diagnostic: grade +
    next/wrap-up) or (normal: fetch bounded history → build three-source
    context → guarded prompt → LLM) → persist both turns.

    ``diagnostic_status``/``diagnostic_questions_asked`` are the
    conversation's own stored diagnostic progress (see
    conversations/store.py) — defaults assume "not in a diagnostic round"
    for callers that don't track it, but the real API layer always passes
    the conversation's actual values.

    ``topic`` is the conversation's own stored topic (see
    conversations/store.py) — passed through to retrieval so curriculum
    chunks tagged with the matching topic actually surface. See
    tutor/context_builder.py's docstring for the vocabulary-alignment note.
    """
    llm = llm or get_client()

    safe_text = redact(student_message)

    if diagnostic_status == "pending":
        return _run_diagnostic_answer_turn(
            student_id=student_id,
            subject=subject,
            topic=topic,
            conversation_id=conversation_id,
            safe_text=safe_text,
            questions_asked=diagnostic_questions_asked,
            llm=llm,
        )

    history_rows = recent_messages(conversation_id, limit=history_window)
    history = [{"role": row["role"], "text": row["content"]} for row in history_rows]

    bundle = build_context(
        student_id=student_id,
        subject=subject,
        query_text=safe_text,
        topic=topic,
    )

    # Explanation-method selection — see module docstring "DONE
    # (2026-08-14)". concept_id comes from the top retrieved chunk; no
    # chunk / no concept_id (e.g. mathematics/english, no curriculum
    # ingested) means this whole mechanism is a clean no-op this turn.
    top_chunk = bundle.curriculum_chunks[0] if bundle.curriculum_chunks else None
    concept_id = top_chunk.get("concept_id") if top_chunk else None

    explanation_method = None
    pending_check = None
    pending = get_pending_interaction(conversation_id)

    if concept_id:
        explanation_method = select_method(student_id)
        if pending and pending["concept_id"] == concept_id:
            concept_label = top_chunk.get("section_title") or _topic_label(subject, topic)
            pending_check = {"concept_label": concept_label}

    prompt = build_prompt(
        subject=subject,
        redacted_student_text=safe_text,
        curriculum_chunks=bundle.curriculum_chunks,
        knowledge_state_summary=bundle.knowledge_state_summary,
        profile_note=bundle.profile_note,
        conversation_history=history,
        explanation_method=explanation_method,
        pending_understanding_check=pending_check,
    )

    raw = llm.generate(prompt.user, system=prompt.system)
    # Empty-answer path resolved generically — see module docstring's
    # DONE (2026-08-14) note. A hard failure raises past this point.
    answer, understood = parse_understanding_marker(raw)

    if pending_check is not None and understood is not None:
        record_understanding(
            interaction_id=pending["id"],
            student_id=student_id,
            method=pending["method"],
            success=understood,
        )
    if concept_id:
        log_interaction(
            student_id=student_id,
            subject=subject,
            conversation_id=conversation_id,
            concept_id=concept_id,
            method=explanation_method,
        )

    add_message(conversation_id, role="student", content=safe_text)
    tutor_message_id = add_message(
        conversation_id,
        role="tutor",
        content=answer,
        chunk_doc_ids=prompt.chunk_doc_ids,
        attributions=prompt.attributions,
    )
    touch_conversation(conversation_id)

    # NOT calling student_state.record_observation here (see module docstring).

    return ChatTurnResponse(
        answer=answer,
        chunk_doc_ids=prompt.chunk_doc_ids,
        attributions=prompt.attributions,
        subject=subject,
        conversation_id=conversation_id,
        tutor_message_id=tutor_message_id,
    )

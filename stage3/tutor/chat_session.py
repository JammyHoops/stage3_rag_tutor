"""Typed-chat turn handler — parallel to, not a replacement for, session.py.

PROVENANCE — NEW. ``tutor/session.py::run_turn`` is file-handoff shaped (it
takes a ``Submission`` produced by the Stage 2 MATLAB bridge) with no
notion of an ongoing conversation. This module adds that: a chat turn
belongs to a persistent ``conversations`` thread (``conversations/
store.py``) keyed by (student, subject, topic), and carries a bounded
window of prior turns into the prompt as ``conversation_history``.

Mastery is only updated via the diagnostic mechanism
(``start_diagnostic`` / ``_run_diagnostic_answer_turn``); normal tutoring
turns never call ``record_observation`` directly — see
``tutor/diagnostic.py``.

Explanation-method selection (``student_state/explanation_method.py``) is
wired into the normal-tutoring branch only. If the top retrieved
curriculum chunk carries a ``concept_id``, a method is Thompson-sampled
each normal turn and logged as a pending interaction; if the previous
turn's pending interaction was about the same concept, the same LLM call
also grades whether the student's answer demonstrated understanding (a
trailing ``[[UNDERSTANDING: yes|no]]`` marker, stripped before display).
A subject with no curriculum content never resolves a concept_id, so this
degrades to a no-op there.

A hard LLM failure (``llm/client.py``'s ``LLMGenerationError``) propagates
straight out of every entry point here without this module needing to
check anything — no message gets persisted, no progress advances, for a
turn that never produced an answer. ``api/chat.py`` catches it and turns
it into a 503.

``prompt.attributions`` (``tutor/attribution.py``) is passed to every
``add_message(role="tutor", ...)`` call site, diagnostic turns included.

``start_diagnostic`` optionally takes ``student_id``/``profiles`` and uses
them once, at the one genuinely cold-start moment: a one-time
diagnostic-opening teaching note (``profile_to_note``) and a one-time
mastery prior (``attainment_band_to_prior`` +
``student_state/store.py::seed_mastery_prior``). See
``tutor/context_builder.py``'s docstring for why it lives here and not
the normal-tutoring path.
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
    the raw topic id if the taxonomy lookup misses."""
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
    fresh round is explicitly requested (api/chat.py's /reassess endpoint)
    — the tutor speaks first, with no preceding student message.

    ``student_id``/``profiles`` should only be passed for a genuinely
    first-ever diagnostic round (api/chat.py's ``post_conversation``,
    never ``/reassess``): the one place Stage 1 data is allowed to touch
    anything, a one-time teaching note (``profile_to_note``) and a
    one-time mastery prior (``attainment_band_to_prior`` +
    ``seed_mastery_prior``). Omitted, the default, degrades cleanly to no
    note and no seed.
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

    # concept_id comes from the top retrieved chunk; no chunk / no
    # concept_id means explanation-method selection is a clean no-op.
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
        conversation_history=history,
        explanation_method=explanation_method,
        pending_understanding_check=pending_check,
    )

    raw = llm.generate(prompt.user, system=prompt.system)
    # A hard LLM failure raises past this point; see llm/client.py.
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

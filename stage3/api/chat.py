"""Chat/conversation endpoints — the API surface for a Claude-Projects-style UI.

PROVENANCE — NEW. Split into its own router (rather than growing
``api/main.py`` further) since this adds six routes on top of the existing
three. Subject = project, topic = chat within that project, matching the
taxonomy in ``stage3/taxonomy/topics.py`` and the persistence in
``stage3/conversations/store.py``.

TODO:
    [ ] Auth: none exists or is planned (local-only research prototype,
        student_id passed explicitly per request — see api/main.py docstring).

DONE: POST /conversations/{id}/messages no longer 501s for normal
tutoring — redact() and summarise_state() are both implemented now (see
tutor/chat_session.py, tutor/context_builder.py). The 501 branch is kept
as a general safety net for any future NotImplementedError, not because
one is currently expected — profile_to_note (2026-08-16) was the last
one and is real now too, see tutor/context_builder.py.

DONE (2026-08-14): every endpoint that can trigger an LLM call
(POST /conversations, /reassess, /messages) now catches
``llm.client.LLMGenerationError`` and returns 503, rather than letting a
hard LLM failure silently produce a blank persisted tutor message (see
that module's docstring — caught directly during live testing, not
hypothetical). The frontend already had a generic non-501 error path
(`ChatThread`'s `sendState === "error"`, `ConversationList`'s
`createError`, `handleReassess`'s catch) built for exactly this shape of
failure, so no frontend change was needed. ``post_conversation`` also
now retries the opening diagnostic question on a re-fetch of an existing
conversation that never got one (0 questions asked, still 'pending') —
without this, a first-creation LLM failure would leave that thread
permanently stuck, since ``get_or_create_conversation`` only reports
``created=True`` once.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..conversations.store import (
    get_conversation,
    get_or_create_conversation,
    list_conversations,
    list_messages,
    reset_diagnostic,
)
from ..llm.client import LLMGenerationError
from ..taxonomy.topics import get_topic, list_subjects, list_topics
from ..tutor.chat_session import run_chat_turn, start_diagnostic

# Friendly, fixed client-facing message — deliberately NOT the raw
# provider exception text (str(e)), which could carry internal
# provider/quota details not meant for the frontend. Full detail is
# already in server logs via llm/client.py's logger.error.
_LLM_UNAVAILABLE_DETAIL = (
    "The tutor is temporarily unavailable (the language model provider "
    "failed after retries). Please try again in a moment."
)

router = APIRouter()


class ConversationCreate(BaseModel):
    student_id: str
    subject: str
    topic: str


class MessageCreate(BaseModel):
    student_id: str
    text: str


@router.get("/subjects")
def get_subjects():
    return {"subjects": list_subjects()}


@router.get("/subjects/{subject}/topics")
def get_subject_topics(subject: str):
    topics = list_topics(subject)
    if not topics:
        raise HTTPException(status_code=404, detail=f"Unknown subject {subject!r}.")
    return {"subject": subject, "topics": [t.__dict__ for t in topics]}


@router.get("/conversations")
def get_conversations(student_id: str, subject: Optional[str] = None):
    return {"conversations": list_conversations(student_id, subject=subject)}


@router.post("/conversations")
def post_conversation(body: ConversationCreate, request: Request):
    """Get-or-create: idempotent per (student, subject, topic) — see
    conversations/store.py's module docstring. Safe to call every time a
    topic is clicked in the UI; never creates a duplicate thread.

    On a genuine first creation, synchronously starts the diagnostic
    round (tutor speaks first — see tutor/chat_session.py::
    start_diagnostic) so the opening question is already there by the
    time the frontend fetches messages. This is the ONLY call site that
    passes student_id/profiles into start_diagnostic — see that
    function's docstring for why: this is the one genuinely cold-start
    moment Stage 1 data is allowed to touch anything.

    Also retries the opening question on an EXISTING conversation that
    never actually got one (0 questions asked, still 'pending') — the
    only way that state can persist is a previous LLMGenerationError
    (see module docstring), and without this retry the thread would be
    stuck forever, since `created` only reports True once.
    """
    if get_topic(body.subject, body.topic) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown topic {body.topic!r} for subject {body.subject!r}.",
        )
    conversation_id, created = get_or_create_conversation(
        body.student_id, body.subject, body.topic
    )
    conversation = get_conversation(conversation_id)
    needs_opening_question = created or (
        conversation["diagnostic_status"] == "pending"
        and conversation["diagnostic_questions_asked"] == 0
    )
    if needs_opening_question:
        try:
            start_diagnostic(
                conversation_id,
                body.subject,
                body.topic,
                student_id=body.student_id,
                profiles=request.app.state.profiles,
            )
        except LLMGenerationError:
            raise HTTPException(status_code=503, detail=_LLM_UNAVAILABLE_DETAIL)
        conversation = get_conversation(conversation_id)
    return conversation


@router.post("/conversations/{conversation_id}/reassess")
def post_conversation_reassess(conversation_id: int):
    """Explicit "Re-check my understanding" — starts a fresh diagnostic
    round on an EXISTING thread (not a new conversation), per the
    one-thread-per-topic decision. See conversations/store.py::
    reset_diagnostic and tutor/chat_session.py::start_diagnostic.

    Deliberately does NOT pass student_id/profiles to start_diagnostic —
    a re-check means the student already has tutoring history, so this
    is no longer "cold start" in the sense Stage 1 data is meant for
    (see start_diagnostic's own docstring). Not a missed wiring spot.
    """
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    reset_diagnostic(conversation_id)
    try:
        start_diagnostic(conversation_id, conversation["subject"], conversation["topic"])
    except LLMGenerationError:
        # reset_diagnostic already ran, so the conversation is left at
        # (0 questions asked, 'pending') — cleanly retryable by clicking
        # the button again, no extra recovery logic needed here.
        raise HTTPException(status_code=503, detail=_LLM_UNAVAILABLE_DETAIL)
    return get_conversation(conversation_id)


@router.get("/conversations/{conversation_id}")
def get_conversation_by_id(conversation_id: int):
    """Single-conversation fetch — used by the frontend to refresh
    diagnostic_status/diagnostic_questions_asked after each turn, since
    those change over the life of a thread (unlike the mostly-static
    fields returned by the list endpoint's cached view)."""
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: int):
    if get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"messages": list_messages(conversation_id)}


@router.post("/conversations/{conversation_id}/messages")
def post_conversation_message(conversation_id: int, body: MessageCreate):
    conversation = get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    try:
        result = run_chat_turn(
            student_id=body.student_id,
            subject=conversation["subject"],
            topic=conversation["topic"],
            conversation_id=conversation_id,
            student_message=body.text,
            diagnostic_status=conversation["diagnostic_status"],
            diagnostic_questions_asked=conversation["diagnostic_questions_asked"],
        )
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except LLMGenerationError:
        raise HTTPException(status_code=503, detail=_LLM_UNAVAILABLE_DETAIL)

    return {
        "answer": result.answer,
        "chunk_doc_ids": result.chunk_doc_ids,
        "attributions": result.attributions,
        "tutor_message_id": result.tutor_message_id,
    }

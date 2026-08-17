"""FastAPI surface for Stage 3.

PROVENANCE — /health and /feedback KEPT (adapted) from AI_IT_Helpdesk; the
duplicate RAG API stack was removed rather than merged. /feedback is the
write side of the retrieval feedback loop (counters read back by the
reranker) — during expert evaluation, a reviewer's chunk-relevance
judgements can be committed through it.

/subjects, /subjects/{subject}/topics, and /conversations* (chat.py
router) are NEW — see stage3/api/chat.py for the conversation/chat
backend that supports a Claude-Projects-style UI. /students* (students.py
router) are also NEW — a student directory (derived from who has
conversations; no real login exists) and a mastery read-through.

/tutor below is superseded, not pending: the conversation/chat backend
(chat.py's router) is the live tutoring path the frontend actually calls.
/tutor was an earlier single-shot sketch before the conversational design
was settled — left as a deliberate 501 rather than removed, in case a
non-conversational integration ever needs one.

No student-facing deployment is in scope — local-only for the project
(bind 127.0.0.1).
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..conversations.store import init_db as init_conversations_db
from ..profiles.stage1_loader import load_profiles
from ..student_state.explanation_method import init_db as init_explanation_method_db
from ..student_state.store import init_db as init_student_state_db
from ..vectordb.store import update_feedback
from .chat import router as chat_router
from .students import router as students_router

app = FastAPI(title="Stage 3 Tutor API")

# Local-only dev CORS: allows the Vite dev server (default port) to call this
# API directly. Explicit origin list, not "*" — costs nothing and documents
# intent. Add another origin here if Vite picks a different port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(chat_router)
app.include_router(students_router)


@app.on_event("startup")
def _startup() -> None:
    init_conversations_db()
    init_student_state_db()
    init_explanation_method_db()
    app.state.profiles = load_profiles()


class FeedbackEvent(BaseModel):
    answer_id: str
    feedback: str = Field(..., pattern=r"^(positive|negative)$")
    doc_ids: List[str]
    timestamp: Optional[str] = None


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/feedback")
def feedback(evt: FeedbackEvent):
    updated = update_feedback(
        doc_ids=evt.doc_ids,
        feedback=evt.feedback,
        answer_id=evt.answer_id,
        timestamp=evt.timestamp,
    )
    return {"ok": True, "updated": updated}


@app.post("/tutor")
def tutor():
    # RETIRED — see module docstring. Superseded by chat.py's conversation
    # endpoints, not pending implementation.
    raise HTTPException(status_code=501, detail="Tutor endpoint superseded by /conversations (chat.py).")

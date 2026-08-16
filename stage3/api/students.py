"""Student-directory + mastery-read endpoints.

PROVENANCE — NEW (2026-08-16, usability pass). Split into its own router
rather than folded into chat.py or main.py, since it wraps TWO different
modules/schemas that are each deliberately kept separate elsewhere
(conversations/store.py vs. student_state/store.py — see the latter's
module docstring for why they live in different SQLite files) — mirrors
why chat.py itself was split out of main.py.

No login/registry exists anywhere in this prototype by design (student_id
is a pseudonymous, freely-typed identifier — see api/main.py's module
docstring). ``GET /students`` is therefore NOT an authoritative roster —
it is "everyone who has ever started a conversation," which is the only
honest thing this system can report. It exists to power the frontend's
searchable student picker (components/StudentSelect) — search-assist, not
access control. A student typing an id that has never been seen before is
still valid and expected.

``GET /students/{id}/mastery`` is a thin read-through to
student_state/store.py::get_knowledge_state, which already returns
exactly the shape the frontend's mastery indicator needs
(student_id, subject, topic, estimate, n_obs, updated_at) — no new store
function needed for that half.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from ..conversations.store import list_student_ids
from ..student_state.store import get_knowledge_state

router = APIRouter()


@router.get("/students")
def get_students():
    return {"student_ids": list_student_ids()}


@router.get("/students/{student_id}/mastery")
def get_student_mastery(student_id: str, subject: Optional[str] = None):
    return {"mastery": get_knowledge_state(student_id, subject=subject)}

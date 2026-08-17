"""Student-directory + mastery-read endpoints.

PROVENANCE — NEW. Split into its own router since it wraps two different
modules/schemas kept separate elsewhere (conversations/store.py vs.
student_state/store.py).

No login/registry exists in this prototype by design; ``student_id`` is a
pseudonymous, freely-typed identifier. ``GET /students`` is therefore not
an authoritative roster — it's "everyone who has ever started a
conversation," powering the frontend's searchable student picker as
search-assist, not access control. A student typing an id that's never
been seen before is still valid and expected.

``GET /students/{id}/mastery`` is a thin read-through to
``student_state/store.py::get_knowledge_state``.
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

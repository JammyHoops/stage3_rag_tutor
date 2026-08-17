"""Three-source context fusion — the core new work of Stage 3.

PROVENANCE — NEW. The helpdesk retrieved from one collection and returned
one ranked list. Stage 3 fuses three sources with different semantics:

    1. curriculum content   -> semantic retrieval (reranked; kept layer)
    2. knowledge state      -> structured lookup, not embedding search
    3. Stage 1 profile      -> small structured record, injected directly

Only source 1 is genuinely a retrieval problem; treating 2 and 3 as
retrieval would be the wrong tool.

``summarise_state`` buckets each topic's mastery estimate into one short,
deterministic clause: >=0.75 "secure on", >=0.4 "developing understanding
of", else "still building the basics of".

``profile_to_note`` and ``attainment_band_to_prior`` map a Stage 1 profile
row to prompt/mastery content, but ``build_context`` below never calls
either — see docs/design/FINDINGS_AND_DECISIONS.md §5 for why (this call
site is structurally never a cold-start moment; the real one is
``chat_session.py::start_diagnostic``, which calls both directly). This
function therefore takes no ``profiles`` argument, and ``ContextBundle``
carries no ``profile_note`` field.

See docs/TODO.md for open items: query formulation, top_k/token budget,
and the foundation-tier trigger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..retriever.search import search_kb
from ..student_state.store import get_knowledge_state


@dataclass
class ContextBundle:
    curriculum_chunks: list[dict[str, Any]] = field(default_factory=list)
    knowledge_state_summary: str = ""


def summarise_state(rows: list[dict[str, Any]]) -> str:
    """Compact, deterministic textual summary of mastery rows for the prompt."""
    if not rows:
        return ""  # cold start: explicit empty, handled by the prompt template

    clauses = []
    for row in rows:
        estimate = row["estimate"]
        if estimate >= 0.75:
            level = "secure on"
        elif estimate >= 0.4:
            level = "developing understanding of"
        else:
            level = "still building the basics of"
        clauses.append(f"{level} {row['topic']} ({row['n_obs']} observation(s))")

    return "; ".join(clauses)


# Coarse, one-time diagnostic-opening tone note per flag_status — called
# from chat_session.py::start_diagnostic, not build_context below. Says
# nothing that would let the tutor signal a gap to the student.
_SCAFFOLDING_NOTES = {
    "confirmed": (
        "This student has a confirmed, documented attainment gap in this "
        "subject. Keep your opening check-in question especially gentle "
        "and low-pressure."
    ),
    "provisional": (
        "This student may have an attainment gap in this subject "
        "(provisional, not yet confirmed) — keep your opening check-in "
        "question approachable, without assuming a gap that might not "
        "be there."
    ),
}


def profile_to_note(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Map a Stage 1 profile row's ``flag_status`` to the single allowed
    prompt field. Emits only {'scaffolding_note': <coarse text>} or {} —
    ``None`` profile, ``flag_status == "none"``, and any unrecognised
    value all fail closed to {} (no note), never a guess.
    """
    if profile is None:
        return {}
    note = _SCAFFOLDING_NOTES.get(profile.get("flag_status"))
    return {"scaffolding_note": note} if note else {}


# Coarse mastery-prior mapping per attainment_band, chosen to land inside
# summarise_state's own bucket boundaries (0.4 / 0.75) so a seeded
# estimate reads consistently with the rest of the mastery scale. See
# student_state/store.py::seed_mastery_prior for how it gets written and
# fades as real evidence accumulates.
_ATTAINMENT_BAND_PRIORS = {
    "well_below": 0.15,
    "below": 0.3,
    "in_line": 0.55,
    "above": 0.8,
}


def attainment_band_to_prior(profile: dict[str, Any] | None) -> float | None:
    """Map a Stage 1 profile row's ``attainment_band`` to a starting
    mastery estimate. ``None`` for a missing profile or an unrecognised
    band — fail closed to no seed, never a guessed default. Independent
    of ``flag_status`` — attainment data exists (and is used) even for
    students with no flag at all.
    """
    if profile is None:
        return None
    return _ATTAINMENT_BAND_PRIORS.get(profile.get("attainment_band"))


def build_context(
    student_id: str,
    subject: str,
    query_text: str,
    topic: str | None = None,
    top_k: int = 4,
) -> ContextBundle:
    """Assemble the curriculum + knowledge-state context for one normal
    tutoring turn.

    ``student_id`` is used only for the knowledge-state lookup; it is
    never placed in the bundle contents.

    ``topic`` should be drawn from the same ``data/topics/<subject>.json``
    vocabulary that curriculum chunks are tagged against at ingest time —
    an arbitrary string will just silently match nothing.

    Does not touch Stage 1 profile data — see module docstring.
    """
    chunks = search_kb(query_text, top_k=top_k, subject=subject, topic=topic)
    state_rows = get_knowledge_state(student_id, subject=subject)

    return ContextBundle(
        curriculum_chunks=chunks,
        knowledge_state_summary=summarise_state(state_rows),
    )

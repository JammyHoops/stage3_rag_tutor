"""Three-source context fusion — the core new work of Stage 3.

PROVENANCE — NEW. The helpdesk retrieved from ONE collection and returned
ONE ranked list. Stage 3 fuses three sources with different semantics:

    1. curriculum content   → semantic retrieval (reranked — KEPT layer)
    2. knowledge state      → structured lookup, NOT embedding search
    3. Stage 1 profile      → small structured record, injected directly

Only source 1 is genuinely a retrieval problem; treating 2 and 3 as
retrieval would be the wrong tool. This module is where that argument
becomes code.

DONE: Knowledge-state summarisation (2026-08-13) — ``summarise_state``
buckets each topic's mastery estimate (from the EWMA rule in
``student_state/store.py``) into one short clause, deterministic and
reportable: ``>=0.75`` "secure on", ``>=0.4`` "developing understanding
of", else "still building the basics of". Mastery itself is only ever
seeded/updated by the LLM-graded diagnostic in ``tutor/diagnostic.py`` —
see that module and ``chat_session.py::start_diagnostic`` /
``_run_diagnostic_answer_turn``.

DONE (2026-08-16): Stage 1 profile handling — ``profile_to_note`` and
``attainment_band_to_prior`` are real now (see their own docstrings
below), built once a real schema landed (synthetic fixture, see
``profiles/stage1_loader.py``). BUT ``build_context`` below no longer
calls either of them, deliberately — checked directly before building
this: ``build_context`` is only ever invoked from ``chat_session.py::
run_chat_turn``'s NORMAL-turn branch, which is only reachable once a
topic's diagnostic has already completed (``diagnostic_status ==
"done"``) and already written real mastery data. By the time this
function ever runs, it's structurally never "cold start" for that topic
— so a profile-driven note here would just repeat forever, not guide a
first encounter (the actual bug this design avoids; see
docs/design/stage3-stage1-schema-requirements.md's originating
discussion). The genuinely cold-start moment is diagnostic START, not
here — see ``chat_session.py::start_diagnostic``, which calls
``profile_to_note``/``attainment_band_to_prior`` directly. This function
therefore no longer takes a ``profiles`` argument at all, and
``ContextBundle`` no longer carries a ``profile_note`` field —
``tutor/prompt_template.py``'s ``profile_note`` parameter and its
``ALLOWED_PROFILE_FIELDS`` guard are unchanged and still fully exercised,
just never called with a non-empty note from this module anymore.

TODO:
    [ ] Query formulation: what is the retrieval query — the raw student
        text, an extracted question, or text + weak-topic terms from the
        knowledge state? This is an experiment worth a subsection.
    [ ] top_k and token budget per source; interaction with chunk size.
    [ ] Foundation-tier trigger: a second, ADDITIVE `search_kb` call
        filtered to `difficulty_tier="foundation"`, fired only when BOTH a
        subject-specific Stage 1 signal AND an in-session
        prerequisite-failure signal hold (neither alone) — see
        docs/design/stage3-curriculum-retrieval-design.md. Blocked on the
        concept-granularity decision noted in student_state/store.py. A
        real per-subject Stage 1 signal exists now (``attainment_band`` —
        see ``profiles/stage1_loader.py``) but this trigger still isn't
        wired to read it.

DONE: `topic` is now threaded through to `search_kb` (previously accepted
by that function but never actually passed here) — see `tutor/
chat_session.py` and `api/chat.py` for where it originates (the
conversation's own stored topic, drawn from the same `data/topics/
<subject>.json` vocabulary that curriculum-chunk metadata is tagged with —
see connectors/isaac_science.py).
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
    """Compact, deterministic textual summary of mastery rows for the
    prompt — see module docstring "DONE" note for the bucketing rule.
    """
    if not rows:
        return ""  # cold start — explicit empty, handled by prompt template

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


# Coarse, one-time diagnostic-opening tone note per flag_status — see
# chat_session.py::start_diagnostic for where this is actually called
# (NOT from build_context below — see module docstring "DONE" note).
# Deliberately doesn't say anything that would let the tutor signal a
# gap to the student — matches prompt_template.py's SYSTEM_PROMPT's
# "never signal a level drop" rule, just applied to diagnostic framing
# instead of normal-tutoring content blending.
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
    prompt field. Emits ONLY {'scaffolding_note': <coarse text>} or {} —
    ``None`` profile, ``flag_status == "none"``, and any unrecognised
    value all fail closed to {} (no note), never a guess.
    """
    if profile is None:
        return {}
    note = _SCAFFOLDING_NOTES.get(profile.get("flag_status"))
    return {"scaffolding_note": note} if note else {}


# Coarse mastery-prior mapping per attainment_band — chosen to land
# inside summarise_state's own bucket boundaries (0.4 / 0.75) so a seeded
# estimate reads consistently with the rest of the mastery scale. See
# student_state/store.py::seed_mastery_prior for how this gets written,
# and why it fades rather than persists (real evidence blends in via the
# existing EWMA rule from the first real diagnostic answer onward).
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

    NOTE: ``student_id`` is used ONLY for the knowledge-state lookup; it
    is never placed in the bundle contents and the prompt guard would
    reject it anyway.

    ``topic`` should be drawn from the same ``data/topics/<subject>.json``
    vocabulary that curriculum chunks are tagged against at ingest time —
    passing an arbitrary string will just silently match nothing.

    Does NOT touch Stage 1 profile data — see module docstring "DONE
    (2026-08-16)" note for why that's handled at diagnostic-start instead.
    """
    chunks = search_kb(query_text, top_k=top_k, subject=subject, topic=topic)
    state_rows = get_knowledge_state(student_id, subject=subject)

    return ContextBundle(
        curriculum_chunks=chunks,
        knowledge_state_summary=summarise_state(state_rows),
    )

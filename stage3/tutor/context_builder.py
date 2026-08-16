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

TODO:
    [ ] Query formulation: what is the retrieval query — the raw student
        text, an extracted question, or text + weak-topic terms from the
        knowledge state? This is an experiment worth a subsection.
    [ ] top_k and token budget per source; interaction with chunk size.
    [ ] Profile → scaffolding_note mapping (the ONLY profile content the
        prompt guard admits): draft the wording, review with supervisor —
        it must be pedagogically useful without leaking model internals.
    [ ] Cold start behaviour when state/profile are empty (must degrade to
        a plain curriculum-grounded tutor, cleanly).
    [ ] Foundation-tier trigger: a second, ADDITIVE `search_kb` call
        filtered to `difficulty_tier="foundation"`, fired only when BOTH a
        subject-specific Stage 1 signal AND an in-session
        prerequisite-failure signal hold (neither alone) — see
        docs/design/stage3-curriculum-retrieval-design.md. Blocked on the
        concept-granularity decision noted in student_state/store.py.

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

from ..profiles.stage1_loader import get_profile
from ..retriever.search import search_kb
from ..student_state.store import get_knowledge_state


@dataclass
class ContextBundle:
    curriculum_chunks: list[dict[str, Any]] = field(default_factory=list)
    knowledge_state_summary: str = ""
    profile_note: dict[str, Any] = field(default_factory=dict)


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


def profile_to_note(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Map a Stage 1 profile row to the single allowed prompt field.

    TODO: implement once export schema + granularity decision are settled.
    Must emit ONLY {'scaffolding_note': <coarse text>} or {}.
    """
    if profile is None:
        return {}
    raise NotImplementedError(
        "Profile-to-note mapping not implemented — see TODO in context_builder.py"
    )


def build_context(
    student_id: str,
    subject: str,
    query_text: str,
    profiles: dict[str, dict[str, Any]],
    topic: str | None = None,
    top_k: int = 4,
) -> ContextBundle:
    """Assemble the three context sources for one tutoring turn.

    NOTE: ``student_id`` is used ONLY for local lookups (sources 2 and 3);
    it is never placed in the bundle contents and the prompt guard would
    reject it anyway.

    ``topic`` should be drawn from the same ``data/topics/<subject>.json``
    vocabulary that curriculum chunks are tagged against at ingest time —
    passing an arbitrary string will just silently match nothing.
    """
    chunks = search_kb(query_text, top_k=top_k, subject=subject, topic=topic)
    state_rows = get_knowledge_state(student_id, subject=subject)
    profile = get_profile(student_id, profiles)

    return ContextBundle(
        curriculum_chunks=chunks,
        knowledge_state_summary=summarise_state(state_rows),
        profile_note=profile_to_note(profile),
    )

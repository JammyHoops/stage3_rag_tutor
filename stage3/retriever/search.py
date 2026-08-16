"""Vector search with local reranking over the curriculum KB.

PROVENANCE — KEPT (adapted) from AI_IT_Helpdesk
``services/kb_agent/retriever/search.py``.

WHY KEPT: this is the most defensible part of the helpdesk design. Rather
than trusting raw vector similarity, it over-fetches candidates
(top_k * 4) and reranks with an explicit, explainable blend:

    rank = (similarity * 0.70 + provenance_trust * 0.25 + feedback * 0.05)
           * time_decay

Every term is named and tuneable, which supports a reasoned account of
ranking in Chapter 3 instead of a black box. Both the raw Chroma distance
and the adjusted score are retained on every result, deliberately: that
enables a reranker-vs-raw-similarity ablation table in Chapter 4 at no
extra cost.

ADAPTATIONS for Stage 3:
- The helpdesk's ``exclude_facilities`` ticket filter is replaced by a
  subject/topic metadata filter, so retrieval can be scoped to the subject
  the student is working in.
- ``kb_score`` now encodes curriculum provenance (set at ingest — see
  stage3/ingest.py) rather than ticket-source trust.

DONE (2026-08-16): weight sanity-check + decay decision.

WEIGHT SANITY-CHECK — ran 7 real questions across all 3 subjects
(2 biology, 2 chemistry, 3 computer_science, top_k=3 each) through
`search_kb` against the live re-ingested corpus and inspected raw
similarity vs. adjusted `rank_score` ordering. Finding worth recording
honestly: `kb_score` is currently 2.0 (`third_party_education_platform`)
on EVERY chunk in the corpus — no `awarding_body_spec`/`mark_scheme`
source has been collected yet (see ingest.py's PROVENANCE_SCORES) — so
the provenance term is a constant offset right now and does not actually
discriminate between candidates; observed ranking in this sanity-check
was effectively driven by similarity alone. That is expected, not a bug:
the term will start discriminating the moment a higher- or lower-tier
source is added. Within that constraint, ordering was sane in all 7
cases — top hits were topically on-target, no evidence of the small
feedback term (all `fb_pos`/`fb_neg` are 0 on this corpus, so it
contributed nothing either) producing a bad ranking. This is a sanity
check, not a tuning exercise or an ablation — a real blend-weight
tuning study (and the reranker-vs-raw-similarity ablation the module
design already supports) belongs with the evaluation instrument in
Chapter 4, once there's provenance-tier diversity in the corpus to
actually tune against.

DECAY DECISION — kept, not removed, but documented as currently inert:
`_decay_multiplier` only discounts chunks carrying `last_feedback_at`,
and no curriculum chunk has that field yet (feedback write-up is a
separate, still-open TODO — see vectordb/store.py). So for all real
content today `time_decay == 1.0` unconditionally; it has no effect to
decide "keep or remove" yet. Framing for Chapter 3: this is a
FEEDBACK-recency decay (a chunk whose feedback signal is stale should
count for less), not a CONTENT-staleness decay — curriculum specifications
do not go stale the way a ticket fix does, and this mechanism was never
meant to imply otherwise. Revisit only once feedback semantics land.

    [ ] Feedback semantics: see TODO in vectordb/store.py.

DONE: `difficulty_tier` filter parameter added (alongside `subject` /
`topic`) — see docs/design/stage3-curriculum-retrieval-design.md. Not
`tier`, which would collide with the existing `provenance_tier`. This
makes foundation-tier content (currently only real for Ada Computer
Science — see connectors/ada_computer_science.py) retrievable on request;
it is NOT wired into an automatic trigger anywhere yet — context_builder.
build_context still only calls search_kb without it. The trigger itself
is blocked on student_state/store.py's mastery-rule stub, a separate,
deliberate fail-closed decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..vectordb.store import get_store

# ---------------------------------------------------------------------------
# Filters  (ADAPTED)
# ---------------------------------------------------------------------------

def build_metadata_filter(
    subject: Optional[str] = None,
    topic: Optional[str] = None,
    difficulty_tier: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Scope retrieval to a subject (and optionally topic / difficulty_tier).

    ``difficulty_tier`` is "core" | "foundation" — deliberately not named
    `tier`, which would collide with the existing `provenance_tier` (trust
    axis). See module docstring: this is additive, not yet called with a
    value from anywhere in the automatic tutoring pipeline.

    Chroma requires ``$and`` for multiple conditions.
    """
    conditions: List[Dict[str, Any]] = []
    if subject:
        conditions.append({"subject": subject})
    if topic:
        conditions.append({"topic": topic})
    if difficulty_tier:
        conditions.append({"difficulty_tier": difficulty_tier})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


# ---------------------------------------------------------------------------
# Scoring helpers  (KEPT verbatim)
# ---------------------------------------------------------------------------

def _parse_iso(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            return None
    return None


def _decay_multiplier(meta: Dict[str, Any]) -> float:
    """Read-time decay of old feedback (floor 0.70). See module TODO on
    whether this stays for curriculum content."""
    last = _parse_iso(meta.get("last_feedback_at"))
    if not last:
        return 1.0
    now = datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age_days = max(0, (now - last).days)
    return max(0.70, 1.0 - (age_days * 0.01))


def _feedback_bonus(meta: Dict[str, Any]) -> float:
    pos = int(meta.get("fb_pos") or 0)
    neg = int(meta.get("fb_neg") or 0)
    # Negatives count slightly stronger — conservative by design.
    return (pos * 0.08) - (neg * 0.12)


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _adjusted_rank_score(chroma_score: float, meta: Dict[str, Any]) -> float:
    """Blend similarity, provenance trust, feedback and decay.

    ``similarity_search_with_score`` returns a DISTANCE (lower = better);
    it is converted to a similarity-like value via 1 / (1 + distance).
    """
    distance = _safe_float(chroma_score, 9999.0)
    sim = 1.0 / (1.0 + max(0.0, distance))

    kb_score = _safe_float(meta.get("kb_score"), 0.0)  # provenance trust
    fb = _feedback_bonus(meta)
    decay = _decay_multiplier(meta)

    base = (sim * 0.70) + (kb_score * 0.25) + (fb * 0.05)
    return base * decay


# ---------------------------------------------------------------------------
# Retriever  (KEPT, filter signature adapted)
# ---------------------------------------------------------------------------

class Retriever:
    """Reranking wrapper around the Chroma store.

    Returns a list of dicts each containing:
        - content     : the chunk text
        - score       : raw Chroma distance   (kept for ablation)
        - rank_score  : adjusted score used for ordering
        - plus all chunk metadata (subject, provenance_tier, doc_id, ...)
    """

    def __init__(self) -> None:
        self.vectorstore = get_store()

    def search(
        self,
        query: str,
        top_k: int = 5,
        subject: Optional[str] = None,
        topic: Optional[str] = None,
        difficulty_tier: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        metadata_filter = build_metadata_filter(
            subject=subject, topic=topic, difficulty_tier=difficulty_tier
        )

        # Over-fetch then rerank locally.
        candidates_k = max(top_k * 4, 10)
        docs_and_scores = self.vectorstore.similarity_search_with_score(
            query, k=candidates_k, filter=metadata_filter
        )

        results: List[Dict[str, Any]] = []
        for doc, score in docs_and_scores:
            meta = dict(doc.metadata or {})
            meta["content"] = doc.page_content
            meta["score"] = float(score)
            meta["rank_score"] = _adjusted_rank_score(float(score), meta)
            results.append(meta)

        results.sort(key=lambda r: r.get("rank_score", 0.0), reverse=True)
        return results[:top_k]


def search_kb(
    query: str,
    top_k: int = 5,
    subject: Optional[str] = None,
    topic: Optional[str] = None,
    difficulty_tier: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Convenience helper (constructed per call — cheap, and avoids the
    helpdesk's module-level singleton, which instantiated the store on
    import and made testing awkward)."""
    return Retriever().search(
        query, top_k=top_k, subject=subject, topic=topic, difficulty_tier=difficulty_tier
    )

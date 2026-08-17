"""Vector search with local reranking over the curriculum KB.

PROVENANCE — KEPT (adapted) from AI_IT_Helpdesk. Rather than trusting raw
vector similarity, this over-fetches candidates (top_k * 4) and reranks
with an explicit, tuneable blend:

    rank = (similarity * 0.70 + provenance_trust * 0.25 + feedback * 0.05)
           * time_decay

Both the raw Chroma distance and the adjusted score are retained on every
result, so a reranker-vs-raw-similarity comparison is possible later at no
extra cost. The helpdesk's ticket-source filter is replaced by a
subject/topic/difficulty_tier metadata filter here.

See docs/design/FINDINGS_AND_DECISIONS.md §3 for the weight sanity-check
findings and why time-decay is currently a no-op, and docs/TODO.md for the
open question about feedback-semantics and the blend-weight tuning study.

``difficulty_tier`` (alongside ``subject``/``topic``) makes foundation-tier
content retrievable on request; it is not wired into an automatic trigger
anywhere yet — see docs/TODO.md.
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

    ``difficulty_tier`` is "core" | "foundation" — not named `tier`, which
    would collide with the existing `provenance_tier` (trust axis).

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
    """Read-time decay of old feedback (floor 0.70)."""
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

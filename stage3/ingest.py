"""CLI entry point: ingest a source into the curriculum knowledge base.

PROVENANCE — KEPT (adapted) from AI_IT_Helpdesk ``services/kb_agent/ingest.py``
and the trust pre-seeding logic from ``services/kb_agent/__init__.py``.

WHY KEPT: the pre-seeding step writes a baseline trust score (``kb_score``)
and zeroed feedback counters into every chunk's metadata at ingest time,
which the retriever's reranker reads back. In the helpdesk, resolved
tickets outranked vendor documentation; here the same mechanism encodes
CURRICULUM PROVENANCE — awarding-body material outranks teacher-made
material when similarity is comparable.

ADAPTATION: chunking is now applied between fetch and store (the helpdesk
stored whole documents — see stage3/chunking.py).

Usage:
    python -m stage3.ingest --source curriculum_docs

DONE (2026-08-16): provenance tiers finalised against the sources actually
collected (Isaac Science, Ada Computer Science — the connectors/design-doc
correction re confirmed CC licences, 2026-08-16, is a separate, unrelated
fix). Justification for Chapter 3: the ordering reflects authority over
what counts as "the curriculum" for the in-scope subjects, not general
quality. Isaac Science and Ada Computer Science are both scored under
``third_party_education_platform`` (2.0) — the same tier as
``endorsed_textbook`` but deliberately its own label rather than folded
into it, because they are curated and Cambridge-vetted but NOT
awarding-body endorsed; scoring them honestly under a distinct label
(rather than either inflating them to endorsed-textbook status or lumping
them with unvetted teacher material) is the defensible position when only
two real sources exist at this tier. ``awarding_body_spec``/
``mark_scheme`` sit above both because nothing currently ingested actually
occupies those tiers — they are kept for a future awarding-body source,
not tuned against real data yet. ``teacher_material``/``DEFAULT_SCORE``
remain below third-party platforms on the same authority argument.

TODO (deliberately deferred, not required for defendability):
    [ ] Consider a --reset flag to wipe the collection before re-ingest
        during chunker experiments — a dev convenience, not blocking;
        the existing idempotent re-ingest (stable doc IDs, see
        vectordb/store.py) already covers the defendability need.
"""

from __future__ import annotations

import argparse

from .chunking import chunk_document
from .connectors.registry import CONNECTORS
from .vectordb.store import add_chunks

# ---------------------------------------------------------------------------
# Provenance trust pre-seeding  (finalised 2026-08-16 — see DONE note above)
# ---------------------------------------------------------------------------

PROVENANCE_SCORES: dict[str, float] = {
    "awarding_body_spec": 3.0,   # the authoritative statement of the curriculum
    "mark_scheme": 2.5,          # authoritative on what answers earn credit
    "endorsed_textbook": 2.0,    # publisher material endorsed by the board
    # Isaac Science / Ada Computer Science: curated, Cambridge-vetted
    # third-party platforms — not board-endorsed, so scored honestly under
    # its own label rather than folded into "endorsed_textbook".
    "third_party_education_platform": 2.0,
    "teacher_material": 1.5,     # departmental resources
}
DEFAULT_SCORE = 0.5


def ingest_source(source_name: str) -> int:
    if source_name not in CONNECTORS:
        raise ValueError(
            f"Unknown source {source_name!r}. Available: {', '.join(CONNECTORS)}"
        )

    connector = CONNECTORS[source_name]()
    print(f"[ingest] Fetching documents from {source_name!r}...")
    docs = connector.fetch()
    if not docs:
        print("[ingest] No documents returned.")
        return 0

    all_chunks: list[dict] = []
    for doc in docs:
        for chunk in chunk_document(doc):
            meta = chunk.setdefault("metadata", {})
            tier = meta.get("provenance_tier", "unassigned")
            # Pre-seed ranking metadata (read by retriever/search.py).
            meta.setdefault("kb_score", PROVENANCE_SCORES.get(tier, DEFAULT_SCORE))
            meta.setdefault("fb_pos", 0)
            meta.setdefault("fb_neg", 0)
            meta.setdefault("last_feedback_at", None)
            meta.setdefault("source", source_name)
            all_chunks.append(chunk)

    ids = add_chunks(all_chunks)
    print(f"[ingest] Stored {len(ids)} chunk(s) from {len(docs)} document(s).")
    return len(ids)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a source into the KB.")
    parser.add_argument("--source", required=True, help="e.g. 'curriculum_docs'")
    args = parser.parse_args()
    ingest_source(args.source)


if __name__ == "__main__":  # pragma: no cover
    main()

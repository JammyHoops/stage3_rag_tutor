"""CLI entry point: ingest a source into the curriculum knowledge base.

PROVENANCE — KEPT (adapted) from AI_IT_Helpdesk's ingest module, including
the trust pre-seeding step (writes a baseline ``kb_score`` and zeroed
feedback counters into every chunk's metadata at ingest time — read back
by the retriever's reranker). See docs/design/FINDINGS_AND_DECISIONS.md
for the reasoning behind the provenance tier ordering below.

Usage:
    python -m stage3.ingest --source curriculum_docs
"""

from __future__ import annotations

import argparse

from .chunking import chunk_document
from .connectors.registry import CONNECTORS
from .vectordb.store import add_chunks

# ---------------------------------------------------------------------------
# Provenance trust pre-seeding — see FINDINGS_AND_DECISIONS.md §3
# ---------------------------------------------------------------------------

PROVENANCE_SCORES: dict[str, float] = {
    "awarding_body_spec": 3.0,
    "mark_scheme": 2.5,
    "endorsed_textbook": 2.0,
    "third_party_education_platform": 2.0,  # Isaac Science, Ada CS
    "teacher_material": 1.5,
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

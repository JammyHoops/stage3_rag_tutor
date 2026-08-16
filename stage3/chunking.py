"""Document chunking for the curriculum knowledge base.

PROVENANCE — NEW. The helpdesk had no real chunker: ``add_chunks`` stored
whole documents (one vector each) and the only splitter was a naive
700-word count with no overlap and no sentence-boundary awareness
(``rag_api/apps/api/rag.py``, now removed). That was survivable for short
helpdesk articles; it will retrieve badly against long curriculum
documents, so this module is flagged as the highest-leverage retrieval
improvement in the build plan.

CURRENT BEHAVIOUR — PASSTHROUGH, AND NOW CONFIRMED SUFFICIENT.
``chunk_document`` returns the whole document as a single chunk. This
started as the helpdesk's document-level baseline, kept "temporary" until
a real chunker was built — but see RETIRED below: no in-scope source ever
needed one.

RETIRED (2026-08-16 cleanup pass) — NOT DOING, no active driver: the real
chunker below (sentence-aware splitting, size/overlap tuning, heading
preservation, list/equation handling) was speculative work for a
prose-only ingestion path. Subject scope was confirmed 2026-08-14 as
exactly three subjects (biology, chemistry, computer_science), and both
real connectors for that scope — Isaac Science and Ada Computer Science —
do their own structure-aware splitting at the source (one document per
natural section/concept), so this passthrough is adequate for everything
actually ingested. `connectors/curriculum_docs.py` (the prose-only .md/.txt
path this chunker would have served) is itself retired for the same
reason — see its own module docstring. If a future prose-only source is
ever added, revisit this TODO list rather than reinvent it:
    - Sentence-aware splitting (regex vs. tokeniser — decide + justify).
    - Chunk size ~150-300 words, 30-50 word overlap (empirical, a
      reportable ablation).
    - Section-heading preservation in chunk text/metadata.
    - Stable chunk IDs ("<doc_id>#<chunk_index>") for idempotent re-ingest.
    - List/equation-aware splitting (don't cut a numbered item mid-list).
"""

from __future__ import annotations

from typing import Any


def chunk_document(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Split one normalised document into chunk dicts ready for the store.

    Input shape (from connectors): {id, text, source, metadata}
    Output shape (for vectordb.store.add_chunks): same keys, with
    chunk-level ids of the form "<doc_id>#<n>".
    """
    # ── TEMPORARY passthrough (see module docstring) ────────────────────
    text = (doc.get("text") or "").strip()
    if not text:
        return []

    meta = dict(doc.get("metadata") or {})
    meta["chunk_index"] = 0
    meta["chunking"] = "passthrough_v0"  # visible in metadata so baseline
    #                                       runs are distinguishable from
    #                                       real-chunker runs in results.

    return [
        {
            "id": f"{doc.get('id', 'unknown')}#0",
            "text": text,
            "source": doc.get("source", "unknown"),
            "metadata": meta,
        }
    ]

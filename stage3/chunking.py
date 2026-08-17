"""Document chunking for the curriculum knowledge base.

PROVENANCE — NEW. Currently a passthrough: ``chunk_document`` returns the
whole document as a single chunk. This is sufficient because every
in-scope connector (Isaac Science, Ada Computer Science) already splits
content into natural sections at ingest time — see those connectors and
docs/design/FINDINGS_AND_DECISIONS.md for why a real sentence-aware
chunker was never needed. See docs/TODO.md if that changes.
"""

from __future__ import annotations

from typing import Any


def chunk_document(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Split one normalised document into chunk dicts ready for the store.

    Input shape (from connectors): {id, text, source, metadata}
    Output shape (for vectordb.store.add_chunks): same keys, with
    chunk-level ids of the form "<doc_id>#<n>".
    """
    text = (doc.get("text") or "").strip()
    if not text:
        return []

    meta = dict(doc.get("metadata") or {})
    meta["chunk_index"] = 0
    meta["chunking"] = "passthrough_v0"

    return [
        {
            "id": f"{doc.get('id', 'unknown')}#0",
            "text": text,
            "source": doc.get("source", "unknown"),
            "metadata": meta,
        }
    ]

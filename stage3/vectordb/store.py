"""Chroma vector store for the curriculum knowledge base.

PROVENANCE — KEPT (lightly adapted) from AI_IT_Helpdesk. ``_stable_doc_id``
and ``_normalize_metadata`` carried over as-is; collection renamed to
"stage3_curriculum" and the persist directory now comes from central
config rather than a hard-coded relative path. See
docs/design/FINDINGS_AND_DECISIONS.md §1 for the reasoning behind what was
kept, and docs/TODO.md for the open feedback-semantics question.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from ..config import CONFIG

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------

CHROMA_DIR: Path = CONFIG.paths.chroma_dir
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

COLLECTION_NAME = "stage3_curriculum"

# ---------------------------------------------------------------------------
# Embeddings (local model — see module docstring)
# ---------------------------------------------------------------------------

_embeddings = HuggingFaceEmbeddings(model_name=CONFIG.embedding.model_name)


def get_store() -> Chroma:
    """Return (and create if needed) the Chroma vector store."""
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=_embeddings,
        persist_directory=str(CHROMA_DIR),
    )


# ---------------------------------------------------------------------------
# Metadata normalisation  (KEPT verbatim)
# ---------------------------------------------------------------------------

def _normalize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Make metadata safe for Chroma: values must be str/int/float/bool/None."""
    safe: Dict[str, Any] = {}
    for key, value in meta.items():
        if hasattr(value, "isoformat"):
            safe[key] = value.isoformat()
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, (list, tuple, set)):
            safe[key] = ", ".join(map(str, value))
        else:
            safe[key] = str(value)
    return safe


# ---------------------------------------------------------------------------
# ID helpers  (KEPT verbatim — critical for idempotent re-ingest)
# ---------------------------------------------------------------------------

def _stable_doc_id(chunk: Dict[str, Any], source_fallback: str = "unknown") -> str:
    meta = chunk.get("metadata") or {}
    source = meta.get("source") or chunk.get("source") or source_fallback
    raw_id = chunk.get("id") or meta.get("id")
    if raw_id:
        return f"{source}:{raw_id}"
    return f"{source}:auto-{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_chunks(chunks: List[Dict[str, Any]]) -> List[str]:
    """Add chunk dicts ({text, metadata, id?}) to the vector DB."""
    store = get_store()
    docs: List[Document] = []
    ids: List[str] = []

    for chunk in chunks:
        text: str = chunk.get("text", "") or ""
        raw_meta: Dict[str, Any] = chunk.get("metadata", {}) or {}
        doc_id = _stable_doc_id(chunk)
        raw_meta.setdefault("doc_id", doc_id)
        docs.append(Document(page_content=text, metadata=_normalize_metadata(raw_meta)))
        ids.append(doc_id)

    return store.add_documents(docs, ids=ids)


def search(query: str, k: int = 5, filters: Optional[Dict[str, Any]] = None):
    """Basic similarity search with optional metadata filters.

    NOTE: the tutoring pipeline should normally go through
    stage3/retriever/search.py (which adds reranking); this raw entry point
    is kept for debugging and for the reranker-vs-raw ablation.
    """
    store = get_store()
    if filters:
        return store.similarity_search(query, k=k, filter=_normalize_metadata(filters))
    return store.similarity_search(query, k=k)


# ---------------------------------------------------------------------------
# Feedback counters (KEPT) — see docs/TODO.md for the open semantics question
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def update_feedback(
    doc_ids: List[str],
    feedback: str,
    answer_id: str,
    timestamp: Optional[str] = None,
) -> int:
    """Update feedback counters in Chroma metadata. Returns docs updated."""
    if feedback not in {"positive", "negative"} or not doc_ids:
        return 0

    store = get_store()
    collection = store._collection  # underlying chromadb collection
    ts = timestamp or _now_iso()
    updated = 0

    for doc_id in doc_ids:
        try:
            result = collection.get(ids=[doc_id], include=["metadatas"])
            if not result or not result.get("ids"):
                continue
            meta = (result.get("metadatas") or [{}])[0] or {}

            pos = int(meta.get("fb_pos") or 0)
            neg = int(meta.get("fb_neg") or 0)
            if feedback == "positive":
                pos += 1
            else:
                neg += 1

            meta.update(
                fb_pos=pos,
                fb_neg=neg,
                fb_total=pos + neg,
                fb_last_ts=ts,
                fb_last_answer_id=answer_id,
                last_feedback_at=ts,
            )
            collection.update(ids=[doc_id], metadatas=[_normalize_metadata(meta)])
            updated += 1
        except Exception as e:  # pragma: no cover
            print(f"[kb_feedback] Failed to update {doc_id}: {e}")

    return updated

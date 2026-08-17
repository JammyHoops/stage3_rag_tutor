"""Durable chat/conversation storage — one thread per (student, subject, topic).

PROVENANCE — NEW. Supports a Claude-Projects-style UI: subject = project,
topic = chat within that project. Topic and conversation are 1:1 (one
continuous thread per (student, subject, topic), enforced by the UNIQUE
constraint below), so every topic in the frontend's fixed taxonomy is
directly clickable as a chat — ``get_or_create_conversation`` is the entry
point, not ``create_conversation`` directly.

Kept in its own SQLite file (``CONFIG.paths.conversations_db``), separate
from ``student_state/store.py`` — that file's schema is mastery-only;
conversation transcripts are a different concern (turn-by-turn chat
history, not a knowledge-state estimate).

SCHEMA:
    conversations : one row per chat thread
                    (student, subject, topic, created_at, updated_at)
    messages      : one row per turn, ordered by id
                    (conversation_id, role ['student'|'tutor'], content,
                     chunk_doc_ids [JSON list, tutor turns only], created_at)

``content`` is always stored post-redaction: rows are replayed back into
prompts as conversation history, so they must already carry the same
privacy guarantee ``redaction.redact()`` provides.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..config import CONFIG

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL,
    subject    TEXT NOT NULL,
    topic      TEXT NOT NULL,          -- topic id from taxonomy, not label
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    diagnostic_status TEXT NOT NULL DEFAULT 'pending',  -- 'pending'|'done'
    diagnostic_questions_asked INTEGER NOT NULL DEFAULT 0,  -- 0..N, see
                                          -- tutor/diagnostic.py QUESTION_COUNT
    UNIQUE (student_id, subject, topic)  -- one continuous thread per topic,
                                          -- see get_or_create_conversation
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL,     -- 'student' | 'tutor'
    content         TEXT NOT NULL,     -- always post-redaction text
    chunk_doc_ids   TEXT,              -- JSON list, tutor turns only
    attributions    TEXT,              -- JSON list of human-readable CC
                                        -- citations, tutor turns only —
                                        -- see tutor/attribution.py. Computed
                                        -- ONCE at creation time and stored,
                                        -- never re-derived on read, so a
                                        -- historical message stays accurate
                                        -- to what was actually shown even if
                                        -- source data changes later.
    created_at      TEXT NOT NULL
);
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or CONFIG.paths.conversations_db
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    """Create tables if absent. Safe to call repeatedly."""
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_message(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    raw_ids = d.pop("chunk_doc_ids")
    d["chunk_doc_ids"] = json.loads(raw_ids) if raw_ids else None
    raw_attributions = d.pop("attributions")
    d["attributions"] = json.loads(raw_attributions) if raw_attributions else None
    return d


def create_conversation(
    student_id: str, subject: str, topic: str, db_path: Path | None = None
) -> int:
    """Start a new chat thread; returns the new conversation id.

    Low-level primitive — raises ``sqlite3.IntegrityError`` if a
    conversation for this exact (student, subject, topic) already exists
    (see the UNIQUE constraint in ``_SCHEMA``). Most callers want
    ``get_or_create_conversation`` instead; this is kept as-is for tests
    and any caller that specifically wants "create, fail if present."
    """
    ts = _now_iso()
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO conversations (student_id, subject, topic, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (student_id, subject, topic, ts, ts),
        )
        return cur.lastrowid


def get_or_create_conversation(
    student_id: str, subject: str, topic: str, db_path: Path | None = None
) -> tuple[int, bool]:
    """Return (id, created) for the (student, subject, topic) thread,
    creating it if it doesn't exist yet. This is the entry point the UI
    actually uses — every topic in the fixed taxonomy is clickable
    immediately, with no separate "New Chat" step; clicking a topic just
    resolves to its one continuous thread. See the module docstring.

    ``created`` tells the caller whether to kick off the opening
    diagnostic question (``tutor/chat_session.py::start_diagnostic``) —
    only on a genuine first creation, never on a re-fetch of an existing
    thread.
    """
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM conversations "
            "WHERE student_id = ? AND subject = ? AND topic = ? "
            "ORDER BY updated_at DESC LIMIT 1",
            (student_id, subject, topic),
        ).fetchone()
        if row:
            return row["id"], False
    return create_conversation(student_id, subject, topic, db_path), True


def set_diagnostic_progress(
    conversation_id: int,
    questions_asked: int,
    status: str,
    db_path: Path | None = None,
) -> None:
    """Update a conversation's diagnostic round progress. ``status`` must
    be 'pending' or 'done' — see the module docstring's DESIGN DECISION
    on the diagnostic mechanism and tutor/diagnostic.py.
    """
    if status not in ("pending", "done"):
        raise ValueError(f"status must be 'pending' or 'done', got {status!r}")
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE conversations SET diagnostic_questions_asked = ?, "
            "diagnostic_status = ? WHERE id = ?",
            (questions_asked, status, conversation_id),
        )


def reset_diagnostic(conversation_id: int, db_path: Path | None = None) -> None:
    """Start a fresh diagnostic round on an EXISTING thread (the "Re-check
    my understanding" action) — appended to the same conversation, not a
    new one, per the one-thread-per-topic decision."""
    set_diagnostic_progress(conversation_id, questions_asked=0, status="pending", db_path=db_path)


def get_conversation(
    conversation_id: int, db_path: Path | None = None
) -> Optional[dict[str, Any]]:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    return dict(row) if row else None


def list_student_ids(db_path: Path | None = None) -> list[str]:
    """All distinct student_ids that have ever started a conversation,
    sorted. This is the only honest source of "known students" in the
    system — there is no login/registry (see api/main.py's module
    docstring) — used to power the frontend's searchable student picker
    (see components/StudentSelect). A student typing a brand-new id is
    still valid and expected; this just lists who's been seen before.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT student_id FROM conversations ORDER BY student_id"
        ).fetchall()
    return [r["student_id"] for r in rows]


def list_conversations(
    student_id: str, subject: str | None = None, db_path: Path | None = None
) -> list[dict[str, Any]]:
    """Most-recently-updated first — matches a Claude-Projects-style chat list."""
    query = "SELECT * FROM conversations WHERE student_id = ?"
    params: tuple[Any, ...] = (student_id,)
    if subject:
        query += " AND subject = ?"
        params += (subject,)
    query += " ORDER BY updated_at DESC"
    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def add_message(
    conversation_id: int,
    role: str,
    content: str,
    chunk_doc_ids: list[str] | None = None,
    attributions: list[dict[str, str]] | None = None,
    db_path: Path | None = None,
) -> int:
    """Append one turn; returns the new message id."""
    if role not in ("student", "tutor"):
        raise ValueError(f"role must be 'student' or 'tutor', got {role!r}")
    ts = _now_iso()
    ids_json = json.dumps(chunk_doc_ids) if chunk_doc_ids else None
    attributions_json = json.dumps(attributions) if attributions else None
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO messages "
            "(conversation_id, role, content, chunk_doc_ids, attributions, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, role, content, ids_json, attributions_json, ts),
        )
        return cur.lastrowid


def list_messages(
    conversation_id: int, db_path: Path | None = None
) -> list[dict[str, Any]]:
    """Full history for a conversation, oldest first."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
    return [_row_to_message(r) for r in rows]


def recent_messages(
    conversation_id: int, limit: int = 6, db_path: Path | None = None
) -> list[dict[str, Any]]:
    """Bounded window of the most recent turns, returned oldest-first (chronological)."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    return [_row_to_message(r) for r in reversed(rows)]


def touch_conversation(conversation_id: int, db_path: Path | None = None) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (_now_iso(), conversation_id),
        )

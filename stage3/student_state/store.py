"""Per-student knowledge state — durable, structured, NOT a vector store.

PROVENANCE — NEW. No helpdesk equivalent; its only "state" was Rasa
session slots that evaporated when a session ended. Stage 3 needs
knowledge state that persists across sessions.

Plain SQLite, not a vector store — knowledge state never needs semantic
search. Students are identified only by the pseudonymous StudentID from
the LAET extract, no names or UPNs.

SCHEMA:
    observations : one row per assessed interaction
                   (student, subject, topic, outcome, timestamp, source)
    mastery      : one row per (student, subject, topic) — the current
                   estimate the tutor reads at prompt-build time

Mastery is seeded and updated by an LLM-graded diagnostic Q&A at the start
of each topic (``tutor/diagnostic.py``, ``tutor/chat_session.py::
start_diagnostic`` / ``_run_diagnostic_answer_turn``), not continuous
grading of ordinary tutoring turns. The student can explicitly trigger a
fresh round later ("Re-check my understanding"). Outcome scale is graded
(0.0/0.5/1.0), not binary. Update rule is EWMA (``ALPHA=0.35``); see
docs/design/FINDINGS_AND_DECISIONS.md §5 for why this over a rolling
window or Bayesian Knowledge Tracing. An unseen (student, subject, topic)
has no ``mastery`` row at all — cold start is an explicit empty state, not
a guessed default.

``seed_mastery_prior`` is a one-time exception to that cold-start rule,
for a student with Stage 1 attainment data — see its own docstring and
FINDINGS_AND_DECISIONS.md §5.

``student_state/explanation_method.py`` is a sibling module sharing this
same SQLite file but kept separate: a genuinely different schema/concern
(Thompson sampling over which teaching method works per student). See
docs/TODO.md for the open mastery-decay and foundation-tier-trigger
questions.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import CONFIG

# EWMA smoothing factor for the mastery update rule. Recent evidence
# weighted more than history, but bounded so one data point can't swing
# the estimate wildly.
MASTERY_EWMA_ALPHA = 0.35

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL,
    subject    TEXT NOT NULL,
    topic      TEXT NOT NULL,
    outcome    REAL NOT NULL,          -- 0.0 | 0.5 | 1.0
    source     TEXT NOT NULL,          -- 'diagnostic' (real) |
                                        -- 'demo_seed' (fabricated, see
                                        -- scripts/seed_demo_students.py) |
                                        -- 'stage2_handwriting' | 'typed'
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mastery (
    student_id TEXT NOT NULL,
    subject    TEXT NOT NULL,
    topic      TEXT NOT NULL,
    estimate   REAL NOT NULL,          -- 0..1
    n_obs      INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (student_id, subject, topic)
);
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or CONFIG.paths.student_db
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    """Create tables if absent. Safe to call repeatedly."""
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)


def record_observation(
    student_id: str,
    subject: str,
    topic: str,
    outcome: float,
    source: str,
    db_path: Path | None = None,
) -> float:
    """Store one observation and update the mastery estimate via EWMA.

    ``outcome`` must be 0.0, 0.5, or 1.0. Returns the new mastery estimate.
    """
    if outcome not in (0.0, 0.5, 1.0):
        raise ValueError(f"outcome must be 0.0, 0.5, or 1.0 — got {outcome!r}")

    ts = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO observations "
            "(student_id, subject, topic, outcome, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, subject, topic, outcome, source, ts),
        )

        row = conn.execute(
            "SELECT estimate, n_obs FROM mastery "
            "WHERE student_id = ? AND subject = ? AND topic = ?",
            (student_id, subject, topic),
        ).fetchone()

        if row is None:
            new_estimate = outcome
            new_n = 1
        else:
            new_estimate = (
                MASTERY_EWMA_ALPHA * outcome + (1 - MASTERY_EWMA_ALPHA) * row["estimate"]
            )
            new_n = row["n_obs"] + 1

        conn.execute(
            "INSERT INTO mastery (student_id, subject, topic, estimate, n_obs, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (student_id, subject, topic) "
            "DO UPDATE SET estimate = excluded.estimate, n_obs = excluded.n_obs, "
            "updated_at = excluded.updated_at",
            (student_id, subject, topic, new_estimate, new_n, ts),
        )

    return new_estimate


def seed_mastery_prior(
    student_id: str,
    subject: str,
    topic: str,
    estimate: float,
    db_path: Path | None = None,
) -> None:
    """Write an initial mastery estimate BEFORE any real diagnostic
    observation exists, derived from a Stage 1 attainment_band (see
    profiles/stage1_loader.py::attainment_band_to_prior via
    tutor/context_builder.py) — n_obs stays 0 so it's structurally
    distinguishable from a real observation-derived row. Called once, at
    diagnostic start, for a genuinely first-ever round only — see
    tutor/chat_session.py::start_diagnostic.

    NEVER overwrites: a no-op if a row already exists for this (student,
    subject, topic) — this must not be able to clobber real progress.
    The first real ``record_observation`` call after this finds the
    seeded row already present and blends into it via the normal EWMA
    branch (not the cold-start ``new_estimate = outcome`` branch), so
    ``n_obs`` becomes 1 — correctly counting only real observations, the
    seed itself is never counted as one.
    """
    ts = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO mastery (student_id, subject, topic, estimate, n_obs, updated_at) "
            "VALUES (?, ?, ?, ?, 0, ?) "
            "ON CONFLICT (student_id, subject, topic) DO NOTHING",
            (student_id, subject, topic, estimate, ts),
        )


def get_knowledge_state(
    student_id: str,
    subject: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return current mastery rows for a student (optionally one subject).

    Returns an empty list for unseen students — the explicit cold-start
    state, not a guessed default.
    """
    query = "SELECT * FROM mastery WHERE student_id = ?"
    params: tuple[Any, ...] = (student_id,)
    if subject:
        query += " AND subject = ?"
        params += (subject,)
    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]

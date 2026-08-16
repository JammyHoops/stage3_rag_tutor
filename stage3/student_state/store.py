"""Per-student knowledge state — durable, structured, NOT a vector store.

PROVENANCE — NEW. This is the largest gap identified when auditing the
helpdesk repo: its only "state" was Rasa session slots (retry_count,
articles_used), which evaporate when the session ends. Stage 3 requires a
knowledge state that accumulates ACROSS sessions and can be joined to the
Stage 1 learner profile. Nothing transferred; built from scratch.

DESIGN DECISIONS (document in Chapter 3):
- SQLite via the standard library: zero extra dependencies, a single local
  file, trivially inspectable. The knowledge state never needs semantic
  search, so a vector store would be the wrong tool.
- Students are identified ONLY by the pseudonymous StudentID issued in the
  LAET extract (Stage 1). No names, no UPNs — consistent with the data
  specification agreed with the school.

SCHEMA (implemented below):
    observations : one row per assessed interaction
                   (student, subject, topic, outcome, timestamp, source)
    mastery      : one row per (student, subject, topic) — the current
                   estimate the tutor reads at prompt-build time

DECISION (2026-08-13, confirmed with the user): mastery is seeded and
updated by an **LLM-graded diagnostic Q&A** at the start of each topic
(see ``tutor/diagnostic.py`` and ``tutor/chat_session.py::
start_diagnostic`` / ``_run_diagnostic_answer_turn``) — not continuous
grading of ordinary tutoring turns. The student can explicitly trigger a
fresh diagnostic round later ("Re-check my understanding") to update it
again; nothing updates mastery silently outside a diagnostic round.

- **Outcome scale**: graded, not binary — ``0.0`` (incorrect) / ``0.5``
  (partial) / ``1.0`` (correct), matching what an LLM grading a short
  free-text answer can actually distinguish. ``source="diagnostic"`` for
  every observation this mechanism records (the ``source`` field already
  existed for this purpose, just unused until now).
- **Update rule**: EWMA — ``new = ALPHA * outcome + (1 - ALPHA) * old``,
  or ``new = outcome`` with no prior row (true cold start). ``ALPHA =
  0.35`` — recent evidence weighted more than history, but one data point
  can't swing the estimate wildly. Chosen over a rolling-window proportion
  (would need to cap/query the observations table on every read) or
  Bayesian Knowledge Tracing (genuinely over-scope for the timeline —
  needs a guess/slip/transition parameter fit this project has no data to
  calibrate).
- **Cold start**: an unseen (student, subject, topic) has no `mastery`
  row at all — ``get_knowledge_state`` already returns ``[]`` for this,
  and ``context_builder.summarise_state`` renders that as "no prior
  record", not a guessed default.

SIBLING MODULE (2026-08-14): ``student_state/explanation_method.py``
lives alongside this file and shares this same SQLite file
(``CONFIG.paths.student_db``), but is kept in its OWN module rather than
appended here — this docstring's SCHEMA section above is deliberately
mastery-only (``observations``/``mastery``, referenced as such from
``conversations/store.py``'s own docstring), and explanation-method
selection is a genuinely different schema/concern (Thompson sampling
over which teaching method works per student) that happens to be, per
``docs/design/stage3-explanation-method-design.md``, "an extension of
the per-student knowledge-state source" rather than a new context
source — hence same DB file, separate module and schema block.

TODO (still open, deliberately not decided here):
    [ ] Decide whether mastery decays with inactivity — separate design
        question from the update rule itself, not raised as part of this
        change.
    [ ] Foundation-tier trigger (in-session half): still needs a
        cross-concept ``prerequisites`` graph, which no ingested source
        provides yet — see connectors/ada_computer_science.py and
        connectors/isaac_science.py's module docstrings. Not blocked by
        this change; `record_observation` now genuinely works, but
        nothing reads mastery for a *foundation-tier* trigger decision
        yet.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import CONFIG

# EWMA smoothing factor for the mastery update rule — see module
# docstring "DECISION" for the reasoning. Recent evidence weighted more
# than history, but bounded so one data point can't swing the estimate
# wildly.
MASTERY_EWMA_ALPHA = 0.35

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL,
    subject    TEXT NOT NULL,
    topic      TEXT NOT NULL,
    outcome    REAL NOT NULL,          -- see TODO: scale
    source     TEXT NOT NULL,          -- 'diagnostic' (real) |
                                        -- 'demo_seed' (fabricated, see
                                        -- scripts/seed_demo_students.py —
                                        -- UI walkthrough only, never real
                                        -- data) | 'stage2_handwriting' |
                                        -- 'typed' | ...
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

    ``outcome`` must be 0.0, 0.5, or 1.0 — see module docstring "DECISION"
    for the scale and update rule. Returns the new mastery estimate.
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


def get_knowledge_state(
    student_id: str,
    subject: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return current mastery rows for a student (optionally one subject).

    Returns an empty list for unseen students — the cold-start default is
    a TODO and must be handled by the caller until decided.
    """
    query = "SELECT * FROM mastery WHERE student_id = ?"
    params: tuple[Any, ...] = (student_id,)
    if subject:
        query += " AND subject = ?"
        params += (subject,)
    with _connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]

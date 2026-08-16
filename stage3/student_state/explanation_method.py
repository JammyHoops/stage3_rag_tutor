"""Per-student explanation-method selection — Thompson sampling.

PROVENANCE — NEW. Implements
``docs/design/stage3-explanation-method-design.md`` (status: decided).
This SUPERSEDES what ``tutor/context_builder.py::profile_to_note`` was
originally going to be (a fixed disability-category -> scaffolding-method
lookup table). Real research showed that's the wrong design: the SEND
Code of Practice and EEF's SEND guidance both push against
diagnosis-keyed strategy rules in favour of universal adaptive teaching,
evaluated per student. So instead of a static table, the tutor tracks,
per (student, method), whether that method has actually worked for THAT
student, and picks a method each turn accordingly. ``profile_to_note``
itself is untouched by this — it's a separate, still-unmade Stage 1
decision (see that module's own TODO).

Kept as a SIBLING module to ``student_state/store.py``, not folded into
it, even though both live in the same SQLite file
(``CONFIG.paths.student_db``) — see the note in ``store.py``'s docstring.
The design doc frames this as "an extension of the per-student
knowledge-state source, not a new context source" (unlike the Stage 1
profile, source 3), which is why it shares mastery's DB file rather than
getting a separate one the way ``conversations.db`` does.

MECHANISM (Thompson sampling, Beta-Bernoulli per (student, method)):
    - Each (student, method, signal_type) pair has a Beta(alpha, beta)
      posterior over "does this method work for this student".
    - Cold start: a student with no data for a method is governed by that
      method's COHORT prior (``method_cohort_prior``); if no cohort data
      exists yet either, a uniform ``Beta(1, 1)`` default is used —
      confirmed with the user rather than inventing numeric priors
      attributed to EEF's guidance, which does not actually publish
      per-method numeric success rates for this taxonomy. Neutral is the
      honest default; differentiation only emerges from real data.
    - Selection samples ONE draw per method from its current posterior and
      picks the argmax — not the highest mean. A method with a high mean
      but few observations has a wide posterior, so it still gets picked
      sometimes (exploration), while a mediocre early result isn't
      permanently discarded (no epsilon-greedy bolt-on needed).

SIGNAL SCOPE THIS PASS: only ``signal_type="immediate"`` is ever written.
``correct_retention`` / ``retention_gap_days`` exist in the schema (per
the design doc) but stay NULL — the design doc itself leaves "how long a
gap counts as retention" as an open item, so populating it now would mean
guessing a threshold. Not a new deferral, just following the doc's own.

ONE LLM CALL, NOT TWO: rather than a dedicated grading call (which would
double latency/cost on every ordinary tutoring turn), the correctness
signal is folded into the SAME normal-turn LLM call as a second trailing
marker line, mirroring ``tutor/diagnostic.py``'s
``[[MASTERY_SCORE: x]]`` pattern for the (unrelated) mastery mechanism.
``parse_understanding_marker`` below is that marker's parser; the prompt
side lives in ``tutor/prompt_template.py``, and the turn-by-turn wiring
in ``tutor/chat_session.py``.

CONCEPT RESOLUTION: no new concept-tracking machinery. The caller passes
whatever ``concept_id`` the top retrieved curriculum chunk carries (see
``connectors/isaac_science.py`` / ``connectors/ada_computer_science.py``).
Subjects with no curriculum content (mathematics/english) simply never
produce a ``concept_id``, so method selection/logging is a no-op there —
same graceful degradation as the rest of ``context_builder.py``.

TODO (deliberately not decided here — see design doc "Open items"):
    [ ] Retention signal / retention window.
    [ ] Splitting the (student, method) posterior by subject or concept
        instead of student-level only — doc says start coarse, only
        split with evaluation evidence.
    [ ] ``recompute_cohort_priors`` has no scheduler — nothing else in
        this project does either (``ingest.py`` is manually invoked
        too). Run it manually / periodically; see ``__main__`` below.
"""

from __future__ import annotations

import logging
import random
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..config import CONFIG

logger = logging.getLogger(__name__)

# Fixed taxonomy — see design doc "Method taxonomy". Deliberately small;
# do not add methods ad hoc without updating the design doc too (more
# categories means less evidence per category per student).
EXPLANATION_METHODS = (
    "worked_example",
    "analogy",
    "step_by_step_scaffold",
    "visual_diagrammatic",
    "socratic_questioning",
    "chunking",
)

# Short instruction text per method — what actually reaches the prompt
# (see tutor/prompt_template.py's EXPLANATION APPROACH line). Plain
# pedagogy description, not a category label.
METHOD_LABELS: dict[str, str] = {
    "worked_example": (
        "a fully worked example first, showing every step, before asking "
        "the student to try one themselves"
    ),
    "analogy": (
        "a concrete analogy to something the student already knows, then "
        "connect it back to the concept"
    ),
    "step_by_step_scaffold": (
        "the smallest possible first step, checking understanding before "
        "adding the next step"
    ),
    "visual_diagrammatic": (
        "a description the student could sketch or picture — a diagram, "
        "labelled parts, or a spatial layout — rather than prose alone"
    ),
    "socratic_questioning": (
        "guiding questions that lead the student to state the idea "
        "themselves, rather than stating it for them"
    ),
    "chunking": (
        "the idea broken into small, separately-checked pieces rather "
        "than one continuous explanation"
    ),
}

# Uniform, deliberately uninformative cold-start prior — confirmed with
# the user (see module docstring). Used only when NEITHER the student NOR
# the cohort has any data yet for a given method.
DEFAULT_PRIOR_ALPHA = 1.0
DEFAULT_PRIOR_BETA = 1.0

_UNDERSTANDING_MARKER_RE = re.compile(
    r"\n?\[\[UNDERSTANDING:\s*(yes|no)\]\]\s*$", re.IGNORECASE
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS method_interactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id          TEXT NOT NULL,
    subject             TEXT NOT NULL,
    conversation_id     INTEGER NOT NULL,  -- ADDITIVE beyond the design
                                            -- doc's schema sketch: scopes
                                            -- "pending interaction" lookups
                                            -- to one thread.
    concept_id          TEXT,              -- nullable: not every turn
                                            -- resolves one
    method              TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    correct_immediate   INTEGER,           -- NULL until graded; 0/1
    correct_retention   INTEGER,           -- NULL — not populated this pass
    retention_gap_days  INTEGER
);

CREATE TABLE IF NOT EXISTS method_posterior (
    student_id      TEXT NOT NULL,
    method          TEXT NOT NULL,
    signal_type     TEXT NOT NULL,     -- 'immediate' | 'retention'
                                        -- (only 'immediate' is written yet)
    alpha           REAL NOT NULL,
    beta            REAL NOT NULL,
    n_observations  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (student_id, method, signal_type)
);

CREATE TABLE IF NOT EXISTS method_cohort_prior (
    method                    TEXT NOT NULL,
    signal_type               TEXT NOT NULL,
    cohort_alpha              REAL NOT NULL,
    cohort_beta               REAL NOT NULL,
    n_students_contributing   INTEGER NOT NULL DEFAULT 0,
    updated_at                TEXT NOT NULL,
    PRIMARY KEY (method, signal_type)
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_or_init_student_posterior(
    conn: sqlite3.Connection, student_id: str, method: str, signal_type: str = "immediate"
) -> tuple[float, float]:
    """Return this student's (alpha, beta) for (method, signal_type),
    creating it (seeded from the cohort prior, or the uniform default if
    the cohort has no data either) if it doesn't exist yet."""
    row = conn.execute(
        "SELECT alpha, beta FROM method_posterior "
        "WHERE student_id = ? AND method = ? AND signal_type = ?",
        (student_id, method, signal_type),
    ).fetchone()
    if row is not None:
        return row["alpha"], row["beta"]

    cohort = conn.execute(
        "SELECT cohort_alpha, cohort_beta FROM method_cohort_prior "
        "WHERE method = ? AND signal_type = ?",
        (method, signal_type),
    ).fetchone()
    alpha, beta = (
        (cohort["cohort_alpha"], cohort["cohort_beta"])
        if cohort is not None
        else (DEFAULT_PRIOR_ALPHA, DEFAULT_PRIOR_BETA)
    )

    conn.execute(
        "INSERT INTO method_posterior "
        "(student_id, method, signal_type, alpha, beta, n_observations) "
        "VALUES (?, ?, ?, ?, ?, 0)",
        (student_id, method, signal_type, alpha, beta),
    )
    return alpha, beta


def select_method(
    student_id: str,
    signal_type: str = "immediate",
    db_path: Path | None = None,
    _rng: random.Random | None = None,
) -> str:
    """Thompson sampling: one Beta draw per method, return the argmax.

    ``_rng`` is an injection point for deterministic tests — production
    callers should never pass it (falls back to the module-level
    ``random`` functions, i.e. genuinely random draws).
    """
    betavariate = _rng.betavariate if _rng is not None else random.betavariate
    with _connect(db_path) as conn:
        best_method = EXPLANATION_METHODS[0]
        best_draw = -1.0
        for method in EXPLANATION_METHODS:
            alpha, beta = _get_or_init_student_posterior(conn, student_id, method, signal_type)
            draw = betavariate(alpha, beta)
            if draw > best_draw:
                best_draw = draw
                best_method = method
        return best_method


def log_interaction(
    student_id: str,
    subject: str,
    conversation_id: int,
    concept_id: Optional[str],
    method: str,
    db_path: Path | None = None,
) -> int:
    """Record that ``method`` was used to explain ``concept_id`` this
    turn. ``correct_immediate`` starts NULL — graded by a later call to
    ``record_understanding`` once the student's next answer on the same
    concept comes in. Returns the new interaction id."""
    ts = _now_iso()
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO method_interactions "
            "(student_id, subject, conversation_id, concept_id, method, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, subject, conversation_id, concept_id, method, ts),
        )
        return cur.lastrowid


def get_pending_interaction(
    conversation_id: int, db_path: Path | None = None
) -> Optional[dict[str, Any]]:
    """The most recent ungraded interaction for this conversation, or
    None. Scoped to ONE conversation (not the whole student) — a
    deliberate addition beyond the design doc's schema sketch, needed so
    two topic threads for the same student never cross-grade each
    other's pending interactions."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM method_interactions "
            "WHERE conversation_id = ? AND correct_immediate IS NULL "
            "ORDER BY id DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    return dict(row) if row else None


def record_understanding(
    interaction_id: int,
    student_id: str,
    method: str,
    success: bool,
    signal_type: str = "immediate",
    db_path: Path | None = None,
) -> tuple[float, float]:
    """Close out a pending interaction and update the Beta-Bernoulli
    posterior for (student, method, signal_type). Returns the new
    (alpha, beta)."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE method_interactions SET correct_immediate = ? WHERE id = ?",
            (1 if success else 0, interaction_id),
        )

        alpha, beta = _get_or_init_student_posterior(conn, student_id, method, signal_type)
        new_alpha = alpha + (1.0 if success else 0.0)
        new_beta = beta + (0.0 if success else 1.0)
        conn.execute(
            "UPDATE method_posterior SET alpha = ?, beta = ?, "
            "n_observations = n_observations + 1 "
            "WHERE student_id = ? AND method = ? AND signal_type = ?",
            (new_alpha, new_beta, student_id, method, signal_type),
        )
        return new_alpha, new_beta


def recompute_cohort_priors(signal_type: str = "immediate", db_path: Path | None = None) -> None:
    """Aggregate every GRADED interaction across all students into a
    per-method cohort prior. Manual/periodic (e.g. a weekly batch) —
    there is no scheduler in this project; see module docstring and
    ``__main__`` below for how it's actually invoked.

    Cohort alpha/beta start from the same uniform default as an
    individual student's cold start (``DEFAULT_PRIOR_ALPHA/BETA``), then
    add the summed successes/failures across all students — so a cohort
    with little data stays close to neutral too, not artificially
    confident.
    """
    ts = _now_iso()
    with _connect(db_path) as conn:
        for method in EXPLANATION_METHODS:
            row = conn.execute(
                "SELECT "
                "  SUM(CASE WHEN correct_immediate = 1 THEN 1 ELSE 0 END) AS successes, "
                "  SUM(CASE WHEN correct_immediate = 0 THEN 1 ELSE 0 END) AS failures, "
                "  COUNT(DISTINCT student_id) AS n_students "
                "FROM method_interactions "
                "WHERE method = ? AND correct_immediate IS NOT NULL",
                (method,),
            ).fetchone()
            successes = row["successes"] or 0
            failures = row["failures"] or 0
            n_students = row["n_students"] or 0

            cohort_alpha = DEFAULT_PRIOR_ALPHA + successes
            cohort_beta = DEFAULT_PRIOR_BETA + failures

            conn.execute(
                "INSERT INTO method_cohort_prior "
                "(method, signal_type, cohort_alpha, cohort_beta, n_students_contributing, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (method, signal_type) DO UPDATE SET "
                "cohort_alpha = excluded.cohort_alpha, "
                "cohort_beta = excluded.cohort_beta, "
                "n_students_contributing = excluded.n_students_contributing, "
                "updated_at = excluded.updated_at",
                (method, signal_type, cohort_alpha, cohort_beta, n_students, ts),
            )


def parse_understanding_marker(raw: str) -> tuple[str, Optional[bool]]:
    """Split an LLM response into (visible_text, understood).

    ``understood`` is ``None`` if the marker is missing or malformed —
    callers must treat that as "no signal", never guess True/False. Same
    fail-safe-not-fail-crash discipline as
    ``tutor/diagnostic.py::parse_graded_response``.
    """
    match = _UNDERSTANDING_MARKER_RE.search(raw)
    if not match:
        return raw.strip(), None

    understood = match.group(1).lower() == "yes"
    visible = raw[: match.start()].strip()
    return visible, understood


if __name__ == "__main__":
    recompute_cohort_priors()
    print("Cohort priors recomputed.")

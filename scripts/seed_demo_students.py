"""Seed a handful of synthetic demo students for UI walkthroughs.

PROVENANCE — NEW. A fresh clone has no students at all — there's no
login, so the only "known students" the searchable picker or mastery
indicator can show is whoever has actually used the system. This script
gives an examiner (or anyone else) opening a fresh clone something to
click through immediately.

Fabricated, synthetic demo data, for UI walkthrough only. Every student id
uses the ``demo-`` prefix so it's never mistaken for a real student, and
every observation uses ``source="demo_seed"`` (reusing the existing
`source` column rather than inventing a parallel one). Not dissertation
evidence, and never conflated with the real scenario runner in
``evaluation/``.

Does not call the live LLM: zero quota cost, deterministic, fast. Instead
this calls the same real store functions a live turn would
(``get_or_create_conversation``, ``add_message``,
``set_diagnostic_progress``, ``record_observation``) with synthetic
inputs, so the seeded rows are produced by the real persistence layer.
Each seeded topic's tutor message also attaches real citations via
``retriever/search.py::search_kb`` + ``tutor/attribution.py::
build_attributions`` (offline/local, no network call beyond the
already-ingested local vectordb).

Usage (from repo root, with requirements installed):
    python scripts/seed_demo_students.py
    python scripts/seed_demo_students.py --reset   # wipe demo-* rows first
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Self-contained: put the repo root on sys.path rather than requiring
# `-m scripts.seed_demo_students` package invocation.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stage3.conversations.store import (  # noqa: E402
    add_message,
    get_or_create_conversation,
    init_db as init_conversations_db,
    set_diagnostic_progress,
)
from stage3.student_state.store import (  # noqa: E402
    init_db as init_student_state_db,
    record_observation,
)
from stage3.taxonomy.topics import get_topic  # noqa: E402

DEMO_SOURCE = "demo_seed"

# student_id -> subject -> topic_id -> sequence of outcomes fed through
# record_observation in order (EWMA, alpha=0.35). Varied per student so
# the picker/dashboard has something to look at: student-1 strong in
# biology, weak in CS, chemistry untouched; student-2 balanced across all
# three; student-3 just started. Between them, all four MasteryBar states
# (no data / low / mixed / high) are demoable.
DEMO_STUDENTS: dict[str, dict[str, dict[str, list[float]]]] = {
    "demo-student-1": {
        "biology": {"biochemistry": [1.0, 1.0], "genetics": [0.5, 1.0]},
        "computer_science": {
            "algorithms_and_data_structures": [0.0, 0.0],
            "computer_networks": [0.0, 0.5],
        },
    },
    "demo-student-2": {
        "biology": {"cell_biology": [0.5, 0.5]},
        "chemistry": {
            "organic_chemistry": [0.5, 1.0],
            "physical_chemistry": [0.0, 0.5],
        },
        "computer_science": {"programming": [0.5, 0.5], "cyber_security": [1.0, 0.5]},
    },
    "demo-student-3": {
        "biology": {"physiology": [0.5]},
    },
}


def _reset_demo_data() -> None:
    """Delete only demo-* rows, from both DBs. Scoped by the id prefix —
    never touches real data."""
    import sqlite3

    from stage3.config import CONFIG

    with sqlite3.connect(CONFIG.paths.conversations_db) as conn:
        rows = conn.execute(
            "SELECT id FROM conversations WHERE student_id LIKE 'demo-%'"
        ).fetchall()
        conv_ids = [r[0] for r in rows]
        for cid in conv_ids:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
        conn.execute("DELETE FROM conversations WHERE student_id LIKE 'demo-%'")
        print(f"[reset] removed {len(conv_ids)} demo conversation(s).")

    with sqlite3.connect(CONFIG.paths.student_db) as conn:
        n = conn.execute(
            "DELETE FROM observations WHERE student_id LIKE 'demo-%'"
        ).rowcount
        conn.execute("DELETE FROM mastery WHERE student_id LIKE 'demo-%'")
        print(f"[reset] removed {n} demo observation(s).")


def _demo_attributions(subject: str, topic_label: str) -> list[dict[str, str]]:
    """Real citations for a demo message, via the real (local, offline)
    retrieval + attribution pipeline — no LLM call. Fails soft (empty
    list) if the vectordb isn't populated yet (e.g. curriculum hasn't
    been ingested on this clone) — a demo message with no citations is
    fine, a crash isn't."""
    try:
        from stage3.retriever.search import search_kb
        from stage3.tutor.attribution import build_attributions

        chunks = search_kb(topic_label, top_k=2, subject=subject)
        return build_attributions(chunks)
    except Exception as e:  # pragma: no cover - environment-dependent
        print(f"  (no attributions for {subject}/{topic_label}: {e})")
        return []


def seed() -> None:
    init_conversations_db()
    init_student_state_db()

    seeded = 0
    skipped = 0
    for student_id, subjects in DEMO_STUDENTS.items():
        for subject, topics in subjects.items():
            for topic_id, outcomes in topics.items():
                topic = get_topic(subject, topic_id)
                if topic is None:
                    print(f"  ! unknown topic {subject}/{topic_id} — skipping.")
                    continue

                conversation_id, created = get_or_create_conversation(
                    student_id, subject, topic_id
                )
                if not created:
                    # Already seeded by a previous run — idempotent no-op.
                    skipped += 1
                    continue

                attributions = _demo_attributions(subject, topic.label)
                add_message(
                    conversation_id,
                    role="student",
                    content=f"[demo seed] Can you help me with {topic.label}?",
                )
                add_message(
                    conversation_id,
                    role="tutor",
                    content=(
                        f"[demo seed] This is a placeholder tutor turn for "
                        f"{topic.label}, seeded for a UI walkthrough — not a "
                        f"real tutoring response."
                    ),
                    attributions=attributions or None,
                )
                # Diagnostic already "done" — clicking this topic in the UI
                # goes straight to normal tutoring, not a fresh diagnostic.
                set_diagnostic_progress(
                    conversation_id, questions_asked=3, status="done"
                )

                for outcome in outcomes:
                    record_observation(
                        student_id, subject, topic_id, outcome, source=DEMO_SOURCE
                    )
                seeded += 1
                print(f"  + {student_id} / {subject} / {topic_id} ({len(outcomes)} obs)")

    print(f"\nSeeded {seeded} demo topic(s), skipped {skipped} already-seeded.")
    print("Student ids: " + ", ".join(DEMO_STUDENTS.keys()))
    print("Reminder: this is fabricated demo data (source='demo_seed'), not real usage.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="Delete existing demo-* rows first."
    )
    args = parser.parse_args()

    if args.reset:
        _reset_demo_data()
    seed()

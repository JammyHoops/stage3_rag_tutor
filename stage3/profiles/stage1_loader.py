"""Loader for the Stage 1 learner-profile export.

PROVENANCE — NEW. No helpdesk equivalent; the third context source in the
Stage 3 design alongside curriculum retrieval and knowledge state.

Real schema: a synthetic fixture matching the user's own Stage 1
pipeline's output, committed at
``data/stage1/stage1_profiles.synthetic.csv`` (the real runtime default
path, ``stage1_profiles.csv``, stays gitignored — copy the fixture into
place to exercise this locally). Real, non-synthetic Stage 1 data is
deliberately not being pursued — see
docs/design/FINDINGS_AND_DECISIONS.md §5.

SCHEMA: one row per (student_id, subject) — a student can appear multiple
times, once per subject Stage 1 has a record for. Two coarse-category
fields, not raw scores:

    flag_status      "none" | "provisional" | "confirmed"
    attainment_band  "well_below" | "below" | "in_line" | "above"

These serve genuinely different purposes downstream, not redundant with
each other:
    - ``flag_status``      -> ``tutor/context_builder.py::profile_to_note``
                              (a one-time pedagogical note, diagnostic-
                              opening only).
    - ``attainment_band``  -> ``tutor/context_builder.py::
                              attainment_band_to_prior`` (a numeric
                              mastery seed — see
                              student_state/store.py::seed_mastery_prior).

Only ``scaffolding_note`` — a short, coarse text string — is ever allowed
to reach an LLM prompt (see ``tutor/prompt_template.py``'s
``ALLOWED_PROFILE_FIELDS`` guard, enforced at runtime). ``attainment_band``
never reaches the LLM as text; it only ever becomes a float written to the
mastery table.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

from ..config import CONFIG

FIELDS = ["student_id", "subject", "flag_status", "attainment_band"]


def load_profiles(path: Path | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """Load the Stage 1 export into {student_id: {subject: profile_row}}.

    Nested by subject because the real export is one row per
    (student_id, subject) — a student with records in two subjects
    appears as two rows, not one row with a list field.
    """
    export = path or (CONFIG.paths.stage1_dir / "stage1_profiles.csv")
    if not export.exists():
        print(f"[stage1_loader] No export found at {export} — profiles empty.")
        return {}

    profiles: dict[str, dict[str, dict[str, Any]]] = {}
    with open(export, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = (row.get("student_id") or "").strip()
            subject = (row.get("subject") or "").strip()
            if sid and subject:
                profiles.setdefault(sid, {})[subject] = dict(row)
    n_rows = sum(len(subjects) for subjects in profiles.values())
    print(f"[stage1_loader] Loaded {n_rows} profile row(s) for {len(profiles)} student(s).")
    return profiles


def get_profile(
    student_id: str,
    subject: str,
    profiles: dict[str, dict[str, dict[str, Any]]],
) -> Optional[dict[str, Any]]:
    """Explicit lookup — returns None for an unknown student or a known
    student with no record in this specific subject."""
    return profiles.get(student_id, {}).get(subject)

"""Loader for the Stage 1 learner-profile export.

PROVENANCE — NEW. No helpdesk equivalent existed; the third context source
in the Stage 3 design (alongside curriculum retrieval and knowledge state).

DONE (2026-08-16): real schema landed — a synthetic fixture produced by
the user's own Stage 1 pipeline (not real student data, not bound by a
data-management agreement — confirmed by the user), committed at
``data/stage1/stage1_profiles.synthetic.csv`` (see the ``.gitignore``
exception carved out for exactly this one file; the real runtime default
path, ``stage1_profiles.csv``, stays gitignored as before — copy the
fixture into place to exercise this locally without real data, same
convention as ``.env.example`` -> ``.env``).

SCHEMA: one row per (student_id, subject) — NOT one row per student; a
student can appear multiple times, once per subject Stage 1 has a record
for. Two content fields, both already coarse categories, not raw scores
(this was a real open design question — see docs/design/stage3-stage1-
schema-requirements.md — resolved by the user: Stage 1 resolves magnitude
internally before ever assigning a flag, so no raw residual reaches
Stage 3 at all):

    flag_status      "none" | "provisional" | "confirmed"
    attainment_band  "well_below" | "below" | "in_line" | "above"

The two fields serve genuinely different, deliberately separate purposes
downstream — NOT redundant with each other:
    - ``flag_status``     -> ``tutor/context_builder.py::profile_to_note``
                              (a one-time pedagogical note, diagnostic-
                              opening only — see that module).
    - ``attainment_band``  -> ``tutor/context_builder.py::
                              attainment_band_to_prior`` (a numeric
                              mastery seed, blended away by real evidence
                              via the existing EWMA rule — see
                              student_state/store.py::seed_mastery_prior).

PRIVACY NOTE (feeds the Chapter 3 data-protection section): the profile
is a structured record that gets INJECTED into prompt construction (via
the note) or a database write (via the prior), not embedded or retrieved.
Only ``scaffolding_note`` — a short, coarse text string — is ever allowed
to reach an LLM prompt at all (see ``tutor/prompt_template.py``'s
``ALLOWED_PROFILE_FIELDS`` guard, enforced at runtime, not just by
convention). ``attainment_band`` never reaches the LLM as text; it only
ever becomes a single float written to the mastery table.

TODO:
    [ ] Real (non-synthetic) Stage 1 export, once it exists (blocked on
        ethics approval) — this loader's parsing logic doesn't need to
        change for that, only the file at the real default path does.
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
    """Explicit lookup — returns None for an unknown student OR a known
    student with no record in this specific subject (see module TODO)."""
    return profiles.get(student_id, {}).get(subject)

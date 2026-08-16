"""Loader for the Stage 1 learner-profile export.

PROVENANCE — NEW. No helpdesk equivalent existed; the third context source
in the Stage 3 design (alongside curriculum retrieval and knowledge state).

The Stage 1 Colab pipeline will export a per-student summary (CSV) keyed by
the pseudonymous StudentID: flag status, residual magnitude, and per-subject
gap indicators. This module is the ONLY place that file is read, so the
field mapping lives in exactly one spot when the real export lands.

PRIVACY NOTE (feeds the Chapter 3 data-protection section): the profile is
a structured record that gets INJECTED into prompt construction, not
embedded or retrieved. What granularity crosses to the cloud LLM is a
deliberate decision — see the TODOs and tutor/prompt_template.py, which
enforces the allowed fields.

TODO:
    [ ] Fix the export schema once Stage 1 runs on the real LAET extract
        (blocked on ethics approval); update FIELDS below to match.
    [ ] Decide prompt granularity: a coarse category ("flagged for
        additional scaffolding in <subject>") is defensible; the raw
        residual value or any support-need field is not to be transmitted.
        Record the decision and reasoning.
    [ ] Validation: unknown StudentID → explicit None, never a fabricated
        default profile.
    [ ] Loading strategy: file is small — load once into a dict at startup
        rather than re-reading per turn.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional

from ..config import CONFIG

# Placeholder schema — MUST be updated to match the real Stage 1 export.
FIELDS = ["student_id", "flagged", "flag_subjects"]


def load_profiles(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load the Stage 1 export into {student_id: profile_row}.

    Currently expects a CSV with the placeholder FIELDS above.
    """
    export = path or (CONFIG.paths.stage1_dir / "stage1_profiles.csv")
    if not export.exists():
        print(f"[stage1_loader] No export found at {export} — profiles empty.")
        return {}

    profiles: dict[str, dict[str, Any]] = {}
    with open(export, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = (row.get("student_id") or "").strip()
            if sid:
                profiles[sid] = dict(row)
    print(f"[stage1_loader] Loaded {len(profiles)} profile(s).")
    return profiles


def get_profile(
    student_id: str, profiles: dict[str, dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """Explicit lookup — returns None for unknown students (see TODO)."""
    return profiles.get(student_id)

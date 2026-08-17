"""Intake for Stage 2 handwriting-recognition output (file-based handoff).

PROVENANCE — NEW. The helpdesk accepted typed text only; this module is
the seam between the MATLAB Stage 2 pipeline and the Stage 3 tutor, via a
file-based handoff.

CONTRACT: MATLAB writes one JSON file per submission into
data/stage2_inbox/ with the shape:

    {
      "submission_id": "SUB-0001",
      "student_id":   "<pseudonymous StudentID>",
      "subject":      "biology",
      "extracted_text": "...",
      "mean_char_confidence": 0.93        # optional
    }

Processed files are moved to data/stage2_archive/ so the inbox only ever
contains unprocessed work.

Stage 2 runs locally precisely so that only redacted extracted text ever
reaches a cloud LLM. ``redact()`` now lives in ``stage3/redaction.py``
(re-exported here for backwards compatibility, since the same gate applies
to typed chat input too, not just Stage 2 output) — see docs/TODO.md for
open items (low-confidence handling, subject validation, malformed-file
handling).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import CONFIG
from ..redaction import redact

REQUIRED_KEYS = {"submission_id", "student_id", "subject", "extracted_text"}


@dataclass
class Submission:
    submission_id: str
    student_id: str
    subject: str
    extracted_text: str
    mean_char_confidence: Optional[float] = None


def list_pending(inbox: Path | None = None) -> list[Path]:
    """List unprocessed Stage 2 output files, oldest first."""
    box = inbox or CONFIG.paths.stage2_inbox
    if not box.exists():
        return []
    return sorted(box.glob("*.json"))


def load_submission(path: Path) -> Submission:
    """Parse and validate one handoff file."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    missing = REQUIRED_KEYS - raw.keys()
    if missing:
        raise ValueError(f"{path.name}: missing required keys {sorted(missing)}")

    return Submission(
        submission_id=str(raw["submission_id"]),
        student_id=str(raw["student_id"]),
        subject=str(raw["subject"]),
        extracted_text=str(raw["extracted_text"]),
        mean_char_confidence=raw.get("mean_char_confidence"),
    )


def archive(path: Path, archive_dir: Path | None = None) -> Path:
    """Move a processed file out of the inbox."""
    dest_dir = archive_dir or CONFIG.paths.stage2_archive
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    shutil.move(str(path), str(dest))
    return dest

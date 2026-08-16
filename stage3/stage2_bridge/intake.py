"""Intake for Stage 2 handwriting-recognition output (file-based handoff).

PROVENANCE — NEW. The helpdesk accepted typed text only; this module is
the seam between the MATLAB Stage 2 pipeline and the Stage 3 tutor, per
the planned file-based handoff (ONNX export remains the alternative if a
tighter integration is needed later).

CONTRACT: MATLAB writes one JSON file per submission into
data/stage2_inbox/ with the shape:

    {
      "submission_id": "SUB-0001",
      "student_id":   "<pseudonymous StudentID>",
      "subject":      "mathematics",
      "extracted_text": "...",
      "mean_char_confidence": 0.93        # optional
    }

Processed files are moved to data/stage2_archive/ so the inbox only ever
contains unprocessed work.

PRIVACY — THE POINT OF THIS MODULE (Chapter 2 / Chapter 3 argument):
Stage 2 runs locally precisely so that only REDACTED extracted text ever
reaches a cloud LLM. ``redact()`` is FAIL-CLOSED (see ``stage3/redaction.py``,
where it now lives — re-exported here for backwards compatibility since the
same gate applies to typed chat input, not just Stage 2 output). When
auditing the helpdesk repo, the orchestrator f-stringed its raw context dict
into the LLM prompt — the exact pattern this module exists to prevent. Do
not weaken this to a passthrough "temporarily".

DONE: ``redact`` is implemented (see ``stage3/redaction.py``) and
re-exported below (``from ..redaction import redact``) — the stale
"[ ] Implement redact" bullet that used to live here was left over from
before that work landed and has been removed (2026-08-16 cleanup pass).

TODO:
    [ ] Decide the failure path for low-confidence recognition — e.g. if
        mean_char_confidence < threshold, route to "please retype" rather
        than tutoring on garbled text. Threshold is an empirical choice;
        tie it to the Stage 2 evaluation figures.
    [ ] Validate subject values against the subjects actually scoped by
        Stage 1 gap analysis.
    [ ] Malformed-file handling: quarantine rather than crash or delete.
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

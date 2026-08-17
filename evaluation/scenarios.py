"""Fixed, reproducible scenario definitions for expert review.

PROVENANCE — NEW. Fixed inputs (synthetic knowledge state, synthetic
profile note) so a review session is reproducible and involves no real
student data.

Data lives in ``scenarios.json`` (plain JSON, hand-editable; this loader
stays thin). ``mastery_rows`` is fed through
``tutor/context_builder.py::summarise_state`` at run time rather than
hand-written as a matching string, so a scenario's "knowledge state" text
can never drift from what the real bucketing logic produces.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_DEFAULT_PATH = Path(__file__).resolve().parent / "scenarios.json"


@dataclass
class Scenario:
    id: str
    subject: str
    topic: str
    student_message: str
    mastery_rows: list[dict[str, Any]] = field(default_factory=list)
    scaffolding_note: Optional[str] = None
    notes: str = ""


def load_scenarios(path: Path | None = None) -> list[Scenario]:
    """Load the scenario set from ``scenarios.json`` (or ``path``)."""
    p = path or _DEFAULT_PATH
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    return [Scenario(**s) for s in raw["scenarios"]]

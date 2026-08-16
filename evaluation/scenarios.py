"""Fixed, reproducible scenario definitions for expert review.

PROVENANCE — NEW. Closes the "build the scenario set" TODO in
``expert_review.py``: fixed inputs (synthetic knowledge state, synthetic
profile note) so a review session is reproducible and involves NO real
student data — see that module's docstring for the full evaluation
design.

Data lives in ``scenarios.json`` (same pattern as
``data/topics/<subject>.json`` — plain JSON, hand-editable, this loader
stays thin). The first draft's CONTENT was written by Claude and is
meant to be edited, not treated as final — see ``run_scenarios.py``'s
module docstring for why nothing runs against the real LLM until that
edit pass happens.

``mastery_rows`` is fed through ``tutor/context_builder.py::
summarise_state`` at run time (see ``run_scenarios.py``), not
hand-written as a matching string here — that way a scenario's
"knowledge state" text can never drift from what the real bucketing
logic actually produces.
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

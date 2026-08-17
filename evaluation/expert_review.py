"""Structured expert review capture for Stage 3 evaluation.

PROVENANCE — NEW. No helpdesk equivalent; the helpdesk was never formally
evaluated. Stage 3's evaluation method is structured expert review (a
SENCO reviewer, remote), so the instrument needs to exist in code: fixed
scenarios in, per-criterion ratings out, saved verbatim.

Records are appended as JSONL, one object per (scenario, criterion), so
nothing is overwritten and the raw record can be archived as required by
the Research Data Management review.

``CRITERIA`` below is a working draft, not yet signed off with the
supervisor — see docs/TODO.md. The CSV/JSONL schema is generic (criterion
name + 1-5 + comment), so revising the list is a small edit, not a
tooling rebuild.

The reviewer interface is CSV export/import: ``export_review_csv`` turns a
transcript run (``run_scenarios.py``) into one row per (scenario,
criterion) with rating/comment left blank; ``import_review_csv`` reads it
back, validating each row through ``record_rating``. ``generate_report``
produces the descriptive-only summary.

The scenario set lives in ``scenarios.py``/``scenarios.json``, run via
``run_scenarios.py`` — this module owns the rubric and review capture;
those own the scenario/transcript side.

The reviewer is identified by role only (``reviewer_role``); this file,
``scenarios.json``, and every generated artifact must never contain the
reviewer's actual name.
"""

from __future__ import annotations

import csv
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESULTS_PATH = Path(__file__).resolve().parent / "review_records.jsonl"
DEFAULT_CSV_PATH = Path(__file__).resolve().parent / "review_sheet.csv"
# Transcript fields carried into every CSV row, for the reviewer's context.
_TRANSCRIPT_CSV_FIELDS = (
    "scenario_id", "subject", "topic", "notes", "student_message",
    "knowledge_state_summary", "scaffolding_note", "answer",
    "grounding_chunks", "tiers_used",
)
_RATING_CSV_FIELDS = ("criterion", "rating", "comment")

CRITERIA = (
    "grounding_accuracy",
    "curriculum_fit",
    "adaptivity",
    "clarity",
    "safety_appropriateness",
)


@dataclass
class ReviewRecord:
    scenario_id: str
    criterion: str
    rating: int            # 1-5 (validate in record_rating)
    comment: str
    reviewer_role: str     # role only — never a name
    recorded_at: str = ""


def record_rating(record: ReviewRecord, path: Path = RESULTS_PATH) -> None:
    """Append one rating to the JSONL file. Validates criterion and scale."""
    if record.criterion not in CRITERIA:
        raise ValueError(f"Unknown criterion {record.criterion!r}; see CRITERIA.")
    if not 1 <= record.rating <= 5:
        raise ValueError("Rating must be 1-5.")
    record.recorded_at = datetime.now(timezone.utc).isoformat()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


# Deliberately NOT imported from run_scenarios.py — that module pulls in
# the vectordb/LLM stack (heavy deps) just to generate transcripts; this
# module stays lightweight (stdlib only) and just needs the path both
# modules already agree on (same directory, same filename).
TRANSCRIPTS_PATH = Path(__file__).resolve().parent / "transcripts.jsonl"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def export_review_csv(
    transcripts_path: Path = TRANSCRIPTS_PATH, out_path: Path = DEFAULT_CSV_PATH
) -> Path:
    """One row per (scenario, criterion) — transcript fields repeated on
    every row (safer for spreadsheet use than merged cells). ``rating``
    and ``comment`` are left blank for the reviewer to fill in."""
    transcripts = _load_jsonl(transcripts_path)

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(_TRANSCRIPT_CSV_FIELDS) + list(_RATING_CSV_FIELDS))
        writer.writeheader()
        for t in transcripts:
            row = {k: t.get(k, "") for k in _TRANSCRIPT_CSV_FIELDS}
            # list fields need flattening for a CSV cell
            row["grounding_chunks"] = "\n---\n".join(t.get("grounding_chunks") or [])
            row["tiers_used"] = ", ".join(t.get("tiers_used") or [])
            for criterion in CRITERIA:
                writer.writerow({**row, "criterion": criterion, "rating": "", "comment": ""})
    return out_path


def import_review_csv(
    path: Path = DEFAULT_CSV_PATH,
    reviewer_role: str = "SENCO",
    results_path: Path = RESULTS_PATH,
) -> list[ReviewRecord]:
    """Read a filled-in review sheet back in. Rows left with an empty
    ``rating`` are skipped (not every criterion has to be rated) — an
    invalid non-empty rating still raises, via ``record_rating``'s own
    validation, rather than being silently dropped."""
    imported: list[ReviewRecord] = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rating_raw = (row.get("rating") or "").strip()
            if not rating_raw:
                continue
            record = ReviewRecord(
                scenario_id=row["scenario_id"],
                criterion=row["criterion"],
                rating=int(rating_raw),
                comment=(row.get("comment") or "").strip(),
                reviewer_role=reviewer_role,
            )
            record_rating(record, path=results_path)
            imported.append(record)
    return imported


def generate_report(results_path: Path = RESULTS_PATH) -> str:
    """Descriptive-only summary: counts, mean, and range per criterion,
    plus every non-empty comment quoted verbatim against its scenario.
    Deliberately no inferential statistics (no significance claims, no
    p-values, no cross-criterion comparison) — a single reviewer's
    ratings don't support that."""
    records = [ReviewRecord(**r) for r in _load_jsonl(results_path)] if results_path.exists() else []

    lines = ["# Expert review — descriptive summary", ""]
    for criterion in CRITERIA:
        ratings = [r.rating for r in records if r.criterion == criterion]
        lines.append(f"## {criterion}")
        if not ratings:
            lines.append("No ratings recorded yet.\n")
            continue
        mean = statistics.mean(ratings)
        lines.append(
            f"n={len(ratings)}, mean={mean:.2f}, range={min(ratings)}-{max(ratings)} "
            "(descriptive only — single reviewer, no inferential statistics)."
        )
        comments = [r for r in records if r.criterion == criterion and r.comment]
        for r in comments:
            lines.append(f"> **{r.scenario_id}** (rated {r.rating}): {r.comment}")
        lines.append("")
    return "\n".join(lines)

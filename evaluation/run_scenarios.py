"""Generate real, grounded transcripts for the fixed scenario set.

PROVENANCE — NEW. Runs each ``evaluation/scenarios.json`` scenario
through the SAME building blocks a real tutoring turn uses —
``retriever/search.py::search_kb``, ``tutor/context_builder.py::
summarise_state``, ``tutor/prompt_template.py::build_prompt``,
``llm/client.py``'s ``generate`` — so the transcript is real evidence of
what the deployed system produces, not a hand-written mockup.

Deliberately does NOT go through ``tutor/chat_session.py::run_chat_turn``:
that function is wired to a real ``student_id`` (mastery writes,
explanation-method Thompson sampling + interaction logging). Scenarios
are fixed/synthetic on purpose — routing them through the stateful chat
machinery would pollute real per-student tables with fake data and
consume real Thompson-sampling draws for nothing. This also cleanly
sidesteps ``tutor.context_builder.profile_to_note`` (still a deliberate
stub) — ``profile_note`` is built directly from each scenario's
``scaffolding_note``, never calling ``get_profile``/``profile_to_note``
at all.

A hard LLM failure (``llm.client.LLMGenerationError``) is allowed to
propagate and abort the run — a scenario that silently produced no
transcript would be worse than a run that visibly failed and can be
resumed. Transcripts are written INCREMENTALLY (flushed after each
scenario), not all at once at the end, specifically because of this:
losing already-succeeded scenarios to one later failure would waste real
quota. See llm/client.py's TODO — Gemini's free tier caps at both 20
requests/DAY and, confirmed live 2026-08-15, 5 requests/MINUTE for
gemini-3.7-flash — so this module paces itself with ``SCENARIO_DELAY_
SECONDS`` between calls rather than firing all 6 back-to-back, which is
exactly what tripped the per-minute cap the first time this was run for
real. That pacing is deliberately NOT applied to ``LLMClient.generate``'s
own retry backoff (see that module) — a real single tutoring turn should
still fail fast, not wait out a whole minute; only this batch script's
rapid-fire pattern needs it.

Usage:  python -m evaluation.run_scenarios
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from stage3.llm.client import LLMClient, get_client
from stage3.redaction import redact
from stage3.retriever.search import search_kb
from stage3.tutor.context_builder import summarise_state
from stage3.tutor.prompt_template import build_prompt

from .scenarios import Scenario, load_scenarios

TRANSCRIPTS_PATH = Path(__file__).resolve().parent / "transcripts.jsonl"
# Confirmed live: Gemini free tier allows 5 requests/minute for
# gemini-3.7-flash. 15s spacing keeps a clean run at ~4/min, leaving
# headroom for a scenario that needs one internal retry.
SCENARIO_DELAY_SECONDS = 15


def _run_one(scenario: Scenario, llm: LLMClient, top_k: int = 4) -> dict[str, Any]:
    safe_text = redact(scenario.student_message)

    chunks = search_kb(safe_text, top_k=top_k, subject=scenario.subject, topic=scenario.topic)
    state_summary = summarise_state(scenario.mastery_rows)
    profile_note = (
        {"scaffolding_note": scenario.scaffolding_note} if scenario.scaffolding_note else {}
    )

    prompt = build_prompt(
        subject=scenario.subject,
        redacted_student_text=safe_text,
        curriculum_chunks=chunks,
        knowledge_state_summary=state_summary,
        profile_note=profile_note,
    )

    answer = llm.generate(prompt.user, system=prompt.system)  # LLMGenerationError propagates

    tiers_used = sorted({c["difficulty_tier"] for c in chunks if c.get("difficulty_tier")})

    return {
        "scenario_id": scenario.id,
        "subject": scenario.subject,
        "topic": scenario.topic,
        "notes": scenario.notes,
        "student_message": scenario.student_message,
        "knowledge_state_summary": state_summary,
        "scaffolding_note": scenario.scaffolding_note,
        "answer": answer,
        "chunk_doc_ids": prompt.chunk_doc_ids,
        "grounding_chunks": [c.get("content", "") for c in chunks],
        "tiers_used": tiers_used,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def generate_transcripts(
    scenarios: Optional[list[Scenario]] = None,
    llm: Optional[LLMClient] = None,
    out_path: Path = TRANSCRIPTS_PATH,
    delay_seconds: float = SCENARIO_DELAY_SECONDS,
) -> list[dict[str, Any]]:
    """Run every scenario for real, OVERWRITING ``out_path`` at the START
    (not append — a transcript file is a snapshot of one run of the
    CURRENT scenario set, not an accumulating log; ``expert_review.py``'s
    ``review_records.jsonl`` is the append-only one) then writing each
    result as it completes, paced ``delay_seconds`` apart. If a later
    scenario fails, everything successfully generated before it is
    already safely on disk — see module docstring for why that matters
    here specifically (real, scarce API quota)."""
    scenario_list = scenarios if scenarios is not None else load_scenarios()
    llm = llm or get_client()

    records: list[dict[str, Any]] = []
    with open(out_path, "w", encoding="utf-8") as f:
        for i, s in enumerate(scenario_list):
            if i > 0:
                time.sleep(delay_seconds)
            record = _run_one(s, llm)
            records.append(record)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  [{i + 1}/{len(scenario_list)}] {s.id} -> ok")
    return records


if __name__ == "__main__":
    results = generate_transcripts()
    print(f"Generated {len(results)} transcript(s) -> {TRANSCRIPTS_PATH}")

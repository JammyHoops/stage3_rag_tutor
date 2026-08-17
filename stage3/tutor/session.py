"""Tutoring turn handler for the Stage 2 file-handoff path.

PROVENANCE — NEW; replaces both Rasa and the helpdesk orchestrator. Rasa
(intent classification + story-based dialogue) is the wrong shape for
open tutoring dialogue, where a turn isn't one of a small set of intents;
the orchestrator's raw-context prompt assembly is replaced by the guarded
template in prompt_template.py. What's retained: the answer travels with
the doc IDs that produced it, so provenance can be shown to a reviewer.

Dormant: this is the older, file-handoff-shaped turn handler (takes a
``Submission`` from the Stage 2 MATLAB bridge), parallel to
``tutor/chat_session.py`` (what the live chat UI actually uses). No
conversation-thread concept, no mastery/explanation-method wiring, no
Stage 1 cold-start parity with ``chat_session.py::start_diagnostic``. Not
exercised by any test or live endpoint today — see docs/TODO.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..llm.client import LLMClient, get_client
from ..stage2_bridge.intake import Submission, redact
from .context_builder import build_context
from .prompt_template import build_prompt


@dataclass
class TutorResponse:
    answer: str
    chunk_doc_ids: list[str]
    subject: str


def run_turn(submission: Submission, llm: LLMClient | None = None) -> TutorResponse:
    """One tutoring turn: Stage 2 submission in -> grounded response out.

    Pipeline: redact -> build curriculum + knowledge-state context ->
    guarded prompt -> LLM.
    """
    llm = llm or get_client()

    safe_text = redact(submission.extracted_text)

    bundle = build_context(
        student_id=submission.student_id,
        subject=submission.subject,
        query_text=safe_text,
    )

    prompt = build_prompt(
        subject=submission.subject,
        redacted_student_text=safe_text,
        curriculum_chunks=bundle.curriculum_chunks,
        knowledge_state_summary=bundle.knowledge_state_summary,
    )

    answer = llm.generate(prompt.user, system=prompt.system)

    return TutorResponse(
        answer=answer,
        chunk_doc_ids=prompt.chunk_doc_ids,
        subject=submission.subject,
    )

"""Tutoring turn handler — replaces both Rasa and the helpdesk orchestrator.

PROVENANCE — NEW; two helpdesk components were deliberately NOT carried
over, and the reasons belong in Chapter 3:

- Rasa (intent classification + story-based dialogue): the wrong shape
  for open tutoring dialogue, where a turn is not one of a small set of
  intents; also a heavy, version-brittle dependency. Its useful ideas —
  per-turn provenance (articles_used) and a feedback commit step — are
  retained here without the framework.
- The orchestrator's raw-context prompt assembly: replaced by the guarded
  template in prompt_template.py (see its docstring for why).

What IS retained from the helpdesk design: the answer travels with the
doc IDs that produced it, so provenance can be shown to the reviewer and
feedback can be committed against exactly those chunks.

TODO:
    [ ] Multi-turn dialogue: carry conversation history into subsequent
        prompts (bounded — decide a turn window / token cap).
    [ ] Confidence gate: consult Submission.mean_char_confidence before
        tutoring on Stage 2 text (threshold TODO in stage2_bridge).
    [ ] Outcome inference: how a turn produces an observation for
        student_state.record_observation (links to the outcome-scale TODO).
    [ ] Transcript logging for expert review: persist {inputs (redacted),
        prompt, response, chunk_doc_ids, timestamps} — evaluation/ reads
        these. Store under UEL OneDrive per the RDM requirements.
    [ ] Failure paths: empty retrieval still needs explicit student-safe
        handling. Empty LLM response is resolved generically — see
        llm/client.py's LLMGenerationError; ``generate`` now raises
        instead of returning "", so a failure here just propagates (this
        path isn't wired to a live endpoint yet — see api/main.py TODO —
        so there's no caller here to add a try/except to yet).
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


def run_turn(
    submission: Submission,
    profiles: dict[str, dict[str, Any]],
    llm: LLMClient | None = None,
) -> TutorResponse:
    """One tutoring turn: Stage 2 submission in → grounded response out.

    Pipeline: redact → build three-source context → guarded prompt → LLM.
    ``redact`` is fail-closed (NotImplementedError) until implemented, so
    this path cannot transmit unredacted student text even by accident.
    """
    llm = llm or get_client()

    safe_text = redact(submission.extracted_text)

    bundle = build_context(
        student_id=submission.student_id,
        subject=submission.subject,
        query_text=safe_text,
        profiles=profiles,
    )

    prompt = build_prompt(
        subject=submission.subject,
        redacted_student_text=safe_text,
        curriculum_chunks=bundle.curriculum_chunks,
        knowledge_state_summary=bundle.knowledge_state_summary,
        profile_note=bundle.profile_note,
    )

    answer = llm.generate(prompt.user, system=prompt.system)
    # Empty-answer path resolved generically (see docstring) — a hard
    # failure now raises past this point rather than returning "".
    # TODO: transcript logging (see docstring).

    return TutorResponse(
        answer=answer,
        chunk_doc_ids=prompt.chunk_doc_ids,
        subject=submission.subject,
    )

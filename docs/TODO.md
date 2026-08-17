# Stage 3 — open TODOs

Single source of truth for outstanding work. Every inline `TODO` comment
that used to live scattered across `stage3/` has been moved here (2026-08-17
cleanup pass) — code should point back to this file rather than carrying
its own TODO list.

Each item names the file(s) it belongs to so it's still easy to find in
context.

## Real open work

- **Foundation-tier retrieval trigger is unbuilt.** The design is finalised
  (`docs/design/stage3-curriculum-retrieval-design.md`) and the retrieval
  filter it needs already exists (`difficulty_tier` param on `search_kb`,
  `retriever/search.py`), but nothing calls it automatically yet. It needs
  a cross-concept `prerequisites` graph, which no ingested source provides
  — Isaac Science and Ada Computer Science both give same-concept,
  lower-difficulty sections, not a dependency graph between different
  concepts. Not to be invented unilaterally.
  Files: `connectors/isaac_science.py`, `connectors/ada_computer_science.py`,
  `student_state/store.py`, `tutor/context_builder.py`.

- **Feedback semantics undefined.** `vectordb/store.py::update_feedback`
  and the `/feedback` endpoint exist, but "positive"/"negative" has no
  agreed meaning in a tutoring context (unlike the helpdesk's "this
  resolved the ticket"). Candidate: an expert reviewer marks a retrieved
  chunk relevant/irrelevant during structured evaluation. Needs deciding
  before the endpoint is wired to anything real.
  Files: `vectordb/store.py`, `retriever/search.py`.

- **Stage 2 failure paths are undecided.**
  - Low-confidence recognition: no threshold on
    `Submission.mean_char_confidence` yet, so garbled OCR text is never
    routed to a "please retype" path. Empirical choice, needs the Stage 2
    evaluation figures.
  - No subject validation against what Stage 1's gap analysis actually
    scopes.
  - Malformed inbox files are not quarantined — no handling beyond a raw
    exception.
  Files: `stage2_bridge/intake.py`.

- **Rubric sign-off (not code).** The expert-review criteria in
  `evaluation/expert_review.py::CRITERIA` are a working draft, not
  confirmed with the supervisor. The CSV/JSONL schema is generic (criterion
  name + 1-5 + comment) so revising the list is a small edit, not a rebuild.
  This is the actual remaining step before a real review session can run.

- **Ethics-application references for the review instrument** — consent /
  information sheet wording isn't in the repo yet. Reviewer is already
  identified by role only (`reviewer_role`) everywhere, never a name.
  Files: `evaluation/expert_review.py`.

## Deliberately deferred design questions

These are real, named open questions with their own reasoning already
written down — fine to stay open, not oversights.

- Mastery decay with inactivity — a separate question from the EWMA update
  rule itself. `student_state/store.py`.
- Retention signal / retention window for explanation-method selection —
  the design doc itself leaves "how long a gap counts as retention" open.
  `student_state/explanation_method.py`.
- Splitting the (student, method) posterior by subject or concept instead
  of student-level only — start coarse, split only with evaluation
  evidence. `student_state/explanation_method.py`.
- Retrieval query formulation — raw student text vs. an extracted question
  vs. text augmented with weak-topic terms from knowledge state. Framed as
  an experiment worth a subsection, not a bug. `tutor/context_builder.py`.
- top_k / token budget per source, and its interaction with chunk size.
  `tutor/context_builder.py`, `tutor/diagnostic.py`.
- A real blend-weight tuning study for the retrieval reranker (similarity /
  provenance / feedback / decay weights) — needs provenance-tier diversity
  in the corpus first; every chunk today scores the same `kb_score`.
  `retriever/search.py`.
- Date-of-birth / generic date detection in redaction — deliberately not
  attempted; no reliable way to distinguish "a DOB" from "a date in a STEM
  word problem" without more context than is available. `redaction.py`.
- Known-names register token collisions with ordinary words — no stoplist
  built; not justified at this scale. `redaction.py`.
- Diagnostic questions have no hard non-repeat guarantee beyond the LLM
  seeing prior questions in-prompt. Acceptable at `QUESTION_COUNT=3`;
  revisit if that grows. `tutor/diagnostic.py`.

## Small / polish, no active driver

- `--reset` flag for `ingest.py` to wipe the collection before a chunker
  experiment — dev convenience only; idempotent re-ingest already covers
  correctness.
- UK phone/email regexes in `redaction.py` are pragmatic, not
  RFC/E.164-validated (no `phonenumbers` dependency added).
- `redaction.py` hasn't been evaluated against real (redacted-for-review)
  Stage 2 output yet — nothing to tune `MIN_TOKEN_LEN`/the allowlist
  against until Stage 2 produces real text.
- `connectors/ada_computer_science.py`: `spec_code` isn't extracted from
  the `examBoard` list Ada exposes per section — left `None` rather than
  guessed; add if a consumer needs it.
- `connectors/isaac_science.py`: LaTeX/mhchem markup (`$\ce{...}$`) is left
  as-is in chunk text, not evaluated for prompt readability; AS/A2 split
  isn't available at the API's granularity (only `gcse`/`a_level`);
  `spec_code`/`misconceptions` aren't in this source's data.
- `taxonomy/topics.py`: no teacher-facing topic-authoring UI (files are
  hand-edited); subject slugs aren't validated against `data/curriculum/`
  at ingest time.
- `student_state/explanation_method.py::recompute_cohort_priors` has no
  scheduler — run manually/periodically, same as `ingest.py`.
- `connectors/registry.py`: no connector exists yet for a mark-scheme or
  worked-examples source — add one only if such a source is actually
  found and scoped in.
- `llm/client.py::get_client`: only Gemini is implemented; OpenAI/
  Anthropic clients would extend the same factory `if`/`elif` chain if a
  real need for a second provider appears.

## Dormant paths (unbuilt, but nothing currently drives them)

- `tutor/session.py` is the older Stage 2 file-handoff turn handler,
  parallel to `tutor/chat_session.py` (the one the live chat UI actually
  uses). It has no conversation-thread concept, no mastery/explanation-
  method wiring, and no Stage 1 cold-start parity with `chat_session.py`'s
  `start_diagnostic`. Not exercised by any test or endpoint today
  (`api/main.py`'s `/tutor` route is a deliberate 501 — see that file).
  Revisit only if a real, non-conversational Stage 2 batch-submission path
  is actually needed.
- `stage2_bridge/intake.py`'s confidence gate (see above) is part of the
  same dormant path.

## Known operational gotchas (not action items — just worth knowing)

- Gemini free-tier caps: 20 requests/day and 5 requests/minute per model,
  both hit for real during this project. `llm/client.py` fails fast rather
  than waiting out a cap; `evaluation/run_scenarios.py` paces itself with
  `SCENARIO_DELAY_SECONDS` for batch runs.
- Pinned model IDs (e.g. `gemini-2.5-flash`) can 404 for a specific account
  even while still listed by `client.models.list()`. Default to the
  `-latest` alias; if that's ever deprecated, re-query the live account
  rather than guessing a replacement ID.
- `usage_metadata.total_token_count` can be much larger than
  prompt+completion alone — current Gemini models bill internal
  "thinking" tokens into the total. Don't assume total == prompt +
  completion for a budget write-up.
- Isaac Science / Ada Computer Science both run version-pinned JSON APIs
  with no stable alias — if `fetch()` starts failing, check the API
  version string against a real browser network tab before assuming
  anything else is wrong.

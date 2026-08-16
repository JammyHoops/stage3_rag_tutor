# Stage 3 — RAG-Based Adaptive Tutoring (skeleton)

Skeleton for Stage 3 of the dissertation *Beyond the Label*, derived by
audit of the prior **AI_IT_Helpdesk** project. Every file states its
provenance in its docstring — **KEPT** (carried over, with reasons),
**ADAPTED**, or **NEW** (stubbed with a TODO list). Those docstrings are
written to be lifted into the Chapter 3 component-reuse account.

**Subject scope (confirmed 2026-08-14): three subjects —
biology, chemistry, computer_science.** Mathematics and English
(`data/topics/mathematics.json`, `english.json`) were provisional
placeholders added before subject scope was confirmed with the user;
removed once it was, rather than chased with new content. Three real,
well-grounded subjects (Isaac Science / Ada Computer Science — see the
curriculum-retrieval section below) is a defensible scope on its own.
This is also why `chunking.py`'s real-chunker TODO and
`connectors/curriculum_docs.py`'s PDF-extraction TODO are both
deprioritised below — neither has an active driver: every in-scope
subject's content is pre-segmented at ingest by its own connector.

## Provenance summary

| Component | Status | Reason |
|---|---|---|
| `connectors/base.py` | KEPT | Source-agnostic document schema; the reuse seam |
| `vectordb/store.py` | KEPT (adapted) | Stable IDs → idempotent re-ingest; Chroma metadata normalisation; feedback counters; local embeddings |
| `retriever/search.py` | KEPT (adapted) | Explainable rerank blend (sim/trust/feedback/decay); both scores retained for a Chapter 4 ablation |
| `ingest.py` | KEPT (adapted) | Trust pre-seeding re-purposed as curriculum provenance tiers |
| `api/main.py` (/health, /feedback) | KEPT | Write side of the retrieval feedback loop |
| `llm/client.py` | Pattern KEPT | Retry/backoff wrapper; provider decided — Google AI Studio / Gemini (`GeminiLLM`) |
| `config.py` | ADAPTED | Original raised on import (mutable dataclass defaults) — fixed |
| `chunking.py` | NEW (passthrough) | Helpdesk stored whole docs; passthrough is adequate for all in-scope subjects (pre-segmented at ingest) — no active driver for a real chunker right now |
| `connectors/curriculum_docs.py` | NEW | Replaces removed IT-specific connectors |
| `student_state/` | NEW | Durable per-student state — the biggest gap in the helpdesk |
| `profiles/stage1_loader.py` | NEW | Third context source (Stage 1 export) |
| `stage2_bridge/intake.py` | NEW | MATLAB file handoff; **fail-closed redaction gate** |
| `tutor/prompt_template.py` | NEW | Replaces raw-context f-string prompting; forbidden-field guard |
| `tutor/attribution.py` | NEW | Human-readable CC citations (Isaac Science CC BY 4.0, Ada CS CC BY-NC-SA 4.0 — corrected 2026-08-16, see "CC attribution" below) |
| `tutor/context_builder.py` | NEW | Three-source fusion (retrieval + lookup + injection) |
| `tutor/session.py` | NEW | Replaces Rasa + orchestrator |
| `evaluation/expert_review.py` (+ `scenarios.py`/`run_scenarios.py`) | NEW | Structured SENCO review instrument — scenario set, transcript runner, CSV review, descriptive report; live-verified 2026-08-15 |

**Removed from the helpdesk, and why:** Rasa (wrong dialogue shape for
tutoring; heavy dependency), the dead embedder/FAISS branch (placeholder
returning fake vectors; broken class definition), the duplicate
`rag_api/` stack (second Chroma client, deprecated SDK), IT-specific
connectors and web scraper, ticket agent, `chat.html`, PowerShell launcher.

## Layout

```
stage3_rag_tutor/
├── data/                    # ALL gitignored except .gitkeep — no student
│   ├── curriculum/          #   data or curriculum extracts in git, ever
│   ├── stage1/              # Stage 1 profile export lands here
│   ├── stage2_inbox/        # MATLAB writes one JSON per submission
│   └── stage2_archive/      # processed submissions move here
├── stage3/
│   ├── config.py            # env-driven; fixes helpdesk import bug
│   ├── chunking.py          # TEMPORARY passthrough — top TODO
│   ├── ingest.py            # CLI: connector → chunk → store (+ provenance scores)
│   ├── connectors/          # base ABC (KEPT) + curriculum connector
│   ├── vectordb/            # Chroma store (KEPT)
│   ├── retriever/           # reranking search (KEPT)
│   ├── student_state/       # SQLite knowledge state (NEW)
│   ├── profiles/            # Stage 1 export loader (NEW)
│   ├── stage2_bridge/       # handoff + fail-closed redact() (NEW)
│   ├── llm/                 # provider-neutral client + offline NullLLM
│   ├── tutor/               # prompt guard, context fusion, session loop
│   └── api/                 # FastAPI: /health, /feedback, /tutor (501)
├── evaluation/              # expert review capture (JSONL)
└── tests/                   # smoke tests — run offline, no API key
```

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m unittest discover tests                    # should pass immediately
# drop .md/.txt under data/curriculum/<subject>/<tier>/ then:
python -m stage3.ingest --source curriculum_docs
```

The pipeline runs offline end-to-end with `NullLLM` (no key, nothing
transmitted) once the `NotImplementedError` stubs are filled.

## Deliberate fail-closed points

This section originally tracked functions that raised `NotImplementedError`
**on purpose**, so placeholder behaviour could never silently reach
evaluated output. As of 2026-08-16, none remain — kept here as a record of
what those were and how each was actually resolved, not left open:

1. ~~`tutor.context_builder.profile_to_note`~~ **Done (2026-08-16)** — see
   the "Stage 1 wiring" section below for the full mechanism. Worth
   recording what this function was NOT, since an earlier note here said
   so at length: it is not a disability-category → scaffolding-method
   lookup (that design was rejected on SEND Code of Practice / EEF
   grounds — see
   [`docs/design/stage3-explanation-method-design.md`](docs/design/stage3-explanation-method-design.md)
   and the "Explanation-method selection" section below, which does that
   job instead). `profile_to_note` ended up being a much narrower thing:
   a `flag_status` → one-time diagnostic-opening tone note, nothing else.

`redaction.redact` (re-exported by `stage2_bridge.intake` for the Stage 2
path; also called directly by the typed-chat pipeline) is **no longer a
stub** — real layered implementation (known-names register + structured
PII regex + local spaCy NER + a curriculum-vocabulary allowlist), see
`stage3/redaction.py` and `tests/test_redaction.py`. It stays fail-closed
in spirit: a missing spaCy model raises rather than silently degrading.

`student_state.store.record_observation` / `tutor.context_builder.
summarise_state` are **also no longer stubs** (2026-08-13) — mastery is
seeded/updated by an LLM-graded diagnostic Q&A at the start of each topic
(EWMA update rule, `ALPHA=0.35`), not continuous grading of ordinary
tutoring turns. See `tutor/diagnostic.py`'s module docstring and
`student_state/store.py`'s "DECISION" note for the full mechanism and
why real Isaac/Ada question content wasn't reusable for this.

## Empty-answer failure path (fixed, 2026-08-14)

`llm/client.py::LLMClient.generate` used to return `""` on hard failure
after retries, with a docstring note that "callers must treat an empty
string as a failed turn." None of the four call sites actually checked
for it (`tutor/chat_session.py` x3, `tutor/session.py`) — caught live,
not hypothetically, while verifying explanation-method selection (see
that section below): a real Gemini failure produced a blank tutor
message that got persisted and returned as if it were a genuine answer,
and (in the diagnostic path) silently advanced the round's question
count.

Fixed at the single source, not per call site: `generate` now raises
`LLMGenerationError` on hard failure (retries exhausted, or every retry
came back empty with no exception either) instead of returning `""`. An
exception naturally skips whatever persistence would have run after
it — no blank message, no advanced diagnostic progress, no logged
explanation-method interaction for a turn that never actually happened.
`api/chat.py`'s three LLM-touching endpoints (`POST /conversations`,
`/reassess`, `/messages`) catch it and return `503` with a fixed,
friendly detail string (not the raw provider error, which could carry
internal quota/account details). The frontend needed **no changes** —
`ChatThread`'s `sendState === "error"` path, `ConversationList`'s
`createError`, and `handleReassess`'s catch block were already built
generically for "some non-501 HTTP error happened," from when the 501
fail-closed path was added.

One companion fix: `POST /conversations` now also retries the opening
diagnostic question when re-fetching an EXISTING conversation that never
got one (0 questions asked, still `pending`) — without this, a
first-creation LLM failure would leave that thread stuck forever, since
`get_or_create_conversation` only reports `created=True` once.

Verified against a **genuine** Gemini quota failure (not simulated —
the free-tier daily cap was hit live during testing): confirmed the API
returns a clean `503`, and the conversation's message count / diagnostic
progress are byte-for-byte unchanged from before the failed attempt.
Also unit-tested in isolation (`tests/test_llm_client.py`) and verified
in-process against the real `conversations.db` with a scripted
always-failing client.

## TODO index (by priority)

1. ~~`chunking.py` — real sentence-aware chunker with overlap~~
   **Retired** (2026-08-16 cleanup pass, re-scoped 2026-08-14): all three
   in-scope subjects (biology, chemistry, computer_science) come from
   Isaac Science / Ada Computer Science, both pre-segmented at ingest —
   see the curriculum-retrieval section below — so the passthrough is
   genuinely adequate for the full current scope, not just "good enough
   for now." Formally marked not-doing in the module docstring rather
   than left open; only matters again if a future source needs the
   generic `curriculum_docs.py` .md/.txt path, which nothing currently
   does (see item 7).
2. ~~`redaction.py` — redaction pass~~ **Done**: layered register + regex +
   spaCy NER + allowlist implementation (see `stage3/redaction.py`'s
   docstring for the full method and its documented limits — DOB
   detection deliberately deferred, register/allowlist collision risk
   noted). `stage2_bridge/intake.py`'s separate confidence-gate TODO
   (low-OCR-confidence handling) is still open, untouched by this. Its
   own stale `[ ] Implement redact` bullet — a leftover from before this
   item was done, since it already re-exports the real implementation —
   was removed 2026-08-16.
3. ~~`student_state/store.py` — mastery update rule + outcome scale~~
   **Done**: LLM-graded diagnostic Q&A, EWMA update, graded 0.0/0.5/1.0
   outcome scale — see `tutor/diagnostic.py` and the fail-closed section
   above. Mastery-decay-with-inactivity is a separate, still-open
   question (not part of this).
4. ~~`tutor/context_builder.py` — state summary~~ **Done** (bucketed
   text, see above). Query formulation is still open. ~~`profile_note`
   remains the one fail-closed stub~~ **Done** (2026-08-16) — see the
   "Stage 1 wiring" section below; the adaptive-teaching job it originally
   looked like it should cover is handled separately, for real, by
   "Explanation-method selection" below.
5. ~~`tutor/prompt_template.py` — pedagogy instructions~~ **Done**
   (2026-08-15) — see the "Pedagogy instructions" section below. Two
   new guarded fields also added (2026-08-14): `explanation_method`,
   `pending_understanding_check` — see the explanation-method section.
   ~~`ALLOWED_PROFILE_FIELDS` finalisation is still open~~ **Done**
   (2026-08-16) — real schema landed, and the tuple itself needed no
   change (it was already correctly scoped to just `scaffolding_note`).
6. ~~`llm/client.py` — provider decision + concrete client + token logging~~
   **Done**: Google AI Studio / Gemini via `google-genai`, `GeminiLLM`,
   token-usage logging. ~~Empty-answer failure path~~ **Done** (see
   the section above). ~~Decide tutoring temperature~~ **Done**
   (2026-08-16): 0.2, not the helpdesk's 0.3 — justified in
   `llm/client.py`'s docstring (grounded, reproducible tutoring answers
   vs. open IT-support chat). A couple of live gotchas remain noted in
   that file's TODO (pinned model IDs can 404 per-account — use
   `-latest` aliases; `total_token_count` includes untracked "thinking"
   tokens).
7. ~~`connectors/curriculum_docs.py` — PDF extraction, topic taxonomy~~
   **Retired** (2026-08-16 cleanup pass). Originally motivated by filling
   the mathematics/English content gap; that gap is now resolved by
   dropping those subjects from scope (2026-08-14 — see the scope note
   near the top of this file) rather than by building extraction.
   Formally marked not-doing in the module docstring — stays as a
   generic fallback connector with no active driver, unused by any
   currently in-scope subject.
8. ~~`ingest.py` — finalise provenance tiers~~ **Done** (2026-08-16) —
   see the justification paragraph in `ingest.py`'s own docstring
   (Isaac Science / Ada Computer Science both scored honestly under
   `third_party_education_platform`, distinct from `endorsed_textbook`).
   Optional `--reset` flag deliberately left deferred (dev convenience,
   not needed for defendability — idempotent re-ingest already covers
   that).
9. ~~`retriever/search.py` — weight tuning; decay decision for
   curriculum~~ **Done** (2026-08-16): decay kept but documented as
   currently inert for all real content (a feedback-recency decay, not a
   content-staleness one — no chunk carries `last_feedback_at` yet); a
   7-query sanity-check across all 3 subjects found sane rankings but
   also that `kb_score` is currently uniform (2.0) across the whole
   corpus, so the provenance term doesn't yet discriminate — a real
   tuning study needs provenance-tier diversity first and belongs with
   the evaluation instrument in Chapter 4, not this pass. See the
   module's own docstring for the full write-up. `difficulty_tier`
   filter was already added (see curriculum-retrieval section below).
10. ~~`api/main.py` — wire /tutor~~ **Retired** (2026-08-16 cleanup
    pass): the chat-turn path goes through `api/chat.py` /
    `tutor/chat_session.py` and is what the frontend actually calls;
    `/tutor` was an earlier single-shot sketch, now explicitly marked
    superseded rather than pending in the module docstring.
11. ~~`evaluation/expert_review.py` — scenario set + reviewer
    tooling~~ **Done** (2026-08-15) — see the "Evaluation instrument"
    section below. Rubric finalisation with the supervisor is still
    open (the CRITERIA are a working draft, confirmed with the user
    rather than blocked on a sign-off that hasn't happened yet).
12. ~~`tests/` — retrieval fixtures~~ **Done** (2026-08-16):
    `tests/test_retriever_search.py` covers `build_metadata_filter`,
    `_decay_multiplier`, `_feedback_bonus`, `_adjusted_rank_score` (18
    tests, pure-function only — `Retriever.search` itself needs a live
    store and is covered by live verification instead). Redaction suite
    reviewed and found already adequate (`tests/test_redaction.py`, 6
    tests covering register names, NER, email/phone, overlap, allowlist,
    end-to-end) — no gap found, nothing added there.

## Curriculum retrieval — core/foundation tiers

Full design: [`docs/design/stage3-curriculum-retrieval-design.md`](docs/design/stage3-curriculum-retrieval-design.md).
Adds a second retrieval source — GCSE ("foundation") content that blends
into an answer silently, with no visible level-drop, when a student has an
*evidenced* prerequisite gap (not just a single wrong answer, and not a
Stage 1 flag alone — both a subject-specific Stage 1 signal AND an
in-session prerequisite-failure signal must hold). This cuts across most of
the numbered list above, so it's tracked here as one unit rather than
scattered across files.

**Proof-of-concept done (2026-08-12): Biology, Isaac Science, core tier
only.** `connectors/isaac_science.py` pulls real content from Isaac
Science's public JSON API (not scraping — the site is a JS-rendered SPA;
confirmed directly before building), splits it at natural boundaries
(pre-segmentation, so `chunking.py`'s passthrough is adequate for this
source specifically), and tags it with `difficulty_tier="core"`,
`provenance_tier="third_party_education_platform"`, and a `topic` drawn
from `data/topics/biology.json` (now itself informed by Isaac's real
category tags, not hand-guessed). `topic` is now actually threaded through
`chat_session.run_chat_turn` → `context_builder.build_context` →
`search_kb` — previously `build_context` never passed it at all. Verified
end-to-end with a real chat turn: a question about carbohydrates correctly
retrieved all 4 sections of the ingested Carbohydrates concept and
produced a grounded, curriculum-accurate answer. See
`stage3/connectors/isaac_science.py`'s module docstring for a real,
documented gotcha (the API is version-pinned with no stable alias — same
class of issue as the Gemini model-ID one in `llm/client.py`).

**Chemistry added same day, core tier only.** Same platform, same API
shape — extended by parameterising `IsaacScienceConnector` (subject +
tag→topic map) rather than duplicating it; see `IsaacChemistryConnector`
in the same module. `data/topics/chemistry.json` has 4 topics
(`physical_chemistry`, `organic_chemistry`, `inorganic_chemistry`,
`foundations`) that map directly onto Isaac's own broad category tags —
confirmed against all 27 real Chemistry concepts before writing the map,
not guessed. 135 chunks ingested. Verified end-to-end the same way as
Biology: a live chat question about Brønsted–Lowry acids/bases correctly
retrieved the right chunks and produced a grounded answer. Two GCSE-only
concepts (`cc_equilibrium`, `cc_moles`) were correctly skipped by the
existing core-tier filter — expected, not a bug; they're foundation-tier
seed content for later.

**Ada Computer Science added (2026-08-12) — the first genuine foundation
tier.** Isaac Science was checked directly for GCSE content first (same
day) and doesn't have real foundation material for Biology (0 GCSE
concepts) or Chemistry (8 GCSE-tagged concepts, but identical text to
their A-level version — nothing simpler to blend in). `connectors/
ada_computer_science.py` — a different domain, same underlying platform —
does have it: individual accordion *sections* within a concept carry
their own audience/stage tag, and GCSE-only sections contain a genuinely
simpler technique (e.g. `number_arithmetic`: "Binary multiplication
(whole numbers)" is A-level-only long multiplication; "Binary
multiplication (left shift)" is a GCSE-only, actually-simpler shortcut).
`difficulty_tier` is therefore decided per-section here, not per-concept
like the Isaac Science connector. 1908 chunks ingested (1749 core / 159
foundation) across 7 topics (`data/topics/computer_science.json`,
informed by real tag data the same way Biology/Chemistry were — an 8th
bucket, `ai_and_machine_learning`, was added after the first ingest run
showed 539/1908 chunks unmapped; re-running with the extended map got
that down to 309, all of them genuine NEA/coursework project content
deliberately left unmapped, confirmed by inspection, not a gap). Verified
end-to-end: `search_kb(..., difficulty_tier="core")` vs.
`difficulty_tier="foundation"` for the same `concept_id` returns
genuinely different text (proven, not just structurally different), and
a live chat turn produced a grounded answer citing real chunks.

**Concept-ID granularity — resolved, but only partially, and said so.**
Isaac's own `concept_id` (e.g. `number_arithmetic`, `cb_carbohydrates`) is
now an explicit metadata field on every chunk from both connectors — the
"what is a concept relative to a chunk" question is answered. What's
*not* resolved: the design doc's `prerequisites` field wants a
cross-concept dependency graph (concept B requires concept A), and no
data source checked so far provides one. `prerequisites` is stored as
`None` everywhere — deliberately, not silently. Ada's data supports a
narrower, still-useful alternative instead: same-`concept_id`,
lower-`difficulty_tier` sections as the natural "simpler treatment" to
blend in, which is what the verification above actually tested. A real
cross-concept graph remains open and is treated like the mastery-rule
stub — a deliberate design decision for the user to make, not to invent
unilaterally.

**Known staleness (found 2026-08-14, RESOLVED 2026-08-16).**
`concept_id` was only on chunks from connector CODE written after the
field existed, not on data ingested BEFORE that code change — checked
directly against the live vectordb at the time: Ada Computer Science
chunks (ingested after `concept_id` was added) carried it correctly;
Biology/Chemistry chunks (ingested from the original Isaac Science pass,
before that field existed) came back with `concept_id: None` despite the
connector code now setting it. Fixed as a side effect of the CC
attribution re-ingest (see "CC attribution" section below, which needed
Biology/Chemistry/Computer Science re-ingested for an unrelated reason —
correcting a stale `licence` value): `python -m stage3.ingest --source
isaac_science` / `isaac_chemistry` picked up `concept_id` for free in
the same pass. Explanation-method selection is now live for all three
in-scope subjects, not just Computer Science — verified directly
post-ingest (`concept_id` populated on fresh biology/chemistry samples).

**Still fully open**, not touched by the above: the GCSE foundation tier
for Biology/Chemistry specifically (would need a different source — see
`isaac_science.py`'s TODO), and the trigger logic itself (items 6, 8, 9,
10 below). `record_observation` is no longer a blocker (see the
fail-closed section above — it's implemented) but nothing reads mastery
for a *foundation-tier* trigger decision yet; still blocked on the
cross-concept `prerequisites` graph and the Stage 1 attainment-magnitude
gap noted below.

**Two things the design doc leaves unresolved — flag before starting:**

- **Naming collision.** Resolved — `difficulty_tier`, not `tier` (would
  collide with the trust-axis `provenance_tier`).
- **Concept-ID granularity.** Resolved as far as "what is a concept" —
  see above. The `prerequisites` graph itself remains open.

**Cross-stage dependency:** the trigger's Stage 1 half needs a
per-subject *attainment magnitude* ("below demonstrated GCSE attainment for
that subject"), not just the binary `flagged` / `flag_subjects` the current
placeholder schema in `profiles/stage1_loader.py` provides. Worth raising
with whoever owns the Stage 1 export shape before that's fixed.

Work items, roughly in dependency order:

1. [x] Naming collision resolved (`difficulty_tier`, not `tier`).
   Concept-ID granularity resolved (`concept_id` field, both connectors).
   Cross-concept `prerequisites` graph **still unresolved** — deliberately
   deferred, not blocking anything currently built.
2. [x] `connectors/isaac_science.py` (Biology, Chemistry — core tier only,
   real public JSON API, no scraping) and `connectors/
   ada_computer_science.py` (Computer Science — core **and** genuine
   foundation tier) both done. All three subjects sourced.
3. [x] Chunk metadata schema extended and now consistent across all three
   subjects: `difficulty_tier`, `level`, `topic`, `concept_id`,
   `spec_code`, `misconceptions`, `prerequisites` all present
   (`spec_code`/`misconceptions`/`prerequisites` are `None` — not
   available from either source, not guessed).
4. [x] `ingest.py` — `third_party_education_platform` tier covers both
   sources honestly (score 2.0, same as `endorsed_textbook`).
5. [x] Resolved differently than expected: both connectors do
   source-structure-aware pre-segmentation themselves (one document per
   natural section, Ada's additionally split by difficulty_tier), so
   `chunking.py`'s passthrough is adequate for both. The general chunker
   (item 1 in the TODO index above) is still needed for prose-only
   sources.
6. [x] (partially) `student_state/store.py::record_observation` is
   implemented (LLM-graded diagnostic Q&A, EWMA — see fail-closed
   section above) — but it records mastery per (student, subject, topic),
   not per prerequisite *concept*. Tracking prerequisite-concept failure
   specifically (the in-session half of the trigger) is still blocked on
   the cross-concept `prerequisites` graph, which remains unresolved.
7. [x] `topic` threaded through `chat_session` → `context_builder` →
   `search_kb` end-to-end (verified). `difficulty_tier` filtering also
   done — `retriever/search.py`'s `search_kb`/`Retriever.search`/
   `build_metadata_filter` all accept it now, verified directly against
   real core-vs-foundation content. **Not** wired into
   `context_builder.build_context` automatically — that's item 8, and
   still needs item 6 first.
8. [ ] `tutor/context_builder.py` — the two-part trigger itself. Not started.
9. [x] `tutor/prompt_template.py` — foundation-blend pedagogy
   instructions **Done** (2026-08-15, see the "Pedagogy instructions"
   section below): SYSTEM_PROMPT now explicitly forbids any
   meta-commentary about level when curriculum extracts mix levels —
   relevant today, not just once item 8's trigger exists (live
   evaluation already showed foundation content surfacing via ordinary
   retrieval with no explicit filter). CC attribution format **Done**
   (2026-08-16, see the "CC attribution" section below) — real
   human-readable citations, not just internal doc IDs, now flow all
   the way to the frontend.
10. [x] Tier-contribution logging — **Done** (2026-08-15), as part of
    the evaluation instrument (see below): `evaluation/run_scenarios.py`
    records `tiers_used` per transcript, derived from the real
    `difficulty_tier` on whatever chunks `search_kb` actually returned
    — not simulated. Live-verified: one real scenario
    (`cs_cybersecurity_established_scaffold`) naturally pulled BOTH
    `core` and `foundation` chunks with no explicit filter, giving
    the SENCO reviewer a genuine (not staged) case to assess for "does
    invisible blending read naturally."

The topic-list-drift concern noted here previously is resolved for Biology
**and Chemistry**: both `data/topics/biology.json` and
`data/topics/chemistry.json` are informed by each subject's real Isaac
category tags rather than hand-guessed —
`connectors/isaac_science.py::_TAG_TO_TOPIC_BY_SUBJECT` (now keyed per
subject, not a single flat dict) is the mapping to keep in sync as more
content/subjects are added.

## Explanation-method selection

Full design: [`docs/design/stage3-explanation-method-design.md`](docs/design/stage3-explanation-method-design.md)
(status: decided). Implements the last piece of the "three context
sources" argument in `tutor/context_builder.py`'s knowledge-state source
— see the fail-closed section above for why this supersedes, rather than
implements, what `profile_to_note` was originally scoped to be.

**Mechanism**: `student_state/explanation_method.py` tracks, per
(student, method), a Beta(α, β) posterior over whether one of 6 fixed
explanation methods (worked example, analogy, step-by-step scaffold,
visual/diagrammatic, Socratic questioning, chunking) has worked for that
student. Each normal tutoring turn — never the diagnostic turns, a
separate mechanism — Thompson-samples one method (a draw per method,
argmax wins; not highest-mean, so exploration survives) and instructs
the LLM to use it. Whether the student's *next* answer on the *same*
concept demonstrates understanding is graded by the same LLM call that
generates the next tutoring reply (a trailing `[[UNDERSTANDING:
yes|no]]` marker, stripped before display — mirrors `tutor/
diagnostic.py`'s `[[MASTERY_SCORE: x]]` pattern, chosen specifically to
avoid a second LLM call every turn) and closes the loop via a
Beta-Bernoulli update.

**Cold-start prior**: uniform `Beta(1, 1)` for every method until real
cohort data exists — confirmed with the user rather than inventing
numeric priors attributed to EEF's guidance, which doesn't actually
publish per-method success rates for this taxonomy. Neutral is the
honest default; differentiation only emerges from real data.
`recompute_cohort_priors()` aggregates graded interactions across all
students into a per-method cohort prior — manual/periodic (no scheduler
in this project; run via `python -m stage3.student_state.
explanation_method`), same as `ingest.py`.

**Concept resolution reuses `concept_id`** (see the curriculum-retrieval
section above) rather than building new concept-tracking machinery — the
top retrieved chunk's `concept_id` is "the concept this turn is about."
Was live-verified as only populated for Computer Science at the time
this was built (see the "Known staleness" note above) — resolved
2026-08-16 via re-ingest (see "CC attribution" below); now live for all
three in-scope subjects.

**Explicitly not done this pass** (the design doc's own "Open items",
not a new deferral): the retention signal (`correct_retention` /
`retention_gap_days` stay schema-only — the doc itself leaves "how long
counts as retention" undefined); splitting the (student, method)
posterior by subject/concept instead of student-level (doc says start
coarse); any frontend surface for this (backend/prompt mechanism only,
same as the mastery EWMA before its own UI banner was added later).

**Live-verified (2026-08-14), and honestly what wasn't.** A fresh
Computer Science topic thread correctly resolved `concept_id=
"search_binary"` across three real turns, Thompson-sampled a method each
time (observed two different real draws — `chunking`, then
`visual_diagrammatic` twice — proving selection isn't hardcoded), and
logged each as a pending interaction, all confirmed via direct reads of
`method_interactions`/`method_posterior` in `data/student_state.db`, not
just API responses. The `[[UNDERSTANDING: ...]]` marker never leaked
into any visible chat response across multiple real turns. What did
**not** get a live round-trip: a *successful* grading pass (i.e. a real
non-empty LLM reply carrying the marker, parsed and fed into
`record_understanding`) — two live attempts both hit Gemini's free-tier
`generate_content_free_tier_requests` daily quota (20/day observed on
this key) mid-session, so `GeminiLLM.generate` returned `""` both times
and, correctly, no observation was guessed (`understood is None` →
skipped, exactly per the fail-safe design — itself a real, if
accidental, live demonstration of that fail-safe working). **Note**:
that "`generate` returns `""`" behaviour is itself what got fixed
immediately after, in the "Empty-answer failure path" section above —
`generate` now raises instead, so a repeat of this exact scenario today
would surface as a clean `503` (no message persisted, no method
interaction logged for that turn at all) rather than a turn that
completes with a silently-skipped grading. That specific leg (marker
parsing + the Beta-Bernoulli update it triggers) is instead covered
exhaustively offline in `tests/test_explanation_method_store.py`
(well-formed/malformed/missing marker, exact alpha/beta arithmetic).
Worth re-confirming live once the quota window resets. The live session
also surfaced one unrelated pre-existing issue: a stale
`uvicorn --reload` worker that hadn't picked up any of this session's
code changes (schema included) — fixed by a clean process restart, not
a bug in this change.

## Evaluation instrument

Turns `evaluation/expert_review.py` from a skeleton (a placeholder
rubric + a JSONL append function, nothing runnable) into something a
real reviewer can actually use. Confirmed with the user before building
(2026-08-14): reviewer interface is CSV export/import (the reviewer is
the school SENCO — identified by role only, `ReviewRecord.reviewer_role`,
never by name, in any code/data/artifact), the 5 placeholder criteria are a working
draft to build against rather than a blocker on supervisor sign-off, and
the first scenario set was drafted by Claude for the user to edit.

**Mechanism**: `evaluation/scenarios.py`/`scenarios.json` hold 6 fixed,
synthetic scenarios (2 each for biology/chemistry/computer_science — the
3 in-scope subjects; see the scope note near the top of this file),
varying cold-start-vs-established mastery and no-note-vs-scaffolding-note
so `adaptivity` has something real to react to.
`evaluation/run_scenarios.py` runs each one through the SAME building
blocks a real tutoring turn uses (`search_kb` → `summarise_state` →
`build_prompt` → `llm.generate`) — deliberately NOT through
`chat_session.run_chat_turn`, which is wired to a real `student_id`
(mastery writes, explanation-method Thompson sampling); routing
synthetic scenarios through it would pollute real per-student tables and
burn real Thompson-sampling draws for nothing. This also cleanly
sidesteps `profile_to_note` entirely (real now, see "Stage 1 wiring"
below, but only ever called from diagnostic-opening, not this path) —
`profile_note` is built directly from each scenario's `scaffolding_note`
and passed straight to `build_prompt`, whose `profile_note` parameter
is unaffected by that change.
`expert_review.py` then does `export_review_csv()` (one row per
scenario × criterion, transcript inline, rating/comment blank),
`import_review_csv()` (reads a filled sheet back in, `reviewer_role`
fixed at `"SENCO"`), and `generate_report()` (descriptive-only —
n/mean/range per criterion plus every comment quoted verbatim, no
significance claims, matching the single-reviewer analysis plan).

**Live-verified end-to-end, 2026-08-15.** Found and fixed a real bug
along the way: Gemini's free tier has a SECOND cap beyond the
already-known 20/day — 5 requests/MINUTE — which firing all 6 scenario
calls back-to-back tripped immediately (`GenerateRequestsPerMinute
PerProjectPerModel-FreeTier`). Fixed in `run_scenarios.py` with a 15s
inter-scenario delay (NOT in `LLMClient.generate`'s own retry policy —
a real single tutoring turn should still fail fast, only this batch
script's rapid-fire pattern needed pacing) — documented in both modules.
Also changed `run_scenarios.py` to write transcripts incrementally
(flushed after each scenario) rather than all at once, so a later
failure can't discard already-succeeded, quota-expensive calls.

With that fixed, all 6 scenarios ran for real: every answer was
correctly grounded (checked directly — e.g. the disaccharide question
correctly named a condensation reaction releasing water; the Caesar
cipher question correctly described the shift-substitution mechanism).
No `[[UNDERSTANDING:...]]`/`[[MASTERY_SCORE:...]]` markers leaked in
(expected — this path never requests them). One scenario
(`cs_cybersecurity_established_scaffold`) naturally pulled BOTH `core`
and `foundation` chunks with no explicit tier filter — a genuine,
un-staged example of the tier-blending question the curriculum-retrieval
design doc raised, now logged via `tiers_used` and ready for the SENCO
reviewer to actually assess. CSV export produced the correct 30 rows (6 scenarios ×
5 criteria); a simulated filled sheet round-tripped correctly through
import and `generate_report()`. The simulated ratings were then deleted
before committing anything further — fabricated data under
`reviewer_role="SENCO"` has no business sitting in files whose real
counterpart gets archived to UEL OneDrive per the RDM requirements;
`evaluation/review_sheet.csv` is left as a clean, blank sheet against
the real transcripts, ready for the actual review session.

**Still open**: rubric finalisation with the supervisor (small edit to
`CRITERIA` when it happens, not a rebuild); consent/information-sheet
references (not this project's to write); a genuinely bigger scenario
set if 6 turns out to be too thin for a defensible Chapter 4 account.

## Pedagogy instructions

`tutor/prompt_template.py`'s `SYSTEM_PROMPT` was one placeholder line
("work step by step and check understanding") until 2026-08-15. Now a
real, literature-grounded instruction set — see that module's docstring
for the full reasoning. Grounded in VanLehn (2011), already cited in
Chapter 2 as the effectiveness benchmark:

- **Guide before telling**: default to a hint, leading question, or just
  the first step, rather than the full answer immediately — matches
  VanLehn's finding that hint-based/step-based tutoring outperforms
  answer-only tutoring. Explicitly worded to DEFER to a per-turn
  `explanation_method` instruction when Thompson sampling picked one
  (see the "Explanation-method selection" section above) — `worked_
  example` deliberately wants the opposite (answer shown up front), and
  needs to win when it's selected.
- **Step-based for multi-part questions, direct for simple ones**: work
  through multi-step/multi-part questions step by step with a check in
  between, but don't manufacture artificial steps for a single short
  factual question. This was a real design tension worth stating
  explicitly rather than leaving to LLM style — it also gives the
  expert-review rubric something concrete to score `clarity` against.
- **Never signal a level drop** when curriculum extracts mix levels
  (see the "Pedagogy" bullet in the curriculum-retrieval section above)
   — baked in now even though the deliberate foundation-tier trigger
  isn't built, because live evaluation already showed foundation content
  can surface via ordinary retrieval with no explicit filter.
- **Chunk token budget**: `MAX_CHUNK_CHARS = 2000` per retrieved chunk,
  calibrated against real ingested chunk lengths checked directly (not
  guessed) — observed range 222–6413 characters, median ~1163, across
  the 24 grounding chunks from the evaluation instrument's live run.
  2000 keeps the large majority of real sections intact while stopping
  the small number of outliers (several over 3000, one at 6413) from
  crowding out the other `top_k` results in the prompt.

**Live-verified, 2026-08-15**, against two real contrasting questions
(not just unit tests): a multi-part algorithms question ("why is binary
search faster, and what's the time complexity of each?") produced a
correctly step-structured, guiding-questions-first response that
withheld the direct answer as instructed; a simple factual question
("what does HTTPS stand for?") correctly got a direct answer with no
artificial step-manufacturing — confirming the "don't overdo it" carve-out
actually works, not just the main rule.

CC attribution format was deliberately scoped OUT of this pass — a
provenance/citation-surfacing change (chunk metadata → a new
`BuiltPrompt` field → `api/chat.py` → the frontend), not a
prompt-wording one, kept separate so this change stayed reviewable on
its own. Done the next day — see the "CC attribution" section below.
`ALLOWED_PROFILE_FIELDS` finalisation and `profile_to_note` were both
resolved later, 2026-08-16 — see "Stage 1 wiring" below.

## CC attribution

Isaac Science and Ada Computer Science content both require real
Creative Commons attribution + link-back wherever it surfaces in tutor
output — a licensing obligation, not optional polish. Before this
(2026-08-16), the only "provenance" exposed anywhere was
`chunk_doc_ids` — internal store IDs like
`isaac_science:cb_carbohydrates__0#0` — and the frontend was already
rendering them raw and unhelpfully as a comma-joined "Sources:" line.

**A real bug found immediately before building this, not after**: both
connectors had the WRONG licence hardcoded, inherited from the original
design doc's unverified assumption. A plain fetch of either site only
ever returns the JS SPA shell (no licence text) — the same wall the
connectors' own research already hit, confirmed again independently.
Settled via a headless-browser render of multiple real concept pages and
both homepages: **Isaac Science is CC BY 4.0** (no NonCommercial or
ShareAlike clause — more permissive than assumed), **Ada Computer
Science is CC BY-NC-SA 4.0** (does carry a NonCommercial clause) — the
two are effectively swapped relative to the original design-doc guess
(CC BY-NC-SA / CC BY-SA respectively). Fixed at the source: both
connectors, their tests, the curriculum-retrieval design doc, and this
README are all corrected — see `isaac_science.py` / `ada_computer_
science.py`'s "CORRECTED" docstring notes. Chunks ingested before the fix
carried the old (wrong) value in stored Chroma metadata until a re-ingest
happened — see "Re-ingested, 2026-08-16" below; RESOLVED same day, not an
outstanding gap.

**Mechanism**: new module `tutor/attribution.py` — a hardcoded, CONFIRMED
`SOURCE_ATTRIBUTION` mapping keyed by the chunk's `source` field
(reliable regardless of ingest staleness — set once at ingest, never
touched by the licence bug), deliberately NOT reading the chunk's own
(possibly stale) `licence` field. `build_attributions(chunks)` recovers
a human title from `section_title` (the connectors insert the plain
concept title as each concept's first section — splitting on " — "
recovers it without a new metadata field), dedupes by `source_url` (a
concept retrieved via several chunks is cited once), and returns
`{title, source_name, source_url, licence, licence_url}` per citation.
Shared by both `prompt_template.py` (normal turns) and `diagnostic.py`
(diagnostic turns — grounded in the same licensed content, previously
overlooked). Computed ONCE at message-creation time and stored alongside
`chunk_doc_ids` in `conversations.db` (new `attributions` column) —
never re-derived on read, so a historical message stays accurate to what
was actually shown even if source data changes later, same pattern
`chunk_doc_ids` already used.

**Live-verified end-to-end, 2026-08-16**: a real diagnostic round and a
real normal tutoring turn on Computer Science / Cyber Security both
produced correct citations via the API (e.g. 4 `chunk_doc_ids` correctly
deduped to 3 unique citations with the right titles/licence/URLs) — then
confirmed VISUALLY in the actual running frontend via a headless-browser
screenshot: real citations like "Defence against malware — Ada Computer
Science (CC BY-NC-SA 4.0)" with working links, replacing the old raw
doc-ID dump. 173/173 tests pass (16 new, across a new `test_attribution.py`
plus extensions to the conversations-store, diagnostic, and prompt-guard
suites). Frontend typechecks clean.

**Re-ingested, 2026-08-16, for defendability** (stored data now matches
the corrected facts, not just the code): `python -m stage3.ingest
--source isaac_science / isaac_chemistry / ada_computer_science`, all
three. Idempotent by design (`_stable_doc_id` composes `source:id`, so
re-ingestion UPDATES existing Chroma documents rather than duplicating
them) — confirmed directly: total chunk count unchanged before/after
(2085), and each source's known count matched exactly (biology 42,
chemistry 135, computer science 1908 from 344 concepts — matching the
original ingest's own reported numbers). Verified the `licence` field
directly post-ingest: biology/chemistry now `CC-BY-4.0`, computer
science now `CC-BY-NC-SA-4.0`. Real side benefit: biology's `concept_id`
field — separately known-stale since before this field existed on that
connector, see the explanation-method section above — is now populated
too, for free, from the same re-ingest. 173/173 tests still pass.

**Independently re-confirmed, 2026-08-16** (a later session, checking the
background re-ingest task's own completion rather than trusting the
paragraph above from memory): queried the live vectordb directly —
2085 chunks total (unchanged), all 1908 `ada_computer_science` chunks
carry `licence: CC-BY-NC-SA-4.0` uniformly, all 177 `isaac_science`
chunks (42 biology + 135 chemistry) carry `licence: CC-BY-4.0`
uniformly. Full test suite re-run clean (193/193, grown since the 173
figure above from the later usability pass — see that section).

~~**Still open**: `ALLOWED_PROFILE_FIELDS` finalisation (blocked on the
Stage 1 export schema)~~ **Resolved 2026-08-16** — see "Stage 1 wiring"
below.

## Usability pass — click-to-run scripts, searchable student picker, mastery indicator

Three changes (2026-08-16), aimed squarely at anyone who isn't the
developer running this — an examiner, a supervisor, anyone else who
clones the repo.

**Click-to-run scripts**: `start.bat` / `stop.bat` at the repo root
(double-click entry points; Windows' default execution policy usually
blocks a bare `.ps1` from running on double-click, so these are thin
shims over the real logic in `scripts/start.ps1` / `scripts/stop.ps1`).
`start.ps1` fails loud with a clear pointer if the one-time setup (venv/
requirements, `npm install`) hasn't happened, starts both servers
detached via `Start-Process -PassThru`, records PIDs in `.run/`, polls
`/health` then the frontend URL, and opens the browser. `stop.ps1` kills
by PID-file first (`taskkill /T` — tree-kill matters, since `uvicorn
--reload` and `npm run dev` both spawn children a plain `Stop-Process`
would orphan), then falls back to checking ports 8000/5173 directly so it
cleans up correctly even if the servers were started the old manual way.
That fallback isn't theoretical — it was needed and exercised during this
change's own live verification, catching a leftover process the PID file
alone didn't track. See `RUNNING.md`'s "Quick start" section.

**Searchable student picker**: there is no login anywhere in this
prototype by design (`student_id` is a freely-typed pseudonymous
identifier), which meant the old `StudentIdBar` was a bare text box with
nothing to search against — correctly flagged as unusable unaided. New
`GET /students` (`stage3/api/students.py`, backed by a new
`conversations/store.py::list_student_ids` — distinct student_ids that
have ever started a conversation, the only honest source of "known
students" available) feeds a new hand-rolled combobox,
`components/StudentSelect` (no UI library anywhere in this frontend —
matches the existing convention): shows the full list on focus, filters
as you type, and still commits a brand-new never-seen id freely on Enter/
blur/an explicit "Use new ID" row — a new student is the normal case
here, not an edge case.

**Per-subject/per-topic mastery indicator**: `student_state/store.py`'s
`get_knowledge_state` already computed exactly this (EWMA mastery per
student/subject/topic) but was never exposed anywhere — no API endpoint,
no UI. New `GET /students/{id}/mastery` is a thin read-through to it.
Rather than a separate dashboard page, the indicator (`components/common/
MasteryBar`, a small red-to-green bar, grey/empty for "no check-in yet")
is shown inline: a per-subject rollup in the `Sidebar`, a per-topic value
in `ConversationList` — visible exactly where a student is already
choosing what to work on next. Refreshed via the same `refreshToken`
convention `App.tsx` already used for conversation-list refresh (a new
`ChatThread` `onActivity` callback bumps it after every send/reassess,
since a diagnostic round completing is exactly the kind of event that
should refresh both).

**Synthetic demo-data seed script** (`scripts/seed_demo_students.py`):
a fresh clone has no students at all, so the picker/indicator above would
otherwise start completely empty. Seeds three clearly-fake students
(`demo-student-1/2/3`, deliberately varied — one strong-in-biology/
weak-in-CS with chemistry untouched, one balanced across all three
subjects, one just-started with a single topic) via the SAME real store
functions a live turn uses (`get_or_create_conversation`, `add_message`,
`record_observation`), just with synthetic inputs — not a fabricated
parallel data shape, and zero LLM calls (the Gemini free-tier daily quota
is a real, documented constraint; seeding three students' worth of live
diagnostic rounds would burn a meaningful fraction of it for a UI
convenience). `record_observation` is tagged `source="demo_seed"`,
distinct from real `source="diagnostic"` rows, so the two can never be
confused in the data. Each seeded topic's tutor message attaches REAL
citations (via `search_kb` + `build_attributions` — both local/offline,
no LLM) so the citation UI is demoable too. **Fabricated, synthetic —
never dissertation evidence**; `evaluation/`'s real scenario runner is
completely untouched by this. Idempotent (`--reset` for a clean re-run).

Live-verified: full test suite (193/193, 6 new — `list_student_ids`
coverage), `npx tsc --noEmit` clean, both new endpoints checked live via
curl, a full `start.ps1` → `stop.ps1` cycle (including the port fallback
actually firing, see above), and a headless-browser screenshot of the
picker filtering across the seeded demo students and the mastery bars
showing a real mixed spread (strong/weak/no-data all visible at once on
`demo-student-1`).

## Stage 1 wiring (2026-08-16)

The last remaining fail-closed stub, `profile_to_note`, is real now — the
user supplied a synthetic fixture produced by their own Stage 1 pipeline
(`data/stage1/stage1_profiles.synthetic.csv`; not real student data, not
bound by a data-management agreement — confirmed by the user, hence
committed rather than gitignored like the real-export path). Full spec
of what was asked for is in
[`stage3-stage1-schema-requirements.md`](docs/design/stage3-stage1-schema-requirements.md);
this is the record of what was actually built against the real schema
that landed.

**Schema**: one row per (student_id, subject) — `flag_status`
(`none`/`provisional`/`confirmed`) and `attainment_band`
(`well_below`/`below`/`in_line`/`above`), both already coarse categories.
Resolves the schema doc's open question directly: Stage 1 resolves
magnitude internally before ever assigning a flag, so no raw residual
reaches Stage 3 at all.

**A real design correction found before building this, not after**:
checked directly (not assumed) where `context_builder.py::build_context`
is actually called from — only ever `chat_session.py::run_chat_turn`'s
NORMAL-turn branch, which is only reachable once a topic's diagnostic
has already completed and already written real mastery data. Gating
`profile_to_note` there (the original plan) would have been dead code —
by the time that path runs, it's structurally never cold start for that
topic anymore. The genuinely cold-start moment is diagnostic START
(`chat_session.py::start_diagnostic`), which took no `student_id`/
`profiles` at all before this. Also checked: every LLM call here is
built fresh per turn with no running memory between calls, so a note
injected only at diagnostic-opening has zero automatic carry-over into
normal tutoring afterward — confirmed with the user which of two designs
they wanted (diagnostic-opening only vs. also re-injecting into the
first few normal turns); decided on the narrower one, **plus** using the
same data to pre-seed an initial mastery estimate, which the user
proposed as a way to get a lasting-but-fading effect through the
existing EWMA rule instead of through prompt text.

**Mechanism — two Stage 1 fields, two genuinely separate purposes**:
- `flag_status` → `profile_to_note` → a one-time TEACHING NOTE rendered
  into the diagnostic's OPENING question prompt only (`tutor/
  diagnostic.py::build_opening_prompt`, reusing `prompt_template.py`'s
  existing `_guard`/`ALLOWED_PROFILE_FIELDS` guard directly rather than
  duplicating it) — shapes tone for that one question, nothing else.
  `none` or an unrecognised value both fail closed to no note.
- `attainment_band` → `attainment_band_to_prior` → a numeric mastery
  estimate (`well_below→0.15, below→0.3, in_line→0.55, above→0.8`,
  chosen to land inside `summarise_state`'s existing 0.4/0.75 bucket
  boundaries) written via new `student_state/store.py::
  seed_mastery_prior` BEFORE the diagnostic's first answer — `n_obs=0`,
  can never overwrite a real row (`ON CONFLICT ... DO NOTHING`). The
  first real diagnostic answer blends into it via the existing EWMA
  branch, not a fresh cold start — so the Stage 1 signal fades as real
  evidence accumulates, exactly matching "only guides cold start, then
  the app already guides itself" (the user's own framing, confirmed
  correct once the diagnostic-vs-normal-turn distinction above was
  found). Independent of `flag_status` — every student with attainment
  data gets a prior, not just flagged ones.

Both only ever fire from `api/chat.py::post_conversation`'s genuine
first-creation path — deliberately NOT from `/reassess` ("Re-check my
understanding"), since a re-check means the student already has
tutoring history and this is no longer cold start in the intended sense.

**Live-verified, 2026-08-16, with real LLM generation** (not a dry run —
the user specifically asked for proof via real generation, not just unit
tests): three synthetic ids, one per `flag_status`, all Biology so only
the profile differed. `SYN0001` (`none`/`above`): prior seeded `0.8`, no
TEACHING NOTE, real question generated normally. `SYN0008`
(`provisional`/`in_line`): prior seeded `0.55`, TEACHING NOTE reached the
LLM, real question generated normally. `SYN0010`
(`confirmed`/`well_below`): prior correctly seeded `0.15` BEFORE the LLM
call — then the call itself hit a genuine exhausted daily Gemini
free-tier quota (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`,
20/day), raising `LLMGenerationError` cleanly (see "Empty-answer failure
path" above) rather than corrupting anything. That conversation is left
in exactly the state `post_conversation`'s existing retry logic already
handles (0 questions asked, still `pending`) — safe to retry once quota
resets, no manual fix needed. 2 of 3 cases fully round-tripped with real
generation; the 3rd demonstrated the fail-loud path working correctly
under a real, external, already-documented constraint, not a bug. 215/215
tests pass (22 new).

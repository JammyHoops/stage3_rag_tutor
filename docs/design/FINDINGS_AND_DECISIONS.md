# Stage 3 — findings and design decisions

Consolidated record of *why* things are built the way they are: component
reuse against AI_IT_Helpdesk, decisions made along the way, and findings
from checking things directly rather than assuming them. Written to be
lifted into the dissertation (Chapter 3 component-reuse account, Chapter 4
findings) rather than left scattered across module docstrings. Code should
carry only what-it-does comments now; the reasoning lives here.

Organised by subsystem, not chronologically. Each entry keeps the module(s)
it came from so it's traceable back to the code.

## 1. Component reuse from AI_IT_Helpdesk

The Stage 3 skeleton was built by auditing AI_IT_Helpdesk (a prior
project) and deciding per-component whether to keep, adapt, or replace it.
Every module in `stage3/` still carries a KEPT / ADAPTED / NEW provenance
line for this reason — that framing is a deliberate methodology device,
not incidental documentation.

**Kept near-verbatim:**
- `connectors/base.py` — the connector abstraction (normalise every source
  into `{id, text, source, metadata}`) is source-agnostic; the helpdesk
  used it to mix Spiceworks tickets, vendor docs and transcripts, Stage 3
  uses the same seam to mix awarding-body specs, mark schemes and teacher
  material.
- `vectordb/store.py` — `_stable_doc_id` (composes `source:id` so
  re-ingestion updates rather than duplicates, making ingest idempotent)
  and `_normalize_metadata` (Chroma only accepts str/int/float/bool/None
  metadata values) both carried over as-is. Local sentence-transformers
  embeddings kept too — nothing leaves the machine at embedding time.
- `retriever/search.py` — the rerank formula
  (`similarity*0.70 + provenance_trust*0.25 + feedback*0.05, * time_decay`)
  is the most defensible part of the helpdesk design: every term is named
  and tuneable rather than a black box, and both raw distance and adjusted
  score are retained on every result specifically to support a
  reranker-vs-raw-similarity ablation later at no extra cost.

**Adapted:**
- `config.py` — the original raised `ValueError: mutable default` on
  import under Python 3.11+ (dataclass fields using nested dataclass
  instances as defaults); fixed with `field(default_factory=...)`. Unused
  FAISS settings removed — Chroma is the only vector store.
- `ingest.py` — the trust pre-seeding mechanism (writes `kb_score` +
  zeroed feedback counters at ingest time) is kept; in the helpdesk,
  resolved tickets outranked vendor docs, here the same mechanism encodes
  curriculum provenance (awarding-body material outranks teacher-made
  material at comparable similarity).
- `llm/client.py` — the retry-with-backoff pattern and the rule that
  vendor specifics stay inside the provider subclass both carried over;
  the concrete Gemini binding did not (see §7).

**Deliberately not carried over:**
- Rasa (intent classification + story-based dialogue) — wrong shape for
  open tutoring dialogue, where a turn isn't one of a small fixed intent
  set; also a heavy, version-brittle dependency. `tutor/session.py`.
- The helpdesk orchestrator's raw-context prompt assembly
  (`f"Raw context: {context}"`) — replaced by the guarded, named-field
  prompt builder in `tutor/prompt_template.py` (see §6). This was a real
  privacy risk found while auditing, not a style preference: that dict
  would have carried the student identifier and Stage 1 data straight to
  a cloud LLM.
- The duplicate `services/rag_api/` stack — re-implemented ingestion,
  chunking and prompting against a second Chroma client and a deprecated
  SDK. One stack only in Stage 3.

## 2. Curriculum sourcing (Isaac Science, Ada Computer Science)

Both isaacscience.org and adacomputerscience.org are JS-rendered SPAs — a
raw HTML fetch returns an empty shell. Confirmed directly (headless
browser + network inspection) before writing either connector; both call
a real, public, unauthenticated JSON API instead
(`GET /api/{version}/api/pages/concepts...`). Both APIs are version-pinned
in the URL with no stable `-latest` alias — the same class of gotcha as
the Gemini model-ID issue (§7), except there's no escape hatch here. If a
connector starts failing, load the real site with devtools open and find
the current version string; there's no cleaner discovery method.

**GCSE ("foundation") content**: checked directly against the live API
rather than assumed. Isaac Science has zero GCSE-stage Biology concepts,
and Chemistry's 8 GCSE-tagged concepts share identical text with their
A-level version — nothing simpler to blend in. Real foundation content
only exists on Ada Computer Science, where individual accordion sections
carry their own `audience` list and GCSE-only sections really are a
simpler technique, not re-tagged prose (confirmed example: "Binary
multiplication (whole numbers)" is `a_level`-only, "Binary multiplication
(left shift)" is a genuinely different, simpler `gcse`-only technique).
This is why Ada is the only connector with a real `difficulty_tier=
"foundation"` output.

**Licence correction**: the original design doc's assumed licences were
swapped relative to reality. Confirmed via headless-browser render of
multiple concept pages + each homepage: Isaac Science is **CC BY 4.0**
(no NonCommercial/ShareAlike clause), Ada Computer Science is
**CC BY-NC-SA 4.0** (does carry NonCommercial) — the reverse of the design
doc's guess. Both connectors were re-ingested the same day the fix
landed (idempotent upsert — chunk counts unchanged, confirming the
re-ingest genuinely updated existing entries rather than duplicating).

**Content segmentation**: rather than one document per whole concept fed
to a generic chunker, both connectors split each concept at its own
natural boundaries (top-level intro + each accordion sub-section) and
return one document per section. This is why `chunking.py`'s passthrough
"chunker" is adequate for both sources — the structure-aware splitting
already happened at ingest.

**concept_id vs. prerequisites**: `concept_id` is stored explicitly on
every chunk from both sources, resolving the concept-ID granularity
question the design doc originally left open. What's *not* resolved is a
cross-concept `prerequisites` graph — Ada's data gives same-concept,
lower-difficulty sections, not a dependency graph between different
concepts, and no ingested source provides one. This is the one genuine
blocker on the foundation-tier retrieval trigger (see `docs/TODO.md`).

## 3. Provenance ranking

`ingest.py::PROVENANCE_SCORES` orders `awarding_body_spec` (3.0) >
`mark_scheme` (2.5) > `endorsed_textbook` / `third_party_education_
platform` (2.0 each) > `teacher_material` (1.5) > unassigned (0.5).
Isaac Science and Ada Computer Science are both scored under
`third_party_education_platform` rather than folded into
`endorsed_textbook` — curated and Cambridge-vetted, but not
awarding-body endorsed, so a distinct label is the honest position when
only two real sources exist at this tier. `awarding_body_spec`/
`mark_scheme` sit above both on the same authority argument, kept for a
future source rather than tuned against real data yet.

**Weight sanity-check (2026-08-16)**: ran 7 real questions across all 3
subjects through `search_kb` against the live corpus and inspected raw
similarity vs. adjusted `rank_score` ordering. Finding worth recording
honestly: `kb_score` is currently 2.0 on every chunk in the corpus (no
`awarding_body_spec`/`mark_scheme` source has been collected yet), so the
provenance term is a constant offset right now and doesn't discriminate
between candidates — observed ranking was effectively similarity-driven.
Expected, not a bug: the term starts discriminating the moment a
higher/lower-tier source is added. Ordering was sane in all 7 cases within
that constraint. This was a sanity check, not a tuning exercise — a real
blend-weight study belongs with the evaluation instrument once there's
provenance-tier diversity in the corpus to tune against.

**Decay is currently inert, on purpose**: `_decay_multiplier` only
discounts chunks carrying `last_feedback_at`, and no curriculum chunk has
that field yet (feedback semantics are still undefined — see
`docs/TODO.md`). So `time_decay == 1.0` for all real content today. Framing
for write-up: this is a *feedback-recency* decay (a chunk whose feedback
signal is stale should count for less), not a *content-staleness* decay —
curriculum specifications don't go stale the way a helpdesk ticket fix
does, and the mechanism was never meant to imply otherwise.

## 4. Privacy and redaction

`redaction.py`'s three-layer design (register, structured-PII regex, local
spaCy NER) plus an allowlist override exists because a single approach
fails somewhere:

- A blind "strip capitalised words" heuristic would wrongly redact
  legitimate STEM vocabulary (Newton, DNA, Pythagoras, Ohm).
- An exact-match known-names register alone only catches names actually
  on the list — it doesn't satisfy the module's own guarantee that
  unredacted text must never reach a cloud LLM, unconditionally (a
  friend's name, an unregistered sibling, an OCR-garbled name would all
  slip through). Local spaCy NER closes that gap.
- NER alone reintroduces the original problem in miniature: a scientist's
  eponym ("Newton's third law") is grammatically identical to a
  person-possessive, so generic NER may tag it PERSON. The allowlist
  (committed curriculum vocabulary, not student data) suppresses this.
  Documented trade-off, stated rather than hidden: a student literally
  named e.g. "Newton" would have that name protected from redaction by
  mistake — narrow and real.

All three layers run independently against the original text and are
merged as spans (never sequentially, so one layer's output can't confuse
another). Matched spans become bracketed placeholders (`[NAME]`, `[EMAIL]`,
`[PHONE]`) rather than being deleted, so sentence structure survives for
the tutor LLM to still parse the question.

Originally a Stage-2-only gate (`stage2_bridge/intake.py`); generalised to
`redaction.py` and applied to all student-authored text, typed chat
included — a student can type a name into a chat box exactly as easily as
write one on paper. The register-based approach is a legitimate
closed-cohort assumption for a specific school's specific SEN deployment,
not a general-purpose hack — stated explicitly because it wouldn't hold
for a public-facing tool.

## 5. Student knowledge state and mastery

No helpdesk equivalent existed — its only "state" was Rasa session slots
that evaporated when a session ended. Stage 3 needed knowledge state that
persists across sessions.

**Storage**: plain SQLite, not a vector store — knowledge state never
needs semantic search, so a vector store would be the wrong tool. Students
identified only by the pseudonymous StudentID from the LAET extract, no
names or UPNs.

**Update rule (confirmed with the user, 2026-08-13)**: EWMA —
`new = ALPHA*outcome + (1-ALPHA)*old`, `ALPHA=0.35`, or `new = outcome`
with no prior row (true cold start). Chosen over a rolling-window
proportion (would need to query/cap the observations table on every read)
or Bayesian Knowledge Tracing (genuinely over-scope — needs a
guess/slip/transition parameter fit this project has no data to
calibrate). Outcome scale is graded (0.0/0.5/1.0), not binary, matching
what an LLM grading a short free-text answer can actually distinguish.

**Mastery is diagnostic-seeded, not continuously re-graded** (confirmed
with the user): a short LLM-graded Q&A opens each topic thread and updates
mastery; ordinary tutoring turns never silently update it. The student can
explicitly trigger a fresh round ("Re-check my understanding") later.

**Why LLM-graded, not real question content**: checked directly against
Isaac Science's actual question pages before building the diagnostic —
real questions use bespoke interactive widgets (equation builder,
drag-to-reorder, cloze fill-in) graded server-side, with no answer key in
the public API response. Building matching UI widgets was out of scope, so
diagnostic questions are LLM-generated and LLM-graded through the same
chat interface as normal tutoring instead.

**Stage 1 wiring — a real design correction found before building**: the
originally-planned approach (gate a Stage-1-derived note inside
`build_context` on "does this topic have zero mastery rows yet") would
have been dead code. Checked directly: `build_context` is only ever
called from the *normal-turn* branch of a chat turn, which is only
reachable once a topic's diagnostic has already completed and already
written a real mastery row — by definition never cold start at that call
site. The actual cold-start moment is diagnostic *start*
(`chat_session.py::start_diagnostic`), which is where the Stage 1 signal
actually got wired instead. Surfaced to the user as a genuine architecture
fork (note injected only at diagnostic-opening vs. also re-injected into
early normal turns) rather than silently picked — every LLM call here is
built fresh per turn with no running memory between calls, so a note
injected once has no automatic effect later regardless.

The user's own proposal improved on the original design: rather than only
a one-time prompt note, also pre-seed a numeric mastery *estimate* from
`attainment_band` before the first diagnostic answer (`seed_mastery_
prior`, `n_obs=0`, never overwrites a real row). This gives the Stage 1
signal a lasting-but-fading effect through the existing EWMA rule instead
of needing new prompt-injection machinery — the first real observation
blends into the seed rather than starting fresh. Real schema landed as a
synthetic fixture from the user's own Stage 1 pipeline: `flag_status`
(`none`/`provisional`/`confirmed`) drives the one-time note,
`attainment_band` (`well_below`/`below`/`in_line`/`above`) drives the
prior — genuinely separate purposes from one CSV export, not redundant
fields.

Real, non-synthetic Stage 1 data was considered and explicitly declined
(user decision): this project's evaluation is a qualitative expert review
of transcripts, not a comparative outcomes study, so there's no pre/post
or control-group design for real numbers to be weighed against. The
synthetic fixture already proves the mechanism end-to-end with real LLM
generation, at no ethics-approval cost, for the same evaluative power.

## 6. Explanation-method selection

Supersedes what a Stage-1-driven scaffolding lookup was originally going
to be (a fixed disability-category -> teaching-method table). Real
research changed the design: the SEND Code of Practice and EEF's SEND
guidance both push against diagnosis-keyed strategy rules in favour of
universal adaptive teaching, evaluated per student. So instead of a static
table, the tutor tracks per (student, method) whether that method has
actually worked for *that* student, and picks a method each turn
accordingly.

**Mechanism**: Thompson sampling, Beta-Bernoulli posterior per (student,
method). Selection draws once per method from its current posterior and
picks the argmax — not the highest mean — so a method with a high mean but
few observations still gets picked sometimes (exploration), and a
mediocre early result isn't permanently discarded.

**Cold-start prior**: uniform `Beta(1,1)`, confirmed with the user rather
than inventing numeric priors attributed to EEF's guidance — EEF does not
publish per-method numeric success rates for this taxonomy, so a neutral
default is the honest choice; differentiation only emerges from real
data.

**One LLM call, not two**: the correctness signal for the *previous*
turn's method is folded into the current turn's ordinary tutoring call as
a trailing `[[UNDERSTANDING: yes|no]]` marker, mirroring the diagnostic's
`[[MASTERY_SCORE: x]]` pattern — avoids doubling latency/cost on every
turn with a dedicated grading call.

## 7. LLM provider and prompt construction

**Provider**: Google AI Studio / Gemini, via the current `google-genai`
SDK (not the deprecated `google.generativeai` the helpdesk had a dead
duplicate of). `NullLLM` exists so the whole pipeline can be exercised
offline — wiring tests, prompt inspection, expert-review dry runs —
without an API key or any network call.

**Temperature**: 0.2, lower than the helpdesk's 0.3. The helpdesk's value
was tuned for open-ended IT-support chat, where answer variety across
near-duplicate tickets is harmless. A tutoring turn is grounded in
retrieved curriculum extracts and should stay close to that grounding
rather than drift toward free generation — lower temperature favours the
more literal, reproducible reading a defensible transcript needs, at some
cost to phrasing variety across repeated runs of the same scenario.

**Empty-answer bug, found and fixed (2026-08-14)**: `generate` used to
return `""` on hard failure, with a docstring note that callers must treat
an empty string as a failed turn — but none of the actual call sites
checked for it, so a hard failure silently produced a blank tutor message
that got persisted and shown as if real. Caught directly during live
verification, not hypothetically. Fixed by raising `LLMGenerationError`
instead — callers don't need to change, since an exception naturally skips
whatever persistence code would have run after a (now never-returned)
empty string.

**Prompt construction as the privacy boundary**: the helpdesk orchestrator
f-stringed its entire raw context dict into the prompt. For Stage 3 that
dict would carry the student identifier and Stage 1 data straight to a
cloud LLM. `prompt_template.py::build_prompt` instead names every field in
its signature; `_guard` rejects any value containing a forbidden key
substring (`student_id`, `name`, `dob`, `residual`, `sen`, `ehcp`,
`diagnosis`, ...), so a future refactor can't quietly reintroduce the
f-string pattern. `ALLOWED_PROFILE_FIELDS = ("scaffolding_note",)` is the
only Stage-1-derived content ever allowed through, enforced at runtime on
every call, not just by convention.

**Pedagogy grounding**: the system prompt's guide-before-tell default and
step-based-for-multi-part-questions instruction are grounded in VanLehn
(2011) — step-based tutoring outperforms answer-only tutoring, and
hint-before-answer outperforms stating the answer outright. Made explicit
rather than incidental LLM style specifically so the expert-review rubric
has a stated expectation to score `clarity`/`curriculum_fit` against. The
default explicitly defers to a per-turn `explanation_method` instruction
when one is Thompson-sampled (e.g. `worked_example` deliberately does the
opposite — answer shown first — and should win when selected). The
"never signal a level drop when foundation content is blended" rule is
baked in even before the foundation-tier auto-trigger exists, because live
evaluation showed foundation chunks can already surface via ordinary
retrieval with no explicit filter.

**Chunk character budget**: `MAX_CHUNK_CHARS = 2000`, calibrated against
real ingested chunk lengths rather than guessed — observed range
222-6413 characters, median ~1163. 2000 keeps the large majority of real
sections intact while reining in the small number of outliers that would
otherwise let one chunk crowd out the rest of the `top_k` results.

**CC attribution bug, found and fixed (2026-08-16)**: before this, the
only "provenance" exposed anywhere was raw internal `chunk_doc_ids`
(e.g. `isaac_science:cb_carbohydrates__0#0`), rendered unhelpfully by the
frontend. Real human-readable citations required first re-checking the
licence values (see §2's licence-correction finding). Attribution is
deliberately derived from the chunk's `source` field via a hardcoded
lookup, not the chunk's own stored `licence` metadata — chunks ingested
before the licence fix still carry the old value in Chroma metadata until
a re-ingest happens, so keying off `source` is robust regardless of
ingest timing.

## 8. Evaluation instrument

No helpdesk equivalent — it was never formally evaluated. Stage 3's
evaluation is structured expert review (a SENCO reviewer, remote), so the
instrument had to exist in code.

**Reviewer interface is CSV export/import**, confirmed with the user
rather than assumed — the reviewer works in a spreadsheet, not a custom
tool. `export_review_csv` turns a transcript run into one row per
(scenario, criterion) with rating/comment left blank; `import_review_csv`
reads it back, validating through the same `record_rating` path either
way.

**Report is descriptive-only, deliberately**: counts, mean, and range per
criterion, plus every non-empty comment quoted verbatim. No inferential
statistics, no significance claims, no cross-criterion comparison — a
single reviewer's ratings don't support that, and the report says so
plainly rather than overclaiming.

**Transcript generation deliberately doesn't go through the live chat
pipeline** (`chat_session.py::run_chat_turn`): that function is wired to a
real `student_id` (mastery writes, Thompson-sampling draws, interaction
logging). Scenarios are fixed and synthetic on purpose — routing them
through the stateful chat machinery would pollute real per-student tables
with fake data and consume real sampling draws for nothing. Building the
prompt directly from the same lower-level functions (`search_kb`,
`summarise_state`, `build_prompt`) keeps the transcript real evidence of
what the deployed system produces without that side effect.

**Quota-aware pacing**: transcripts are written incrementally (flushed
after each scenario), and the runner paces itself with a delay between
calls — Gemini's free tier caps at 5 requests/minute as well as 20/day,
confirmed live when an unpaced run tripped the per-minute cap immediately.
That pacing is deliberately *not* applied to `LLMClient.generate`'s own
retry backoff — a single real tutoring turn should still fail fast, not
wait out a whole minute; only this batch script's rapid-fire pattern
needed it.

## 9. Housekeeping findings (2026-08-17 cleanup pass)

- **`tutor/chat_session.py::run_chat_turn` was broken — the live chat
  path.** The previous session's Stage 1 refactor removed `ContextBundle`'s
  `profile_note` field, but `run_chat_turn`'s normal-tutoring branch (the
  code path every ordinary chat message goes through, once a topic's
  diagnostic has completed) still read `bundle.profile_note` when building
  the prompt. This would raise `AttributeError` on every normal tutoring
  turn — found only by reading the module directly against
  `context_builder.py`'s current `ContextBundle` definition, not by any
  test: `run_chat_turn`'s normal-turn branch has no test coverage
  (`tests/` has no `test_chat_session.py`). The prior session's live
  verification exercised diagnostic-opening turns only, which never reach
  this code path, so the break went unnoticed. Fixed by dropping the
  `profile_note=` argument from that `build_prompt` call, consistent with
  `build_context` no longer producing one. This is the most consequential
  finding of this pass — flagged prominently rather than folded in as a
  minor fix.
- **`tutor/session.py` was also broken**, the same way: it called
  `build_context(..., profiles=profiles)` (parameter removed) and read
  `bundle.profile_note` (field removed). Dormant path, no test coverage,
  not wired to any live endpoint, so nothing broke visibly. Fixed the same
  way — dropped the now-nonexistent `profiles` plumbing. This dormant path
  has no Stage 1 cold-start parity of its own yet; tracked in
  `docs/TODO.md`.
- Git/data hygiene checked directly (tracked-file list, `.gitignore`
  coverage, a grep for name-leak patterns across every tracked file type)
  — clean; no secrets, no stray real names, no accidentally-tracked
  databases or `node_modules`.

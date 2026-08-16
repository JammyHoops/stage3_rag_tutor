# Stage 3 — remaining work, plan for 2026-08-15

**Bottom line: yes, everything actionable fits comfortably in one
focused day.** Two real pieces of work (`profile_to_note`, the
foundation-tier trigger) are deliberately NOT in that day — they're
blocked on decisions/approvals that aren't yours to rush, not on
implementation time. Flagged separately below so they don't read as
"forgotten."

## Do this first: finish the evaluation instrument

Fully built and unit-tested (153/153) as of tonight, just not run for
real — today's Gemini quota was already gone before it was even built.

1. Confirm `evaluation/scenarios.json` as drafted, or edit it (6
   scenarios: 2 each for biology/chemistry/computer_science, varying
   cold-start-vs-established mastery and no-note-vs-scaffolding-note).
2. `python -m evaluation.run_scenarios` — real transcripts, ~6 Gemini
   calls (well inside the 20/day cap, but see the quota tip below).
3. `export_review_csv()` from `evaluation/expert_review.py` — open the
   resulting CSV and sanity-check it reads sensibly as a spreadsheet.
4. Hand-fill a couple of rows, `import_review_csv()`, `generate_report()`
   — confirm the descriptive summary reads honestly (no significance
   claims — single reviewer).
5. Update README's evaluation-related TODO items + the
   `project-stage3-evaluation-instrument` memory file once this is
   actually verified, not before.

Est. 30–60 min including reading the output properly.

## Then: pedagogy prompt instructions

`tutor/prompt_template.py`'s `SYSTEM_PROMPT` is still one placeholder
line. This is genuine writing/prompt-engineering work, not
mechanical — the docstring already points at VanLehn (2011) as the
effectiveness benchmark from Chapter 2, so ground it there rather than
inventing pedagogy from scratch.

- Scaffolding style, questioning-over-answer-giving, reading-age
  considerations.
- Decide response format constraints (e.g. worked-step structure) —
  this affects expert-review scoring, so it's worth deciding alongside
  (or right after) thinking about the rubric, not independently.
- Live-verify against a few real turns across the 3 subjects.

Est. 1–2 hrs, a handful of Gemini calls.

## Then: CC attribution format

Isaac Science (CC BY-NC-SA 4.0) and Ada Computer Science (CC BY-SA) both
require real attribution + link-back wherever their content surfaces in
tutor output. `chunk_doc_ids` today are internal store IDs, not
something a student or reviewer could actually click through to a
source. Needs an actual human-readable citation format.

Est. 30–60 min, mostly formatting — low LLM cost.

## Quick decisions worth just making (cheap, low-risk)

- **Tutoring temperature** — currently `0.3`, carried over from the
  helpdesk unjustified. Decide and write down the reasoning (or
  deliberately keep it and say why).
- **Token budget / truncation rule** for retrieved chunk text in
  prompts — currently uncapped.
- **Retrieval time-decay** (`retriever/search.py`) — decide whether it's
  meaningful for curriculum content at all (a spec doesn't go stale the
  way a ticket fix does) — probably: no, set to a no-op and document why
  rather than leave it silently active.

Est. ~30 min total — these are decisions more than code.

## Stretch, only if energy remains

- `retriever/search.py` blend-weight tuning against real pilot queries.
- `api/main.py`'s `/tutor` endpoint — arguably moot now that the chat
  path (`api/chat.py`) is the actually-live one; consider explicitly
  marking it "not needed" rather than leaving it as an open TODO.
- `stage2_bridge/intake.py`'s low-OCR-confidence threshold — only
  matters if the Stage 2 MATLAB path is ever actually exercised;
  currently dormant.
- **Doc cleanup, trivial**: `stage2_bridge/intake.py`'s TODO list still
  says "Implement `redact`" — stale, `redact()` has been real since
  2026-08-12 (the file already imports the real one). One-line delete.

## Explicitly NOT part of tomorrow — blocked, not undone

- **`tutor.context_builder.profile_to_note`** — the one remaining
  fail-closed stub. Blocked on the real Stage 1 export schema, which is
  blocked on ethics approval. Nothing to build until that lands.
- **Foundation-tier auto-trigger** — blocked on a cross-concept
  `prerequisites` graph (no ingested source provides one) and a real
  Stage 1 attainment-magnitude field (current schema is just a binary
  flag). The design doc itself calls this "a deliberate design decision
  for the user to make, not to invent unilaterally" — a methodology
  question, not a coding task.
- **Rubric finalisation with your supervisor** — a conversation, not
  code. The tooling is ready whenever that happens: revising `CRITERIA`
  in `expert_review.py` is a small edit, not a rebuild.
- **Mastery decay with inactivity**, **explanation-method retention
  signal** — deliberately deferred open items in their own design docs.
  Not scoped yet; don't need deciding tomorrow.

## One quota-management tip

Do the evaluation live-run **first** tomorrow, before any other live
testing — it's the most "shippable" remaining piece and only needs ~6
calls. Save prompt-instruction verification for after it, so a slow
start doesn't eat into the 20/day cap before the highest-value thing is
done.

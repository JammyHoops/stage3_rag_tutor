# Stage 3 — What's needed from the Stage 1 export, and why

Status: **blocking** — this is the one remaining piece of work that only
you can unblock (ethics approval + the real Colab pipeline output), not
something further coding on my side can substitute for.

Scope: the CSV handoff from Stage 1 (learner-profile / attainment-gap
analysis over the LAET extract) to Stage 3 (this tutor). Does not cover
Stage 2 (handwriting recognition) — that handoff is separate and already
implemented (`stage3/stage2_bridge/intake.py`).

## Why Stage 3 needs anything from Stage 1 at all

Quick recap of the point of this, since it's easy to lose sight of: Stage
3's own mastery tracking (the EWMA diagnostic-derived estimate) is
**session-derived** — it starts from nothing and only reflects what a
student has actually done inside the tutor. Stage 1's signal is the only
thing that could inform a student's *very first* turn on a topic they've
never touched, using real institutional evidence (teacher assessment,
exam results) instead of a blank slate. It has exactly two consumers in
the code, both currently blocked:

1. **`tutor/context_builder.py::profile_to_note`** — maps a Stage 1
   profile row to a single coarse scaffolding note injected into the
   prompt's very first turn on a topic. Currently raises
   `NotImplementedError` (deliberately, fail-closed) because there's
   nothing real to map yet.
2. **The foundation-tier retrieval trigger** (design already finalised in
   [`stage3-curriculum-retrieval-design.md`](stage3-curriculum-retrieval-design.md#activation-trigger))
   — fires lower-tier (GCSE) content alongside normal content, but only
   when a Stage 1 flag **and** a live in-session prerequisite-failure
   signal both hold. Not built at all yet; there's no real flag to read.

Neither of these is guessing at what to build — both designs are already
written and decided. What's missing is the actual data.

## What form it needs to take

- **One CSV file**, dropped at `data/stage1/stage1_profiles.csv` (already
  gitignored — never committed, see `.gitignore`'s "ETHICS-CRITICAL"
  block).
- **Keyed by `student_id`** — the same pseudonymous StudentID issued in
  the LAET extract that Stage 2 and Stage 3 already use everywhere else
  (`student_state/store.py`'s module docstring: "No names, no UPNs").
  This has to be the *same* id space Stage 3's conversations/mastery
  tables already use, or nothing will join.
- Loaded once at startup (`stage3/profiles/stage1_loader.py::
  load_profiles`), not re-read per request.
- Unknown student_id → `None`, never a fabricated default profile
  (already implemented this way).

## Fields — what's settled vs. what still needs a decision

The placeholder schema in `stage1_loader.py` right now is
`student_id, flagged, flag_subjects` — literally a guess, not derived
from a real Stage 1 output. Based on what the two consumers above
actually need:

| Field | Status | Why |
|---|---|---|
| `student_id` | **Settled** | Join key, see above. |
| `flagged` (per subject, provisional/confirmed) | **Settled in design, not in data** | The curriculum-retrieval design doc requires this to be **per-subject**, not one blanket flag — "a student can be strong in GCSE Maths and weak in GCSE Biology; use the subject-specific signal, not the aggregate score." Needs one flag per in-scope subject (biology / chemistry / computer_science), each `none` \| `provisional` \| `confirmed`. |
| Subject-specific attainment level | **Not settled — needs your input** | The foundation trigger fires when "the concept... sits below the student's demonstrated GCSE attainment *for that subject domain*." That requires *some* attainment representation per subject (a grade? an APS-style score?), not just a binary flag. What does Stage 1's gap-analysis actually output here? This is the one genuine open design question, not just missing data. |
| Raw residual / gap magnitude | **Deliberately NOT wanted in the prompt, still an open question for the export itself** | `stage1_loader.py`'s docstring already flags this: only a *coarse category* is defensible to inject into an LLM prompt; the raw residual value is not to be transmitted. Two ways to satisfy that — (a) Stage 1 exports the raw value and Stage 3 buckets it before it ever reaches `profile_to_note`'s output, or (b) Stage 1 pre-buckets before export and Stage 3 never receives the raw number at all. (b) is better data-minimisation (Stage 3's process never touches the sensitive number, full stop) and is probably the easier thing to defend in the ethics application — but it's your call, and worth deciding once rather than reworking later. |
| Anything about *why* a student is flagged (disability category, SEND status, EAL, etc.) | **Explicitly do not include** | Not used anywhere in the design, and actively contradicts the reasoning already written up in [`stage3-explanation-method-design.md`](stage3-explanation-method-design.md#rationale) (SEND Code of Practice: category labels are for planning provision, not for slotting a pupil into a fixed-response bucket; a category-keyed system would misrepresent the evidence base). Stage 3 only ever wants "there's a demonstrated gap here," never the underlying reason. |

## The safety net that already exists, regardless of what you send

Worth knowing before this feels like a bigger risk than it is: no matter
what raw fields land in the CSV, only ONE derived field is structurally
allowed to reach the LLM prompt at all —
`stage3/tutor/prompt_template.py`'s `ALLOWED_PROFILE_FIELDS =
("scaffolding_note",)`. The prompt guard (`build_prompt`) raises an
exception if anything else appears in the profile-derived content, not
just at code-review time — at runtime, every single turn. So even a
richer-than-expected Stage 1 export can't leak extra fields into a
prompt by accident; the guard would break loudly, not silently. This is
also why the raw-residual decision above matters less than it might feel
like — worst case, an unbucketed field just sits unused in `stage1_loader.py`'s
`FIELDS` list until `profile_to_note` is written to reduce it down.

## What's genuinely outside my lane here

Ethics approval for exporting real LAET-derived attainment data is an
institutional process, not something I can help move forward directly —
flagging that plainly rather than implying otherwise. What I *can* do
now, in parallel with that process rather than waiting on it: help you
draft the exact field list/data-minimisation reasoning above into
whatever the ethics application actually needs, since that's largely the
same document. Say the word if that's useful.

## What happens once this lands

Once you can tell me the real field names/shapes (or the CSV itself, even
with synthetic rows matching the real shape, is enough to build against):

1. Update `FIELDS` in `stage1_loader.py` to match.
2. Implement `profile_to_note` — the bucketing/wording logic, output
   strictly `{"scaffolding_note": <text>}` or `{}`.
3. Wire the foundation-tier trigger in `context_builder.py::build_context`
   (design already finalised, just needs the real signal to read).
4. Tests + live verification, same as every other feature in this project.

None of that needs anything further from you beyond the schema itself —
this document is the complete ask.

# Stage 3 — Curriculum Retrieval Design: Core / Foundation Tiers

Status: decided, ready to implement.
Scope: the curriculum-retrieval source only (one of the three RAG context
sources — curriculum retrieval, per-student knowledge state, Stage 1 learner
profile). Does not change the other two sources.

## Decision

Curriculum content is split into two tiers at ingestion time. Retrieval
defaults to `core`. `foundation` activates automatically per-query when a
specific, evidenced trigger fires (below) — never manually, never as a blanket
setting per student. When `foundation` content is used, it is blended into
the explanation. The tutor never announces a level drop (e.g. never says
"let's go back to GCSE basics") — this was an open question, now resolved:
always blend, no explicit signalling.

## Chunk schema

Extends the existing chunk schema with one field:

```
id                  stable identifier (existing convention — do not change)
subject             Biology / Chemistry / Computer Science
tier                "core" | "foundation"
level               AS / A2 (bold vs non-bold per DfE convention) — core only
                     GCSE — foundation only
topic / subtopic    e.g. "Equilibria" / "Kc and reacting quantities"
spec_code           board + code where relevant, e.g. OCR H432
content             the actual explanatory text — this is what gets embedded
misconceptions      common errors at this concept, if the source states them
prerequisites       list of concept IDs this concept depends on
                     (this is the field the trigger logic reads — see below)
source              "Isaac Science" | "Ada Computer Science" | "DfE Appendix 6"
source_url          exact page, for attribution
licence             CC-BY-4.0 | CC-BY-NC-SA-4.0 | OGL-v2.0 (see the
                     correction note under Sourcing below — the specific
                     licence-per-source pairing here was wrong originally)
retrieved_date
```

`tier` is set at ingestion from the source platform's own level tagging
(Ada and Isaac Science both tag GCSE vs A-level natively — do not infer this
from prose, read it off the source).

## Sourcing

| Subject | Source | Licence (assumed here — see correction below) | Tiers present |
|---|---|---|---|
| Biology | Isaac Science (isaacscience.org) | CC BY-NC-SA 4.0 | core + foundation |
| Chemistry | Isaac Science (isaacscience.org) | CC BY-NC-SA 4.0 | core + foundation |
| Computer Science | Ada Computer Science (adacomputerscience.org) | CC BY-SA | core + foundation |

**Correction (2026-08-16): both licences above were wrong, confirmed
directly.** A plain fetch of either site only ever returns the JS SPA
shell (no licence text), which is why this went unverified for so long
— a headless-browser render of multiple real concept pages and each
homepage settled it: **Isaac Science is CC BY 4.0** (no NonCommercial or
ShareAlike clause — more permissive than assumed), **Ada Computer
Science is CC BY-NC-SA 4.0** (does carry a NonCommercial clause — the
two sites' actual licences are effectively swapped relative to this
table's original guess). Both connectors and their tests are updated to
the confirmed values; chunks ingested before the fix still carry the old
value in stored metadata until re-ingested — see `isaac_science.py`'s
and `ada_computer_science.py`'s "CORRECTED" docstring notes.

Ingest both tiers for all three subjects. Do not filter GCSE-tagged content
out at ingestion — filtering happens at retrieval time via the trigger logic,
not at corpus-build time. Every chunk (both tiers) carries `source_url` and
`licence` — both platforms' licences require attribution with a link back to
the original wherever content surfaces in output, so the tutor must be able
to construct that citation at generation time.

## Activation trigger

`foundation` retrieval for a given query fires only when **both**:

1. **Stage 1 signal**: the student is flagged (provisional or confirmed,
   per the Stage 1 output), AND the concept currently being asked about has
   a `prerequisites` entry that sits below the student's demonstrated GCSE
   attainment *for that subject domain specifically* — not overall GCSE APS.
   A student can be strong in GCSE Maths and weak in GCSE Biology; use the
   subject-specific signal, not the aggregate score.

2. **In-session signal**: the per-student knowledge state shows repeated
   failure on the *prerequisite* concept (via the `prerequisites` link), not
   on the current concept itself.

Do **not** fire foundation tier on:
- A single wrong answer on the current concept (this is a slip, not a gap —
  correct it directly at `core` tier)
- Stage 1 flag alone, without an in-session prerequisite-failure signal
  (a flagged student asking a question they're getting right doesn't need
  foundation content)
- In-session signal alone, without Stage 1 flag (protects against firing
  for students who are simply encountering a topic for the first time —
  that's normal learning, not a gap)

Both conditions must hold. This is deliberate: it's the difference between
"this student made a mistake" and "this student has an actual unaddressed
prerequisite gap," and conflating the two produces a tutor that condescends
on every wrong answer — a real risk for a SEN-focused tool.

## Retrieval behaviour when foundation fires

- Foundation-tier chunks are retrieved *in addition to* core-tier chunks for
  that query, not instead of them.
- The LLM blends foundation content into the explanation inline. No
  meta-commentary about level, no "stepping back to GCSE," no visible tier
  switch of any kind in the output shown to the student.
- Log which tier(s) contributed to each response (for evaluation / SENCO
  review purposes — the SENCO reviewer needs to be able to see when
  foundation content was used and assess whether the blend read naturally, even though the
  student never sees the tier label).

## Open item

None — this design is finalised pending implementation. If SENCO review
surfaces cases where invisible blending reads badly for
specific students, revisit; do not pre-empt that with a visible-toggle
option before evaluation data exists.

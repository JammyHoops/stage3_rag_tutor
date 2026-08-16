# Stage 3 — Explanation Method Selection Design

Status: decided, ready to implement.
Scope: how the tutor chooses *how* to explain a concept (not *what* content
to retrieve — see stage3-curriculum-retrieval-design.md for that). This is
an extension of the per-student knowledge-state source, not a new context
source.

## Decision

The tutor tracks, per student, which explanation method has worked for
them, and uses that to guide future method selection for that student. It
does not use a fixed disability-category-to-method lookup table.

## Rationale

The SEND Code of Practice is explicit that the four broad areas of need
"give an overview of the range of needs that should be planned for, not to
fit a pupil into a category," and EEF's evidence-based SEND guidance
recommends universal high-quality adaptive teaching as the primary lever,
not diagnosis-keyed strategy rules. A fixed method-per-category table would
misrepresent the evidence base it claims to be grounded in. Per-student
tracked efficacy makes a much narrower, defensible claim: this worked for
this student, last time — not a population-level claim about a diagnostic
group.

## Method taxonomy

A small, fixed set — deliberately not fine-grained, for the same reason
Stage 1 pooled low-entry subjects rather than modelling each individually:

- Worked example
- Analogy
- Step-by-step scaffold
- Visual / diagrammatic
- Socratic questioning
- Chunking

Do not add methods ad hoc during implementation without updating this list.
More categories means less evidence per category per student.

## Success signal

Behavioural, not self-reported — asking "did that help?" adds interaction
burden and is noisy, particularly for a SEN population.

Two signals, tracked separately, not conflated:

- **Immediate**: correctness on the next question touching the same
  concept, directly after the explanation.
- **Retention**: correctness on that concept after a gap (next session, or
  next time the concept recurs). An explanation that produces a correct
  immediate answer but doesn't hold up on retest is a different outcome
  from one that does, and the two should not be averaged into one number.

## Selection policy: Thompson sampling, not deterministic best-known-method

Three requirements have to be satisfied by one mechanism, not three bolted
together:

1. Cold start — a student's first encounter with a method has zero history.
2. Shrinkage — a student's own history is small-n; early estimates need to
   borrow strength from cohort-wide evidence, the same problem Stage 1
   solved for low-entry subjects via partial pooling (crossed random
   effects, stage1_pipeline.ipynb §8).
3. Avoiding a pedagogical filter bubble — always selecting the
   currently-best-known method for a student means the system never tests
   whether another method might work better, and any early noisy success
   gets locked in.

**Thompson sampling with a Beta-Bernoulli model per (student, method) pair
satisfies all three at once:**

- Each (student, method) pair has a Beta(α, β) distribution over its
  success probability. α/β update with each observed success/failure
  (tracked separately for immediate and retention signal — two models per
  pair, not one).
- The prior (before any student-specific data exists) is **not**
  uninformative — it's set from the cohort-wide success rate for that
  method, with EEF's five-a-day recommendations as the default weighting
  where no cohort data yet exists at all. This is the cold-start answer and
  the pooling answer in one step: a student with no history is governed by
  the cohort prior; as their own data accumulates, their posterior moves
  away from the cohort estimate at a rate proportional to how much evidence
  they've generated — exactly the shrinkage behaviour from Stage 1's
  partial pooling, arrived at through the prior/posterior mechanism instead
  of a separate BLUP calculation.
- At selection time, sample a success probability from each method's
  current posterior for that student and pick the method with the highest
  sample — not the highest posterior mean. This is what prevents the filter
  bubble: a method with a high mean but few observations has a wide
  posterior, so it still gets sampled and selected some of the time. A
  method with a mediocre early result isn't permanently discarded; its
  posterior narrows and updates as more evidence comes in, same as every
  other method. No separate epsilon-random exploration step is needed —
  exploration is built into the sampling, not bolted on.

## Data schema

Interaction log (append-only, one row per explanation given):

```
id                  stable identifier
student_id
concept_id           links to the curriculum chunk schema's concept space
subject
method               one of the six taxonomy values above
timestamp
correct_immediate    bool, set after the next question on this concept
correct_retention    bool, nullable until a retest occurs; null = not yet observed
retention_gap_days   set when correct_retention is set
```

Aggregated posterior state (updated incrementally, not recomputed from
scratch per query):

```
student_id
method
signal_type          "immediate" | "retention"
alpha
beta
n_observations
```

Cohort-level prior (recomputed periodically, e.g. weekly batch, not live):

```
method
signal_type
cohort_alpha
cohort_beta
n_students_contributing
```

## What this is not

This does not replace the two-tier core/foundation retrieval design — method
selection determines *how* a concept is explained; tier determines *what
level* of content it draws from. Both can vary independently for the same
interaction.

## Open items / future work

- **Granularity**: this spec tracks (student, method) at the level of "the
  student" — not (student, method, subject) or (student, method, concept).
  A method that works for a student in Biology might not transfer to
  Computer Science. Log at the finer grain (schema above already supports
  it via `concept_id` and `subject`) but start the selection policy at the
  coarser (student, method) level, and only split further if evaluation
  data shows subject-specific effects are large enough to matter. Don't
  pre-split without evidence — same discipline as the flag-magnitude item
  in the retrieval design doc.
- **Retention window**: how long a gap counts as "retention" versus just
  "the next question" is not yet defined. Needs a concrete threshold before
  `correct_retention` can be populated consistently.
- **SENCO review**: the SENCO reviewer is well suited to auditing a
  bounded sample of tracked (student, method) histories for pedagogical
  plausibility — a concrete, scoped artefact rather than judging the tutor
  holistically.

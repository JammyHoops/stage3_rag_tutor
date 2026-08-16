# Stage 3 — Finding a real GCSE foundation-tier source for Biology/Chemistry

Status: **investigation guide, not a decision** — this is a checklist to
work through, not a recommendation of any one source. None of the
candidates below have been verified directly; treat every licence claim
in this document as "reported, unverified" until checked the way Isaac
Science and Ada Computer Science's licences were (see "How to verify a
candidate", below) — that check found BOTH of those originally-assumed
licences wrong, so there's real precedent for not trusting the obvious
answer here.

Scope: Biology and Chemistry only. Computer Science already has genuine
GCSE-level (`foundation`-tier) content from Ada Computer Science (159
chunks, live in the corpus). This is purely about closing the same gap
for the other two subjects.

## Recap: why this is needed, and why Isaac Science doesn't cover it

The core/foundation tiering design
([`stage3-curriculum-retrieval-design.md`](stage3-curriculum-retrieval-design.md#activation-trigger))
blends GCSE-level content into an A-level answer when a student has a
demonstrated prerequisite gap — never signalled to the student, just
quietly present. Checked directly against the live Isaac Science API
(see `connectors/isaac_science.py`'s TODO): **Biology has zero
GCSE-stage concepts on that platform**, and **Chemistry's 8 GCSE-tagged
concepts are textually identical to their A-level version** — so even if
ingested, there'd be no simpler explanation actually present to blend in.
This isn't a scraping-effort problem, it's a content-availability
problem, specific to that one source.

## What a candidate actually needs to satisfy

Be strict about all four — a source that's strong on three but fails the
fourth isn't worth building a connector for:

1. **Real GCSE-level UK content, Biology or Chemistry specifically** —
   not KS3, not a US curriculum (AP Biology / Chemistry ≠ GCSE), and
   genuinely *explanatory* prose a tutor can draw from — not just a
   specification/topic list (a list of "what must be taught" has no
   content to retrieve; see the DfE Appendix 6 note below).
2. **A licence that actually permits this use, confirmed directly, not
   assumed.** CC BY / CC BY-SA / CC BY-NC-SA / OGL v3.0 are all workable
   (Ada Computer Science's NC clause hasn't blocked anything so far) —
   what isn't workable is standard all-rights-reserved copyright (most
   broadcaster and commercial revision-site content) or a licence that
   explicitly excludes redistribution/reuse, even for research.
3. **A real way to get the content out** — either a documented,
   unauthenticated API (like Isaac Science's), or plain
   downloadable/scrapable text under a licence that permits scraping.
   A JS-rendered SPA with no API is a dead end unless there's a bulk
   export option — don't commit to building scraping infrastructure for
   one source without checking that first.
4. **Enough real coverage to matter** — a handful of topics isn't worth a
   whole new connector; roughly GCSE-specification-breadth for the
   subject is the bar (compare: Isaac Science gave 42 Biology / 135
   Chemistry core-tier chunks from full A-level coverage).

## Candidates worth checking (unverified — see caveat above)

Roughly ordered by how promising they seem on paper, most promising
first. "Needs verification" is doing real work in every row — don't
build against any of these from memory/reputation alone.

| Candidate | Why it might work | What to actually check |
|---|---|---|
| **Oak National Academy** (oaknational.org) | UK government-backed, GCSE Biology/Chemistry lessons exist, aimed at teaching (not just revision) | Exact licence terms per resource type — Oak's licensing has reportedly varied by content type and over time; confirm current terms directly on the site's own licence/terms page, not from general knowledge. Check for an API vs. needing to scrape a rendered site. |
| **Wikibooks / Wikiversity** (GCSE Science shelves) | Wikimedia projects are CC BY-SA by platform-wide policy — this is the one candidate where the licence is close to certain without checking a specific page | Coverage/completeness and quality are the real risk here, not licensing — GCSE content on Wikibooks may be partial or inconsistent across topics. Wikimedia has a real, well-documented API (same family as MediaWiki's API used across all WMF projects). |
| **Khan Academy** | Structured content, some UK-curriculum-aligned material exists, has a real API surface | Licence is reportedly CC BY-NC-SA but confirm directly — and confirm GCSE (not just US-curriculum) alignment for the specific Biology/Chemistry content before investing further. |
| **DfE GCSE subject content documents** ("Appendix 6" in the original design doc's source enum — never actually pursued) | Official, likely OGL v3.0 (UK government default), unambiguous authority | Almost certainly a *specification* (required topic list), not explanatory teaching prose — probably NOT directly usable as retrieval content on its own. Worth checking anyway, since it could still be useful as a `prerequisites`/topic-coverage source even if not as chunk content — that's a second, smaller use case, not this one. |
| **CK-12** | Established OER platform, real API/structured content, CC-licensed | US-curriculum-shaped — GCSE alignment is the real question, likely poor. Lower priority than the above. |
| BBC Bitesize | The obvious first thought — extensive, genuinely GCSE-aligned, well-written | Standard BBC copyright almost certainly applies (no evidence of an open licence) — worth a direct check of the footer/terms page before ruling out, but don't expect this one to clear the licence bar. |
| Exam board specimen materials (AQA/OCR/Edexcel GCSE Combined/Separate Science) | Directly spec-aligned by definition | Copyrighted by the board, typically restricted to registered centres — likely a dead end for a redistributable research corpus, but the connectors' own TODOs already flagged "confirm copyright position on ingesting exam-board materials" as unresolved, so worth one direct check rather than assuming. |
| Seneca Learning, Save My Exams, Physics & Maths Tutor, Twinkl | GCSE-aligned, well-produced | Commercial/subscription products — almost certainly not openly licensed. Deprioritise unless the above all fail. |

## How to verify a candidate (don't skip this step)

This project has direct, recent precedent for why "looks openly licensed"
isn't good enough: Isaac Science and Ada Computer Science's licences were
both **wrong** in the original design doc — not just imprecise, effectively
swapped — until checked via a real headless-browser render of the actual
site (plain fetch only ever returned a JS-SPA shell with no licence text
at all, for both). Same discipline applies here:

1. Try a plain fetch/read of the site's licence or terms page first — it
   may just work, unlike the JS-SPA sites already in this project.
2. If it doesn't (empty shell, JS-only rendering), escalate to a real
   headless-browser render of the actual licence/footer text — don't
   infer it from marketing copy, a Wikipedia summary, or general
   knowledge about the platform. Screenshot or quote the exact text
   found.
3. Check licence terms on **more than one page** — a global footer claim
   and a specific resource's own stated terms can differ (this is
   exactly the kind of detail that would matter for a defensibility
   argument in Chapter 3).
4. Note the exact licence string and a link to where it was confirmed —
   this project's convention is to cite that provenance directly in the
   connector's docstring (see `isaac_science.py` / `ada_computer_
   science.py`'s "CORRECTED" notes for the pattern to follow).

## Once a real candidate is confirmed

Bring back: the source name, confirmed licence + where you confirmed it,
whether it has a real API or needs the plain-text-plus-chunking route,
and a rough sense of coverage. Two different build paths from there:

- **Has a real API with natural content structure** (like Isaac Science/
  Ada Computer Science) → same pattern as those two connectors:
  subject-scoped, `difficulty_tier="foundation"`, structure-aware
  splitting at the source so `chunking.py`'s passthrough chunker stays
  adequate.
- **Plain open-licensed text with no native structure** → this is the
  one case that would actually need `chunking.py`'s real chunker, which
  was retired in the 2026-08-16 cleanup pass specifically because
  nothing in scope needed it. A source like this would be the genuine
  driver to un-retire that TODO — worth flagging explicitly when you
  bring a candidate back, since it changes the shape of the work.

Either way, this stays a documented, deferred candidate until the Stage 1
schema lands and the foundation-tier trigger is actually built — no
urgency to rush a connector before then, just to have a real option ready
rather than starting the search from scratch later.

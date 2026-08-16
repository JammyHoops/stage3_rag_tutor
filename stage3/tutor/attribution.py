"""Human-readable Creative Commons attribution for curriculum content.

PROVENANCE — NEW. Closes the "CC attribution" TODO that lived in
``prompt_template.py``: Isaac Science and Ada Computer Science content
both require real attribution + link-back wherever it surfaces in tutor
output — a licensing obligation, not optional polish. Before this, the
only "provenance" exposed anywhere was ``chunk_doc_ids`` (internal IDs
like ``isaac_science:cb_carbohydrates__0#0``), which the frontend was
rendering raw and unhelpfully.

Shared by ``prompt_template.py`` (normal tutoring turns) and
``diagnostic.py`` (diagnostic turns) — kept as its own module rather
than duplicated in both, since they'd otherwise need the identical
title-recovery/dedup logic twice.

LICENCE VALUES — CONFIRMED 2026-08-16, not the original design doc's
assumption. A plain fetch of either site only ever returns the JS SPA
shell (no licence text) — confirmed directly, same failure mode the
connectors already documented for content fetching. Settled via a
headless-browser render of multiple real concept pages and each
homepage: **Isaac Science is CC BY 4.0** (no NonCommercial or ShareAlike
clause), **Ada Computer Science is CC BY-NC-SA 4.0** (does carry a
NonCommercial clause) — the two are effectively swapped relative to the
original design-doc guess (CC BY-NC-SA / CC BY-SA respectively). See
``connectors/isaac_science.py`` and ``connectors/ada_computer_science.py``
"CORRECTED" docstring notes.

DELIBERATELY NOT reading the chunk's own ``licence`` metadata field —
chunks ingested before the 2026-08-16 fix still carry the OLD (wrong)
value in stored Chroma metadata until a re-ingest happens (not done as
part of that fix — see those connectors' docstrings). ``SOURCE_
ATTRIBUTION`` below is hardcoded and keyed by ``source`` instead, which
IS reliable regardless of ingest staleness (set once at ingest, never
touched by the licence bug).

TITLE RECOVERY: chunk metadata has no dedicated "concept title" field,
only ``section_title`` (e.g. "Carbohydrates" for a concept's intro
section, "Carbohydrates — Monosaccharides" for a sub-section — see both
connectors' ``sections.insert(0, {"title": title, ...})``). Splitting on
" — " and taking the first part recovers the plain concept title without
a new metadata field.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

# Keyed by the chunk `source` field. NOT derived from the chunk's own
# `licence` field — see module docstring.
SOURCE_ATTRIBUTION: dict[str, dict[str, str]] = {
    "isaac_science": {
        "source_name": "Isaac Science",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
    },
    "ada_computer_science": {
        "source_name": "Ada Computer Science",
        "licence": "CC BY-NC-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-nc-sa/4.0",
    },
}


def build_attributions(chunks: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """One citation per unique source concept (deduped by ``source_url``),
    sorted by title for deterministic output. Chunks from an unrecognised
    or missing ``source`` are silently skipped — nothing to attribute
    (e.g. a future non-CC source), not an error.
    """
    by_url: dict[str, dict[str, str]] = {}
    for chunk in chunks:
        source = chunk.get("source")
        attribution = SOURCE_ATTRIBUTION.get(source) if source else None
        if attribution is None:
            continue
        source_url = chunk.get("source_url")
        if not source_url or source_url in by_url:
            continue

        section_title = chunk.get("section_title") or ""
        title = section_title.split(" — ", 1)[0].strip() or chunk.get(
            "concept_id", "Untitled"
        )

        by_url[source_url] = {
            "title": title,
            "source_name": attribution["source_name"],
            "source_url": source_url,
            "licence": attribution["licence"],
            "licence_url": attribution["licence_url"],
        }

    return sorted(by_url.values(), key=lambda a: a["title"])

"""Human-readable Creative Commons attribution for curriculum content.

PROVENANCE — NEW. Isaac Science and Ada Computer Science content both
require real attribution and link-back wherever it surfaces in tutor
output — a licensing obligation. Before this, the only "provenance"
exposed anywhere was raw internal ``chunk_doc_ids``.

Shared by ``prompt_template.py`` (normal tutoring turns) and
``diagnostic.py`` (diagnostic turns) so the title-recovery/dedup logic
doesn't have to be duplicated.

Licence values: Isaac Science is CC BY 4.0, Ada Computer Science is
CC BY-NC-SA 4.0, confirmed via headless-browser render; see
docs/design/FINDINGS_AND_DECISIONS.md §2. Attribution is keyed by the
chunk's ``source`` field via a hardcoded lookup, rather than the chunk's
own stored ``licence`` field, so it stays correct regardless of ingest
timing.

TITLE RECOVERY: chunk metadata has no dedicated "concept title" field,
only ``section_title`` (e.g. "Carbohydrates" for a concept's intro
section, "Carbohydrates - Monosaccharides" for a sub-section). Splitting
on the separator and taking the first part recovers the plain concept
title without a new metadata field.
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

"""Connector for Isaac Science (isaacscience.org) — curriculum retrieval source.

PROVENANCE — NEW. First connector for the core/foundation curriculum-tiering
design (docs/design/stage3-curriculum-retrieval-design.md). Covers Biology
and Chemistry, core (A-level) tier — see ``IsaacChemistryConnector`` below
for the Chemistry variant.

WHY AN API CONNECTOR, NOT A SCRAPER: isaacscience.org is a JS-rendered SPA;
a raw HTML fetch returns an empty shell. The site calls a real, public,
unauthenticated JSON API instead:

    GET {BASE}/pages/concepts?subjects=<subject>&limit=N&start_index=N
        -> {"results": [{"id", "title", "tags", ...}, ...]}
    GET {BASE}/pages/concepts/{id}
        -> full concept: title, tags, audience[].stage (gcse/a_level),
          a "children" tree of markdown content blocks, some laid out as
          an accordion of named sub-sections (natural chunk boundaries).

PINNED API VERSION: the API is version-pinned in the URL (``API_VERSION``
below) with no stable alias — an unversioned path or ``/api/latest/...``
returns a 502 or the SPA's HTML shell instead of JSON. If ``fetch()``
starts returning nothing or logging "stale" warnings: load isaacscience.org
in a browser with devtools open, find a request under
``/api/v.../api/...``, and update ``API_VERSION`` to match.

CONTENT SEGMENTATION: each concept is split at its own natural boundaries
(the top-level intro plus each accordion sub-section) into one document
per section — see ``_extract_sections``. This is why ``chunking.py``'s
passthrough chunker is adequate here: the structure-aware splitting
already happened at this layer.

TOPIC MAPPING: Isaac's own ``tags`` are more granular than the fixed
chat-UI topic list needs. ``_TAG_TO_TOPIC_BY_SUBJECT`` is a small,
hand-authored, extensible lookup — an unmapped concept is still ingested
(subject-scoped retrieval still finds it) but logged with a warning.

No real GCSE ("foundation") content exists on this source for Biology or
Chemistry — see docs/design/FINDINGS_AND_DECISIONS.md §2 for what was
checked and why. ``prerequisites`` is stored as ``None`` — no cross-concept
dependency graph is available from this source; see docs/TODO.md.
``spec_code``/``misconceptions`` are likewise not present in this source's
data. The AS/A2 split isn't available at this API's granularity, only
``audience[].stage`` (gcse/a_level); ``level`` stores the raw stage value.
LaTeX/mhchem markup (``$\\ce{C6H12O6}$`` etc.) is left as-is in chunk text.

Licence is CC BY 4.0 (confirmed via headless-browser render — see
FINDINGS_AND_DECISIONS.md §2). ``tutor/attribution.py`` derives licence
from ``source`` rather than this stored field, robust regardless of
ingest timing.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from .base import Connector

logger = logging.getLogger(__name__)

# PINNED — see module docstring above before touching this.
API_VERSION = "v4.2.7"
BASE_URL = f"https://isaacscience.org/api/{API_VERSION}/api"

REQUEST_TIMEOUT = 15  # seconds

# Hand-authored, extensible — see module docstring "TOPIC MAPPING".
# Keyed by subject, then by Isaac tag string (lowercased, spaces->underscores).
# One dict per subject: tag vocabularies don't overlap meaningfully across
# subjects (biology's "transport" and chemistry's "transport [of
# electrons]" aren't the same concept).
_TAG_TO_TOPIC_BY_SUBJECT: dict[str, dict[str, str]] = {
    "biology": {
        # biochemistry
        "biochemistry": "biochemistry",
        "carbohydrates": "biochemistry",
        "proteins": "biochemistry",
        "lipids": "biochemistry",
        "nucleic_acids": "biochemistry",
        "dna": "biochemistry",
        "enzymes": "biochemistry",
        "water": "biochemistry",
        # cell biology
        "cell_biology": "cell_biology",
        "cells": "cell_biology",
        "cell_structure": "cell_biology",
        "cell_membrane": "cell_biology",
        "cell_division": "cell_biology",
        "mitosis": "cell_biology",
        "meiosis": "cell_biology",
        # genetics
        "genetics": "genetics",
        "inheritance": "genetics",
        "variation": "genetics",
        "evolution": "genetics",
        "gene_expression": "genetics",
        "genetic_diversity": "genetics",
        # physiology
        "physiology": "physiology",
        "exchange": "physiology",
        "transport": "physiology",
        "gas_exchange": "physiology",
        "circulatory_system": "physiology",
        "digestion": "physiology",
        "nervous_system": "physiology",
        "homeostasis": "physiology",
        "immunity": "physiology",
        # ecology
        "ecology": "ecology",
        "ecosystems": "ecology",
        "populations": "ecology",
        "biodiversity": "ecology",
        # data analysis / statistics
        "bio_maths_skills": "data_analysis",
        "bio_statistical_tests": "data_analysis",
        "statistics": "data_analysis",
    },
    "chemistry": {
        # Isaac tags every chemistry concept with one of four broad
        # category tags (physical/organic/inorganic/foundations) as well
        # as finer-grained tags. Mapping both is deliberately redundant:
        # if Isaac ever drops the broad tag, the specific one still
        # resolves it.
        "physical": "physical_chemistry",
        "organic": "organic_chemistry",
        "inorganic": "inorganic_chemistry",
        "foundations": "foundations",
        "acids_and_bases": "physical_chemistry",
        "kinetics": "physical_chemistry",
        "electrochemistry": "physical_chemistry",
        "energetics": "physical_chemistry",
        "entropy": "physical_chemistry",
        "equilibrium": "physical_chemistry",
        "bonding": "inorganic_chemistry",
        "isomerism": "organic_chemistry",
        "functional_groups": "organic_chemistry",
        "organic_reactions": "organic_chemistry",
        "organic_mechanisms": "organic_chemistry",
        "atomic_structure": "foundations",
        "gas_laws": "foundations",
        "stoichiometry": "foundations",
    },
}

_GLOSSARY_INLINE_RE = re.compile(r'\[glossary-inline:[^|]+\|[^"\]]*"([^"]+)"\]')


def _clean_markdown(value: str) -> str:
    """Strip Isaac's glossary-inline markup down to the plain term text."""
    return _GLOSSARY_INLINE_RE.sub(r"\1", value)


def _collect_text_fragments(node: dict[str, Any]) -> list[str]:
    """Recursively walk a content node's children, collecting text.

    Figure nodes contribute their caption as "[Figure: ...]" rather than
    the image itself — non-text content is a documented limitation, not
    handled here.
    """
    fragments: list[str] = []
    value = node.get("value")
    if node.get("type") == "figure":
        if value:
            fragments.append(f"[Figure: {value}]")
    elif value:
        fragments.append(_clean_markdown(value))
    for child in node.get("children") or []:
        fragments.extend(_collect_text_fragments(child))
    return fragments


def _extract_sections(concept: dict[str, Any]) -> list[dict[str, str]]:
    """Split one concept JSON into natural sections: the top-level intro
    (all non-accordion content blocks combined) plus one section per
    accordion sub-item, e.g. "Carbohydrates" -> "Carbohydrates -
    Monosaccharides"."""
    title = concept.get("title") or concept.get("id", "untitled")
    sections: list[dict[str, str]] = []
    intro_fragments: list[str] = []

    for child in concept.get("children") or []:
        if child.get("layout") == "accordion":
            for item in child.get("children") or []:
                item_title = item.get("title", "")
                text = "\n\n".join(_collect_text_fragments(item)).strip()
                if text:
                    sections.append(
                        {
                            "title": f"{title} — {item_title}" if item_title else title,
                            "text": text,
                        }
                    )
        else:
            intro_fragments.extend(_collect_text_fragments(child))

    intro_text = "\n\n".join(intro_fragments).strip()
    if intro_text:
        sections.insert(0, {"title": title, "text": intro_text})

    return sections


class IsaacScienceConnector(Connector):
    source_name = "isaac_science"

    def __init__(self, subject: str = "biology", page_limit: int = 200) -> None:
        self.subject = subject
        self.page_limit = page_limit

    def fetch(self) -> list[dict[str, Any]]:
        concept_ids = self._list_concept_ids()
        docs: list[dict[str, Any]] = []
        for concept_id in concept_ids:
            concept = self._get_concept(concept_id)
            if concept is None:
                continue
            docs.extend(self._concept_to_documents(concept))
        print(
            f"[IsaacScienceConnector] Produced {len(docs)} document(s) "
            f"from {len(concept_ids)} concept(s) (subject={self.subject!r})."
        )
        return docs

    # -- API calls -----------------------------------------------------

    def _list_concept_ids(self) -> list[str]:
        ids: list[str] = []
        start_index = 0
        while True:
            body = self._get(
                f"{BASE_URL}/pages/concepts",
                params={
                    "subjects": self.subject,
                    "limit": self.page_limit,
                    "start_index": start_index,
                },
            )
            if body is None:
                break
            results = body.get("results", [])
            # Filter client-side on tags too, regardless of whether the
            # `subjects` query param is fully reliable: cheap to
            # double-check here, expensive to silently ingest the wrong
            # subject's content.
            ids.extend(
                r["id"] for r in results if self.subject in (r.get("tags") or [])
            )
            if len(results) < self.page_limit:
                break
            start_index += self.page_limit
        return ids

    def _get_concept(self, concept_id: str) -> Optional[dict[str, Any]]:
        return self._get(f"{BASE_URL}/pages/concepts/{concept_id}")

    def _get(
        self, url: str, params: dict[str, Any] | None = None
    ) -> Optional[dict[str, Any]]:
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            logger.warning("[IsaacScienceConnector] Request failed for %s: %s", url, e)
            return None
        if resp.status_code != 200:
            logger.warning(
                "[IsaacScienceConnector] %s -> HTTP %s. API_VERSION %r may be "
                "stale — see module docstring for how to rediscover it.",
                url, resp.status_code, API_VERSION,
            )
            return None
        try:
            return resp.json()
        except ValueError:
            logger.warning(
                "[IsaacScienceConnector] %s returned non-JSON (likely the SPA "
                "HTML shell) — API_VERSION %r is probably stale; see module "
                "docstring.", url, API_VERSION,
            )
            return None

    # -- Document construction ------------------------------------------

    def _map_topic(self, tags: list[str]) -> Optional[str]:
        tag_map = _TAG_TO_TOPIC_BY_SUBJECT.get(self.subject, {})
        for tag in tags:
            key = tag.lower().replace(" ", "_")
            if key in tag_map:
                return tag_map[key]
        return None

    def _concept_to_documents(self, concept: dict[str, Any]) -> list[dict[str, Any]]:
        audience = concept.get("audience") or []
        stages = {s for a in audience for s in (a.get("stage") or [])}
        if "a_level" not in stages:
            return []  # core tier only from this source; no GCSE content

        concept_id = concept["id"]
        tags = concept.get("tags") or []
        topic = self._map_topic(tags)
        if topic is None:
            logger.warning(
                "[IsaacScienceConnector] No topic mapping for concept %r "
                "(tags=%s) — ingested without a topic; won't surface in "
                "topic-filtered retrieval until _TAG_TO_TOPIC is extended.",
                concept_id, tags,
            )

        retrieved_date = datetime.now(timezone.utc).date().isoformat()
        docs: list[dict[str, Any]] = []
        for i, section in enumerate(_extract_sections(concept)):
            docs.append(
                {
                    "id": f"{concept_id}__{i}",
                    "text": section["text"],
                    "source": self.source_name,
                    "metadata": {
                        "subject": self.subject,
                        "difficulty_tier": "core",
                        "level": "a_level",
                        "topic": topic,
                        "concept_id": concept_id,
                        "spec_code": None,
                        "misconceptions": None,
                        "prerequisites": None,
                        "source": self.source_name,
                        "source_url": f"https://isaacscience.org/concepts/{concept_id}",
                        "licence": "CC-BY-4.0",
                        "retrieved_date": retrieved_date,
                        "provenance_tier": "third_party_education_platform",
                        "section_title": section["title"],
                    },
                }
            )
        return docs


class IsaacChemistryConnector(IsaacScienceConnector):
    """Chemistry variant — same platform, API and parsing logic as
    ``IsaacScienceConnector``; only ``subject`` (and therefore the tag-to-
    topic map it looks up) differs. A thin subclass rather than a second
    copy, so ``connectors/registry.py`` keeps its "one class per registry
    key, no-arg instantiation" convention.
    """

    def __init__(self, page_limit: int = 200) -> None:
        super().__init__(subject="chemistry", page_limit=page_limit)

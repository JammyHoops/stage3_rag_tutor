"""Connector for Isaac Science (isaacscience.org) — curriculum retrieval source.

PROVENANCE — NEW. First connector for the core/foundation curriculum-tiering
design (docs/design/stage3-curriculum-retrieval-design.md). Originally
built for Biology, core (A-level) tier only, as a deliberately narrow
proof-of-concept slice; Chemistry (also on the Isaac platform) was added
straight after by parameterising subject + tag map rather than
duplicating the connector — see ``IsaacChemistryConnector`` below. Ada
Computer Science and the GCSE "foundation" tier remain explicitly
deferred — see README's TODO index.

WHY AN API CONNECTOR, NOT A SCRAPER: isaacscience.org is a JS-rendered SPA
— a raw HTML fetch returns an empty shell, confirmed directly (headless
Edge + network inspection) before writing this module. The site calls a
real, public, unauthenticated JSON API to render content:

    GET {BASE}/pages/concepts?subjects=<subject>&limit=N&start_index=N
        → {"results": [{"id", "title", "tags", ...}, ...]}
    GET {BASE}/pages/concepts/{id}
        → full concept: title, tags, audience[].stage (gcse/a_level),
          a "children" tree of markdown content blocks, some laid out as
          an accordion of named sub-sections (natural chunk boundaries).

PINNED API VERSION — READ BEFORE DEBUGGING A FAILURE HERE:
The API is version-pinned in the URL (``API_VERSION`` below) and there is
NO stable alias — checked directly: both an unversioned path and
``/api/latest/...`` failed (502, or silently served the SPA's HTML shell
instead of JSON — a real observed failure mode, not hypothetical). This is
the same class of gotcha as the Gemini model-ID issue in
``llm/client.py``, except there is no ``-latest``-style escape hatch here.
If ``fetch()`` starts returning nothing / logging "stale" warnings: load
isaacscience.org in a real browser with devtools network tab open, find
any request under ``/api/v.../api/...``, and update ``API_VERSION`` to
match. There is no cleaner discovery mechanism — checked.

CONTENT SEGMENTATION: rather than returning one whole concept as a single
document and relying on the generic chunker, this connector splits each
concept at its own natural boundaries (the top-level intro plus each
accordion sub-section) and returns one document per section — see
``_extract_sections``. This is why ``chunking.py``'s passthrough chunker
is adequate for this source: the structure-aware splitting already
happened here, matching the note already left in that module's TODO.

TOPIC MAPPING: Isaac's own ``tags`` are far more granular than the fixed
chat-UI topic list (``data/topics/biology.json``) needs. ``_TAG_TO_TOPIC``
is a small, hand-authored, extensible lookup — a concept whose tags don't
hit it is still ingested (subject-scoped retrieval still finds it) but
logged with a warning, since a silently-unmapped concept would just never
surface in topic-filtered retrieval with no visible sign why.

TODO:
    [ ] GCSE "foundation" tier for Biology/Chemistry specifically —
        checked directly against the live API and NOT available from this
        source: Biology has zero GCSE-stage concepts, and Chemistry's 8
        GCSE-tagged concepts share identical text with their A-level
        version (no simpler explanation to blend in). Real foundation
        content came from ``connectors/ada_computer_science.py`` instead,
        which has genuine per-section stage splits — see that module.
        ``concept_id`` (below) and the ``difficulty_tier`` retrieval filter
        (``retriever/search.py``) were built with that connector in mind
        but apply here too.
    [ ] ``prerequisites`` is stored as ``None`` — a real cross-concept
        dependency graph (what the design doc's trigger logic actually
        wants) is not something this source's data provides and is a
        separate, deliberately-deferred design decision — same category as
        the mastery-update-rule stub in ``student_state/store.py``, not to
        be invented unilaterally. See ``ada_computer_science.py``'s
        docstring for the narrower, source-grounded alternative that
        connector uses instead (same-concept, lower-difficulty sections).
    [ ] LaTeX/mhchem markup (``$\\ce{C6H12O6}$`` etc.) is left as-is in
        chunk text — not evaluated for how well it survives into the LLM
        prompt / whether it should be stripped or reformatted.
    [ ] AS/A2 split (design doc's ``level`` field) is not available at the
        granularity this API exposes — only ``audience[].stage`` ("gcse" /
        "a_level") was observed. ``level`` is stored as the raw stage
        value; the finer AS/A2 distinction is a documented limitation, not
        implemented.
    [ ] ``spec_code`` / ``misconceptions`` are not present in this source's
        data — left ``None`` rather than guessed.
CORRECTED (2026-08-16): the design doc's assumed licence, CC BY-NC-SA
4.0, was WRONG — confirmed directly via a headless-browser render of the
real site (isaacscience.org is a JS-rendered SPA; a plain fetch only
ever returns the shell, which is why this wasn't caught earlier).
The actual footer link target, checked on multiple concept pages and
the homepage, is ``https://creativecommons.org/licenses/by/4.0/`` —
**CC BY 4.0**, no NonCommercial or ShareAlike clause. ``licence`` below
is now ``CC-BY-4.0``. RE-INGESTED same day (``python -m stage3.ingest
--source isaac_science``) — this connector's stored Chroma metadata is
current, not stale; the previously-noted ``concept_id`` staleness on
Biology (see the curriculum-retrieval section of README.md) was fixed
by this same re-ingest, for free. The CC-attribution feature (see
`tutor/prompt_template.py`) still derives licence from `source` rather
than the stored field, on principle (robust regardless of ingest
timing), not because this data is currently known-stale.
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
# Keyed by subject, then by Isaac tag string (lowercased, spaces→underscores).
# One dict per subject because tag vocabularies don't overlap meaningfully
# across subjects (biology's "transport" and chemistry's "transport [of
# electrons]" are not the same concept) — see IsaacChemistryConnector.
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
        # data analysis / statistics — a substantial real chunk of Isaac's
        # actual biology concept catalog (statistical tests for biology data),
        # not just a hypothetical bucket; added after seeing it live.
        "bio_maths_skills": "data_analysis",
        "bio_statistical_tests": "data_analysis",
        "statistics": "data_analysis",
    },
    "chemistry": {
        # Isaac tags every chemistry concept with one of its own four broad
        # category tags (physical/organic/inorganic/foundations) *as well
        # as* finer-grained tags — confirmed directly against the live API
        # (all 25 A-level-tagged concepts checked) rather than assumed.
        # Mapping both the broad and the specific tags is redundant by
        # design: if Isaac ever drops the broad tag from a concept, the
        # specific one still resolves it.
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
    the image itself — matches the existing "non-text content, documented
    limitation" stance in connectors/curriculum_docs.py.
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
    accordion sub-item, e.g. "Carbohydrates" -> "Carbohydrates —
    Monosaccharides". This pre-segmentation is why chunking.py's
    passthrough is adequate for this source — see module docstring.
    """
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
            # Filter client-side on tags regardless of whether the
            # `subjects` query param is fully reliable — see module
            # docstring / plan rationale: cheap to double-check here,
            # not cheap to silently ingest the wrong subject's content.
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
            return []  # core tier only for this pass — GCSE deferred

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
    """Chemistry variant — same platform, same API, same parsing logic as
    ``IsaacScienceConnector``; only ``subject`` (and therefore the tag→topic
    map it looks up) differs. A thin no-arg-constructible subclass rather
    than a second copy of the class, so ``connectors/registry.py`` can keep
    its existing "one class per registry key, no-arg instantiation"
    convention (see ``ingest.py``: ``CONNECTORS[source_name]()``).

    Confirmed directly against the live API before writing this (25
    chemistry concepts, 23 of them A-level-tagged; cc_equilibrium and
    cc_moles are GCSE-only and correctly skipped by the inherited core-tier
    filter — they're the seed content for the still-deferred foundation
    tier, not a bug).
    """

    def __init__(self, page_limit: int = 200) -> None:
        super().__init__(subject="chemistry", page_limit=page_limit)

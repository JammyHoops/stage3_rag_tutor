"""Connector for Ada Computer Science (adacomputerscience.org).

PROVENANCE — NEW. Third subject for the core/foundation curriculum-tiering
design (docs/design/stage3-curriculum-retrieval-design.md), and the first
connector to deliver a *genuine* foundation tier.

WHY NOT IN isaac_science.py: this is a different domain
(adacomputerscience.org, not isaacscience.org) running the same
open-source platform (confirmed live: identical ``isaacConceptPage`` JSON
shape, identical ``/api/{version}/api/pages/concepts`` path). ``_clean_
markdown`` and ``_collect_text_fragments`` are imported from
``isaac_science.py`` rather than duplicated — genuinely shared logic.
Everything else here is new because the tier extraction is structurally
different: Isaac Science's Biology/Chemistry connector decides
``difficulty_tier`` once per whole concept; this one decides it per
SECTION, because that's what Ada's data actually supports (see below).

WHY A GENUINE FOUNDATION TIER, UNLIKE BIOLOGY/CHEMISTRY: checked directly
against the live API before writing this (see conversation / plan). Isaac
Science has no real GCSE content for Biology (0 concepts) and Chemistry's
GCSE-tagged concepts share identical text with their A-level version — no
simpler explanation exists to blend in. Ada's concept pages are
different: individual accordion sections carry their OWN ``audience``
list, and GCSE-only sections contain a genuinely simpler technique, not
re-tagged prose. Confirmed example (``number_arithmetic``, "Binary
arithmetic"): "Binary multiplication (whole numbers)" is tagged
``a_level``-only, while "Binary multiplication (left shift)" — a
different, simpler technique — is tagged ``gcse``-only. That is what
``difficulty_tier`` is built from here.

CONCEPT-ID / PREREQUISITES: ``concept_id`` (Isaac's own id, e.g.
``number_arithmetic``) is stored explicitly on every document — the
concept-ID granularity blocker in the design doc is resolved this far,
honestly. What it is NOT resolved into is a cross-concept ``prerequisites``
graph: Ada's data gives same-concept, lower-difficulty SECTIONS, not a
dependency graph between different concepts. The practical consequence:
whenever the foundation-tier trigger is eventually built (still out of
scope — see student_state/store.py's mastery-rule stub, which it
depends on), the natural query for "simpler treatment of what the student
is currently asking about" is `difficulty_tier="foundation"` filtered to
the SAME `concept_id` already in play — not a lookup into a hand-authored
`prerequisites` list. `prerequisites` is stored as `None`, matching
isaac_science.py's convention for fields this source doesn't provide.

PINNED API VERSION: confirmed working with the same version string as
Isaac Science (``v4.2.7``) at time of writing, but pinned independently —
this is a separate deployment of the same platform and could drift out of
lockstep. Same failure mode / rediscovery method as documented in
isaac_science.py's module docstring (502, or JSON where the SPA's HTML
shell was expected).

CORRECTED (2026-08-16): the design doc's assumed licence, CC BY-SA (no
version stated), was WRONG — confirmed via a headless-browser render
(adacomputerscience.org is also a JS-rendered SPA; a plain fetch only
returns an empty shell, which is why this wasn't caught earlier). The
actual footer text and CC link target, checked on multiple concept
pages and the homepage, is **CC BY-NC-SA 4.0** — it DOES carry a
NonCommercial clause, unlike what was assumed. ``licence`` below is now
``CC-BY-NC-SA-4.0``. RE-INGESTED same day (``python -m stage3.ingest
--source ada_computer_science`` — 1908 chunks, 344 concepts, count
unchanged from before, confirming the idempotent upsert worked) — this
connector's stored Chroma metadata is current, not stale. See the
matching note in ``isaac_science.py`` for why the CC-attribution feature
still derives licence from `source` rather than the stored field
regardless (robustness, not a workaround for stale data anymore).

TODO:
    [ ] `spec_code`: Ada's audience data includes an `examBoard` list per
        section (e.g. ["aqa","ocr","wjec"]) but not a specific spec code
        number — left `None` rather than guessed, same policy as Isaac
        Science. The exam-board list itself is discarded, not stored; add
        it as its own field later if a consumer needs it.
    [ ] Project/meta tags (`projects`, `web_project`, `database_project`,
        `progamming_project`, `aqa_nea_project`, `ocr_nea_project`,
        `design_and_development`, `effective_use_of_tools`) are
        deliberately excluded from `_TAG_TO_TOPIC` — checked against real
        ingest results (see conversation): every concept carrying one of
        these ALSO carries a more specific content-area tag (`hardware`,
        `software`, `program_design`, `testing`, etc. — all mapped) except
        genuine NEA/coursework project-scenario concepts (~40 of them,
        e.g. `projweb_coursepal_*`, `dbs_scenario_*`), which really are
        applied-project scaffolding rather than topic-explanation content
        and are correctly left unmapped — won't surface in topic-filtered
        retrieval, still findable via subject-only retrieval. Not a gap to
        close, a deliberate content-type distinction.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from .base import Connector
from .isaac_science import _clean_markdown, _collect_text_fragments

logger = logging.getLogger(__name__)

# PINNED — see module docstring above before touching this.
API_VERSION = "v4.2.7"
BASE_URL = f"https://adacomputerscience.org/api/{API_VERSION}/api"

REQUEST_TIMEOUT = 15  # seconds

# Hand-authored, extensible — see module docstring "TODO" re: excluded
# project/meta tags. Keys are Ada tag strings, lowercased with
# spaces→underscores.
_TAG_TO_TOPIC: dict[str, str] = {
    "programming": "programming",
    "programming_concepts": "programming",
    "subroutines": "programming",
    "object_oriented_programming": "programming",
    # program design / software engineering process / testing — grouped
    # under "programming" (matches how exam-board specs place these:
    # design, testing and the dev lifecycle sit in the Programming paper,
    # not Computer Systems). Reached via their specific co-tags, not the
    # "design_and_development" meta-tag itself — see module docstring TODO.
    "program_design": "programming",
    "software_engineering_principles": "programming",
    "testing": "programming",
    "computer_systems": "computer_systems",
    "operating_systems": "computer_systems",
    "number_representation": "computer_systems",
    "boolean_logic": "computer_systems",
    "hardware": "computer_systems",
    "software": "computer_systems",
    "data_structures_and_algorithms": "algorithms_and_data_structures",
    "data_structures": "algorithms_and_data_structures",
    "theory_of_computation": "algorithms_and_data_structures",
    "computational_thinking": "algorithms_and_data_structures",
    "computer_networks": "computer_networks",
    "networking": "computer_networks",
    "cyber_security": "cyber_security",
    "security": "cyber_security",
    "data_and_information": "data_and_information",
    # image/sound representation and "creating media" are data-
    # representation content in GCSE/A-level specs, not a separate topic.
    "image_representation": "data_and_information",
    "sound_representation": "data_and_information",
    "creating_media": "data_and_information",
    "impacts_of_digital_tech": "impacts_and_ethics",
    "ai_and_machine_learning": "ai_and_machine_learning",
    "artificial_intelligence": "ai_and_machine_learning",
    "machine_learning": "ai_and_machine_learning",
}


def _section_difficulty_tier(stages: set[str]) -> Optional[str]:
    """Map a section's own audience stages to our difficulty_tier.

    a_level takes priority if both are present (matches the existing
    Biology/Chemistry convention: a_level-inclusive content is safe to
    surface by default). gcse-only sections are the genuine foundation
    content — see module docstring. Anything else (Scotland's
    scotland_national_5 / scotland_higher / scotland_advanced_higher, or
    Ada's own internal "core"/"advanced" curriculum labels with neither
    gcse nor a_level present) is not guessed at — skipped.
    """
    if "a_level" in stages:
        return "core"
    if "gcse" in stages:
        return "foundation"
    return None


def _extract_tiered_sections(concept: dict[str, Any]) -> list[dict[str, Any]]:
    """Split one concept JSON into tiered sections: the top-level intro
    (tiered from the concept's own top-level audience) plus one section
    per accordion sub-item (tiered from that item's own audience — Ada's
    accordion items carry their own audience list, unlike Isaac Science's
    where only the whole concept is tiered). Sections whose stages don't
    resolve to a difficulty_tier are dropped, not guessed.
    """
    title = concept.get("title") or concept.get("id", "untitled")
    concept_stages = {
        s for a in (concept.get("audience") or []) for s in (a.get("stage") or [])
    }
    concept_tier = _section_difficulty_tier(concept_stages)

    sections: list[dict[str, Any]] = []
    intro_fragments: list[str] = []

    for child in concept.get("children") or []:
        if child.get("layout") == "accordion":
            for item in child.get("children") or []:
                item_stages = {
                    s
                    for a in (item.get("audience") or [])
                    for s in (a.get("stage") or [])
                }
                tier = _section_difficulty_tier(item_stages)
                if tier is None:
                    continue  # e.g. Scotland-only section — not guessed
                item_title = item.get("title", "")
                text = "\n\n".join(_collect_text_fragments(item)).strip()
                if text:
                    sections.append(
                        {
                            "title": f"{title} — {item_title}" if item_title else title,
                            "text": text,
                            "difficulty_tier": tier,
                        }
                    )
        else:
            intro_fragments.extend(_collect_text_fragments(child))

    intro_text = "\n\n".join(intro_fragments).strip()
    if intro_text and concept_tier is not None:
        sections.insert(
            0, {"title": title, "text": intro_text, "difficulty_tier": concept_tier}
        )

    return sections


class AdaComputerScienceConnector(Connector):
    source_name = "ada_computer_science"

    def __init__(self, page_limit: int = 250) -> None:
        self.subject = "computer_science"
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
            f"[AdaComputerScienceConnector] Produced {len(docs)} document(s) "
            f"from {len(concept_ids)} concept(s)."
        )
        return docs

    # -- API calls -----------------------------------------------------

    def _list_concept_ids(self) -> list[str]:
        ids: list[str] = []
        start_index = 0
        while True:
            body = self._get(
                f"{BASE_URL}/pages/concepts",
                params={"limit": self.page_limit, "start_index": start_index},
            )
            if body is None:
                break
            results = body.get("results", [])
            # The `subjects` query param is a no-op on this platform (same
            # finding as Isaac Science) — filter client-side instead. A
            # handful of real outliers (Scotland/SQA reference pages, one
            # untagged page) lack "computer_science" and are correctly
            # excluded here, not a bug.
            ids.extend(
                r["id"] for r in results if "computer_science" in (r.get("tags") or [])
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
            logger.warning("[AdaComputerScienceConnector] Request failed for %s: %s", url, e)
            return None
        if resp.status_code != 200:
            logger.warning(
                "[AdaComputerScienceConnector] %s -> HTTP %s. API_VERSION %r "
                "may be stale — see module docstring for how to rediscover it.",
                url, resp.status_code, API_VERSION,
            )
            return None
        try:
            return resp.json()
        except ValueError:
            logger.warning(
                "[AdaComputerScienceConnector] %s returned non-JSON (likely "
                "the SPA HTML shell) — API_VERSION %r is probably stale; see "
                "module docstring.", url, API_VERSION,
            )
            return None

    # -- Document construction ------------------------------------------

    def _map_topic(self, tags: list[str]) -> Optional[str]:
        for tag in tags:
            key = tag.lower().replace(" ", "_")
            if key in _TAG_TO_TOPIC:
                return _TAG_TO_TOPIC[key]
        return None

    def _concept_to_documents(self, concept: dict[str, Any]) -> list[dict[str, Any]]:
        sections = _extract_tiered_sections(concept)
        if not sections:
            return []  # e.g. fully Scotland-only concept — nothing tiered

        concept_id = concept["id"]
        tags = concept.get("tags") or []
        topic = self._map_topic(tags)
        if topic is None:
            logger.warning(
                "[AdaComputerScienceConnector] No topic mapping for concept "
                "%r (tags=%s) — ingested without a topic; won't surface in "
                "topic-filtered retrieval until _TAG_TO_TOPIC is extended.",
                concept_id, tags,
            )

        retrieved_date = datetime.now(timezone.utc).date().isoformat()
        docs: list[dict[str, Any]] = []
        for i, section in enumerate(sections):
            tier = section["difficulty_tier"]
            docs.append(
                {
                    "id": f"{concept_id}__{i}",
                    "text": section["text"],
                    "source": self.source_name,
                    "metadata": {
                        "subject": self.subject,
                        "difficulty_tier": tier,
                        "level": "a_level" if tier == "core" else "gcse",
                        "topic": topic,
                        "concept_id": concept_id,
                        "spec_code": None,
                        "misconceptions": None,
                        "prerequisites": None,
                        "source": self.source_name,
                        "source_url": f"https://adacomputerscience.org/concepts/{concept_id}",
                        "licence": "CC-BY-NC-SA-4.0",
                        "retrieved_date": retrieved_date,
                        "provenance_tier": "third_party_education_platform",
                        "section_title": section["title"],
                    },
                }
            )
        return docs

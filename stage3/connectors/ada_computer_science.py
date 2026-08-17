"""Connector for Ada Computer Science (adacomputerscience.org).

PROVENANCE — NEW. Third subject for the core/foundation curriculum-tiering
design (docs/design/stage3-curriculum-retrieval-design.md), and the only
connector that delivers a genuine foundation (GCSE) tier — see
docs/design/FINDINGS_AND_DECISIONS.md §2 for why Isaac Science's
Biology/Chemistry content doesn't.

Runs the same open-source platform as Isaac Science (identical JSON shape,
identical API path, on a different domain) — ``_clean_markdown`` and
``_collect_text_fragments`` are imported from ``isaac_science.py`` rather
than duplicated. Tier extraction is structurally different from that
connector though: Isaac Science decides ``difficulty_tier`` once per whole
concept; this one decides it per SECTION, because individual accordion
sections here carry their own ``audience`` list.

``concept_id`` is stored explicitly on every document. ``prerequisites``
is stored as ``None`` — see docs/TODO.md for the foundation-tier trigger
this blocks.

PINNED API VERSION: same version string as Isaac Science (``v4.2.7``) at
time of writing, pinned independently since this is a separate deployment
of the platform. Same failure mode / rediscovery method as documented in
``isaac_science.py``.

Licence is CC BY-NC-SA 4.0 (confirmed via headless-browser render — see
FINDINGS_AND_DECISIONS.md §2). ``spec_code`` is left ``None``: Ada's
audience data includes an ``examBoard`` list per section but not a spec
code number. Project/coursework meta-tags (NEA scenario concepts) are
deliberately excluded from ``_TAG_TO_TOPIC`` — see docs/TODO.md.
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

# Hand-authored, extensible. Keys are Ada tag strings, lowercased with
# spaces->underscores. See docs/TODO.md for excluded project/meta tags.
_TAG_TO_TOPIC: dict[str, str] = {
    "programming": "programming",
    "programming_concepts": "programming",
    "subroutines": "programming",
    "object_oriented_programming": "programming",
    # design/testing/dev-lifecycle content sits in the Programming paper
    # in exam-board specs, not Computer Systems, so it's grouped here too.
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

    a_level takes priority if both are present. gcse-only sections are the
    genuine foundation content. Anything else (Scotland's own stage
    labels, or Ada's internal "core"/"advanced" labels with neither gcse
    nor a_level present) is skipped, not guessed.
    """
    if "a_level" in stages:
        return "core"
    if "gcse" in stages:
        return "foundation"
    return None


def _extract_tiered_sections(concept: dict[str, Any]) -> list[dict[str, Any]]:
    """Split one concept JSON into tiered sections: the top-level intro
    (tiered from the concept's own audience) plus one section per
    accordion sub-item (tiered from that item's own audience — unlike
    Isaac Science, where only the whole concept is tiered). Sections whose
    stages don't resolve to a difficulty_tier are dropped, not guessed.
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

"""Base connector interface for all knowledge sources.

PROVENANCE — KEPT (near-verbatim) from AI_IT_Helpdesk
``services/kb_agent/connectors/base.py``.

WHY KEPT: the abstraction is source-agnostic. It normalises every source
into the same document shape ({id, text, source, metadata}) before anything
downstream sees it, which is what made the helpdesk able to mix Spiceworks
tickets, vendor docs and transcripts in one index. Stage 3 reuses the same
seam to mix awarding-body specifications, mark schemes and teacher
materials. For Chapter 3: this is the component-reuse boundary — the
interface pre-existed; the concrete curriculum connectors are new work.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Connector(ABC):
    """Abstract base class for all knowledge-base sources.

    Each connector must return a list of document dicts with keys:
    - "id": str (unique within that source — enables stable Chroma IDs)
    - "text": str (full text content, pre-chunking)
    - "source": str (name of the connector)
    - "metadata": dict (e.g. subject, topic, provenance tier, file path)
    """

    source_name: str = "base"

    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        """Fetch and normalise documents from the source.

        Minimal logic only: file reads / API calls plus light cleaning
        into the standard document schema. Chunking happens later
        (stage3/chunking.py), not here.
        """
        raise NotImplementedError

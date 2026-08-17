"""Base connector interface for all knowledge sources.

PROVENANCE — KEPT (near-verbatim) from AI_IT_Helpdesk. Normalises every
source into the same document shape before anything downstream sees it.
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

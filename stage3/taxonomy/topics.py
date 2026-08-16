"""Controlled subject/topic taxonomy for the tutoring UI.

PROVENANCE — NEW. Supports a Claude-Projects-style UI: subject = project,
topic = chat within that project. Topics are a FIXED, curriculum-authored
list per subject — students do not invent topics. Free-text topic naming
and a teacher-facing topic-authoring UI are deferred; for now these files
are hand-edited directly, which also means a future authoring UI would just
write the same file shape.

Expected layout under data/topics/ (one file per subject):

    data/topics/<subject>.json
    e.g. data/topics/mathematics.json ->
        {"subject": "mathematics",
         "topics": [{"id": "algebra", "label": "Algebra"}, ...]}

The subject slug should match the corresponding data/curriculum/<subject>/
directory by convention (not enforced here — retrieval stays subject-scoped
only; topic is not yet wired into curriculum chunk metadata, see
connectors/curriculum_docs.py TODO).

TODO:
    [ ] Teacher-facing topic authoring UI (writes these same JSON files).
    [ ] Validate subject slugs against data/curriculum/ at ingest time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import CONFIG


@dataclass
class Topic:
    id: str
    label: str


def list_subjects(topics_dir: Path | None = None) -> list[str]:
    """Return the sorted subject slugs that have a topic file."""
    directory = topics_dir or CONFIG.paths.topics_dir
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


def list_topics(subject: str, topics_dir: Path | None = None) -> list[Topic]:
    """Return the fixed topic list for a subject; [] if the subject is unknown."""
    directory = topics_dir or CONFIG.paths.topics_dir
    path = directory / f"{subject}.json"
    if not path.exists():
        return []

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    return [Topic(id=t["id"], label=t["label"]) for t in raw.get("topics", [])]


def get_topic(
    subject: str, topic_id: str, topics_dir: Path | None = None
) -> Optional[Topic]:
    """Look up one topic; None if the subject or topic id is unknown."""
    for topic in list_topics(subject, topics_dir):
        if topic.id == topic_id:
            return topic
    return None

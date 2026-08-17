"""Connector for curriculum documents on local disk.

PROVENANCE — NEW. Follows the pattern of the helpdesk's transcript
connector (walk a directory, normalise each file into the standard
document schema).

Not currently wired to any real content — every in-scope subject is
sourced from Isaac Science / Ada Computer Science instead (see those
connectors). Kept in case a genuinely document-only source (e.g. a
locally-supplied spec PDF) is ever added — see docs/TODO.md.

Expected layout under data/curriculum/ (drives metadata):

    data/curriculum/<subject>/<provenance_tier>/<files>
    e.g. data/curriculum/biology/awarding_body_spec/organisms.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import CONFIG
from .base import Connector

# File types readable without extraction libraries; no PDF support yet.
_TEXT_EXTS = {".md", ".txt"}


class CurriculumDocsConnector(Connector):
    source_name = "curriculum_docs"

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or CONFIG.paths.curriculum_dir

    def fetch(self) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        if not self.root_dir.exists():
            print(f"[CurriculumDocsConnector] Missing directory: {self.root_dir}")
            return docs

        for path in sorted(self.root_dir.rglob("*")):
            if path.suffix.lower() not in _TEXT_EXTS or not path.is_file():
                continue

            rel = path.relative_to(self.root_dir)
            parts = rel.parts
            # <subject>/<provenance_tier>/<file> — fall back gracefully if
            # the layout is shallower than expected.
            subject = parts[0] if len(parts) >= 2 else "unassigned"
            tier = parts[1] if len(parts) >= 3 else "unassigned"

            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:  # pragma: no cover
                print(f"[CurriculumDocsConnector] Failed to read {path}: {e}")
                continue

            docs.append(
                {
                    "id": str(rel).replace("\\", "/"),
                    "text": text,
                    "source": self.source_name,
                    "metadata": {
                        "source": self.source_name,
                        "subject": subject,
                        "provenance_tier": tier,
                        "file": str(rel),
                    },
                }
            )

        print(f"[CurriculumDocsConnector] Loaded {len(docs)} document(s).")
        return docs

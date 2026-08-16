"""Connector for curriculum documents on local disk.

PROVENANCE — NEW, but follows the pattern of the helpdesk's
``rasa_transcripts.py`` connector (walk a directory, normalise each file
into the standard document schema). Replaces the removed IT-specific
connectors (spiceworks, papercut, microsoft_support, google_support),
which had no use in a tutoring context.

Expected layout under data/curriculum/ (drives metadata):

    data/curriculum/<subject>/<provenance_tier>/<files>
    e.g. data/curriculum/biology/awarding_body_spec/organisms.md

RETIRED (2026-08-16 cleanup pass) — NOT DOING, no active driver. Subject
scope was confirmed 2026-08-14 as exactly three subjects (biology,
chemistry, computer_science), and every source actually collected for
that scope (Isaac Science, Ada Computer Science) has its own dedicated
connector with native structure-aware ingestion — this generic
local-filesystem connector was never wired to a real subject directory
and has no content under data/curriculum/. The taxonomy/PDF-extraction/
topic-metadata/copyright questions below were speculative for a source
that never materialised; keep this list only in case a genuinely
document-only source (e.g. a locally-supplied spec PDF) is ever added:
    - Subject/topic taxonomy alignment.
    - PDF extraction (pypdf / pdfplumber, kept local).
    - Topic-level metadata assignment (per file / heading / manifest).
    - Copyright position on ingesting exam-board materials for research
      use (would need ethics/write-up documentation).
    - Non-text content (diagrams, equations) — likely a documented
      limitation, mirroring the cursive-writing decision in Stage 2.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import CONFIG
from .base import Connector

# File types readable without extraction libraries. PDF extraction was
# never added — see RETIRED note above.
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

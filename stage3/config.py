"""Central configuration for Stage 3.

PROVENANCE — ADAPTED from AI_IT_Helpdesk's config module. All values can
be overridden from the environment (.env) so nothing sensitive is
hard-coded. See docs/design/FINDINGS_AND_DECISIONS.md for the reasoning
behind individual defaults (temperature, embedding model, etc).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Project root = directory containing the stage3/ package
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


@dataclass
class Paths:
    curriculum_dir: Path = DATA_DIR / "curriculum"
    chroma_dir: Path = DATA_DIR / "chroma"
    stage1_dir: Path = DATA_DIR / "stage1"
    stage2_inbox: Path = DATA_DIR / "stage2_inbox"
    stage2_archive: Path = DATA_DIR / "stage2_archive"
    student_db: Path = DATA_DIR / "student_state.db"
    topics_dir: Path = DATA_DIR / "topics"
    conversations_db: Path = DATA_DIR / "conversations.db"
    known_names_file: Path = DATA_DIR / "redaction" / "known_names.txt"
    allowed_terms_file: Path = DATA_DIR / "redaction" / "allowed_terms.txt"


@dataclass
class EmbeddingConfig:
    # Local model: no data leaves the machine at embedding time.
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class LLMConfig:
    provider: str = os.getenv("LLM_PROVIDER", "null")
    model: str = os.getenv("LLM_MODEL", "")
    api_key: str = os.getenv("LLM_API_KEY", "")
    temperature: float = 0.2
    max_output_tokens: int = 1024
    max_retries: int = 3
    retry_backoff_seconds: float = 2.0


@dataclass
class Stage3Config:
    paths: Paths = field(default_factory=Paths)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


CONFIG = Stage3Config()

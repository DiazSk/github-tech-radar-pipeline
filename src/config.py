"""Central configuration: loads .env and exposes paths + tunables.

Importing this module loads environment variables once. All other modules
read settings from here so there is a single source of truth.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = parent of the src/ package directory.
ROOT_DIR = Path(__file__).resolve().parent.parent

# Load .env (then .env.local overrides) if present. CI relies on real env vars.
load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / ".env.local", override=True)

# ---- Paths ----
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
DUCKDB_PATH = DATA_DIR / "tech_signals.duckdb"

# ---- LLM provider ----
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

# ---- Scraper ----
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip() or None
SCRAPE_LIMIT = int(os.getenv("SCRAPE_LIMIT", "25"))
README_SNIPPET_CHARS = int(os.getenv("README_SNIPPET_CHARS", "800"))
TRENDING_URL = "https://github.com/trending"
SEARCH_API_URL = "https://api.github.com/search/repositories"


def ensure_dirs() -> None:
    """Create data directories if they do not yet exist."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

"""LLM enrichment: raw repos -> structured TechSignal rows -> DuckDB.

Reads unprocessed data/raw/<date>.json files, calls the configured LLM with
`with_structured_output(TechSignal)`, and writes validated rows to DuckDB.
Days already present in the DB are skipped, so this is safe to re-run.

Run this where the LLM is reachable (locally with Ollama by default).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import List, Optional

from langchain_core.prompts import ChatPromptTemplate

from . import config, db
from .llm_provider import get_llm
from .models import RawRepo, TechSignal

SYSTEM_PROMPT = (
    "You are a precise tech-radar analyst. Extract structured tech metadata from "
    "a GitHub repository. Identify the concrete tools/frameworks/languages, the "
    "primary category, the maturity tier, a confidence score, and a one-line use "
    "case. Only output fields defined by the schema."
)

HUMAN_PROMPT = (
    "Extract tech signals from this GitHub repo.\n"
    "Name: {repo_name}\n"
    "Description: {description}\n"
    "Language: {language}\n"
    "Topics: {topics}\n"
    "README (first {snippet_chars} chars):\n{readme_snippet}"
)


def _build_chain():
    llm = get_llm()
    structured_llm = llm.with_structured_output(schema=TechSignal)
    prompt = ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", HUMAN_PROMPT)]
    )
    return prompt | structured_llm


def extract_repo(chain, repo: RawRepo) -> Optional[TechSignal]:
    """Run the LLM on a single repo, returning None on failure."""
    try:
        return chain.invoke(
            {
                "repo_name": repo.repo_name,
                "description": repo.description or "(none)",
                "language": repo.language or "(unknown)",
                "topics": ", ".join(repo.topics) if repo.topics else "(none)",
                "snippet_chars": config.README_SNIPPET_CHARS,
                "readme_snippet": repo.readme_snippet or "(no README)",
            }
        )
    except Exception as exc:  # noqa: BLE001 - keep the batch going
        print(f"[extractor] extraction failed for {repo.repo_name}: {exc}")
        return None


def _raw_files() -> List[Path]:
    return sorted(config.RAW_DIR.glob("*.json"))


def _date_from_path(path: Path) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(path.stem)
    except ValueError:
        return None


def _fallback_tools(repo: RawRepo) -> List[str]:
    """Guarantee every repo contributes at least one tool to the radar.

    The small local LLM frequently returns an empty `tools` list. Since all
    dashboard queries UNNEST the tools array, such repos would be invisible.
    Derive a sensible default from the language, then topics, then repo name.
    """
    if repo.language:
        return [repo.language]
    if repo.topics:
        return repo.topics[:3]
    return [repo.repo_name.split("/")[-1]]


def process_file(chain, con, path: Path) -> int:
    """Enrich every repo in a raw file and write to DuckDB. Returns row count."""
    scraped_date = _date_from_path(path)
    if scraped_date is None:
        print(f"[extractor] skipping non-date file: {path.name}")
        return 0

    raw_items = json.loads(path.read_text(encoding="utf-8"))
    repos = [RawRepo(**item) for item in raw_items]

    rows: List[dict] = []
    failures = 0
    for repo in repos:
        signal = extract_repo(chain, repo)
        if signal is None:
            failures += 1
            continue
        row = signal.model_dump()
        row["repo_name"] = repo.repo_name
        row["stars_today"] = repo.stars_today
        row["language"] = repo.language
        if not row.get("tools"):
            row["tools"] = _fallback_tools(repo)
        rows.append(row)

    inserted = db.insert_signals(con, rows, scraped_date)
    print(
        f"[extractor] {path.name}: {inserted} signals written, "
        f"{failures} failures out of {len(repos)} repos"
    )
    return inserted


def run(force: bool = False, only_date: Optional[str] = None) -> int:
    """Process all unprocessed raw files. Returns total rows written."""
    con = db.connect()
    processed = set() if force else db.get_processed_dates(con)

    files = _raw_files()
    if only_date:
        files = [p for p in files if p.stem == only_date]

    pending = [
        p
        for p in files
        if _date_from_path(p) is not None and (force or p.stem not in processed)
    ]

    if not pending:
        print("[extractor] nothing to do (all raw days already processed).")
        con.close()
        return 0

    chain = _build_chain()
    total = 0
    for path in pending:
        total += process_file(chain, con, path)

    print(f"[extractor] done. {total} rows written across {len(pending)} day(s).")
    con.close()
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich raw repos into DuckDB.")
    parser.add_argument(
        "--force", action="store_true", help="Re-process days already in the DB."
    )
    parser.add_argument(
        "--date", help="Only process a specific YYYY-MM-DD raw file.", default=None
    )
    args = parser.parse_args()
    run(force=args.force, only_date=args.date)


if __name__ == "__main__":
    main()

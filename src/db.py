"""DuckDB access layer: schema, inserts, and idempotency helpers.

The .duckdb file is the committed dataset (an append-only time-series). One row
per (scraped_date, repo) after LLM enrichment.
"""
from __future__ import annotations

import datetime as dt
from typing import List, Optional

import duckdb

from . import config

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS tech_signals (
    scraped_date DATE,
    repo_name    VARCHAR,
    stars_today  INTEGER,
    language     VARCHAR,
    category     VARCHAR,
    tools        VARCHAR[],
    maturity     VARCHAR,
    confidence   FLOAT,
    use_case     VARCHAR
);
"""


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the DuckDB file, ensuring the directory and schema exist."""
    config.ensure_dirs()
    con = duckdb.connect(str(config.DUCKDB_PATH), read_only=read_only)
    if not read_only:
        con.execute(SCHEMA_DDL)
    return con


def get_processed_dates(con: duckdb.DuckDBPyConnection) -> set[str]:
    """Return ISO date strings already present in tech_signals."""
    try:
        rows = con.execute(
            "SELECT DISTINCT scraped_date FROM tech_signals"
        ).fetchall()
    except duckdb.CatalogException:
        return set()
    return {r[0].isoformat() for r in rows if r[0] is not None}


def insert_signals(
    con: duckdb.DuckDBPyConnection, rows: List[dict], scraped_date: dt.date
) -> int:
    """Insert enriched rows for a given date. Replaces any existing rows for
    that date first, so re-running extraction is idempotent."""
    con.execute("DELETE FROM tech_signals WHERE scraped_date = ?", [scraped_date])

    if not rows:
        return 0

    con.executemany(
        """
        INSERT INTO tech_signals
            (scraped_date, repo_name, stars_today, language,
             category, tools, maturity, confidence, use_case)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                scraped_date,
                r["repo_name"],
                int(r.get("stars_today", 0) or 0),
                r.get("language"),
                r["category"],
                list(r.get("tools", []) or []),
                r["maturity"],
                float(r.get("confidence", 0.0) or 0.0),
                r.get("use_case", ""),
            )
            for r in rows
        ],
    )
    return len(rows)


def row_count(con: duckdb.DuckDBPyConnection) -> int:
    try:
        return con.execute("SELECT COUNT(*) FROM tech_signals").fetchone()[0]
    except duckdb.CatalogException:
        return 0

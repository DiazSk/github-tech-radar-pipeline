"""Analytics queries over the tech_signals time-series.

The momentum score compares a tool's last-7-day appearance rate against its
last-30-day rate (annualised to a weekly basis): > 1.0 rising, < 1.0 falling.
Uses DuckDB UNNEST on the tools array, so no Pandas wrangling is needed.
"""
from __future__ import annotations

from typing import Optional

import duckdb
import pandas as pd

from . import db

MOMENTUM_SQL = """
WITH exploded AS (
    SELECT
        scraped_date,
        category,
        maturity,
        stars_today,
        tool
    FROM tech_signals, UNNEST(tools) AS t(tool)
    WHERE scraped_date >= CURRENT_DATE - INTERVAL '{window}' DAY
),
agg AS (
    SELECT
        tool,
        category,
        -- dominant maturity tier for this tool (mode)
        MODE(maturity) AS maturity,
        COUNT(*) AS appearances,
        ROUND(AVG(stars_today), 1) AS avg_daily_stars,
        COUNT(*) FILTER (WHERE scraped_date >= CURRENT_DATE - 7)  AS last_7d,
        COUNT(*) FILTER (WHERE scraped_date >= CURRENT_DATE - 30) AS last_30d
    FROM exploded
    GROUP BY tool, category
)
SELECT
    tool,
    category,
    maturity,
    appearances,
    avg_daily_stars,
    last_7d,
    last_30d,
    ROUND(last_7d * 4.3 / NULLIF(last_30d, 0), 2) AS momentum_score
FROM agg
ORDER BY momentum_score DESC NULLS LAST, appearances DESC
"""


def momentum(
    con: Optional[duckdb.DuckDBPyConnection] = None, window: int = 90
) -> pd.DataFrame:
    """Return per-tool momentum over the trailing `window` days."""
    own = con is None
    con = con or db.connect(read_only=True)
    try:
        return con.execute(MOMENTUM_SQL.format(window=int(window))).df()
    finally:
        if own:
            con.close()


def category_momentum(
    con: Optional[duckdb.DuckDBPyConnection] = None, window: int = 90
) -> pd.DataFrame:
    """Aggregate momentum to the category level (mean tool momentum)."""
    df = momentum(con, window)
    if df.empty:
        return df
    return (
        df.groupby(["category", "maturity"], as_index=False)
        .agg(
            momentum_score=("momentum_score", "mean"),
            tools=("tool", "count"),
            appearances=("appearances", "sum"),
        )
        .round({"momentum_score": 2})
    )


def daily_appearances(
    tool: str, con: Optional[duckdb.DuckDBPyConnection] = None, window: int = 90
) -> pd.DataFrame:
    """Per-day appearance count for a single tool (for sparklines)."""
    own = con is None
    con = con or db.connect(read_only=True)
    try:
        return con.execute(
            """
            SELECT scraped_date, COUNT(*) AS appearances
            FROM tech_signals, UNNEST(tools) AS t(tool)
            WHERE tool = ?
              AND scraped_date >= CURRENT_DATE - INTERVAL '{window}' DAY
            GROUP BY scraped_date
            ORDER BY scraped_date
            """.format(window=int(window)),
            [tool],
        ).df()
    finally:
        if own:
            con.close()


def date_bounds(con: Optional[duckdb.DuckDBPyConnection] = None):
    """Return (min_date, max_date) present in the data, or (None, None)."""
    own = con is None
    con = con or db.connect(read_only=True)
    try:
        row = con.execute(
            "SELECT MIN(scraped_date), MAX(scraped_date) FROM tech_signals"
        ).fetchone()
        return row[0], row[1]
    finally:
        if own:
            con.close()

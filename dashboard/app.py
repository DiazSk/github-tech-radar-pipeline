"""GitHub Tech Radar — Streamlit dashboard.

Reads the committed DuckDB dataset and renders:
  Tab 1: Radar chart of category momentum split by maturity tier
  Tab 2: Rising tools bar chart (sorted by momentum score)
  Tab 3: Category drilldown with per-tool time-series sparklines

Run: streamlit run app.py
"""
from __future__ import annotations

import duckdb
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import config, queries
from src.db import SCHEMA_DDL

st.set_page_config(page_title="GitHub Tech Radar", page_icon="📡", layout="wide")

MATURITY_TIERS = ["emerging", "growing", "mainstream", "declining"]


@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection:
    """Cached read-only DuckDB connection. Falls back to in-memory if no file."""
    if not config.DUCKDB_PATH.exists():
        con = duckdb.connect(":memory:")
        con.execute(SCHEMA_DDL)
        return con
    return duckdb.connect(str(config.DUCKDB_PATH), read_only=True)


@st.cache_data(ttl=300)
def load_momentum(window: int):
    return queries.momentum(get_connection(), window=window)


@st.cache_data(ttl=300)
def load_category_momentum(window: int):
    return queries.category_momentum(get_connection(), window=window)


@st.cache_data(ttl=300)
def load_daily(tool: str, window: int):
    return queries.daily_appearances(tool, get_connection(), window=window)


def render_radar(window: int, min_momentum: float) -> None:
    cat_df = load_category_momentum(window)
    if cat_df.empty:
        st.info("No data yet. Run the scraper and extractor to populate the radar.")
        return

    cat_df = cat_df[cat_df["momentum_score"] >= min_momentum]
    if cat_df.empty:
        st.warning("No categories meet the current momentum threshold.")
        return

    categories = sorted(cat_df["category"].unique())
    fig = go.Figure()
    for maturity in MATURITY_TIERS:
        subset = cat_df[cat_df["maturity"] == maturity]
        if subset.empty:
            continue
        lookup = dict(zip(subset["category"], subset["momentum_score"]))
        r = [lookup.get(cat, 0) for cat in categories]
        fig.add_trace(
            go.Scatterpolar(
                r=r + [r[0]],
                theta=categories + [categories[0]],
                fill="toself",
                name=maturity,
            )
        )

    max_r = max(cat_df["momentum_score"].max(), 1.0)
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, round(max_r + 0.5, 1)])),
        title=f"GitHub Tech Radar — Category Momentum (trailing {window} days)",
        legend_title="Maturity",
        height=600,
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Momentum > 1.0 = a category is appearing more often recently (rising); "
        "< 1.0 = cooling off."
    )


def render_rising(window: int, min_momentum: float, top_n: int) -> None:
    df = load_momentum(window)
    if df.empty:
        st.info("No data yet.")
        return

    df = df[df["momentum_score"].notna() & (df["momentum_score"] >= min_momentum)]
    df = df.sort_values("momentum_score", ascending=False).head(top_n)
    if df.empty:
        st.warning("No tools meet the current momentum threshold.")
        return

    fig = px.bar(
        df.sort_values("momentum_score"),
        x="momentum_score",
        y="tool",
        color="category",
        orientation="h",
        hover_data=["appearances", "avg_daily_stars", "maturity"],
        title=f"Top {len(df)} Rising Tools (trailing {window} days)",
    )
    fig.update_layout(height=max(400, 22 * len(df)), yaxis_title="", xaxis_title="Momentum score")
    st.plotly_chart(fig, use_container_width=True)


def render_drilldown(window: int) -> None:
    df = load_momentum(window)
    if df.empty:
        st.info("No data yet.")
        return

    categories = sorted(df["category"].unique())
    category = st.selectbox("Category", categories)
    sub = df[df["category"] == category].sort_values("momentum_score", ascending=False)

    st.dataframe(
        sub[
            [
                "tool",
                "maturity",
                "momentum_score",
                "appearances",
                "last_7d",
                "last_30d",
                "avg_daily_stars",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    tools = sub["tool"].tolist()
    if not tools:
        return
    tool = st.selectbox("Tool time-series", tools)
    daily = load_daily(tool, window)
    if daily.empty:
        st.caption("Not enough history for a time-series yet.")
        return
    line = px.line(
        daily,
        x="scraped_date",
        y="appearances",
        markers=True,
        title=f"Daily appearances — {tool}",
    )
    line.update_layout(height=320, xaxis_title="", yaxis_title="Appearances")
    st.plotly_chart(line, use_container_width=True)


def main() -> None:
    st.title("📡 GitHub Tech Radar")
    st.caption(
        "Daily GitHub trending repos, structured by an LLM into a rolling tech-momentum radar."
    )

    min_date, max_date = queries.date_bounds(get_connection())
    with st.sidebar:
        st.header("Filters")
        window = st.slider("Lookback window (days)", 7, 90, 30, step=1)
        min_momentum = st.slider("Min momentum score", 0.0, 5.0, 0.0, step=0.1)
        top_n = st.slider("Max tools in bar chart", 5, 50, 20, step=5)
        st.divider()
        if min_date and max_date:
            st.metric("Data range", f"{min_date} → {max_date}")
        st.metric("LLM provider", config.LLM_PROVIDER)

    if not config.DUCKDB_PATH.exists() or min_date is None:
        st.warning(
            "No data found yet. Populate it by running:\n\n"
            "```\npython -m src.scraper\npython -m src.extractor\n```"
        )

    tab1, tab2, tab3 = st.tabs(["Radar", "Rising tools", "Category drilldown"])
    with tab1:
        render_radar(window, min_momentum)
    with tab2:
        render_rising(window, min_momentum, top_n)
    with tab3:
        render_drilldown(window)


if __name__ == "__main__":
    main()

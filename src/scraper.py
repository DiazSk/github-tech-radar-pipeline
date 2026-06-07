"""Scrape GitHub trending repos and persist raw metadata.

Primary source: the github.com/trending HTML page (no official API exists).
Fallback: the GitHub Search API sorted by recently-created stars.
For each repo we also fetch the first chunk of its README via the REST API.

Output: data/raw/<YYYY-MM-DD>.json  (a list of RawRepo dicts).

This module does NOT call any LLM, so it runs safely in GitHub Actions.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import re
import time
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from . import config
from .models import RawRepo

USER_AGENT = "tech-radar-pipeline/1.0 (+https://github.com)"


def _headers(accept: str = "application/vnd.github+json") -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": accept}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return headers


def _parse_int(text: Optional[str]) -> int:
    """Turn '1,234' / '1.2k' / '2,345 stars today' into an int."""
    if not text:
        return 0
    text = text.strip().lower().replace(",", "")
    match = re.search(r"([\d.]+)\s*([km]?)", text)
    if not match:
        return 0
    value = float(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        value *= 1_000
    elif suffix == "m":
        value *= 1_000_000
    return int(value)


def fetch_trending_html(limit: int) -> List[RawRepo]:
    """Scrape the trending page. Returns [] on any failure so caller can fall back."""
    try:
        resp = requests.get(
            config.TRENDING_URL, headers=_headers("text/html"), timeout=30
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[scraper] trending HTML fetch failed: {exc}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    repos: List[RawRepo] = []

    for article in soup.select("article.Box-row")[:limit]:
        anchor = article.select_one("h2 a")
        if not anchor:
            continue
        full_name = re.sub(r"\s+", "", anchor.get_text(strip=True))  # "owner / repo"
        href = anchor.get("href", "")
        url = f"https://github.com{href}" if href else None

        desc_el = article.select_one("p")
        description = desc_el.get_text(strip=True) if desc_el else None

        lang_el = article.select_one('[itemprop="programmingLanguage"]')
        language = lang_el.get_text(strip=True) if lang_el else None

        stars_today_el = article.select_one("span.d-inline-block.float-sm-right")
        stars_today = _parse_int(stars_today_el.get_text() if stars_today_el else None)

        star_link = article.select_one('a[href$="/stargazers"]')
        stars_total = _parse_int(star_link.get_text() if star_link else None)

        repos.append(
            RawRepo(
                repo_name=full_name,
                description=description,
                language=language,
                stars_today=stars_today,
                stars_total=stars_total,
                url=url,
            )
        )

    return repos


def fetch_trending_search_api(limit: int) -> List[RawRepo]:
    """Fallback: GitHub Search API for repos created in the last 7 days, by stars."""
    since = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    params = {
        "q": f"created:>{since}",
        "sort": "stars",
        "order": "desc",
        "per_page": str(limit),
    }
    try:
        resp = requests.get(
            config.SEARCH_API_URL, headers=_headers(), params=params, timeout=30
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[scraper] search API fallback failed: {exc}")
        return []

    repos: List[RawRepo] = []
    for item in resp.json().get("items", [])[:limit]:
        repos.append(
            RawRepo(
                repo_name=item.get("full_name", ""),
                description=item.get("description"),
                language=item.get("language"),
                stars_today=0,  # search API has no per-day delta
                stars_total=item.get("stargazers_count", 0),
                topics=item.get("topics", []) or [],
                url=item.get("html_url"),
            )
        )
    return repos


def fetch_readme_snippet(repo_full_name: str, chars: int) -> str:
    """Fetch and decode the first `chars` characters of a repo README."""
    api_url = f"https://api.github.com/repos/{repo_full_name}/readme"
    try:
        resp = requests.get(api_url, headers=_headers(), timeout=30)
        if resp.status_code != 200:
            return ""
        content = resp.json().get("content", "")
        decoded = base64.b64decode(content).decode("utf-8", errors="ignore")
        return decoded[:chars]
    except (requests.RequestException, ValueError) as exc:
        print(f"[scraper] README fetch failed for {repo_full_name}: {exc}")
        return ""


def fetch_topics(repo_full_name: str) -> List[str]:
    """Fetch repository topics (trending HTML does not expose them)."""
    api_url = f"https://api.github.com/repos/{repo_full_name}/topics"
    try:
        resp = requests.get(
            api_url,
            headers=_headers("application/vnd.github.mercy-preview+json"),
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("names", []) or []
    except requests.RequestException:
        return []


def scrape(limit: Optional[int] = None) -> List[RawRepo]:
    """Scrape trending repos and enrich each with topics + README snippet."""
    limit = limit or config.SCRAPE_LIMIT

    repos = fetch_trending_html(limit)
    if not repos:
        print("[scraper] falling back to GitHub Search API")
        repos = fetch_trending_search_api(limit)

    for repo in repos:
        if not repo.topics:
            repo.topics = fetch_topics(repo.repo_name)
        repo.readme_snippet = fetch_readme_snippet(
            repo.repo_name, config.README_SNIPPET_CHARS
        )
        time.sleep(0.3)  # be polite to the API

    return repos


def save_raw(repos: List[RawRepo], date: Optional[dt.date] = None) -> str:
    """Write repos to data/raw/<date>.json and return the path."""
    config.ensure_dirs()
    date = date or dt.date.today()
    out_path = config.RAW_DIR / f"{date.isoformat()}.json"
    payload = [r.model_dump() for r in repos]
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(out_path)


def main() -> None:
    repos = scrape()
    path = save_raw(repos)
    print(f"[scraper] saved {len(repos)} repos -> {path}")


if __name__ == "__main__":
    main()

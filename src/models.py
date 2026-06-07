"""Pydantic v2 schemas.

`TechSignal` is the contract the LLM must fill via `with_structured_output`.
`RawRepo` is the shape the scraper writes to data/raw/<date>.json.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Category = Literal["AI/ML", "Data", "DevOps", "Web", "Security", "Mobile", "Other"]
Maturity = Literal["emerging", "growing", "mainstream", "declining"]


class TechSignal(BaseModel):
    """Structured tech metadata extracted from a single repo."""

    tools: List[str] = Field(
        default_factory=list,
        description="Specific frameworks, libraries, languages, or tools mentioned",
    )
    category: Category = Field(description="Primary domain this repo belongs to")
    maturity: Maturity = Field(
        description="How established the tech is: emerging, growing, mainstream, or declining"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Extraction confidence score between 0 and 1"
    )
    use_case: str = Field(description="One-line summary of what this repo does")


class RawRepo(BaseModel):
    """Raw scraped repo metadata persisted before LLM enrichment."""

    repo_name: str
    description: Optional[str] = None
    language: Optional[str] = None
    stars_today: int = 0
    stars_total: Optional[int] = None
    topics: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    readme_snippet: str = ""

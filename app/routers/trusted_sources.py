# trusted_sources.py

"""Trusted Sources router.

Endpoints:
    GET /trusted-sources          — returns all sources with credibility >= min_credibility
    GET /trusted-sources/suggest  — returns trusted sources relevant to a given verdict
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import ExternalRating

router = APIRouter()

# Category icons for UI display
_CATEGORY_ICONS = {
    "mainstream":  "📰",
    "tabloid":     "🗞️",
    "satire":      "🎭",
    "conspiracy":  "⚠️",
    "state-media": "🏛️",
    "unknown":     "🔍",
}

# Curated category groupings for the Trusted Sources page
_CATEGORY_GROUPS = {
    "News":         ["mainstream"],
    "Fact-Checking": [],           # matched by domain keyword below
    "Science":      [],            # matched by domain keyword below
}

_FACT_CHECK_DOMAINS = {
    "snopes.com", "factcheck.org", "politifact.com", "fullfact.org"
}

_SCIENCE_DOMAINS = {
    "nature.com", "science.org", "scientificamerican.com", "newscientist.com"
}


def _enrich(entry: ExternalRating) -> dict:
    """Convert an ExternalRating row to a frontend-ready dict."""
    if entry.domain in _FACT_CHECK_DOMAINS:
        group = "Fact-Checking"
    elif entry.domain in _SCIENCE_DOMAINS:
        group = "Science"
    elif entry.category == "mainstream":
        group = "News"
    else:
        group = "Other"

    return {
        "domain":      entry.domain,
        "credibility": entry.credibility,
        "category":    entry.category,
        "bias":        entry.bias,
        "notes":       entry.notes,
        "api_source":  entry.api_source,
        "icon":        _CATEGORY_ICONS.get(entry.category, "🔍"),
        "group":       group,
        "url":         f"https://{entry.domain}",
    }


@router.get("/trusted-sources")
def get_trusted_sources(
    min_credibility: int = Query(default=70, ge=0, le=100),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Return all sources with credibility >= min_credibility.
    Optionally filter by category (mainstream, tabloid, etc.).

    Query params:
        min_credibility : int  — minimum credibility score (default 70)
        category        : str  — filter by category (optional)
    """
    query = db.query(ExternalRating).filter(
        ExternalRating.credibility >= min_credibility
    )

    if category:
        query = query.filter(ExternalRating.category == category)

    results = query.order_by(ExternalRating.credibility.desc()).all()

    enriched = [_enrich(r) for r in results]

    # Group by category group
    groups: dict[str, list] = {}
    for item in enriched:
        g = item["group"]
        if g not in groups:
            groups[g] = []
        groups[g].append(item)

    return {
        "total":  len(enriched),
        "groups": groups,
        "items":  enriched,
    }


@router.get("/trusted-sources/suggest")
def suggest_trusted_sources(
    verdict: str = Query(...),
    limit:   int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """
    Suggest trusted sources when a fake/uncertain verdict is detected.
    Only returns suggestions for Fake, Likely Fake, and Uncertain verdicts.

    Query params:
        verdict : str — the verdict from the analysis
        limit   : int — number of suggestions to return (default 3)
    """
    SUGGEST_FOR = {"Fake", "Likely Fake", "Uncertain"}

    if verdict not in SUGGEST_FOR:
        return {"suggest": False, "sources": []}

    # Return top mainstream + fact-checking sources
    results = (
        db.query(ExternalRating)
        .filter(
            ExternalRating.credibility >= 80,
            ExternalRating.category == "mainstream",
        )
        .order_by(ExternalRating.credibility.desc())
        .limit(limit)
        .all()
    )

    # Always include at least one fact-checker if available
    fact_checkers = (
        db.query(ExternalRating)
        .filter(ExternalRating.domain.in_(list(_FACT_CHECK_DOMAINS)))
        .order_by(ExternalRating.credibility.desc())
        .limit(1)
        .all()
    )

    combined = {r.domain: r for r in results}
    for fc in fact_checkers:
        combined[fc.domain] = fc

    suggestions = [_enrich(r) for r in list(combined.values())[:limit + 1]]

    return {
        "suggest": True,
        "verdict": verdict,
        "message": "This claim may be unreliable. Consider checking these trusted sources:",
        "sources": suggestions,
    }
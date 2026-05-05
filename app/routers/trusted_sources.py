# trusted_sources.py

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import ExternalRating

router = APIRouter()

_CATEGORY_ICONS = {
    "mainstream":  "📰",
    "tabloid":     "🗞️",
    "satire":      "🎭",
    "conspiracy":  "⚠️",
    "state-media": "🏛️",
    "unknown":     "🔍",
}

_CATEGORY_GROUPS = {
    "News":         ["mainstream"],
    "Fact-Checking": [],           
    "Science":      [],            
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
   
    query = db.query(ExternalRating).filter(
        ExternalRating.credibility >= min_credibility
    )

    if category:
        query = query.filter(ExternalRating.category == category)

    results = query.order_by(ExternalRating.credibility.desc()).all()

    enriched = [_enrich(r) for r in results]

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
   
    SUGGEST_FOR = {"Fake", "Likely Fake", "Uncertain"}

    if verdict not in SUGGEST_FOR:
        return {"suggest": False, "sources": []}

    mainstream = (
        db.query(ExternalRating)
        .filter(
            ExternalRating.credibility >= 80,
            ExternalRating.category == "mainstream",
        )
        .order_by(ExternalRating.credibility.desc())
        .limit(limit)
        .all()
    )

    fact_checkers = (
        db.query(ExternalRating)
        .filter(ExternalRating.domain.in_(list(_FACT_CHECK_DOMAINS)))
        .order_by(ExternalRating.credibility.desc())
        .limit(1)
        .all()
    )

    science_sources = (
        db.query(ExternalRating)
        .filter(ExternalRating.domain.in_(list(_SCIENCE_DOMAINS)))
        .order_by(ExternalRating.credibility.desc())
        .limit(1)
        .all()
    )

    combined: dict[str, ExternalRating] = {r.domain: r for r in mainstream}
    for r in fact_checkers:
        combined[r.domain] = combined.get(r.domain) or r
    for r in science_sources:
        combined[r.domain] = combined.get(r.domain) or r

    suggestions = [_enrich(r) for r in list(combined.values())[: limit + 1]]

    return {
        "suggest": True,
        "verdict": verdict,
        "message": "This claim may be unreliable. Consider checking these trusted sources:",
        "sources": suggestions,
    }
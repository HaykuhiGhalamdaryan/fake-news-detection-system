# external_sync.py

from __future__ import annotations

import logging
from datetime import datetime
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.database.models import ExternalRating

logger = logging.getLogger(__name__)


_MOCK_API_DATA: dict[str, dict] = {
    # Wire services
    "reuters.com":           {"credibility": 95, "category": "mainstream",   "bias": "center",      "notes": "Reuters — international wire service, strict factual reporting",        "source": "MBFC"},
    "apnews.com":            {"credibility": 95, "category": "mainstream",   "bias": "center",      "notes": "Associated Press — international wire service",                          "source": "MBFC"},
    # Mainstream international
    "bbc.com":               {"credibility": 92, "category": "mainstream",   "bias": "center",      "notes": "BBC — UK public broadcaster, strong editorial standards",                "source": "MBFC"},
    "bbc.co.uk":             {"credibility": 92, "category": "mainstream",   "bias": "center",      "notes": "BBC — UK public broadcaster",                                            "source": "MBFC"},
    "theguardian.com":       {"credibility": 85, "category": "mainstream",   "bias": "center-left", "notes": "The Guardian — UK newspaper, strong editorial standards",                "source": "MBFC"},
    "economist.com":         {"credibility": 88, "category": "mainstream",   "bias": "center",      "notes": "The Economist — UK weekly, rigorous fact-checking",                      "source": "MBFC"},
    "bloomberg.com":         {"credibility": 87, "category": "mainstream",   "bias": "center",      "notes": "Bloomberg — major financial/business news",                              "source": "MBFC"},
    # Mainstream US
    "nytimes.com":           {"credibility": 85, "category": "mainstream",   "bias": "center-left", "notes": "New York Times — major US newspaper",                                    "source": "MBFC"},
    "washingtonpost.com":    {"credibility": 83, "category": "mainstream",   "bias": "center-left", "notes": "Washington Post — major US newspaper",                                   "source": "MBFC"},
    "npr.org":               {"credibility": 88, "category": "mainstream",   "bias": "center-left", "notes": "NPR — US public radio, rigorous editorial standards",                    "source": "MBFC"},
    "foxnews.com":           {"credibility": 60, "category": "mainstream",   "bias": "right",       "notes": "Fox News — major US cable news, strong editorial slant",                 "source": "MBFC"},
    # Fact-checkers
    "snopes.com":            {"credibility": 85, "category": "mainstream",   "bias": "center",      "notes": "Snopes — established fact-checking website",                             "source": "MBFC"},
    "factcheck.org":         {"credibility": 88, "category": "mainstream",   "bias": "center",      "notes": "FactCheck.org — non-partisan fact-checking",                             "source": "MBFC"},
    "politifact.com":        {"credibility": 82, "category": "mainstream",   "bias": "center-left", "notes": "PolitiFact — Pulitzer Prize-winning fact-checker",                       "source": "MBFC"},
    "fullfact.org":          {"credibility": 85, "category": "mainstream",   "bias": "center",      "notes": "Full Fact — UK independent fact-checking charity",                       "source": "MBFC"},
    # Science
    "nature.com":            {"credibility": 97, "category": "mainstream",   "bias": "center",      "notes": "Nature — peer-reviewed scientific journal",                              "source": "MBFC"},
    "science.org":           {"credibility": 97, "category": "mainstream",   "bias": "center",      "notes": "Science — peer-reviewed journal, AAAS",                                  "source": "MBFC"},
    "scientificamerican.com":{"credibility": 90, "category": "mainstream",   "bias": "center",      "notes": "Scientific American — established science magazine",                     "source": "MBFC"},
    "newscientist.com":      {"credibility": 88, "category": "mainstream",   "bias": "center",      "notes": "New Scientist — science and technology magazine",                        "source": "MBFC"},
    # Tabloids
    "dailymail.co.uk":       {"credibility": 40, "category": "tabloid",      "bias": "right",       "notes": "Daily Mail — UK tabloid, frequent sensationalism",                      "source": "MBFC"},
    "nypost.com":            {"credibility": 50, "category": "tabloid",      "bias": "right",       "notes": "New York Post — US tabloid, editorial slant",                            "source": "MBFC"},
    # Conspiracy / misinformation
    "infowars.com":          {"credibility": 2,  "category": "conspiracy",   "bias": "right",       "notes": "InfoWars — known misinformation and conspiracy theories",                "source": "MBFC"},
    "breitbart.com":         {"credibility": 20, "category": "conspiracy",   "bias": "right",       "notes": "Breitbart — far-right, frequent misinformation",                        "source": "MBFC"},
    # State media
    "rt.com":                {"credibility": 20, "category": "state-media",  "bias": "unknown",     "notes": "RT — Russian state media, known propaganda",                             "source": "MBFC"},
    "tass.com":              {"credibility": 15, "category": "state-media",  "bias": "unknown",     "notes": "TASS — Russian state news agency",                                       "source": "MBFC"},
    # Satire
    "theonion.com":          {"credibility": 10, "category": "satire",       "bias": "center",      "notes": "The Onion — well-known satire website, not real news",                   "source": "MBFC"},
    "babylonbee.com":        {"credibility": 10, "category": "satire",       "bias": "right",       "notes": "Babylon Bee — satirical website, not real news",                         "source": "MBFC"},
}


def _fetch_from_mock_api() -> dict[str, dict]:
    logger.info("Fetching data from mock external API (%d entries)", len(_MOCK_API_DATA))
    return _MOCK_API_DATA


def run_sync(db: Session) -> dict:
    """
    Fetch external ratings and upsert them into the ExternalRating table.

    Returns a summary dict with counts of inserted/updated/unchanged entries.
    """
    logger.info("Starting external sync — %s", datetime.utcnow().isoformat())

    api_data = _fetch_from_mock_api()

    inserted  = 0
    updated   = 0
    unchanged = 0

    for domain, rating in api_data.items():
        existing = db.query(ExternalRating).filter(
            ExternalRating.domain == domain
        ).first()

        if existing is None:
            db.add(ExternalRating(
                domain      = domain,
                credibility = rating["credibility"],
                category    = rating["category"],
                bias        = rating["bias"],
                notes       = rating["notes"],
                api_source  = rating["source"],
                fetched_at  = datetime.utcnow(),
            ))
            inserted += 1
            logger.debug("Inserted: %s (credibility=%d)", domain, rating["credibility"])

        elif existing.credibility != rating["credibility"]:
            old_score = existing.credibility
            existing.credibility = rating["credibility"]
            existing.category    = rating["category"]
            existing.bias        = rating["bias"]
            existing.notes       = rating["notes"]
            existing.fetched_at  = datetime.utcnow()
            updated += 1
            logger.debug(
                "Updated: %s (credibility %d -> %d)",
                domain, old_score, rating["credibility"]
            )

        else:
            unchanged += 1

    db.commit()

    summary = {
        "synced_at": datetime.utcnow().isoformat(),
        "total":     len(api_data),
        "inserted":  inserted,
        "updated":   updated,
        "unchanged": unchanged,
    }

    logger.info("Sync complete — inserted=%d, updated=%d, unchanged=%d",
                inserted, updated, unchanged)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        result = run_sync(db)
        print(result)
    finally:
        db.close()
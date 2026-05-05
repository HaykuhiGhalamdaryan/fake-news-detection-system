# citation_graph.py

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.database.models import AnalysisResult, DomainCache, CitationLog

logger = logging.getLogger(__name__)

TRUST_THRESHOLD   = 0.35   
BASE_BOOST        = 3      
MAX_BOOST_PER_RUN = 8      
SCORE_MIN         = 0
SCORE_MAX         = 100

_URL_RE = re.compile(
    r"https?://(?:www\.)?([a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)+)"
    r"(?:/[^\s\"\')>]*)?"
)


# URL extraction
def _extract_cited_domains(text: str, source_domain: str | None = None) -> list[str]:
    domains = set()
    for match in _URL_RE.finditer(text):
        domain = match.group(1).lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain != source_domain and len(domain) > 4:
            domains.add(domain)
    return list(domains)


def _get_source_domain(article) -> str | None:
    if article.source_domain:
        return article.source_domain
    try:
        urls = _URL_RE.findall(article.text)
        if urls:
            return urls[0].lower()
    except Exception:
        pass
    return None


def _clamp(value: int) -> int:
    return max(SCORE_MIN, min(SCORE_MAX, value))


def _build_citation_scores(db: Session) -> dict[str, float]:
    trusted_articles = db.query(AnalysisResult).filter(
        AnalysisResult.fake_probability <= TRUST_THRESHOLD
    ).all()

    logger.info(
        "Found %d trusted articles (fake_probability <= %.0f%%)",
        len(trusted_articles), TRUST_THRESHOLD * 100
    )

    citation_scores: dict[str, float] = defaultdict(float)

    for article in trusted_articles:
        source_domain = _get_source_domain(article)
        cited_domains = _extract_cited_domains(article.text, source_domain)

        article_weight = 1.0 - article.fake_probability

        for domain in cited_domains:
            boost = BASE_BOOST * article_weight
            citation_scores[domain] += boost
            logger.debug(
                "Citation: %s cited by trusted article (weight=%.2f, boost=+%.2f)",
                domain, article_weight, boost
            )

    return dict(citation_scores)


def run_citation_graph(db: Session) -> dict:
    logger.info("Starting citation graph — %s", datetime.utcnow().isoformat())

    citation_scores = _build_citation_scores(db)
    boosts_applied  = []
    skipped         = []

    for domain, raw_boost in citation_scores.items():
        boost = int(min(round(raw_boost), MAX_BOOST_PER_RUN))

        if boost <= 0:
            skipped.append({"domain": domain, "reason": "Boost rounded to 0"})
            continue

        cached = db.query(DomainCache).filter(DomainCache.domain == domain).first()
        if cached is None:
            skipped.append({
                "domain": domain,
                "reason": "Not in DomainCache — run WHOIS analysis first",
            })
            continue

        old_score = cached.credibility
        cached.credibility = _clamp(old_score + boost)
        new_score = cached.credibility

        reason = (
            f"Citation boost from {len([d for d in citation_scores if d == domain])} "
            f"trusted article(s) — raw boost {raw_boost:.1f}, capped at {boost}"
        )

        logger.info(
            "%s: credibility %d → %d (+%d) | %s",
            domain, old_score, new_score, boost, reason
        )

        # Log citation event
        db.add(CitationLog(
            domain     = domain,
            raw_boost  = raw_boost,
            boost      = boost,
            old_score  = old_score,
            new_score  = new_score,
            reason     = reason,
            run_at     = datetime.utcnow(),
        ))

        boosts_applied.append({
            "domain":    domain,
            "raw_boost": round(raw_boost, 2),
            "boost":     boost,
            "old_score": old_score,
            "new_score": new_score,
        })

    db.commit()

    summary = {
        "run_at":         datetime.utcnow().isoformat(),
        "domains_cited":  len(citation_scores),
        "boosts_applied": boosts_applied,
        "skipped":        skipped,
    }

    logger.info(
        "Citation graph complete — %d boosts applied, %d skipped",
        len(boosts_applied), len(skipped)
    )
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        result = run_citation_graph(db)
        for b in result["boosts_applied"]:
            print(f"{b['domain']:30s} boost=+{b['boost']}  "
                  f"score: {b['old_score']} → {b['new_score']}")
        if result["skipped"]:
            print(f"\nSkipped {len(result['skipped'])} domains:")
            for s in result["skipped"]:
                print(f"  {s['domain']:30s} — {s['reason']}")
    finally:
        db.close()
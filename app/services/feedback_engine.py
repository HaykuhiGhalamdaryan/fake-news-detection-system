# feedback_engine.py

"""Feedback Engine — Module 2.

Periodically scans AnalysisResult records and adjusts DomainCache credibility
scores based on the fake_probability of articles from each domain.

Logic
-----
For each domain that has been analyzed at least MIN_ARTICLES times:

    domain_fake_rate = average fake_probability across all articles from domain

    if domain_fake_rate >= HIGH_FAKE_THRESHOLD  → strong penalty  (-PENALTY_HIGH)
    if domain_fake_rate >= MED_FAKE_THRESHOLD   → mild penalty    (-PENALTY_MED)
    if domain_fake_rate <= LOW_FAKE_THRESHOLD   → reward          (+REWARD)

The adjustment is applied to DomainCache.credibility (unknown domains only).
Domains in the static _SOURCE_DB are not modified — they are managed by
external_sync.py which has authoritative data.

Anomaly detection
-----------------
If a domain's article count spikes by more than ANOMALY_SPIKE_FACTOR in one
run, it is flagged as suspicious and skipped (possible manipulation attempt).

Usage
-----
    # Run once manually
    python -m app.services.feedback_engine

    # Or call from scheduler
    from app.services.feedback_engine import run_feedback
    run_feedback(db)
"""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.database.models import AnalysisResult, DomainCache, FeedbackLog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

MIN_ARTICLES         = 3     # minimum articles before adjusting score
HIGH_FAKE_THRESHOLD  = 0.70  # domain fake rate above this → strong penalty
MED_FAKE_THRESHOLD   = 0.50  # domain fake rate above this → mild penalty
LOW_FAKE_THRESHOLD   = 0.25  # domain fake rate below this → reward

PENALTY_HIGH         = 15    # points deducted for high fake rate
PENALTY_MED          = 7     # points deducted for medium fake rate
REWARD               = 5     # points added for low fake rate

ANOMALY_SPIKE_FACTOR = 3.0   # flag domain if article count tripled since last run
SCORE_MIN            = 0
SCORE_MAX            = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_domain_from_text(text: str) -> str | None:
    """
    AnalysisResult stores raw text, not the source URL.
    We check if the text starts with a URL (url_extractor prepends the title
    but the domain is stored in DomainCache separately).

    This function is a best-effort extraction — returns None if not found.
    In a future version, AnalysisResult should store the source_domain field.
    """
    try:
        if text.startswith("http"):
            parsed = urlparse(text.split()[0])
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain or None
    except Exception:
        pass
    return None


def _clamp(value: int) -> int:
    return max(SCORE_MIN, min(SCORE_MAX, value))


# ---------------------------------------------------------------------------
# Core feedback logic
# ---------------------------------------------------------------------------

def _compute_domain_stats(db: Session) -> dict[str, dict]:
    """
    Query AnalysisResult and group by domain.
    Returns {domain: {count, avg_fake_probability}}.

    Note: This works with the current schema where source domain is not
    stored directly. We use DomainCache domains as the reference list and
    join on article text prefix matching.

    In production, add a `source_domain` column to AnalysisResult for
    accurate per-domain aggregation.
    """
    # Get all cached domains that have had articles analyzed
    cached_domains = db.query(DomainCache.domain).all()
    cached_domains = [row.domain for row in cached_domains]

    stats = {}
    for domain in cached_domains:
        # Match articles whose text contains the domain (URL was prepended)
        results = db.query(AnalysisResult).filter(
            AnalysisResult.text.contains(domain)
        ).all()

        if len(results) >= MIN_ARTICLES:
            avg_fake = sum(r.fake_probability for r in results) / len(results)
            stats[domain] = {
                "count":            len(results),
                "avg_fake_probability": round(avg_fake, 4),
            }

    return stats


def run_feedback(db: Session) -> dict:
    """
    Scan analysis history and adjust DomainCache credibility scores.

    Returns a summary of all adjustments made.
    """
    logger.info("Starting feedback engine — %s", datetime.utcnow().isoformat())

    domain_stats = _compute_domain_stats(db)
    adjustments  = []
    skipped      = []

    for domain, stats in domain_stats.items():
        count    = stats["count"]
        fake_rate = stats["avg_fake_probability"]

        # Anomaly detection — check previous log
        last_log = (
            db.query(FeedbackLog)
            .filter(FeedbackLog.domain == domain)
            .order_by(FeedbackLog.run_at.desc())
            .first()
        )

        if last_log and last_log.article_count > 0:
            spike = count / last_log.article_count
            if spike >= ANOMALY_SPIKE_FACTOR:
                logger.warning(
                    "Anomaly detected for %s: article count spiked %.1fx "
                    "(prev=%d, now=%d) — skipping",
                    domain, spike, last_log.article_count, count
                )
                skipped.append({
                    "domain": domain,
                    "reason": f"Anomaly: count spiked {spike:.1f}x",
                })
                continue

        # Determine adjustment
        if fake_rate >= HIGH_FAKE_THRESHOLD:
            delta  = -PENALTY_HIGH
            reason = f"High fake rate ({fake_rate:.0%}) — strong penalty"
        elif fake_rate >= MED_FAKE_THRESHOLD:
            delta  = -PENALTY_MED
            reason = f"Medium fake rate ({fake_rate:.0%}) — mild penalty"
        elif fake_rate <= LOW_FAKE_THRESHOLD:
            delta  = +REWARD
            reason = f"Low fake rate ({fake_rate:.0%}) — credibility reward"
        else:
            # Neutral zone — no adjustment
            delta  = 0
            reason = f"Neutral fake rate ({fake_rate:.0%}) — no change"

        # Apply adjustment to DomainCache
        cached = db.query(DomainCache).filter(DomainCache.domain == domain).first()
        if cached and delta != 0:
            old_score    = cached.credibility
            cached.credibility = _clamp(old_score + delta)
            new_score    = cached.credibility
            logger.info(
                "%s: credibility %d → %d (%+d) | %s",
                domain, old_score, new_score, delta, reason
            )
        else:
            old_score = cached.credibility if cached else None
            new_score = old_score

        # Log this run
        db.add(FeedbackLog(
            domain        = domain,
            article_count = count,
            avg_fake_rate = fake_rate,
            score_delta   = delta,
            reason        = reason,
            run_at        = datetime.utcnow(),
        ))

        adjustments.append({
            "domain":     domain,
            "articles":   count,
            "fake_rate":  fake_rate,
            "delta":      delta,
            "old_score":  old_score,
            "new_score":  new_score,
            "reason":     reason,
        })

    db.commit()

    summary = {
        "run_at":      datetime.utcnow().isoformat(),
        "domains_processed": len(domain_stats),
        "adjustments": adjustments,
        "skipped":     skipped,
    }

    logger.info(
        "Feedback engine complete — %d domains processed, %d skipped",
        len(domain_stats), len(skipped)
    )
    return summary


# ---------------------------------------------------------------------------
# Run manually
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        result = run_feedback(db)
        for adj in result["adjustments"]:
            print(f"{adj['domain']:30s} fake_rate={adj['fake_rate']:.0%}  "
                  f"delta={adj['delta']:+d}  "
                  f"score: {adj['old_score']} → {adj['new_score']}")
    finally:
        db.close()
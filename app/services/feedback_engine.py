# feedback_engine.py

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.db import SessionLocal
from app.database.models import AnalysisResult, DomainCache, FeedbackLog

logger = logging.getLogger(__name__)


MIN_ARTICLES         = 3     
HIGH_FAKE_THRESHOLD  = 0.70  
MED_FAKE_THRESHOLD   = 0.50  
LOW_FAKE_THRESHOLD   = 0.25
  
PENALTY_HIGH         = 15    
PENALTY_MED          = 7     
REWARD               = 5     

ANOMALY_SPIKE_FACTOR = 3.0   
SCORE_MIN            = 0
SCORE_MAX            = 100


def _extract_domain_from_text(text: str) -> str | None:
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


def _compute_domain_stats(db: Session) -> dict[str, dict]:
    from sqlalchemy import func as sqlfunc

    rows = (
        db.query(
            AnalysisResult.source_domain,
            sqlfunc.count(AnalysisResult.id).label("count"),
            sqlfunc.avg(AnalysisResult.fake_probability).label("avg_fake"),
        )
        .filter(AnalysisResult.source_domain.isnot(None))
        .group_by(AnalysisResult.source_domain)
        .having(sqlfunc.count(AnalysisResult.id) >= MIN_ARTICLES)
        .all()
    )

    return {
        row.source_domain: {
            "count":                row.count,
            "avg_fake_probability": round(float(row.avg_fake), 4),
        }
        for row in rows
    }


def run_feedback(db: Session) -> dict:
    logger.info("Starting feedback engine — %s", datetime.utcnow().isoformat())

    domain_stats = _compute_domain_stats(db)
    adjustments  = []
    skipped      = []

    for domain, stats in domain_stats.items():
        count    = stats["count"]
        fake_rate = stats["avg_fake_probability"]

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
            delta  = 0
            reason = f"Neutral fake rate ({fake_rate:.0%}) — no change"

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
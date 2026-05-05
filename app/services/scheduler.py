# scheduler.py

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.database.db import SessionLocal
from app.services.external_sync import run_sync
from app.services.feedback_engine import run_feedback
from app.services.citation_graph import run_citation_graph

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _job_external_sync():
    logger.info("[Scheduler] Running external_sync")
    db = SessionLocal()
    try:
        result = run_sync(db)
        logger.info("[Scheduler] external_sync done: %s", result)
    except Exception as e:
        logger.error("[Scheduler] external_sync failed: %s", e)
    finally:
        db.close()


def _job_feedback_engine():
    logger.info("[Scheduler] Running feedback_engine")
    db = SessionLocal()
    try:
        result = run_feedback(db)
        logger.info(
            "[Scheduler] feedback_engine done — %d adjustments",
            len(result.get("adjustments", []))
        )
    except Exception as e:
        logger.error("[Scheduler] feedback_engine failed: %s", e)
    finally:
        db.close()


def _job_citation_graph():
    logger.info("[Scheduler] Running citation_graph")
    db = SessionLocal()
    try:
        result = run_citation_graph(db)
        logger.info(
            "[Scheduler] citation_graph done — %d boosts applied",
            len(result.get("boosts_applied", []))
        )
    except Exception as e:
        logger.error("[Scheduler] citation_graph failed: %s", e)
    finally:
        db.close()


def start_scheduler():
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler already running — skipping start")
        return

    _scheduler = BackgroundScheduler()

    _scheduler.add_job(
        _job_external_sync,
        trigger="interval",
        hours=24,
        id="external_sync",
        next_run_time=datetime.now(),  
    )

    _scheduler.add_job(
        _job_feedback_engine,
        trigger="interval",
        hours=6,
        id="feedback_engine",
    )

    _scheduler.add_job(
        _job_citation_graph,
        trigger="interval",
        hours=12,
        id="citation_graph",
    )

    _scheduler.start()
    logger.info(
        "Credibility scheduler started — "
        "external_sync: 24h, feedback_engine: 6h, citation_graph: 12h"
    )


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Credibility scheduler stopped")


if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.INFO)

    print("Running all three modules once (standalone test)...\n")

    db = SessionLocal()
    try:
        print("=== Module 1: external_sync ===")
        r1 = run_sync(db)
        print(f"  inserted={r1['inserted']}, updated={r1['updated']}, unchanged={r1['unchanged']}\n")

        print("=== Module 2: feedback_engine ===")
        r2 = run_feedback(db)
        for adj in r2["adjustments"]:
            print(f"  {adj['domain']:30s} delta={adj['delta']:+d}  {adj['reason']}")
        print()

        print("=== Module 3: citation_graph ===")
        r3 = run_citation_graph(db)
        for b in r3["boosts_applied"]:
            print(f"  {b['domain']:30s} boost=+{b['boost']}  {b['old_score']} → {b['new_score']}")
        if not r3["boosts_applied"]:
            print("  No boosts applied (no trusted articles with citations yet)")
    finally:
        db.close()
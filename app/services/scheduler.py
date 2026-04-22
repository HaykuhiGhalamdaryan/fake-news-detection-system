# scheduler.py

"""Credibility pipeline scheduler.

Runs all three credibility modules on a fixed schedule using APScheduler.
Add this to main.py startup to enable automatic credibility updates.

Schedule (configurable below):
    Module 1 — external_sync   : every 24 hours  (external API is rate-limited)
    Module 2 — feedback_engine : every  6 hours  (reacts to new article analyses)
    Module 3 — citation_graph  : every 12 hours  (citation graph is slower to change)

Usage
-----
    # In main.py, add:
    from app.services.scheduler import start_scheduler
    start_scheduler()

    # Or run standalone for testing:
    python -m app.services.scheduler
"""

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


# ---------------------------------------------------------------------------
# Job wrappers — each opens its own DB session
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def start_scheduler():
    """
    Start the background scheduler. Call once at application startup.

    Add to main.py:
        from app.services.scheduler import start_scheduler

        @app.on_event("startup")
        def startup_event():
            start_scheduler()
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler already running — skipping start")
        return

    _scheduler = BackgroundScheduler()

    # Module 1 — sync external ratings every 24 hours
    _scheduler.add_job(
        _job_external_sync,
        trigger="interval",
        hours=24,
        id="external_sync",
        next_run_time=datetime.now(),  # run immediately on startup
    )

    # Module 2 — feedback engine every 6 hours
    _scheduler.add_job(
        _job_feedback_engine,
        trigger="interval",
        hours=6,
        id="feedback_engine",
    )

    # Module 3 — citation graph every 12 hours
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
    """Gracefully stop the scheduler. Call at application shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Credibility scheduler stopped")


# ---------------------------------------------------------------------------
# Run standalone for testing
# ---------------------------------------------------------------------------

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
#analytics.py

from fastapi import APIRouter, Depends
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from app.database.db import get_db
from app.database.models import AnalysisResult

router = APIRouter()

_analytics_cache: dict = {}
_cache_ttl_seconds = 60


@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):
    global _analytics_cache

    cached_at = _analytics_cache.get("cached_at")
    if cached_at and (datetime.utcnow() - cached_at).total_seconds() < _cache_ttl_seconds:
        return _analytics_cache["data"]

    today = datetime.utcnow().date()

    row = db.query(
        func.count(AnalysisResult.id).label("total"),
        func.sum(
            case((AnalysisResult.verdict == "Fake", 1), else_=0)
        ).label("fake_count"),
        func.sum(
            case((AnalysisResult.verdict.in_(["True", "Likely True"]), 1), else_=0)
        ).label("real_count"),
        func.sum(
            case((AnalysisResult.risk_level == "HIGH", 1), else_=0)
        ).label("high_risk"),
        func.sum(
            case((AnalysisResult.risk_level == "MEDIUM", 1), else_=0)
        ).label("medium_risk"),
        func.sum(
            case((AnalysisResult.risk_level == "LOW", 1), else_=0)
        ).label("low_risk"),
        func.avg(AnalysisResult.credibility_score).label("avg_credibility"),
        func.avg(AnalysisResult.fake_probability).label("avg_fake_probability"),
        func.avg(AnalysisResult.risk_score).label("avg_risk"),
        func.sum(
            case((func.date(AnalysisResult.created_at) == today, 1), else_=0)
        ).label("today_count"),
    ).one()

    data = {
        "total_analyses":          row.total or 0,
        "fake_count":              row.fake_count or 0,
        "real_count":              row.real_count or 0,
        "high_risk":               row.high_risk or 0,
        "medium_risk":             row.medium_risk or 0,
        "low_risk":                row.low_risk or 0,
        "average_credibility":     round(float(row.avg_credibility or 0), 2),
        "average_fake_probability": round(float(row.avg_fake_probability or 0), 2),
        "average_risk_score":      round(float(row.avg_risk or 0), 2),
        "analyses_today":          row.today_count or 0,
    }

    _analytics_cache = {"cached_at": datetime.utcnow(), "data": data}
    return data
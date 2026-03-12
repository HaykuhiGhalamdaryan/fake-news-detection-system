#analytics.py

from fastapi import APIRouter, Depends
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.db import get_db
from app.database.models import AnalysisResult

router = APIRouter()

@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)):

    total_analyses = db.query(func.count(AnalysisResult.id)).scalar()

    fake_count = db.query(func.count(AnalysisResult.id))\
        .filter(AnalysisResult.verdict == "Fake")\
        .scalar()

    real_count = db.query(func.count(AnalysisResult.id))\
        .filter(AnalysisResult.verdict.in_(["True", "Likely True"]))\
        .scalar()

    high_risk = db.query(func.count(AnalysisResult.id))\
        .filter(AnalysisResult.risk_level == "HIGH")\
        .scalar()

    medium_risk = db.query(func.count(AnalysisResult.id))\
        .filter(AnalysisResult.risk_level == "MEDIUM")\
        .scalar()

    low_risk = db.query(func.count(AnalysisResult.id))\
        .filter(AnalysisResult.risk_level == "LOW")\
        .scalar()

    avg_credibility = db.query(func.avg(AnalysisResult.credibility_score)).scalar()
    avg_fake_probability = db.query(
        func.avg(AnalysisResult.fake_probability)
    ).scalar()
    avg_risk = db.query(
        func.avg(AnalysisResult.risk_score)
    ).scalar()

    today = datetime.utcnow().date()
    today_count = db.query(func.count(AnalysisResult.id)).filter(
        func.date(AnalysisResult.created_at) == today
    ).scalar()

    return {
        "total_analyses": total_analyses,
        "fake_count": fake_count,
        "real_count": real_count,
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "low_risk": low_risk,
        "average_credibility": round(avg_credibility or 0, 2),
        "average_fake_probability": round(avg_fake_probability or 0, 2),
        "average_risk_score": round(avg_risk or 0, 2),
        "analyses_today": today_count,
    }

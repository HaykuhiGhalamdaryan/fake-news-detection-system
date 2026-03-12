#history.py

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.database.models import AnalysisResult

router = APIRouter()

@router.get("/history")
def get_history(
    verdict: str | None = None,
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
):

    query = db.query(AnalysisResult)

    if verdict:
        query = query.filter(AnalysisResult.verdict == verdict)
        
    results = query\
        .order_by(AnalysisResult.created_at.desc())\
        .offset(skip)\
        .limit(limit)\
        .all()

    return results

@router.delete("/history/{analysis_id}")
def delete_analysis(
    analysis_id: int,
    db: Session = Depends(get_db)
):
    analysis = db.query(AnalysisResult).filter(
        AnalysisResult.id == analysis_id
    ).first()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    db.delete(analysis)
    db.commit()

    return {"message": "Analysis deleted successfully"}
#models.py

from sqlalchemy import Column, Integer, String, Float, Text, DateTime
from datetime import datetime
from app.database.db import Base

class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    verdict = Column(String, nullable=False)
    confidence = Column(Integer, nullable=False)
    credibility_score = Column(Integer, nullable=False)
    sentiment = Column(String, nullable=False)
    fake_probability = Column(Float, nullable=False)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

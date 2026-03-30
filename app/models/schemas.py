# schemas.py

from pydantic import BaseModel
from typing import List, Optional


class AnalyzeRequest(BaseModel):
    text: str


class AnalyzeURLRequest(BaseModel):
    url: str


class AnalysisDetails(BaseModel):
    sentiment: str
    fake_probability: float
    primary_score: Optional[float]
    secondary_score: Optional[float]
    tiebreaker_score: Optional[float]   # None if tiebreaker model unavailable
    model_spread: Optional[float]       # |primary - secondary| — how much models disagreed
    high_disagreement: bool             # True if spread > 0.35
    negation_detected: bool             # True if negation correction was applied


class Explanation(BaseModel):
    primary_reason: str
    supporting_reasons: List[str]


class LLMAnalysis(BaseModel):
    reasoning: str
    detected_patterns: List[str]
    tone: str


class FactCheck(BaseModel):
    sources: List[str]
    support_score: float
    evidence: List[str]


class AnalyzeResponse(BaseModel):
    verdict: str
    confidence: int
    model_confidence: str
    credibility_score: int
    risk_score: int
    risk_level: str
    analysis: AnalysisDetails
    llm_analysis: LLMAnalysis
    fact_check: FactCheck
    signals: List[str]
    explanation: Explanation
    article_warning: Optional[str] = None 
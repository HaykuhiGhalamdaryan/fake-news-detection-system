# schemas.py

from pydantic import BaseModel
from typing import List, Optional


class AnalyzeRequest(BaseModel):
    text: str
    source_url: Optional[str] = None


class AnalyzeURLRequest(BaseModel):
    url: str


class AnalysisDetails(BaseModel):
    sentiment: str
    fake_probability: float
    primary_score: Optional[float]
    secondary_score: Optional[float]
    tiebreaker_score: Optional[float]
    model_spread: Optional[float]
    high_disagreement: bool
    negation_detected: bool


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


class SourceAnalysis(BaseModel):
    """Credibility analysis of the news source."""
    domain: str
    known_source: bool
    credibility: int
    category: str
    bias: str
    domain_age_days: int
    notes: str
    warning: str


class SourceOnlyResponse(BaseModel):
    """
    Returned when a news source homepage is submitted (not a specific article).
    Contains only source analysis — no NLP pipeline is run.
    """
    mode: str = "source_only"      # always "source_only" — frontend uses this to detect
    source_analysis: SourceAnalysis


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
    source_analysis: Optional[SourceAnalysis] = None
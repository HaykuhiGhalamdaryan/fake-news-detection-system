#schemas.py

from pydantic import BaseModel
from typing import List


class AnalyzeRequest(BaseModel):
    text: str

class AnalysisDetails(BaseModel):
    sentiment: str
    fake_probability: float

class Explanation(BaseModel):
    primary_reason: str
    supporting_reasons: List[str]
    #score_breakdown: dict[str, float | int]
    
    # summary: str
    # reasons: list[str]  

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
    

# credibility.py

from __future__ import annotations


def calculate_credibility(
    fake_score: float,
    sentiment_score: float,
    support_score: float = 0.0,
    manipulation_score: float = 0.0,
    verdict_hint: str = "UNKNOWN",
) -> int:

    score = 50.0

    #    fake_score=0.0 → +35 (very credible)
    #    fake_score=0.5 → ±0  (neutral)
    #    fake_score=1.0 → -35 (very low credibility)
    score += (0.5 - fake_score) * 70

    if verdict_hint == "SUPPORTED":
        score += (support_score - 0.3) * 20
    elif verdict_hint == "CONTRADICTED":
        score -= 20
    else:
        if support_score >= 0.15:
            score -= 4
            
    score -= manipulation_score * 15

    if sentiment_score > 0.92:
        score -= 5

    return int(max(0, min(100, round(score))))
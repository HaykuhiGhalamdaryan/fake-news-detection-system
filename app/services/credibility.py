# credibility.py

"""Credibility score calculator.

Produces a 0-100 integer representing how credible a piece of text appears.
Higher = more credible.

Scoring is additive from a neutral baseline of 50, not purely subtractive
from 100. This produces a more balanced distribution of scores and avoids
clustering everything near 100 for borderline cases.

Inputs used
-----------
- fake_score         : ML ensemble fake probability (0-1)
- sentiment_score    : sentiment model confidence (0-1)
- support_score      : fact-check semantic similarity (0-1)   [optional]
- manipulation_score : text-feature manipulation score (0-1)  [optional]
"""

from __future__ import annotations


def calculate_credibility(
    fake_score: float,
    sentiment_score: float,
    support_score: float = 0.0,
    manipulation_score: float = 0.0,
    verdict_hint: str = "UNKNOWN",
) -> int:
    """
    Calculate a credibility score (0-100) from all available signals.

    Parameters
    ----------
    fake_score         : ML fake probability — primary driver (0-1)
    sentiment_score    : sentiment model confidence (0-1)
    support_score      : best fact-check match score (0-1), default 0
    manipulation_score : text-feature manipulation score (0-1), default 0
    verdict_hint       : "SUPPORTED" | "CONTRADICTED" | "UNKNOWN"
                         Used to distinguish "no evidence found" (neutral)
                         from "evidence found but contradicts claim" (penalty).

    Fact-check contribution logic
    -----------------------------
    SUPPORTED     → positive boost based on support_score strength
    CONTRADICTED  → strong penalty (-20) — evidence actively contradicts claim
    UNKNOWN with low support_score → small neutral penalty (-4)
                                     (topic may simply not be on Wikipedia)
    UNKNOWN with no evidence at all → no penalty — we genuinely don't know
    """

    score = 50.0

    #    fake_score=0.0 → +35 (very credible)
    #    fake_score=0.5 → ±0  (neutral)
    #    fake_score=1.0 → -35 (very low credibility)
    score += (0.5 - fake_score) * 70

    # Fact-check contribution — differentiated by verdict_hint
    if verdict_hint == "SUPPORTED":
        # Positive evidence found — boost proportional to similarity strength
        score += (support_score - 0.3) * 20
    elif verdict_hint == "CONTRADICTED":
        # Evidence actively contradicts the claim — strong penalty
        score -= 20
    else:
        # UNKNOWN: distinguish "low similarity" from "nothing found at all"
        if support_score >= 0.15:
            # Some evidence retrieved but not conclusive — mild penalty
            score -= 4
        # support_score < 0.15 → no relevant evidence found at all
        # Topic may simply not be covered by Wikipedia/NewsAPI
        # → no penalty, treat as neutral

    #    manipulation_score=0.0 → 0
    #    manipulation_score=1.0 → -15
    score -= manipulation_score * 15

    if sentiment_score > 0.92:
        score -= 5

    return int(max(0, min(100, round(score))))
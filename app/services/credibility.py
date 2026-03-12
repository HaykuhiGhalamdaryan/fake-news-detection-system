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
) -> int:
    """
    Calculate a credibility score (0-100) from all available signals.

    Parameters
    ----------
    fake_score         : ML fake probability — primary driver (0-1)
    sentiment_score    : sentiment model confidence (0-1)
    support_score      : best fact-check match score (0-1), default 0
    manipulation_score : text-feature manipulation score (0-1), default 0
    """

    # Start from a neutral midpoint
    score = 50.0

    # ------------------------------------------------------------------
    # 1. Fake score — primary driver (±35 points)
    #    fake_score=0.0 → +35 (very credible)
    #    fake_score=0.5 → ±0  (neutral)
    #    fake_score=1.0 → -35 (very low credibility)
    # ------------------------------------------------------------------
    score += (0.5 - fake_score) * 70   # maps [0,1] → [+35, -35]

    # ------------------------------------------------------------------
    # 2. Fact support — can raise OR lower credibility (±20 points)
    #    support_score=0.0 → -10 (no evidence found → slight penalty)
    #    support_score=0.5 → +0  (neutral)
    #    support_score=1.0 → +10 (strong evidence → boost)
    #
    #    When support is completely absent (< 0.15), apply extra penalty.
    # ------------------------------------------------------------------
    score += (support_score - 0.3) * 20

    if support_score < 0.15:
        score -= 8   # no evidence found at all

    # ------------------------------------------------------------------
    # 3. Manipulation signals — penalty only (up to -15 points)
    #    manipulation_score=0.0 → 0
    #    manipulation_score=1.0 → -15
    # ------------------------------------------------------------------
    score -= manipulation_score * 15

    # ------------------------------------------------------------------
    # 4. Extreme sentiment intensity — small penalty
    #    Only penalise very high confidence + negative sentiment combo.
    #    (Positive sentiment at high confidence is fine — e.g. sports news)
    # ------------------------------------------------------------------
    if sentiment_score > 0.92:
        score -= 5

    # ------------------------------------------------------------------
    # 5. Clamp and return as integer
    # ------------------------------------------------------------------
    return int(max(0, min(100, round(score))))
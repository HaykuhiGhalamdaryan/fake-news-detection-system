# decision_engine.py

"""Hybrid verdict engine.

Since sentence transformers cannot understand negation, contradiction is
now detected via explicit geographic/entity mismatch rules in
fact_check_service.py. The verdict_hint is therefore reliable:

  SUPPORTED    → evidence clearly about same entity, high similarity
  CONTRADICTED → geo mismatch OR evidence about different entity
  UNKNOWN      → insufficient or ambiguous evidence

This makes Track A purely hint-driven, which is much more reliable
than threshold-based net_support_score comparisons.
"""

from __future__ import annotations


class _T:
    FAKE_HIGH     = 0.62
    FAKE_MODERATE = 0.40
    FAKE_LOW      = 0.30

    NET_STRONG   = 0.45
    NET_MODERATE = 0.20

    CRED_HIGH = 60
    CRED_LOW  = 35

    MANIP_HIGH     = 0.50
    MANIP_MODERATE = 0.20

    RHETORIC_SIGNALS = {
        "secret", "hidden truth", "they don't want you to know",
        "exposed", "shocking", "cover up", "government hiding",
        "mainstream media lies", "CLICKBAIT_LANGUAGE",
        "HYPERBOLIC_LANGUAGE", "VAGUE_ATTRIBUTION",
        "MANIPULATIVE_LANGUAGE",
    }


def generate_hybrid_verdict(
    fake_score: float,
    support_score: float,
    credibility_score: int,
    detected_patterns: list,
    manipulation_score: float = 0.0,
    net_support_score: float | None = None,
    verdict_hint: str = "UNKNOWN",
    high_disagreement: bool = False,
) -> str:
    net = net_support_score if net_support_score is not None else (support_score - 0.3)
    rhetoric_count = sum(1 for p in detected_patterns if p in _T.RHETORIC_SIGNALS)

    if high_disagreement and verdict_hint == "UNKNOWN":
        if fake_score < _T.FAKE_MODERATE:
            return "Uncertain"
        if fake_score < _T.FAKE_HIGH:
            return "Uncertain"

    if verdict_hint == "SUPPORTED" and fake_score < _T.FAKE_HIGH:
        if fake_score < _T.FAKE_MODERATE:
            return "True"
        return "Likely True"

    if verdict_hint == "CONTRADICTED":
        return "Likely Fake"

    if net >= _T.NET_STRONG and fake_score < _T.FAKE_MODERATE:
        return "True"

    if (
        net >= _T.NET_MODERATE
        and credibility_score >= _T.CRED_HIGH
        and fake_score < _T.FAKE_MODERATE
        and manipulation_score < _T.MANIP_HIGH
    ):
        return "Likely True"

    if fake_score >= _T.FAKE_HIGH and net < _T.NET_MODERATE:
        return "Fake"

    if (
        fake_score >= _T.FAKE_MODERATE
        and manipulation_score >= _T.MANIP_MODERATE
        and net < _T.NET_MODERATE
    ):
        return "Likely Fake"

    if fake_score >= _T.FAKE_MODERATE and rhetoric_count >= 1:
        return "Likely Fake"

    if fake_score >= _T.FAKE_MODERATE and credibility_score < _T.CRED_LOW:
        return "Likely Fake"

    if manipulation_score >= _T.MANIP_HIGH and fake_score >= _T.FAKE_LOW:
        return "Likely Fake"

    return "Uncertain"


def classify_model_confidence(fake_score: float) -> str:
    distance = abs(fake_score - 0.5)
    if distance >= 0.35:
        return "HIGH"
    elif distance >= 0.15:
        return "MEDIUM"
    else:
        return "LOW"


def generate_verdict(fake_score: float, credibility_score: int) -> str:
    """Legacy two-signal verdict — NOT used by the analyze router.
    
    Kept for reference only. Use generate_hybrid_verdict() for all new code.
    """
    if fake_score < 0.40 and credibility_score > 70:
        return "True"
    elif fake_score < 0.60:
        return "Likely True"
    elif 0.60 <= fake_score <= 0.75:
        return "Uncertain"
    elif fake_score < 0.85:
        return "Likely Fake"
    else:
        return "Fake"
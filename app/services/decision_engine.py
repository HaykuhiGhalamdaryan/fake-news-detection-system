# decision_engine.py

"""Hybrid verdict engine — fact-check driven.

Key insight from testing
------------------------
The ML models (hamzab + jy46604790) produce fake_score ~0.15-0.35 for
almost ALL short neutral sentences regardless of truth value. This means
fake_score alone cannot distinguish "Yerevan is the capital of Armenia"
(true) from "Armenia is in South America" (false) — both score ~0.16.

Solution: use a TWO-TRACK decision system.

Track A — FACT-CHECK TRACK (for verifiable factual claims)
  Primary signal : net_support_score (support - contradiction)
  Secondary signal: fake_score as a soft veto only
  Triggered when : net_support_score is meaningful (> 0.15 either direction)

Track B — ML TRACK (for opinion/manipulation/unverifiable claims)
  Primary signal : fake_score + manipulation_score + rhetoric signals
  Triggered when : fact-check finds no strong evidence (net_support near 0)

Contradiction detection
-----------------------
net_support_score = support_score - contradiction_score
  > +0.35  → evidence clearly supports the claim    → push toward True
  < -0.05  → evidence contradicts the claim          → push toward Fake
  near 0   → ambiguous (wrong entity, no evidence)  → rely on ML track
"""

from __future__ import annotations


class _T:
    # --- Fact-check track thresholds ---
    # net_support = support_score - contradiction_score
    NET_TRUE         = 0.42   # strong support → True
    NET_LIKELY_TRUE  = 0.22   # moderate support → Likely True
    NET_CONTRADICTED = -0.03  # evidence contradicts → push toward Fake
    NET_AMBIGUOUS_LO = -0.03
    NET_AMBIGUOUS_HI = 0.22   # zone where we fall back to ML track
    NET_STRONG       = 0.30
    NET_MODERATE     = 0.15

    # --- ML track thresholds (conservative — models score low) ---
    FAKE_HIGH        = 0.62
    FAKE_MODERATE    = 0.42
    FAKE_LOW         = 0.32

    # --- Supporting signals ---
    CRED_HIGH  = 60
    CRED_LOW   = 35
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
) -> str:
    net = net_support_score if net_support_score is not None else (support_score - 0.3)

    rhetoric_count = sum(1 for p in detected_patterns if p in _T.RHETORIC_SIGNALS)

    # ==================================================================
    # TRACK A — FACT-CHECK DRIVEN
    # Applies when fact-check found meaningful evidence (positive or negative)
    # ==================================================================

    # A1 — Strong support + fake_score not alarming → True
    if net >= _T.NET_TRUE and fake_score < _T.FAKE_MODERATE:
        return "True"

    # A2 — Strong support but fake_score somewhat elevated → Likely True
    if net >= _T.NET_TRUE and fake_score < _T.FAKE_HIGH:
        return "Likely True"

    # A3 — Moderate support + good credibility + no heavy manipulation
    if (
        net >= _T.NET_LIKELY_TRUE
        and credibility_score >= _T.CRED_HIGH
        and fake_score < _T.FAKE_MODERATE
        and manipulation_score < _T.MANIP_HIGH
    ):
        return "Likely True"

    # A4 — Evidence clearly contradicts the claim
    if net <= _T.NET_CONTRADICTED and verdict_hint == "CONTRADICTED":
        if fake_score >= _T.FAKE_LOW or manipulation_score >= _T.MANIP_MODERATE:
            return "Likely Fake"
        return "Uncertain"

    # A5 — Hint says CONTRADICTED even without very negative net
    if verdict_hint == "CONTRADICTED" and fake_score >= _T.FAKE_MODERATE:
        return "Likely Fake"

    # ==================================================================
    # TRACK B — ML / MANIPULATION DRIVEN
    # Applies when fact-check is ambiguous or found no strong evidence
    # ==================================================================

    # B1 — High fake probability + weak fact support → Fake
    if fake_score >= _T.FAKE_HIGH and net < _T.NET_LIKELY_TRUE:
        return "Fake"

    # B2 — Moderate fake + high manipulation + weak support
    if (
        fake_score >= _T.FAKE_MODERATE
        and manipulation_score >= _T.MANIP_MODERATE
        and net < _T.NET_LIKELY_TRUE
    ):
        return "Likely Fake"

    # B3 — Moderate fake + rhetoric signals (conspiracy language)
    if fake_score >= _T.FAKE_MODERATE and rhetoric_count >= 1:
        return "Likely Fake"

    # B4 — Low credibility + moderate fake
    if fake_score >= _T.FAKE_MODERATE and credibility_score < _T.CRED_LOW:
        return "Likely Fake"

    # B5 — Manipulation language present even with moderate fake score
    if manipulation_score >= _T.MANIP_HIGH and fake_score >= _T.FAKE_LOW:
        return "Likely Fake"

    # ==================================================================
    # DEFAULT — not enough signal to decide confidently
    # ==================================================================
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
    """Legacy two-signal verdict. Prefer generate_hybrid_verdict()."""
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
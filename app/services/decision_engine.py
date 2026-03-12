# decision_engine.py

"""Hybrid verdict engine.

The key insight driving this version:
- The ML models (hamzab + jy46604790) produce LOW fake_scores (~0.15-0.35)
  even for true statements — they are conservative by design.
- Therefore we CANNOT use fake_score thresholds alone to decide verdicts.
- Instead, net_support_score (fact evidence) is the PRIMARY driver for
  TRUE/LIKELY_TRUE decisions.
- fake_score is the PRIMARY driver for FAKE/LIKELY_FAKE decisions.
- When both are weak → UNCERTAIN.

Verdict logic summary
---------------------
  net_support HIGH + fake LOW  → True
  net_support MED  + fake LOW  → Likely True
  fake HIGH  + support LOW     → Fake
  fake MED   + manipulation    → Likely Fake
  otherwise                    → Uncertain
"""

from __future__ import annotations


class _T:
    # fake_score bands — lowered because models are conservative
    FAKE_HIGH        = 0.65
    FAKE_MODERATE    = 0.45
    FAKE_LOW         = 0.35

    # net_support_score bands (support - contradiction)
    NET_STRONG       = 0.40
    NET_MODERATE     = 0.20
    NET_WEAK         = 0.05

    # credibility
    CRED_HIGH = 60
    CRED_LOW  = 35

    # manipulation
    MANIP_HIGH     = 0.50
    MANIP_MODERATE = 0.20

    # Rhetoric signal names (subset — not all text_feature signals)
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
    # Use net_support if provided, fall back to raw support
    net = net_support_score if net_support_score is not None else support_score

    rhetoric_count = sum(
        1 for p in detected_patterns if p in _T.RHETORIC_SIGNALS
    )

    # ------------------------------------------------------------------
    # Rule 0 — Explicitly CONTRADICTED by evidence + elevated fake score
    # ------------------------------------------------------------------
    if verdict_hint == "CONTRADICTED":
        if fake_score >= _T.FAKE_MODERATE:
            return "Fake"
        return "Likely Fake"

    # ------------------------------------------------------------------
    # Rule 1 — Strong evidence support + low fake score → True
    # PRIMARY path for factual claims like "Yerevan is capital of Armenia"
    # ------------------------------------------------------------------
    if net >= _T.NET_STRONG and fake_score < _T.FAKE_LOW:
        return "True"

    # ------------------------------------------------------------------
    # Rule 2 — Strong evidence even with slightly higher fake score
    # ------------------------------------------------------------------
    if net >= _T.NET_STRONG and fake_score < _T.FAKE_MODERATE and credibility_score >= _T.CRED_HIGH:
        return "Likely True"

    # ------------------------------------------------------------------
    # Rule 3 — Moderate evidence + good credibility + no manipulation
    # ------------------------------------------------------------------
    if (
        net >= _T.NET_MODERATE
        and credibility_score >= _T.CRED_HIGH
        and fake_score < _T.FAKE_MODERATE
        and manipulation_score < _T.MANIP_HIGH
        and verdict_hint != "CONTRADICTED"
    ):
        return "Likely True"

    # ------------------------------------------------------------------
    # Rule 4 — High fake probability + weak support → Fake
    # ------------------------------------------------------------------
    if fake_score >= _T.FAKE_HIGH and net < _T.NET_MODERATE:
        return "Fake"

    # ------------------------------------------------------------------
    # Rule 5 — Moderate fake + high manipulation + weak support → Likely Fake
    # ------------------------------------------------------------------
    if (
        fake_score >= _T.FAKE_MODERATE
        and manipulation_score >= _T.MANIP_MODERATE
        and net < _T.NET_MODERATE
    ):
        return "Likely Fake"

    # ------------------------------------------------------------------
    # Rule 6 — Moderate fake + rhetoric signals → Likely Fake
    # ------------------------------------------------------------------
    if fake_score >= _T.FAKE_MODERATE and rhetoric_count >= 1:
        return "Likely Fake"

    # ------------------------------------------------------------------
    # Rule 7 — Moderate fake + low credibility → Likely Fake
    # ------------------------------------------------------------------
    if fake_score >= _T.FAKE_MODERATE and credibility_score < _T.CRED_LOW:
        return "Likely Fake"

    # ------------------------------------------------------------------
    # Rule 8 — Supported hint + any credibility → Likely True
    # ------------------------------------------------------------------
    if verdict_hint == "SUPPORTED" and fake_score < _T.FAKE_MODERATE:
        return "Likely True"

    # ------------------------------------------------------------------
    # Default
    # ------------------------------------------------------------------
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
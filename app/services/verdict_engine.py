#verdict_engine.py

from __future__ import annotations


def compute_risk_score(
    fake_probability: float,
    support_score: float,
    emotional_words_detected: bool,
    emotional_signal_count: int = 0,
) -> int:
    """
    Compute a risk score (0-100).

    emotional_signal_count replaces the broad emotional_words_detected boolean
    for the +15 penalty — only genuinely emotional/manipulation signals
    (EMOTIONAL_LANGUAGE, CLICKBAIT_LANGUAGE, HYPERBOLIC_LANGUAGE) contribute,
    not structural signals like TITLE_CASE_ABUSE or MODERATE_CAPS_RATIO.
    emotional_words_detected is kept for backward compatibility.
    """
    risk_score = int(fake_probability * 70)

    # Scale emotional penalty by count, cap at +15
    if emotional_signal_count > 0:
        risk_score += min(emotional_signal_count * 7, 15)
    elif emotional_words_detected:
        # Legacy fallback — broad boolean still adds a smaller penalty
        risk_score += 8

    if support_score >= 0.40:
        risk_score -= 25

    if support_score < 0.15:
        risk_score += 10

    return max(0, min(100, risk_score))


def generate_signals(
    fake_probability: float,
    credibility_score: int,
    support_score: float,
    emotional_words_detected: bool,
    verdict_hint: str = "UNKNOWN",
    manipulation_signals: list[str] | None = None,
):
    """
    Generate named signals for the response and explanation engine.

    Changes vs original:
    - FACT_CONTRADICTION now fires on verdict_hint == "CONTRADICTED"
      (not on support_score < 0.15 which means "no evidence", not contradiction)
    - FACT_SUPPORTED added for strong positive evidence
    - verdict_hint is now a first-class input so fact-check outcome
      is always reflected in signals
    - manipulation_signals passed through so explanation engine can
      reference specific patterns without re-computing
    """
    signals = []

    if fake_probability > 0.8:
        signals.append("HIGH_FAKE_PROBABILITY")
    elif fake_probability > 0.65:
        signals.append("ELEVATED_FAKE_PROBABILITY")

    if emotional_words_detected:
        signals.append("EMOTIONAL_LANGUAGE")

    if credibility_score < 40:
        signals.append("LOW_CREDIBILITY")
    elif credibility_score >= 75:
        signals.append("HIGH_CREDIBILITY")

    # Fact-check outcome — use verdict_hint, not raw support_score
    if verdict_hint == "CONTRADICTED":
        signals.append("FACT_CONTRADICTION")
    elif verdict_hint == "SUPPORTED" and support_score >= 0.60:
        signals.append("FACT_SUPPORTED")
    elif support_score < 0.15:
        signals.append("NO_EVIDENCE_FOUND")

    # Pass through manipulation signals from text_features
    for sig in (manipulation_signals or []):
        if sig not in signals:
            signals.append(sig)

    return signals
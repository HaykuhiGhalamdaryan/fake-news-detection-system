#verdict_engine.py

from __future__ import annotations


def compute_verdict(fake_probability: float, support_score: float) -> str:
    """Decision rule that combines ML probability with fact-check support."""
    if fake_probability >= 0.75:
        return "Fake"
    elif fake_probability <= 0.35 and support_score >= 0.30:
        return "True"
    elif fake_probability >= 0.55 and support_score < 0.20:
        return "Fake"
    elif support_score >= 0.40:
        return "True"
    else:
        return "Uncertain"


def compute_risk_score(
    fake_probability: float,
    support_score: float,
    emotional_words_detected: bool,
) -> int:
    """Less aggressive risk scoring with fact-support corrections."""
    risk_score = int(fake_probability * 70)

    if emotional_words_detected:
        risk_score += 15

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
):
    signals = []

    if fake_probability > 0.8:
        signals.append("HIGH_FAKE_PROBABILITY")

    if emotional_words_detected:
        signals.append("EMOTIONAL_LANGUAGE")

    if credibility_score < 40:
        signals.append("LOW_CREDIBILITY")

    if support_score < 0.15:
        signals.append("FACT_CONTRADICTION")

    return signals

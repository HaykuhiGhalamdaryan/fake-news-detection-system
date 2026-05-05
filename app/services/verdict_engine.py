#verdict_engine.py

from __future__ import annotations


def compute_risk_score(
    fake_probability: float,
    support_score: float,
    emotional_words_detected: bool,
    emotional_signal_count: int = 0,
) -> int:
    
    risk_score = int(fake_probability * 70)

    if emotional_signal_count > 0:
        risk_score += min(emotional_signal_count * 7, 15)
    elif emotional_words_detected:
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

    if verdict_hint == "CONTRADICTED":
        signals.append("FACT_CONTRADICTION")
    elif verdict_hint == "SUPPORTED" and support_score >= 0.60:
        signals.append("FACT_SUPPORTED")
    elif support_score < 0.15:
        signals.append("NO_EVIDENCE_FOUND")

    for sig in (manipulation_signals or []):
        if sig not in signals:
            signals.append(sig)

    return signals
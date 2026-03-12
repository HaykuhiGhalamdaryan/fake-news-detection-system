#explanation.py

def generate_explanation(
    fake_score: float,
    sentiment: str = "",
    credibility_score: int = 100,
    sentiment_score: float = 0.0,
    signals: list[str] | None = None,
):
    signals = signals or []
    supporting_reasons = []

    if "FACT_CONTRADICTION" in signals:
        primary_reason = (
            "The claim contradicts information found in trusted sources."
        )
    elif fake_score > 0.85:
        primary_reason = (
            f"The claim has a very high probability of being fake "
            f"({round(fake_score * 100)}%)."
        )
    elif fake_score > 0.65 or "HIGH_FAKE_PROBABILITY" in signals:
        primary_reason = (
            "The machine learning model strongly predicts misinformation."
        )
    elif fake_score > 0.45:
        primary_reason = (
            "The claim has some weak indicators of misinformation but remains uncertain."
        )
    else:
        primary_reason = (
            "The claim does not show strong indicators of misinformation."
        )

    if "EMOTIONAL_LANGUAGE" in signals:
        supporting_reasons.append(
            "The text uses emotionally charged language often seen in misinformation."
        )

    if "HIGH_FAKE_PROBABILITY" in signals:
        supporting_reasons.append(
            "The machine learning model strongly predicts misinformation."
        )

    if "LOW_CREDIBILITY" in signals or credibility_score < 50:
        supporting_reasons.append(
            "The credibility score is relatively low."
        )
        
    if not supporting_reasons:
        supporting_reasons.append(
            "No strong secondary indicators were detected."
        )

    return {
        "primary_reason": primary_reason,
        "supporting_reasons": supporting_reasons
        # "score_breakdown": {
        #     "fake_probability": round(fake_score, 2),
        #     "credibility_score": credibility_score
        # }
    }

#explanation.py

def generate_explanation(
    fake_score: float,
    sentiment: str = "",
    credibility_score: int = 100,
    sentiment_score: float = 0.0,
    signals: list[str] | None = None,
    verdict: str = "",
):
    signals = signals or []
    supporting_reasons = []

    if verdict == "True":
        if "FACT_SUPPORTED" in signals:
            primary_reason = "The claim is supported by evidence found in trusted sources."
        else:
            primary_reason = "The claim does not show significant indicators of misinformation."

    elif verdict == "Likely True":
        primary_reason = "The claim shows low indicators of misinformation and appears credible."

    elif verdict == "Uncertain":
        if "NO_EVIDENCE_FOUND" in signals:
            primary_reason = (
                "No relevant evidence was found to confirm or contradict this claim."
            )
        elif "FACT_CONTRADICTION" in signals:
            primary_reason = (
                "The claim contains elements that conflict with available sources, "
                "but confidence is low."
            )
        else:
            primary_reason = (
                "The available signals are mixed and a confident verdict cannot be reached."
            )

    elif verdict == "Likely Fake":
        if "FACT_CONTRADICTION" in signals:
            primary_reason = "The claim contradicts information found in trusted sources."
        else:
            primary_reason = (
                f"The claim shows elevated indicators of misinformation "
                f"({round(fake_score * 100)}% fake probability)."
            )

    elif verdict == "Fake":
        if "FACT_CONTRADICTION" in signals:
            primary_reason = (
                "The claim directly contradicts evidence found in trusted sources "
                "and has a very high fake probability."
            )
        else:
            primary_reason = (
                f"The claim has a very high probability of being fake "
                f"({round(fake_score * 100)}%)."
            )

    else:
        if fake_score > 0.65:
            primary_reason = "The machine learning model strongly predicts misinformation."
        elif fake_score > 0.45:
            primary_reason = "The claim has some weak indicators of misinformation."
        else:
            primary_reason = "The claim does not show strong indicators of misinformation."

    if "EMOTIONAL_LANGUAGE" in signals:
        supporting_reasons.append(
            "The text uses emotionally charged language often associated with misinformation."
        )

    if "CLICKBAIT_LANGUAGE" in signals:
        supporting_reasons.append(
            "The text contains clickbait phrases designed to provoke sharing."
        )

    if "HYPERBOLIC_LANGUAGE" in signals:
        supporting_reasons.append(
            "The text uses hyperbolic or exaggerated language."
        )

    if "VAGUE_ATTRIBUTION" in signals:
        supporting_reasons.append(
            "Claims are attributed to unnamed or vague sources."
        )

    if "FACT_SUPPORTED" in signals and verdict not in ("True", "Likely True"):
        supporting_reasons.append(
            "Some supporting evidence was found in trusted sources."
        )

    if "LOW_CREDIBILITY" in signals:
        supporting_reasons.append("The overall credibility score is low.")

    if "HIGH_CREDIBILITY" in signals and verdict in ("True", "Likely True"):
        supporting_reasons.append("The overall credibility score is high.")

    if not supporting_reasons:
        supporting_reasons.append("No strong secondary indicators were detected.")

    return {
        "primary_reason":    primary_reason,
        "supporting_reasons": supporting_reasons,
    }
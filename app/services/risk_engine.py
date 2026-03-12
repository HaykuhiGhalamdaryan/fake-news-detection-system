#risk_engine.py

def calculate_risk_score(
    fake_score: float,
    credibility_score: int,
    sentiment_score: float
) -> int:
    """
    Combines all factors into a unified 0–100 risk score.
    """

    # fake_score already 0-1
    fake_component = fake_score * 100

    # credibility is 0-100 but inverse risk
    credibility_component = 100 - credibility_score

    # sentiment intensity (absolute value if needed)
    sentiment_component = sentiment_score * 100

    risk = (
        fake_component * 0.6 +
        credibility_component * 0.3 +
        sentiment_component * 0.1
    )

    return int(min(max(risk, 0), 100))

def classify_risk(risk_score: int) -> str:
    if risk_score >= 70:
        return "HIGH"
    elif risk_score >= 40:
        return "MEDIUM"
    else:
        return "LOW"

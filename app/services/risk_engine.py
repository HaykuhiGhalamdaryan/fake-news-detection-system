# risk_engine.py

def classify_risk(risk_score: int) -> str:
    if risk_score >= 70:
        return "HIGH"
    elif risk_score >= 40:
        return "MEDIUM"
    else:
        return "LOW"
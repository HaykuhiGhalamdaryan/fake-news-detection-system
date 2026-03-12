# analyze.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import AnalysisResult
from app.models.schemas import AnalyzeRequest, AnalyzeResponse
from app.services.credibility import calculate_credibility
from app.services.decision_engine import classify_model_confidence, generate_hybrid_verdict
from app.services.emotion_detector import detect_patterns
from app.services.explanation import generate_explanation
from app.services.fact_check_service import fact_check_claim
from app.services.nlp_service import analyze_text
from app.services.risk_engine import classify_risk
from app.services.text_chunker import analyze_with_chunking
from app.services.text_features import analyze_text_features, get_manipulation_score_contribution
from app.services.verdict_engine import compute_risk_score, generate_signals

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_claim(request: AnalyzeRequest, db: Session = Depends(get_db)):

    # ------------------------------------------------------------------
    # 1. Core NLP — uses chunking automatically for long texts
    #    For short texts (<280 words) this is identical to before.
    #    For long texts it splits, scores each chunk, and aggregates.
    # ------------------------------------------------------------------
    nlp_result = analyze_with_chunking(request.text, analyze_text)
    fake_probability = float(nlp_result["fake_score"])

    # ------------------------------------------------------------------
    # 2. Text feature analysis — surface manipulation signals
    #    Always run on the FULL text (regex is fast, no token limit)
    # ------------------------------------------------------------------
    text_features = analyze_text_features(request.text)
    manipulation_score = text_features["manipulation_score"]
    manipulation_contribution = get_manipulation_score_contribution(manipulation_score)

    # Blend: 85% ML score + 15% manipulation nudge
    fake_probability = round(0.85 * fake_probability + 0.15 * manipulation_contribution, 4)

    # ------------------------------------------------------------------
    # 3. Fact checking — run on first 500 words for relevance
    #    (fact-check works best on the core claim, not full article body)
    # ------------------------------------------------------------------
    claim_text = " ".join(request.text.split()[:500])
    fact_check_result = fact_check_claim(claim_text)
    support_score     = float(fact_check_result.get("support_score", 0.0))
    net_support_score = float(fact_check_result.get("net_support_score", support_score))
    verdict_hint      = fact_check_result.get("verdict_hint", "UNKNOWN")

    # ------------------------------------------------------------------
    # 4. Credibility score
    # ------------------------------------------------------------------
    credibility_score = calculate_credibility(
        fake_score=fake_probability,
        sentiment_score=nlp_result["sentiment_score"],
        support_score=support_score,
        manipulation_score=manipulation_score,
    )

    # ------------------------------------------------------------------
    # 5. Emotion / manipulation pattern detection
    #    Always run on full text
    # ------------------------------------------------------------------
    emotion_analysis = detect_patterns(request.text)

    for sig in text_features["signals"]:
        if sig not in emotion_analysis["detected_patterns"]:
            emotion_analysis["detected_patterns"].append(sig)

    if text_features["manipulation_level"] == "HIGH":
        emotion_analysis["tone"] = "emotional"

    emotional_words_detected = len(emotion_analysis["detected_patterns"]) > 0

    # ------------------------------------------------------------------
    # 6. Verdict
    # ------------------------------------------------------------------
    verdict = generate_hybrid_verdict(
        fake_score=fake_probability,
        support_score=support_score,
        credibility_score=credibility_score,
        detected_patterns=emotion_analysis["detected_patterns"],
        manipulation_score=manipulation_score,
        net_support_score=net_support_score,
        verdict_hint=verdict_hint,
    )

    confidence = int(fake_probability * 100)
    model_confidence = classify_model_confidence(fake_probability)

    # ------------------------------------------------------------------
    # 7. Signals
    # ------------------------------------------------------------------
    signals = generate_signals(
        fake_probability,
        credibility_score,
        support_score,
        emotional_words_detected,
    )

    for sig in text_features["signals"]:
        if sig not in signals:
            signals.append(sig)

    if emotion_analysis["detected_patterns"] and "MANIPULATIVE_LANGUAGE" not in signals:
        signals.append("MANIPULATIVE_LANGUAGE")

    if verdict_hint == "CONTRADICTED":
        signals.append("FACT_CONTRADICTION")

    # ------------------------------------------------------------------
    # 8. Explanation
    # ------------------------------------------------------------------
    explanation = generate_explanation(
        fake_probability,
        nlp_result["sentiment"],
        credibility_score,
        nlp_result["sentiment_score"],
        signals=signals,
    )

    # ------------------------------------------------------------------
    # 9. Risk scoring
    # ------------------------------------------------------------------
    risk_score = compute_risk_score(
        fake_probability,
        support_score,
        emotional_words_detected,
    )

    risk_level = classify_risk(risk_score)

    if (
        emotion_analysis["tone"] == "neutral"
        and fake_probability < 0.50
        and net_support_score >= 0.25
    ):
        risk_level = "LOW"

    # ------------------------------------------------------------------
    # 10. Persist to database
    # ------------------------------------------------------------------
    db_record = AnalysisResult(
        text=request.text,
        verdict=verdict,
        confidence=confidence,
        credibility_score=credibility_score,
        sentiment=nlp_result["sentiment"],
        fake_probability=fake_probability,
        risk_score=risk_score,
        risk_level=risk_level,
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    # ------------------------------------------------------------------
    # 11. Response
    # ------------------------------------------------------------------
    return {
        "verdict": verdict,
        "confidence": confidence,
        "model_confidence": model_confidence,
        "credibility_score": credibility_score,
        "analysis": {
            "sentiment": nlp_result["sentiment"],
            "fake_probability": round(fake_probability, 2),
        },
        "llm_analysis": {
            "tone": emotion_analysis["tone"],
            "detected_patterns": emotion_analysis["detected_patterns"],
            "reasoning": (
                f"Analyzed {nlp_result.get('chunks_analyzed', 1)} chunk(s). "
                "Pattern-based manipulation scan completed."
            ),
        },
        "fact_check": {
            "sources": fact_check_result.get("sources", []),
            "support_score": support_score,
            "evidence": fact_check_result.get("evidence", []),
        },
        "signals": signals,
        "explanation": explanation,
        "risk_score": risk_score,
        "risk_level": risk_level,
    }
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

    nlp_result = analyze_with_chunking(request.text, analyze_text)
    fake_probability = float(nlp_result["fake_score"])

    text_features = analyze_text_features(request.text)
    manipulation_score = text_features["manipulation_score"]
    manipulation_contribution = get_manipulation_score_contribution(manipulation_score)

    # 85% ML score + 15% manipulation nudge
    fake_probability = round(0.85 * fake_probability + 0.15 * manipulation_contribution, 4)

    claim_text = " ".join(request.text.split()[:500])
    fact_check_result = fact_check_claim(claim_text)
    
    
    support_score     = float(fact_check_result.get("support_score", 0.0))
    net_support_score = float(fact_check_result.get("net_support_score", support_score))
    verdict_hint      = fact_check_result.get("verdict_hint", "UNKNOWN")

    credibility_score = calculate_credibility(
        fake_score=fake_probability,
        sentiment_score=nlp_result["sentiment_score"],
        support_score=support_score,
        manipulation_score=manipulation_score,
    )

    emotion_analysis = detect_patterns(request.text)

    for sig in text_features["signals"]:
        if sig not in emotion_analysis["detected_patterns"]:
            emotion_analysis["detected_patterns"].append(sig)

    if text_features["manipulation_level"] == "HIGH":
        emotion_analysis["tone"] = "emotional"

    emotional_words_detected = len(emotion_analysis["detected_patterns"]) > 0

    verdict = generate_hybrid_verdict(
        fake_score=fake_probability,
        support_score=support_score,
        credibility_score=credibility_score,
        detected_patterns=emotion_analysis["detected_patterns"],
        manipulation_score=manipulation_score,
        net_support_score=net_support_score,
        verdict_hint=verdict_hint,
        high_disagreement=nlp_result.get("high_disagreement", False),
    )

    fake_confidence = int(fake_probability * 100)
    model_confidence = classify_model_confidence(fake_probability)

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

    explanation = generate_explanation(
        fake_probability,
        nlp_result["sentiment"],
        credibility_score,
        nlp_result["sentiment_score"],
        signals=signals,
    )
    
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

    db_record = AnalysisResult(
        text=request.text,
        verdict=verdict,
        confidence=fake_confidence,
        credibility_score=credibility_score,
        sentiment=nlp_result["sentiment"],
        fake_probability=fake_probability,
        risk_score=risk_score,
        risk_level=risk_level,
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    return {
        "verdict": verdict,
        "confidence": fake_confidence,
        "model_confidence": model_confidence,
        "credibility_score": credibility_score,
        "analysis": {
            "sentiment":         nlp_result["sentiment"],
            "fake_probability":  round(fake_probability, 2),
            "primary_score":     nlp_result.get("primary_score") or nlp_result.get("fake_score"),
            "secondary_score":   nlp_result.get("secondary_score") or nlp_result.get("fake_score"),
            "tiebreaker_score":  nlp_result.get("tiebreaker_score"),
            "model_spread":      nlp_result.get("model_spread"),
            "high_disagreement": nlp_result.get("high_disagreement", False),
            "negation_detected": nlp_result.get("negation_detected", False),
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
        "article_warning": None,
    }

from app.services.url_extractor import extract_text_from_url
from app.models.schemas import AnalyzeURLRequest
from fastapi import HTTPException


@router.post("/analyze-url", response_model=AnalyzeResponse)
def analyze_url(request: AnalyzeURLRequest, db: Session = Depends(get_db)):
    """
    Fetch a news article from *url*, extract its text, then run the full
    analysis pipeline — identical to POST /analyze but the input is a URL.
    """
    result = extract_text_from_url(request.url)

    if not result["success"] and not result.get("text"):
        raise HTTPException(
            status_code=422,
            detail=f"Could not fetch article: {result.get('error', 'Unknown error')}"
        )

    text = result.get("text", "")
    word_count = result.get("word_count", len(text.split()))

    # Build warning — set whenever the page looks like a listing/homepage
    # or when very little text was extracted
    article_warning = None
    if result.get("listing_warning"):
        article_warning = result["listing_warning"]
    elif word_count < 150:
        article_warning = (
            "Very little text was extracted from this page. "
            "It may be a homepage, paywalled, or blocking scrapers. "
            "Try a direct article URL instead."
        )

    if result.get("title"):
        text = result["title"] + ". " + text

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract any text from this URL."
        )

    fake_req = AnalyzeRequest(text=text)
    response = analyze_claim(fake_req, db)

    response["article_warning"] = article_warning

    return response
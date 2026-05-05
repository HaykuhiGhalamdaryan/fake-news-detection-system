# analyze.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from urllib.parse import urlparse

from app.database.db import get_db
from app.database.models import AnalysisResult
from app.models.schemas import AnalyzeRequest, AnalyzeResponse, AnalyzeURLRequest, TranslationInfo
from app.services.credibility import calculate_credibility
from app.services.decision_engine import classify_model_confidence, generate_hybrid_verdict
from app.services.emotion_detector import detect_patterns
from app.services.explanation import generate_explanation
from app.services.fact_check_service import fact_check_claim
from app.services.nlp_service import analyze_text
from app.services.risk_engine import classify_risk
from app.services.text_chunker import analyze_with_chunking
from app.services.text_features import analyze_text_features, get_manipulation_score_contribution
from app.services.translation_service import maybe_translate
from app.services.verdict_engine import compute_risk_score, generate_signals
from app.services.source_analyzer import analyze_source
from app.services.url_extractor import extract_text_from_url, is_homepage_url

router = APIRouter()


def _extract_domain(text: str, source_url: str | None = None) -> str | None:
    url = source_url or (text.split()[0] if text.strip() else "")
    if url.startswith("http"):
        try:
            domain = urlparse(url).netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            return domain or None
        except Exception:
            pass
    return None


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_claim(request: AnalyzeRequest, db: Session = Depends(get_db)):
    translation_result = maybe_translate(request.text)
    analysis_text      = translation_result["text"]   
    was_translated     = translation_result["was_translated"]
    original_lang      = translation_result["original_lang"]
    translation_error  = translation_result["translation_error"]

    nlp_result       = analyze_with_chunking(analysis_text, analyze_text)
    fake_probability = float(nlp_result["fake_score"])

    text_features         = analyze_text_features(analysis_text)
    manipulation_score    = text_features["manipulation_score"]
    manipulation_contribution = get_manipulation_score_contribution(manipulation_score)

    claim_text        = " ".join(analysis_text.split()[:500])
    fact_check_result = fact_check_claim(claim_text)

    support_score     = float(fact_check_result.get("support_score", 0.0))
    net_support_score = float(fact_check_result.get("net_support_score", support_score))
    verdict_hint      = fact_check_result.get("verdict_hint", "UNKNOWN")

    fake_probability = round(
        0.85 * fake_probability + 0.15 * manipulation_contribution, 4
    )

    credibility_score = calculate_credibility(
        fake_score=fake_probability,
        sentiment_score=nlp_result["sentiment_score"],
        support_score=support_score,
        manipulation_score=manipulation_score,
        verdict_hint=verdict_hint,
    )

    emotion_analysis = detect_patterns(request.text)

    for sig in text_features["signals"]:
        if sig not in emotion_analysis["detected_patterns"]:
            emotion_analysis["detected_patterns"].append(sig)

    if text_features["manipulation_level"] == "HIGH":
        emotion_analysis["tone"] = "emotional"

    emotional_words_detected = len(emotion_analysis["detected_patterns"]) > 0

    _EMOTIONAL_SIGNAL_TAGS = {
        "EMOTIONAL_LANGUAGE", "CLICKBAIT_LANGUAGE",
        "HYPERBOLIC_LANGUAGE", "VAGUE_ATTRIBUTION",
    }
    emotional_signal_count = sum(
        1 for s in emotion_analysis["detected_patterns"]
        if s in _EMOTIONAL_SIGNAL_TAGS
    )

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

    fake_confidence  = int(fake_probability * 100)
    model_confidence = classify_model_confidence(fake_probability)

    signals = generate_signals(
        fake_probability=fake_probability,
        credibility_score=credibility_score,
        support_score=support_score,
        emotional_words_detected=emotional_words_detected,
        verdict_hint=verdict_hint,
        manipulation_signals=text_features["signals"],
    )

    if emotion_analysis["detected_patterns"] and "MANIPULATIVE_LANGUAGE" not in signals:
        signals.append("MANIPULATIVE_LANGUAGE")

    explanation = generate_explanation(
        fake_score=fake_probability,
        sentiment=nlp_result["sentiment"],
        credibility_score=credibility_score,
        sentiment_score=nlp_result["sentiment_score"],
        signals=signals,
        verdict=verdict,
    )

    risk_score = compute_risk_score(
        fake_probability,
        support_score,
        emotional_words_detected,
        emotional_signal_count=emotional_signal_count,
    )

    risk_level = classify_risk(risk_score)

    if verdict in ("True", "Likely True"):
        if risk_level == "HIGH":
            risk_level = "MEDIUM"
        if (
            verdict == "True"
            or (verdict == "Likely True" and net_support_score >= 0.25)
        ):
            risk_level = "LOW"

    elif verdict in ("Fake", "Likely Fake"):
        if risk_level == "LOW":
            risk_level = "MEDIUM"
        if verdict == "Fake" or fake_probability >= 0.70:
            risk_level = "HIGH"

    db_record = AnalysisResult(
        text=request.text,
        source_domain=_extract_domain(request.text, request.source_url),
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
        "verdict":          verdict,
        "confidence":       fake_confidence,
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
            "tone":              emotion_analysis["tone"],
            "detected_patterns": emotion_analysis["detected_patterns"],
            "reasoning": (
                f"Analyzed {nlp_result.get('chunks_analyzed', 1)} chunk(s). "
                "Pattern-based manipulation scan completed."
            ),
        },
        "fact_check": {
            "sources":       fact_check_result.get("sources", []),
            "support_score": support_score,
            "evidence":      fact_check_result.get("evidence", []),
        },
        "signals":         signals,
        "explanation":     explanation,
        "risk_score":      risk_score,
        "risk_level":      risk_level,
        "article_warning": None,
        "source_analysis": None,
        "translation": TranslationInfo(
            was_translated=was_translated,
            original_lang=original_lang,
            translation_error=translation_error,
        ) if (was_translated or original_lang != "en") else None,
    }


@router.post("/analyze-url")
def analyze_url(request: AnalyzeURLRequest, db: Session = Depends(get_db)):
    
    if is_homepage_url(request.url):
        source_analysis = analyze_source(request.url, db)

        if not source_analysis.get("known_source"):
            raise HTTPException(
                status_code=422,
                detail=(
                    "This URL does not appear to be a news article or a known news source. "
                    "Please submit a direct link to a specific news article."
                )
            )

        return {
            "mode":            "source_only",
            "source_analysis": source_analysis,
        }

    result = extract_text_from_url(request.url)

    if not result["success"] and not result.get("text"):
        raise HTTPException(
            status_code=422,
            detail=f"Could not fetch article: {result.get('error', 'Unknown error')}"
        )

    text       = result.get("text", "")
    word_count = result.get("word_count", len(text.split()))

    _MIN_WORDS = 50

    if word_count < _MIN_WORDS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Not enough article text could be extracted from this URL "
                f"({word_count} words found, minimum {_MIN_WORDS} required). "
                "Please make sure it is a direct link to a news article — "
                "not a homepage, video, social media page, or paywalled content."
            )
        )

    if result.get("is_likely_listing") and word_count < 100:
        source_analysis = analyze_source(request.url, db)
        return {
            "mode":            "source_only",
            "source_analysis": source_analysis,
        }

    article_warning = None
    if result.get("listing_warning"):
        article_warning = result["listing_warning"]
    elif word_count < 150:
        article_warning = (
            "Very little text was extracted from this page. "
            "It may be paywalled or blocking scrapers. "
            "Try a direct article URL instead."
        )

    if result.get("title"):
        text = result["title"] + ". " + text

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract any text from this URL."
        )

    source_analysis = analyze_source(request.url, db)

    fake_req     = AnalyzeRequest(text=text, source_url=request.url)
    raw_response = analyze_claim(fake_req, db)

    if hasattr(raw_response, "model_dump"):
        response = raw_response.model_dump()   
    elif hasattr(raw_response, "dict"):
        response = raw_response.dict()         
    else:
        response = dict(raw_response)

    response["mode"]            = "article"
    response["article_warning"] = article_warning
    response["source_analysis"] = source_analysis

    return response
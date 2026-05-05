# nlp_service.py

from __future__ import annotations

import re
from transformers import pipeline

_sentiment_model  = None
_primary_model    = None   
_secondary_model  = None   
_tiebreaker_model = None   

_NEGATION_RE = re.compile(
    r"\b(not|never|isn'?t|aren'?t|wasn'?t|weren'?t|don'?t|doesn'?t"
    r"|didn'?t|no longer|false that|untrue|incorrect|no evidence"
    r"|has not|have not|had not|cannot|can't|won'?t|wouldn'?t)\b",
    re.IGNORECASE,
)

_NEGATION_CORRECTION_MIN = 0.40
_NEGATION_CORRECTION_MAX = 0.70
_NEGATION_DAMPENING = 0.30

_DISAGREEMENT_THRESHOLD = 0.35


def _has_negation(text: str) -> bool:
    return bool(_NEGATION_RE.search(text))


def _apply_negation_correction(score: float) -> float:
    if _NEGATION_CORRECTION_MIN <= score <= _NEGATION_CORRECTION_MAX:
        return round(score + _NEGATION_DAMPENING * (0.5 - score), 4)
    return score


def _get_models():
    global _sentiment_model, _primary_model, _secondary_model, _tiebreaker_model

    if _sentiment_model is None:
        _sentiment_model = pipeline(
            "sentiment-analysis",
            model="distilbert/distilbert-base-uncased-finetuned-sst-2-english",
            framework="pt",
        )

    if _primary_model is None:
        # LABEL_0 = FAKE, LABEL_1 = REAL
        _primary_model = pipeline(
            "text-classification",
            model="hamzab/roberta-fake-news-classification",
            framework="pt",
            truncation=True,
            max_length=512,
        )

    if _secondary_model is None:
        _secondary_model = pipeline(
            "text-classification",
            model="jy46604790/Fake-News-Bert-Detect",
            framework="pt",
            truncation=True,
            max_length=512,
        )

    if _tiebreaker_model is None:
        try:
            _tiebreaker_model = pipeline(
                "text-classification",
                model="mrm8488/bert-tiny-finetuned-fake-news-detection",
                framework="pt",
                truncation=True,
                max_length=512,
            )
        except Exception:
            _tiebreaker_model = None

    return _sentiment_model, _primary_model, _secondary_model, _tiebreaker_model


def _to_fake_prob(result: dict) -> float:
    label: str   = result["label"]
    score: float = float(result["score"])

    if label in ("LABEL_0", "FAKE"):   
        return score
    else:                               
        return 1.0 - score


def analyze_text(text: str) -> dict:
    sentiment_model, primary_model, secondary_model, tiebreaker_model = _get_models()

    sentiment_result = sentiment_model(text, truncation=True, max_length=512)[0]
    sentiment        = sentiment_result["label"]
    sentiment_score  = float(sentiment_result["score"])

    primary_result = primary_model(text)[0]
    primary_score  = _to_fake_prob(primary_result)

    try:
        secondary_result = secondary_model(text)[0]
        secondary_score  = _to_fake_prob(secondary_result)
    except Exception:
        secondary_score = primary_score

    tiebreaker_score = None
    if tiebreaker_model is not None:
        try:
            tiebreaker_result = tiebreaker_model(text)[0]
            tiebreaker_score  = _to_fake_prob(tiebreaker_result)
        except Exception:
            tiebreaker_score = None

    if tiebreaker_score is not None:
        fake_score = (
            0.50 * primary_score
            + 0.35 * secondary_score
            + 0.15 * tiebreaker_score
        )
    else:
        fake_score = 0.60 * primary_score + 0.40 * secondary_score

    model_spread      = round(abs(primary_score - secondary_score), 4)
    high_disagreement = model_spread > _DISAGREEMENT_THRESHOLD

    negation_detected = _has_negation(text)
    if negation_detected:
        fake_score = _apply_negation_correction(fake_score)

    fake_score = round(fake_score, 4)
    fake_label = "FAKE" if fake_score >= 0.5 else "REAL"

    return {
        "sentiment":         sentiment,
        "sentiment_score":   sentiment_score,
        "fake_label":        fake_label,
        "fake_score":        fake_score,
        "primary_score":     round(primary_score, 4),
        "secondary_score":   round(secondary_score, 4),
        "tiebreaker_score":  round(tiebreaker_score, 4) if tiebreaker_score is not None else None,
        "model_spread":      model_spread,
        "high_disagreement": high_disagreement,
        "negation_detected": negation_detected,
    }
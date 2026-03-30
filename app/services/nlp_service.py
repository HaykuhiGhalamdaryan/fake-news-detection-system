# nlp_service.py

"""NLP Service — fake-news probability + sentiment.

Models used
-----------
1. Sentiment  : distilbert-base-uncased-finetuned-sst-2-english
               Fast, reliable SST-2 sentiment classifier.

2. Fake-news  : hamzab/roberta-fake-news-classification  (PRIMARY)
               RoBERTa fine-tuned on fake-and-real-news-dataset.
               Labels: LABEL_0 = FAKE, LABEL_1 = REAL
               Weight: 0.50

3. Fake-news  : jy46604790/Fake-News-Bert-Detect  (SECONDARY)
               RoBERTa trained on 40,000+ news articles.
               Labels: LABEL_0 = FAKE, LABEL_1 = REAL
               Weight: 0.35

4. Fake-news  : mrm8488/bert-tiny-finetuned-fake-news-detection  (TIEBREAKER)
               Lightweight BERT, fast inference, used to break deadlocks
               when primary and secondary strongly disagree.
               Labels: LABEL_0 = FAKE, LABEL_1 = REAL
               Weight: 0.15

Ensemble formula
----------------
    fake_score = 0.50 * primary + 0.35 * secondary + 0.15 * tiebreaker

The tiebreaker is lightweight and slightly less accurate on its own, but
it consistently resolves cases where the two main models produce scores
on opposite sides of 0.5 — previously these always collapsed to
"Uncertain". The result is a more decisive and calibrated final score.

Negation correction
-------------------
Transformer models notoriously ignore negation ("not guilty" ~ "guilty"
in embedding space). When the input contains strong negation words AND
the ensemble score is in the moderate fake zone (0.40-0.70), we apply
a dampening correction that pulls the score toward 0.50 to signal
genuine uncertainty rather than a false confident verdict.

Disagreement signal
-------------------
When the two main models disagree strongly (spread > 0.35), the
returned dict includes model_spread and a high_disagreement flag.
The verdict engine uses this to widen confidence intervals.
"""

from __future__ import annotations

import re
from transformers import pipeline

_sentiment_model  = None
_primary_model    = None   # hamzab/roberta-fake-news-classification
_secondary_model  = None   # jy46604790/Fake-News-Bert-Detect
_tiebreaker_model = None   # mrm8488/bert-tiny-finetuned-fake-news-detection

_NEGATION_RE = re.compile(
    r"\b(not|never|isn'?t|aren'?t|wasn'?t|weren'?t|don'?t|doesn'?t"
    r"|didn'?t|no longer|false that|untrue|incorrect|no evidence"
    r"|has not|have not|had not|cannot|can't|won'?t|wouldn'?t)\b",
    re.IGNORECASE,
)

# Only apply correction when score is in the ambiguous zone
_NEGATION_CORRECTION_MIN = 0.40
_NEGATION_CORRECTION_MAX = 0.70
# How strongly to pull toward 0.5 (0 = no pull, 1 = full pull to 0.5)
_NEGATION_DAMPENING = 0.30

# Models disagree strongly when their scores differ by more than this
_DISAGREEMENT_THRESHOLD = 0.35


def _has_negation(text: str) -> bool:
    return bool(_NEGATION_RE.search(text))


def _apply_negation_correction(score: float) -> float:
    """Pull score toward 0.5 when negation is detected in ambiguous zone."""
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
        # LABEL_0 = FAKE, LABEL_1 = REAL
        _secondary_model = pipeline(
            "text-classification",
            model="jy46604790/Fake-News-Bert-Detect",
            framework="pt",
            truncation=True,
            max_length=512,
        )

    if _tiebreaker_model is None:
        # LABEL_0 = FAKE, LABEL_1 = REAL
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
    """
    Convert a text-classification result to a fake probability (0-1).

    Both models use:
        LABEL_0 / "FAKE" -> FAKE
        LABEL_1 / "REAL" -> REAL
    """
    label: str   = result["label"]
    score: float = float(result["score"])

    if label in ("LABEL_0", "FAKE"):   
        return score
    else:                               
        return 1.0 - score


def analyze_text(text: str) -> dict:
    """
    Analyse *text* and return:

        sentiment          : "POSITIVE" | "NEGATIVE"
        sentiment_score    : float 0-1
        fake_label         : "FAKE" | "REAL"
        fake_score         : float 0-1  (ensemble, negation-corrected)
        primary_score      : float 0-1  (hamzab model)
        secondary_score    : float 0-1  (jy46604790 model)
        tiebreaker_score   : float | None (bert-tiny model)
        model_spread       : float 0-1  (|primary - secondary|)
        high_disagreement  : bool       (spread > threshold)
        negation_detected  : bool       (negation correction applied)
    """
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
        # Full three-model ensemble: 50 / 35 / 15
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
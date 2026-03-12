# nlp_service.py

"""NLP Service — fake-news probability + sentiment.

Models used
-----------
1. Sentiment  : distilbert-base-uncased-finetuned-sst-2-english
               Fast, reliable SST-2 sentiment classifier.

2. Fake-news  : hamzab/roberta-fake-news-classification  (PRIMARY)
               RoBERTa fine-tuned on fake-and-real-news-dataset.
               Labels: LABEL_0 = FAKE, LABEL_1 = REAL

3. Fake-news  : jy46604790/Fake-News-Bert-Detect  (SECONDARY)
               RoBERTa trained on 40,000+ news articles.
               Labels: LABEL_0 = FAKE, LABEL_1 = REAL

Ensemble formula
----------------
    fake_score = 0.60 * primary_fake_prob + 0.40 * secondary_fake_prob

Both models are domain-specific fake news detectors, so we trust them
more equally than the old zero-shot bart model.
"""

from __future__ import annotations

from transformers import pipeline

# ---------------------------------------------------------------------------
# Globals — loaded lazily on first request so startup is fast
# ---------------------------------------------------------------------------
_sentiment_model = None
_primary_fake_model = None    # hamzab/roberta-fake-news-classification
_secondary_fake_model = None  # jy46604790/Fake-News-Bert-Detect


def _get_models():
    global _sentiment_model, _primary_fake_model, _secondary_fake_model

    if _sentiment_model is None:
        _sentiment_model = pipeline(
            "sentiment-analysis",
            model="distilbert/distilbert-base-uncased-finetuned-sst-2-english",
            framework="pt",
        )

    if _primary_fake_model is None:
        # LABEL_0 = FAKE, LABEL_1 = REAL
        _primary_fake_model = pipeline(
            "text-classification",
            model="hamzab/roberta-fake-news-classification",
            framework="pt",
            truncation=True,
            max_length=512,
        )

    if _secondary_fake_model is None:
        # LABEL_0 = FAKE, LABEL_1 = REAL
        _secondary_fake_model = pipeline(
            "text-classification",
            model="jy46604790/Fake-News-Bert-Detect",
            framework="pt",
            truncation=True,
            max_length=512,
        )

    return _sentiment_model, _primary_fake_model, _secondary_fake_model


# ---------------------------------------------------------------------------
# Label helper
# ---------------------------------------------------------------------------

def _to_fake_prob(result: dict) -> float:
    """
    Convert a text-classification result to a fake probability (0-1).

    Both models use:
        LABEL_0 → FAKE
        LABEL_1 → REAL
    """
    label: str = result["label"]
    score: float = float(result["score"])

    if label == "LABEL_0":   # model says FAKE
        return score
    else:                     # model says REAL → invert
        return 1.0 - score


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_text(text: str) -> dict:
    """
    Analyse *text* and return:

        sentiment       : "POSITIVE" | "NEGATIVE"
        sentiment_score : float 0-1
        fake_label      : "FAKE" | "REAL"
        fake_score      : float 0-1  (ensemble)
        primary_score   : float 0-1  (hamzab model, for debugging)
        secondary_score : float 0-1  (jy46604790 model, for debugging)
    """
    sentiment_model, primary_model, secondary_model = _get_models()

    # --- 1. Sentiment ---
    sentiment_result = sentiment_model(text, truncation=True, max_length=512)[0]
    sentiment = sentiment_result["label"]
    sentiment_score = float(sentiment_result["score"])

    # --- 2. Primary fake-news model ---
    primary_result = primary_model(text)[0]
    primary_score = _to_fake_prob(primary_result)

    # --- 3. Secondary fake-news model ---
    try:
        secondary_result = secondary_model(text)[0]
        secondary_score = _to_fake_prob(secondary_result)
    except Exception:
        # If secondary model fails, fall back to primary only
        secondary_score = primary_score

    # --- 4. Ensemble (60/40 — both are domain-specific) ---
    fake_score = 0.60 * primary_score + 0.40 * secondary_score
    fake_label = "FAKE" if fake_score >= 0.5 else "REAL"

    return {
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "fake_label": fake_label,
        "fake_score": round(fake_score, 4),
        "primary_score": round(primary_score, 4),
        "secondary_score": round(secondary_score, 4),
    }
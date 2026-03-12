# text_chunker.py

"""Text chunking service for long articles.

Problem
-------
The ML models (RoBERTa-based) have a hard limit of 512 tokens (~350 words).
A long news article silently gets truncated at token 512, meaning the model
only sees the first ~3 paragraphs and ignores the rest.

Solution
--------
1. Split the article into overlapping chunks of ~300 words each.
2. Score each chunk independently with the ML model.
3. Aggregate chunk scores using a weighted average:
   - Earlier chunks (headline/intro) get slightly higher weight
   - Chunks with higher model confidence get higher weight
   - Result: a single representative fake_score for the whole article

This makes the system work on full news articles, not just short claims.

Chunking strategy
-----------------
- Chunk size  : 300 words  (safely under 512 token limit)
- Overlap     : 50 words   (preserves context across chunk boundaries)
- Max chunks  : 8          (caps latency for very long articles)
- Min length  : 30 words   (skip tiny fragments)
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CHUNK_SIZE    = 300   # words per chunk
CHUNK_OVERLAP = 50    # words of overlap between chunks
MAX_CHUNKS    = 8     # maximum chunks to process (performance cap)
MIN_CHUNK_LEN = 30    # minimum words for a chunk to be processed
SHORT_TEXT_THRESHOLD = 280  # texts shorter than this skip chunking entirely


# ---------------------------------------------------------------------------
# Text splitting
# ---------------------------------------------------------------------------

def _tokenize_words(text: str) -> list[str]:
    """Split text into words, preserving whitespace boundaries."""
    return text.split()


def _split_into_chunks(text: str) -> list[str]:
    """
    Split *text* into overlapping word-based chunks.

    Returns a list of chunk strings. For short texts (under threshold),
    returns the original text as a single-element list.
    """
    words = _tokenize_words(text)

    # Short text — no chunking needed
    if len(words) <= SHORT_TEXT_THRESHOLD:
        return [text]

    chunks = []
    start = 0

    while start < len(words):
        end = start + CHUNK_SIZE
        chunk_words = words[start:end]

        if len(chunk_words) >= MIN_CHUNK_LEN:
            chunks.append(" ".join(chunk_words))

        # Move forward by (CHUNK_SIZE - OVERLAP) to create overlap
        start += CHUNK_SIZE - CHUNK_OVERLAP

        if len(chunks) >= MAX_CHUNKS:
            break

    return chunks if chunks else [text]


# ---------------------------------------------------------------------------
# Score aggregation
# ---------------------------------------------------------------------------

def _position_weight(index: int, total: int) -> float:
    """
    Earlier chunks get more weight.

    Rationale: In news articles, the headline and first paragraphs
    contain the core claim. Later paragraphs are context/quotes.

    Weight curve: 1.0, 0.9, 0.85, 0.80, 0.75, 0.75, ...
    (flattens after the first few chunks)
    """
    weights = [1.0, 0.90, 0.85, 0.80, 0.75, 0.75, 0.75, 0.75]
    if index < len(weights):
        return weights[index]
    return 0.75


def aggregate_chunk_scores(chunk_scores: list[float]) -> float:
    """
    Aggregate a list of per-chunk fake scores into a single score.

    Uses position-weighted average. Chunks with extreme scores
    (very high or very low) pull the result more strongly.

    Parameters
    ----------
    chunk_scores : list of fake_score floats (0-1) per chunk

    Returns
    -------
    float : aggregated fake_score (0-1)
    """
    if not chunk_scores:
        return 0.0

    if len(chunk_scores) == 1:
        return chunk_scores[0]

    total_weight = 0.0
    weighted_sum = 0.0

    for i, score in enumerate(chunk_scores):
        # Confidence weight: scores near 0 or 1 are more reliable
        confidence = abs(score - 0.5) * 2   # 0 at 0.5, 1 at 0 or 1
        confidence_weight = 0.5 + 0.5 * confidence  # range: 0.5 – 1.0

        position_w = _position_weight(i, len(chunk_scores))
        weight = position_w * confidence_weight

        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0:
        return sum(chunk_scores) / len(chunk_scores)

    return round(weighted_sum / total_weight, 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def needs_chunking(text: str) -> bool:
    """Return True if text is long enough to require chunking."""
    return len(_tokenize_words(text)) > SHORT_TEXT_THRESHOLD


def analyze_with_chunking(text: str, analyze_fn) -> dict:
    """
    Analyze *text* using chunking if it is long, otherwise analyze directly.

    Parameters
    ----------
    text       : the input text (any length)
    analyze_fn : callable — your existing analyze_text() function from
                 nlp_service.py. Must return a dict with 'fake_score',
                 'sentiment', 'sentiment_score'.

    Returns
    -------
    dict with same keys as analyze_fn, but fake_score is the aggregated
    score across all chunks. Also includes:
        "chunks_analyzed" : int   — how many chunks were processed
        "chunk_scores"    : list  — individual chunk fake scores
        "was_chunked"     : bool  — whether chunking was applied
    """
    chunks = _split_into_chunks(text)
    was_chunked = len(chunks) > 1

    if not was_chunked:
        # Short text — analyze directly, just add metadata fields
        result = analyze_fn(text)
        result["chunks_analyzed"] = 1
        result["chunk_scores"] = [result["fake_score"]]
        result["was_chunked"] = False
        return result

    # --- Analyze each chunk ---
    chunk_results = []
    chunk_scores  = []

    for chunk in chunks:
        try:
            result = analyze_fn(chunk)
            chunk_results.append(result)
            chunk_scores.append(float(result["fake_score"]))
        except Exception:
            # Skip failed chunks — don't let one bad chunk crash everything
            continue

    if not chunk_results:
        # All chunks failed — fall back to direct analysis of full text
        result = analyze_fn(text[:1000])  # truncate as last resort
        result["chunks_analyzed"] = 0
        result["chunk_scores"] = []
        result["was_chunked"] = False
        return result

    # --- Aggregate scores ---
    aggregated_fake_score = aggregate_chunk_scores(chunk_scores)

    # Use sentiment from the first chunk (most representative — headline/intro)
    first = chunk_results[0]

    return {
        "sentiment":        first["sentiment"],
        "sentiment_score":  first["sentiment_score"],
        "fake_label":       "FAKE" if aggregated_fake_score >= 0.5 else "REAL",
        "fake_score":       aggregated_fake_score,
        # Debug/transparency fields
        "primary_score":    first.get("primary_score", aggregated_fake_score),
        "secondary_score":  first.get("secondary_score", aggregated_fake_score),
        "chunks_analyzed":  len(chunk_results),
        "chunk_scores":     chunk_scores,
        "was_chunked":      True,
    }
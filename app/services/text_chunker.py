# text_chunker.py

from __future__ import annotations

import re

CHUNK_SIZE    = 300   
CHUNK_OVERLAP = 50    
MAX_CHUNKS    = 8     
MIN_CHUNK_LEN = 30    
SHORT_TEXT_THRESHOLD = 280  


def _tokenize_words(text: str) -> list[str]:
    return text.split()


def _split_into_chunks(text: str) -> list[str]:
    words = _tokenize_words(text)

    if len(words) <= SHORT_TEXT_THRESHOLD:
        return [text]

    chunks = []
    start = 0

    while start < len(words):
        end = start + CHUNK_SIZE
        chunk_words = words[start:end]

        if len(chunk_words) >= MIN_CHUNK_LEN:
            chunks.append(" ".join(chunk_words))

        start += CHUNK_SIZE - CHUNK_OVERLAP

        if len(chunks) >= MAX_CHUNKS:
            break

    return chunks if chunks else [text]


def _position_weight(index: int, total: int) -> float:
    weights = [1.0, 0.90, 0.85, 0.80, 0.75, 0.75, 0.75, 0.75]
    if index < len(weights):
        return weights[index]
    return 0.75


def aggregate_chunk_scores(chunk_scores: list[float]) -> float:
    if not chunk_scores:
        return 0.0

    if len(chunk_scores) == 1:
        return chunk_scores[0]

    total_weight = 0.0
    weighted_sum = 0.0

    for i, score in enumerate(chunk_scores):
        confidence = abs(score - 0.5) * 2   
        confidence_weight = 0.5 + 0.5 * confidence  

        position_w = _position_weight(i, len(chunk_scores))
        weight = position_w * confidence_weight

        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0:
        return sum(chunk_scores) / len(chunk_scores)

    return round(weighted_sum / total_weight, 4)


def needs_chunking(text: str) -> bool:
    return len(_tokenize_words(text)) > SHORT_TEXT_THRESHOLD


def analyze_with_chunking(text: str, analyze_fn) -> dict:
    chunks = _split_into_chunks(text)
    was_chunked = len(chunks) > 1

    if not was_chunked:
        result = analyze_fn(text)
        result["chunks_analyzed"] = 1
        result["chunk_scores"] = [result["fake_score"]]
        result["was_chunked"] = False
        return result

    chunk_results = []
    chunk_scores  = []

    for chunk in chunks:
        try:
            result = analyze_fn(chunk)
            chunk_results.append(result)
            chunk_scores.append(float(result["fake_score"]))
        except Exception:
            continue

    if not chunk_results:
        result = analyze_fn(text[:1000])  
        result["chunks_analyzed"] = 0
        result["chunk_scores"] = []
        result["was_chunked"] = False
        return result

    aggregated_fake_score = aggregate_chunk_scores(chunk_scores)

    first = chunk_results[0]

    return {
        "sentiment":        first["sentiment"],
        "sentiment_score":  first["sentiment_score"],
        "fake_label":       "FAKE" if aggregated_fake_score >= 0.5 else "REAL",
        "fake_score":       aggregated_fake_score,
        "primary_score":    first.get("primary_score", aggregated_fake_score),
        "secondary_score":  first.get("secondary_score", aggregated_fake_score),
        "chunks_analyzed":  len(chunk_results),
        "chunk_scores":     chunk_scores,
        "was_chunked":      True,
    }
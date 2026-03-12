# fact_check_service.py

"""Multi-source fact-checking service with contradiction detection.

Sources
-------
1. NewsAPI     — real news articles (requires NEWS_API_KEY env var)
2. Wikipedia   — encyclopedic facts
3. DuckDuckGo  — free web fallback

New in this version
-------------------
- contradiction_score : semantic similarity between the claim and the
  NEGATION of the claim vs the evidence. If evidence strongly supports
  the negation, the claim is likely false.
- entity-aware query builder : keeps named entities (capitalised words)
  in the search query to avoid matching wrong entities (e.g. "Armenia"
  the city in Colombia vs Armenia the country).
"""

from __future__ import annotations

import os
import re
import concurrent.futures
from typing import Optional

import requests
import wikipedia
from sentence_transformers import SentenceTransformer, util

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
_model: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


# ---------------------------------------------------------------------------
# Query builder — entity-aware
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "the", "is", "in", "at", "of", "and", "to", "a", "an", "about",
    "this", "that", "has", "have", "been", "was", "were", "are", "on",
    "for", "with", "from", "by", "as", "it", "its", "be", "or", "but",
    "not", "he", "she", "they", "we", "you", "i", "do", "did", "will",
    "would", "could", "should", "may", "might", "also", "just", "than",
    "then", "there", "their", "what", "which", "who", "how", "when",
    "located", "capital", "country", "city", "place", "region",
}


def _build_query(text: str, max_words: int = 6) -> str:
    """
    Build a search query that prioritises named entities (proper nouns).

    Strategy:
    1. Extract capitalised words first (likely named entities)
    2. Fill remaining slots with meaningful lowercase keywords
    3. Result: query is entity-first, not just first-N-words
    """
    text_clean = re.sub(r"https?://\S+", "", text)
    tokens = re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", text_clean)

    proper_nouns = []
    keywords = []
    seen = set()

    for token in tokens:
        lower = token.lower()
        if lower in seen:
            continue
        seen.add(lower)

        is_proper = token[0].isupper() and len(token) > 1
        is_stop = lower in _STOP_WORDS
        is_short = len(lower) < 3

        if is_proper and not is_stop:
            proper_nouns.append(lower)
        elif not is_stop and not is_short:
            keywords.append(lower)

    # Entity-first ordering
    combined = proper_nouns + keywords
    return " ".join(combined[:max_words])


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------

def _split_sentences(text: str, max_sentences: int = 60) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if len(s.strip()) > 20][:max_sentences]


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

_NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
_NEWSAPI_URL = "https://newsapi.org/v2/everything"


def _fetch_newsapi(query: str) -> list[str]:
    if not _NEWS_API_KEY:
        return []
    try:
        response = requests.get(
            _NEWSAPI_URL,
            params={
                "q": query,
                "language": "en",
                "sortBy": "relevancy",
                "pageSize": 10,
                "apiKey": _NEWS_API_KEY,
            },
            timeout=6,
        )
        data = response.json()
        snippets = []
        for article in data.get("articles", []):
            combined = f"{article.get('title','')}. {article.get('description','')}. {article.get('content','')}"
            snippets.extend(_split_sentences(combined))
        return snippets
    except Exception:
        return []


def _fetch_wikipedia(query: str) -> tuple[list[str], list[str]]:
    try:
        titles = wikipedia.search(query, results=5)
    except Exception:
        return [], []
    sentences = []
    for title in titles:
        try:
            page = wikipedia.page(title)
            sentences.extend(_split_sentences(page.content))
        except Exception:
            continue
    return sentences, titles


def _fetch_duckduckgo(query: str) -> list[str]:
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=5,
            headers={"User-Agent": "FakeNewsDetector/1.0"},
        )
        data = response.json()
        snippets = []
        abstract = data.get("AbstractText", "")
        if abstract:
            snippets.extend(_split_sentences(abstract))
        for topic in data.get("RelatedTopics", []):
            text = topic.get("Text", "")
            if text:
                snippets.extend(_split_sentences(text))
        return snippets
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Semantic scoring
# ---------------------------------------------------------------------------

def _best_match(
    claim_embedding,
    sentences: list[str],
    model: SentenceTransformer,
) -> tuple[float, str]:
    best_score = 0.0
    best_sentence = ""
    for sentence in sentences:
        try:
            emb = model.encode(sentence, convert_to_tensor=True)
            score = float(util.cos_sim(claim_embedding, emb).item())
            if score > best_score:
                best_score = score
                best_sentence = sentence
        except Exception:
            continue
    return best_score, best_sentence


def _build_negation(claim: str) -> str:
    """
    Build a simple negation of the claim for contradiction detection.
    e.g. "Armenia is in South America" → "Armenia is NOT in South America"
    """
    negation_insertions = [
        (r"\b(is|are|was|were)\b", r"\1 not"),
        (r"\b(has|have|had)\b", r"\1 not"),
        (r"\b(located)\b", r"not \1"),
    ]
    negated = claim
    for pattern, replacement in negation_insertions:
        result = re.sub(pattern, replacement, negated, count=1, flags=re.IGNORECASE)
        if result != negated:
            return result
    # Fallback: prepend "It is false that"
    return f"It is false that {claim}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fact_check_claim(claim: str) -> dict:
    """
    Fact-check *claim* against multiple sources.

    Returns
    -------
    {
        "sources"              : list[str]  — source names with data
        "found_sources"        : list[str]  — Wikipedia titles (compat)
        "support_score"        : float      — how well evidence supports claim
        "contradiction_score"  : float      — how well evidence contradicts claim
        "net_support_score"    : float      — support_score - contradiction_score
        "evidence"             : list[str]  — best matching sentence
        "source_used"          : str        — which source had best evidence
        "verdict_hint"         : str        — "SUPPORTED"|"CONTRADICTED"|"UNKNOWN"
    }
    """
    model = _get_model()
    query = _build_query(claim)

    try:
        claim_embedding = model.encode(claim, convert_to_tensor=True)
        negation = _build_negation(claim)
        negation_embedding = model.encode(negation, convert_to_tensor=True)
    except Exception:
        return {
            "sources": [], "found_sources": [],
            "support_score": 0.1, "contradiction_score": 0.0,
            "net_support_score": 0.1,
            "evidence": ["Embedding failed."], "source_used": "none",
            "verdict_hint": "UNKNOWN",
        }

    # Fetch all sources in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_news = executor.submit(_fetch_newsapi, query)
        future_wiki = executor.submit(_fetch_wikipedia, query)
        future_ddg  = executor.submit(_fetch_duckduckgo, query)

        news_sentences              = future_news.result()
        wiki_sentences, wiki_titles = future_wiki.result()
        ddg_sentences               = future_ddg.result()

    # Score each source for SUPPORT (similarity to claim)
    news_score, news_sentence = _best_match(claim_embedding, news_sentences, model)
    wiki_score, wiki_sentence = _best_match(claim_embedding, wiki_sentences, model)
    ddg_score,  ddg_sentence  = _best_match(claim_embedding, ddg_sentences,  model)

    results = [
        (news_score, news_sentence, "NewsAPI"),
        (wiki_score, wiki_sentence, "Wikipedia"),
        (ddg_score,  ddg_sentence,  "DuckDuckGo"),
    ]
    best_score, best_sentence, best_source = max(results, key=lambda x: x[0])

    # Score the same best sentence for CONTRADICTION (similarity to negation)
    contradiction_score = 0.0
    if best_sentence:
        try:
            evidence_embedding = model.encode(best_sentence, convert_to_tensor=True)
            contradiction_score = float(
                util.cos_sim(negation_embedding, evidence_embedding).item()
            )
        except Exception:
            contradiction_score = 0.0

    # Calibration boost for strong matches
    if best_score > 0.5:
        best_score = min(best_score + 0.08, 1.0)

    # Net support = how much more the evidence supports vs contradicts
    net_support = round(best_score - contradiction_score, 4)

    # Verdict hint for the decision engine
    if best_score < 0.3:
        verdict_hint = "UNKNOWN"
    elif net_support > 0.25:
        verdict_hint = "SUPPORTED"
    elif net_support < -0.05 or contradiction_score > best_score:
        verdict_hint = "CONTRADICTED"
    else:
        verdict_hint = "UNKNOWN"

    active_sources = []
    if news_sentences:
        active_sources.append("NewsAPI")
    if wiki_sentences:
        active_sources.append("Wikipedia")
    if ddg_sentences:
        active_sources.append("DuckDuckGo")

    if not best_sentence:
        return {
            "sources": active_sources, "found_sources": wiki_titles,
            "support_score": 0.1, "contradiction_score": 0.0,
            "net_support_score": 0.1,
            "evidence": ["No matching evidence found."],
            "source_used": "none", "verdict_hint": "UNKNOWN",
        }

    return {
        "sources": active_sources,
        "found_sources": wiki_titles,
        "support_score": round(best_score, 4),
        "contradiction_score": round(contradiction_score, 4),
        "net_support_score": net_support,
        "evidence": [best_sentence],
        "source_used": best_source,
        "verdict_hint": verdict_hint,
    }
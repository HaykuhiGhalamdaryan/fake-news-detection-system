# fact_check_service.py

from __future__ import annotations

import os
import re
import concurrent.futures
from typing import Optional

import requests
import wikipedia
from sentence_transformers import SentenceTransformer, util

_model: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


_STOP_WORDS = {
    "the", "is", "in", "at", "of", "and", "to", "a", "an", "about",
    "this", "that", "has", "have", "been", "was", "were", "are", "on",
    "for", "with", "from", "by", "as", "it", "its", "be", "or", "but",
    "not", "he", "she", "they", "we", "you", "i", "do", "did", "will",
    "would", "could", "should", "may", "might", "also", "just", "than",
    "then", "there", "their", "what", "which", "who", "how", "when",
    "located", "capital", "country", "city", "place", "region", "very",
    "standing", "under", "over", "only", "also", "even", "still",
}

_NEGATION_PATTERNS = re.compile(
    r"\b(not|never|isn'?t|aren'?t|wasn'?t|weren'?t|don'?t|doesn'?t"
    r"|didn'?t|no longer|false that|untrue|incorrect)\b",
    re.IGNORECASE,
)


def _claim_has_negation(claim: str) -> bool:
    return bool(_NEGATION_PATTERNS.search(claim))


def _build_query(text: str, max_words: int = 6) -> str:
    text_clean = re.sub(r"https?://\S+", "", text)
    tokens = re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", text_clean)
    proper_nouns, keywords, seen = [], [], set()
    for token in tokens:
        lower = token.lower()
        if lower in seen:
            continue
        seen.add(lower)
        is_proper = token[0].isupper() and len(token) > 1
        if is_proper and lower not in _STOP_WORDS:
            proper_nouns.append(lower)
        elif lower not in _STOP_WORDS and len(lower) >= 3:
            keywords.append(lower)
    return " ".join((proper_nouns + keywords)[:max_words])


def _split_sentences(text: str, max_sentences: int = 60) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if len(s.strip()) > 20][:max_sentences]


_NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")


def _fetch_newsapi(query: str) -> list[str]:
    if not _NEWS_API_KEY:
        return []
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "language": "en", "sortBy": "relevancy",
                    "pageSize": 10, "apiKey": _NEWS_API_KEY},
            timeout=6,
        )
        snippets = []
        for a in r.json().get("articles", []):
            combined = f"{a.get('title', '')}. {a.get('description', '')}. {a.get('content', '')}"
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
            sentences.extend(_split_sentences(wikipedia.page(title).content))
        except Exception:
            continue
    return sentences, titles


def _fetch_duckduckgo(query: str) -> list[str]:
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=5,
            headers={"User-Agent": "FakeNewsDetector/1.0"},
        )
        data = r.json()
        snippets = []
        if data.get("AbstractText"):
            snippets.extend(_split_sentences(data["AbstractText"]))
        for topic in data.get("RelatedTopics", []):
            if topic.get("Text"):
                snippets.extend(_split_sentences(topic["Text"]))
        return snippets
    except Exception:
        return []


_GEO_CONTRADICTIONS = [
    (
        {"south america", "latin america", "colombia", "brazil", "peru",
         "argentina", "chile", "venezuela", "ecuador"},
        {"caucasus", "south caucasus", "transcaucasia", "yerevan",
         "tbilisi", "baku", "georgia", "azerbaijan"}
    ),
    (
        {"north america", "united states", "usa", "canada", "mexico"},
        {"caucasus", "europe", "asia", "africa", "australia", "middle east"}
    ),
    (
        {"western europe", "france", "germany", "spain", "italy"},
        {"caucasus", "central asia", "middle east", "africa"}
    ),
    (
        {"africa", "sub-saharan"},
        {"europe", "asia", "america", "caucasus", "pacific", "scandinavia"}
    ),
    (
        {"australia", "oceania"},
        {"europe", "asia", "america", "africa", "caucasus"}
    ),
]


def _geo_mismatch_penalty(claim: str, evidence: str) -> float:
    claim_lower    = claim.lower()
    evidence_lower = evidence.lower()
    for claim_kws, contra_kws in _GEO_CONTRADICTIONS:
        if any(kw in claim_lower    for kw in claim_kws) and \
           any(kw in evidence_lower for kw in contra_kws):
            return 0.50
    return 0.0


def _extract_proper_nouns(text: str) -> set[str]:
    tokens = re.findall(r"\b[A-Z][a-z]{2,}\b", text)
    return {t.lower() for t in tokens}


def _entity_overlap(claim: str, evidence: str) -> float:
    """Fraction of claim's proper nouns that appear in evidence."""
    claim_entities = _extract_proper_nouns(claim)
    evidence_lower = evidence.lower()
    if not claim_entities:
        return 1.0
    matches = sum(1 for e in claim_entities if e in evidence_lower)
    return matches / len(claim_entities)


def _topic_relevance(claim: str, evidence: str) -> float:
    """
    Fraction of claim's KEY CONTENT WORDS that appear in the evidence.

    This checks whether the evidence is actually about the same topic
    as the claim — not just whether it mentions the same person/entity.

    Example:
      claim    = "Napoleon was very short, standing under 5 feet tall"
      keywords = ["napoleon", "short", "feet", "tall", "standing"]
      evidence = "David managed to persuade him to sit for a portrait in 1798"
      → none of the topic keywords appear → topic_relevance = 0.0 → NOT relevant

      claim    = "Yerevan is the capital of Armenia"
      keywords = ["yerevan", "capital", "armenia"]
      evidence = "Yerevan is the capital and largest city of Armenia"
      → all keywords appear → topic_relevance = 1.0 → relevant ✅
    """
    claim_lower    = claim.lower()
    evidence_lower = evidence.lower()

    words = re.findall(r"\b[a-z]{4,}\b", claim_lower)
    content_words = [w for w in words if w not in _STOP_WORDS]

    if not content_words:
        return 1.0  

    matches = sum(1 for w in content_words if w in evidence_lower)
    return matches / len(content_words)


def _best_match(claim_emb, sentences: list[str], model) -> tuple[float, str]:
    best_score, best_sentence = 0.0, ""
    for s in sentences:
        try:
            score = float(util.cos_sim(
                claim_emb, model.encode(s, convert_to_tensor=True)
            ).item())
            if score > best_score:
                best_score, best_sentence = score, s
        except Exception:
            continue
    return best_score, best_sentence


def fact_check_claim(claim: str) -> dict:
    model        = _get_model()
    query        = _build_query(claim)
    has_negation = _claim_has_negation(claim)

    try:
        claim_emb = model.encode(claim, convert_to_tensor=True)
    except Exception:
        return {
            "sources": [], "found_sources": [], "support_score": 0.1,
            "contradiction_score": 0.0, "net_support_score": 0.1,
            "evidence": ["Embedding failed."], "source_used": "none",
            "verdict_hint": "UNKNOWN", "entity_overlap": 0.0,
            "topic_relevance": 0.0,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        f_news = ex.submit(_fetch_newsapi,    query)
        f_wiki = ex.submit(_fetch_wikipedia,  query)
        f_ddg  = ex.submit(_fetch_duckduckgo, query)
        news_sents              = f_news.result()
        wiki_sents, wiki_titles = f_wiki.result()
        ddg_sents               = f_ddg.result()

    news_score, news_sent = _best_match(claim_emb, news_sents, model)
    wiki_score, wiki_sent = _best_match(claim_emb, wiki_sents, model)
    ddg_score,  ddg_sent  = _best_match(claim_emb, ddg_sents,  model)

    results = [
        (news_score, news_sent, "NewsAPI"),
        (wiki_score, wiki_sent, "Wikipedia"),
        (ddg_score,  ddg_sent,  "DuckDuckGo"),
    ]
    best_score, best_sentence, best_source = max(results, key=lambda x: x[0])

    geo_penalty      = _geo_mismatch_penalty(claim, best_sentence) if best_sentence else 0.0
    entity_overlap   = _entity_overlap(claim, best_sentence)       if best_sentence else 0.0
    topic_relevance  = _topic_relevance(claim, best_sentence)      if best_sentence else 0.0
    entity_penalty   = 0.20 if entity_overlap < 0.40 else 0.0
    contradiction_score = min(geo_penalty + entity_penalty, 0.60)
    net_support      = round(best_score - contradiction_score, 4)

    if best_score < 0.25:
        verdict_hint = "UNKNOWN"

    elif has_negation:
        verdict_hint = "UNKNOWN"

    elif geo_penalty > 0:
        verdict_hint = "CONTRADICTED"

    elif entity_overlap < 0.30:
        verdict_hint = "CONTRADICTED"

    elif topic_relevance < 0.30:
        verdict_hint = "UNKNOWN"

    elif (
        best_score >= 0.75          
        and entity_overlap >= 0.60  
        and topic_relevance >= 0.40 
        and contradiction_score == 0.0
    ):
        verdict_hint = "SUPPORTED"

    elif (
        net_support >= 0.40
        and entity_overlap >= 0.50
        and topic_relevance >= 0.40
    ):
        verdict_hint = "SUPPORTED"

    else:
        verdict_hint = "UNKNOWN"

    active_sources = (
        (["NewsAPI"]    if news_sents else []) +
        (["Wikipedia"]  if wiki_sents else []) +
        (["DuckDuckGo"] if ddg_sents  else [])
    )

    if not best_sentence:
        return {
            "sources": active_sources, "found_sources": wiki_titles,
            "support_score": 0.1, "contradiction_score": 0.0,
            "net_support_score": 0.1, "evidence": ["No evidence found."],
            "source_used": "none", "verdict_hint": "UNKNOWN",
            "entity_overlap": 0.0, "topic_relevance": 0.0,
        }

    return {
        "sources":             active_sources,
        "found_sources":       wiki_titles,
        "support_score":       round(best_score, 4),
        "contradiction_score": round(contradiction_score, 4),
        "net_support_score":   net_support,
        "evidence":            [best_sentence],
        "source_used":         best_source,
        "verdict_hint":        verdict_hint,
        "entity_overlap":      round(entity_overlap, 3),
        "topic_relevance":     round(topic_relevance, 3),
    }
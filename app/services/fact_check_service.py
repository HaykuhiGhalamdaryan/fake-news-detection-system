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


_SOURCE_CREDIBILITY: dict[str, float] = {
    "wikipedia.org": 0.85,
    "duckduckgo.com": 0.70,
    "newsapi.org":   0.70,
    "reuters.com":   0.95,
    "apnews.com":    0.95,
    "bbc.com":       0.92,
    "bbc.co.uk":     0.92,
    "theguardian.com": 0.85,
    "nytimes.com":   0.85,
    "economist.com": 0.88,
    "bloomberg.com": 0.87,
    "nature.com":    0.97,
    "science.org":   0.97,
    "snopes.com":    0.85,
    "factcheck.org": 0.88,
    "politifact.com": 0.82,
    "foxnews.com":   0.60,
    "dailymail.co.uk": 0.40,
    "breitbart.com": 0.20,
    "infowars.com":  0.02,
    "rt.com":        0.20,
}

_DEFAULT_SOURCE_WEIGHT = 0.65  


def _source_weight(source_label: str) -> float:
    """Return a credibility weight (0–1) for a named source."""
    return _SOURCE_CREDIBILITY.get(source_label.lower(), _DEFAULT_SOURCE_WEIGHT)


_NEGATION_FLIP_PAIRS = [
    (re.compile(r"\bisn'?t\b",    re.I), "is"),
    (re.compile(r"\baren'?t\b",   re.I), "are"),
    (re.compile(r"\bwasn'?t\b",   re.I), "was"),
    (re.compile(r"\bweren'?t\b",  re.I), "were"),
    (re.compile(r"\bdon'?t\b",    re.I), "do"),
    (re.compile(r"\bdoesn'?t\b",  re.I), "does"),
    (re.compile(r"\bdidn'?t\b",   re.I), "did"),
    (re.compile(r"\bcan'?t\b",    re.I), "can"),
    (re.compile(r"\bwon'?t\b",    re.I), "will"),
    (re.compile(r"\bwouldn'?t\b", re.I), "would"),
    (re.compile(r"\bno longer\b", re.I), "still"),
    (re.compile(r"\bnot\b",       re.I), ""),
    (re.compile(r"\bnever\b",     re.I), ""),
    (re.compile(r"\buntrue\b",    re.I), "true"),
    (re.compile(r"\bincorrect\b", re.I), "correct"),
    (re.compile(r"\bfalse that\b",re.I), "true that"),
]


def _flip_negation(claim: str) -> str:
    for pattern, replacement in _NEGATION_FLIP_PAIRS:
        flipped = pattern.sub(replacement, claim, count=1).strip()
        flipped = re.sub(r" {2,}", " ", flipped)
        if flipped != claim:
            return flipped
    return claim


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
    claim_lower    = claim.lower()
    evidence_lower = evidence.lower()

    words = re.findall(r"\b[a-z]{4,}\b", claim_lower)
    content_words = [w for w in words if w not in _STOP_WORDS]

    if not content_words:
        return 1.0  

    matches = sum(1 for w in content_words if w in evidence_lower)
    return matches / len(content_words)


def _best_match(claim_emb, sentences: list[str], model,
                source_weight: float = 1.0) -> tuple[float, str]:
    best_score, best_sentence = 0.0, ""
    for s in sentences:
        try:
            raw = float(util.cos_sim(
                claim_emb, model.encode(s, convert_to_tensor=True)
            ).item())
            weighted = raw * source_weight
            if weighted > best_score:
                best_score, best_sentence = weighted, s
        except Exception:
            continue
    return best_score, best_sentence


def fact_check_claim(claim: str) -> dict:
    model        = _get_model()
    has_negation = _claim_has_negation(claim)

    if has_negation:
        search_claim = _flip_negation(claim)
        negation_inverted = True
    else:
        search_claim = claim
        negation_inverted = False

    query = _build_query(search_claim)

    try:
        search_emb = model.encode(search_claim, convert_to_tensor=True)
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

    news_wscore, news_sent = _best_match(
        search_emb, news_sents, model,
        source_weight=_source_weight("newsapi.org")
    )
    wiki_wscore, wiki_sent = _best_match(
        search_emb, wiki_sents, model,
        source_weight=_source_weight("wikipedia.org")
    )
    ddg_wscore, ddg_sent = _best_match(
        search_emb, ddg_sents, model,
        source_weight=_source_weight("duckduckgo.com")
    )

    results = [
        (news_wscore, news_sent, "NewsAPI"),
        (wiki_wscore, wiki_sent, "Wikipedia"),
        (ddg_wscore,  ddg_sent,  "DuckDuckGo"),
    ]
    best_wscore, best_sentence, best_source = max(results, key=lambda x: x[0])

    best_weight = _source_weight(
        "newsapi.org"    if best_source == "NewsAPI"    else
        "wikipedia.org"  if best_source == "Wikipedia"  else
        "duckduckgo.com"
    )
    best_score = round(best_wscore / best_weight, 4) if best_weight else best_wscore

    geo_penalty      = _geo_mismatch_penalty(search_claim, best_sentence) if best_sentence else 0.0
    entity_overlap   = _entity_overlap(search_claim, best_sentence)       if best_sentence else 0.0
    topic_relevance  = _topic_relevance(search_claim, best_sentence)      if best_sentence else 0.0
    entity_penalty   = 0.20 if entity_overlap < 0.40 else 0.0
    contradiction_score = min(geo_penalty + entity_penalty, 0.60)
    net_support      = round(best_score - contradiction_score, 4)

    if best_score < 0.25:
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

    if negation_inverted:
        if verdict_hint == "SUPPORTED":
            verdict_hint = "CONTRADICTED"
        elif verdict_hint == "CONTRADICTED":
            verdict_hint = "SUPPORTED"

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
        "negation_inverted":   negation_inverted,
    }
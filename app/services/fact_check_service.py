# fact_check_service.py

"""Multi-source fact-checking with strong contradiction detection.

Sources: NewsAPI + Wikipedia + DuckDuckGo (parallel fetch)

Contradiction detection
-----------------------
For each candidate evidence sentence we compute TWO similarity scores:

  support_sim      = cosine_sim(claim,    evidence_sentence)
  contradiction_sim = cosine_sim(negation, evidence_sentence)

net = support_sim - contradiction_sim

If the evidence sentence says something like:
  "Armenia is in the South Caucasus, not South America"
then contradiction_sim will be HIGH and net will be negative → CONTRADICTED.

We also apply a geographic/entity mismatch penalty: if the evidence
mentions an explicit geographic contradiction keyword (e.g. the claim
says "South America" but the evidence says "Caucasus" or "Europe"),
we boost the contradiction score directly.
"""

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


# ---------------------------------------------------------------------------
# Query builder — entity-first
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


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

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
            combined = f"{a.get('title','')}. {a.get('description','')}. {a.get('content','')}"
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


# ---------------------------------------------------------------------------
# Negation builder
# ---------------------------------------------------------------------------

def _build_negation(claim: str) -> str:
    """Insert 'not/NOT' into the claim to build its negation."""
    patterns = [
        (r"\b(is|are|was|were)\b",      r"\1 not"),
        (r"\b(has|have|had)\b",          r"\1 not"),
        (r"\b(located)\b",               r"not \1"),
        (r"\b(belongs?)\b",              r"does not belong"),
    ]
    for pat, rep in patterns:
        result = re.sub(pat, rep, claim, count=1, flags=re.IGNORECASE)
        if result != claim:
            return result
    return f"It is false that {claim}"


# ---------------------------------------------------------------------------
# Geographic / entity mismatch detector
# ---------------------------------------------------------------------------

# Map of claim keywords → contradicting evidence keywords
# If claim contains key A but evidence contains value B → contradiction boost
_GEO_CONTRADICTIONS = [
    ({"south america", "latin america", "colombia", "brazil"},
     {"caucasus", "europe", "asia", "middle east", "eurasia", "yerevan"}),
    ({"north america", "united states", "usa", "canada"},
     {"caucasus", "europe", "asia", "africa", "australia"}),
    ({"africa"},
     {"europe", "asia", "america", "caucasus", "pacific"}),
    ({"asia"},
     {"europe", "america", "africa", "pacific"}),
]


def _geo_mismatch_penalty(claim: str, evidence: str) -> float:
    """
    Return an additional contradiction penalty (0-0.3) if the claim's
    geographic keywords are contradicted by the evidence's geography.
    """
    claim_lower    = claim.lower()
    evidence_lower = evidence.lower()

    for claim_keywords, contra_keywords in _GEO_CONTRADICTIONS:
        claim_hit    = any(kw in claim_lower    for kw in claim_keywords)
        evidence_hit = any(kw in evidence_lower for kw in contra_keywords)
        if claim_hit and evidence_hit:
            return 0.25   # strong geographic contradiction

    return 0.0


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _best_match(
    claim_emb,
    sentences: list[str],
    model: SentenceTransformer,
) -> tuple[float, str]:
    best_score, best_sentence = 0.0, ""
    for s in sentences:
        try:
            score = float(util.cos_sim(claim_emb, model.encode(s, convert_to_tensor=True)).item())
            if score > best_score:
                best_score, best_sentence = score, s
        except Exception:
            continue
    return best_score, best_sentence


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fact_check_claim(claim: str) -> dict:
    """
    Returns
    -------
    {
        sources, found_sources, support_score,
        contradiction_score, net_support_score,
        evidence, source_used, verdict_hint
    }
    """
    model = _get_model()
    query = _build_query(claim)

    try:
        claim_emb    = model.encode(claim,              convert_to_tensor=True)
        negation_emb = model.encode(_build_negation(claim), convert_to_tensor=True)
    except Exception:
        return {"sources": [], "found_sources": [], "support_score": 0.1,
                "contradiction_score": 0.0, "net_support_score": 0.1,
                "evidence": ["Embedding failed."], "source_used": "none",
                "verdict_hint": "UNKNOWN"}

    # Fetch all sources in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        f_news = ex.submit(_fetch_newsapi,    query)
        f_wiki = ex.submit(_fetch_wikipedia,  query)
        f_ddg  = ex.submit(_fetch_duckduckgo, query)
        news_sents               = f_news.result()
        wiki_sents, wiki_titles  = f_wiki.result()
        ddg_sents                = f_ddg.result()

    # Find best matching sentence across all sources
    news_score, news_sent = _best_match(claim_emb, news_sents, model)
    wiki_score, wiki_sent = _best_match(claim_emb, wiki_sents, model)
    ddg_score,  ddg_sent  = _best_match(claim_emb, ddg_sents,  model)

    results = [
        (news_score, news_sent, "NewsAPI"),
        (wiki_score, wiki_sent, "Wikipedia"),
        (ddg_score,  ddg_sent,  "DuckDuckGo"),
    ]
    best_score, best_sentence, best_source = max(results, key=lambda x: x[0])

    # Compute contradiction score against best evidence sentence
    contradiction_score = 0.0
    geo_penalty         = 0.0
    if best_sentence:
        try:
            ev_emb = model.encode(best_sentence, convert_to_tensor=True)
            contradiction_score = float(util.cos_sim(negation_emb, ev_emb).item())
        except Exception:
            pass
        # Geographic mismatch penalty
        geo_penalty = _geo_mismatch_penalty(claim, best_sentence)
        contradiction_score = min(contradiction_score + geo_penalty, 1.0)

    # Calibration boost for strong matches
    if best_score > 0.5:
        best_score = min(best_score + 0.08, 1.0)

    net_support = round(best_score - contradiction_score, 4)

    # Determine verdict hint
    if best_score < 0.30:
        verdict_hint = "UNKNOWN"
    elif net_support >= 0.35:
        verdict_hint = "SUPPORTED"
    elif net_support <= -0.03 or geo_penalty > 0:
        verdict_hint = "CONTRADICTED"
    else:
        verdict_hint = "UNKNOWN"

    active_sources = (
        (["NewsAPI"]    if news_sents else []) +
        (["Wikipedia"]  if wiki_sents else []) +
        (["DuckDuckGo"] if ddg_sents  else [])
    )

    if not best_sentence:
        return {"sources": active_sources, "found_sources": wiki_titles,
                "support_score": 0.1, "contradiction_score": 0.0,
                "net_support_score": 0.1, "evidence": ["No evidence found."],
                "source_used": "none", "verdict_hint": "UNKNOWN"}

    return {
        "sources":             active_sources,
        "found_sources":       wiki_titles,
        "support_score":       round(best_score, 4),
        "contradiction_score": round(contradiction_score, 4),
        "net_support_score":   net_support,
        "evidence":            [best_sentence],
        "source_used":         best_source,
        "verdict_hint":        verdict_hint,
    }
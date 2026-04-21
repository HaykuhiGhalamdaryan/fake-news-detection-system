# source_analyzer.py

"""News source credibility analyzer.

Two-layer approach:
  1. Static database  — curated credibility ratings for ~80 known domains.
  2. Domain analysis  — WHOIS-based fallback for unknown domains.
     Checks domain age, registration privacy, TLD suspiciousness.

Returns a SourceAnalysis dict with:
    domain          : str   — extracted domain (e.g. "bbc.com")
    known_source    : bool  — True if domain is in the static database
    credibility     : int   — 0-100 credibility score
    category        : str   — "mainstream" | "tabloid" | "satire" |
                              "conspiracy" | "state-media" | "unknown"
    bias            : str   — "left" | "center-left" | "center" |
                              "center-right" | "right" | "unknown"
    domain_age_days : int   — how old the domain is (-1 if unknown)
    notes           : str   — human-readable explanation
    warning         : str   — warning message if source is suspicious (empty if not)
"""

from __future__ import annotations

import re
import socket
import requests
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Optional

_SOURCE_DB: dict[str, tuple[int, str, str, str]] = {
    "bbc.com":           (92, "mainstream",   "center",       "BBC — UK public broadcaster, strong editorial standards"),
    "bbc.co.uk":         (92, "mainstream",   "center",       "BBC — UK public broadcaster, strong editorial standards"),
    "reuters.com":       (95, "mainstream",   "center",       "Reuters — international wire service, strict factual reporting"),
    "apnews.com":        (95, "mainstream",   "center",       "Associated Press — international wire service"),
    "theguardian.com":   (85, "mainstream",   "center-left",  "The Guardian — established UK broadsheet"),
    "nytimes.com":       (85, "mainstream",   "center-left",  "New York Times — major US newspaper"),
    "washingtonpost.com":(84, "mainstream",   "center-left",  "Washington Post — major US newspaper"),
    "wsj.com":           (84, "mainstream",   "center-right", "Wall Street Journal — major US financial newspaper"),
    "economist.com":     (88, "mainstream",   "center",       "The Economist — respected weekly magazine"),
    "ft.com":            (88, "mainstream",   "center",       "Financial Times — respected financial newspaper"),
    "npr.org":           (87, "mainstream",   "center-left",  "NPR — US public radio, strong editorial standards"),
    "pbs.org":           (87, "mainstream",   "center",       "PBS — US public broadcaster"),
    "cnn.com":           (75, "mainstream",   "center-left",  "CNN — major US cable news network"),
    "foxnews.com":       (60, "mainstream",   "right",        "Fox News — major US cable news, strong editorial slant"),
    "msnbc.com":         (65, "mainstream",   "left",         "MSNBC — US cable news, strong left-leaning coverage"),
    "nbcnews.com":       (80, "mainstream",   "center-left",  "NBC News — major US broadcast network"),
    "abcnews.go.com":    (80, "mainstream",   "center-left",  "ABC News — major US broadcast network"),
    "cbsnews.com":       (80, "mainstream",   "center",       "CBS News — major US broadcast network"),
    "usatoday.com":      (75, "mainstream",   "center",       "USA Today — major US national newspaper"),
    "time.com":          (80, "mainstream",   "center-left",  "Time Magazine — respected US news magazine"),
    "newsweek.com":      (65, "mainstream",   "center",       "Newsweek — US news magazine, quality has varied"),
    "politico.com":      (78, "mainstream",   "center",       "Politico — US political news outlet"),
    "thehill.com":       (75, "mainstream",   "center",       "The Hill — US political news outlet"),
    "axios.com":         (82, "mainstream",   "center",       "Axios — modern US news outlet, fact-focused"),
    "bloomberg.com":     (87, "mainstream",   "center",       "Bloomberg — major financial/business news"),
    "aljazeera.com":     (72, "mainstream",   "center",       "Al Jazeera — Qatar-based international news"),
    "dw.com":            (85, "mainstream",   "center",       "Deutsche Welle — German public international broadcaster"),
    "france24.com":      (83, "mainstream",   "center",       "France 24 — French public international broadcaster"),
    "euronews.com":      (78, "mainstream",   "center",       "Euronews — European multilingual news channel"),
    "independent.co.uk": (74, "mainstream",   "center-left",  "The Independent — UK online newspaper"),
    "telegraph.co.uk":   (78, "mainstream",   "center-right", "The Telegraph — UK broadsheet"),
    "thetimes.co.uk":    (80, "mainstream",   "center-right", "The Times — UK broadsheet"),
    "vice.com":          (60, "mainstream",   "left",         "Vice — US digital media, variable quality"),
    "vox.com":           (72, "mainstream",   "center-left",  "Vox — US explanatory journalism outlet"),
    "theatlantic.com":   (82, "mainstream",   "center-left",  "The Atlantic — respected US magazine"),
    "wired.com":         (82, "mainstream",   "center",       "Wired — respected technology journalism"),

    "nature.com":        (97, "mainstream",   "center",       "Nature — top peer-reviewed scientific journal"),
    "science.org":       (97, "mainstream",   "center",       "Science — top peer-reviewed scientific journal"),
    "scientificamerican.com": (90, "mainstream", "center",    "Scientific American — respected science magazine"),
    "newscientist.com":  (85, "mainstream",   "center",       "New Scientist — respected science news magazine"),
    "snopes.com":        (85, "mainstream",   "center",       "Snopes — established fact-checking website"),
    "factcheck.org":     (88, "mainstream",   "center",       "FactCheck.org — non-partisan fact-checking"),
    "politifact.com":    (82, "mainstream",   "center",       "PolitiFact — Pulitzer Prize-winning fact-checker"),
    "fullfact.org":      (85, "mainstream",   "center",       "Full Fact — UK independent fact-checker"),

    "dailymail.co.uk":   (40, "tabloid",      "right",        "Daily Mail — UK tabloid, frequent sensationalism"),
    "thesun.co.uk":      (35, "tabloid",      "right",        "The Sun — UK tabloid, low factual reliability"),
    "nypost.com":        (45, "tabloid",      "right",        "New York Post — US tabloid"),
    "mirror.co.uk":      (45, "tabloid",      "center-left",  "Daily Mirror — UK tabloid"),
    "express.co.uk":     (35, "tabloid",      "right",        "Daily Express — UK tabloid, frequent misinformation"),
    "theglobeandmail.com":(72,"mainstream",   "center",       "The Globe and Mail — major Canadian newspaper"),

    "theonion.com":      (10, "satire",       "center",       "The Onion — well-known satire website, not real news"),
    "babylonbee.com":    (10, "satire",       "right",        "Babylon Bee — conservative satire website"),
    "clickhole.com":     (10, "satire",       "center",       "ClickHole — satire website"),
    "waterfordwhispersnews.com": (10, "satire", "center",     "Waterford Whispers — Irish satire website"),

    "infowars.com":      (2,  "conspiracy",   "right",        "InfoWars — known misinformation, conspiracy theories"),
    "naturalnews.com":   (3,  "conspiracy",   "right",        "Natural News — known health misinformation"),
    "breitbart.com":     (20, "conspiracy",   "right",        "Breitbart — far-right, frequent misinformation"),
    "zerohedge.com":     (15, "conspiracy",   "right",        "ZeroHedge — frequent financial conspiracy content"),
    "beforeitsnews.com": (2,  "conspiracy",   "unknown",      "Before It's News — known misinformation aggregator"),
    "worldnewsdailyreport.com": (1, "conspiracy", "unknown",  "World News Daily Report — known fake news site"),
    "empirenews.net":    (1,  "conspiracy",   "unknown",      "Empire News — known fake news satire site"),
    "thegatewaypundit.com": (10, "conspiracy", "right",       "The Gateway Pundit — frequent misinformation"),

    "rt.com":            (20, "state-media",  "unknown",      "RT (Russia Today) — Russian state media, known propaganda"),
    "sputniknews.com":   (15, "state-media",  "unknown",      "Sputnik — Russian state media"),
    "xinhuanet.com":     (25, "state-media",  "unknown",      "Xinhua — Chinese state news agency"),
    "globaltimes.cn":    (20, "state-media",  "unknown",      "Global Times — Chinese state media tabloid"),
    "presstv.ir":        (15, "state-media",  "unknown",      "Press TV — Iranian state media"),
    "voanews.com":       (72, "state-media",  "center",       "VOA — US government-funded international broadcaster"),
    "rferl.org":         (70, "state-media",  "center",       "Radio Free Europe — US government-funded, covers Eastern Europe"),
}

_SUSPICIOUS_TLDS = {
    ".xyz", ".top", ".click", ".link", ".info", ".biz",
    ".tk", ".ml", ".ga", ".cf", ".gq",  
    ".news",
}

_TRUSTED_TLDS = {".com", ".org", ".net", ".gov", ".edu", ".co.uk", ".ac.uk"}

def extract_domain(url: str) -> str:
    """Extract the base domain from a URL, stripping www."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""

def _analyze_domain_whois(domain: str) -> dict:
    """
    Attempt to get domain age and registration info via WHOIS.
    Uses the free whois.iana.org API as a lightweight check.
    Falls back gracefully if the query fails or times out.
    """
    result = {
        "domain_age_days": -1,
        "privacy_protected": False,
        "resolves": False,
        "suspicious_tld": False,
        "notes": "",
    }

    try:
        socket.setdefaulttimeout(3)
        socket.gethostbyname(domain)
        result["resolves"] = True
    except Exception:
        result["notes"] = "Domain does not resolve — may not exist"
        return result

    tld = "." + domain.split(".")[-1]
    if tld in _SUSPICIOUS_TLDS:
        result["suspicious_tld"] = True

    try:
        tld_clean = domain.split(".")[-1]
        rdap_url = f"https://rdap.org/domain/{domain}"
        r = requests.get(rdap_url, timeout=5,
                        headers={"User-Agent": "TruthLens/1.0 (academic research)"})
        if r.status_code == 200:
            data = r.json()

            for event in data.get("events", []):
                if event.get("eventAction") == "registration":
                    date_str = event.get("eventDate", "")
                    try:
                        reg_date = datetime.fromisoformat(
                            date_str.replace("Z", "+00:00")
                        )
                        age = (datetime.now(timezone.utc) - reg_date).days
                        result["domain_age_days"] = age
                    except Exception:
                        pass

            entities = data.get("entities", [])
            for entity in entities:
                vcard = entity.get("vcardArray", [])
                if any("privacy" in str(v).lower() or
                       "redacted" in str(v).lower() or
                       "withheld" in str(v).lower()
                       for v in vcard):
                    result["privacy_protected"] = True

    except Exception:
        pass  

    return result

def _score_unknown_domain(domain: str, whois_data: dict) -> tuple[int, str, str]:
    """
    Calculate a credibility score for an unknown domain based on
    domain analysis signals. Returns (score, category, warning).
    """
    score = 50  
    warnings = []
    notes_parts = []

    age = whois_data.get("domain_age_days", -1)
    if age == -1:
        warnings.append("Domain age could not be determined")
        score -= 5
    elif age < 30:
        warnings.append(f"Very new domain — registered only {age} days ago")
        score -= 30
    elif age < 180:
        warnings.append(f"Relatively new domain — registered {age} days ago")
        score -= 15
    elif age < 365:
        score -= 5
        notes_parts.append(f"Domain registered {age} days ago")
    else:
        years = age // 365
        score += min(years * 3, 15) 
        notes_parts.append(f"Established domain — {years} year(s) old")

    if whois_data.get("suspicious_tld"):
        warnings.append("Suspicious top-level domain (TLD) — commonly used for low-quality sites")
        score -= 20

    if whois_data.get("privacy_protected"):
        warnings.append("Domain registration is privacy-protected — owner identity hidden")
        score -= 10

    if not whois_data.get("resolves"):
        warnings.append("Domain does not resolve to a server")
        score -= 40

    score = max(0, min(100, score))

    if score >= 60:
        category = "unknown"
        warning = ""
    elif score >= 35:
        category = "unknown"
        warning = "; ".join(warnings) if warnings else "Limited information available for this source"
    else:
        category = "unknown"
        warning = "This source has multiple credibility risk factors: " + "; ".join(warnings)

    notes = ". ".join(notes_parts) if notes_parts else "Unknown source — no credibility data available"

    return score, category, warning

def _build_result_from_static(domain: str) -> dict:
    """Build response dict from the static database entry."""
    credibility, category, bias, notes = _SOURCE_DB[domain]

    warning = ""
    if category == "satire":
        warning = f"{domain} is a known satire website — content is not real news"
    elif category == "conspiracy":
        warning = f"{domain} is a known misinformation source — treat content with extreme caution"
    elif category == "state-media":
        warning = f"{domain} is state-controlled media — content may reflect government bias"
    elif credibility < 40:
        warning = f"{domain} has a low credibility rating — content should be verified independently"

    return {
        "domain":          domain,
        "known_source":    True,
        "credibility":     credibility,
        "category":        category,
        "bias":            bias,
        "domain_age_days": -1,
        "notes":           notes,
        "warning":         warning,
    }


def _build_result_from_cache(cached) -> dict:
    """Build response dict from a DomainCache ORM object."""
    return {
        "domain":          cached.domain,
        "known_source":    False,
        "credibility":     cached.credibility,
        "category":        cached.category,
        "bias":            "unknown",
        "domain_age_days": cached.domain_age_days,
        "notes":           cached.notes,
        "warning":         cached.warning,
    }


def _build_result_from_whois(domain: str, whois_data: dict,
                              score: int, category: str, warning: str) -> dict:
    """Build response dict from a fresh WHOIS query result."""
    return {
        "domain":          domain,
        "known_source":    False,
        "credibility":     score,
        "category":        category,
        "bias":            "unknown",
        "domain_age_days": whois_data.get("domain_age_days", -1),
        "notes":           whois_data.get("notes") or "Unknown source — credibility estimated from domain analysis",
        "warning":         warning,
    }

def analyze_source(url: str, db=None) -> dict:
    """
    Analyze the credibility of a news source from its URL.

    Parameters
    ----------
    url : str
        The full URL submitted by the user.
    db : SQLAlchemy Session | None
        If provided, enables SQL caching of WHOIS results for unknown domains.
        If None, falls back to live WHOIS query every time (original behaviour).

    Returns
    -------
    {
        "domain"          : str   — base domain
        "known_source"    : bool  — True if in static database
        "credibility"     : int   — 0-100
        "category"        : str   — mainstream/tabloid/satire/conspiracy/state-media/unknown
        "bias"            : str   — left/center-left/center/center-right/right/unknown
        "domain_age_days" : int   — -1 if unknown
        "notes"           : str
        "warning"         : str   — empty string if no warning
    }
    """
    domain = extract_domain(url)

    if not domain:
        return {
            "domain":          "",
            "known_source":    False,
            "credibility":     50,
            "category":        "unknown",
            "bias":            "unknown",
            "domain_age_days": -1,
            "notes":           "Could not extract domain from URL",
            "warning":         "",
        }

    if domain in _SOURCE_DB:
        return _build_result_from_static(domain)

    if db is not None:
        try:
            from app.database.models import DomainCache
            cached = db.query(DomainCache).filter(
                DomainCache.domain == domain
            ).first()
            if cached:
                return _build_result_from_cache(cached)
        except Exception:
            pass  

    whois_data = _analyze_domain_whois(domain)
    score, category, warning = _score_unknown_domain(domain, whois_data)
    result = _build_result_from_whois(domain, whois_data, score, category, warning)

    if db is not None:
        try:
            from app.database.models import DomainCache
            cache_entry = DomainCache(
                domain=domain,
                credibility=score,
                category=category,
                domain_age_days=whois_data.get("domain_age_days", -1),
                notes=result["notes"],
                warning=warning,
            )
            db.add(cache_entry)
            db.commit()
        except Exception:
            db.rollback() 

    return result
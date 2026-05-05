# source_analyzer.py

from __future__ import annotations

import re
import socket
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Optional

import requests
 
_SOURCE_DB: dict[str, dict] = {

    "reuters.com": {
        "credibility": 95,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Reuters — international wire service, strict factual reporting, used by thousands of outlets worldwide",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 100/100",
            "AllSides: Center",
            "RSF: Globally trusted wire service",
        ]
    },
    "apnews.com": {
        "credibility": 95,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Associated Press — international wire service, non-profit, strict factual standards",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 100/100",
            "AllSides: Center",
        ]
    },

    "bbc.com": {
        "credibility": 92,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "BBC — UK public broadcaster, strong editorial standards, global reach",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 96/100",
            "AllSides: Center",
            "RSF: High press freedom rating",
        ]
    },
    "bbc.co.uk": {
        "credibility": 92,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "BBC — UK public broadcaster, strong editorial standards, global reach",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 96/100",
            "AllSides: Center",
        ]
    },
    "npr.org": {
        "credibility": 87,
        "category":    "mainstream",
        "bias":        "center-left",
        "notes":       "NPR — US public radio, strong editorial standards, member-supported",
        "sources":     [
            "MBFC: High factual reporting, Left-Center bias",
            "NewsGuard: 97/100",
            "AllSides: Center-Left",
        ]
    },
    "pbs.org": {
        "credibility": 87,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "PBS — US public broadcaster, editorially independent",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 95/100",
        ]
    },
    "dw.com": {
        "credibility": 85,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Deutsche Welle — German public international broadcaster, editorial independence guaranteed by law",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "RSF: High press freedom",
        ]
    },
    "france24.com": {
        "credibility": 83,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "France 24 — French public international broadcaster",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "RSF: Moderate press freedom",
        ]
    },
    "euronews.com": {
        "credibility": 78,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Euronews — European multilingual news channel, partially public funded",
        "sources":     [
            "MBFC: Mostly Factual, Least Biased",
        ]
    },

    "theguardian.com": {
        "credibility": 85,
        "category":    "mainstream",
        "bias":        "center-left",
        "notes":       "The Guardian — established UK broadsheet, owned by Scott Trust (non-profit)",
        "sources":     [
            "MBFC: High factual reporting, Left-Center bias",
            "NewsGuard: 97/100",
            "AllSides: Center-Left",
        ]
    },
    "nytimes.com": {
        "credibility": 85,
        "category":    "mainstream",
        "bias":        "center-left",
        "notes":       "New York Times — major US newspaper, Pulitzer Prize-winning journalism",
        "sources":     [
            "MBFC: High factual reporting, Left-Center bias",
            "NewsGuard: 97/100",
            "AllSides: Center-Left",
        ]
    },
    "washingtonpost.com": {
        "credibility": 84,
        "category":    "mainstream",
        "bias":        "center-left",
        "notes":       "Washington Post — major US newspaper, strong investigative journalism tradition",
        "sources":     [
            "MBFC: High factual reporting, Left-Center bias",
            "NewsGuard: 97/100",
            "AllSides: Center-Left",
        ]
    },
    "wsj.com": {
        "credibility": 84,
        "category":    "mainstream",
        "bias":        "center-right",
        "notes":       "Wall Street Journal — major US financial newspaper, Pulitzer Prize-winning",
        "sources":     [
            "MBFC: High factual reporting, Right-Center bias",
            "NewsGuard: 97/100",
            "AllSides: Center-Right",
        ]
    },
    "economist.com": {
        "credibility": 88,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "The Economist — respected UK weekly magazine, rigorous editorial standards",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 100/100",
            "AllSides: Center",
        ]
    },
    "ft.com": {
        "credibility": 88,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Financial Times — respected UK financial newspaper, strong editorial standards",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 98/100",
        ]
    },
    "bloomberg.com": {
        "credibility": 87,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Bloomberg — major financial/business news, strong factual reporting",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 97/100",
            "AllSides: Center",
        ]
    },
    "telegraph.co.uk": {
        "credibility": 78,
        "category":    "mainstream",
        "bias":        "center-right",
        "notes":       "The Telegraph — UK broadsheet, conservative editorial stance",
        "sources":     [
            "MBFC: Mostly Factual, Right-Center bias",
            "NewsGuard: 86/100",
            "AllSides: Center-Right",
        ]
    },
    "thetimes.co.uk": {
        "credibility": 80,
        "category":    "mainstream",
        "bias":        "center-right",
        "notes":       "The Times — UK broadsheet, Rupert Murdoch-owned, strong editorial tradition",
        "sources":     [
            "MBFC: Mostly Factual, Right-Center bias",
            "NewsGuard: 91/100",
        ]
    },
    "independent.co.uk": {
        "credibility": 74,
        "category":    "mainstream",
        "bias":        "center-left",
        "notes":       "The Independent — UK online newspaper, no print edition since 2016",
        "sources":     [
            "MBFC: Mostly Factual, Left-Center bias",
            "NewsGuard: 83/100",
        ]
    },
    "theglobeandmail.com": {
        "credibility": 72,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "The Globe and Mail — major Canadian newspaper",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 90/100",
        ]
    },
    "aljazeera.com": {
        "credibility": 72,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Al Jazeera — Qatar-based international news, strong Middle East coverage, some state influence concerns",
        "sources":     [
            "MBFC: Mostly Factual, Left-Center bias",
            "NewsGuard: 76/100",
            "RSF: Moderate press freedom concerns",
        ]
    },

    "nbcnews.com": {
        "credibility": 80,
        "category":    "mainstream",
        "bias":        "center-left",
        "notes":       "NBC News — major US broadcast network news division",
        "sources":     [
            "MBFC: High factual reporting, Left-Center bias",
            "NewsGuard: 94/100",
            "AllSides: Center-Left",
        ]
    },
    "abcnews.go.com": {
        "credibility": 80,
        "category":    "mainstream",
        "bias":        "center-left",
        "notes":       "ABC News — major US broadcast network news division",
        "sources":     [
            "MBFC: High factual reporting, Left-Center bias",
            "NewsGuard: 94/100",
            "AllSides: Center-Left",
        ]
    },
    "cbsnews.com": {
        "credibility": 80,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "CBS News — major US broadcast network news division",
        "sources":     [
            "MBFC: High factual reporting, Left-Center bias",
            "NewsGuard: 95/100",
        ]
    },
    "cnn.com": {
        "credibility": 75,
        "category":    "mainstream",
        "bias":        "center-left",
        "notes":       "CNN — major US cable news network, 24-hour news cycle, some sensationalism",
        "sources":     [
            "MBFC: Mostly Factual, Left-Center bias",
            "NewsGuard: 90/100",
            "AllSides: Center-Left",
        ]
    },
    "foxnews.com": {
        "credibility": 60,
        "category":    "mainstream",
        "bias":        "right",
        "notes":       "Fox News — major US cable news, strong right-leaning editorial slant, mixed factual record",
        "sources":     [
            "MBFC: Mixed factual reporting, Right bias",
            "NewsGuard: 60/100",
            "AllSides: Right",
        ]
    },
    "msnbc.com": {
        "credibility": 65,
        "category":    "mainstream",
        "bias":        "left",
        "notes":       "MSNBC — US cable news, strong left-leaning opinion programming",
        "sources":     [
            "MBFC: Mostly Factual, Left bias",
            "NewsGuard: 80/100",
            "AllSides: Left",
        ]
    },

    "usatoday.com": {
        "credibility": 75,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "USA Today — major US national newspaper, broad general audience",
        "sources":     [
            "MBFC: Mostly Factual, Least Biased",
            "NewsGuard: 88/100",
            "AllSides: Center",
        ]
    },
    "time.com": {
        "credibility": 80,
        "category":    "mainstream",
        "bias":        "center-left",
        "notes":       "Time Magazine — respected US news magazine, strong editorial tradition",
        "sources":     [
            "MBFC: High factual reporting, Left-Center bias",
            "NewsGuard: 93/100",
        ]
    },
    "newsweek.com": {
        "credibility": 65,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Newsweek — US news magazine, editorial quality has varied since 2012 ownership change",
        "sources":     [
            "MBFC: Mostly Factual, Least Biased",
            "NewsGuard: 71/100",
        ]
    },
    "politico.com": {
        "credibility": 78,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Politico — US political news outlet, strong Washington DC coverage",
        "sources":     [
            "MBFC: High factual reporting, Left-Center bias",
            "NewsGuard: 93/100",
            "AllSides: Center",
        ]
    },
    "thehill.com": {
        "credibility": 75,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "The Hill — US political news outlet, covers Congress and White House",
        "sources":     [
            "MBFC: Mostly Factual, Least Biased",
            "NewsGuard: 88/100",
            "AllSides: Center",
        ]
    },
    "axios.com": {
        "credibility": 82,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Axios — modern US news outlet, concise fact-focused reporting",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 96/100",
            "AllSides: Center",
        ]
    },
    "theatlantic.com": {
        "credibility": 82,
        "category":    "mainstream",
        "bias":        "center-left",
        "notes":       "The Atlantic — respected US magazine, long-form journalism, strong editorial tradition",
        "sources":     [
            "MBFC: High factual reporting, Left-Center bias",
            "NewsGuard: 95/100",
        ]
    },
    "vox.com": {
        "credibility": 72,
        "category":    "mainstream",
        "bias":        "center-left",
        "notes":       "Vox — US explanatory journalism outlet, transparent methodology",
        "sources":     [
            "MBFC: Mostly Factual, Left-Center bias",
            "NewsGuard: 83/100",
            "AllSides: Center-Left",
        ]
    },
    "wired.com": {
        "credibility": 82,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Wired — respected technology journalism, Conde Nast publication",
        "sources":     [
            "MBFC: High factual reporting, Left-Center bias",
            "NewsGuard: 92/100",
        ]
    },
    "vice.com": {
        "credibility": 60,
        "category":    "mainstream",
        "bias":        "left",
        "notes":       "Vice — US digital media, variable quality, strong on investigative pieces but inconsistent",
        "sources":     [
            "MBFC: Mostly Factual, Left bias",
            "NewsGuard: 72/100",
        ]
    },

    "nature.com": {
        "credibility": 97,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Nature — top peer-reviewed scientific journal, established 1869, rigorous peer review",
        "sources":     [
            "MBFC: Very High factual reporting",
            "Peer-reviewed journal — highest academic standard",
            "Impact Factor: one of highest in science",
        ]
    },
    "science.org": {
        "credibility": 97,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Science — top peer-reviewed journal, published by AAAS since 1880",
        "sources":     [
            "MBFC: Very High factual reporting",
            "Peer-reviewed journal — highest academic standard",
        ]
    },
    "scientificamerican.com": {
        "credibility": 90,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Scientific American — respected science magazine, peer-reviewed content, founded 1845",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 98/100",
        ]
    },
    "newscientist.com": {
        "credibility": 85,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "New Scientist — respected science news magazine, expert editorial board",
        "sources":     [
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 92/100",
        ]
    },

    "snopes.com": {
        "credibility": 85,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Snopes — established fact-checking website, founded 1994, transparent methodology",
        "sources":     [
            "IFCN: Signatory — meets IFCN code of principles",
            "MBFC: High factual reporting",
            "NewsGuard: 95/100",
        ]
    },
    "factcheck.org": {
        "credibility": 88,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "FactCheck.org — non-partisan fact-checking, run by Annenberg Public Policy Center",
        "sources":     [
            "IFCN: Signatory — meets IFCN code of principles",
            "MBFC: High factual reporting, Least Biased",
            "NewsGuard: 99/100",
        ]
    },
    "politifact.com": {
        "credibility": 82,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "PolitiFact — Pulitzer Prize-winning fact-checker, Tampa Bay Times",
        "sources":     [
            "IFCN: Signatory — meets IFCN code of principles",
            "Pulitzer Prize winner 2009",
            "MBFC: High factual reporting",
            "NewsGuard: 94/100",
        ]
    },
    "fullfact.org": {
        "credibility": 85,
        "category":    "mainstream",
        "bias":        "center",
        "notes":       "Full Fact — UK independent fact-checker, non-partisan charity",
        "sources":     [
            "IFCN: Signatory — meets IFCN code of principles",
            "MBFC: High factual reporting, Least Biased",
        ]
    },

    "dailymail.co.uk": {
        "credibility": 40,
        "category":    "tabloid",
        "bias":        "right",
        "notes":       "Daily Mail — UK tabloid, frequent sensationalism, misleading headlines",
        "sources":     [
            "MBFC: Mixed factual reporting, Right-Center bias",
            "NewsGuard: 56/100",
            "Wikipedia: Reliability disputed by multiple studies",
        ]
    },
    "thesun.co.uk": {
        "credibility": 35,
        "category":    "tabloid",
        "bias":        "right",
        "notes":       "The Sun — UK tabloid, low factual reliability, Rupert Murdoch-owned",
        "sources":     [
            "MBFC: Mixed factual reporting, Right bias",
            "NewsGuard: 49/100",
        ]
    },
    "nypost.com": {
        "credibility": 45,
        "category":    "tabloid",
        "bias":        "right",
        "notes":       "New York Post — US tabloid, Rupert Murdoch-owned, sensationalist style",
        "sources":     [
            "MBFC: Mixed factual reporting, Right bias",
            "NewsGuard: 59/100",
            "AllSides: Right",
        ]
    },
    "mirror.co.uk": {
        "credibility": 45,
        "category":    "tabloid",
        "bias":        "center-left",
        "notes":       "Daily Mirror — UK tabloid, left-leaning, moderate factual reliability",
        "sources":     [
            "MBFC: Mostly Factual, Left-Center bias",
            "NewsGuard: 68/100",
        ]
    },
    "express.co.uk": {
        "credibility": 35,
        "category":    "tabloid",
        "bias":        "right",
        "notes":       "Daily Express — UK tabloid, frequent health misinformation and sensationalism",
        "sources":     [
            "MBFC: Mixed factual reporting, Right bias",
            "NewsGuard: 48/100",
        ]
    },

    "theonion.com": {
        "credibility": 10,
        "category":    "satire",
        "bias":        "center",
        "notes":       "The Onion — well-known American satire website, founded 1988, content is fictional",
        "sources":     [
            "Self-identified satire publication",
            "MBFC: Satire category",
            "Universally recognized as satire",
        ]
    },
    "babylonbee.com": {
        "credibility": 10,
        "category":    "satire",
        "bias":        "right",
        "notes":       "Babylon Bee — conservative Christian satire website, content is fictional",
        "sources":     [
            "Self-identified satire publication",
            "MBFC: Satire category",
        ]
    },
    "clickhole.com": {
        "credibility": 10,
        "category":    "satire",
        "bias":        "center",
        "notes":       "ClickHole — satire website, parodies viral content and clickbait",
        "sources":     [
            "Self-identified satire publication",
            "MBFC: Satire category",
        ]
    },
    "waterfordwhispersnews.com": {
        "credibility": 10,
        "category":    "satire",
        "bias":        "center",
        "notes":       "Waterford Whispers — Irish satire website, content is fictional",
        "sources":     [
            "Self-identified satire publication",
            "MBFC: Satire category",
        ]
    },

    "infowars.com": {
        "credibility": 2,
        "category":    "conspiracy",
        "bias":        "right",
        "notes":       "InfoWars — Alex Jones's conspiracy and misinformation outlet, spreads health and political disinformation",
        "sources":     [
            "MBFC: Very Low factual reporting, Conspiracy-Pseudoscience",
            "NewsGuard: 0/100",
            "Multiple court findings of defamation and misinformation",
            "Banned from multiple social media platforms for misinformation",
        ]
    },
    "naturalnews.com": {
        "credibility": 3,
        "category":    "conspiracy",
        "bias":        "right",
        "notes":       "Natural News — known health misinformation, anti-vaccine content, conspiracy theories",
        "sources":     [
            "MBFC: Very Low factual reporting, Conspiracy-Pseudoscience",
            "NewsGuard: 0/100",
            "Google deindexed site for policy violations (2019)",
        ]
    },
    "breitbart.com": {
        "credibility": 20,
        "category":    "conspiracy",
        "bias":        "right",
        "notes":       "Breitbart — far-right outlet, frequent misinformation, founded by Andrew Breitbart",
        "sources":     [
            "MBFC: Low factual reporting, Extreme Right bias",
            "NewsGuard: 27/100",
            "AllSides: Right",
        ]
    },
    "zerohedge.com": {
        "credibility": 15,
        "category":    "conspiracy",
        "bias":        "right",
        "notes":       "ZeroHedge — frequent financial conspiracy content, anonymous authorship, links to Russian disinformation",
        "sources":     [
            "MBFC: Low factual reporting, Right bias",
            "NewsGuard: 12/100",
            "Stanford Internet Observatory: Identified in disinformation campaigns",
        ]
    },
    "beforeitsnews.com": {
        "credibility": 2,
        "category":    "conspiracy",
        "bias":        "unknown",
        "notes":       "Before It's News — user-generated misinformation aggregator, no editorial oversight",
        "sources":     [
            "MBFC: Very Low factual reporting, Conspiracy-Pseudoscience",
            "NewsGuard: 0/100",
        ]
    },
    "worldnewsdailyreport.com": {
        "credibility": 1,
        "category":    "conspiracy",
        "bias":        "unknown",
        "notes":       "World News Daily Report — known fake news site, fabricates stories entirely",
        "sources":     [
            "MBFC: Very Low — Fake News / Satire",
            "Snopes: Repeatedly debunked",
            "Listed on multiple fake news site databases",
        ]
    },
    "empirenews.net": {
        "credibility": 1,
        "category":    "conspiracy",
        "bias":        "unknown",
        "notes":       "Empire News — known fake news site, fabricates satirical stories presented as real",
        "sources":     [
            "MBFC: Fake News",
            "Listed on multiple fake news site databases",
        ]
    },
    "thegatewaypundit.com": {
        "credibility": 10,
        "category":    "conspiracy",
        "bias":        "right",
        "notes":       "The Gateway Pundit — frequent election misinformation and far-right conspiracy content",
        "sources":     [
            "MBFC: Very Low factual reporting, Extreme Right bias",
            "NewsGuard: 13/100",
            "AllSides: Right",
        ]
    },

    "rt.com": {
        "credibility": 20,
        "category":    "state-media",
        "bias":        "unknown",
        "notes":       "RT (Russia Today) — Russian state media, funded by Russian government, known propaganda outlet",
        "sources":     [
            "MBFC: Low factual reporting, Conspiracy-Pseudoscience",
            "NewsGuard: 18/100",
            "RSF: State-controlled, press freedom violations",
            "EU banned in multiple countries for disinformation",
            "US registered as foreign agent (FARA)",
        ]
    },
    "sputniknews.com": {
        "credibility": 15,
        "category":    "state-media",
        "bias":        "unknown",
        "notes":       "Sputnik — Russian state media news agency, disinformation operations documented",
        "sources":     [
            "MBFC: Low factual reporting",
            "NewsGuard: 14/100",
            "RSF: State-controlled",
            "US registered as foreign agent (FARA)",
        ]
    },
    "xinhuanet.com": {
        "credibility": 25,
        "category":    "state-media",
        "bias":        "unknown",
        "notes":       "Xinhua — Chinese state news agency, official government mouthpiece",
        "sources":     [
            "MBFC: Low factual reporting on political issues",
            "RSF: State-controlled, China ranked very low on press freedom",
            "WJP: Government-controlled media",
        ]
    },
    "globaltimes.cn": {
        "credibility": 20,
        "category":    "state-media",
        "bias":        "unknown",
        "notes":       "Global Times — Chinese state media tabloid, nationalist propaganda",
        "sources":     [
            "MBFC: Low factual reporting, propaganda",
            "NewsGuard: 21/100",
            "RSF: State-controlled",
        ]
    },
    "presstv.ir": {
        "credibility": 15,
        "category":    "state-media",
        "bias":        "unknown",
        "notes":       "Press TV — Iranian state media, English-language propaganda outlet",
        "sources":     [
            "MBFC: Low factual reporting",
            "RSF: State-controlled, Iran ranked very low on press freedom",
            "Banned in UK and Germany",
        ]
    },
    "voanews.com": {
        "credibility": 72,
        "category":    "state-media",
        "bias":        "center",
        "notes":       "VOA (Voice of America) — US government-funded international broadcaster, editorial independence protected by law",
        "sources":     [
            "MBFC: Mostly Factual, Least Biased",
            "NewsGuard: 88/100",
            "Editorial independence mandated by US Broadcasting Board of Governors",
        ]
    },
    "rferl.org": {
        "credibility": 70,
        "category":    "state-media",
        "bias":        "center",
        "notes":       "Radio Free Europe/Radio Liberty — US government-funded, covers Eastern Europe and Central Asia, editorial independence maintained",
        "sources":     [
            "MBFC: Mostly Factual, Least Biased",
            "NewsGuard: 85/100",
            "IFCN: Fact-checking affiliate",
        ]
    },
}

_SUSPICIOUS_TLDS = {
    ".xyz", ".top", ".click", ".link", ".info", ".biz",
    ".tk", ".ml", ".ga", ".cf", ".gq",
    ".news",
}

_TRUSTED_TLDS = {".com", ".org", ".net", ".gov", ".edu", ".co.uk", ".ac.uk"}

def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _analyze_domain_whois(domain: str) -> dict:
    result = {
        "domain_age_days":    -1,
        "privacy_protected":  False,
        "resolves":           False,
        "suspicious_tld":     False,
        "notes":              "",
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
        rdap_url = f"https://rdap.org/domain/{domain}"
        r = requests.get(rdap_url, timeout=5,
                         headers={"User-Agent": "TruthLens/1.0 (academic research)"})
        if r.status_code == 200:
            data = r.json()
            for event in data.get("events", []):
                if event.get("eventAction") == "registration":
                    date_str = event.get("eventDate", "")
                    try:
                        reg_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        age = (datetime.now(timezone.utc) - reg_date).days
                        result["domain_age_days"] = age
                    except Exception:
                        pass
            for entity in data.get("entities", []):
                vcard = entity.get("vcardArray", [])
                if any("privacy"  in str(v).lower() or
                       "redacted" in str(v).lower() or
                       "withheld" in str(v).lower()
                       for v in vcard):
                    result["privacy_protected"] = True
    except Exception:
        pass

    return result


def _score_unknown_domain(domain: str, whois_data: dict) -> tuple[int, str, str]:
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
        warnings.append("Suspicious top-level domain — commonly used for low-quality sites")
        score -= 20

    if whois_data.get("privacy_protected"):
        warnings.append("Domain registration is privacy-protected — owner identity hidden")
        score -= 10

    if not whois_data.get("resolves"):
        warnings.append("Domain does not resolve to a server")
        score -= 40

    score = max(0, min(100, score))

    if score >= 60:
        warning = ""
    elif score >= 35:
        warning = "; ".join(warnings) if warnings else "Limited information available for this source"
    else:
        warning = "This source has multiple credibility risk factors: " + "; ".join(warnings)

    notes = ". ".join(notes_parts) if notes_parts else "Unknown source — credibility estimated from domain analysis"
    return score, "unknown", warning


def _build_result_from_static(domain: str) -> dict:
    entry = _SOURCE_DB[domain]
    credibility = entry["credibility"]
    category    = entry["category"]

    warning = ""
    if category == "satire":
        warning = f"{domain} is a known satire website — content is not real news"
    elif category == "conspiracy":
        warning = f"{domain} is a known misinformation source — treat content with extreme caution"
    elif category == "state-media" and credibility < 50:
        warning = f"{domain} is state-controlled media — content may reflect government bias"
    elif credibility < 40:
        warning = f"{domain} has a low credibility rating — content should be verified independently"

    return {
        "domain":          domain,
        "known_source":    True,
        "credibility":     credibility,
        "category":        category,
        "bias":            entry["bias"],
        "domain_age_days": -1,
        "notes":           entry["notes"],
        "rating_sources":  entry["sources"],
        "warning":         warning,
    }


def _build_result_from_cache(cached) -> dict:
    return {
        "domain":          cached.domain,
        "known_source":    False,
        "credibility":     cached.credibility,
        "category":        cached.category,
        "bias":            "unknown",
        "domain_age_days": cached.domain_age_days,
        "notes":           cached.notes,
        "rating_sources":  [],
        "warning":         cached.warning,
    }


def _build_result_from_whois(domain: str, whois_data: dict,
                              score: int, category: str, warning: str) -> dict:
    return {
        "domain":          domain,
        "known_source":    False,
        "credibility":     score,
        "category":        category,
        "bias":            "unknown",
        "domain_age_days": whois_data.get("domain_age_days", -1),
        "notes":           whois_data.get("notes") or "Unknown source — credibility estimated from domain analysis",
        "rating_sources":  ["RDAP domain analysis — age, TLD, privacy protection"],
        "warning":         warning,
    }


def analyze_source(url: str, db=None) -> dict:
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
            "rating_sources":  [],
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
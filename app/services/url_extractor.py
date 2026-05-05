# url_extractor.py

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

_TIMEOUT      = 10   
_MAX_RETRIES  = 2   
_MAX_TEXT_CHARS = 8000
_USER_AGENT = (
    "Mozilla/5.0 (compatible; TruthLens/1.0; fake-news-detection-research)"
)

_BOILERPLATE_TAGS = [
    "script", "style", "noscript", "nav", "header", "footer",
    "aside", "form", "iframe", "button", "svg", "figure", "figcaption",
    "advertisement", "ads",
]

_BOILERPLATE_PATTERNS = re.compile(
    r"(nav|menu|sidebar|footer|header|cookie|banner|popup|modal"
    r"|newsletter|subscribe|social|share|comment|related|recommend"
    r"|advertisement|promo|widget|breadcrumb)",
    re.IGNORECASE,
)


def _is_boilerplate_element(tag) -> bool:
    if not hasattr(tag, "attrs") or tag.attrs is None:
        return False
    for attr in ("class", "id"):
        value = " ".join(tag.get(attr, []) if isinstance(tag.get(attr), list) else [tag.get(attr, "")])
        if _BOILERPLATE_PATTERNS.search(value):
            return True
    return False


def _extract_article_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "nav", "footer",
                      "header", "aside", "form", "iframe", "button", "svg"]):
        tag.decompose()

    for tag in soup.find_all(True):
        if _is_boilerplate_element(tag):
            tag.decompose()

    for selector in [
        "article",
        '[role="main"]',
        "main",
        ".article-body",
        ".article-content",
        ".story-body",
        ".post-content",
        ".entry-content",
        "#article-body",
        "#content",
    ]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 200:
                return text

    paragraphs = soup.find_all("p")
    text = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
    if len(text) > 200:
        return text

    body = soup.find("body")
    if body:
        return body.get_text(separator=" ", strip=True)

    return soup.get_text(separator=" ", strip=True)


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r" ([.,;:!?])", r"\1", text)
    return text.strip()


def validate_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, "URL must start with http:// or https://"
        if not parsed.netloc:
            return False, "Invalid URL — no domain found"
        return True, ""
    except Exception:
        return False, "Could not parse URL"


def is_homepage_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')

        if not path or path == '':
            return True

        segments = [s for s in path.split('/') if s]

        if len(segments) == 1:
            seg = segments[0]
            if len(seg) < 20 and '-' not in seg and not any(c.isdigit() for c in seg):
                return True

        if len(segments) == 2:
            s1, s2 = segments
            if (len(s1) < 20 and len(s2) < 20
                    and '-' not in s1 and '-' not in s2
                    and not any(c.isdigit() for c in s1 + s2)):
                return True

        if any(s.isdigit() and len(s) == 4 and s.startswith(('19', '20')) for s in segments):
            return False

        if any(len(s) > 30 and '-' in s for s in segments):
            return False

        if any(s in ('articles', 'article', 'story', 'stories', 'post', 'posts')
               for s in segments[:-1]):
            return False

        return False
    except Exception:
        return False

def extract_text_from_url(url: str) -> dict:
    is_valid, err = validate_url(url)
    if not is_valid:
        return {"success": False, "text": "", "title": "", "url": url,
                "word_count": 0, "is_likely_listing": False, "listing_warning": "", "error": err}

    _fail_result = {"success": False, "text": "", "title": "", "url": url,
                    "word_count": 0, "is_likely_listing": False, "listing_warning": ""}

    last_error = ""
    response   = None

    for attempt in range(_MAX_RETRIES):
        try:
            response = requests.get(
                url,
                timeout=_TIMEOUT,
                headers={
                    "User-Agent":      _USER_AGENT,
                    "Accept":          "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                allow_redirects=True,
            )
            response.raise_for_status()
            break   

        except requests.exceptions.Timeout:
            last_error = f"Request timed out after {_TIMEOUT} seconds"
        except requests.exceptions.ConnectionError:
            last_error = "Could not connect to the URL"
        except requests.exceptions.HTTPError as e:
            last_error = f"HTTP error: {e.response.status_code}"
            return {**_fail_result, "error": last_error}
        except Exception as e:
            last_error = str(e)

        if attempt + 1 < _MAX_RETRIES:
            import time
            time.sleep(1)

    if response is None:
        return {**_fail_result, "error": last_error}

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        return {"success": False, "text": "", "title": "", "url": url,
                "word_count": 0, "is_likely_listing": False, "listing_warning": "", "error": f"URL returned non-HTML content: {content_type}"}

    soup = BeautifulSoup(response.text, "html.parser")

    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "")

    raw_text = _extract_article_text(soup)
    text = _clean_text(raw_text)

    if len(text) > _MAX_TEXT_CHARS:
        text = text[:_MAX_TEXT_CHARS]

    if len(text) < 50:
        return {
            "success":           False,
            "text":              text,
            "title":             title,
            "url":               response.url,
            "word_count":        len(text.split()) if text else 0,
            "is_likely_listing": True,
            "listing_warning":   (
                "Very little text was extracted from this page. "
                "It may be a homepage, paywalled, or blocking scrapers. "
                "Try a direct article URL instead."
            ),
            "error": "Could not extract meaningful text from this page",
        }

    word_count = len(text.split())

    sentences = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 3]
    is_likely_listing = False
    listing_warning = ""

    if sentences:
        avg_sentence_len = sum(len(s.split()) for s in sentences) / len(sentences)
        short_sentence_ratio = sum(1 for s in sentences if len(s.split()) < 8) / len(sentences)

        if avg_sentence_len < 12 and short_sentence_ratio > 0.6:
            is_likely_listing = True
            listing_warning = (
                "This URL looks like a homepage or listing page rather than a single article. "
                "Results may be less accurate. Try copying the URL of a specific article instead."
            )
        elif word_count < 150:
            is_likely_listing = True
            listing_warning = (
                "Very little text was extracted from this page. "
                "It may be paywalled, a homepage, or a page that blocks scrapers. "
                "Try a direct article URL instead."
            )

    return {
        "success":           True,
        "text":              text,
        "title":             title,
        "url":               response.url,
        "word_count":        word_count,
        "error":             "",
        "is_likely_listing": is_likely_listing,
        "listing_warning":   listing_warning,
    }
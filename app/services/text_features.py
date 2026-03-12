# text_features.py

"""Text Feature Analysis Service.

Detects surface-level manipulation signals that are common in fake news:

    1. ALL CAPS ratio          — shouting / panic inducing
    2. Excessive punctuation   — "!!!", "???" patterns
    3. Clickbait phrases       — "you won't believe", "shocking truth", etc.
    4. Hyperbolic language     — "best ever", "worst in history", "100% proven"
    5. Vague attribution       — "sources say", "people are saying", "experts claim"
    6. Numerical exaggeration  — "millions of people", "thousands dead"
    7. Title case abuse        — Every Single Word Capitalised In A Sentence

Each signal contributes a weighted penalty to a final `manipulation_score`
(0.0 – 1.0). The score and detected signals are returned to the caller so
the verdict engine and explanation engine can use them.

This module is intentionally fast (regex only, no ML models) so it adds
negligible latency to each request.
"""

from __future__ import annotations

import re
import string


# ---------------------------------------------------------------------------
# Signal definitions
# ---------------------------------------------------------------------------

# Clickbait phrases — ordered roughly by severity
CLICKBAIT_PHRASES = [
    "you won't believe",
    "what they don't want you to know",
    "they don't want you to see",
    "the truth they hide",
    "doctors hate",
    "one weird trick",
    "this changes everything",
    "share before it's deleted",
    "share before they delete",
    "before it gets removed",
    "wake up people",
    "open your eyes",
    "do your research",
    "the mainstream media won't tell you",
    "mainstream media is hiding",
    "what the government doesn't want",
    "what they're not telling you",
    "breaking news",
    "shocking truth",
    "the real truth",
    "secret they hide",
    "exposed finally",
    "must watch",
    "must read",
    "going viral",
    "100% proof",
    "undeniable proof",
    "absolute proof",
]

# Hyperbolic superlatives
HYPERBOLIC_PATTERNS = [
    r"\bbiggest (ever|in history|of all time)\b",
    r"\bworst (ever|in history|of all time)\b",
    r"\bbest (ever|in history|of all time)\b",
    r"\b100\s*%\s*(proven|confirmed|true|real|fact)\b",
    r"\bcompletely (fake|false|fabricated|proven|confirmed)\b",
    r"\babsolutely (proven|confirmed|fake|false)\b",
    r"\bundeniable (fact|proof|evidence|truth)\b",
    r"\birrefutable (proof|evidence|fact)\b",
    r"\bscientists (hate|fear|don't want)\b",
    r"\bexperts (hate|fear|are shocked)\b",
]

# Vague attribution — claims without verifiable sources
VAGUE_ATTRIBUTION_PATTERNS = [
    r"\bsome people (say|think|believe|claim)\b",
    r"\bpeople are saying\b",
    r"\beveryone (knows|is saying|agrees)\b",
    r"\bsources say\b",
    r"\bmany people (say|think|believe|feel)\b",
    r"\bthey say\b",
    r"\bword is\b",
    r"\bI heard\b",
    r"\bapparently\b",
    r"\brumors? (say|suggest|indicate)\b",
    r"\baccording to (anonymous|unnamed|secret) sources?\b",
]

# Numerical exaggeration markers
NUMERICAL_EXAGGERATION_PATTERNS = [
    r"\b(millions|billions|thousands) of (people|lives|deaths|victims)\b",
    r"\b\d+\s*%\s*of (all|every|most)\b",
    r"\bover \d{6,}\b",   # "over 1,000,000" style numbers
]


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def _caps_ratio(text: str) -> float:
    """Fraction of alphabetic characters that are uppercase."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def _excessive_punctuation(text: str) -> bool:
    """True if the text contains 3+ consecutive identical punctuation marks."""
    return bool(re.search(r"[!?]{3,}", text))


def _punctuation_density(text: str) -> float:
    """Ratio of exclamation/question marks to total characters."""
    if not text:
        return 0.0
    count = sum(1 for c in text if c in "!?")
    return count / len(text)


def _is_title_case_abuse(text: str) -> bool:
    """
    Detect every-word capitalisation in a sentence that is NOT a proper title.
    Heuristic: ≥ 6 words and ≥ 80 % of words start with a capital letter.
    """
    words = text.split()
    if len(words) < 6:
        return False
    capitalised = sum(1 for w in words if w and w[0].isupper())
    return (capitalised / len(words)) >= 0.80


def _find_phrases(text_lower: str, phrases: list[str]) -> list[str]:
    """Return which phrases from the list appear in text_lower."""
    return [p for p in phrases if p in text_lower]


def _find_patterns(text_lower: str, patterns: list[str]) -> list[str]:
    """Return which regex patterns match in text_lower."""
    return [p for p in patterns if re.search(p, text_lower)]


# ---------------------------------------------------------------------------
# Scoring weights
# Each signal contributes this much to the raw manipulation score (0-1 sum)
# ---------------------------------------------------------------------------

WEIGHTS = {
    "high_caps_ratio":            0.20,
    "excessive_punctuation":      0.15,
    "high_punctuation_density":   0.10,
    "title_case_abuse":           0.10,
    "clickbait_phrase":           0.15,   # per phrase, capped at 0.30
    "hyperbolic_language":        0.12,   # per match, capped at 0.24
    "vague_attribution":          0.10,   # per match, capped at 0.20
    "numerical_exaggeration":     0.08,   # per match, capped at 0.16
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_text_features(text: str) -> dict:
    """
    Analyse surface-level manipulation signals in *text*.

    Returns
    -------
    {
        "manipulation_score"  : float 0-1   overall signal strength
        "manipulation_level"  : str         "LOW" | "MEDIUM" | "HIGH"
        "signals"             : list[str]   machine-readable signal tags
        "details"             : dict        human-readable breakdown
        "clickbait_phrases"   : list[str]   matched clickbait phrases
        "hyperbolic_matches"  : list[str]   matched hyperbole patterns
        "vague_attributions"  : list[str]   matched vague attribution patterns
    }
    """
    text_lower = text.lower()
    raw_score = 0.0
    signals: list[str] = []
    details: dict = {}

    # --- 1. ALL CAPS ratio ---
    caps = _caps_ratio(text)
    details["caps_ratio"] = round(caps, 3)
    if caps > 0.5:
        raw_score += WEIGHTS["high_caps_ratio"]
        signals.append("HIGH_CAPS_RATIO")
    elif caps > 0.3:
        raw_score += WEIGHTS["high_caps_ratio"] * 0.5
        signals.append("MODERATE_CAPS_RATIO")

    # --- 2. Excessive punctuation (!!!, ???) ---
    if _excessive_punctuation(text):
        raw_score += WEIGHTS["excessive_punctuation"]
        signals.append("EXCESSIVE_PUNCTUATION")

    # --- 3. High punctuation density ---
    punct_density = _punctuation_density(text)
    details["punctuation_density"] = round(punct_density, 4)
    if punct_density > 0.05:
        raw_score += WEIGHTS["high_punctuation_density"]
        signals.append("HIGH_PUNCTUATION_DENSITY")

    # --- 4. Title case abuse ---
    if _is_title_case_abuse(text):
        raw_score += WEIGHTS["title_case_abuse"]
        signals.append("TITLE_CASE_ABUSE")

    # --- 5. Clickbait phrases ---
    clickbait_found = _find_phrases(text_lower, CLICKBAIT_PHRASES)
    details["clickbait_phrases"] = clickbait_found
    if clickbait_found:
        penalty = min(len(clickbait_found) * WEIGHTS["clickbait_phrase"], 0.30)
        raw_score += penalty
        signals.append("CLICKBAIT_LANGUAGE")

    # --- 6. Hyperbolic language ---
    hyperbolic_found = _find_patterns(text_lower, HYPERBOLIC_PATTERNS)
    details["hyperbolic_matches"] = hyperbolic_found
    if hyperbolic_found:
        penalty = min(len(hyperbolic_found) * WEIGHTS["hyperbolic_language"], 0.24)
        raw_score += penalty
        signals.append("HYPERBOLIC_LANGUAGE")

    # --- 7. Vague attribution ---
    vague_found = _find_patterns(text_lower, VAGUE_ATTRIBUTION_PATTERNS)
    details["vague_attributions"] = vague_found
    if vague_found:
        penalty = min(len(vague_found) * WEIGHTS["vague_attribution"], 0.20)
        raw_score += penalty
        signals.append("VAGUE_ATTRIBUTION")

    # --- 8. Numerical exaggeration ---
    numerical_found = _find_patterns(text_lower, NUMERICAL_EXAGGERATION_PATTERNS)
    details["numerical_exaggerations"] = numerical_found
    if numerical_found:
        penalty = min(len(numerical_found) * WEIGHTS["numerical_exaggeration"], 0.16)
        raw_score += penalty
        signals.append("NUMERICAL_EXAGGERATION")

    # --- Final score: clamp to 0-1 ---
    manipulation_score = round(min(raw_score, 1.0), 4)

    # --- Level classification ---
    if manipulation_score >= 0.50:
        manipulation_level = "HIGH"
    elif manipulation_score >= 0.25:
        manipulation_level = "MEDIUM"
    else:
        manipulation_level = "LOW"

    return {
        "manipulation_score":  manipulation_score,
        "manipulation_level":  manipulation_level,
        "signals":             signals,
        "details":             details,
        "clickbait_phrases":   clickbait_found,
        "hyperbolic_matches":  hyperbolic_found,
        "vague_attributions":  vague_found,
    }


def get_manipulation_score_contribution(manipulation_score: float) -> float:
    """
    Convert manipulation_score into a fake_score contribution (0-1).

    Used by the verdict engine to blend text features into the final score.
    Scaled so even a HIGH manipulation score only nudges — never dominates.

        manipulation_score 0.0  →  contribution 0.00
        manipulation_score 0.5  →  contribution 0.15
        manipulation_score 1.0  →  contribution 0.25
    """
    return round(min(manipulation_score * 0.25, 0.25), 4)
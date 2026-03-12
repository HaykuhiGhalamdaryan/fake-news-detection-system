# emotion_detector.py

"""Emotion and manipulation pattern detector.

Uses regex patterns (not simple substring match) so that variations like
"government is hiding", "hiding the truth", "they are hiding" all match
the same underlying manipulation signal.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Regex-based manipulation patterns
# Each entry: (pattern_string, display_name)
# ---------------------------------------------------------------------------
MANIPULATION_PATTERNS = [
    # Conspiracy / cover-up language
    (r"\bsecret(ly)?\b",                          "secret"),
    (r"\bhidden\s+truth\b",                       "hidden truth"),
    (r"\bthey\s+(don'?t|do\s+not)\s+want\s+you", "they don't want you to know"),
    (r"\b(government|govt|state).{0,20}hiding\b", "government hiding"),
    (r"\bhiding\s+the\s+(truth|facts?|reality)\b","government hiding"),
    (r"\bcover.?up\b",                            "cover up"),
    (r"\bexposed\b",                              "exposed"),
    (r"\bshocking\b",                             "shocking"),
    (r"\bmainstream\s+media.{0,20}(lies?|lying|fake|false)\b",
                                                  "mainstream media lies"),
    (r"\bwake\s+up\b",                            "wake up"),
    (r"\bopen\s+your\s+eyes\b",                   "open your eyes"),
    (r"\bdo\s+your\s+(own\s+)?research\b",        "do your research"),
    (r"\bthey('re|\s+are)\s+hiding\b",            "government hiding"),
    (r"\bthe\s+(truth|facts?)\s+(they|that).{0,20}hide\b",
                                                  "hidden truth"),
    (r"\bwhat\s+(they|the\s+(government|media)).{0,20}(hide|hiding|won'?t\s+tell)\b",
                                                  "government hiding"),
]

# Emotional trigger words (kept for detect_emotional_language)
EMOTIONAL_WORDS = [
    "shocking", "secret", "hidden", "truth", "exposed", "breaking",
    "urgent", "cover-up", "conspiracy", "hiding", "scandal", "lies",
    "they don't want you to know",
]


def detect_patterns(text: str) -> dict:
    """
    Detect manipulation phrases using regex and classify tone.

    Returns
    -------
    {
        "tone"              : "emotional" | "neutral"
        "detected_patterns" : list of matched display names (deduplicated)
    }
    """
    text_lower = text.lower()
    found = []
    seen = set()

    for pattern, display_name in MANIPULATION_PATTERNS:
        if display_name in seen:
            continue
        if re.search(pattern, text_lower):
            found.append(display_name)
            seen.add(display_name)

    tone = "emotional" if found else "neutral"

    return {
        "tone": tone,
        "detected_patterns": found,
    }


def detect_emotional_language(text: str) -> list[str]:
    """Return emotional trigger words detected in the input text."""
    detected = []
    text_lower = text.lower()
    seen = set()

    for word in EMOTIONAL_WORDS:
        if word in text_lower and word not in seen:
            detected.append(word)
            seen.add(word)

    return detected
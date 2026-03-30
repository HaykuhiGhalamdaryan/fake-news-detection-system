#llm_reasoning.py

from __future__ import annotations

import re

from app.services.emotion_detector import detect_emotional_language

STRONG_CLAIM_PATTERNS = [
    r"\beveryone knows\b",
    r"\bwithout doubt\b",
    r"\bno one is telling you\b",
    r"\bthe truth they hide\b",
    r"\bthis proves\b",
]


def llm_analyze(text: str):
    """
    Performs reasoning-based analysis of a claim.
    Returns:
        {
            "reasoning": "...",
            "detected_patterns": [],
            "tone": "neutral/emotional/sensational"
        }
    """
    detected_patterns = []

    emotional_hits = detect_emotional_language(text)
    lowered = text.lower()
    strong_claim_hits = [
        pattern for pattern in STRONG_CLAIM_PATTERNS if re.search(pattern, lowered)
    ]

    if emotional_hits:
        detected_patterns.append("EMOTIONAL_LANGUAGE")
    if strong_claim_hits:
        detected_patterns.append("STRONG_CLAIMS")

    if emotional_hits:
        tone = "emotional"
    else:
        tone = "neutral"

    if not detected_patterns:
        reasoning = (
            "The claim appears linguistically neutral and does not show strong "
            "misinformation-style rhetoric."
        )
    else:
        reasons = []
        if emotional_hits:
            reasons.append("emotionally charged keywords were detected")
        if strong_claim_hits:
            reasons.append("overconfident claim patterns were identified")
        reasoning = "The claim shows risk signals because " + ", ".join(reasons) + "."

    return {
        "reasoning": reasoning,
        "detected_patterns": detected_patterns,
        "tone": tone,
    }

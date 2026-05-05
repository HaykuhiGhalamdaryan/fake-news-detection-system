# translation_service.py

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_ARMENIAN_LANGS = {"hy"}   

def detect_language(text: str) -> str:
    try:
        from langdetect import detect, LangDetectException
        sample = text[:500].strip()
        if not sample:
            return "en"
        lang = detect(sample)
        return lang
    except Exception as e:
        logger.warning("Language detection failed: %s — assuming English", e)
        return "en"


def is_armenian(text: str) -> bool:
    armenian_chars = sum(1 for c in text[:200] if "\u0530" <= c <= "\u058F")
    if armenian_chars >= 5:
        return True
    return detect_language(text) in _ARMENIAN_LANGS


_translator = None   
_MAX_CHUNK_TOKENS = 400   


def _get_translator():
    global _translator
    if _translator is None:
        try:
            from transformers import pipeline as hf_pipeline
            logger.info("Loading Helsinki-NLP/opus-mt-hy-en translation model…")
            _translator = hf_pipeline(
                "translation",
                model="Helsinki-NLP/opus-mt-hy-en",
                max_length=512,
            )
            logger.info("Translation model loaded.")
        except Exception as e:
            logger.error("Failed to load translation model: %s", e)
            raise RuntimeError(
                "Translation model could not be loaded. "
                "Make sure transformers and sentencepiece are installed."
            ) from e
    return _translator


def _split_into_chunks(text: str, max_words: int = _MAX_CHUNK_TOKENS) -> list[str]:
    import re
    sentences = re.split(r"(?<=[։\.!\?])\s+", text.strip())

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for sentence in sentences:
        words = sentence.split()
        if current_words + len(words) > max_words and current:
            chunks.append(" ".join(current))
            current = []
            current_words = 0
        current.extend(words)
        current_words += len(words)

    if current:
        chunks.append(" ".join(current))

    return chunks or [text]


def translate_hy_to_en(text: str) -> dict:
    if not text.strip():
        return {
            "translated_text": text,
            "original_lang": "hy",
            "was_translated": False,
            "chunk_count": 0,
            "error": "Empty text",
        }

    try:
        translator = _get_translator()
        chunks = _split_into_chunks(text)
        translated_chunks: list[str] = []

        for chunk in chunks:
            result = translator(chunk)
            translated_chunks.append(result[0]["translation_text"])

        translated = " ".join(translated_chunks)

        logger.info(
            "Translated %d chars (%d chunks) from Armenian to English.",
            len(text), len(chunks),
        )

        return {
            "translated_text": translated,
            "original_lang": "hy",
            "was_translated": True,
            "chunk_count": len(chunks),
            "error": "",
        }

    except Exception as e:
        logger.error("Translation failed: %s", e)
        return {
            "translated_text": text,   
            "original_lang": "hy",
            "was_translated": False,
            "chunk_count": 0,
            "error": str(e),
        }


def maybe_translate(text: str) -> dict:
    if is_armenian(text):
        result = translate_hy_to_en(text)
        return {
            "text":              result["translated_text"],
            "was_translated":    result["was_translated"],
            "original_lang":     result["original_lang"],
            "translation_error": result["error"],
        }

    return {
        "text":              text,
        "was_translated":    False,
        "original_lang":     detect_language(text),
        "translation_error": "",
    }
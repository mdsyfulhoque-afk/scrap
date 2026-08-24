"""Phase 2: Deterministic language detection."""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class LanguageDetectionError(Exception):
    """Language detection errors."""
    def __init__(self, category: str, message: str):
        self.category = category
        super().__init__(message)


@dataclass
class LanguageResult:
    """Result of language detection."""
    language: str
    confidence: str
    method: str
    method_version: str
    warnings: list[str]
    errors: list[str]


# Character bigram profiles for common languages (deterministic, CPU-first)
_LANGUAGE_PROFILES: dict[str, dict[str, float]] = {
    "en": {
        "th": 3.56, "he": 3.07, "in": 2.43, "er": 2.05, "an": 1.99,
        "re": 1.85, "on": 1.76, "at": 1.49, "en": 1.45, "nd": 1.44,
        "ti": 1.34, "es": 1.28, "or": 1.24, "te": 1.20, "of": 1.17,
        "ed": 1.17, "is": 1.13, "it": 1.12, "al": 1.09, "ar": 1.07,
        "st": 1.05, "to": 1.04, "nt": 1.04, "ng": 0.95, "se": 0.93,
        "ha": 0.93, "as": 0.87, "ou": 0.87, "io": 0.83, "le": 0.83,
        "ve": 0.83, "co": 0.79, "me": 0.79, "de": 0.76, "hi": 0.76,
        "ri": 0.73, "ro": 0.73, "ic": 0.71, "ne": 0.71, "ea": 0.71,
        "ra": 0.69, "ce": 0.69, "li": 0.68, "ch": 0.68, "ll": 0.67,
        "be": 0.64, "ma": 0.63, "si": 0.61, "om": 0.60, "ur": 0.59,
    },
    "es": {
        "es": 3.71, "de": 2.51, "en": 2.13, "el": 1.91, "la": 1.86,
        "os": 1.62, "on": 1.51, "co": 1.48, "as": 1.40, "er": 1.37,
        "an": 1.36, "re": 1.32, "or": 1.29, "al": 1.27, "ta": 1.24,
        "it": 1.20, "ue": 1.16, "lo": 1.15, "qu": 1.12, "no": 1.10,
        "ac": 1.09, "ad": 1.07, "ci": 1.06, "pa": 1.06, "ar": 1.05,
        "tr": 1.04, "un": 1.03, "ri": 1.03, "to": 1.02, "nt": 1.00,
        "io": 0.99, "ha": 0.98, "se": 0.95, "na": 0.94, "po": 0.93,
        "so": 0.90, "te": 0.90, "di": 0.88, "pr": 0.87, "ch": 0.85,
    },
    "fr": {
        "es": 3.15, "en": 2.63, "le": 2.37, "de": 2.35, "on": 2.31,
        "an": 1.99, "ou": 1.84, "la": 1.71, "ai": 1.69, "is": 1.63,
        "re": 1.53, "et": 1.48, "er": 1.43, "qu": 1.40, "it": 1.38,
        "ar": 1.35, "at": 1.33, "te": 1.32, "co": 1.28, "nt": 1.26,
        "al": 1.25, "me": 1.24, "un": 1.23, "pa": 1.22, "el": 1.21,
        "us": 1.19, "em": 1.18, "ro": 1.17, "ce": 1.16, "ns": 1.15,
        "ur": 1.14, "ma": 1.13, "oi": 1.12, "se": 1.11, "ra": 1.10,
        "ac": 1.09, "io": 1.08, "ne": 1.07, "pr": 1.06, "tr": 1.05,
    },
    "de": {
        "en": 4.19, "er": 3.40, "de": 2.79, "ch": 2.52, "te": 2.41,
        "in": 2.34, "ei": 2.25, "ge": 2.08, "an": 1.99, "he": 1.94,
        "re": 1.87, "un": 1.85, "sc": 1.81, "di": 1.77, "ie": 1.76,
        "au": 1.67, "be": 1.62, "ra": 1.60, "ha": 1.53, "ne": 1.51,
        "se": 1.49, "ac": 1.47, "ad": 1.45, "ci": 1.43, "pa": 1.41,
        "ar": 1.39, "tr": 1.37, "ri": 1.35, "to": 1.33, "nt": 1.31,
        "io": 1.29, "ma": 1.27, "pr": 1.25, "ch": 1.23, "no": 1.21,
        "em": 1.19, "so": 1.17, "li": 1.15, "el": 1.13, "oo": 1.11,
        "la": 1.09, "sc": 1.07, "ei": 1.05, "ge": 1.03, "un": 1.01,
    },
    "pt": {
        "de": 3.21, "os": 2.89, "en": 2.78, "co": 2.35, "as": 2.28,
        "es": 2.21, "an": 2.17, "er": 1.99, "on": 1.95, "al": 1.93,
        "re": 1.89, "or": 1.84, "ta": 1.80, "qu": 1.77, "it": 1.76,
        "ue": 1.72, "lo": 1.70, "ac": 1.68, "ad": 1.66, "ci": 1.64,
        "pa": 1.62, "ar": 1.60, "tr": 1.58, "un": 1.56, "ri": 1.54,
        "to": 1.52, "nt": 1.50, "io": 1.48, "ha": 1.46, "se": 1.44,
        "na": 1.42, "po": 1.40, "so": 1.38, "te": 1.36, "di": 1.34,
        "pr": 1.32, "ch": 1.30, "ma": 1.28, "no": 1.26, "em": 1.24,
    },
    "it": {
        "di": 3.12, "en": 2.95, "de": 2.78, "er": 2.51, "la": 2.45,
        "el": 2.38, "an": 2.31, "on": 2.25, "co": 2.18, "es": 2.12,
        "re": 2.06, "or": 2.00, "al": 1.95, "ta": 1.90, "it": 1.85,
        "qu": 1.80, "ue": 1.75, "lo": 1.70, "ac": 1.65, "ad": 1.60,
        "ci": 1.55, "pa": 1.50, "ar": 1.45, "tr": 1.40, "un": 1.35,
        "ri": 1.30, "to": 1.25, "nt": 1.20, "io": 1.15, "ha": 1.10,
        "se": 1.05, "na": 1.00, "po": 0.95, "so": 0.90, "te": 0.85,
        "di": 0.80, "pr": 0.75, "ch": 0.70, "ma": 0.65, "no": 0.60,
    },
    "nl": {
        "en": 3.85, "de": 3.12, "er": 2.98, "an": 2.76, "ge": 2.65,
        "ch": 2.54, "te": 2.43, "in": 2.32, "ei": 2.21, "he": 2.10,
        "re": 1.99, "un": 1.88, "sc": 1.77, "di": 1.66, "ie": 1.55,
        "au": 1.44, "be": 1.33, "ra": 1.22, "ha": 1.11, "ne": 1.00,
        "se": 0.95, "ac": 0.90, "ad": 0.85, "ci": 0.80, "pa": 0.75,
        "ar": 0.70, "tr": 0.65, "ri": 0.60, "to": 0.55, "nt": 0.50,
        "io": 0.45, "ma": 0.40, "pr": 0.35, "ch": 0.30, "sc": 0.25,
    },
}

_LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
}


def _extract_bigrams(text: str) -> dict[str, float]:
    """Extract character bigram frequencies from text."""
    normalized = []
    for char in text.lower():
        if char.isalpha():
            normalized.append(char)
    
    text_clean = "".join(normalized)
    
    if len(text_clean) < 2:
        return {}
    
    bigrams: dict[str, float] = {}
    total = 0
    for i in range(len(text_clean) - 1):
        bigram = text_clean[i:i + 2]
        bigrams[bigram] = bigrams.get(bigram, 0.0) + 1.0
        total += 1
    
    if total > 0:
        for key in bigrams:
            bigrams[key] /= total
    
    return bigrams


def _compute_cosine_similarity(profile1: dict[str, float], profile2: dict[str, float]) -> float:
    """Compute cosine similarity between two bigram profiles."""
    common_keys = set(profile1.keys()) & set(profile2.keys())
    if not common_keys:
        return 0.0
    
    dot_product = sum(profile1[k] * profile2[k] for k in common_keys)
    mag1 = sum(v * v for v in profile1.values()) ** 0.5
    mag2 = sum(v * v for v in profile2.values()) ** 0.5
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
    
    return dot_product / (mag1 * mag2)


def detect_language(text: str, min_confidence: float = 0.15) -> LanguageResult:
    """
    Detect language of text using character bigram frequency profiling.
    
    Args:
        text: Text to analyze
        min_confidence: Minimum cosine similarity to consider a match
        
    Returns:
        LanguageResult with detected language and confidence
    """
    warnings: list[str] = []
    errors: list[str] = []
    
    if not text or not text.strip():
        return LanguageResult(
            language="unknown",
            confidence="unknown",
            method="bigram-profile",
            method_version="1.0.0",
            warnings=["Empty text provided"],
            errors=[],
        )
    
    text_profile = _extract_bigrams(text)
    if not text_profile:
        return LanguageResult(
            language="unknown",
            confidence="unknown",
            method="bigram-profile",
            method_version="1.0.0",
            warnings=["Insufficient alphabetic content for language detection"],
            errors=[],
        )
    
    # Compare against known language profiles
    scores: dict[str, float] = {}
    for lang, profile in _LANGUAGE_PROFILES.items():
        similarity = _compute_cosine_similarity(text_profile, profile)
        scores[lang] = similarity
    
    best_lang = max(scores, key=scores.get)
    best_score = scores[best_lang]
    
    # Determine confidence
    if best_score >= 0.5:
        confidence = "high"
    elif best_score >= min_confidence:
        confidence = "medium"
    else:
        confidence = "low"
        warnings.append(f"Low confidence language detection ({best_score:.2f})")
    
    return LanguageResult(
        language=_LANGUAGE_NAMES.get(best_lang, best_lang),
        confidence=confidence,
        method="bigram-profile",
        method_version="1.0.0",
        warnings=warnings,
        errors=errors,
    )


def detect_language_from_canonical(canonical_document: CanonicalDocument, min_confidence: float = 0.15) -> LanguageResult:
    """Detect language from canonical document text."""
    text = canonical_document.canonical_text or ""
    return detect_language(text, min_confidence)

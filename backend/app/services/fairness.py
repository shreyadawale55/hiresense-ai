"""Bias detection, fairness checks, and explainability helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


BIAS_KEYWORDS = [
    "age",
    "gender",
    "race",
    "ethnicity",
    "nationality",
    "religion",
    "marital",
    "family",
    "pregnant",
    "disability",
    "accent",
    "photo",
    "young",
    "old",
    "male",
    "female",
    "boy",
    "girl",
    "he ",
    "she ",
    "his ",
    "her ",
]

PROTECTED_TERMS = {
    "race",
    "gender",
    "religion",
    "nationality",
    "ethnicity",
    "age",
    "disability",
    "marital status",
    "pregnancy",
}


def detect_bias_keywords(text: str) -> list[str]:
    lowered = text.lower()
    flags = []
    for keyword in BIAS_KEYWORDS:
        if keyword in lowered:
            flags.append(keyword.strip())
    # Add explicit regex checks for pronouns in short recommendation text.
    if re.search(r"\b(him|her|his|hers|man|woman)\b", lowered):
        flags.append("gendered_language")
    return sorted(set(flags))


def fairness_score_from_flags(flags: Iterable[str]) -> float:
    count = len(set(flags))
    if count == 0:
        return 100.0
    return max(0.0, 100.0 - count * 12.5)


def confidence_from_signal_counts(*, matched_skills: int, missing_skills: int, timeline_items: int, projects: int) -> float:
    signal = 0.45
    signal += min(0.2, matched_skills * 0.03)
    signal += min(0.1, timeline_items * 0.02)
    signal += min(0.1, projects * 0.02)
    signal -= min(0.15, missing_skills * 0.01)
    return round(max(0.0, min(1.0, signal)), 3)


def sanitize_biased_text(text: str) -> str:
    """Strip obvious demographic references from generated text."""
    sanitized = text
    for keyword in PROTECTED_TERMS:
        sanitized = re.sub(fr"\b{re.escape(keyword)}\b", "[redacted]", sanitized, flags=re.IGNORECASE)
    return sanitized


def build_fairness_report(text: str) -> dict[str, object]:
    flags = detect_bias_keywords(text)
    return {
        "bias_detected": bool(flags),
        "bias_keywords": flags,
        "fairness_score": fairness_score_from_flags(flags),
    }


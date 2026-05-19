import re
import unicodedata
from dataclasses import dataclass
from typing import List

_WORD = re.compile(r"[a-zA-Z]{2,}")
_ALPHA = re.compile(r"[a-zA-Z]")
_VOWEL = re.compile(r"[aeiou]", re.I)

_GIBBERISH = re.compile(r"^[a-z]{8,}$", re.I)
_REPEAT = re.compile(r"(.)\1{5,}")
_MOSTLY_NONALNUM = re.compile(r"^[^a-zA-Z0-9]{6,}$")

def _clean_text(t: str) -> str:
    if not t:
        return ""
    # Remove common invisible / filler chars (LinkedIn digests etc.)
    # Includes U+034F (Combining Grapheme Joiner) and other oddities.
    s = t.replace("\u034f", "")  # very common in LinkedIn snippets
    # Drop any character that is "mark" or "format" category
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat.startswith("M") or cat == "Cf":
            continue
        out.append(ch)
    s2 = "".join(out)
    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2

@dataclass
class CoherenceResult:
    coherence: float
    band: str
    signals: List[str]

def coherence_score(text: str) -> CoherenceResult:
    raw = (text or "").strip()
    t = _clean_text(raw)

    if not t:
        return CoherenceResult(coherence=0.0, band="LOW_COHERENCE", signals=["empty_or_invisible"])

    s = t.lower()
    signals: List[str] = []

    # Hard gibberish checks
    if _MOSTLY_NONALNUM.match(s):
        return CoherenceResult(0.0, "GIBBERISH", ["mostly_symbols"])
    if _REPEAT.search(s):
        return CoherenceResult(0.05, "GIBBERISH", ["repeated_chars"])
    if _GIBBERISH.match(s) and not _VOWEL.search(s):
        return CoherenceResult(0.10, "GIBBERISH", ["consonant_heavy"])

    words = _WORD.findall(s)
    word_count = len(words)
    char_count = len(s)
    has_alpha = bool(_ALPHA.search(s))

    if not has_alpha:
        return CoherenceResult(0.0, "LOW_COHERENCE", ["no_alpha"])

    score = 0.35

    if word_count >= 6:
        score += 0.45
        signals.append("many_words")
    elif word_count >= 3:
        score += 0.30
        signals.append("some_words")
    elif word_count >= 1:
        score += 0.15
        signals.append("few_words")
    else:
        score -= 0.25
        signals.append("no_dictionary_words")

    if "?" in s or "!" in s:
        score += 0.05
        signals.append("punctuation_emotion")

    if char_count <= 20 and word_count == 0:
        score -= 0.25
        signals.append("short_and_wordless")

    score = max(0.0, min(1.0, score))

    band = "COHERENT"
    if score < 0.35:
        band = "LOW_COHERENCE"
    if score < 0.18:
        band = "GIBBERISH"

    return CoherenceResult(coherence=score, band=band, signals=signals)
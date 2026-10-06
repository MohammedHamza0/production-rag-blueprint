"""Text normalization, Unicode sanitation, and lexical token utilities.

Ensures safe database storage (no null bytes), uniform search representation,
and consistent token estimation across Arabic, English, and multilingual corpora.
"""

import re
import unicodedata
from typing import Optional


# Arabic Unicode Ranges & Patterns
ARABIC_DIACRITICS_REGEX = re.compile(
    r"[\u064B-\u0652\u0670\u06D6-\u06ED]"
)  # Fathatan to Sukun, dagger alef, quranic marks
TATWEEL_REGEX = re.compile(r"\u0640")  # Kashida / Tatweel
ALEF_VARIANTS_REGEX = re.compile(r"[إأآٱ]")  # Hamza variants of Alef
ARABIC_CHAR_REGEX = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")

# Whitespace patterns
MULTIPLE_SPACES_REGEX = re.compile(r"[^\S\r\n]+")
EXCESSIVE_NEWLINES_REGEX = re.compile(r"\n{3,}")


def strip_null_bytes(text: str) -> str:
    """Removes null bytes (0x00) which cause PostgreSQL string inserts to crash."""
    if not text:
        return ""
    return text.replace("\x00", "").replace("\0", "")


def clean_text(text: str) -> str:
    """Performs foundational text normalization and sanitization.

    - Strips null bytes.
    - Applies Unicode NFKC normalization.
    - Normalizes line breaks to Unix LF (\\n).
    - Collapses multiple horizontal spaces while preserving line structure.
    - Limits consecutive blank lines to at most two.
    - Strips leading and trailing whitespace.
    """
    if not text:
        return ""

    # 1. Null byte removal
    text = strip_null_bytes(text)

    # 2. Unicode NFKC normalization
    text = unicodedata.normalize("NFKC", text)

    # 3. Newline normalization
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 4. Collapse redundant horizontal spaces/tabs
    lines = [MULTIPLE_SPACES_REGEX.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)

    # 5. Collapse 3+ newlines to max 2 (preserve paragraph separation)
    text = EXCESSIVE_NEWLINES_REGEX.sub("\n\n", text)

    return text.strip()


def remove_arabic_diacritics(text: str) -> str:
    """Removes Arabic vowel marks (Tashkeel / Harakat) and Tatweel."""
    if not text:
        return ""
    text = ARABIC_DIACRITICS_REGEX.sub("", text)
    text = TATWEEL_REGEX.sub("", text)
    return text


def normalize_arabic_letters(
    text: str,
    normalize_teh_marbuta: bool = False,
    normalize_alef_maksura: bool = False,
) -> str:
    """Normalizes Arabic letter variants for uniform indexing and search matching.

    - Replaces [إأآٱ] with bare Alef [ا].
    - Optionally replaces ة with ه.
    - Optionally replaces ى with ي.
    """
    if not text:
        return ""

    # Normalize all Alef forms to bare Alef
    text = ALEF_VARIANTS_REGEX.sub("ا", text)

    if normalize_teh_marbuta:
        text = text.replace("ة", "ه")

    if normalize_alef_maksura:
        text = text.replace("ى", "ي")

    return text


def normalize_for_lexical(
    text: str,
    lang: str = "ar",
    normalize_teh_marbuta: bool = True,
    normalize_alef_maksura: bool = True,
) -> str:
    """Produces a clean normalized representation for lexical matching and tsvector generation.

    Strips diacritics, unifies letter shapes, and lowercases Latin text.
    """
    cleaned = clean_text(text)
    if not cleaned:
        return ""

    if lang == "ar" or has_arabic_script(cleaned):
        cleaned = remove_arabic_diacritics(cleaned)
        cleaned = normalize_arabic_letters(
            cleaned,
            normalize_teh_marbuta=normalize_teh_marbuta,
            normalize_alef_maksura=normalize_alef_maksura,
        )

    # Always lowercase for Latin / mixed scripts
    return cleaned.lower()


def has_arabic_script(text: str) -> bool:
    """Returns True if the text contains any Arabic Unicode characters."""
    return bool(ARABIC_CHAR_REGEX.search(text))


def detect_language_simple(text: str) -> str:
    """Heuristic language detection based on character frequency (fast & dependency-free).

    Returns 'ar' if Arabic characters represent >20% of alphabetic characters,
    otherwise returns 'en'.
    """
    if not text:
        return "en"

    arabic_count = len(ARABIC_CHAR_REGEX.findall(text))
    latin_count = len(re.findall(r"[a-zA-Z]", text))

    total_alpha = arabic_count + latin_count
    if total_alpha == 0:
        return "en"

    if (arabic_count / total_alpha) >= 0.20:
        return "ar"
    return "en"


def estimate_tokens(text: str, lang: Optional[str] = None) -> int:
    """Calibrated token count estimation without external model weight dependencies.

    Calibration:
    - Arabic text typically yields ~1.4 tokens per word due to clitic prefixes (و, ف, ب, ال).
    - English / Latin text averages ~1.3 tokens per word (or ~4 chars per token).
    """
    if not text or not text.strip():
        return 0

    if lang is None:
        lang = detect_language_simple(text)

    words = text.split()
    word_count = len(words)
    char_count = len(text)

    if lang == "ar":
        # Arabic estimate: max of word-based and char-based (approx 3.2 chars/token)
        by_words = int(word_count * 1.45)
        by_chars = int(char_count / 3.2)
        return max(1, max(by_words, by_chars))
    else:
        # Latin estimate: approx 4.0 chars/token or 1.3 words/token
        by_words = int(word_count * 1.3)
        by_chars = int(char_count / 4.0)
        return max(1, max(by_words, by_chars))

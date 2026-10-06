"""Sentence-aware semantic boundary splitter protecting bilingual abbreviations."""

import re
from typing import List, Optional
from src.ingestion.normalizers import clean_text, estimate_tokens

# Bilingual abbreviation patterns that should NOT trigger a sentence split
PROTECTED_ABBREVIATIONS = [
    # Arabic abbreviations
    r"د\.",  # دكتور
    r"أ\.",  # أستاذ
    r"ص\.",  # صفحة
    r"ق\.م\.",  # قبل الميلاد
    r"هـ\.",  # هجري
    r"م\.",  # ميلادي
    r"إلخ\.",  # إلى آخره
    r"ج\.",  # جزء
    r"ط\.",  # طبعة
    # English / Latin abbreviations
    r"dr\.",
    r"mr\.",
    r"mrs\.",
    r"ms\.",
    r"prof\.",
    r"e\.g\.",
    r"i\.e\.",
    r"vs\.",
    r"etc\.",
    r"fig\.",
    r"al\.",
    r"no\.",
    r"vol\.",
    r"dept\.",
]

# Combined regex for abbreviations
ABBREV_RE = re.compile(
    r"\b(" + "|".join(PROTECTED_ABBREVIATIONS) + r")",
    re.IGNORECASE,
)

# Decimal number pattern: digits followed by dot and digits
DECIMAL_RE = re.compile(r"\b\d+\.\d+\b")

# Sentence terminators: period, exclamation mark, question mark, Arabic question mark, semicolon, Arabic semicolon
# Followed by whitespace or end of line
SENTENCE_SPLIT_RE = re.compile(r"([.!?؟؛;])\s+")


class SentenceSemanticChunker:
    """Splits text into sentences while protecting abbreviations and formatting."""

    def __init__(self, lang: str = "ar"):
        self.lang = lang

    def split_into_sentences(self, text: str) -> List[str]:
        """Splits raw text into a list of sentences, protecting abbreviations and numbers."""
        cleaned = clean_text(text)
        if not cleaned:
            return []

        # Mask decimal numbers temporarily (e.g. 3.14 -> 3__DEC__14)
        masked_text = DECIMAL_RE.sub(lambda m: m.group(0).replace(".", "__DEC__"), cleaned)

        # Mask protected abbreviations (e.g. Dr. -> Dr__DOT__)
        def mask_abbrev(match: re.Match) -> str:
            return match.group(0).replace(".", "__DOT__")

        masked_text = ABBREV_RE.sub(mask_abbrev, masked_text)

        # Also mask multiple dots (ellipses ...)
        masked_text = re.sub(r"\.{2,}", "__ELLIPSIS__", masked_text)

        # Split on sentence boundaries
        parts = SENTENCE_SPLIT_RE.split(masked_text)

        sentences: List[str] = []
        i = 0
        while i < len(parts):
            sentence_body = parts[i]
            # Check if next part is the captured punctuation delimiter
            if i + 1 < len(parts) and parts[i + 1] in [".", "!", "?", "؟", "؛", ";"]:
                full_sentence = sentence_body + parts[i + 1]
                i += 2
            else:
                full_sentence = sentence_body
                i += 1

            # Restore masked characters
            restored = (
                full_sentence.replace("__DEC__", ".")
                .replace("__DOT__", ".")
                .replace("__ELLIPSIS__", "...")
                .strip()
            )
            if restored:
                sentences.append(restored)

        return sentences

    def pack_sentences_into_chunks(
        self,
        sentences: List[str],
        target_tokens: int,
        overlap_tokens: int = 0,
        lang: Optional[str] = None,
    ) -> List[str]:
        """Packs a sequence of sentences into chunks within the target token budget.

        Uses sentence-level boundary overlap when overlap_tokens > 0.
        """
        if not sentences:
            return []

        lang = lang or self.lang
        chunks: List[str] = []
        current_sentences: List[str] = []
        current_tokens = 0

        i = 0
        while i < len(sentences):
            sent = sentences[i]
            sent_tokens = estimate_tokens(sent, lang=lang)

            if current_tokens + sent_tokens <= target_tokens or not current_sentences:
                current_sentences.append(sent)
                current_tokens += sent_tokens
                i += 1
            else:
                # Target exceeded, flush current chunk
                chunk_text = " ".join(current_sentences)
                chunks.append(chunk_text)

                # Determine overlap sentences
                if overlap_tokens > 0:
                    overlap_sents: List[str] = []
                    acc_overlap = 0
                    for s in reversed(current_sentences):
                        s_tok = estimate_tokens(s, lang=lang)
                        if acc_overlap + s_tok <= overlap_tokens or not overlap_sents:
                            overlap_sents.insert(0, s)
                            acc_overlap += s_tok
                        else:
                            break
                    current_sentences = overlap_sents
                    current_tokens = acc_overlap
                else:
                    current_sentences = []
                    current_tokens = 0

        if current_sentences:
            chunks.append(" ".join(current_sentences))

        return chunks

"""Query transformation, boilerplate stripping, and sub-query decomposition."""

from dataclasses import dataclass, field
import re
from typing import List, Optional
from src.ingestion.normalizers import clean_text, normalize_for_lexical

# Conversational preambles and boilerplate patterns to strip
BOILERPLATE_PATTERNS = [
    # Arabic greetings and politeness
    r"^(من فضلك|لو سمحت|أرجو منك|بالله عليك|تحياتي|السلام عليكم|مرحبا)\s*",
    r"^(أريد أن أعرف|أود معرفة|هل يمكنك أن تخبرني|هل تستطيع إخباري|أخبرني عن|حدثني عن)\s*",
    r"^(ابحث لي عن|أعطني معلومات عن|ما هي معلوماتك عن)\s*",
    # English greetings and politeness
    r"^(please|kindly|hello|hi|hey|greetings)\s*",
    r"^(can you please tell me|could you explain|i would like to know|tell me about|what can you tell me about)\s*",
    r"^(give me information on|search for|find me details about)\s*",
]

BOILERPLATE_REGEX = re.compile("|".join(BOILERPLATE_PATTERNS), re.IGNORECASE)

# Exact quotation marks pattern
EXACT_PHRASE_REGEX = re.compile(r'["\']([^"\']+)["\']|«([^»]+)»')

# Conjunction splitters for sub-query generation (e.g. "X versus Y", "قارن بين X و Y")
COMPARATIVE_SPLIT_REGEX = re.compile(
    r"\b(?:versus|vs\.?|compared to|مقارنة بـ?|بالمقارنة مع)\b",
    re.IGNORECASE,
)


@dataclass
class TransformedQuery:
    """Encapsulates the original and transformed query representations for multi-stage search."""

    original_query: str
    cleaned_query: str
    lexical_query: str
    sub_queries: List[str] = field(default_factory=list)
    exact_phrases: List[str] = field(default_factory=list)
    is_transformed: bool = False


class QueryTransformer:
    """Transforms raw user input into optimized vector and lexical search queries."""

    def __init__(self, default_lang: str = "ar"):
        self.default_lang = default_lang

    def transform(self, query: str, lang: Optional[str] = None) -> TransformedQuery:
        """Cleans boilerplate, extracts exact phrases, and decomposes compound queries."""
        raw = clean_text(query)
        if not raw:
            return TransformedQuery(
                original_query=query,
                cleaned_query="",
                lexical_query="",
                sub_queries=[],
                exact_phrases=[],
                is_transformed=False,
            )

        # 1. Extract exact phrases within quotes
        exact_phrases: List[str] = []
        for match in EXACT_PHRASE_REGEX.finditer(raw):
            phrase = match.group(1) or match.group(2)
            if phrase and len(phrase.strip()) > 1:
                exact_phrases.append(phrase.strip())

        # 2. Strip conversational preambles
        cleaned = raw
        # Apply iteratively until stable
        for _ in range(2):
            prev = cleaned
            cleaned = BOILERPLATE_REGEX.sub("", cleaned).strip()
            if cleaned == prev:
                break

        # Remove trailing question marks or punctuation for clean retrieval
        cleaned_no_punct = re.sub(r"[?؟.!]+$", "", cleaned).strip()
        if cleaned_no_punct:
            cleaned = cleaned_no_punct

        # 3. Normalized lexical query
        actual_lang = lang or self.default_lang
        lexical = normalize_for_lexical(cleaned, lang=actual_lang)

        # 4. Generate sub-queries for comparative or multi-aspect queries
        sub_queries: List[str] = []
        if COMPARATIVE_SPLIT_REGEX.search(cleaned):
            parts = COMPARATIVE_SPLIT_REGEX.split(cleaned)
            sub_queries = [p.strip() for p in parts if len(p.strip()) > 3]

        is_transformed = (cleaned != raw) or bool(sub_queries)

        return TransformedQuery(
            original_query=raw,
            cleaned_query=cleaned if cleaned else raw,
            lexical_query=lexical if lexical else raw,
            sub_queries=sub_queries,
            exact_phrases=exact_phrases,
            is_transformed=is_transformed,
        )

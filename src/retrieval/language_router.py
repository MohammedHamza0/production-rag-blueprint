"""Language routing, query classification, and dynamic weight calculation for 5-way hybrid search."""

from dataclasses import dataclass, field
import re
from typing import List, Optional
from src.ingestion.normalizers import detect_language_simple, normalize_for_lexical


@dataclass
class ClassificationResult:
    """Result of query linguistic and intent analysis."""

    detected_language: str
    query_type: str  # "conceptual", "exact_factoid", "balanced"
    vector_weight: float
    keyword_weight: float
    preferred_languages: List[str] = field(default_factory=list)
    normalized_lexical_query: str = ""
    is_numeric_or_citation: bool = False


# Patterns indicating exact factoid, citation, page number, or statutory query
FACTOID_PATTERNS = [
    # Quotes
    r'["\'].+?["\']',
    r'«.+?»',
    # Numbers and IDs
    r"\b\d+\b",
    # Page / chapter / section keywords (Arabic & English)
    r"\b(صفحة|ص\.|فصل|باب|مادة|رقم|قانون|مرسوم|آية|حديث)\b",
    r"\b(page|p\.|chapter|section|article|number|no\.|law|statute|verse)\b",
    # Exact query operators
    r"^من هو\b",
    r"^متى\b",
    r"^أين\b",
    r"^كم\b",
    r"^who is\b",
    r"^when\b",
    r"^where\b",
    r"^how many\b",
]

# Patterns indicating conceptual, analytical, or explanatory queries
CONCEPTUAL_PATTERNS = [
    r"\b(ما الفرق|قارن|كيف يعمل|اشرح|وضح|حلل|أسباب|أثر|علاقة|مفهوم|فلسفة|دلالة)\b",
    r"\b(what is the difference|compare|how does|explain|clarify|analyze|reasons|impact|relationship|concept|philosophy)\b",
]

FACTOID_REGEX = re.compile("|".join(FACTOID_PATTERNS), re.IGNORECASE)
CONCEPTUAL_REGEX = re.compile("|".join(CONCEPTUAL_PATTERNS), re.IGNORECASE)


class LanguageRouter:
    """Analyzes user queries to route search channels and dynamically assign RRF weights."""

    # Standard production weight presets
    WEIGHTS_CONCEPTUAL = (0.75, 0.25)  # Heavy semantic / dense
    WEIGHTS_FACTOID = (0.40, 0.60)     # Heavy lexical / exact
    WEIGHTS_BALANCED = (0.65, 0.35)    # Default balanced

    def classify_query(self, query: str, preferred_lang: Optional[str] = None) -> ClassificationResult:
        """Classifies query into query_type and calculates optimal vector and lexical weights."""
        raw = query.strip()
        if not raw:
            return ClassificationResult(
                detected_language="en",
                query_type="balanced",
                vector_weight=self.WEIGHTS_BALANCED[0],
                keyword_weight=self.WEIGHTS_BALANCED[1],
                preferred_languages=["en"],
                normalized_lexical_query="",
                is_numeric_or_citation=False,
            )

        # 1. Detect language
        detected_lang = preferred_lang or detect_language_simple(raw)
        preferred_langs = [detected_lang]
        if detected_lang != "en":
            preferred_langs.append("en")  # English as universal fallback

        # 2. Analyze query characteristics
        has_factoid_indicators = bool(FACTOID_REGEX.search(raw))
        has_conceptual_indicators = bool(CONCEPTUAL_REGEX.search(raw))
        has_numbers_or_quotes = bool(re.search(r'[\d"\'«»]', raw))

        if has_factoid_indicators or (has_numbers_or_quotes and not has_conceptual_indicators):
            query_type = "exact_factoid"
            v_weight, k_weight = self.WEIGHTS_FACTOID
            is_num_or_cite = True
        elif has_conceptual_indicators:
            query_type = "conceptual"
            v_weight, k_weight = self.WEIGHTS_CONCEPTUAL
            is_num_or_cite = False
        else:
            query_type = "balanced"
            v_weight, k_weight = self.WEIGHTS_BALANCED
            is_num_or_cite = False

        # 3. Compute normalized lexical representation
        lexical_query = normalize_for_lexical(raw, lang=detected_lang)

        return ClassificationResult(
            detected_language=detected_lang,
            query_type=query_type,
            vector_weight=v_weight,
            keyword_weight=k_weight,
            preferred_languages=preferred_langs,
            normalized_lexical_query=lexical_query,
            is_numeric_or_citation=is_num_or_cite,
        )

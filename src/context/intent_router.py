"""Intent classification router running in parallel with retrieval."""

from dataclasses import dataclass
from enum import Enum
import re
from typing import List, Optional
from src.core.logging import get_logger

logger = get_logger("context.intent_router")


class QueryIntent(str, Enum):
    """Categorization of user conversational intent."""

    NEW_QUERY = "NEW_QUERY"          # Fresh domain / factual query requiring search
    FOLLOW_UP = "FOLLOW_UP"          # Multi-turn query referencing prior context
    CLARIFICATION = "CLARIFICATION"  # User asks to clarify assistant's previous message
    TRANSFORM = "TRANSFORM"          # User asks to reformat / summarize / translate prior reply


@dataclass
class IntentResult:
    """Outcome of intent routing."""

    intent: QueryIntent
    confidence: float
    requires_retrieval: bool
    sub_aspect: Optional[str] = None


# Intent indicators
FOLLOW_UP_PATTERNS = [
    r"^(وماذا\s+عن|وكيف\s+عن|ولماذا\s+إذن|وهل\s+يعني\s+ذلك|أكمل\s+حديثك|وما\s+الفرق\s+بينهما)\b",
    r"^(اشرح\s+(المزيد|النقطة\s+الثانية|هذا\s+الأمر|تلك\s+المسألة))\b",
    r"^(what\s+about|how\s+about|and\s+why|can\s+you\s+elaborate|tell\s+me\s+more\s+about\s+that)\b",
    r"^(explain\s+(the\s+second\s+point|this\s+further|what\s+happened\s+next))\b",
]

CLARIFICATION_PATTERNS = [
    r"^(ماذا\s+(تقصد|تعني)\s+بـ|لم\s+أفهم\s+قصدك|وضح\s+لي\s+أكثر|هل\s+يمكنك\s+توضيح)\b",
    r"^(what\s+do\s+you\s+mean\s+by|i\s+didn'?t\s+understand|could\s+you\s+clarify)\b",
]

TRANSFORM_PATTERNS = [
    r"(لخص\s+(هذا|ذلك|ما\s+سبق)\s+في|حول\s+(هذا|ذلك)\s+إلى\s+جدول|صغ\s+ذلك\s+في\s+نقاط|ترجم\s+(هذا|ذلك)\s+إلى)",
    r"(summarize\s+(this|that|above)\s+in|convert\s+(this|that)\s+to\s+a\s+table|put\s+this\s+in\s+bullet\s+points|translate\s+(this|that)\s+to)",
]

FOLLOW_UP_REGEX = re.compile("|".join(FOLLOW_UP_PATTERNS), re.IGNORECASE)
CLARIFICATION_REGEX = re.compile("|".join(CLARIFICATION_PATTERNS), re.IGNORECASE)
TRANSFORM_REGEX = re.compile("|".join(TRANSFORM_PATTERNS), re.IGNORECASE)


class IntentRouter:
    """Fast deterministic intent router with zero external network overhead."""

    def route_intent(
        self,
        query: str,
        has_conversation_history: bool = False,
    ) -> IntentResult:
        """Classifies query intent to determine conversational state and retrieval requirements."""
        cleaned = query.strip()
        if not cleaned:
            return IntentResult(
                intent=QueryIntent.NEW_QUERY,
                confidence=1.0,
                requires_retrieval=False,
            )

        # If there is no previous conversation, it cannot be a follow-up, clarification, or transform of prior text
        if not has_conversation_history:
            return IntentResult(
                intent=QueryIntent.NEW_QUERY,
                confidence=0.95,
                requires_retrieval=True,
            )

        # 1. Check for transform request (summarize/translate previous turn)
        if TRANSFORM_REGEX.search(cleaned):
            logger.debug("intent_detected_transform", query=cleaned[:40])
            return IntentResult(
                intent=QueryIntent.TRANSFORM,
                confidence=0.90,
                requires_retrieval=False,  # Can operate on prior turn directly
            )

        # 2. Check for clarification request
        if CLARIFICATION_REGEX.search(cleaned):
            logger.debug("intent_detected_clarification", query=cleaned[:40])
            return IntentResult(
                intent=QueryIntent.CLARIFICATION,
                confidence=0.88,
                requires_retrieval=False,
            )

        # 3. Check for follow-up
        if FOLLOW_UP_REGEX.search(cleaned):
            logger.debug("intent_detected_follow_up", query=cleaned[:40])
            return IntentResult(
                intent=QueryIntent.FOLLOW_UP,
                confidence=0.85,
                requires_retrieval=True,  # Usually needs contextual retrieval
            )

        # Default to new query
        return IntentResult(
            intent=QueryIntent.NEW_QUERY,
            confidence=0.80,
            requires_retrieval=True,
        )

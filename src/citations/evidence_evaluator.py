"""Evidence sufficiency evaluator implementing pre-generation grounding checks and scientific abstention."""

from dataclasses import dataclass
from typing import List, Optional
from src.core.logging import get_logger
from src.domain.entities import RetrievedSource

logger = get_logger("citations.evidence_evaluator")

ABSTENTION_MESSAGES = {
    "ar": "لم تتوفر في المراجع المعتمدة أدلة كافية ومؤكدة للإجابة عن هذا السؤال بدقة علمية. نوصي بتوسيع نطاق البحث أو مراجعة صياغة السؤال.",
    "en": "There is insufficient evidence in the verified sources to reliably answer this question. Please broaden your search or refine your query.",
}


@dataclass
class EvidenceEvaluationResult:
    """Outcome of pre-generation evidence sufficiency evaluation."""

    status: str  # STRONG, MODERATE, INSUFFICIENT
    should_abstain: bool
    top_score: float
    total_sources: int
    abstention_message: Optional[str] = None
    confidence_score: float = 0.0


class EvidenceEvaluator:
    """Evaluates retrieved candidate sources before generative LLM execution to prevent hallucination."""

    def __init__(
        self,
        min_score_threshold: float = 0.35,
        strong_score_threshold: float = 0.65,
    ):
        self.min_score_threshold = min_score_threshold
        self.strong_score_threshold = strong_score_threshold

    def evaluate(
        self,
        sources: List[RetrievedSource],
        target_lang: str = "ar",
    ) -> EvidenceEvaluationResult:
        """Evaluates whether retrieved sources provide sufficient factual grounding to proceed to generation."""
        lang_key = "ar" if target_lang.startswith("ar") else "en"

        if not sources:
            logger.info("evidence_evaluation_empty_sources_abstain")
            return EvidenceEvaluationResult(
                status="INSUFFICIENT",
                should_abstain=True,
                top_score=0.0,
                total_sources=0,
                abstention_message=ABSTENTION_MESSAGES[lang_key],
                confidence_score=0.0,
            )

        # Find best combined or similarity score
        best_source = max(sources, key=lambda s: max(s.combined_score, s.vector_similarity))
        top_score = max(best_source.combined_score, best_source.vector_similarity)

        # Check for empty content
        valid_chunks_count = sum(1 for s in sources if len(s.content.strip()) > 20)

        if valid_chunks_count == 0 or top_score < self.min_score_threshold:
            logger.info(
                "evidence_evaluation_insufficient_score_abstain",
                top_score=top_score,
                threshold=self.min_score_threshold,
                valid_chunks=valid_chunks_count,
            )
            return EvidenceEvaluationResult(
                status="INSUFFICIENT",
                should_abstain=True,
                top_score=top_score,
                total_sources=len(sources),
                abstention_message=ABSTENTION_MESSAGES[lang_key],
                confidence_score=top_score,
            )

        if top_score >= self.strong_score_threshold:
            status = "STRONG"
        else:
            status = "MODERATE"

        logger.debug(
            "evidence_evaluation_passed",
            status=status,
            top_score=top_score,
            sources_count=len(sources),
        )
        return EvidenceEvaluationResult(
            status=status,
            should_abstain=False,
            top_score=top_score,
            total_sources=len(sources),
            abstention_message=None,
            confidence_score=top_score,
        )

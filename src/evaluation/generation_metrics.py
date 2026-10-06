"""Generation & grounding evaluation metrics: Groundedness, Citation Precision, Hallucination Rate."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GenerationMetricsReport:
    """Aggregated generation, grounding, and citation evaluation metrics."""
    groundedness_score: float
    citation_precision: float
    hallucination_rate: float
    total_claims: int
    verified_claims: int
    unsupported_claims: int
    phantom_citations_detected: int
    abstention_accuracy: Optional[float] = None
    is_fully_grounded: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "groundedness_score": round(self.groundedness_score, 4),
            "citation_precision": round(self.citation_precision, 4),
            "hallucination_rate": round(self.hallucination_rate, 4),
            "total_claims": self.total_claims,
            "verified_claims": self.verified_claims,
            "unsupported_claims": self.unsupported_claims,
            "phantom_citations_detected": self.phantom_citations_detected,
            "abstention_accuracy": round(self.abstention_accuracy, 4) if self.abstention_accuracy is not None else None,
            "is_fully_grounded": self.is_fully_grounded,
        }


def calculate_groundedness_score(claims: List[Dict[str, Any]]) -> float:
    """Calculates groundedness score as the ratio of supported claims to total verified claims."""
    if not claims:
        return 1.0  # Empty claims or trivial answer defaults to fully non-hallucinatory

    supported = sum(1 for c in claims if c.get("is_supported", False))
    return supported / float(len(claims))


def calculate_citation_precision(citations: List[Dict[str, Any]], available_source_count: int) -> float:
    """Calculates citation precision by penalizing phantom references.
    
    A citation is valid if its source_index is in 1..available_source_count.
    """
    if not citations:
        return 1.0

    valid_citations = 0
    for cit in citations:
        source_idx = cit.get("source_index", 0)
        if 1 <= source_idx <= available_source_count:
            valid_citations += 1

    return valid_citations / float(len(citations))


def calculate_hallucination_rate(claims: List[Dict[str, Any]]) -> float:
    """Calculates the hallucination rate (1.0 - groundedness_score)."""
    return 1.0 - calculate_groundedness_score(claims)


def evaluate_generation(
    claims: List[Dict[str, Any]],
    citations: List[Dict[str, Any]],
    available_source_count: int,
    is_abstained: bool = False,
    expected_abstention: Optional[bool] = None,
) -> GenerationMetricsReport:
    """Evaluates generation grounding, citation precision, and abstention fidelity."""
    groundedness = calculate_groundedness_score(claims)
    citation_prec = calculate_citation_precision(citations, available_source_count)
    hallucination = calculate_hallucination_rate(claims)

    total_c = len(claims)
    verified_c = sum(1 for c in claims if c.get("is_supported", False))
    unsupported_c = total_c - verified_c

    phantom_count = 0
    for cit in citations:
        idx = cit.get("source_index", 0)
        if idx < 1 or idx > available_source_count:
            phantom_count += 1

    abstention_acc: Optional[float] = None
    if expected_abstention is not None:
        abstention_acc = 1.0 if (is_abstained == expected_abstention) else 0.0

    return GenerationMetricsReport(
        groundedness_score=groundedness,
        citation_precision=citation_prec,
        hallucination_rate=hallucination,
        total_claims=total_c,
        verified_claims=verified_c,
        unsupported_claims=unsupported_c,
        phantom_citations_detected=phantom_count,
        abstention_accuracy=abstention_acc,
        is_fully_grounded=(unsupported_c == 0 and phantom_count == 0),
    )

"""Evaluation package: IR retrieval metrics, generation grounding, and benchmark runners."""

from src.evaluation.generation_metrics import (
    GenerationMetricsReport,
    calculate_citation_precision,
    calculate_groundedness_score,
    calculate_hallucination_rate,
    evaluate_generation,
)
from src.evaluation.rag_evaluator import (
    RAGBenchmarkReport,
    RAGBenchmarkSample,
    RAGEvaluator,
)
from src.evaluation.retrieval_metrics import (
    RetrievalMetricsReport,
    evaluate_retrieval,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)

__all__ = [
    # Retrieval
    "recall_at_k",
    "precision_at_k",
    "mean_reciprocal_rank",
    "ndcg_at_k",
    "evaluate_retrieval",
    "RetrievalMetricsReport",
    # Generation
    "calculate_groundedness_score",
    "calculate_citation_precision",
    "calculate_hallucination_rate",
    "evaluate_generation",
    "GenerationMetricsReport",
    # Pipeline Orchestrator
    "RAGEvaluator",
    "RAGBenchmarkSample",
    "RAGBenchmarkReport",
]

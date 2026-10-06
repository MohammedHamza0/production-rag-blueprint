"""Comprehensive RAG pipeline evaluator combining retrieval and generation metrics."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.evaluation.generation_metrics import GenerationMetricsReport, evaluate_generation
from src.evaluation.retrieval_metrics import RetrievalMetricsReport, evaluate_retrieval


@dataclass
class RAGBenchmarkSample:
    """A single evaluation benchmark test case."""
    query: str
    ground_truth_doc_ids: List[str]
    retrieved_doc_ids: List[str]
    generated_text: str
    claims: List[Dict[str, Any]]
    citations: List[Dict[str, Any]]
    available_source_count: int
    is_abstained: bool = False
    expected_abstention: bool = False


@dataclass
class RAGBenchmarkReport:
    """Holistic benchmark report across retrieval and generation subsystems."""
    sample_count: int
    mean_recall_at_5: float
    mean_mrr: float
    mean_ndcg_at_5: float
    mean_groundedness: float
    mean_citation_precision: float
    mean_hallucination_rate: float
    abstention_accuracy: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_count": self.sample_count,
            "mean_recall_at_5": round(self.mean_recall_at_5, 4),
            "mean_mrr": round(self.mean_mrr, 4),
            "mean_ndcg_at_5": round(self.mean_ndcg_at_5, 4),
            "mean_groundedness": round(self.mean_groundedness, 4),
            "mean_citation_precision": round(self.mean_citation_precision, 4),
            "mean_hallucination_rate": round(self.mean_hallucination_rate, 4),
            "abstention_accuracy": round(self.abstention_accuracy, 4),
        }


class RAGEvaluator:
    """Automated evaluation suite for the production RAG pipeline."""

    def evaluate_sample(self, sample: RAGBenchmarkSample) -> Dict[str, Any]:
        """Evaluates an individual benchmark sample."""
        retrieval_res: RetrievalMetricsReport = evaluate_retrieval(
            retrieved_ids=sample.retrieved_doc_ids,
            ground_truth_ids=sample.ground_truth_doc_ids,
            k_values=[1, 3, 5, 10],
        )

        generation_res: GenerationMetricsReport = evaluate_generation(
            claims=sample.claims,
            citations=sample.citations,
            available_source_count=sample.available_source_count,
            is_abstained=sample.is_abstained,
            expected_abstention=sample.expected_abstention,
        )

        return {
            "query": sample.query,
            "retrieval": retrieval_res.to_dict(),
            "generation": generation_res.to_dict(),
        }

    def evaluate_dataset(self, samples: List[RAGBenchmarkSample]) -> RAGBenchmarkReport:
        """Evaluates an entire dataset and computes macroeconomic pipeline averages."""
        if not samples:
            return RAGBenchmarkReport(
                sample_count=0,
                mean_recall_at_5=0.0,
                mean_mrr=0.0,
                mean_ndcg_at_5=0.0,
                mean_groundedness=0.0,
                mean_citation_precision=0.0,
                mean_hallucination_rate=0.0,
                abstention_accuracy=0.0,
            )

        total_r5 = 0.0
        total_mrr = 0.0
        total_ndcg5 = 0.0
        total_groundedness = 0.0
        total_citation_prec = 0.0
        total_hallucination = 0.0
        correct_abstentions = 0

        for sample in samples:
            r_report = evaluate_retrieval(
                retrieved_ids=sample.retrieved_doc_ids,
                ground_truth_ids=sample.ground_truth_doc_ids,
                k_values=[5],
            )
            g_report = evaluate_generation(
                claims=sample.claims,
                citations=sample.citations,
                available_source_count=sample.available_source_count,
                is_abstained=sample.is_abstained,
                expected_abstention=sample.expected_abstention,
            )

            total_r5 += r_report.recall_at_k.get(5, 0.0)
            total_mrr += r_report.mrr
            total_ndcg5 += r_report.ndcg_at_k.get(5, 0.0)

            total_groundedness += g_report.groundedness_score
            total_citation_prec += g_report.citation_precision
            total_hallucination += g_report.hallucination_rate

            if sample.is_abstained == sample.expected_abstention:
                correct_abstentions += 1

        n = float(len(samples))
        return RAGBenchmarkReport(
            sample_count=len(samples),
            mean_recall_at_5=total_r5 / n,
            mean_mrr=total_mrr / n,
            mean_ndcg_at_5=total_ndcg5 / n,
            mean_groundedness=total_groundedness / n,
            mean_citation_precision=total_citation_prec / n,
            mean_hallucination_rate=total_hallucination / n,
            abstention_accuracy=correct_abstentions / n,
        )

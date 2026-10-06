"""Information Retrieval (IR) evaluation metrics: Recall@K, Precision@K, MRR, NDCG@K."""

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Set


@dataclass
class RetrievalMetricsReport:
    """Aggregated retrieval evaluation metrics."""
    recall_at_k: Dict[int, float]
    precision_at_k: Dict[int, float]
    mrr: float
    ndcg_at_k: Dict[int, float]
    total_retrieved: int
    total_relevant: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recall": self.recall_at_k,
            "precision": self.precision_at_k,
            "mrr": round(self.mrr, 4),
            "ndcg": {k: round(v, 4) for k, v in self.ndcg_at_k.items()},
            "total_retrieved": self.total_retrieved,
            "total_relevant": self.total_relevant,
        }


def recall_at_k(retrieved_ids: List[str], ground_truth_ids: List[str], k: int) -> float:
    """Computes Recall@K: fraction of relevant documents successfully retrieved in top-K."""
    if not ground_truth_ids or k <= 0:
        return 0.0

    relevant_set: Set[str] = set(ground_truth_ids)
    top_k_retrieved: Set[str] = set(retrieved_ids[:k])

    hits = len(relevant_set.intersection(top_k_retrieved))
    return hits / float(len(relevant_set))


def precision_at_k(retrieved_ids: List[str], ground_truth_ids: List[str], k: int) -> float:
    """Computes Precision@K: fraction of retrieved documents in top-K that are relevant."""
    if k <= 0:
        return 0.0
    if not retrieved_ids:
        return 0.0

    relevant_set: Set[str] = set(ground_truth_ids)
    top_k_retrieved = retrieved_ids[:k]

    hits = sum(1 for item in top_k_retrieved if item in relevant_set)
    return hits / float(k)


def mean_reciprocal_rank(retrieved_ids: List[str], ground_truth_ids: List[str]) -> float:
    """Computes Reciprocal Rank (RR): reciprocal of the 1-based rank of first relevant item."""
    if not ground_truth_ids or not retrieved_ids:
        return 0.0

    relevant_set: Set[str] = set(ground_truth_ids)
    for rank_idx, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_set:
            return 1.0 / rank_idx

    return 0.0


def ndcg_at_k(retrieved_ids: List[str], ground_truth_ids: List[str], k: int) -> float:
    """Computes Normalized Discounted Cumulative Gain at rank K (NDCG@K)."""
    if not ground_truth_ids or k <= 0 or not retrieved_ids:
        return 0.0

    relevant_set: Set[str] = set(ground_truth_ids)
    top_k = retrieved_ids[:k]

    # Calculate DCG@K
    dcg = 0.0
    for i, doc_id in enumerate(top_k, start=1):
        relevance = 1.0 if doc_id in relevant_set else 0.0
        if relevance > 0:
            dcg += relevance / math.log2(i + 1)

    # Calculate Ideal DCG@K (IDCG@K)
    num_relevant_in_top_k = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, num_relevant_in_top_k + 1))

    if idcg == 0.0:
        return 0.0

    return dcg / idcg


def evaluate_retrieval(
    retrieved_ids: List[str],
    ground_truth_ids: List[str],
    k_values: Optional[List[int]] = None,
) -> RetrievalMetricsReport:
    """Evaluates a retrieval output against ground truth across multiple K cutoffs."""
    if k_values is None:
        k_values = [1, 3, 5, 10]

    recalls: Dict[int, float] = {}
    precisions: Dict[int, float] = {}
    ndcgs: Dict[int, float] = {}

    for k in k_values:
        recalls[k] = round(recall_at_k(retrieved_ids, ground_truth_ids, k), 4)
        precisions[k] = round(precision_at_k(retrieved_ids, ground_truth_ids, k), 4)
        ndcgs[k] = round(ndcg_at_k(retrieved_ids, ground_truth_ids, k), 4)

    mrr_score = mean_reciprocal_rank(retrieved_ids, ground_truth_ids)

    return RetrievalMetricsReport(
        recall_at_k=recalls,
        precision_at_k=precisions,
        mrr=round(mrr_score, 4),
        ndcg_at_k=ndcgs,
        total_retrieved=len(retrieved_ids),
        total_relevant=len(ground_truth_ids),
    )

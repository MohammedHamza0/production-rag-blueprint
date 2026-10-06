"""Unit tests for evaluation metrics (IR & Generation) and observability subsystem."""

import math
from unittest.mock import AsyncMock
import uuid
import pytest
import httpx

from src.evaluation.generation_metrics import (
    calculate_citation_precision,
    calculate_groundedness_score,
    calculate_hallucination_rate,
    evaluate_generation,
)
from src.evaluation.rag_evaluator import (
    RAGBenchmarkSample,
    RAGEvaluator,
)
from src.evaluation.retrieval_metrics import (
    evaluate_retrieval,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from src.main import app
from src.observability.audit import SecurityAuditLogger
from src.observability.metrics import MetricsCollector, metrics_collector


class TestRetrievalMetrics:
    """Tests for Information Retrieval metrics (Recall, Precision, MRR, NDCG)."""

    def test_recall_at_k(self):
        gt = ["doc1", "doc2", "doc3", "doc4"]
        retrieved = ["doc1", "doc5", "doc2", "doc6", "doc7"]

        # In top 3: doc1 and doc2 are retrieved -> 2 / 4 = 0.5
        assert recall_at_k(retrieved, gt, k=3) == 0.5
        # In top 1: only doc1 -> 1 / 4 = 0.25
        assert recall_at_k(retrieved, gt, k=1) == 0.25
        # In top 0: 0.0
        assert recall_at_k(retrieved, gt, k=0) == 0.0
        # Empty GT: 0.0
        assert recall_at_k(retrieved, [], k=5) == 0.0

    def test_precision_at_k(self):
        gt = ["doc1", "doc2"]
        retrieved = ["doc1", "doc3", "doc2", "doc4"]

        # In top 2: doc1 is relevant -> 1 / 2 = 0.5
        assert precision_at_k(retrieved, gt, k=2) == 0.5
        # In top 3: doc1 and doc2 are relevant -> 2 / 3 ~ 0.6667
        assert math.isclose(precision_at_k(retrieved, gt, k=3), 2.0 / 3.0)
        # In top 0: 0.0
        assert precision_at_k(retrieved, gt, k=0) == 0.0

    def test_mean_reciprocal_rank(self):
        gt = ["docA", "docB"]
        # First relevant item docA is at rank 1 -> RR = 1.0
        assert mean_reciprocal_rank(["docA", "docX", "docY"], gt) == 1.0
        # First relevant item docB is at rank 2 -> RR = 1/2 = 0.5
        assert mean_reciprocal_rank(["docX", "docB", "docA"], gt) == 0.5
        # First relevant item at rank 3 -> RR = 1/3
        assert math.isclose(mean_reciprocal_rank(["docX", "docY", "docA"], gt), 1.0 / 3.0)
        # No relevant item found -> RR = 0.0
        assert mean_reciprocal_rank(["docX", "docY"], gt) == 0.0

    def test_ndcg_at_k(self):
        gt = ["doc1", "doc2"]
        # Perfect ranking: doc1 at pos 1, doc2 at pos 2
        perfect_retrieved = ["doc1", "doc2", "doc3", "doc4"]
        assert math.isclose(ndcg_at_k(perfect_retrieved, gt, k=2), 1.0, rel_tol=1e-4)

        # Inverted ranking: doc3, doc1, doc2
        inverted_retrieved = ["doc3", "doc1", "doc2"]
        score = ndcg_at_k(inverted_retrieved, gt, k=3)
        assert 0.0 < score < 1.0

        # Zero hits
        zero_retrieved = ["docX", "docY"]
        assert ndcg_at_k(zero_retrieved, gt, k=2) == 0.0

    def test_evaluate_retrieval_report(self):
        gt = ["doc1", "doc2"]
        retrieved = ["doc1", "doc3", "doc2", "doc4"]

        report = evaluate_retrieval(retrieved, gt, k_values=[1, 2, 5])
        assert report.recall_at_k[1] == 0.5
        assert report.recall_at_k[5] == 1.0
        assert report.mrr == 1.0
        assert report.total_retrieved == 4
        assert report.total_relevant == 2

        d = report.to_dict()
        assert "recall" in d
        assert "mrr" in d


class TestGenerationMetrics:
    """Tests for generation faithfulness, citation precision, and hallucination rate."""

    def test_groundedness_score(self):
        claims = [
            {"claim_text": "C1", "is_supported": True},
            {"claim_text": "C2", "is_supported": True},
            {"claim_text": "C3", "is_supported": False},
        ]
        score = calculate_groundedness_score(claims)
        assert math.isclose(score, 2.0 / 3.0)

        # Empty claims -> 1.0
        assert calculate_groundedness_score([]) == 1.0

    def test_citation_precision(self):
        # 3 available sources
        valid_citations = [
            {"source_index": 1},
            {"source_index": 2},
            {"source_index": 3},
        ]
        assert calculate_citation_precision(valid_citations, available_source_count=3) == 1.0

        # Contains phantom citation [5]
        mixed_citations = [
            {"source_index": 1},
            {"source_index": 5},
        ]
        assert calculate_citation_precision(mixed_citations, available_source_count=3) == 0.5

        # Empty citations
        assert calculate_citation_precision([], available_source_count=3) == 1.0

    def test_hallucination_rate(self):
        claims = [
            {"claim_text": "C1", "is_supported": True},
            {"claim_text": "C2", "is_supported": False},
        ]
        assert calculate_hallucination_rate(claims) == 0.5

    def test_evaluate_generation_report(self):
        claims = [
            {"claim_text": "C1", "is_supported": True},
            {"claim_text": "C2", "is_supported": False},
        ]
        citations = [
            {"source_index": 1},
            {"source_index": 99},  # phantom
        ]

        report = evaluate_generation(
            claims=claims,
            citations=citations,
            available_source_count=2,
            is_abstained=False,
            expected_abstention=False,
        )

        assert report.groundedness_score == 0.5
        assert report.citation_precision == 0.5
        assert report.hallucination_rate == 0.5
        assert report.phantom_citations_detected == 1
        assert report.abstention_accuracy == 1.0
        assert report.is_fully_grounded is False


class TestRAGEvaluator:
    """Tests for holistic benchmark dataset evaluation."""

    def test_evaluate_dataset_averages(self):
        sample1 = RAGBenchmarkSample(
            query="Q1",
            ground_truth_doc_ids=["d1"],
            retrieved_doc_ids=["d1", "d2"],
            generated_text="Answer 1 [1]",
            claims=[{"is_supported": True}],
            citations=[{"source_index": 1}],
            available_source_count=2,
            is_abstained=False,
            expected_abstention=False,
        )

        sample2 = RAGBenchmarkSample(
            query="Q2",
            ground_truth_doc_ids=["d3"],
            retrieved_doc_ids=["d4", "d5"],  # miss
            generated_text="No evidence",
            claims=[],
            citations=[],
            available_source_count=0,
            is_abstained=True,
            expected_abstention=True,
        )

        evaluator = RAGEvaluator()
        benchmark_report = evaluator.evaluate_dataset([sample1, sample2])

        assert benchmark_report.sample_count == 2
        assert benchmark_report.mean_recall_at_5 == 0.5  # 1.0 + 0.0 / 2
        assert benchmark_report.abstention_accuracy == 1.0
        assert benchmark_report.mean_groundedness == 1.0


class TestObservabilityMetricsAndCollector:
    """Tests for Prometheus metrics collector and exposition formatting."""

    def test_counter_and_gauge_operations(self):
        collector = MetricsCollector()

        # Counter
        collector.increment_counter("rag_requests_total", 1.0, {"endpoint": "/api/search"})
        collector.increment_counter("rag_requests_total", 2.0, {"endpoint": "/api/search"})
        assert collector.get_counter_value("rag_requests_total", {"endpoint": "/api/search"}) == 3.0

        # Gauge
        collector.set_gauge("rag_active_requests", 5.0)
        assert collector.get_gauge_value("rag_active_requests") == 5.0

    def test_histogram_recording(self):
        collector = MetricsCollector()
        collector.record_histogram("rag_request_duration_seconds", 0.025, {"endpoint": "/api/chat"})
        collector.record_histogram("rag_request_duration_seconds", 0.080, {"endpoint": "/api/chat"})

        exposition = collector.generate_prometheus_exposition()
        assert "# HELP rag_request_duration_seconds" in exposition
        assert "# TYPE rag_request_duration_seconds histogram" in exposition
        assert "rag_request_duration_seconds_bucket" in exposition
        assert "rag_request_duration_seconds_sum" in exposition
        assert "rag_request_duration_seconds_count" in exposition

    def test_prometheus_exposition_format(self):
        collector = MetricsCollector()
        collector.increment_counter("rag_cache_hits_total", 1.0, {"tier": "L1_EXACT"})
        collector.increment_counter("rag_cache_hits_total", 2.0, {"tier": "L2_VECTOR"})

        text = collector.generate_prometheus_exposition()
        assert "# HELP rag_cache_hits_total" in text
        assert "# TYPE rag_cache_hits_total counter" in text
        assert 'rag_cache_hits_total{tier="L1_EXACT"} 1.0' in text
        assert 'rag_cache_hits_total{tier="L2_VECTOR"} 2.0' in text


class TestSecurityAuditLogger:
    """Tests for structured security audit logging."""

    @pytest.mark.asyncio
    async def test_record_audit_event_with_mock_session(self):
        from unittest.mock import MagicMock
        mock_session = AsyncMock()
        mock_session.add = MagicMock()


        record = await SecurityAuditLogger.record_event(
            actor_id="admin_user_01",
            actor_role="admin",
            action="API_KEY_REVOCATION",
            target_resource="api_keys/key_123",
            ip_address="192.168.1.100",
            user_agent="pytest-client",
            details={"reason": "routine_rotation"},
            session=mock_session,
        )

        assert record.actor_id == "admin_user_01"
        assert record.action == "API_KEY_REVOCATION"
        assert record.details["reason"] == "routine_rotation"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


class TestMetricsEndpoint:
    """Tests for GET /metrics endpoint via FastAPI test client."""

    @pytest.mark.asyncio
    async def test_get_metrics_endpoint_returns_prometheus_format(self):
        # Register a metric
        metrics_collector.increment_counter("rag_requests_total", 1.0, {"endpoint": "/metrics_test"})

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/metrics")
            assert resp.status_code == 200
            assert "text/plain" in resp.headers["content-type"]
            body = resp.text
            assert "# HELP" in body
            assert "# TYPE" in body
            assert "rag_requests_total" in body

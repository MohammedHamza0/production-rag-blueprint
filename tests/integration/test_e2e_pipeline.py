"""End-to-end integration tests simulating complete production user journeys."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from src.api.dependencies import (
    get_db_session,
    get_hybrid_retriever,
    get_llm_provider,
    get_semantic_cache,
)
from src.domain.entities import RetrievedSource
from src.infrastructure.models import DocumentChunkModel, DocumentModel, IngestionJobModel
from src.llm.mock_provider import MockLLMProvider
from src.main import app
from src.workers.tasks import ingest_document_task


class MockScalarResult:
    def __init__(self, items):
        self._items = items

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None

    def scalars(self):
        return self

    def all(self):
        return self._items


@pytest.mark.asyncio
async def test_end_to_end_upload_ingest_search_and_stream(tmp_path: Path):
    """Complete E2E workflow: Upload -> Ingest -> Search -> Chat Stream -> Cached Turn."""
    # 1. Prepare sample markdown document
    sample_file = tmp_path / "architecture_blueprint.md"
    content = (
        "# Enterprise RAG Blueprint\n\n"
        "This blueprint provides a production-grade multi-tier retrieval architecture.\n\n"
        "## Hybrid Search Specification\n\n"
        "Combines dense HNSW cosine vector search with PostgreSQL GIN full-text indexes using Reciprocal Rank Fusion."
    )
    sample_file.write_text(content, encoding="utf-8")

    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()

    mock_doc = DocumentModel(
        id=doc_id,
        title="Enterprise RAG Blueprint",
        author="Staff AI Engineer",
        file_name="architecture_blueprint.md",
        file_size=len(content.encode("utf-8")),
        file_type="text/markdown",
        status="pending",
        checkpoint_stage="VALIDATED",
        language="en",
    )

    mock_job = IngestionJobModel(
        id=job_id,
        job_type="ingest-document",
        target_id=doc_id,
        status="pending",
        progress=10,
        details={},
    )

    stored_chunks = []

    mock_db = AsyncMock()

    def mock_add(entity):
        if isinstance(entity, DocumentChunkModel):
            stored_chunks.append(entity)

    mock_db.add = MagicMock(side_effect=mock_add)

    async def mock_execute(statement):
        stmt_str = str(statement)
        if "documents" in stmt_str and "SELECT" in stmt_str.upper():
            return MockScalarResult([mock_doc])
        if "ingestion_jobs" in stmt_str and "SELECT" in stmt_str.upper():
            return MockScalarResult([mock_job])
        if "document_chunks" in stmt_str and "SELECT" in stmt_str.upper():
            return MockScalarResult(stored_chunks)
        return MockScalarResult([])

    mock_db.execute.side_effect = mock_execute
    mock_db.commit = AsyncMock()

    # Configure dependency overrides
    app.dependency_overrides[get_db_session] = lambda: mock_db
    app.dependency_overrides[get_llm_provider] = lambda: MockLLMProvider()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Step A: Ingest the document through the background worker pipeline
        ingest_res = await ingest_document_task(
            document_id=str(doc_id),
            file_path=str(sample_file),
            job_id=str(job_id),
            session_override=mock_db,
        )
        assert ingest_res["status"] == "completed"
        assert mock_doc.status == "completed"
        assert mock_doc.checkpoint_stage == "INDEXED"

        # Step B: Inspect document status via REST endpoint
        status_resp = await client.get(f"/api/documents/{doc_id}/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["status"] == "completed"
        assert status_data["checkpoint_stage"] == "INDEXED"

        # Step C: Execute direct hybrid search
        mock_retriever = AsyncMock()
        mock_retriever.search.return_value = [
            RetrievedSource(
                source_index=1,
                document_id=doc_id,
                document_title="Enterprise RAG Blueprint",
                document_author="Staff AI Engineer",
                work_id=None,
                work_title=None,
                edition_id=None,
                edition_title=None,
                edition_language="en",
                chunk_language="en",
                content="Combines dense HNSW cosine vector search with PostgreSQL GIN full-text indexes.",
                page_number=1,
                chapter_title="Hybrid Search Specification",
                chunk_id=uuid.uuid4(),
                combined_score=0.92,
                vector_similarity=0.90,
                text_score=0.88,
            )
        ]
        app.dependency_overrides[get_hybrid_retriever] = lambda: mock_retriever

        search_resp = await client.post(
            "/api/search",
            json={"query": "How does hybrid search combine dense and sparse?", "match_count": 5},
        )
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert len(search_data["results"]) >= 1
        assert search_data["results"][0]["document_title"] == "Enterprise RAG Blueprint"

        # Step D: Chat Stream SSE Flow
        mock_cache = AsyncMock()
        mock_cache.find_hit.return_value = None  # Miss on first query
        mock_cache.store.return_value = True
        app.dependency_overrides[get_semantic_cache] = lambda: mock_cache

        chat_payload = {
            "message": "Explain the hybrid search architecture of the blueprint.",
            "responseLanguage": "en",
        }
        chat_resp = await client.post("/api/chat/stream", json=chat_payload)
        assert chat_resp.status_code == 200
        assert "text/event-stream" in chat_resp.headers["content-type"]
        body = chat_resp.text
        assert "event: conversation" in body
        assert "event: sources" in body
        assert "event: chunk" in body
        assert "event: text_done" in body
        assert "event: done" in body
        assert "groundingAudit" in body

        # Step E: Subsequent query hits semantic cache
        mock_cache.find_hit.return_value = {
            "tier": "L1_EXACT",
            "response_text": "Cached explanation of hybrid search architecture.",
            "sources": [{"source_index": 1, "document_title": "Enterprise RAG Blueprint"}],
            "suggestions": ["Tell me about semantic caching"],
            "grounding_audit": {"status": "VERIFIED", "groundedness_score": 1.0},
        }

        cached_chat_resp = await client.post("/api/chat/stream", json=chat_payload)
        assert cached_chat_resp.status_code == 200
        cached_body = cached_chat_resp.text
        assert "event: chunk" in cached_body
        assert "Cached explanation of hybrid search architecture" in cached_body
        assert '"tier": "L1_EXACT"' in cached_body

"""Unit tests for background workers, Taskiq broker, and staged ingestion checkpoints."""

import math
from pathlib import Path
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq_redis import ListQueueBroker

from src.infrastructure.models import DocumentChunkModel, DocumentModel, IngestionJobModel
from src.workers.broker import broker
from src.workers.tasks import (
    _generate_dense_embedding,
    ingest_document_task,
    reindex_collection_task,
)


class MockScalarResult:
    """Mock helper for SQLAlchemy execute().scalars() and scalar_one_or_none()."""

    def __init__(self, items: List[Any]):
        self._items = items

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None

    def scalars(self):
        return self

    def all(self):
        return self._items


class TestWorkerBroker:
    """Tests for Taskiq broker configuration and registered tasks."""

    def test_broker_queue_configuration(self):
        assert isinstance(broker, ListQueueBroker)
        assert broker.queue_name == "rag_ingestion_queue"

    def test_tasks_registered_on_broker(self):
        available_tasks = list(broker.get_all_tasks().keys())
        assert "ingest_document_task" in available_tasks
        assert "reindex_collection_task" in available_tasks


class TestDenseEmbeddingGenerator:
    """Tests for deterministic 768-dim fallback dense embedding generator."""

    def test_embedding_dimension_and_normalization(self):
        text = "هندسة معمارية التوليد المعزز بالاسترجاع (RAG)"
        vec = _generate_dense_embedding(text, dim=768)

        assert len(vec) == 768
        norm = math.sqrt(sum(x * x for x in vec))
        assert math.isclose(norm, 1.0, rel_tol=1e-4)

    def test_empty_text_returns_zero_vector(self):
        vec = _generate_dense_embedding("", dim=768)
        assert len(vec) == 768
        assert all(x == 0.0 for x in vec)

    def test_deterministic_output_for_same_text(self):
        text = "Consistent test phrase for embedding"
        vec1 = _generate_dense_embedding(text)
        vec2 = _generate_dense_embedding(text)
        assert vec1 == vec2


class TestIngestDocumentTask:
    """Tests for staged pipeline execution, checkpoints, and resilience."""

    @pytest.mark.asyncio
    async def test_full_pipeline_ingestion_success(self, tmp_path: Path):
        # 1. Create source test markdown file
        md_file = tmp_path / "rag_spec.md"
        content = (
            "# Introduction to RAG\n\n"
            "Retrieval-Augmented Generation enhances language models with private knowledge.\n\n"
            "## Storage Layer\n\n"
            "PostgreSQL and pgvector store HNSW vector indexes.\n\n"
            "## Caching Layer\n\n"
            "Redis handles exact L1 caching while pgvector provides L2 semantic equivalence."
        )
        md_file.write_text(content, encoding="utf-8")

        # 2. Setup mock DB entities
        doc_id = uuid.uuid4()
        job_id = uuid.uuid4()

        mock_doc = DocumentModel(
            id=doc_id,
            title="RAG Spec",
            author="Staff AI Engineer",
            file_name="rag_spec.md",
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
            progress=0,
            details={},
        )

        # 3. Setup mock AsyncSession
        mock_session = AsyncMock(spec=AsyncSession)
        stored_chunks: List[DocumentChunkModel] = []

        def mock_add(entity):
            if isinstance(entity, DocumentChunkModel):
                stored_chunks.append(entity)

        mock_session.add.side_effect = mock_add

        async def mock_execute(statement):
            stmt_str = str(statement)
            if "documents" in stmt_str and "SELECT" in stmt_str.upper():
                return MockScalarResult([mock_doc])
            if "ingestion_jobs" in stmt_str and "SELECT" in stmt_str.upper():
                return MockScalarResult([mock_job])
            return MockScalarResult([])

        mock_session.execute.side_effect = mock_execute
        mock_session.commit = AsyncMock()

        # 4. Execute task
        res = await ingest_document_task(
            document_id=str(doc_id),
            file_path=str(md_file),
            job_id=str(job_id),
            session_override=mock_session,
        )

        # 5. Verify results
        assert res["status"] == "completed"
        assert res["document_id"] == str(doc_id)
        assert res["total_chunks"] > 0

        # Verify DocumentModel state
        assert mock_doc.status == "completed"
        assert mock_doc.checkpoint_stage == "INDEXED"
        assert mock_doc.total_chunks == res["total_chunks"]

        # Verify IngestionJobModel state
        assert mock_job.status == "completed"
        assert mock_job.progress == 100
        assert mock_job.completed_at is not None

        # Verify generated chunks
        assert len(stored_chunks) > 0
        parents = [c for c in stored_chunks if c.chunk_type == "PARENT"]
        children = [c for c in stored_chunks if c.chunk_type == "CHILD"]
        assert len(parents) >= 1
        assert len(children) >= 1

        # Check child chunk properties
        child = children[0]
        assert child.depth == 1
        assert child.parent_chunk_id is not None
        assert len(child.embedding) == 768
        assert child.context_header is not None
        assert "[Document: " in child.context_header
        assert "Introduction to RAG" in child.context_header


    @pytest.mark.asyncio
    async def test_idempotent_skip_when_already_completed(self, tmp_path: Path):
        md_file = tmp_path / "dummy.txt"
        md_file.write_text("Sample", encoding="utf-8")

        doc_id = uuid.uuid4()
        mock_doc = DocumentModel(
            id=doc_id,
            title="Completed Doc",
            status="completed",
            checkpoint_stage="INDEXED",
            total_chunks=15,
            total_pages=3,
        )

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute.return_value = MockScalarResult([mock_doc])

        res = await ingest_document_task(
            document_id=str(doc_id),
            file_path=str(md_file),
            session_override=mock_session,
            force_restart=False,
        )

        assert res["status"] == "already_completed"
        assert res["total_chunks"] == 15
        assert res["total_pages"] == 3

    @pytest.mark.asyncio
    async def test_missing_file_records_failed_stage(self, tmp_path: Path):
        doc_id = uuid.uuid4()
        job_id = uuid.uuid4()

        mock_doc = DocumentModel(
            id=doc_id,
            title="Missing File Doc",
            status="pending",
            checkpoint_stage="INIT",
        )
        mock_job = IngestionJobModel(
            id=job_id,
            job_type="ingest-document",
            target_id=doc_id,
            status="pending",
        )

        mock_session = AsyncMock(spec=AsyncSession)

        async def mock_execute(statement):
            stmt_str = str(statement)
            if "documents" in stmt_str and "SELECT" in stmt_str.upper():
                return MockScalarResult([mock_doc])
            if "ingestion_jobs" in stmt_str and "SELECT" in stmt_str.upper():
                return MockScalarResult([mock_job])
            return MockScalarResult([])

        mock_session.execute.side_effect = mock_execute
        mock_session.commit = AsyncMock()

        missing_path = tmp_path / "non_existent_file.pdf"

        with pytest.raises(FileNotFoundError):
            await ingest_document_task(
                document_id=str(doc_id),
                file_path=str(missing_path),
                job_id=str(job_id),
                session_override=mock_session,
            )

        assert mock_doc.status == "failed"
        assert "FAILED" in mock_doc.checkpoint_stage
        assert mock_doc.error_message is not None
        assert "Source file not found" in mock_doc.error_message

        assert mock_job.status == "failed"
        assert "Source file not found" in mock_job.error_message

    @pytest.mark.asyncio
    async def test_document_not_found_raises_value_error(self):
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute.return_value = MockScalarResult([])

        with pytest.raises(ValueError) as exc_info:
            await ingest_document_task(
                document_id=str(uuid.uuid4()),
                file_path="dummy.txt",
                session_override=mock_session,
            )

        assert "not found in database" in str(exc_info.value)


class TestReindexCollectionTask:
    """Tests for batch reindexing of collection chunks."""

    @pytest.mark.asyncio
    async def test_reindex_collection_updates_chunk_embeddings(self):
        col_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        mock_doc = DocumentModel(
            id=doc_id,
            collection_id=col_id,
            title="Collection Document",
            embedding_model="gemini-embedding-2",
        )

        mock_chunks = [
            DocumentChunkModel(
                id=uuid.uuid4(),
                document_id=doc_id,
                chunk_index=0,
                content="Chunk 1 content for reindexing",
                embedding=[0.01] * 768,
                embedding_model="gemini-embedding-2",
            ),
            DocumentChunkModel(
                id=uuid.uuid4(),
                document_id=doc_id,
                chunk_index=1,
                content="Chunk 2 content for reindexing",
                embedding=[0.02] * 768,
                embedding_model="gemini-embedding-2",
            ),
        ]

        mock_session = AsyncMock(spec=AsyncSession)

        async def mock_execute(statement):
            stmt_str = str(statement)
            if "documents" in stmt_str and "SELECT" in stmt_str.upper():
                return MockScalarResult([mock_doc])
            if "document_chunks" in stmt_str and "SELECT" in stmt_str.upper():
                return MockScalarResult(mock_chunks)
            return MockScalarResult([])

        mock_session.execute.side_effect = mock_execute
        mock_session.commit = AsyncMock()

        res = await reindex_collection_task(
            collection_id=str(col_id),
            new_embedding_model="gemini-embedding-3",
            session_override=mock_session,
        )

        assert res["status"] == "completed"
        assert res["chunks_updated"] == 2
        assert res["documents_updated"] == 1
        assert mock_doc.embedding_model == "gemini-embedding-3"
        assert mock_chunks[0].embedding_model == "gemini-embedding-3"
        assert mock_chunks[1].embedding_model == "gemini-embedding-3"
        assert len(mock_chunks[0].embedding) == 768

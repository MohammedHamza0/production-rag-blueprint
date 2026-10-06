"""Document management and ingestion upload API endpoints."""

import hashlib
from pathlib import Path
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.dependencies import get_db_session
from src.core.exceptions import DocumentParsingError, UnsupportedMimeTypeError
from src.domain.schemas import DocumentStatusResponse, UploadDocumentResponse
from src.infrastructure.models import DocumentModel, IngestionJobModel
from src.ingestion.parsers.factory import ParserFactory

router = APIRouter(prefix="/api/documents", tags=["Documents"])


@router.post("/upload", response_model=UploadDocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    collection_id: Optional[uuid.UUID] = Form(None),
    session: AsyncSession = Depends(get_db_session),
):
    """Uploads a document for background parsing, chunking, embedding, and indexing."""
    filename = file.filename or "uploaded_file"
    ext = Path(filename).suffix.lower()

    # Validate file extension
    factory = ParserFactory()
    try:
        factory.get_parser_for_path(filename)
    except DocumentParsingError as dpe:
        raise UnsupportedMimeTypeError(mime_type=file.content_type or ext, allowed=[".pdf", ".docx", ".md", ".txt"])

    # Read content and compute SHA-256 hash
    content_bytes = await file.read()
    file_hash = hashlib.sha256(content_bytes).hexdigest()
    file_size = len(content_bytes)

    # Check deduplication in database
    existing_stmt = select(DocumentModel).where(DocumentModel.file_hash == file_hash)
    existing_doc = (await session.execute(existing_stmt)).scalar_one_or_none()

    if existing_doc:
        return UploadDocumentResponse(
            document_id=existing_doc.id,
            job_id=str(uuid.uuid4()),
            status=existing_doc.status,
            message="Document with identical SHA-256 hash already exists. Existing record linked.",
        )

    # Create new document record
    doc_id = uuid.uuid4()
    job_id = str(uuid.uuid4())
    doc_title = title or Path(filename).stem.replace("_", " ").title()

    new_doc = DocumentModel(
        id=doc_id,
        collection_id=collection_id,
        title=doc_title,
        author=author or "Unknown",
        file_name=filename,
        file_size=file_size,
        file_type=file.content_type or "text/plain",
        file_hash=file_hash,
        status="pending",
        checkpoint_stage="VALIDATED",
    )
    new_job = IngestionJobModel(
        id=uuid.UUID(job_id),
        job_type="ingest-document",
        target_id=doc_id,
        status="pending",
        progress=10,
        details={"checkpoint_stage": "VALIDATED", "file_name": filename},
    )
    session.add(new_doc)
    session.add(new_job)
    await session.commit()



    return UploadDocumentResponse(
        document_id=doc_id,
        job_id=job_id,
        status="pending",
        message="Document uploaded successfully and queued for background ingestion pipeline.",
    )


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
):
    """Retrieves document ingestion status, progress percentage, and current checkpoint."""
    stmt = select(DocumentModel).where(DocumentModel.id == document_id)
    doc = (await session.execute(stmt)).scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    # Compute progress percentage based on checkpoint stage
    progress_map = {
        "PENDING": 0,
        "VALIDATED": 20,
        "PARSED": 40,
        "CHUNKED": 60,
        "EMBEDDED": 80,
        "INDEXED": 100,
    }
    progress = 100 if doc.status == "completed" else progress_map.get(doc.checkpoint_stage or "PENDING", 25)

    return DocumentStatusResponse(
        document_id=doc.id,
        status=doc.status,
        checkpoint_stage=doc.checkpoint_stage,
        total_chunks=doc.total_chunks or 0,
        progress_percent=progress,
        error_message=doc.error_message,
    )


@router.get("")
async def list_documents(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
):
    """Lists ingested documents with pagination."""
    stmt = select(DocumentModel).order_by(desc(DocumentModel.created_at)).limit(limit).offset(offset)
    docs = (await session.execute(stmt)).scalars().all()

    return [
        {
            "id": d.id,
            "title": d.title,
            "author": d.author,
            "status": d.status,
            "checkpoint_stage": d.checkpoint_stage,
            "total_chunks": d.total_chunks,
            "created_at": d.created_at,
        }
        for d in docs
    ]

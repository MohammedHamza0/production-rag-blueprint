"""Pydantic v2 schemas for API contracts, streaming events, and validation."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChatHistoryTurn(BaseModel):
    """Single prior dialogue message turn."""
    role: str = Field(..., description="Role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text content")


class ChatStreamRequest(BaseModel):
    """Incoming request contract for /api/chat/stream."""
    model_config = ConfigDict(extra="ignore")

    message: str = Field(..., min_length=1, max_length=4000, description="User query or instruction")
    conversation_id: Optional[uuid.UUID] = Field(default=None, alias="conversationId")
    history: List[ChatHistoryTurn] = Field(default_factory=list)
    persona_mode: str = Field(default="standard", alias="personaMode")
    response_language: str = Field(default="auto", alias="responseLanguage")
    evidence_language: str = Field(default="all", alias="evidenceLanguage")
    document_ids: Optional[List[uuid.UUID]] = Field(default=None, alias="documentIds")
    collection_id: Optional[uuid.UUID] = Field(default=None, alias="collectionId")
    target_message_id: Optional[uuid.UUID] = Field(default=None, alias="targetMessageId")
    target_content: Optional[str] = Field(default=None, alias="targetContent")
    action_type: Optional[str] = Field(default=None, alias="actionType")  # 'transform', 'clarify', etc.
    filter_hash: Optional[str] = Field(default=None, alias="filterHash")
    query_embedding: Optional[List[float]] = Field(default=None, alias="queryEmbedding")


class SourceCardSchema(BaseModel):
    """Public representation of a verified source card."""
    source_index: int
    original_source_index: Optional[int] = None
    document_id: str
    document_title: str
    document_author: Optional[str] = None
    edition_title: Optional[str] = None
    chapter_title: Optional[str] = None
    page_number: Optional[int] = None
    volume_number: Optional[int] = None
    breadcrumb: Optional[str] = None
    content: str
    has_footnotes: bool = False
    footnotes_data: List[Dict[str, Any]] = Field(default_factory=list)
    vector_similarity: float = 0.0
    text_score: float = 0.0
    combined_score: float = 0.0


class StructuredCitationSchema(BaseModel):
    """Entity representation of a specific citation claim."""
    citation_index: int
    source_index: int
    document_title: str
    page_number: Optional[int] = None
    chapter_title: Optional[str] = None
    claim_text: Optional[str] = None
    entailment_score: float = 0.0
    is_supported: bool = True


class GroundingAuditSchema(BaseModel):
    """Public grounding audit metadata returned at stream completion."""
    status: str
    groundedness_score: float
    claim_entailment_score: float
    claims_verified: int
    total_claims: int
    structured_citations: List[StructuredCitationSchema] = Field(default_factory=list)


class ChatStreamDonePayload(BaseModel):
    """Payload emitted on SSE event: done."""
    conversation_id: Optional[str]
    model: str
    reconciled_sources: List[SourceCardSchema] = Field(default_factory=list)
    sanitized_text: Optional[str] = None
    grounding_audit: GroundingAuditSchema
    suggestions: List[str] = Field(default_factory=list)
    abstained: bool = False
    cached: bool = False


class DirectSearchRequest(BaseModel):
    """Request contract for direct /api/search without generation."""
    query: str = Field(..., min_length=1, max_length=1000)
    match_count: int = Field(default=8, ge=1, le=50)
    document_ids: Optional[List[uuid.UUID]] = None
    collection_id: Optional[uuid.UUID] = None
    languages: Optional[List[str]] = None
    vector_weight: float = Field(default=0.5, alias="vectorWeight")
    keyword_weight: float = Field(default=0.5, alias="keywordWeight")
    filter_languages: Optional[List[str]] = Field(default=None, alias="filterLanguages")



class DirectSearchResultItem(BaseModel):
    """Single item returned from direct search."""
    chunk_id: str
    document_id: str
    document_title: str
    chapter_title: Optional[str] = None
    page_number: Optional[int] = None
    volume_number: Optional[int] = None
    breadcrumb: Optional[str] = None
    content: str
    combined_score: float
    vector_similarity: float
    text_score: float
    rank: Optional[int] = None



class DirectSearchResponse(BaseModel):
    """Response contract for direct search endpoint."""
    query: str
    match_count: int
    results: List[DirectSearchResultItem]


class DocumentUploadResponse(BaseModel):
    """Response returned upon accepting a document upload."""
    document_id: uuid.UUID
    job_id: str
    status: str
    message: str


class DocumentStatusResponse(BaseModel):
    """Response for checking asynchronous ingestion status."""
    document_id: uuid.UUID
    status: str  # pending, processing, completed, failed
    checkpoint_stage: Optional[str] = None
    total_chunks: int = 0
    total_pages: Optional[int] = None
    progress_percent: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class HealthCheckResponse(BaseModel):
    """Response contract for /api/health/liveness."""
    status: str = "ok"
    timestamp: datetime = Field(default_factory=utc_now)
    version: str = "1.0.0"
    database: Optional[str] = None
    redis: Optional[str] = None


class ReadinessCheckResponse(BaseModel):
    """Response contract for /api/health/readiness."""
    status: str  # ready, degraded, unavailable
    timestamp: datetime = Field(default_factory=utc_now)
    checks: Dict[str, str] = Field(default_factory=dict)


# Standard Aliases
UploadDocumentResponse = DocumentUploadResponse
HealthResponse = HealthCheckResponse
DirectSearchItem = DirectSearchResultItem

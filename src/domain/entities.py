"""Domain entities representing knowledge, chunks, citations, and conversation state."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Collection:
    """Logical grouping of works or documents (e.g. Journal Issues, Library Volumes)."""
    id: uuid.UUID
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    icon: str = "book-open"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Work:
    """Intellectual or artistic creation (FRBR Work Level)."""
    id: uuid.UUID
    canonical_title: str
    original_title: Optional[str] = None
    canonical_author: Optional[str] = None
    original_language: str = "ar"
    domain: Optional[str] = None
    provisional: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Edition:
    """Published manifestation of a Work (FRBR Edition Level)."""
    id: uuid.UUID
    work_id: uuid.UUID
    edition_title: Optional[str] = None
    editor: Optional[str] = None
    translator: Optional[str] = None
    publisher: Optional[str] = None
    publication_year: Optional[int] = None
    publication_place: Optional[str] = None
    edition_language: str = "ar"
    is_translation: bool = False
    isbn: Optional[str] = None
    provisional: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Document:
    """Physical uploaded file or article instance (FRBR Item Level)."""
    id: uuid.UUID
    edition_id: Optional[uuid.UUID] = None
    collection_id: Optional[uuid.UUID] = None
    title: str = ""
    author: Optional[str] = None
    file_name: Optional[str] = None
    file_type: str = "article"
    file_size: int = 0
    file_hash: Optional[str] = None
    total_pages: int = 0
    total_chunks: int = 0
    status: str = "pending"  # pending, processing, completed, failed
    checkpoint_stage: str = "INIT"
    checkpoint_data: Dict[str, Any] = field(default_factory=dict)
    embedding_model: str = "gemini-embedding-2"
    embedding_version: str = "v2"
    category: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    language: str = "ar"
    cover_url: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class DocumentChunk:
    """Granular passage or section representation (Parent or Child)."""
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    content: str
    chunk_type: str = "CHILD"  # PARENT, CHILD, STANDALONE
    parent_chunk_id: Optional[uuid.UUID] = None
    depth: int = 1
    clean_content: Optional[str] = None
    chapter_title: Optional[str] = None
    page_number: Optional[int] = None
    token_count: int = 0
    language: str = "ar"
    embedding: Optional[List[float]] = None
    embedding_model: str = "gemini-embedding-2"
    embedding_version: str = "v2"
    content_hash: Optional[str] = None
    section_path: List[str] = field(default_factory=list)
    context_header: Optional[str] = None
    volume_number: Optional[int] = None
    volume_title: Optional[str] = None
    breadcrumb: Optional[str] = None
    has_footnotes: bool = False
    footnotes_data: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class RetrievedSource:
    """Unified evidence entity returned from hybrid search and passed to LLM."""
    source_index: int
    document_id: uuid.UUID
    document_title: str
    document_author: Optional[str]
    work_id: Optional[uuid.UUID]
    work_title: Optional[str]
    edition_id: Optional[uuid.UUID]
    edition_title: Optional[str]
    edition_language: str
    chunk_language: str
    content: str
    chapter_title: Optional[str] = None
    page_number: Optional[int] = None
    chunk_id: Optional[uuid.UUID] = None
    chunk_index: int = 0
    chunk_type: str = "CHILD"
    parent_chunk_id: Optional[uuid.UUID] = None
    depth: int = 1
    volume_number: Optional[int] = None
    volume_title: Optional[str] = None
    breadcrumb: Optional[str] = None
    has_footnotes: bool = False
    footnotes_data: List[Dict[str, Any]] = field(default_factory=list)
    vector_similarity: float = 0.0
    text_score: float = 0.0
    combined_score: float = 0.0
    original_source_index: Optional[int] = None
    expanded_content: Optional[str] = None
    parent_content: Optional[str] = None
    is_expanded: bool = False


@dataclass
class StructuredCitation:
    """Resolved first-class citation linking answer claim to physical source."""
    citation_index: int
    raw_match: str
    source_index: int
    document_id: str
    document_title: str
    page_number: Optional[int] = None
    chapter_title: Optional[str] = None
    breadcrumb: Optional[str] = None
    claim_text: Optional[str] = None
    entailment_score: float = 0.0
    is_supported: bool = True


@dataclass
class GroundingAudit:
    """Verification report of the generation groundedness and citation validity."""
    status: str = "VERIFIED"  # VERIFIED, WEAK_SUPPORT, ABSTAINED, EMPTY, CACHED
    total_citations: int = 0
    valid_citations: int = 0
    invalid_count: int = 0
    groundedness_score: float = 100.0
    claim_entailment_score: float = 100.0
    claims_count: int = 0
    supported_claims_count: int = 0
    structured_citations: List[StructuredCitation] = field(default_factory=list)
    reconciled_sources: List[RetrievedSource] = field(default_factory=list)


@dataclass
class ConversationMemory:
    """Atomic episodic fact or preference extracted from dialogue turns."""
    id: uuid.UUID
    conversation_id: uuid.UUID
    turn_index: int
    memory_type: str  # entity, preference, constraint, fact
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    created_at: datetime = field(default_factory=utc_now)

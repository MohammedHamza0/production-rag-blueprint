"""SQLAlchemy 2.0 declarative database models with pgvector and full-text search."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BIGINT,
    BOOLEAN,
    FLOAT,
    INTEGER,
    JSON,
    SMALLINT,
    TEXT,
    TIMESTAMP,
    VARCHAR,
    Column,
    ForeignKey,
    Index,
    String,
    Table,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base class with custom JSONB representation."""
    pass


class CollectionModel(Base):
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(TEXT, nullable=False)
    slug: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    icon: Mapped[str] = mapped_column(TEXT, default="book-open")
    metadata_: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now, onupdate=utc_now)

    documents = relationship("DocumentModel", back_populates="collection")


class WorkModel(Base):
    __tablename__ = "works"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_title: Mapped[str] = mapped_column(TEXT, nullable=False)
    original_title: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    canonical_author: Mapped[Optional[str]] = mapped_column(TEXT, default="Author")
    original_language: Mapped[str] = mapped_column(TEXT, default="ar")
    domain: Mapped[Optional[str]] = mapped_column(TEXT, default="General")
    provisional: Mapped[bool] = mapped_column(BOOLEAN, default=False)
    metadata_: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now, onupdate=utc_now)

    editions = relationship("EditionModel", back_populates="work", cascade="all, delete-orphan")


class EditionModel(Base):
    __tablename__ = "editions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    work_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("works.id", ondelete="CASCADE"), nullable=False)
    edition_title: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    editor: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    translator: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    publication_year: Mapped[Optional[int]] = mapped_column(INTEGER, nullable=True)
    publication_place: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    edition_language: Mapped[str] = mapped_column(TEXT, default="ar")
    is_translation: Mapped[bool] = mapped_column(BOOLEAN, default=False)
    isbn: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    provisional: Mapped[bool] = mapped_column(BOOLEAN, default=False)
    metadata_: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now, onupdate=utc_now)

    work = relationship("WorkModel", back_populates="editions")
    documents = relationship("DocumentModel", back_populates="edition")


class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    edition_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("editions.id", ondelete="SET NULL"), nullable=True)
    collection_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(TEXT, nullable=False)
    author: Mapped[Optional[str]] = mapped_column(TEXT, default="Author")
    file_name: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    file_type: Mapped[str] = mapped_column(TEXT, default="article")
    file_size: Mapped[int] = mapped_column(BIGINT, default=0)
    file_hash: Mapped[Optional[str]] = mapped_column(VARCHAR(64), nullable=True)
    total_pages: Mapped[int] = mapped_column(INTEGER, default=0)
    total_chunks: Mapped[int] = mapped_column(INTEGER, default=0)
    status: Mapped[str] = mapped_column(TEXT, default="pending")  # pending, processing, completed, failed
    checkpoint_stage: Mapped[str] = mapped_column(VARCHAR(32), default="INIT")
    checkpoint_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    embedding_model: Mapped[str] = mapped_column(TEXT, default="gemini-embedding-2")
    embedding_version: Mapped[str] = mapped_column(TEXT, default="v2")
    category: Mapped[Optional[str]] = mapped_column(TEXT, default="General")
    description: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    tags: Mapped[List[str]] = mapped_column(ARRAY(TEXT), default=list)
    language: Mapped[str] = mapped_column(TEXT, default="ar")
    cover_url: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    metadata_: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now, onupdate=utc_now)

    collection = relationship("CollectionModel", back_populates="documents")
    edition = relationship("EditionModel", back_populates="documents")
    chunks = relationship("DocumentChunkModel", back_populates="document", cascade="all, delete-orphan")


class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    parent_chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=True)
    chunk_index: Mapped[int] = mapped_column(INTEGER, nullable=False)
    chunk_type: Mapped[str] = mapped_column(TEXT, default="CHILD")  # PARENT, CHILD, STANDALONE
    depth: Mapped[int] = mapped_column(INTEGER, default=1)
    content: Mapped[str] = mapped_column(TEXT, nullable=False)
    clean_content: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    chapter_title: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(INTEGER, nullable=True)
    token_count: Mapped[int] = mapped_column(INTEGER, default=0)
    language: Mapped[str] = mapped_column(VARCHAR(16), default="ar")
    embedding = mapped_column(Vector(768), nullable=True)
    embedding_model: Mapped[str] = mapped_column(TEXT, default="gemini-embedding-2")
    embedding_version: Mapped[str] = mapped_column(TEXT, default="v2")
    content_hash: Mapped[Optional[str]] = mapped_column(VARCHAR(64), nullable=True)
    section_path: Mapped[List[str]] = mapped_column(ARRAY(TEXT), default=list)
    context_header: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    volume_number: Mapped[Optional[int]] = mapped_column(INTEGER, nullable=True)
    volume_title: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    breadcrumb: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    has_footnotes: Mapped[bool] = mapped_column(BOOLEAN, default=False)
    footnotes_data: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    metadata_: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)

    # Multi-lingual Full-Text TSVectors (generated always as stored in PostgreSQL)
    tsv = mapped_column(TSVECTOR, nullable=True)
    tsv_simple = mapped_column(TSVECTOR, nullable=True)
    tsv_english = mapped_column(TSVECTOR, nullable=True)
    tsv_spanish = mapped_column(TSVECTOR, nullable=True)
    tsv_portuguese = mapped_column(TSVECTOR, nullable=True)

    document = relationship("DocumentModel", back_populates="chunks")
    parent_chunk = relationship("DocumentChunkModel", remote_side=[id], backref="child_chunks")


class ChatConversationModel(Base):
    __tablename__ = "chat_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(TEXT, default="محادثة جديدة")
    user_identifier: Mapped[str] = mapped_column(TEXT, default="local-user")
    persona_mode: Mapped[str] = mapped_column(TEXT, default="standard")
    system_prompt_override: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    selected_document_ids: Mapped[Optional[List[uuid.UUID]]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    temperature: Mapped[float] = mapped_column(FLOAT, default=0.2)
    is_shared: Mapped[bool] = mapped_column(BOOLEAN, default=False)
    share_id: Mapped[Optional[str]] = mapped_column(VARCHAR(64), unique=True, nullable=True)
    shared_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    session_state: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        default=lambda: {
            "goal": None,
            "decisions": [],
            "turn_count": 0,
            "constraints": [],
            "preferences": {},
            "active_topic": None,
            "last_condensed_turn": 0,
            "unresolved_questions": [],
        },
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now, onupdate=utc_now)

    messages = relationship("ChatMessageModel", back_populates="conversation", cascade="all, delete-orphan")
    memories = relationship("ChatConversationMemoryModel", back_populates="conversation", cascade="all, delete-orphan")


class ChatMessageModel(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(TEXT, nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(TEXT, nullable=False)
    sources: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    citations: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    suggestions: Mapped[List[str]] = mapped_column(JSONB, default=list)
    token_usage: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    grounding_audit: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    persona_mode: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    feedback: Mapped[int] = mapped_column(SMALLINT, default=0)
    feedback_tag: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)

    conversation = relationship("ChatConversationModel", back_populates="messages")


class ChatConversationMemoryModel(Base):
    __tablename__ = "chat_conversation_memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False)
    turn_index: Mapped[int] = mapped_column(INTEGER, nullable=False)
    memory_type: Mapped[str] = mapped_column(VARCHAR(50), nullable=False)
    content: Mapped[str] = mapped_column(TEXT, nullable=False)
    metadata_: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(BOOLEAN, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)

    conversation = relationship("ChatConversationModel", back_populates="memories")


class SemanticQueryCacheModel(Base):
    __tablename__ = "semantic_query_cache"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_text: Mapped[str] = mapped_column(TEXT, nullable=False)
    normalized_query: Mapped[str] = mapped_column(TEXT, nullable=False, default="")
    query_embedding = mapped_column(Vector(768), nullable=False)
    response_text: Mapped[str] = mapped_column(TEXT, nullable=False)
    sources: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    suggestions: Mapped[List[str]] = mapped_column(JSONB, default=list)
    persona: Mapped[str] = mapped_column(VARCHAR(50), default="standard")
    language: Mapped[str] = mapped_column(VARCHAR(10), default="ar")
    answer_shape: Mapped[str] = mapped_column(VARCHAR(50), default="standard")
    filter_hash: Mapped[str] = mapped_column(VARCHAR(64), default="ALL")
    embedding_model: Mapped[str] = mapped_column(VARCHAR(64), default="gemini-embedding-2")
    corpus_version: Mapped[str] = mapped_column(VARCHAR(32), default="v1")
    schema_version: Mapped[str] = mapped_column(VARCHAR(32), default="v1")
    format_directive: Mapped[str] = mapped_column(VARCHAR(32), default="none")
    hit_count: Mapped[int] = mapped_column(INTEGER, default=1)
    grounding_audit: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)
    last_hit_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class APIKeyModel(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(VARCHAR(64), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(VARCHAR(12), nullable=False)
    role: Mapped[str] = mapped_column(VARCHAR(20), default="reader")  # admin, ingestor, reader
    rate_limit_rpm: Mapped[int] = mapped_column(INTEGER, default=120)
    is_active: Mapped[bool] = mapped_column(BOOLEAN, default=True)
    metadata_: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)
    expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class IngestionJobModel(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(TEXT, nullable=False)  # ingest-document, reindex, embed
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(TEXT, default="pending")  # pending, active, completed, failed
    progress: Mapped[int] = mapped_column(INTEGER, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)


class SecurityAuditLogModel(Base):
    __tablename__ = "security_audit_logs"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now)
    actor_id: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    actor_role: Mapped[str] = mapped_column(VARCHAR(20), nullable=False)
    action: Mapped[str] = mapped_column(VARCHAR(100), nullable=False)
    target_resource: Mapped[Optional[str]] = mapped_column(VARCHAR(255), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(VARCHAR(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)


class SystemSettingModel(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(TEXT, primary_key=True)
    value: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=utc_now, onupdate=utc_now)

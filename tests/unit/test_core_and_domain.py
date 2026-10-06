"""Unit tests for Core Infrastructure and Domain Layer (Milestone M1)."""

import os
import uuid
import pytest
from pydantic import ValidationError

from src.core.config import AppSettings
from src.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    DocumentParsingError,
    FileTooLargeError,
    InsufficientEvidenceError,
    ProviderAPIError,
    RAGBaseException,
    RateLimitExceededError,
    UnsupportedMimeTypeError,
    VectorDimensionMismatchError,
)
from src.core.logging import (
    bind_correlation_id,
    get_correlation_id,
    setup_logging,
)
from src.core.security import (
    KeyVault,
    generate_boundary_nonce,
    hash_api_key,
    is_valid_uuid,
)
from src.domain.entities import (
    Collection,
    ConversationMemory,
    Document,
    DocumentChunk,
    Edition,
    GroundingAudit,
    RetrievedSource,
    StructuredCitation,
    Work,
)
from src.domain.protocols import (
    Chunker,
    DocumentParser,
    EmbeddingProvider,
    HybridRetriever,
    LLMProvider,
    RerankerProtocol,
    SemanticCacheStore,
)
from src.domain.schemas import (
    ChatHistoryTurn,
    ChatStreamRequest,
    DirectSearchRequest,
    DirectSearchResponse,
    DirectSearchResultItem,
    DocumentStatusResponse,
    DocumentUploadResponse,
    GroundingAuditSchema,
    SourceCardSchema,
    StructuredCitationSchema,
)
from src.infrastructure.models import (
    Base,
    CollectionModel,
    DocumentChunkModel,
    DocumentModel,
    EditionModel,
    SemanticQueryCacheModel,
    WorkModel,
)


class TestCoreConfiguration:
    """Verifies AppSettings, model validators, and environment parsing."""

    def test_default_settings(self):
        settings = AppSettings(
            _env_file=None,
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
        )
        assert settings.default_chat_model == "gemini-3.5-flash-lite"
        assert settings.default_fallback_model == "gemini-1.5-flash"
        assert settings.default_embedding_model == "gemini-embedding-2"
        assert settings.embedding_dimension == 768
        assert settings.rrf_k_constant == 60.0
        assert settings.retrieval_top_k == 8
        assert settings.diversity_max_per_book == 2

    def test_rejects_unsupported_gemini_2_5(self):
        with pytest.raises(ValidationError) as exc_info:
            AppSettings(
                _env_file=None,
                DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/testdb",
                DEFAULT_CHAT_MODEL="gemini-2.5-flash",
            )
        assert "no longer supported" in str(exc_info.value)


class TestKeyVaultAndSecurity:
    """Verifies deceptive KeyVault assembly, hashing, and nonces."""

    def test_key_vault_reassembly_deceptive_slices(self):
        fake_env = {
            "TadabburApiKey": "AIzaSyPart1",
            "ApiSecret": "Part2Middle",
            "ApiSalt": "Part3End",
        }
        assembled = KeyVault.resolve_gemini_api_key(fake_env)
        assert assembled == "AIzaSyPart1Part2MiddlePart3End"
        assert KeyVault.has_gemini_key(fake_env) is True

    def test_key_vault_fallback_to_direct_key(self):
        fake_env = {"GEMINI_API_KEY": "AIzaSyDirectKey123"}
        assembled = KeyVault.resolve_gemini_api_key(fake_env)
        assert assembled == "AIzaSyDirectKey123"

    def test_key_vault_split_and_reconstruct(self):
        original = "AIzaSyABC123456789xyz"
        p1, p2, p3 = KeyVault.split_key(original)
        assert f"{p1}{p2}{p3}" == original

    def test_hash_api_key(self):
        raw_key = "rag_live_sec_1234567890abcdef"
        key_hash, key_prefix = hash_api_key(raw_key)
        assert len(key_hash) == 64
        assert key_prefix == "rag_live_s"

    def test_boundary_nonce(self):
        n1 = generate_boundary_nonce(12)
        n2 = generate_boundary_nonce(12)
        assert len(n1) == 12
        assert len(n2) == 12
        assert n1 != n2

    def test_is_valid_uuid(self):
        real_uuid = str(uuid.uuid4())
        assert is_valid_uuid(real_uuid) is True
        assert is_valid_uuid(uuid.uuid4()) is True
        assert is_valid_uuid("not-a-valid-uuid") is False
        assert is_valid_uuid("") is False
        assert is_valid_uuid(None) is False


class TestLoggingAndCorrelation:
    """Verifies correlation ID propagation in asyncio context."""

    def test_correlation_id_lifecycle(self):
        test_id = "req_test_12345"
        bind_correlation_id(test_id)
        assert get_correlation_id() == test_id


class TestDomainEntitiesAndSchemas:
    """Verifies domain entities and Pydantic schemas."""

    def test_create_work_and_edition(self):
        work_id = uuid.uuid4()
        work = Work(
            id=work_id,
            canonical_title="مجلة تدبر",
            domain="الدراسات القرآنية",
        )
        assert work.id == work_id
        assert work.original_language == "ar"

        edition = Edition(
            id=uuid.uuid4(),
            work_id=work_id,
            edition_title="العدد 21",
            publication_year=2026,
        )
        assert edition.work_id == work_id
        assert edition.edition_title == "العدد 21"

    def test_chat_stream_request_schema(self):
        req = ChatStreamRequest(
            message="ما مقاصد قصة استخلاف آدم؟",
            personaMode="academic_researcher",
            history=[ChatHistoryTurn(role="user", content="السلام عليكم")],
        )
        assert req.message == "ما مقاصد قصة استخلاف آدم؟"
        assert req.persona_mode == "academic_researcher"
        assert len(req.history) == 1

    def test_direct_search_schemas(self):
        req = DirectSearchRequest(query="أحكام الزكاة", match_count=5)
        assert req.match_count == 5

        res = DirectSearchResponse(
            query="أحكام الزكاة",
            match_count=1,
            results=[
                DirectSearchResultItem(
                    chunk_id=str(uuid.uuid4()),
                    document_id=str(uuid.uuid4()),
                    document_title="الفقه الميسر",
                    content="نص الفقه...",
                    combined_score=0.045,
                    vector_similarity=0.89,
                    text_score=0.92,
                )
            ],
        )
        assert len(res.results) == 1
        assert res.results[0].document_title == "الفقه الميسر"


class TestDatabaseModels:
    """Verifies SQLAlchemy declarative models mappings."""

    def test_document_chunk_model_columns(self):
        assert DocumentChunkModel.__tablename__ == "document_chunks"
        cols = {c.name for c in DocumentChunkModel.__table__.columns}
        assert "embedding" in cols
        assert "parent_chunk_id" in cols
        assert "tsv" in cols
        assert "tsv_simple" in cols
        assert "tsv_english" in cols
        assert "tsv_spanish" in cols
        assert "tsv_portuguese" in cols

    def test_semantic_query_cache_columns(self):
        assert SemanticQueryCacheModel.__tablename__ == "semantic_query_cache"
        cols = {c.name for c in SemanticQueryCacheModel.__table__.columns}
        assert "query_embedding" in cols
        assert "persona" in cols
        assert "language" in cols
        assert "answer_shape" in cols
        assert "filter_hash" in cols
        assert "format_directive" in cols

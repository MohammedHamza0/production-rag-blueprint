"""Global application settings and configuration management using Pydantic Settings v2."""

from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Central configuration for the Production RAG Blueprint."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment & Identity
    environment: str = Field(default="production", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_origins: List[str] = Field(default=["*"], alias="CORS_ORIGINS")

    # Database Persistence (PostgreSQL + asyncpg)
    database_url: str = Field(
        default="postgresql+asyncpg://rag_user:rag_secure_password_2026@localhost:5432/rag_blueprint_db",
        alias="DATABASE_URL",
    )
    database_pool_size: int = Field(default=20, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")

    # Redis Cache, Mutex & Broker
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # AI Models (Gemini 3.5 default, gemini-2.5 strictly excluded)
    default_llm_provider: str = Field(default="gemini", alias="DEFAULT_LLM_PROVIDER")
    default_chat_model: str = Field(default="gemini-3.5-flash-lite", alias="DEFAULT_CHAT_MODEL")
    default_fallback_model: str = Field(default="gemini-1.5-flash", alias="DEFAULT_FALLBACK_MODEL")
    default_embedding_model: str = Field(default="gemini-embedding-2", alias="DEFAULT_EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=768, alias="EMBEDDING_DIMENSION")
    embedding_version: str = Field(default="v2", alias="EMBEDDING_VERSION")

    @property
    def gemini_default_model(self) -> str:
        return self.default_chat_model

    @property
    def gemini_fallback_model(self) -> str:
        return self.default_fallback_model

    def get_gemini_api_key(self) -> str:
        """Resolves Gemini API key using KeyVault or direct key."""
        from src.core.security import KeyVault
        key = KeyVault.resolve_gemini_api_key()
        if key:
            return key
        return self.gemini_api_key_direct or ""

    # Deceptive KeyVault Partitions
    api_key_part1: Optional[str] = Field(default=None, alias="TadabburApiKey")
    api_key_part2: Optional[str] = Field(default=None, alias="ApiSecret")
    api_key_part3: Optional[str] = Field(default=None, alias="ApiSalt")
    gemini_api_key_direct: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")

    # Retrieval & RRF Tuning
    rrf_k_constant: float = Field(default=60.0, alias="RRF_K_CONSTANT")
    retrieval_top_k: int = Field(default=8, alias="RETRIEVAL_TOP_K")
    diversity_max_per_book: int = Field(default=2, alias="DIVERSITY_MAX_PER_BOOK")

    # Semantic Cache Multi-Dimensional Scoping
    semantic_cache_similarity_threshold: float = Field(default=0.87, alias="SEMANTIC_CACHE_SIMILARITY_THRESHOLD")
    semantic_cache_direct_hit_threshold: float = Field(default=0.97, alias="SEMANTIC_CACHE_DIRECT_HIT_THRESHOLD")
    semantic_cache_verifier_enabled: bool = Field(default=True, alias="SEMANTIC_CACHE_VERIFIER_ENABLED")
    semantic_cache_ttl_days: int = Field(default=7, alias="SEMANTIC_CACHE_TTL_DAYS")
    l1_redis_cache_ttl_seconds: int = Field(default=86400, alias="L1_REDIS_CACHE_TTL_SECONDS")

    # Ingestion & Chunking
    chunker_max_tokens: int = Field(default=280, alias="CHUNKER_MAX_TOKENS")
    chunker_overlap_tokens: int = Field(default=50, alias="CHUNKER_OVERLAP_TOKENS")
    parent_section_max_tokens: int = Field(default=1000, alias="PARENT_SECTION_MAX_TOKENS")

    # Context & Token Budgeting
    chat_target_input_budget: int = Field(default=12000, alias="CHAT_TARGET_INPUT_BUDGET")
    chat_hard_max_input: int = Field(default=16384, alias="CHAT_HARD_MAX_INPUT")
    chat_max_output_tokens: int = Field(default=8192, alias="CHAT_MAX_OUTPUT_TOKENS")

    # Rate Limiting
    rate_limit_user_rpm: int = Field(default=120, alias="RATE_LIMIT_USER_RPM")
    rate_limit_guest_rpm: int = Field(default=15, alias="RATE_LIMIT_GUEST_RPM")

    @field_validator("default_chat_model", "default_fallback_model")
    @classmethod
    def validate_chat_model(cls, v: str) -> str:
        """Enforces that deprecated/unsupported models like gemini-2.5 are rejected."""
        lower = v.lower()
        if "gemini-2.5" in lower:
            raise ValueError(
                f"Model '{v}' is no longer supported and is strictly deprecated. "
                "Use 'gemini-3.5-flash-lite', 'gemini-3.5-flash', or 'gemini-1.5-flash'."
            )
        return v


# Global singleton settings instance
settings = AppSettings()


def get_settings() -> AppSettings:
    """Returns the singleton AppSettings instance."""
    return settings

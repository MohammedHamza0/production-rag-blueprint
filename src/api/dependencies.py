"""Dependency injection container for FastAPI routes."""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from src.caching.coordinator import SemanticCacheCoordinator
from src.caching.equivalence_verifier import CacheEquivalenceVerifier
from src.caching.l1_redis import L1RedisCache
from src.caching.l2_vector import L2VectorSemanticCache
from src.caching.single_flight import SingleFlightMutex
from src.citations.citation_sanitizer import CitationSanitizer
from src.citations.evidence_evaluator import EvidenceEvaluator
from src.context.context_manager import AdaptiveContextManager
from src.context.intent_router import IntentRouter
from src.context.policy_guard import PolicyGuard
from src.context.shape_detector import ShapeDetector
from src.core.config import get_settings
from src.domain.protocols import HybridRetriever, LLMProvider, SemanticCacheStore
from src.infrastructure.database import async_session_factory
from src.infrastructure.redis_client import get_redis_client
from src.llm.factory import LLMFactory
from src.retrieval.context_expander import ContextExpander
from src.retrieval.diversity_guard import DiversityGuard
from src.retrieval.hybrid_retriever import HybridRRFRetriever
from src.retrieval.language_router import LanguageRouter
from src.retrieval.query_transformer import QueryTransformer


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields a database session from the async session factory."""
    async with async_session_factory() as session:
        yield session


def get_llm_provider() -> LLMProvider:
    """Provides the configured LLMProvider instance."""
    factory = LLMFactory()
    return factory.get_provider()


def get_policy_guard() -> PolicyGuard:
    return PolicyGuard()


def get_intent_router() -> IntentRouter:
    return IntentRouter()


def get_shape_detector() -> ShapeDetector:
    return ShapeDetector()


def get_context_manager() -> AdaptiveContextManager:
    return AdaptiveContextManager()


def get_evidence_evaluator() -> EvidenceEvaluator:
    return EvidenceEvaluator()


def get_citation_sanitizer() -> CitationSanitizer:
    return CitationSanitizer()


def get_hybrid_retriever() -> HybridRetriever:
    return HybridRRFRetriever(session_factory=async_session_factory)


def get_semantic_cache() -> SemanticCacheStore:
    redis = get_redis_client()
    llm = get_llm_provider()
    l1 = L1RedisCache(redis_client=redis)
    l2 = L2VectorSemanticCache(session_factory=async_session_factory)
    verifier = CacheEquivalenceVerifier(redis_client=redis, llm_provider=llm)
    single_flight = SingleFlightMutex(redis_client=redis)
    return SemanticCacheCoordinator(
        l1_cache=l1,
        l2_cache=l2,
        verifier=verifier,
        single_flight=single_flight,
    )

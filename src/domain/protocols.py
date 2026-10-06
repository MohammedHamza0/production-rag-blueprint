"""Clean Architecture structural protocols (interfaces) for dependency inversion."""

from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, Tuple, runtime_checkable
import uuid
from src.domain.entities import DocumentChunk, RetrievedSource


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for abstracting generative model providers (Gemini, OpenAI, Claude, Ollama)."""

    async def generate_stream(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Streams raw text tokens asynchronously."""
        ...

    async def generate_json(
        self,
        system_instruction: str,
        user_prompt: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generates a structured JSON object response."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for dense vector embedding generation."""

    async def get_embedding(self, text: str) -> List[float]:
        """Generates a dense vector embedding for a single text."""
        ...

    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings for a batch of texts with concurrency and backoff."""
        ...


@runtime_checkable
class DocumentParser(Protocol):
    """Protocol for extracting text, structure, and metadata from documents."""

    async def extract(self, file_path: str) -> Dict[str, Any]:
        """Extracts structured pages, sections, and metadata from a file."""
        ...


@runtime_checkable
class Chunker(Protocol):
    """Protocol for chunking parsed documents into Parent sections and Child chunks."""

    def chunk_document(
        self,
        raw_text: str,
        doc_title: str,
        doc_author: Optional[str] = None,
        parent_target_tokens: int = 1000,
        child_target_tokens: int = 280,
        child_overlap_tokens: int = 50,
        lang: str = "ar",
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Splits text into (parents, children) lists with context headers."""
        ...


@runtime_checkable
class HybridRetriever(Protocol):
    """Protocol for 5-way hybrid search execution."""

    async def search(
        self,
        query_text: str,
        query_embedding: List[float],
        match_count: int = 8,
        filter_doc_ids: Optional[List[uuid.UUID]] = None,
        filter_collection_id: Optional[uuid.UUID] = None,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        filter_languages: Optional[List[str]] = None,
        preferred_languages: Optional[List[str]] = None,
    ) -> List[RetrievedSource]:
        """Executes hybrid RRF search across vector and lexical channels."""
        ...


@runtime_checkable
class SemanticCacheStore(Protocol):
    """Protocol for two-tier multi-dimensional semantic query cache."""

    async def find_hit(
        self,
        query_text: str,
        query_embedding: List[float],
        persona: str,
        language: str,
        answer_shape: str,
        filter_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """Searches L1 and L2 cache tiers with multi-dimensional partition filtering."""
        ...

    async def store(
        self,
        query_text: str,
        normalized_query: str,
        query_embedding: List[float],
        response_text: str,
        sources: List[Dict[str, Any]],
        suggestions: List[str],
        persona: str,
        language: str,
        answer_shape: str,
        filter_hash: str,
        grounding_audit: Dict[str, Any],
    ) -> bool:
        """Stores a validated grounded answer in L1 and L2 cache tiers."""
        ...


@runtime_checkable
class RerankerProtocol(Protocol):
    """Protocol for rescoring candidate passages."""

    async def rerank(
        self,
        query: str,
        candidates: List[RetrievedSource],
        top_k: int = 8,
    ) -> List[RetrievedSource]:
        """Scores and re-ranks candidate passages for maximal relevance."""
        ...

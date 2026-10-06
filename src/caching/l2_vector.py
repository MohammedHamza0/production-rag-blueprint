"""Tier 2: Vector semantic cache using PostgreSQL pgvector with hard partition scoping."""

import json
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.logging import get_logger

logger = get_logger("caching.l2_vector")


class L2VectorSemanticCache:
    """PostgreSQL pgvector backed L2 semantic cache with multi-dimensional partitioning."""

    def __init__(
        self,
        session_factory,
        similarity_threshold: float = 0.87,
        corpus_version: str = "v1",
        schema_version: str = "v1",
        embedding_model: str = "gemini-embedding-2",
    ):
        self.session_factory = session_factory
        self.similarity_threshold = similarity_threshold
        self.corpus_version = corpus_version
        self.schema_version = schema_version
        self.embedding_model = embedding_model

    async def find_candidate(
        self,
        query_embedding: List[float],
        persona: str,
        language: str,
        answer_shape: str,
        filter_hash: str,
        threshold: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Queries pgvector semantic cache enforcing hard scoping dimensions."""
        sim_threshold = threshold if threshold is not None else self.similarity_threshold
        embedding_str = "[" + ",".join(f"{x:.6f}" for x in query_embedding) + "]"

        # Call stored function find_semantic_cache_candidates
        query_sql = text("""
            SELECT 
                id,
                query_text,
                normalized_query,
                response_text,
                sources,
                suggestions,
                persona,
                language,
                answer_shape,
                filter_hash,
                corpus_version,
                grounding_audit,
                similarity
            FROM find_semantic_cache_candidates(
                query_embedding := :query_embedding::vector,
                p_persona := :persona,
                p_language := :language,
                p_answer_shape := :answer_shape,
                p_filter_hash := :filter_hash,
                similarity_threshold := :similarity_threshold,
                p_corpus_version := :corpus_version,
                match_count := 1
            );
        """)

        async with self.session_factory() as session:
            try:
                res = await session.execute(
                    query_sql,
                    {
                        "query_embedding": embedding_str,
                        "persona": persona,
                        "language": language,
                        "answer_shape": answer_shape,
                        "filter_hash": filter_hash,
                        "similarity_threshold": sim_threshold,
                        "corpus_version": self.corpus_version,
                    },
                )
                row = res.first()
                if not row:
                    return None

                # Asynchronously increment hit count
                update_sql = text("""
                    UPDATE semantic_query_cache 
                    SET hit_count = hit_count + 1, last_hit_at = NOW() 
                    WHERE id = :id;
                """)
                await session.execute(update_sql, {"id": row.id})
                await session.commit()

                # Parse JSON fields if returned as string/dict
                sources = row.sources if isinstance(row.sources, list) else json.loads(row.sources or "[]")
                suggestions = row.suggestions if isinstance(row.suggestions, list) else json.loads(row.suggestions or "[]")
                grounding = row.grounding_audit if isinstance(row.grounding_audit, dict) else json.loads(row.grounding_audit or "{}")

                candidate = {
                    "id": str(row.id),
                    "query_text": row.query_text,
                    "normalized_query": row.normalized_query,
                    "response_text": row.response_text,
                    "sources": sources,
                    "suggestions": suggestions,
                    "persona": row.persona,
                    "language": row.language,
                    "answer_shape": row.answer_shape,
                    "filter_hash": row.filter_hash,
                    "corpus_version": row.corpus_version,
                    "grounding_audit": grounding,
                    "similarity": float(row.similarity),
                    "tier": "L2",
                }
                logger.info(
                    "l2_cache_candidate_found",
                    candidate_id=str(row.id),
                    similarity=float(row.similarity),
                )
                return candidate

            except Exception as exc:
                logger.warning("l2_cache_query_failed", error=str(exc))
                return None

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
        """Stores a newly generated verified answer in L2 pgvector semantic cache."""
        embedding_str = "[" + ",".join(f"{x:.6f}" for x in query_embedding) + "]"

        insert_sql = text("""
            INSERT INTO semantic_query_cache (
                id,
                query_text,
                normalized_query,
                query_embedding,
                response_text,
                sources,
                suggestions,
                persona,
                language,
                answer_shape,
                filter_hash,
                embedding_model,
                corpus_version,
                schema_version,
                format_directive,
                hit_count,
                grounding_audit,
                created_at,
                last_hit_at,
                expires_at
            ) VALUES (
                gen_random_uuid(),
                :query_text,
                :normalized_query,
                :query_embedding::vector,
                :response_text,
                :sources::jsonb,
                :suggestions::jsonb,
                :persona,
                :language,
                :answer_shape,
                :filter_hash,
                :embedding_model,
                :corpus_version,
                :schema_version,
                'none',
                1,
                :grounding_audit::jsonb,
                NOW(),
                NOW(),
                NOW() + interval '7 days'
            )
            ON CONFLICT (normalized_query, persona, language, filter_hash, format_directive, embedding_model, corpus_version, schema_version)
            DO UPDATE SET 
                hit_count = semantic_query_cache.hit_count + 1,
                last_hit_at = NOW(),
                response_text = EXCLUDED.response_text,
                sources = EXCLUDED.sources,
                suggestions = EXCLUDED.suggestions,
                grounding_audit = EXCLUDED.grounding_audit;
        """)

        async with self.session_factory() as session:
            try:
                await session.execute(
                    insert_sql,
                    {
                        "query_text": query_text,
                        "normalized_query": normalized_query,
                        "query_embedding": embedding_str,
                        "response_text": response_text,
                        "sources": json.dumps(sources, ensure_ascii=False),
                        "suggestions": json.dumps(suggestions, ensure_ascii=False),
                        "persona": persona,
                        "language": language,
                        "answer_shape": answer_shape,
                        "filter_hash": filter_hash,
                        "embedding_model": self.embedding_model,
                        "corpus_version": self.corpus_version,
                        "schema_version": self.schema_version,
                        "grounding_audit": json.dumps(grounding_audit, ensure_ascii=False),
                    },
                )
                await session.commit()
                logger.info("l2_cache_stored_successfully", query=query_text[:40])
                return True
            except Exception as exc:
                logger.warning("l2_cache_store_failed", error=str(exc))
                await session.rollback()
                return False

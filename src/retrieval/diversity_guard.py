"""Diversity guard preventing document monopolization in retrieval results."""

from collections import defaultdict
from typing import List, Optional
from src.core.logging import get_logger
from src.domain.entities import RetrievedSource

logger = get_logger("retrieval.diversity_guard")


class DiversityGuard:
    """Filters candidate chunks to guarantee source and topical diversity."""

    def __init__(
        self,
        max_chunks_per_document: int = 3,
        max_chunks_per_chapter: int = 2,
    ):
        self.max_chunks_per_document = max_chunks_per_document
        self.max_chunks_per_chapter = max_chunks_per_chapter

    def enforce_diversity(
        self,
        candidates: List[RetrievedSource],
        target_count: int = 8,
    ) -> List[RetrievedSource]:
        """Applies diversity filtering to prevent any single document or chapter from saturating results."""
        if not candidates:
            return []

        if len(candidates) <= target_count and len({c.document_id for c in candidates}) > 1:
            return candidates[:target_count]

        doc_counts = defaultdict(int)
        chapter_counts = defaultdict(int)

        accepted: List[RetrievedSource] = []
        deferred: List[RetrievedSource] = []

        # Pass 1: Accept candidates meeting diversity constraints
        for chunk in candidates:
            doc_id = str(chunk.document_id)
            chapter_key = f"{doc_id}:{chunk.chapter_title or 'default'}"

            if (
                doc_counts[doc_id] < self.max_chunks_per_document
                and chapter_counts[chapter_key] < self.max_chunks_per_chapter
            ):
                accepted.append(chunk)
                doc_counts[doc_id] += 1
                chapter_counts[chapter_key] += 1
            else:
                deferred.append(chunk)

            if len(accepted) >= target_count:
                break

        # Pass 2: If diversity constraints produced fewer chunks than target_count, backfill from deferred
        if len(accepted) < target_count and deferred:
            logger.debug(
                "diversity_guard_backfilling",
                accepted=len(accepted),
                target=target_count,
                deferred=len(deferred),
            )
            for chunk in deferred:
                accepted.append(chunk)
                if len(accepted) >= target_count:
                    break

        return accepted

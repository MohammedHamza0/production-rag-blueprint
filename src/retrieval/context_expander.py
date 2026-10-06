"""Context expansion and page-level evidence aggregation.

Resolves full PARENT sections for retrieved child chunks to provide complete
unbroken context to the generative LLM, avoiding isolated fragments.
"""

from collections import defaultdict
from typing import Dict, List, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.logging import get_logger
from src.domain.entities import RetrievedSource
from src.infrastructure.models import DocumentChunkModel

logger = get_logger("retrieval.context_expander")


class ContextExpander:
    """Expands retrieved child chunks by resolving their parent sections and grouping pages."""

    async def expand_parents(
        self,
        sources: List[RetrievedSource],
        session: AsyncSession,
    ) -> List[RetrievedSource]:
        """Fetches parent chunks in a single batched query and attaches parent content."""
        if not sources:
            return []

        # Collect unique parent chunk IDs
        parent_ids = {
            s.parent_chunk_id
            for s in sources
            if s.parent_chunk_id is not None
        }

        if not parent_ids:
            return sources

        try:
            stmt = select(
                DocumentChunkModel.id,
                DocumentChunkModel.content,
                DocumentChunkModel.chapter_title,
                DocumentChunkModel.breadcrumb,
            ).where(DocumentChunkModel.id.in_(parent_ids))

            result = await session.execute(stmt)
            parent_lookup: Dict[uuid.UUID, Dict[str, str]] = {
                row.id: {
                    "content": row.content,
                    "chapter_title": row.chapter_title or "",
                    "breadcrumb": row.breadcrumb or "",
                }
                for row in result.all()
            }

            expanded_sources: List[RetrievedSource] = []
            for src in sources:
                if src.parent_chunk_id and src.parent_chunk_id in parent_lookup:
                    p_info = parent_lookup[src.parent_chunk_id]
                    src.parent_content = p_info["content"]
                    src.is_expanded = True
                    if not src.chapter_title and p_info["chapter_title"]:
                        src.chapter_title = p_info["chapter_title"]
                    if not src.breadcrumb and p_info["breadcrumb"]:
                        src.breadcrumb = p_info["breadcrumb"]
                expanded_sources.append(src)

            return expanded_sources

        except Exception as exc:
            logger.warning("parent_expansion_failed", error=str(exc))
            return sources

    @staticmethod
    def group_by_page(sources: List[RetrievedSource]) -> List[RetrievedSource]:
        """Groups multiple child chunks from the same document and page into a single consolidated source."""
        if len(sources) <= 1:
            return sources

        grouped: Dict[str, List[RetrievedSource]] = defaultdict(list)
        for s in sources:
            key = f"{s.document_id}:{s.page_number if s.page_number is not None else s.chapter_title}"
            grouped[key].append(s)

        consolidated: List[RetrievedSource] = []
        for group in grouped.values():
            if len(group) == 1:
                consolidated.append(group[0])
            else:
                # Merge multiple chunks from same page/section
                primary = max(group, key=lambda x: x.combined_score)
                # Combine unique text contents in sequence
                merged_contents = []
                seen_texts = set()
                for item in sorted(group, key=lambda x: x.source_index):
                    if item.content not in seen_texts:
                        merged_contents.append(item.content)
                        seen_texts.add(item.content)

                consolidated_content = "\n\n---\n\n".join(merged_contents)
                consolidated.append(
                    RetrievedSource(
                        source_index=primary.source_index,
                        document_id=primary.document_id,
                        document_title=primary.document_title,
                        document_author=primary.document_author,
                        work_id=primary.work_id,
                        work_title=primary.work_title,
                        edition_id=primary.edition_id,
                        edition_title=primary.edition_title,
                        edition_language=primary.edition_language,
                        chunk_language=primary.chunk_language,
                        content=consolidated_content,
                        page_number=primary.page_number,
                        chapter_title=primary.chapter_title,
                        chunk_id=primary.chunk_id,
                        parent_chunk_id=primary.parent_chunk_id,
                        vector_similarity=primary.vector_similarity,
                        text_score=primary.text_score,
                        combined_score=primary.combined_score,
                        parent_content=primary.parent_content,
                        is_expanded=primary.is_expanded,
                    )
                )

        # Sort by original best score
        consolidated.sort(key=lambda x: x.combined_score, reverse=True)
        for rank_idx, item in enumerate(consolidated, start=1):
            item.source_index = rank_idx

        return consolidated

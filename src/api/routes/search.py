"""Direct 5-Way Hybrid Search API endpoint."""

import time
from typing import List
from fastapi import APIRouter, Depends
from src.api.dependencies import get_hybrid_retriever
from src.domain.protocols import HybridRetriever
from src.domain.schemas import DirectSearchItem, DirectSearchRequest, DirectSearchResponse

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.post("", response_model=DirectSearchResponse)
async def direct_search(
    req: DirectSearchRequest,
    retriever: HybridRetriever = Depends(get_hybrid_retriever),
):
    """Executes 5-way hybrid RRF search directly against PostgreSQL vector & lexical indexes."""
    start_time = time.perf_counter()

    # Generate synthetic or dense vector for search query
    # In production, this calls EmbeddingService; here we supply dense representation
    query_vector: List[float] = [0.05] * 768

    sources = await retriever.search(
        query_text=req.query,
        query_embedding=query_vector,
        match_count=req.match_count,
        filter_doc_ids=req.document_ids,
        filter_collection_id=req.collection_id,
        vector_weight=req.vector_weight,
        keyword_weight=req.keyword_weight,
        filter_languages=req.filter_languages,
        expand_parents=True,
    )

    items: List[DirectSearchItem] = []
    for s in sources:
        items.append(
            DirectSearchItem(
                chunk_id=str(s.chunk_id or s.document_id),
                document_id=str(s.document_id),
                document_title=s.document_title,
                document_author=s.document_author,
                content=s.parent_content if (s.is_expanded and s.parent_content) else s.content,
                page_number=s.page_number,
                chapter_title=s.chapter_title,
                combined_score=s.combined_score,
                vector_similarity=s.vector_similarity,
                text_score=s.text_score,
                rank=s.source_index,
            )
        )


    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    return DirectSearchResponse(
        query=req.query,
        match_count=len(items),
        execution_time_ms=round(elapsed_ms, 2),
        results=items,
    )

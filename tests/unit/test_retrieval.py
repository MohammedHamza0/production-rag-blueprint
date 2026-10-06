"""Comprehensive unit tests for the 5-way hybrid retrieval engine."""

from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest
from src.domain.entities import RetrievedSource
from src.domain.protocols import HybridRetriever
from src.retrieval.context_expander import ContextExpander
from src.retrieval.diversity_guard import DiversityGuard
from src.retrieval.hybrid_retriever import HybridRRFRetriever
from src.retrieval.language_router import LanguageRouter
from src.retrieval.query_transformer import QueryTransformer


class TestLanguageRouter:
    """Tests for language classification and dynamic RRF weighting."""

    def setup_method(self):
        self.router = LanguageRouter()

    def test_classify_arabic_conceptual_query(self):
        res = self.router.classify_query("ما الفرق بين التجزئة الهيكلية والتجزئة الدلالية؟")
        assert res.detected_language == "ar"
        assert res.query_type == "conceptual"
        assert res.vector_weight == 0.75
        assert res.keyword_weight == 0.25
        assert "ar" in res.preferred_languages
        assert "en" in res.preferred_languages

    def test_classify_arabic_factoid_or_citation_query(self):
        res = self.router.classify_query("في أي صفحة ورد الحديث رقم 45؟")
        assert res.detected_language == "ar"
        assert res.query_type == "exact_factoid"
        assert res.vector_weight == 0.40
        assert res.keyword_weight == 0.60
        assert res.is_numeric_or_citation is True

    def test_classify_english_conceptual_query(self):
        res = self.router.classify_query("Explain how HNSW cosine search works in pgvector.")
        assert res.detected_language == "en"
        assert res.query_type == "conceptual"
        assert res.vector_weight == 0.75
        assert res.keyword_weight == 0.25

    def test_classify_english_quote_query(self):
        res = self.router.classify_query('What does "article 42" state?')
        assert res.query_type == "exact_factoid"
        assert res.vector_weight == 0.40
        assert res.keyword_weight == 0.60

    def test_classify_empty_query(self):
        res = self.router.classify_query("")
        assert res.query_type == "balanced"
        assert res.vector_weight == 0.65
        assert res.keyword_weight == 0.35


class TestQueryTransformer:
    """Tests for query normalization, boilerplate stripping, and sub-queries."""

    def setup_method(self):
        self.transformer = QueryTransformer()

    def test_strip_arabic_politeness_preambles(self):
        res = self.transformer.transform("من فضلك أريد أن أعرف عن معمارية RAG؟")
        assert "من فضلك" not in res.cleaned_query
        assert "أريد أن أعرف" not in res.cleaned_query
        assert "معمارية RAG" in res.cleaned_query
        assert res.is_transformed is True

    def test_strip_english_conversational_boilerplate(self):
        res = self.transformer.transform("Can you please tell me what is semantic caching?")
        assert "Can you please tell me" not in res.cleaned_query
        assert "semantic caching" in res.cleaned_query

    def test_extract_exact_quotes(self):
        query = 'Find details about "HNSW index" and «الاسترجاع الهجين»'
        res = self.transformer.transform(query)
        assert "HNSW index" in res.exact_phrases
        assert "الاسترجاع الهجين" in res.exact_phrases

    def test_comparative_query_decomposition(self):
        query = "PostgreSQL versus Redis in semantic caching"
        res = self.transformer.transform(query)
        assert len(res.sub_queries) == 2
        assert any("PostgreSQL" in s for s in res.sub_queries)
        assert any("Redis" in s for s in res.sub_queries)


class TestDiversityGuard:
    """Tests for preventing document/chapter monopolization."""

    def setup_method(self):
        self.guard = DiversityGuard(max_chunks_per_document=2, max_chunks_per_chapter=1)

    def test_enforces_document_cap(self):
        doc_a = uuid.uuid4()
        doc_b = uuid.uuid4()
        doc_c = uuid.uuid4()

        # Create 6 chunks from doc_a and 2 from doc_b, 1 from doc_c
        candidates = [
            RetrievedSource(
                source_index=i,
                document_id=doc_a,
                document_title="Doc A",
                document_author="Author A",
                work_id=None,
                work_title=None,
                edition_id=None,
                edition_title=None,
                edition_language="ar",
                chunk_language="ar",
                content=f"Doc A Chunk {i}",
                page_number=i,
                chapter_title=f"Chapter {i}",
                chunk_id=uuid.uuid4(),
                parent_chunk_id=None,
                vector_similarity=0.9 - (i * 0.01),
                text_score=0.8,
                combined_score=0.85 - (i * 0.01),
            )
            for i in range(1, 7)
        ]
        candidates.extend([
            RetrievedSource(
                source_index=7,
                document_id=doc_b,
                document_title="Doc B",
                document_author="Author B",
                work_id=None,
                work_title=None,
                edition_id=None,
                edition_title=None,
                edition_language="ar",
                chunk_language="ar",
                content="Doc B Chunk 1",
                page_number=1,
                chapter_title="Chapter B",
                chunk_id=uuid.uuid4(),
                parent_chunk_id=None,
                vector_similarity=0.75,
                text_score=0.70,
                combined_score=0.72,
            ),
            RetrievedSource(
                source_index=8,
                document_id=doc_c,
                document_title="Doc C",
                document_author="Author C",
                work_id=None,
                work_title=None,
                edition_id=None,
                edition_title=None,
                edition_language="ar",
                chunk_language="ar",
                content="Doc C Chunk 1",
                page_number=1,
                chapter_title="Chapter C",
                chunk_id=uuid.uuid4(),
                parent_chunk_id=None,
                vector_similarity=0.71,
                text_score=0.68,
                combined_score=0.70,
            ),
        ])

        diversified = self.guard.enforce_diversity(candidates, target_count=4)

        doc_ids = [c.document_id for c in diversified]
        assert doc_ids.count(doc_a) <= 2
        assert doc_b in doc_ids
        assert doc_c in doc_ids


class TestContextExpander:
    """Tests for parent chunk resolution and page grouping."""

    def test_group_by_page_merges_chunks_from_same_page(self):
        doc_id = uuid.uuid4()
        sources = [
            RetrievedSource(
                source_index=1,
                document_id=doc_id,
                document_title="Architecture Book",
                document_author="Architect",
                work_id=None,
                work_title=None,
                edition_id=None,
                edition_title=None,
                edition_language="en",
                chunk_language="en",
                content="First paragraph on page 10.",
                page_number=10,
                chapter_title="Storage",
                chunk_id=uuid.uuid4(),
                parent_chunk_id=None,
                vector_similarity=0.9,
                text_score=0.8,
                combined_score=0.85,
            ),
            RetrievedSource(
                source_index=2,
                document_id=doc_id,
                document_title="Architecture Book",
                document_author="Architect",
                work_id=None,
                work_title=None,
                edition_id=None,
                edition_title=None,
                edition_language="en",
                chunk_language="en",
                content="Second paragraph on page 10.",
                page_number=10,
                chapter_title="Storage",
                chunk_id=uuid.uuid4(),
                parent_chunk_id=None,
                vector_similarity=0.88,
                text_score=0.79,
                combined_score=0.83,
            ),
            RetrievedSource(
                source_index=3,
                document_id=doc_id,
                document_title="Architecture Book",
                document_author="Architect",
                work_id=None,
                work_title=None,
                edition_id=None,
                edition_title=None,
                edition_language="en",
                chunk_language="en",
                content="Paragraph from page 11.",
                page_number=11,
                chapter_title="Caching",
                chunk_id=uuid.uuid4(),
                parent_chunk_id=None,
                vector_similarity=0.85,
                text_score=0.75,
                combined_score=0.80,
            ),
        ]

        grouped = ContextExpander.group_by_page(sources)
        assert len(grouped) == 2  # Page 10 (merged) and Page 11

        page_10 = [g for g in grouped if g.page_number == 10][0]
        assert "First paragraph on page 10." in page_10.content
        assert "Second paragraph on page 10." in page_10.content

    @pytest.mark.asyncio
    async def test_expand_parents_enriches_sources(self):
        parent_id = uuid.uuid4()
        sources = [
            RetrievedSource(
                source_index=1,
                document_id=uuid.uuid4(),
                document_title="Doc",
                document_author="Author",
                work_id=None,
                work_title=None,
                edition_id=None,
                edition_title=None,
                edition_language="ar",
                chunk_language="ar",
                content="Child chunk content.",
                page_number=1,
                chapter_title=None,
                chunk_id=uuid.uuid4(),
                parent_chunk_id=parent_id,
                vector_similarity=0.85,
                text_score=0.80,
                combined_score=0.82,
            )
        ]

        # Mock session execute
        mock_row = MagicMock()
        mock_row.id = parent_id
        mock_row.content = "Complete parent chapter content."
        mock_row.chapter_title = "Chapter 1: Foundations"
        mock_row.breadcrumb = "Overview > Chapter 1"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        expander = ContextExpander()
        expanded = await expander.expand_parents(sources, mock_session)

        assert len(expanded) == 1
        assert expanded[0].is_expanded is True
        assert expanded[0].parent_content == "Complete parent chapter content."
        assert expanded[0].chapter_title == "Chapter 1: Foundations"


class TestHybridRRFRetriever:
    """Tests for protocol compliance and retrieval orchestrator."""

    def test_satisfies_protocol(self):
        mock_session_factory = MagicMock()
        retriever = HybridRRFRetriever(session_factory=mock_session_factory)
        assert isinstance(retriever, HybridRetriever)

    @pytest.mark.asyncio
    async def test_search_executes_query_and_maps_results(self):
        doc_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        mock_row = MagicMock()
        mock_row.id = chunk_id
        mock_row.document_id = doc_id
        mock_row.document_title = "Production RAG"
        mock_row.document_author = "Architect"
        mock_row.work_id = None
        mock_row.work_title = None
        mock_row.edition_id = None
        mock_row.edition_title = None
        mock_row.edition_language = "ar"
        mock_row.chunk_language = "ar"
        mock_row.content = "5-way hybrid RRF combines HNSW with GIN."
        mock_row.chapter_title = "Retrieval"
        mock_row.page_number = 5
        mock_row.chunk_index = 12
        mock_row.chunk_type = "CHILD"
        mock_row.parent_chunk_id = None
        mock_row.depth = 1
        mock_row.volume_number = 1
        mock_row.breadcrumb = "Search > Retrieval"
        mock_row.vector_similarity = 0.92
        mock_row.text_score = 0.85
        mock_row.combined_score = 0.89

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        # Context manager mock
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_session_factory.return_value.__aexit__.return_value = None

        retriever = HybridRRFRetriever(session_factory=mock_session_factory)
        results = await retriever.search(
            query_text="كيف يعمل البحث الهجين؟",
            query_embedding=[0.1] * 768,
            match_count=5,
            expand_parents=False,
        )

        assert len(results) == 1
        assert results[0].chunk_id == chunk_id
        assert results[0].document_title == "Production RAG"
        assert results[0].vector_similarity == 0.92
        assert results[0].combined_score == 0.89
        assert results[0].chapter_title == "Retrieval"

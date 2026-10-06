"""Comprehensive unit tests for Multi-Provider LLM, EvidenceEvaluator, and CitationSanitizer."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from src.citations.citation_sanitizer import CitationSanitizer
from src.citations.evidence_evaluator import EvidenceEvaluator
from src.core.exceptions import ConfigurationError
from src.domain.entities import GroundingAudit, RetrievedSource
from src.domain.protocols import LLMProvider
from src.llm.factory import LLMFactory
from src.llm.gemini_provider import GeminiProvider
from src.llm.mock_provider import MockLLMProvider


class TestGeminiProvider:
    """Tests for GeminiProvider model policy enforcement and REST calls."""

    def test_strictly_rejects_unsupported_gemini_2_5(self):
        with pytest.raises(ConfigurationError) as exc_info:
            GeminiProvider(api_key="fake-key", default_model="gemini-2.5-flash")
        assert "gemini-2.5-flash' is unsupported and deprecated" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_configuration_error(self):
        provider = GeminiProvider(api_key="temp", default_model="gemini-3.5-flash-lite")
        provider.api_key = ""
        with pytest.raises(ConfigurationError) as exc_info:
            gen = provider.generate_stream(system_instruction="", user_prompt="test")
            await gen.__anext__()
        assert "Gemini API key is not configured" in str(exc_info.value)

    def test_conforms_to_llm_provider_protocol(self):
        provider = GeminiProvider(api_key="fake-key", default_model="gemini-3.5-flash-lite")
        assert isinstance(provider, LLMProvider)


class TestMockLLMProvider:
    """Tests for MockLLMProvider deterministic streaming and JSON generation."""

    def test_satisfies_protocol(self):
        provider = MockLLMProvider()
        assert isinstance(provider, LLMProvider)

    @pytest.mark.asyncio
    async def test_streaming_tokens(self):
        provider = MockLLMProvider(canned_stream_tokens=["token1 ", "token2."])
        tokens = []
        async for t in provider.generate_stream(system_instruction="", user_prompt="hello"):
            tokens.append(t)
        assert "".join(tokens) == "token1 token2."

    @pytest.mark.asyncio
    async def test_json_generation(self):
        provider = MockLLMProvider(canned_json_response={"answer": "ok"})
        res = await provider.generate_json(system_instruction="", user_prompt="")
        assert res == {"answer": "ok"}


class TestLLMFactory:
    """Tests for LLMFactory resolving providers."""

    def test_resolve_mock_provider(self):
        factory = LLMFactory()
        provider = factory.get_provider("mock")
        assert isinstance(provider, MockLLMProvider)

    def test_resolve_gemini_provider(self):
        factory = LLMFactory()
        with patch("src.llm.gemini_provider.get_settings") as mock_settings:
            mock_settings.return_value.get_gemini_api_key.return_value = "key"
            mock_settings.return_value.gemini_default_model = "gemini-3.5-flash-lite"
            mock_settings.return_value.gemini_fallback_model = "gemini-1.5-flash"
            provider = factory.get_provider("gemini")
            assert isinstance(provider, GeminiProvider)

    def test_unsupported_provider_raises(self):
        factory = LLMFactory()
        with pytest.raises(ConfigurationError) as exc_info:
            factory.get_provider("unsupported_ai")
        assert "Unsupported LLM provider 'unsupported_ai'" in str(exc_info.value)


class TestEvidenceEvaluator:
    """Tests for evidence sufficiency checks and scientific abstention."""

    def setup_method(self):
        self.evaluator = EvidenceEvaluator(min_score_threshold=0.35, strong_score_threshold=0.65)

    def test_empty_sources_trigger_abstention(self):
        res = self.evaluator.evaluate([], target_lang="ar")
        assert res.should_abstain is True
        assert res.status == "INSUFFICIENT"
        assert "لم تتوفر في المراجع المعتمدة أدلة كافية" in res.abstention_message

    def test_low_score_sources_trigger_abstention(self):
        low_source = RetrievedSource(
            source_index=1,
            document_id=uuid.uuid4(),
            document_title="مستند ضعيف الصلة",
            document_author="مؤلف",
            work_id=None,
            work_title=None,
            edition_id=None,
            edition_title=None,
            edition_language="ar",
            chunk_language="ar",
            content="هذا نص تجريبي لكنه بعيد جداً عن موضوع السؤال ولا يقدم معلومة مفيدة.",
            combined_score=0.20,
            vector_similarity=0.22,
        )
        res = self.evaluator.evaluate([low_source], target_lang="ar")
        assert res.should_abstain is True
        assert res.status == "INSUFFICIENT"

    def test_strong_sources_pass(self):
        strong_source = RetrievedSource(
            source_index=1,
            document_id=uuid.uuid4(),
            document_title="معمارية RAG",
            document_author="مؤلف",
            work_id=None,
            work_title=None,
            edition_id=None,
            edition_title=None,
            edition_language="ar",
            chunk_language="ar",
            content="يعتمد البحث الهجين على دمج متجهات HNSW مع فهارس GIN المعجمية باستخدام RRF.",
            combined_score=0.85,
            vector_similarity=0.88,
        )
        res = self.evaluator.evaluate([strong_source], target_lang="ar")
        assert res.should_abstain is False
        assert res.status == "STRONG"
        assert res.abstention_message is None


class TestCitationSanitizer:
    """Tests for Eastern digit conversion, phantom removal, and sequential alignment."""

    def setup_method(self):
        self.sanitizer = CitationSanitizer()

    def test_normalizes_eastern_arabic_numerals(self):
        sources = [
            RetrievedSource(
                source_index=1,
                document_id=uuid.uuid4(),
                document_title="كتاب 1",
                document_author="مؤلف",
                work_id=None,
                work_title=None,
                edition_id=None,
                edition_title=None,
                edition_language="ar",
                chunk_language="ar",
                content="النص المرجعي الأول حول الفهارس.",
            )
        ]
        text_with_eastern_digits = "تعتمد المعمارية على فهارس HNSW [١]."
        res = self.sanitizer.sanitize_and_align(text_with_eastern_digits, sources)

        assert "[1]" in res.sanitized_text
        assert "[١]" not in res.sanitized_text
        assert len(res.reconciled_sources) == 1

    def test_phantom_citations_stripped(self):
        sources = [
            RetrievedSource(
                source_index=1,
                document_id=uuid.uuid4(),
                document_title="كتاب 1",
                document_author="مؤلف",
                work_id=None,
                work_title=None,
                edition_id=None,
                edition_title=None,
                edition_language="ar",
                chunk_language="ar",
                content="نص المرجع الأول.",
            )
        ]
        # Text cites [1] (valid) and [9] (phantom)
        raw_text = "المعلومة الأولى صحيحة [1]. والمعلومة الثانية غير موثقة [9]."
        res = self.sanitizer.sanitize_and_align(raw_text, sources)

        assert "[1]" in res.sanitized_text
        assert "[9]" not in res.sanitized_text
        assert res.stripped_phantoms_count == 1
        assert len(res.reconciled_sources) == 1

    def test_sequential_alignment_and_remapping(self):
        # 3 sources provided: [1], [2], [3]
        # LLM only cites [2] and [3]
        src1 = RetrievedSource(
            source_index=1,
            document_id=uuid.uuid4(),
            document_title="كتاب 1 (لم يُستشهد به)",
            document_author="أ",
            work_id=None,
            work_title=None,
            edition_id=None,
            edition_title=None,
            edition_language="ar",
            chunk_language="ar",
            content="محتوى غير مستشهد به.",
        )
        src2 = RetrievedSource(
            source_index=2,
            document_id=uuid.uuid4(),
            document_title="كتاب 2 (أول مرجع مستشهد به)",
            document_author="ب",
            work_id=None,
            work_title=None,
            edition_id=None,
            edition_title=None,
            edition_language="ar",
            chunk_language="ar",
            content="محتوى المرجع الثاني المستخدم.",
        )
        src3 = RetrievedSource(
            source_index=3,
            document_id=uuid.uuid4(),
            document_title="كتاب 3 (ثاني مرجع مستشهد به)",
            document_author="ج",
            work_id=None,
            work_title=None,
            edition_id=None,
            edition_title=None,
            edition_language="ar",
            chunk_language="ar",
            content="محتوى المرجع الثالث المستخدم.",
        )

        raw_text = "ورد في المرجع [2] أن RRF فعال. وأكد المرجع [3] ذلك."
        res = self.sanitizer.sanitize_and_align(raw_text, [src1, src2, src3])

        # Remapped: [2] -> [1], [3] -> [2]
        assert "المرجع [1] أن RRF فعال" in res.sanitized_text
        assert "وأكد المرجع [2] ذلك" in res.sanitized_text
        assert len(res.reconciled_sources) == 2
        assert res.reconciled_sources[0].source_index == 1
        assert res.reconciled_sources[0].document_title == "كتاب 2 (أول مرجع مستشهد به)"
        assert res.reconciled_sources[1].source_index == 2
        assert res.reconciled_sources[1].document_title == "كتاب 3 (ثاني مرجع مستشهد به)"

    def test_structured_citations_and_grounding_audit(self):
        src = RetrievedSource(
            source_index=1,
            document_id=uuid.uuid4(),
            document_title="كتاب الأصول",
            document_author="المصنف",
            work_id=None,
            work_title=None,
            edition_id=None,
            edition_title=None,
            edition_language="ar",
            chunk_language="ar",
            content="تعتمد التجزئة على حفظ الفصول والأقسام.",
            page_number=25,
            chapter_title="التجزئة",
        )
        text = "تعتمد التجزئة على حفظ الفصول والأقسام [1]."
        res = self.sanitizer.sanitize_and_align(text, [src])

        assert len(res.structured_citations) == 1
        sc = res.structured_citations[0]
        assert sc.source_index == 1
        assert sc.document_title == "كتاب الأصول"
        assert sc.page_number == 25
        assert sc.chapter_title == "التجزئة"
        assert sc.is_supported is True
        assert res.grounding_audit.status == "VERIFIED"
        assert res.grounding_audit.groundedness_score == 100.0

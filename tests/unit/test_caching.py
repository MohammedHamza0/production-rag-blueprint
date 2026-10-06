"""Comprehensive unit tests for the 2-tier semantic caching engine."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
import uuid
import pytest
from src.caching.coordinator import SemanticCacheCoordinator
from src.caching.equivalence_verifier import CacheEquivalenceVerifier
from src.caching.l1_redis import L1RedisCache
from src.caching.l2_vector import L2VectorSemanticCache
from src.caching.single_flight import SingleFlightMutex
from src.domain.protocols import LLMProvider, SemanticCacheStore


class TestL1RedisCache:
    """Tests for L1 exact-match cache."""

    @pytest.mark.asyncio
    async def test_compute_cache_key_deterministic(self):
        k1 = L1RedisCache.compute_cache_key("ما هي أركان الصلاة؟", "standard", "ar", "standard", "ALL")
        k2 = L1RedisCache.compute_cache_key("ما هي أركان الصلاة؟", "standard", "ar", "standard", "ALL")
        assert k1 == k2
        assert "rag:l1:standard:ar:standard:ALL:" in k1

    @pytest.mark.asyncio
    async def test_set_and_get_hit(self):
        mock_redis = AsyncMock()
        payload = {
            "response_text": "أركان الصلاة أربعة عشر ركناً.",
            "sources": [{"title": "Doc 1"}],
        }
        mock_redis.get.return_value = json.dumps(payload)

        cache = L1RedisCache(redis_client=mock_redis)
        res = await cache.get("ما هي أركان الصلاة؟", "standard", "ar", "standard", "ALL")

        assert res is not None
        assert res["response_text"] == payload["response_text"]
        assert res["cached"] is True
        assert res["tier"] == "L1"
        mock_redis.incr.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        cache = L1RedisCache(redis_client=mock_redis)
        res = await cache.get("سؤال غير مخزن", "standard", "ar", "standard", "ALL")
        assert res is None


class TestSingleFlightMutex:
    """Tests for single-flight distributed mutex and coalescing."""

    @pytest.mark.asyncio
    async def test_leader_election_and_follower(self):
        mock_redis = AsyncMock()
        # First call succeeds (Leader)
        mock_redis.set.return_value = True
        sf = SingleFlightMutex(redis_client=mock_redis)

        lock_key = sf.compute_lock_key("query", "standard", "ar", "standard", "ALL")
        is_leader = await sf.try_acquire_leader(lock_key)
        assert is_leader is True

        # Second call fails (Follower)
        mock_redis.set.return_value = False
        is_second_leader = await sf.try_acquire_leader(lock_key)
        assert is_second_leader is False

    @pytest.mark.asyncio
    async def test_wait_for_leader_coalesces_result(self):
        mock_redis = AsyncMock()
        sf = SingleFlightMutex(redis_client=mock_redis)

        calls = 0

        async def mock_lookup():
            nonlocal calls
            calls += 1
            if calls >= 2:
                return {"response_text": "Leader generated answer"}
            return None

        result = await sf.wait_for_leader(lookup_fn=mock_lookup, max_wait_ms=1000, poll_interval_ms=50)
        assert result is not None
        assert result["response_text"] == "Leader generated answer"
        assert result["coalesced"] is True


class TestCacheEquivalenceVerifier:
    """Tests for equivalence verification, pair-hash caching, and fail-closed safety."""

    @pytest.mark.asyncio
    async def test_exact_match_bypasses_llm(self):
        verifier = CacheEquivalenceVerifier(redis_client=None, llm_provider=None)
        res = await verifier.is_equivalent(
            stored_query="ما هي أركان الصلاة؟",
            incoming_query="ما هي أركان الصلاة؟",
            cosine_similarity=0.99,
        )
        assert res is True

    @pytest.mark.asyncio
    async def test_high_confidence_similarity_bypasses_llm(self):
        verifier = CacheEquivalenceVerifier(redis_client=None, llm_provider=None)
        res = await verifier.is_equivalent(
            stored_query="أركان الصلاة الأساسية",
            incoming_query="ما أركان الصلاة الأساسية",
            cosine_similarity=0.98,
        )
        assert res is True

    @pytest.mark.asyncio
    async def test_low_similarity_rejected_immediately(self):
        verifier = CacheEquivalenceVerifier(redis_client=None, llm_provider=None)
        res = await verifier.is_equivalent(
            stored_query="ما هي أركان الصلاة؟",
            incoming_query="ما حكم الزكاة؟",
            cosine_similarity=0.82,
        )
        assert res is False

    @pytest.mark.asyncio
    async def test_pair_cache_hit_returns_cached_verdict(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "1"

        verifier = CacheEquivalenceVerifier(redis_client=mock_redis, llm_provider=None)
        res = await verifier.is_equivalent(
            stored_query="ما هي أركان الصلاة؟",
            incoming_query="أركان الصلاة ما هي؟",
            cosine_similarity=0.93,
        )
        assert res is True
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_verification_in_ambiguous_band(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Cache miss

        mock_llm = AsyncMock()
        mock_llm.generate_json.return_value = {
            "equivalent": False,
            "reason": "Conditions vs Pillars are distinct concepts",
        }

        verifier = CacheEquivalenceVerifier(redis_client=mock_redis, llm_provider=mock_llm)
        res = await verifier.is_equivalent(
            stored_query="ما هي شروط الصلاة؟",
            incoming_query="ما هي أركان الصلاة؟",
            cosine_similarity=0.93,
        )
        assert res is False
        mock_redis.set.assert_called_once()  # Persisted verdict "0" in Redis

    @pytest.mark.asyncio
    async def test_fail_closed_on_llm_failure(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_llm = AsyncMock()
        mock_llm.generate_json.side_effect = TimeoutError("LLM timeout")

        verifier = CacheEquivalenceVerifier(
            redis_client=mock_redis,
            llm_provider=mock_llm,
            timeout_seconds=0.1,
        )
        res = await verifier.is_equivalent(
            stored_query="query 1",
            incoming_query="query 2",
            cosine_similarity=0.92,
        )
        # Must fail-closed (return False) to prevent ungrounded cache hits
        assert res is False


class TestL2VectorSemanticCache:
    """Tests for pgvector candidate search and storage."""

    @pytest.mark.asyncio
    async def test_find_candidate_hit(self):
        mock_session = AsyncMock()
        mock_row = MagicMock()
        mock_row.id = uuid.uuid4()
        mock_row.query_text = "ما هي مقاصد الشريعة؟"
        mock_row.normalized_query = "ما هي مقاصد الشريعة"
        mock_row.response_text = "مقاصد الشريعة خمسة..."
        mock_row.sources = []
        mock_row.suggestions = []
        mock_row.persona = "standard"
        mock_row.language = "ar"
        mock_row.answer_shape = "standard"
        mock_row.filter_hash = "ALL"
        mock_row.corpus_version = "v1"
        mock_row.grounding_audit = {"status": "VERIFIED"}
        mock_row.similarity = 0.94

        mock_res = MagicMock()
        mock_res.first.return_value = mock_row
        mock_session.execute.return_value = mock_res

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_session_factory.return_value.__aexit__.return_value = None

        l2 = L2VectorSemanticCache(session_factory=mock_session_factory)
        cand = await l2.find_candidate(
            query_embedding=[0.1] * 768,
            persona="standard",
            language="ar",
            answer_shape="standard",
            filter_hash="ALL",
        )

        assert cand is not None
        assert cand["response_text"] == "مقاصد الشريعة خمسة..."
        assert cand["similarity"] == 0.94
        assert cand["tier"] == "L2"


class TestSemanticCacheCoordinator:
    """Tests for end-to-end multi-tier cache coordination."""

    def test_satisfies_protocol(self):
        mock_l1 = MagicMock()
        mock_l2 = MagicMock()
        mock_ver = MagicMock()
        coordinator = SemanticCacheCoordinator(l1_cache=mock_l1, l2_cache=mock_l2, verifier=mock_ver)
        assert isinstance(coordinator, SemanticCacheStore)

    @pytest.mark.asyncio
    async def test_l1_hit_bypasses_l2(self):
        mock_l1 = AsyncMock()
        mock_l1.get.return_value = {"response_text": "L1 fast answer", "tier": "L1"}
        mock_l2 = AsyncMock()
        mock_ver = AsyncMock()

        coordinator = SemanticCacheCoordinator(l1_cache=mock_l1, l2_cache=mock_l2, verifier=mock_ver)
        res = await coordinator.find_hit(
            query_text="ما هي مقاصد الشريعة؟",
            query_embedding=[0.1] * 768,
        )

        assert res is not None
        assert res["response_text"] == "L1 fast answer"
        mock_l2.find_candidate.assert_not_called()
        mock_ver.is_equivalent.assert_not_called()

    @pytest.mark.asyncio
    async def test_l2_hit_verified_and_backfilled_to_l1(self):
        mock_l1 = AsyncMock()
        mock_l1.get.return_value = None  # L1 Miss
        mock_l2 = AsyncMock()
        mock_l2.find_candidate.return_value = {
            "query_text": "ما هي مقاصد الشريعة الخمسة؟",
            "response_text": "حفظ الدين والنفس والعقل والنسل والمال",
            "similarity": 0.92,
        }
        mock_ver = AsyncMock()
        mock_ver.is_equivalent.return_value = True  # Verifier approves!

        coordinator = SemanticCacheCoordinator(l1_cache=mock_l1, l2_cache=mock_l2, verifier=mock_ver)
        res = await coordinator.find_hit(
            query_text="مقاصد الشريعة الخمسة ما هي؟",
            query_embedding=[0.1] * 768,
        )

        assert res is not None
        assert res["response_text"] == "حفظ الدين والنفس والعقل والنسل والمال"
        assert res["tier"] == "L2"
        # Must backfill L1 Redis for subsequent sub-5ms calls
        mock_l1.set.assert_called_once()

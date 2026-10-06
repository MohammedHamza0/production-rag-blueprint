"""Mock LLM Provider for deterministic offline testing and CI/CD pipelines."""

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional
from src.domain.protocols import LLMProvider


class MockLLMProvider(LLMProvider):
    """Deterministic in-memory mock provider implementing the LLMProvider protocol."""

    def __init__(
        self,
        canned_stream_tokens: Optional[List[str]] = None,
        canned_json_response: Optional[Dict[str, Any]] = None,
    ):
        self.canned_stream_tokens = canned_stream_tokens or [
            "تعتمد ",
            "معمارية ",
            "البحث ",
            "الهجين ",
            "على ",
            "دمج ",
            "HNSW ",
            "مع ",
            "GIN ",
            "[1]. ",
            "وهذا ",
            "يضمن ",
            "الدقة ",
            "[2].",
        ]
        self.canned_json_response = canned_json_response or {
            "equivalent": True,
            "reason": "Deterministic mock match",
        }

    async def generate_stream(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        for token in self.canned_stream_tokens:
            await asyncio.sleep(0.001)  # Simulate non-blocking micro-delay
            yield token

    async def generate_json(
        self,
        system_instruction: str,
        user_prompt: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.canned_json_response

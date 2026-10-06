"""LLM Provider Factory resolving model providers by configuration."""

from typing import Dict, Optional
from src.core.config import get_settings
from src.core.exceptions import ConfigurationError
from src.domain.protocols import LLMProvider
from src.llm.gemini_provider import GeminiProvider
from src.llm.mock_provider import MockLLMProvider


class LLMFactory:
    """Factory creating and caching configured LLMProvider instances."""

    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}

    def get_provider(self, provider_name: Optional[str] = None) -> LLMProvider:
        """Resolves LLMProvider instance based on provider name or application settings."""
        settings = get_settings()
        name = (provider_name or settings.default_llm_provider).lower()

        if name in self._providers:
            return self._providers[name]

        if name == "gemini":
            provider = GeminiProvider(
                default_model=settings.gemini_default_model,
                fallback_model=settings.gemini_fallback_model,
            )
        elif name == "mock":
            provider = MockLLMProvider()
        else:
            raise ConfigurationError(
                f"Unsupported LLM provider '{name}'. Supported providers: gemini, mock"
            )

        self._providers[name] = provider
        return provider

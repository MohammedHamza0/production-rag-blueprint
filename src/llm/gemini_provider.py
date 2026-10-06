"""Gemini LLM Provider using direct streaming REST API with httpx."""

import json
from typing import Any, AsyncIterator, Dict, List, Optional
import httpx
from src.core.config import get_settings
from src.core.exceptions import ConfigurationError, ProviderAPIError
from src.core.logging import get_logger
from src.domain.protocols import LLMProvider

logger = get_logger("llm.gemini")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(LLMProvider):
    """Google Gemini AI Provider supporting SSE token streaming and structured JSON output."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "gemini-3.5-flash-lite",
        fallback_model: str = "gemini-1.5-flash",
        timeout_seconds: float = 30.0,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.get_gemini_api_key()
        self.default_model = default_model
        self.fallback_model = fallback_model
        self.timeout = timeout_seconds
        self._validate_model(self.default_model)
        self._validate_model(self.fallback_model)

    @staticmethod
    def _validate_model(model_name: str) -> None:
        """Enforces system-wide model policy, strictly rejecting deprecated/unsupported models."""
        if "gemini-2.5" in model_name.lower():
            raise ConfigurationError(
                f"Model '{model_name}' is unsupported and deprecated. "
                "Use 'gemini-3.5-flash-lite' (default), 'gemini-3.5-flash', or 'gemini-1.5-flash' instead."
            )

    async def generate_stream(
        self,
        system_instruction: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_output_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Streams text chunks in real-time from Gemini SSE API."""
        chosen_model = model or self.default_model
        self._validate_model(chosen_model)

        if not self.api_key:
            raise ConfigurationError("Gemini API key is not configured or resolved from KeyVault.")

        url = f"{GEMINI_BASE_URL}/models/{chosen_model}:streamGenerateContent?alt=sse&key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}],
            }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        logger.error(
                            "gemini_stream_failed",
                            status=response.status_code,
                            body=err_body.decode(errors="replace")[:300],
                        )
                        raise ProviderAPIError(
                            provider="gemini",
                            message=f"HTTP {response.status_code}: {err_body.decode(errors='replace')[:200]}",
                            provider_status_code=response.status_code,
                        )

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        json_str = line[6:].strip()
                        if not json_str:
                            continue

                        try:
                            data = json.loads(json_str)
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for p in parts:
                                    text_token = p.get("text", "")
                                    if text_token:
                                        yield text_token
                        except json.JSONDecodeError:
                            continue

            except httpx.TimeoutException:
                logger.error("gemini_stream_timeout", model=chosen_model)
                raise ProviderAPIError(
                    provider="gemini",
                    message=f"Gemini API timed out after {self.timeout}s",
                    provider_status_code=504,
                )
            except ProviderAPIError:
                raise
            except Exception as exc:
                logger.error("gemini_stream_exception", error=str(exc))
                raise ProviderAPIError(
                    provider="gemini",
                    message=f"Gemini streaming connection failed: {str(exc)}",
                )

    async def generate_json(
        self,
        system_instruction: str,
        user_prompt: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generates a structured JSON object response enforcing application/json MIME type."""
        chosen_model = model or self.default_model
        self._validate_model(chosen_model)

        if not self.api_key:
            raise ConfigurationError("Gemini API key is not configured.")

        url = f"{GEMINI_BASE_URL}/models/{chosen_model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
            },
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}],
            }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    raise ProviderAPIError(
                        provider="gemini",
                        message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                        provider_status_code=resp.status_code,
                    )

                data = resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return {}

                text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
                return json.loads(text_content)

            except json.JSONDecodeError as jde:
                logger.warning("gemini_invalid_json_returned", error=str(jde))
                return {}
            except ProviderAPIError:
                raise
            except Exception as exc:
                logger.error("gemini_json_generation_failed", error=str(exc))
                raise ProviderAPIError(
                    provider="gemini",
                    message=f"Gemini JSON generation failed: {str(exc)}",
                )

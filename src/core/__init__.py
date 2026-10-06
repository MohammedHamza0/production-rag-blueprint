"""Core infrastructure module."""

from src.core.config import AppSettings, settings
from src.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    DocumentParsingError,
    FileTooLargeError,
    InsufficientEvidenceError,
    ProviderAPIError,
    RAGBaseException,
    RateLimitExceededError,
    UnsupportedMimeTypeError,
    VectorDimensionMismatchError,
)
from src.core.logging import bind_correlation_id, get_correlation_id, get_logger, setup_logging
from src.core.security import KeyVault, generate_boundary_nonce, hash_api_key, is_valid_uuid

__all__ = [
    "AppSettings",
    "settings",
    "RAGBaseException",
    "ConfigurationError",
    "AuthenticationError",
    "AuthorizationError",
    "RateLimitExceededError",
    "DocumentParsingError",
    "UnsupportedMimeTypeError",
    "FileTooLargeError",
    "VectorDimensionMismatchError",
    "InsufficientEvidenceError",
    "ProviderAPIError",
    "KeyVault",
    "hash_api_key",
    "generate_boundary_nonce",
    "is_valid_uuid",
    "setup_logging",
    "get_logger",
    "bind_correlation_id",
    "get_correlation_id",
]

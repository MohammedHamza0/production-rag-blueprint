"""Domain and system exception hierarchy for the Production RAG Blueprint."""

from typing import Any, Dict, Optional


class RAGBaseException(Exception):
    """Root base exception for all RAG system errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class ConfigurationError(RAGBaseException):
    """Raised when environment variables or configurations are invalid or missing."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="CONFIG_ERROR",
            status_code=500,
            details=details,
        )


class AuthenticationError(RAGBaseException):
    """Raised when authentication fails or API key is missing/invalid."""

    def __init__(self, message: str = "Authentication failed.", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="AUTHENTICATION_FAILED",
            status_code=401,
            details=details,
        )


class AuthorizationError(RAGBaseException):
    """Raised when an actor attempts an action outside their granted permissions."""

    def __init__(self, message: str = "Access forbidden.", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="FORBIDDEN_ACCESS",
            status_code=403,
            details=details,
        )


class RateLimitExceededError(RAGBaseException):
    """Raised when a user or guest exceeds the configured rate limits."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please wait before retrying.",
        retry_after_seconds: int = 30,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        det = details or {}
        det["retry_after_seconds"] = retry_after_seconds
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=det,
        )


class DocumentParsingError(RAGBaseException):
    """Raised when document ingestion parser fails to extract text or metadata."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="DOCUMENT_PARSING_FAILED",
            status_code=422,
            details=details,
        )


class UnsupportedMimeTypeError(RAGBaseException):
    """Raised when an uploaded document has an unsupported extension or MIME type."""

    def __init__(self, mime_type: str, allowed: Optional[list[str]] = None) -> None:
        super().__init__(
            message=f"Unsupported document MIME type: '{mime_type}'. Allowed types: {allowed or []}",
            code="UNSUPPORTED_MIME_TYPE",
            status_code=415,
            details={"mime_type": mime_type, "allowed": allowed},
        )


class FileTooLargeError(RAGBaseException):
    """Raised when an uploaded file exceeds the maximum allowed size limit."""

    def __init__(self, file_size_bytes: int, max_allowed_bytes: int) -> None:
        super().__init__(
            message=f"File size {file_size_bytes} bytes exceeds maximum allowed limit {max_allowed_bytes} bytes.",
            code="FILE_TOO_LARGE",
            status_code=413,
            details={"file_size": file_size_bytes, "max_allowed": max_allowed_bytes},
        )


class VectorDimensionMismatchError(RAGBaseException):
    """Raised when embedding dimension does not match database schema dimension."""

    def __init__(self, expected: int, received: int) -> None:
        super().__init__(
            message=f"Vector dimension mismatch: expected {expected}d, received {received}d.",
            code="VECTOR_DIMENSION_MISMATCH",
            status_code=500,
            details={"expected": expected, "received": received},
        )


class InsufficientEvidenceError(RAGBaseException):
    """Raised when evidence evaluator determines retrieved context is inadequate."""

    def __init__(self, message: str = "Insufficient evidence to answer reliably.", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="INSUFFICIENT_EVIDENCE",
            status_code=200,  # Graceful domain response
            details=details,
        )


class ProviderAPIError(RAGBaseException):
    """Raised when an external model provider (Gemini, OpenAI, Anthropic) returns an error."""

    def __init__(
        self,
        provider: str,
        message: str,
        provider_status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        det = details or {}
        det["provider"] = provider
        det["provider_status_code"] = provider_status_code
        super().__init__(
            message=f"Error from AI provider '{provider}': {message}",
            code="AI_PROVIDER_ERROR",
            status_code=502,
            details=det,
        )


class RetrievalError(RAGBaseException):
    """Raised when search execution or hybrid retrieval fails."""

    def __init__(self, message: str = "Retrieval execution failed.", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="RETRIEVAL_FAILED",
            status_code=500,
            details=details,
        )


class DatabaseError(RAGBaseException):
    """Raised when an unexpected database transaction or connection failure occurs."""

    def __init__(self, message: str = "Database operation failed.", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=500,
            details=details,
        )

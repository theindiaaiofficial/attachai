"""Structured domain and HTTP exceptions for Orbit AI."""

from __future__ import annotations

from typing import Any, Dict, Optional


class OrbitError(Exception):
    """Base exception for all Orbit AI application errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str = "orbit_error",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}


class ConfigurationError(OrbitError):
    """Raised when environment or provider configuration is invalid."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=500, code="configuration_error", details=details)


class AuthenticationError(OrbitError):
    """Raised when authentication credentials are missing or invalid."""

    def __init__(self, message: str = "Authentication required", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=401, code="authentication_error", details=details)


class AuthorizationError(OrbitError):
    """Raised when a caller attempts an unauthorized or cross-tenant operation."""

    def __init__(self, message: str = "Access denied", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=403, code="authorization_error", details=details)


class NotFoundError(OrbitError):
    """Raised when a tenant-scoped resource does not exist."""

    def __init__(self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=404, code="not_found", details=details)


class ValidationError(OrbitError):
    """Raised when request payloads or uploaded files fail validation."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=422, code="validation_error", details=details)


class RateLimitError(OrbitError):
    """Raised when per-IP or per-tenant rate limits are exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60) -> None:
        super().__init__(
            message=message,
            status_code=429,
            code="rate_limit_exceeded",
            details={"retryAfter": retry_after},
        )


class ProviderError(OrbitError):
    """Raised when an upstream LLM, storage, database, or vector provider fails."""

    def __init__(
        self,
        message: str,
        status_code: int = 503,
        provider: str = "upstream",
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status_code,
            code="provider_error",
            details={"provider": provider, "retryable": retryable},
        )
        self.provider = provider
        self.retryable = retryable

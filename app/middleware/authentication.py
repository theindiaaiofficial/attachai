"""Admin and tenant authentication helpers."""

from __future__ import annotations

from typing import Dict, Optional

from app.core.dependencies import ServiceContainer
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import constant_time_equals, verify_admin_session_token
from app.domain.models import ClientRecord


def verify_admin_request(
    container: ServiceContainer,
    headers: Dict[str, str],
    cookies: Optional[Dict[str, str]] = None,
    method: str = "GET",
) -> None:
    """
    Authenticate administrative API call via `x-admin-api-key` header
    or signed HttpOnly session cookie (with CSRF check on state-changing requests).
    """
    norm_headers = {k.lower(): v for k, v in (headers or {}).items()}
    header_key = norm_headers.get("x-admin-api-key", "").strip()

    # In production, if ADMIN_API_KEY was not explicitly configured by the operator, lock admin endpoints
    if container.settings.is_production and not container.settings.admin_api_key_configured:
        raise AuthenticationError("Production administrator API access requires configuring the ADMIN_API_KEY environment variable.")

    # In production, explicitly reject known insecure/default keys
    if container.settings.is_production and header_key in (
        "orbit-dev-admin-key",
        "change-me-in-production-admin-secret",
        "orbit-auto-runtime-admin-key-prod",
    ):
        raise AuthenticationError("Insecure default administrator API key is prohibited in production.")

    if header_key:
        if constant_time_equals(container.settings.admin_api_key, header_key):
            return
        raise AuthenticationError("Invalid administrator API key.")

    cookies = cookies or {}
    session_token = cookies.get("orbit_admin_session", "")
    if session_token:
        valid, csrf_expected = verify_admin_session_token(session_token, container.settings.admin_api_key)
        if not valid:
            raise AuthenticationError("Invalid or expired administrator session.")
        if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            csrf_provided = norm_headers.get("x-csrf-token", "").strip()
            if not constant_time_equals(csrf_expected, csrf_provided):
                raise AuthorizationError("CSRF token validation failed.")
        return

    raise AuthenticationError("Missing x-admin-api-key header.")


def verify_public_tenant_request(
    container: ServiceContainer,
    headers: Dict[str, str],
    expected_client_id: Optional[str] = None,
) -> ClientRecord:
    """Authenticate public widget request via `x-api-key` and verify domain allowlist."""
    norm_headers = {k.lower(): v for k, v in (headers or {}).items()}
    raw_key = norm_headers.get("x-api-key", "").strip()
    origin = norm_headers.get("origin") or norm_headers.get("referer") or ""
    header_client_id = norm_headers.get("x-client-id") or expected_client_id
    return container.client_service.authenticate_tenant_request(
        raw_api_key=raw_key,
        origin_or_host=origin,
        expected_client_id=header_client_id,
    )

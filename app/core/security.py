"""Cryptographic helpers, constant-time secret verification, API key hashing, and domain matching."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Iterable, Tuple
from urllib.parse import urlparse


def constant_time_equals(expected: str, provided: str) -> bool:
    """Compare two secrets in constant time."""
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))


def hash_api_key(raw_key: str) -> str:
    """Compute a deterministic SHA-256 hex digest of a tenant API key."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


def generate_tenant_api_key() -> Tuple[str, str, str]:
    """Generate a new tenant API key and return (raw_key, key_prefix, key_hash)."""
    token = secrets.token_urlsafe(24).replace("-", "").replace("_", "")[:32]
    raw_key = f"orb_live_{token}"
    key_prefix = raw_key[:14]
    key_hash = hash_api_key(raw_key)
    return raw_key, key_prefix, key_hash


def create_admin_session_token(admin_secret: str, ttl_seconds: int = 86400) -> Tuple[str, str]:
    """Create a signed admin session cookie value and a paired CSRF token."""
    expires_at = int(time.time()) + ttl_seconds
    nonce = secrets.token_hex(16)
    csrf_token = secrets.token_hex(16)
    payload = f"{expires_at}.{nonce}.{csrf_token}"
    sig = hmac.new(admin_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}", csrf_token


def verify_admin_session_token(token: str, admin_secret: str) -> Tuple[bool, str]:
    """Verify a signed admin session token and return (is_valid, csrf_token)."""
    if not token or not admin_secret:
        return False, ""
    parts = token.split(".")
    if len(parts) != 4:
        return False, ""
    expires_str, nonce, csrf_token, provided_sig = parts
    try:
        expires_at = int(expires_str)
    except ValueError:
        return False, ""
    if expires_at < int(time.time()):
        return False, ""
    payload = f"{expires_str}.{nonce}.{csrf_token}"
    expected_sig = hmac.new(admin_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not constant_time_equals(expected_sig, provided_sig):
        return False, ""
    return True, csrf_token


def extract_hostname(origin_or_url: str) -> str:
    """Normalize an Origin, Referer, or hostname string to lowercase hostname without port."""
    if not origin_or_url:
        return ""
    raw = origin_or_url.strip().lower()
    if "://" in raw:
        parsed = urlparse(raw)
        host = parsed.hostname or ""
    else:
        host = raw.split("/")[0].split(":")[0]
    return host.strip(".")


def is_domain_allowed(origin_or_host: str, allowed_domains: Iterable[str]) -> bool:
    """Verify whether the request origin/host matches the tenant's allowed domains."""
    domains = [extract_hostname(d) for d in allowed_domains if d and d.strip()]
    if not domains:
        # When no domain restriction is configured for the tenant, allow access
        return True
    if not origin_or_host:
        return True
    host = extract_hostname(origin_or_host)
    if not host or host in ("localhost", "127.0.0.1", "testserver"):
        return True
    for allowed in domains:
        if allowed == "*" or host == allowed or host.endswith(f".{allowed}"):
            return True
    return False

"""PII and secret redaction utilities."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_REGEX = re.compile(
    r"(?:(?:\+|00)\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?|\d{3,4}[\s.-]?)\d{3}[\s.-]?\d{3,4}\b"
)
BEARER_REGEX = re.compile(r"(?i)\b(bearer|token|apikey|api_key|secret|password)\s*[:=]\s*([^\s,;\"']+)")
ORBIT_KEY_REGEX = re.compile(r"\b(?:orb_live_|orb_test_|sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})[A-Za-z0-9_-]*")

SENSITIVE_FIELD_NAMES = {
    "admin_api_key",
    "x-admin-api-key",
    "x-api-key",
    "api_key",
    "apikey",
    "authorization",
    "supabase_service_role_key",
    "service_role_key",
    "llm_api_key",
    "embedding_api_key",
    "tts_api_key",
    "smtp_pass",
    "password",
    "secret",
    "token",
    "key_hash",
}


def redact_text(text: str, extra_secrets: Optional[Iterable[str]] = None) -> str:
    """Redact emails, phone numbers, bearer tokens, API keys, and configured secrets."""
    if not text:
        return text
    redacted = str(text)
    if extra_secrets:
        for secret in extra_secrets:
            if secret and len(secret.strip()) >= 4:
                redacted = redacted.replace(secret.strip(), "[REDACTED_SECRET]")

    redacted = ORBIT_KEY_REGEX.sub("[REDACTED_TOKEN]", redacted)
    redacted = BEARER_REGEX.sub(r"\1=[REDACTED_SECRET]", redacted)
    redacted = EMAIL_REGEX.sub("[REDACTED_EMAIL]", redacted)
    redacted = PHONE_REGEX.sub("[REDACTED_PHONE]", redacted)
    return redacted


def redact_dict(data: Dict[str, Any], extra_secrets: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Recursively redact sensitive keys and PII inside dictionaries."""
    cleaned: Dict[str, Any] = {}
    for key, value in data.items():
        lower_key = str(key).lower()
        if lower_key in SENSITIVE_FIELD_NAMES or any(s in lower_key for s in ("secret", "password", "api_key", "token", "authorization")):
            cleaned[key] = "[REDACTED_SECRET]"
        elif isinstance(value, dict):
            cleaned[key] = redact_dict(value, extra_secrets=extra_secrets)
        elif isinstance(value, list):
            cleaned[key] = [
                redact_dict(item, extra_secrets=extra_secrets)
                if isinstance(item, dict)
                else (redact_text(item, extra_secrets=extra_secrets) if isinstance(item, str) else item)
                for item in value
            ]
        elif isinstance(value, str):
            cleaned[key] = redact_text(value, extra_secrets=extra_secrets)
        else:
            cleaned[key] = value
    return cleaned

"""Strict CORS and security headers middleware."""

from __future__ import annotations

from typing import Dict, List


def build_security_and_cors_headers(origin: str, allowed_origins: List[str], is_production: bool = False) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "SAMEORIGIN",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
    if is_production:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    clean_origin = (origin or "").strip()
    if clean_origin and ("*" in allowed_origins or clean_origin in allowed_origins):
        headers["Access-Control-Allow-Origin"] = clean_origin
        headers["Access-Control-Allow-Headers"] = "Content-Type, x-api-key, x-admin-api-key, x-client-id, x-csrf-token"
        headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        headers["Vary"] = "Origin"
    return headers

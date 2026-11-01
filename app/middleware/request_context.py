"""Request ID and context tracking."""

from __future__ import annotations

import uuid
from typing import Dict


def get_or_create_request_id(headers: Dict[str, str]) -> str:
    for k, v in (headers or {}).items():
        if k.lower() == "x-request-id" and v.strip():
            return v.strip()[:64]
    return str(uuid.uuid4())

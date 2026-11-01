"""Structured logging with automatic secret and PII redaction."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from app.utils.pii import redact_dict, redact_text


class SafeStructuredLogger:
    """Logger wrapper that redacts PII and secrets before emitting records."""

    def __init__(self, name: str = "orbit_ai", extra_secrets: Optional[Iterable[str]] = None) -> None:
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)
        self._secrets = list(extra_secrets or [])

    def update_secrets(self, secrets: Iterable[str]) -> None:
        self._secrets = [s for s in secrets if s]

    def format_entry(self, level: str, event: str, **fields: Any) -> str:
        safe_fields = redact_dict(fields, extra_secrets=self._secrets)
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "event": redact_text(event, extra_secrets=self._secrets),
            **safe_fields,
        }
        return json.dumps(payload, sort_keys=True)

    def info(self, event: str, **fields: Any) -> str:
        entry = self.format_entry("INFO", event, **fields)
        self._logger.info(entry)
        return entry

    def warning(self, event: str, **fields: Any) -> str:
        entry = self.format_entry("WARNING", event, **fields)
        self._logger.warning(entry)
        return entry

    def error(self, event: str, **fields: Any) -> str:
        entry = self.format_entry("ERROR", event, **fields)
        self._logger.error(entry)
        return entry

    def debug(self, event: str, enabled: bool = False, **fields: Any) -> Optional[str]:
        if not enabled:
            return None
        entry = self.format_entry("DEBUG", event, **fields)
        self._logger.debug(entry)
        return entry

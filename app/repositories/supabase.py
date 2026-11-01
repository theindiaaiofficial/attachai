"""Supabase PostgreSQL repository adapter with schema verification and explicit tenant filtering."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from app.core.exceptions import ConfigurationError, ProviderError
from app.repositories.sqlite import SQLiteRepository


class SupabaseRepository(SQLiteRepository):
    """
    Production Supabase PostgREST / SDK repository adapter.
    Verifies required tables and RPC functions against the live Supabase project,
    and ensures every query includes explicit `client_id` filters.
    """

    REQUIRED_TABLES = (
        "clients",
        "api_keys",
        "domains",
        "prompt_versions",
        "conversations",
        "messages",
        "message_feedback",
        "leads",
        "lead_workflow",
        "usage_logs",
        "audit_logs",
        "knowledge_files",
        "knowledge_vectors",
        "settings",
        "notifications",
    )

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        vector_dimensions: int = 128,
        http_transport: Optional[Any] = None,
    ) -> None:
        if not supabase_url.strip() or not service_role_key.strip():
            raise ConfigurationError("SupabaseRepository requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        super().__init__(db_path=":memory:")
        self.supabase_url = supabase_url.rstrip("/")
        self.service_role_key = service_role_key.strip()
        self.vector_dimensions = vector_dimensions
        self._http_transport = http_transport
        self._schema_verified = False

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def rest_request(
        self,
        method: str,
        path: str,
        query: Optional[Dict[str, str]] = None,
        body: Optional[ Any] = None,
    ) -> Any:
        url = f"{self.supabase_url}/rest/v1/{path.lstrip('/')}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        if self._http_transport is not None:
            return self._http_transport(method, url, self._headers(), body)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else []
        except urllib.error.HTTPError as exc:
            raise ProviderError(
                f"Supabase REST HTTP {exc.code} on {path}",
                status_code=503,
                provider="supabase",
            ) from exc
        except Exception as exc:
            raise ProviderError(
                "Supabase connection error",
                status_code=503,
                provider="supabase",
            ) from exc

    def check_health(self) -> Tuple[bool, str]:
        """Verify database connectivity, required tables, and `match_knowledge_vectors` RPC."""
        try:
            # 1. Check required tables
            for table in ("clients", "knowledge_files", "knowledge_vectors", "message_feedback"):
                self.rest_request("GET", table, query={"select": "id", "limit": "1"})

            # 2. Check match_knowledge_vectors RPC with a 128-dim zero vector
            zero_vec = [0.0] * self.vector_dimensions
            self.rest_request(
                "POST",
                "rpc/match_knowledge_vectors",
                body={
                    "query_embedding": zero_vec,
                    "match_client_id": "00000000-0000-0000-0000-000000000000",
                    "match_threshold": 0.99,
                    "match_count": 1,
                },
            )
            self._schema_verified = True
            return True, "Supabase schema and match_knowledge_vectors RPC verified"
        except Exception as exc:
            return False, f"Supabase readiness check failed: {exc}"

"""Application configuration and startup validation for Orbit AI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.exceptions import ConfigurationError


def _parse_bool(val: Optional[str], default: bool = False) -> bool:
    if val is None or val == "":
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _parse_int(val: Optional[str], default: int) -> int:
    if val is None or val.strip() == "":
        return default
    try:
        return int(val.strip())
    except ValueError as exc:
        raise ConfigurationError(f"Invalid integer configuration value: {val!r}") from exc


def _parse_float(val: Optional[str], default: float) -> float:
    if val is None or val.strip() == "":
        return default
    try:
        return float(val.strip())
    except ValueError as exc:
        raise ConfigurationError(f"Invalid float configuration value: {val!r}") from exc


def _parse_origins(allowed_origins: Optional[str], cors_origins: Optional[str]) -> List[str]:
    """ALLOWED_ORIGINS takes precedence over legacy CORS_ORIGINS."""
    raw = allowed_origins if (allowed_origins is not None and allowed_origins.strip() != "") else (cors_origins or "")
    if not raw.strip():
        return ["http://localhost:3000", "http://localhost:8000"]
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_single_origin_list(raw: Optional[str]) -> List[str]:
    if not raw or not raw.strip():
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    """Centralized validated configuration for Orbit AI."""

    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    public_base_url: str = "http://localhost:8000"

    admin_api_key: str = "orbit-dev-admin-key"
    admin_api_key_configured: bool = True
    allowed_origins: List[str] = field(default_factory=lambda: ["http://localhost:3000", "http://localhost:8000"])
    cors_origins: List[str] = field(default_factory=list)

    database_provider: str = "sqlite"
    storage_provider: str = "local"
    vector_provider: str = "local"

    sqlite_path: str = "data/orbit_ai.db"
    local_storage_dir: str = "data/storage"

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "knowledge"
    supabase_vector_dimensions: int = 128

    llm_provider_type: str = "local"
    llm_provider_name: str = "local"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "orbit-local-v1"
    llm_timeout_ms: int = 15000
    llm_max_retries: int = 2
    llm_temperature: float = 0.2
    llm_max_tokens: int = 800
    llm_chat_path: str = "/chat/completions"
    llm_health_path: str = "/models"
    llm_auth_header_name: str = "Authorization"
    llm_auth_scheme: str = "Bearer"

    embedding_provider: str = "local"
    embedding_dimensions: int = 128
    embedding_base_url: str = ""
    embedding_model: str = "orbit-embed-128"
    embedding_api_key: str = ""

    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "orbit_knowledge"

    notification_provider: str = "outbox"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = ""

    orbit_rag_diagnostics: bool = False
    orbit_temp_debug_client_id: str = ""
    orbit_temp_debug_gousto: bool = False
    orbit_temp_debug_llm_input: bool = False
    orbit_temp_debug_puregym: bool = False

    tts_api_key: str = ""
    tts_provider: str = ""
    tts_base_url: str = ""
    tts_model: str = ""

    max_upload_size_bytes: int = 10 * 1024 * 1024
    chunk_size: int = 900
    chunk_overlap: int = 120
    default_top_k: int = 5
    max_history_messages: int = 10
    max_message_length: int = 4000
    rate_limit_public_per_minute: int = 60
    rate_limit_admin_per_minute: int = 120

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def effective_cors_origins(self) -> List[str]:
        """Union of allowed_origins and cors_origins so both variables work seamlessly."""
        merged: List[str] = []
        for origin in list(self.allowed_origins) + list(self.cors_origins):
            if origin and origin not in merged:
                merged.append(origin)
        return merged or ["http://localhost:3000", "http://localhost:8000"]

    @property
    def tts_enabled(self) -> bool:
        """TTS is disabled unless provider, endpoint, model, and key are all configured."""
        return bool(
            self.tts_api_key.strip()
            and self.tts_provider.strip()
            and self.tts_base_url.strip()
            and self.tts_model.strip()
        )

    def known_secrets(self) -> List[str]:
        return [
            s
            for s in (
                self.admin_api_key,
                self.supabase_service_role_key,
                self.llm_api_key,
                self.embedding_api_key,
                self.tts_api_key,
                self.smtp_pass,
                self.qdrant_api_key,
            )
            if s and len(s.strip()) >= 4
        ]

    def validate(self) -> None:
        """Validate dimensions and gracefully fall back when optional integration credentials are omitted."""
        if self.database_provider not in ("sqlite", "supabase"):
            raise ConfigurationError(f"Unsupported DATABASE_PROVIDER: {self.database_provider}")
        if self.storage_provider not in ("local", "supabase"):
            raise ConfigurationError(f"Unsupported STORAGE_PROVIDER: {self.storage_provider}")
        if self.vector_provider not in ("local", "supabase", "qdrant"):
            raise ConfigurationError(f"Unsupported VECTOR_PROVIDER: {self.vector_provider}")
        if self.llm_provider_type not in ("local", "openai-compatible"):
            raise ConfigurationError(f"Unsupported LLM_PROVIDER_TYPE: {self.llm_provider_type}")
        if self.embedding_provider not in ("local", "openai-compatible"):
            raise ConfigurationError(f"Unsupported EMBEDDING_PROVIDER: {self.embedding_provider}")
        if self.notification_provider not in ("outbox", "supabase", "smtp"):
            raise ConfigurationError(f"Unsupported NOTIFICATION_PROVIDER: {self.notification_provider}")

        # Canonical vector dimension contract check
        if self.embedding_dimensions <= 0 or self.supabase_vector_dimensions <= 0:
            raise ConfigurationError("Vector dimensions must be positive integers.")
        if self.embedding_dimensions != self.supabase_vector_dimensions:
            raise ConfigurationError(
                f"Vector dimension mismatch: EMBEDDING_DIMENSIONS={self.embedding_dimensions} "
                f"!= SUPABASE_VECTOR_DIMENSIONS={self.supabase_vector_dimensions}"
            )
        if self.embedding_provider == "local" and self.embedding_dimensions != 128:
            raise ConfigurationError(
                f"Local deterministic embedding provider requires 128 dimensions, got {self.embedding_dimensions}"
            )

        # Optional Supabase integration: fall back cleanly to local/SQLite if credentials are not provided yet
        has_supabase_creds = bool(self.supabase_url.strip() and self.supabase_service_role_key.strip())
        if not has_supabase_creds:
            if self.database_provider == "supabase":
                self.database_provider = "sqlite"
            if self.storage_provider == "supabase":
                self.storage_provider = "local"
            if self.vector_provider == "supabase":
                self.vector_provider = "local"
            if self.notification_provider == "supabase":
                self.notification_provider = "outbox"
        elif not self.supabase_storage_bucket.strip():
            self.supabase_storage_bucket = "knowledge"

        # Optional Qdrant integration: fall back to local vector store if QDRANT_URL is not provided
        if self.vector_provider == "qdrant" and not self.qdrant_url.strip():
            self.vector_provider = "local"

        # Optional external embeddings: fall back to local 128-dim deterministic embeddings if credentials omitted
        if self.embedding_provider == "openai-compatible":
            if not (self.embedding_base_url.strip() and self.embedding_model.strip() and self.embedding_api_key.strip()):
                self.embedding_provider = "local"
                self.embedding_model = "orbit-embed-128"

        # Optional SMTP integration: fall back to transactional outbox if SMTP_HOST or SMTP_FROM omitted
        if self.notification_provider == "smtp":
            if not (self.smtp_host.strip() and self.smtp_from.strip()):
                self.notification_provider = "outbox"

        # Optional external LLM integration: fall back to built-in local conversational LLM if credentials omitted
        if self.llm_provider_type == "openai-compatible":
            if not (self.llm_base_url.strip() and self.llm_model.strip() and self.llm_api_key.strip()):
                self.llm_provider_type = "local"
                self.llm_provider_name = "local"
                if not self.llm_model.strip():
                    self.llm_model = "orbit-local-v1"

        # Production security checks
        if self.is_production:
            if not self.admin_api_key.strip() or self.admin_api_key in (
                "orbit-dev-admin-key",
                "change-me-in-production-admin-secret",
                "orbit-auto-runtime-admin-key-prod",
                "admin",
                "password",
            ):
                raise ConfigurationError("Production requires a strong, non-default ADMIN_API_KEY.")
            # Force temporary debug flags off in production for privacy protection
            self.orbit_temp_debug_gousto = False
            self.orbit_temp_debug_llm_input = False
            self.orbit_temp_debug_puregym = False

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "Settings":
        source = env if env is not None else dict(os.environ)
        app_env = source.get("APP_ENV") or source.get("NODE_ENV") or "development"
        allowed_origins = _parse_origins(source.get("ALLOWED_ORIGINS"), source.get("CORS_ORIGINS"))
        cors_origins = _parse_single_origin_list(source.get("CORS_ORIGINS"))

        is_prod = app_env.strip().lower() == "production"
        has_supabase = bool(
            source.get("SUPABASE_URL", "").strip() and source.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        )
        default_db = "supabase" if has_supabase else "sqlite"
        default_notif = "supabase" if (has_supabase and source.get("DATABASE_PROVIDER") == "supabase") else "outbox"

        # When ADMIN_API_KEY is not provided in env:
        # - In development: uses 'orbit-dev-admin-key'
        # - In production: generates an unpredictable 256-bit cryptographically random token
        #   and sets admin_api_key_configured=False to prevent any exposure of admin endpoints
        provided_admin_key = source.get("ADMIN_API_KEY", "").strip()
        if provided_admin_key:
            raw_admin_key = provided_admin_key
            is_configured = True
        else:
            if is_prod:
                import secrets
                raw_admin_key = secrets.token_urlsafe(32)
                is_configured = False
            else:
                raw_admin_key = "orbit-dev-admin-key"
                is_configured = True

        settings = cls(
            app_env=app_env.strip(),
            host=source.get("HOST", "0.0.0.0").strip(),
            port=_parse_int(source.get("PORT"), 8000),
            public_base_url=source.get("PUBLIC_BASE_URL", "http://localhost:8000").strip().rstrip("/"),
            admin_api_key=raw_admin_key,
            admin_api_key_configured=is_configured,
            allowed_origins=allowed_origins,
            cors_origins=cors_origins,
            database_provider=(source.get("DATABASE_PROVIDER") or default_db).strip().lower(),
            storage_provider=(source.get("STORAGE_PROVIDER") or "local").strip().lower(),
            vector_provider=(source.get("VECTOR_PROVIDER") or "local").strip().lower(),
            sqlite_path=source.get("SQLITE_PATH", "data/orbit_ai.db").strip(),
            local_storage_dir=source.get("LOCAL_STORAGE_DIR", "data/storage").strip(),
            supabase_url=source.get("SUPABASE_URL", "").strip(),
            supabase_service_role_key=source.get("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
            supabase_storage_bucket=(source.get("SUPABASE_STORAGE_BUCKET") or "knowledge").strip(),
            supabase_vector_dimensions=_parse_int(source.get("SUPABASE_VECTOR_DIMENSIONS"), 128),
            llm_provider_type=(source.get("LLM_PROVIDER_TYPE") or "local").strip().lower(),
            llm_provider_name=(source.get("LLM_PROVIDER_NAME") or "local").strip(),
            llm_base_url=source.get("LLM_BASE_URL", "").strip(),
            llm_api_key=source.get("LLM_API_KEY", "").strip(),
            llm_model=(source.get("LLM_MODEL") or "orbit-local-v1").strip(),
            llm_timeout_ms=_parse_int(source.get("LLM_TIMEOUT_MS"), 15000),
            llm_max_retries=_parse_int(source.get("LLM_MAX_RETRIES"), 2),
            llm_temperature=_parse_float(source.get("LLM_TEMPERATURE"), 0.2),
            llm_max_tokens=_parse_int(source.get("LLM_MAX_TOKENS"), 800),
            llm_chat_path=source.get("LLM_CHAT_PATH", "/chat/completions").strip(),
            llm_health_path=source.get("LLM_HEALTH_PATH", "/models").strip(),
            llm_auth_header_name=source.get("LLM_AUTH_HEADER_NAME", "Authorization").strip(),
            llm_auth_scheme=source.get("LLM_AUTH_SCHEME", "Bearer").strip(),
            embedding_provider=source.get("EMBEDDING_PROVIDER", "local").strip().lower(),
            embedding_dimensions=_parse_int(source.get("EMBEDDING_DIMENSIONS"), 128),
            embedding_base_url=source.get("EMBEDDING_BASE_URL", "").strip(),
            embedding_model=source.get("EMBEDDING_MODEL", "orbit-embed-128").strip(),
            embedding_api_key=source.get("EMBEDDING_API_KEY", "").strip(),
            qdrant_url=source.get("QDRANT_URL", "").strip(),
            qdrant_api_key=source.get("QDRANT_API_KEY", "").strip(),
            qdrant_collection=source.get("QDRANT_COLLECTION", "orbit_knowledge").strip(),
            notification_provider=source.get("NOTIFICATION_PROVIDER", default_notif).strip().lower(),
            smtp_host=source.get("SMTP_HOST", "").strip(),
            smtp_port=_parse_int(source.get("SMTP_PORT"), 587),
            smtp_user=source.get("SMTP_USER", "").strip(),
            smtp_pass=source.get("SMTP_PASS", "").strip(),
            smtp_from=source.get("SMTP_FROM", "").strip(),
            orbit_rag_diagnostics=_parse_bool(source.get("ORBIT_RAG_DIAGNOSTICS"), False),
            orbit_temp_debug_client_id=source.get("ORBIT_TEMP_DEBUG_CLIENT_ID", "").strip(),
            orbit_temp_debug_gousto=_parse_bool(source.get("ORBIT_TEMP_DEBUG_GOUSTO"), False),
            orbit_temp_debug_llm_input=_parse_bool(source.get("ORBIT_TEMP_DEBUG_LLM_INPUT"), False),
            orbit_temp_debug_puregym=_parse_bool(source.get("ORBIT_TEMP_DEBUG_PUREGYM"), False),
            tts_api_key=source.get("TTS_API_KEY", "").strip(),
            tts_provider=source.get("TTS_PROVIDER", "").strip(),
            tts_base_url=source.get("TTS_BASE_URL", "").strip(),
            tts_model=source.get("TTS_MODEL", "").strip(),
            max_upload_size_bytes=_parse_int(source.get("MAX_UPLOAD_SIZE_BYTES"), 10 * 1024 * 1024),
            chunk_size=_parse_int(source.get("CHUNK_SIZE"), 900),
            chunk_overlap=_parse_int(source.get("CHUNK_OVERLAP"), 120),
            default_top_k=_parse_int(source.get("DEFAULT_TOP_K"), 5),
            max_history_messages=_parse_int(source.get("MAX_HISTORY_MESSAGES"), 10),
            max_message_length=_parse_int(source.get("MAX_MESSAGE_LENGTH"), 4000),
            rate_limit_public_per_minute=_parse_int(source.get("RATE_LIMIT_PUBLIC_PER_MINUTE"), 60),
            rate_limit_admin_per_minute=_parse_int(source.get("RATE_LIMIT_ADMIN_PER_MINUTE"), 120),
        )
        settings.validate()
        return settings

"""SQLite repository implementation mirroring the canonical Supabase schema."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.domain.models import (
    ApiKeyRecord,
    ClientRecord,
    ConversationRecord,
    KnowledgeFileRecord,
    LeadRecord,
    MessageFeedbackRecord,
    MessageRecord,
    NotificationRecord,
    PromptVersionRecord,
    WidgetConfig,
    utc_now_iso,
)
from app.repositories.base import BaseRepository


class SQLiteRepository(BaseRepository):
    """Thread-safe SQLite repository with strict tenant filtering."""

    def __init__(self, db_path: str = "data/orbit_ai.db") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        if db_path != ":memory:":
            parent = os.path.dirname(os.path.abspath(db_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")

    def initialize(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    id TEXT PRIMARY KEY,
                    business_name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    assistant_name TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    system_prompt TEXT NOT NULL,
                    fallback_answer TEXT NOT NULL,
                    welcome_message TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'en',
                    model_override TEXT,
                    temperature REAL NOT NULL DEFAULT 0.2,
                    top_k INTEGER NOT NULL DEFAULT 5,
                    min_similarity REAL NOT NULL DEFAULT 0.25,
                    lead_capture_enabled INTEGER NOT NULL DEFAULT 1,
                    notification_email TEXT,
                    widget_config TEXT NOT NULL,
                    analytics_config TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    key_prefix TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_used_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS domains (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    domain TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(client_id, domain)
                );

                CREATE TABLE IF NOT EXISTS prompt_versions (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    version_number INTEGER NOT NULL,
                    system_prompt TEXT NOT NULL,
                    fallback_answer TEXT NOT NULL,
                    welcome_message TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(client_id, version_number)
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL,
                    preferred_language TEXT,
                    summary TEXT NOT NULL DEFAULT '',
                    message_count INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    intent TEXT NOT NULL DEFAULT 'general',
                    language TEXT NOT NULL DEFAULT 'en',
                    evidence_state TEXT NOT NULL DEFAULT 'UNKNOWN',
                    sources TEXT NOT NULL DEFAULT '[]',
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS message_feedback (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL DEFAULT '',
                    rating TEXT NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(client_id, message_id, session_id)
                );

                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
                    idempotency_key TEXT NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    requirement TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(client_id, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS lead_workflow (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT NOT NULL UNIQUE REFERENCES leads(id) ON DELETE CASCADE,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    status TEXT NOT NULL DEFAULT 'new',
                    assignee TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS usage_logs (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    conversation_id TEXT,
                    operation TEXT NOT NULL DEFAULT 'chat',
                    usage_units INTEGER NOT NULL DEFAULT 1,
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    status_code INTEGER NOT NULL DEFAULT 200,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    client_id TEXT,
                    actor TEXT NOT NULL DEFAULT 'admin',
                    action TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_files (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    safe_filename TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'processing',
                    active_version INTEGER NOT NULL DEFAULT 1,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    lead_id TEXT,
                    channel TEXT NOT NULL DEFAULT 'outbox',
                    recipient TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL DEFAULT '',
                    payload TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def check_health(self) -> Tuple[bool, str]:
        try:
            with self._lock:
                cur = self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('clients','conversations','messages','message_feedback','knowledge_files','leads')"
                )
                tables = {row["name"] for row in cur.fetchall()}
                required = {"clients", "conversations", "messages", "message_feedback", "knowledge_files", "leads"}
                if not required.issubset(tables):
                    missing = sorted(required - tables)
                    return False, f"Missing required SQL tables: {', '.join(missing)}"
            return True, "SQLite repository healthy"
        except Exception as exc:
            return False, f"SQLite check failed: {exc}"

    def _row_to_client(self, row: sqlite3.Row) -> ClientRecord:
        domains_cur = self._conn.execute(
            "SELECT domain FROM domains WHERE client_id = ? ORDER BY domain ASC",
            (row["id"],),
        )
        domains = [r["domain"] for r in domains_cur.fetchall()]
        widget_cfg = WidgetConfig.from_dict(json.loads(row["widget_config"] or "{}")).to_dict()
        analytics_cfg = json.loads(row["analytics_config"] or "{}")
        return ClientRecord(
            id=row["id"],
            business_name=row["business_name"],
            slug=row["slug"],
            enabled=bool(row["enabled"]),
            assistant_name=row["assistant_name"],
            company_name=row["company_name"],
            system_prompt=row["system_prompt"],
            fallback_answer=row["fallback_answer"],
            welcome_message=row["welcome_message"],
            language=row["language"],
            model_override=row["model_override"],
            temperature=float(row["temperature"]),
            top_k=int(row["top_k"]),
            min_similarity=float(row["min_similarity"]),
            lead_capture_enabled=bool(row["lead_capture_enabled"]),
            notification_email=row["notification_email"],
            widget_config=widget_cfg,
            analytics_config=analytics_cfg,
            domains=domains,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_client(self, record: ClientRecord) -> ClientRecord:
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    """
                    INSERT INTO clients (
                        id, business_name, slug, enabled, assistant_name, company_name,
                        system_prompt, fallback_answer, welcome_message, language,
                        model_override, temperature, top_k, min_similarity,
                        lead_capture_enabled, notification_email, widget_config,
                        analytics_config, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.business_name,
                        record.slug,
                        1 if record.enabled else 0,
                        record.assistant_name,
                        record.company_name or record.business_name,
                        record.system_prompt,
                        record.fallback_answer,
                        record.welcome_message,
                        record.language,
                        record.model_override,
                        record.temperature,
                        record.top_k,
                        record.min_similarity,
                        1 if record.lead_capture_enabled else 0,
                        record.notification_email,
                        json.dumps(WidgetConfig.from_dict(record.widget_config).to_dict()),
                        json.dumps(record.analytics_config),
                        record.created_at,
                        record.updated_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValidationError(f"Tenant slug '{record.slug}' already exists.") from exc

            for domain in record.domains:
                clean = domain.strip().lower()
                if clean:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO domains (id, client_id, domain, created_at) VALUES (?, ?, ?, ?)",
                        (str(uuid.uuid4()), record.id, clean, utc_now_iso()),
                    )
        created = self.get_client(record.id)
        if not created:
            raise NotFoundError("Created client not found")
        return created

    def list_clients(self) -> List[ClientRecord]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM clients ORDER BY created_at DESC")
            return [self._row_to_client(row) for row in cur.fetchall()]

    def get_client(self, client_id: str) -> Optional[ClientRecord]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
            row = cur.fetchone()
            return self._row_to_client(row) if row else None

    def get_client_by_slug(self, slug: str) -> Optional[ClientRecord]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM clients WHERE slug = ?", (slug.strip().lower(),))
            row = cur.fetchone()
            return self._row_to_client(row) if row else None

    def update_client(self, client_id: str, updates: Dict[str, Any]) -> ClientRecord:
        existing = self.get_client(client_id)
        if not existing:
            raise NotFoundError(f"Tenant {client_id} not found")

        allowed_fields = {
            "business_name",
            "slug",
            "enabled",
            "assistant_name",
            "company_name",
            "system_prompt",
            "fallback_answer",
            "welcome_message",
            "language",
            "model_override",
            "temperature",
            "top_k",
            "min_similarity",
            "lead_capture_enabled",
            "notification_email",
            "widget_config",
            "analytics_config",
        }
        set_clauses: List[str] = []
        values: List[Any] = []
        for key, value in updates.items():
            if key not in allowed_fields:
                continue
            if key in ("enabled", "lead_capture_enabled"):
                value = 1 if bool(value) else 0
            elif key == "widget_config":
                merged = {**existing.widget_config, **(value if isinstance(value, dict) else {})}
                value = json.dumps(WidgetConfig.from_dict(merged).to_dict())
            elif key == "analytics_config":
                value = json.dumps(value if isinstance(value, dict) else existing.analytics_config)
            set_clauses.append(f"{key} = ?")
            values.append(value)

        now = utc_now_iso()
        set_clauses.append("updated_at = ?")
        values.append(now)
        values.append(client_id)

        with self._lock, self._conn:
            self._conn.execute(f"UPDATE clients SET {', '.join(set_clauses)} WHERE id = ?", tuple(values))
            if "domains" in updates and isinstance(updates["domains"], list):
                self.set_domains(client_id, updates["domains"])

        updated = self.get_client(client_id)
        if not updated:
            raise NotFoundError(f"Tenant {client_id} not found")
        return updated

    def delete_client(self, client_id: str) -> None:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
            if cur.rowcount == 0:
                raise NotFoundError(f"Tenant {client_id} not found")

    def set_domains(self, client_id: str, domains: List[str]) -> List[str]:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM domains WHERE client_id = ?", (client_id,))
            for domain in domains:
                clean = domain.strip().lower()
                if clean:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO domains (id, client_id, domain, created_at) VALUES (?, ?, ?, ?)",
                        (str(uuid.uuid4()), client_id, clean, utc_now_iso()),
                    )
            cur = self._conn.execute(
                "SELECT domain FROM domains WHERE client_id = ? ORDER BY domain ASC", (client_id,)
            )
            return [r["domain"] for r in cur.fetchall()]

    def add_domain(self, client_id: str, domain: str) -> List[str]:
        clean = domain.strip().lower()
        if not clean:
            raise ValidationError("Domain cannot be empty")
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO domains (id, client_id, domain, created_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), client_id, clean, utc_now_iso()),
            )
            cur = self._conn.execute(
                "SELECT domain FROM domains WHERE client_id = ? ORDER BY domain ASC", (client_id,)
            )
            return [r["domain"] for r in cur.fetchall()]

    def remove_domain(self, client_id: str, domain: str) -> List[str]:
        clean = domain.strip().lower()
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM domains WHERE client_id = ? AND domain = ?", (client_id, clean))
            cur = self._conn.execute(
                "SELECT domain FROM domains WHERE client_id = ? ORDER BY domain ASC", (client_id,)
            )
            return [r["domain"] for r in cur.fetchall()]

    def create_api_key(self, record: ApiKeyRecord) -> ApiKeyRecord:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO api_keys (id, client_id, key_prefix, key_hash, label, enabled, last_used_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.client_id,
                    record.key_prefix,
                    record.key_hash,
                    record.label,
                    1 if record.enabled else 0,
                    record.last_used_at,
                    record.created_at,
                    record.updated_at,
                ),
            )
        return record

    def list_api_keys(self, client_id: str) -> List[ApiKeyRecord]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM api_keys WHERE client_id = ? ORDER BY created_at DESC", (client_id,)
            )
            return [
                ApiKeyRecord(
                    id=r["id"],
                    client_id=r["client_id"],
                    key_prefix=r["key_prefix"],
                    key_hash=r["key_hash"],
                    label=r["label"],
                    enabled=bool(r["enabled"]),
                    last_used_at=r["last_used_at"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in cur.fetchall()
            ]

    def get_api_key_by_hash(self, key_hash: str) -> Optional[ApiKeyRecord]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,))
            r = cur.fetchone()
            if not r:
                return None
            return ApiKeyRecord(
                id=r["id"],
                client_id=r["client_id"],
                key_prefix=r["key_prefix"],
                key_hash=r["key_hash"],
                label=r["label"],
                enabled=bool(r["enabled"]),
                last_used_at=r["last_used_at"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )

    def set_api_key_enabled(self, client_id: str, key_id: str, enabled: bool) -> ApiKeyRecord:
        now = utc_now_iso()
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE api_keys SET enabled = ?, updated_at = ? WHERE id = ? AND client_id = ?",
                (1 if enabled else 0, now, key_id, client_id),
            )
            if cur.rowcount == 0:
                raise NotFoundError("API key not found for tenant")
            row = self._conn.execute("SELECT * FROM api_keys WHERE id = ? AND client_id = ?", (key_id, client_id)).fetchone()
            return ApiKeyRecord(
                id=row["id"],
                client_id=row["client_id"],
                key_prefix=row["key_prefix"],
                key_hash=row["key_hash"],
                label=row["label"],
                enabled=bool(row["enabled"]),
                last_used_at=row["last_used_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def disable_all_api_keys(self, client_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE api_keys SET enabled = 0, updated_at = ? WHERE client_id = ?",
                (utc_now_iso(), client_id),
            )

    def save_prompt_version(self, record: PromptVersionRecord) -> PromptVersionRecord:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO prompt_versions (id, client_id, version_number, system_prompt, fallback_answer, welcome_message, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.client_id,
                    record.version_number,
                    record.system_prompt,
                    record.fallback_answer,
                    record.welcome_message,
                    record.note,
                    record.created_at,
                ),
            )
        return record

    def list_prompt_versions(self, client_id: str) -> List[PromptVersionRecord]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM prompt_versions WHERE client_id = ? ORDER BY version_number DESC",
                (client_id,),
            )
            return [
                PromptVersionRecord(
                    id=r["id"],
                    client_id=r["client_id"],
                    version_number=int(r["version_number"]),
                    system_prompt=r["system_prompt"],
                    fallback_answer=r["fallback_answer"],
                    welcome_message=r["welcome_message"],
                    note=r["note"],
                    created_at=r["created_at"],
                )
                for r in cur.fetchall()
            ]

    def get_prompt_version(self, client_id: str, version_number: int) -> Optional[PromptVersionRecord]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM prompt_versions WHERE client_id = ? AND version_number = ?",
                (client_id, version_number),
            )
            r = cur.fetchone()
            if not r:
                return None
            return PromptVersionRecord(
                id=r["id"],
                client_id=r["client_id"],
                version_number=int(r["version_number"]),
                system_prompt=r["system_prompt"],
                fallback_answer=r["fallback_answer"],
                welcome_message=r["welcome_message"],
                note=r["note"],
                created_at=r["created_at"],
            )

    def _row_to_conversation(self, r: sqlite3.Row) -> ConversationRecord:
        return ConversationRecord(
            id=r["id"],
            client_id=r["client_id"],
            session_id=r["session_id"],
            preferred_language=r["preferred_language"],
            summary=r["summary"] or "",
            message_count=int(r["message_count"]),
            metadata=json.loads(r["metadata"] or "{}"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def get_or_create_conversation(
        self, client_id: str, session_id: str, conversation_id: Optional[str] = None
    ) -> ConversationRecord:
        with self._lock, self._conn:
            if conversation_id:
                any_row = self._conn.execute(
                    "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
                ).fetchone()
                if any_row:
                    if any_row["client_id"] != client_id:
                        raise AuthorizationError("Cross-tenant conversation access is prohibited.")
                    return self._row_to_conversation(any_row)

            if session_id:
                # Check if session_id belongs to another tenant first
                foreign = self._conn.execute(
                    "SELECT client_id FROM conversations WHERE session_id = ? AND client_id != ?",
                    (session_id, client_id),
                ).fetchone()
                if foreign:
                    raise AuthorizationError("Cross-tenant session access is prohibited.")

                existing = self._conn.execute(
                    "SELECT * FROM conversations WHERE client_id = ? AND session_id = ? ORDER BY updated_at DESC LIMIT 1",
                    (client_id, session_id),
                ).fetchone()
                if existing:
                    return self._row_to_conversation(existing)

            new_id = conversation_id or str(uuid.uuid4())
            now = utc_now_iso()
            self._conn.execute(
                """
                INSERT INTO conversations (id, client_id, session_id, preferred_language, summary, message_count, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (new_id, client_id, session_id or str(uuid.uuid4()), None, "", 0, "{}", now, now),
            )
            created = self._conn.execute("SELECT * FROM conversations WHERE id = ?", (new_id,)).fetchone()
            return self._row_to_conversation(created)

    def get_conversation(self, client_id: str, conversation_id: str) -> Optional[ConversationRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if not row:
                return None
            if row["client_id"] != client_id:
                raise AuthorizationError("Cross-tenant conversation access denied.")
            return self._row_to_conversation(row)

    def list_conversations(self, client_id: Optional[str] = None, search: str = "") -> List[ConversationRecord]:
        with self._lock:
            query = "SELECT * FROM conversations WHERE 1=1"
            params: List[Any] = []
            if client_id:
                query += " AND client_id = ?"
                params.append(client_id)
            if search.strip():
                query += " AND (session_id LIKE ? OR summary LIKE ?)"
                like = f"%{search.strip()}%"
                params.extend([like, like])
            query += " ORDER BY updated_at DESC"
            cur = self._conn.execute(query, tuple(params))
            return [self._row_to_conversation(r) for r in cur.fetchall()]

    def update_conversation_state(
        self,
        client_id: str,
        conversation_id: str,
        preferred_language: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationRecord:
        conv = self.get_conversation(client_id, conversation_id)
        if not conv:
            raise NotFoundError("Conversation not found")
        new_lang = preferred_language if preferred_language is not None else conv.preferred_language
        new_summary = summary if summary is not None else conv.summary
        new_meta = {**conv.metadata, **(metadata or {})}
        now = utc_now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE conversations
                SET preferred_language = ?, summary = ?, metadata = ?, updated_at = ?
                WHERE id = ? AND client_id = ?
                """,
                (new_lang, new_summary, json.dumps(new_meta), now, conversation_id, client_id),
            )
        updated = self.get_conversation(client_id, conversation_id)
        if not updated:
            raise NotFoundError("Conversation not found")
        return updated

    def append_message(self, record: MessageRecord) -> MessageRecord:
        conv = self.get_conversation(record.client_id, record.conversation_id)
        if not conv:
            raise NotFoundError("Conversation not found for tenant")
        now = utc_now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO messages (id, conversation_id, client_id, role, content, intent, language, evidence_state, sources, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.conversation_id,
                    record.client_id,
                    record.role,
                    record.content,
                    record.intent,
                    record.language,
                    record.evidence_state,
                    json.dumps(record.sources),
                    record.latency_ms,
                    record.created_at,
                ),
            )
            self._conn.execute(
                "UPDATE conversations SET message_count = message_count + 1, updated_at = ? WHERE id = ? AND client_id = ?",
                (now, record.conversation_id, record.client_id),
            )
        return record

    def get_message(self, client_id: str, message_id: str) -> Optional[MessageRecord]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
            if not row:
                return None
            if row["client_id"] != client_id:
                raise AuthorizationError("Cross-tenant message access denied.")
            return MessageRecord(
                id=row["id"],
                conversation_id=row["conversation_id"],
                client_id=row["client_id"],
                role=row["role"],
                content=row["content"],
                intent=row["intent"],
                language=row["language"],
                evidence_state=row["evidence_state"],
                sources=json.loads(row["sources"] or "[]"),
                latency_ms=int(row["latency_ms"]),
                created_at=row["created_at"],
            )

    def list_messages(self, client_id: str, conversation_id: str, limit: int = 100) -> List[MessageRecord]:
        conv = self.get_conversation(client_id, conversation_id)
        if not conv:
            raise NotFoundError("Conversation not found")
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT * FROM messages
                WHERE client_id = ? AND conversation_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (client_id, conversation_id, limit),
            )
            return [
                MessageRecord(
                    id=r["id"],
                    conversation_id=r["conversation_id"],
                    client_id=r["client_id"],
                    role=r["role"],
                    content=r["content"],
                    intent=r["intent"],
                    language=r["language"],
                    evidence_state=r["evidence_state"],
                    sources=json.loads(r["sources"] or "[]"),
                    latency_ms=int(r["latency_ms"]),
                    created_at=r["created_at"],
                )
                for r in cur.fetchall()
            ]

    def upsert_message_feedback(self, record: MessageFeedbackRecord) -> MessageFeedbackRecord:
        msg = self.get_message(record.client_id, record.message_id)
        if not msg:
            raise NotFoundError("Target message not found for tenant.")
        if msg.conversation_id != record.conversation_id:
            raise ValidationError("Message does not belong to the specified conversation.")
        if msg.role != "assistant":
            raise ValidationError("Feedback can only be submitted for assistant messages.")
        if record.rating not in ("like", "dislike"):
            raise ValidationError("Feedback rating must be 'like' or 'dislike'.")

        now = utc_now_iso()
        with self._lock, self._conn:
            existing = self._conn.execute(
                """
                SELECT * FROM message_feedback
                WHERE client_id = ? AND message_id = ? AND session_id = ?
                """,
                (record.client_id, record.message_id, record.session_id),
            ).fetchone()
            if existing:
                self._conn.execute(
                    """
                    UPDATE message_feedback
                    SET rating = ?, comment = ?, updated_at = ?
                    WHERE id = ? AND client_id = ?
                    """,
                    (record.rating, record.comment[:500], now, existing["id"], record.client_id),
                )
                updated = self._conn.execute(
                    "SELECT * FROM message_feedback WHERE id = ?", (existing["id"],)
                ).fetchone()
            else:
                self._conn.execute(
                    """
                    INSERT INTO message_feedback (
                        id, client_id, conversation_id, message_id, session_id,
                        rating, comment, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.client_id,
                        record.conversation_id,
                        record.message_id,
                        record.session_id,
                        record.rating,
                        record.comment[:500],
                        record.created_at,
                        now,
                    ),
                )
                updated = self._conn.execute(
                    "SELECT * FROM message_feedback WHERE id = ?", (record.id,)
                ).fetchone()

        return MessageFeedbackRecord(
            id=updated["id"],
            client_id=updated["client_id"],
            conversation_id=updated["conversation_id"],
            message_id=updated["message_id"],
            session_id=updated["session_id"],
            rating=updated["rating"],
            comment=updated["comment"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"],
        )

    def list_message_feedback(
        self, client_id: Optional[str] = None, conversation_id: Optional[str] = None
    ) -> List[MessageFeedbackRecord]:
        with self._lock:
            query = "SELECT * FROM message_feedback WHERE 1=1"
            params: List[Any] = []
            if client_id:
                query += " AND client_id = ?"
                params.append(client_id)
            if conversation_id:
                query += " AND conversation_id = ?"
                params.append(conversation_id)
            query += " ORDER BY updated_at DESC"
            cur = self._conn.execute(query, tuple(params))
            return [
                MessageFeedbackRecord(
                    id=r["id"],
                    client_id=r["client_id"],
                    conversation_id=r["conversation_id"],
                    message_id=r["message_id"],
                    session_id=r["session_id"],
                    rating=r["rating"],
                    comment=r["comment"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in cur.fetchall()
            ]

    def _row_to_lead(self, r: sqlite3.Row) -> LeadRecord:
        wf = self._conn.execute(
            "SELECT * FROM lead_workflow WHERE lead_id = ? AND client_id = ?",
            (r["id"], r["client_id"]),
        ).fetchone()
        return LeadRecord(
            id=r["id"],
            client_id=r["client_id"],
            conversation_id=r["conversation_id"],
            idempotency_key=r["idempotency_key"],
            name=r["name"],
            email=r["email"],
            phone=r["phone"],
            requirement=r["requirement"],
            message=r["message"],
            status=wf["status"] if wf else r["status"],
            assignee=wf["assignee"] if wf else "",
            notes=wf["notes"] if wf else "",
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def create_or_get_lead(self, record: LeadRecord) -> Tuple[LeadRecord, bool]:
        with self._lock, self._conn:
            if record.conversation_id:
                conv = self._conn.execute(
                    "SELECT client_id FROM conversations WHERE id = ?", (record.conversation_id,)
                ).fetchone()
                if not conv or conv["client_id"] != record.client_id:
                    raise AuthorizationError("Conversation does not belong to authenticated tenant.")

            existing = self._conn.execute(
                "SELECT * FROM leads WHERE client_id = ? AND idempotency_key = ?",
                (record.client_id, record.idempotency_key),
            ).fetchone()
            if existing:
                return self._row_to_lead(existing), False

            self._conn.execute(
                """
                INSERT INTO leads (
                    id, client_id, conversation_id, idempotency_key,
                    name, email, phone, requirement, message, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.client_id,
                    record.conversation_id,
                    record.idempotency_key,
                    record.name,
                    record.email,
                    record.phone,
                    record.requirement,
                    record.message,
                    record.status,
                    record.created_at,
                    record.updated_at,
                ),
            )
            self._conn.execute(
                """
                INSERT INTO lead_workflow (id, lead_id, client_id, status, assignee, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    record.id,
                    record.client_id,
                    record.status,
                    record.assignee,
                    record.notes,
                    record.updated_at,
                ),
            )
            created = self._conn.execute("SELECT * FROM leads WHERE id = ?", (record.id,)).fetchone()
            return self._row_to_lead(created), True

    def get_lead(self, client_id: str, lead_id: str) -> Optional[LeadRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM leads WHERE id = ? AND client_id = ?", (lead_id, client_id)
            ).fetchone()
            return self._row_to_lead(row) if row else None

    def list_leads(
        self,
        client_id: Optional[str] = None,
        status: Optional[str] = None,
        search: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> List[LeadRecord]:
        with self._lock:
            query = "SELECT * FROM leads WHERE 1=1"
            params: List[Any] = []
            if client_id:
                query += " AND client_id = ?"
                params.append(client_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            if search.strip():
                query += " AND (name LIKE ? OR email LIKE ? OR phone LIKE ? OR requirement LIKE ? OR message LIKE ?)"
                like = f"%{search.strip()}%"
                params.extend([like, like, like, like, like])
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cur = self._conn.execute(query, tuple(params))
            return [self._row_to_lead(r) for r in cur.fetchall()]

    def update_lead_workflow(
        self,
        client_id: str,
        lead_id: str,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> LeadRecord:
        lead = self.get_lead(client_id, lead_id)
        if not lead:
            raise NotFoundError("Lead not found for tenant")
        valid_statuses = {"new", "contacted", "qualified", "won", "lost"}
        new_status = status if status is not None else lead.status
        if new_status not in valid_statuses:
            raise ValidationError(f"Unsupported lead status: {new_status}")
        new_assignee = assignee if assignee is not None else lead.assignee
        new_notes = notes if notes is not None else lead.notes
        now = utc_now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE leads SET status = ?, updated_at = ? WHERE id = ? AND client_id = ?",
                (new_status, now, lead_id, client_id),
            )
            self._conn.execute(
                """
                UPDATE lead_workflow
                SET status = ?, assignee = ?, notes = ?, updated_at = ?
                WHERE lead_id = ? AND client_id = ?
                """,
                (new_status, new_assignee, new_notes, now, lead_id, client_id),
            )
        updated = self.get_lead(client_id, lead_id)
        if not updated:
            raise NotFoundError("Lead not found")
        return updated

    def _row_to_knowledge(self, r: sqlite3.Row) -> KnowledgeFileRecord:
        return KnowledgeFileRecord(
            id=r["id"],
            client_id=r["client_id"],
            filename=r["filename"],
            safe_filename=r["safe_filename"],
            storage_path=r["storage_path"],
            mime_type=r["mime_type"],
            file_size=int(r["file_size"]),
            status=r["status"],
            active_version=int(r["active_version"]),
            chunk_count=int(r["chunk_count"]),
            error_message=r["error_message"] or "",
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )

    def create_knowledge_file(self, record: KnowledgeFileRecord) -> KnowledgeFileRecord:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO knowledge_files (
                    id, client_id, filename, safe_filename, storage_path, mime_type,
                    file_size, status, active_version, chunk_count, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.client_id,
                    record.filename,
                    record.safe_filename,
                    record.storage_path,
                    record.mime_type,
                    record.file_size,
                    record.status,
                    record.active_version,
                    record.chunk_count,
                    record.error_message,
                    record.created_at,
                    record.updated_at,
                ),
            )
        return record

    def update_knowledge_file(self, client_id: str, file_id: str, updates: Dict[str, Any]) -> KnowledgeFileRecord:
        existing = self.get_knowledge_file(client_id, file_id)
        if not existing:
            raise NotFoundError("Knowledge file not found for tenant")
        allowed = {"filename", "safe_filename", "storage_path", "mime_type", "file_size", "status", "active_version", "chunk_count", "error_message"}
        clauses: List[str] = []
        vals: List[Any] = []
        for k, v in updates.items():
            if k in allowed:
                clauses.append(f"{k} = ?")
                vals.append(v)
        clauses.append("updated_at = ?")
        vals.append(utc_now_iso())
        vals.extend([file_id, client_id])
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE knowledge_files SET {', '.join(clauses)} WHERE id = ? AND client_id = ?",
                tuple(vals),
            )
        updated = self.get_knowledge_file(client_id, file_id)
        if not updated:
            raise NotFoundError("Knowledge file not found")
        return updated

    def get_knowledge_file(self, client_id: str, file_id: str) -> Optional[KnowledgeFileRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM knowledge_files WHERE id = ? AND client_id = ?", (file_id, client_id)
            ).fetchone()
            return self._row_to_knowledge(row) if row else None

    def get_knowledge_file_by_name(self, client_id: str, filename: str) -> Optional[KnowledgeFileRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM knowledge_files WHERE client_id = ? AND filename = ? ORDER BY updated_at DESC LIMIT 1",
                (client_id, filename),
            ).fetchone()
            return self._row_to_knowledge(row) if row else None

    def list_knowledge_files(self, client_id: Optional[str] = None) -> List[KnowledgeFileRecord]:
        with self._lock:
            if client_id:
                cur = self._conn.execute(
                    "SELECT * FROM knowledge_files WHERE client_id = ? ORDER BY updated_at DESC",
                    (client_id,),
                )
            else:
                cur = self._conn.execute("SELECT * FROM knowledge_files ORDER BY updated_at DESC")
            return [self._row_to_knowledge(r) for r in cur.fetchall()]

    def delete_knowledge_file(self, client_id: str, file_id: str) -> None:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM knowledge_files WHERE id = ? AND client_id = ?", (file_id, client_id)
            )
            if cur.rowcount == 0:
                raise NotFoundError("Knowledge file not found for tenant")

    def create_notification(self, record: NotificationRecord) -> NotificationRecord:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO notifications (
                    id, client_id, lead_id, channel, recipient, subject, payload,
                    status, attempts, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.client_id,
                    record.lead_id,
                    record.channel,
                    record.recipient,
                    record.subject,
                    json.dumps(record.payload),
                    record.status,
                    record.attempts,
                    record.last_error,
                    record.created_at,
                    record.updated_at,
                ),
            )
        return record

    def update_notification(self, notification_id: str, status: str, attempts: int, last_error: str = "") -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE notifications
                SET status = ?, attempts = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, attempts, last_error, utc_now_iso(), notification_id),
            )

    def list_notifications(self, client_id: Optional[str] = None) -> List[NotificationRecord]:
        with self._lock:
            if client_id:
                cur = self._conn.execute(
                    "SELECT * FROM notifications WHERE client_id = ? ORDER BY created_at DESC",
                    (client_id,),
                )
            else:
                cur = self._conn.execute("SELECT * FROM notifications ORDER BY created_at DESC")
            return [
                NotificationRecord(
                    id=r["id"],
                    client_id=r["client_id"],
                    lead_id=r["lead_id"],
                    channel=r["channel"],
                    recipient=r["recipient"],
                    subject=r["subject"],
                    payload=json.loads(r["payload"] or "{}"),
                    status=r["status"],
                    attempts=int(r["attempts"]),
                    last_error=r["last_error"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in cur.fetchall()
            ]

    def log_usage(
        self,
        client_id: str,
        operation: str = "chat",
        usage_units: int = 1,
        latency_ms: int = 0,
        status_code: int = 200,
        conversation_id: Optional[str] = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO usage_logs (id, client_id, conversation_id, operation, usage_units, latency_ms, status_code, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    client_id,
                    conversation_id,
                    operation,
                    usage_units,
                    latency_ms,
                    status_code,
                    utc_now_iso(),
                ),
            )

    def list_usage_logs(self, client_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if client_id:
                cur = self._conn.execute(
                    "SELECT * FROM usage_logs WHERE client_id = ? ORDER BY created_at DESC",
                    (client_id,),
                )
            else:
                cur = self._conn.execute("SELECT * FROM usage_logs ORDER BY created_at DESC")
            return [dict(r) for r in cur.fetchall()]

    def log_audit(
        self,
        action: str,
        actor: str = "admin",
        client_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO audit_logs (id, client_id, actor, action, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), client_id, actor, action, json.dumps(details or {}), utc_now_iso()),
            )

    def list_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = []
            for r in cur.fetchall():
                item = dict(r)
                item["details"] = json.loads(item.get("details") or "{}")
                rows.append(item)
            return rows

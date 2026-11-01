"""Abstract repository interface for tenant-scoped data access."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

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
)


class BaseRepository(ABC):
    """Contract shared by SupabaseRepository and SQLiteRepository."""

    @abstractmethod
    def initialize(self) -> None:
        pass

    @abstractmethod
    def check_health(self) -> Tuple[bool, str]:
        pass

    @abstractmethod
    def create_client(self, record: ClientRecord) -> ClientRecord:
        pass

    @abstractmethod
    def list_clients(self) -> List[ClientRecord]:
        pass

    @abstractmethod
    def get_client(self, client_id: str) -> Optional[ClientRecord]:
        pass

    @abstractmethod
    def get_client_by_slug(self, slug: str) -> Optional[ClientRecord]:
        pass

    @abstractmethod
    def update_client(self, client_id: str, updates: Dict[str, Any]) -> ClientRecord:
        pass

    @abstractmethod
    def delete_client(self, client_id: str) -> None:
        pass

    @abstractmethod
    def set_domains(self, client_id: str, domains: List[str]) -> List[str]:
        pass

    @abstractmethod
    def add_domain(self, client_id: str, domain: str) -> List[str]:
        pass

    @abstractmethod
    def remove_domain(self, client_id: str, domain: str) -> List[str]:
        pass

    @abstractmethod
    def create_api_key(self, record: ApiKeyRecord) -> ApiKeyRecord:
        pass

    @abstractmethod
    def list_api_keys(self, client_id: str) -> List[ApiKeyRecord]:
        pass

    @abstractmethod
    def get_api_key_by_hash(self, key_hash: str) -> Optional[ApiKeyRecord]:
        pass

    @abstractmethod
    def set_api_key_enabled(self, client_id: str, key_id: str, enabled: bool) -> ApiKeyRecord:
        pass

    @abstractmethod
    def disable_all_api_keys(self, client_id: str) -> None:
        pass

    @abstractmethod
    def save_prompt_version(self, record: PromptVersionRecord) -> PromptVersionRecord:
        pass

    @abstractmethod
    def list_prompt_versions(self, client_id: str) -> List[PromptVersionRecord]:
        pass

    @abstractmethod
    def get_prompt_version(self, client_id: str, version_number: int) -> Optional[PromptVersionRecord]:
        pass

    @abstractmethod
    def get_or_create_conversation(
        self, client_id: str, session_id: str, conversation_id: Optional[str] = None
    ) -> ConversationRecord:
        pass

    @abstractmethod
    def get_conversation(self, client_id: str, conversation_id: str) -> Optional[ConversationRecord]:
        pass

    @abstractmethod
    def list_conversations(self, client_id: Optional[str] = None, search: str = "") -> List[ConversationRecord]:
        pass

    @abstractmethod
    def update_conversation_state(
        self,
        client_id: str,
        conversation_id: str,
        preferred_language: Optional[str] = None,
        summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationRecord:
        pass

    @abstractmethod
    def append_message(self, record: MessageRecord) -> MessageRecord:
        pass

    @abstractmethod
    def get_message(self, client_id: str, message_id: str) -> Optional[MessageRecord]:
        pass

    @abstractmethod
    def list_messages(self, client_id: str, conversation_id: str, limit: int = 100) -> List[MessageRecord]:
        pass

    @abstractmethod
    def upsert_message_feedback(self, record: MessageFeedbackRecord) -> MessageFeedbackRecord:
        pass

    @abstractmethod
    def list_message_feedback(
        self, client_id: Optional[str] = None, conversation_id: Optional[str] = None
    ) -> List[MessageFeedbackRecord]:
        pass

    @abstractmethod
    def create_or_get_lead(self, record: LeadRecord) -> Tuple[LeadRecord, bool]:
        pass

    @abstractmethod
    def get_lead(self, client_id: str, lead_id: str) -> Optional[LeadRecord]:
        pass

    @abstractmethod
    def list_leads(
        self,
        client_id: Optional[str] = None,
        status: Optional[str] = None,
        search: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> List[LeadRecord]:
        pass

    @abstractmethod
    def update_lead_workflow(
        self,
        client_id: str,
        lead_id: str,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> LeadRecord:
        pass

    @abstractmethod
    def create_knowledge_file(self, record: KnowledgeFileRecord) -> KnowledgeFileRecord:
        pass

    @abstractmethod
    def update_knowledge_file(self, client_id: str, file_id: str, updates: Dict[str, Any]) -> KnowledgeFileRecord:
        pass

    @abstractmethod
    def get_knowledge_file(self, client_id: str, file_id: str) -> Optional[KnowledgeFileRecord]:
        pass

    @abstractmethod
    def get_knowledge_file_by_name(self, client_id: str, filename: str) -> Optional[KnowledgeFileRecord]:
        pass

    @abstractmethod
    def list_knowledge_files(self, client_id: Optional[str] = None) -> List[KnowledgeFileRecord]:
        pass

    @abstractmethod
    def delete_knowledge_file(self, client_id: str, file_id: str) -> None:
        pass

    @abstractmethod
    def create_notification(self, record: NotificationRecord) -> NotificationRecord:
        pass

    @abstractmethod
    def update_notification(self, notification_id: str, status: str, attempts: int, last_error: str = "") -> None:
        pass

    @abstractmethod
    def list_notifications(self, client_id: Optional[str] = None) -> List[NotificationRecord]:
        pass

    @abstractmethod
    def log_usage(
        self,
        client_id: str,
        operation: str = "chat",
        usage_units: int = 1,
        latency_ms: int = 0,
        status_code: int = 200,
        conversation_id: Optional[str] = None,
    ) -> None:
        pass

    @abstractmethod
    def list_usage_logs(self, client_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def log_audit(self, action: str, actor: str = "admin", client_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        pass

    @abstractmethod
    def list_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        pass

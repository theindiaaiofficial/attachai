"""Administrator API controller for tenants, knowledge, conversations, leads, prompts, and analytics."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional, Tuple

from app.api.schemas import serialize_admin_tenant
from app.core.dependencies import ServiceContainer
from app.core.exceptions import AuthenticationError
from app.core.security import constant_time_equals, create_admin_session_token
from app.middleware.authentication import verify_admin_request


class AdminApiController:
    """Protected administrative endpoints requiring `x-admin-api-key` or verified admin session."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container

    def login(self, api_key: str) -> Tuple[str, str]:
        clean_key = (api_key or "").strip()
        if self.container.settings.is_production:
            if not self.container.settings.admin_api_key_configured:
                raise AuthenticationError("Production administrator API access requires configuring the ADMIN_API_KEY environment variable.")
            if clean_key in (
                "orbit-dev-admin-key",
                "change-me-in-production-admin-secret",
                "orbit-auto-runtime-admin-key-prod",
            ):
                raise AuthenticationError("Insecure default administrator API key is prohibited in production.")
        if not constant_time_equals(self.container.settings.admin_api_key, clean_key):
            raise AuthenticationError("Invalid administrator API key.")
        return create_admin_session_token(self.container.settings.admin_api_key)

    def authorize(
        self,
        headers: Dict[str, str],
        cookies: Optional[Dict[str, str]] = None,
        method: str = "GET",
    ) -> None:
        verify_admin_request(self.container, headers=headers, cookies=cookies, method=method)

    def get_overview(self, headers: Dict[str, str], cookies: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        self.authorize(headers, cookies, "GET")
        summary = self.container.analytics_service.get_summary()
        diagnostics = self.container.provider_diagnostics()
        audits = self.container.repository.list_audit_logs(limit=15)
        return {
            "summary": summary,
            "providers": diagnostics,
            "recentActivity": audits,
        }

    def list_tenants(self, headers: Dict[str, str], cookies: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        self.authorize(headers, cookies, "GET")
        tenants = self.container.client_service.list_tenants()
        return {
            "tenants": [
                serialize_admin_tenant(t, self.container.settings.public_base_url) for t in tenants
            ]
        }

    def create_tenant(
        self,
        headers: Dict[str, str],
        body: Dict[str, Any],
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.authorize(headers, cookies, "POST")
        client, raw_key = self.container.client_service.create_tenant(body)
        return {
            "tenant": serialize_admin_tenant(client, self.container.settings.public_base_url),
            "apiKey": raw_key,
            "notice": "Store this API key securely now. It will not be shown in full again.",
        }

    def get_tenant_detail(
        self,
        headers: Dict[str, str],
        client_id: str,
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.authorize(headers, cookies, "GET")
        client = self.container.client_service.get_tenant(client_id)
        keys = self.container.client_service.list_api_keys(client_id)
        versions = self.container.client_service.list_prompt_versions(client_id)
        files = self.container.knowledge_service.list_files(client_id)
        return {
            "tenant": serialize_admin_tenant(client, self.container.settings.public_base_url),
            "apiKeys": [
                {
                    "id": k.id,
                    "keyPrefix": k.key_prefix,
                    "label": k.label,
                    "enabled": k.enabled,
                    "createdAt": k.created_at,
                }
                for k in keys
            ],
            "promptVersions": [asdict(v) for v in versions],
            "knowledgeFiles": [asdict(f) for f in files],
        }

    def update_tenant(
        self,
        headers: Dict[str, str],
        client_id: str,
        body: Dict[str, Any],
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.authorize(headers, cookies, "PATCH")
        updated = self.container.client_service.update_tenant(client_id, body)
        return {"tenant": serialize_admin_tenant(updated, self.container.settings.public_base_url)}

    def duplicate_tenant(
        self,
        headers: Dict[str, str],
        client_id: str,
        body: Optional[Dict[str, Any]] = None,
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.authorize(headers, cookies, "POST")
        body = body or {}
        dup, raw_key = self.container.client_service.duplicate_tenant(
            client_id=client_id,
            new_slug=body.get("slug"),
            new_name=body.get("businessName") or body.get("business_name"),
        )
        return {
            "tenant": serialize_admin_tenant(dup, self.container.settings.public_base_url),
            "apiKey": raw_key,
        }

    def delete_tenant(
        self,
        headers: Dict[str, str],
        client_id: str,
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.authorize(headers, cookies, "DELETE")
        cleanup = self.container.client_service.delete_tenant(client_id)
        return {"deleted": True, "cleanup": cleanup}

    def rotate_key(
        self,
        headers: Dict[str, str],
        client_id: str,
        label: str = "Rotated Widget Key",
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.authorize(headers, cookies, "POST")
        raw_key, record = self.container.client_service.rotate_api_key(client_id, label=label)
        return {
            "apiKey": raw_key,
            "keyRecord": {
                "id": record.id,
                "keyPrefix": record.key_prefix,
                "label": record.label,
                "enabled": record.enabled,
            },
        }

    def upload_knowledge(
        self,
        headers: Dict[str, str],
        client_id: str,
        filename: str,
        content: bytes,
        mime_type: str = "application/octet-stream",
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.authorize(headers, cookies, "POST")
        file_rec = self.container.knowledge_service.ingest_document(
            client_id=client_id,
            filename=filename,
            content=content,
            mime_type=mime_type,
        )
        return {"file": asdict(file_rec)}

    def rebuild_knowledge(
        self,
        headers: Dict[str, str],
        client_id: str,
        file_id: str,
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.authorize(headers, cookies, "POST")
        file_rec = self.container.knowledge_service.rebuild_document(client_id, file_id)
        return {"file": asdict(file_rec)}

    def delete_knowledge(
        self,
        headers: Dict[str, str],
        client_id: str,
        file_id: str,
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.authorize(headers, cookies, "DELETE")
        self.container.knowledge_service.delete_file(client_id, file_id)
        return {"deleted": True}

    def list_conversations(
        self,
        headers: Dict[str, str],
        client_id: Optional[str] = None,
        search: str = "",
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.authorize(headers, cookies, "GET")
        convs = self.container.repository.list_conversations(client_id=client_id, search=search)
        feedback = self.container.repository.list_message_feedback(client_id=client_id)
        return {
            "conversations": [asdict(c) for c in convs],
            "feedback": [asdict(f) for f in feedback],
        }

    def get_conversation_messages(
        self,
        headers: Dict[str, str],
        client_id: str,
        conversation_id: str,
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self.authorize(headers, cookies, "GET")
        conv = self.container.repository.get_conversation(client_id, conversation_id)
        msgs = self.container.repository.list_messages(client_id, conversation_id)
        feedback = self.container.repository.list_message_feedback(
            client_id=client_id, conversation_id=conversation_id
        )
        return {
            "conversation": asdict(conv) if conv else None,
            "messages": [asdict(m) for m in msgs],
            "feedback": [asdict(f) for f in feedback],
        }

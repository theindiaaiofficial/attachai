"""Multi-tenant Client/Tenant management service."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.exceptions import AuthenticationError, AuthorizationError, NotFoundError, ValidationError
from app.core.security import generate_tenant_api_key, hash_api_key, is_domain_allowed
from app.domain.models import ApiKeyRecord, ClientRecord, PromptVersionRecord, WidgetConfig, utc_now_iso
from app.providers.storage import BaseStorageProvider
from app.providers.vector import BaseVectorProvider
from app.repositories.base import BaseRepository
from app.utils.validators import validate_slug


class ClientService:
    """Manages tenant lifecycle, API keys, domain allowlists, and prompt versions."""

    def __init__(
        self,
        repository: BaseRepository,
        storage_provider: BaseStorageProvider,
        vector_provider: BaseVectorProvider,
    ) -> None:
        self.repository = repository
        self.storage_provider = storage_provider
        self.vector_provider = vector_provider

    def create_tenant(self, payload: Dict[str, Any]) -> Tuple[ClientRecord, str]:
        """Create a tenant, initial prompt version, and primary API key. Returns (client, raw_api_key)."""
        business_name = str(payload.get("business_name") or payload.get("businessName") or "").strip()
        if not business_name:
            raise ValidationError("business_name is required.")
        raw_slug = str(payload.get("slug") or business_name.lower().replace(" ", "-"))
        slug = validate_slug(raw_slug)

        if self.repository.get_client_by_slug(slug):
            raise ValidationError(f"Tenant slug '{slug}' is already in use.")

        client_id = str(payload.get("id") or uuid.uuid4())
        assistant_name = str(payload.get("assistant_name") or payload.get("assistantName") or f"{business_name} AI").strip()
        company_name = str(payload.get("company_name") or payload.get("companyName") or business_name).strip()
        system_prompt = str(
            payload.get("system_prompt")
            or payload.get("systemPrompt")
            or f"You are {assistant_name}, the helpful customer support assistant for {company_name}. Answer accurately using verified company information."
        ).strip()
        fallback_answer = str(
            payload.get("fallback_answer")
            or payload.get("fallbackAnswer")
            or f"I do not have enough verified information in {company_name}'s knowledge base to answer that accurately. Please share your contact details and our team will help you."
        ).strip()
        welcome_message = str(
            payload.get("welcome_message")
            or payload.get("welcomeMessage")
            or f"Hello! I'm {assistant_name} from {company_name}. How can I help you today?"
        ).strip()
        language = str(payload.get("language") or "en").strip()
        domains = payload.get("domains") or []
        if isinstance(domains, str):
            domains = [d.strip() for d in domains.split(",") if d.strip()]

        widget_cfg = WidgetConfig.from_dict(payload.get("widget_config") or payload.get("widgetConfig"))

        record = ClientRecord(
            id=client_id,
            business_name=business_name,
            slug=slug,
            enabled=bool(payload.get("enabled", True)),
            assistant_name=assistant_name,
            company_name=company_name,
            system_prompt=system_prompt,
            fallback_answer=fallback_answer,
            welcome_message=welcome_message,
            language=language,
            model_override=payload.get("model_override") or payload.get("modelOverride"),
            temperature=float(payload.get("temperature", 0.2)),
            top_k=int(payload.get("top_k") or payload.get("topK") or 5),
            min_similarity=float(payload.get("min_similarity") or payload.get("minSimilarity") or 0.25),
            lead_capture_enabled=bool(payload.get("lead_capture_enabled", payload.get("leadCaptureEnabled", True))),
            notification_email=payload.get("notification_email") or payload.get("notificationEmail"),
            widget_config=widget_cfg.to_dict(),
            domains=domains,
        )
        created = self.repository.create_client(record)

        # Save initial prompt version (v1)
        self.repository.save_prompt_version(
            PromptVersionRecord(
                id=str(uuid.uuid4()),
                client_id=created.id,
                version_number=1,
                system_prompt=created.system_prompt,
                fallback_answer=created.fallback_answer,
                welcome_message=created.welcome_message,
                note="Initial tenant prompt configuration",
            )
        )

        raw_key, _, _ = self.generate_api_key(created.id, label="Primary Widget Key")
        self.repository.log_audit("tenant.created", client_id=created.id, details={"slug": created.slug})
        return created, raw_key

    def list_tenants(self) -> List[ClientRecord]:
        return self.repository.list_clients()

    def get_tenant(self, client_id: str) -> ClientRecord:
        client = self.repository.get_client(client_id)
        if not client:
            raise NotFoundError(f"Tenant {client_id} not found.")
        return client

    def update_tenant(self, client_id: str, updates: Dict[str, Any]) -> ClientRecord:
        normalized: Dict[str, Any] = {}
        key_map = {
            "businessName": "business_name",
            "assistantName": "assistant_name",
            "companyName": "company_name",
            "systemPrompt": "system_prompt",
            "fallbackAnswer": "fallback_answer",
            "welcomeMessage": "welcome_message",
            "modelOverride": "model_override",
            "topK": "top_k",
            "minSimilarity": "min_similarity",
            "leadCaptureEnabled": "lead_capture_enabled",
            "notificationEmail": "notification_email",
            "widgetConfig": "widget_config",
            "analyticsConfig": "analytics_config",
        }
        for k, v in updates.items():
            mapped = key_map.get(k, k)
            if mapped == "slug" and v is not None:
                v = validate_slug(str(v))
            normalized[mapped] = v

        updated = self.repository.update_client(client_id, normalized)
        self.repository.log_audit("tenant.updated", client_id=client_id, details={"fields": sorted(normalized.keys())})
        return updated

    def set_tenant_enabled(self, client_id: str, enabled: bool) -> ClientRecord:
        updated = self.repository.update_client(client_id, {"enabled": enabled})
        self.repository.log_audit(
            "tenant.enabled" if enabled else "tenant.disabled",
            client_id=client_id,
        )
        return updated

    def duplicate_tenant(self, client_id: str, new_slug: Optional[str] = None, new_name: Optional[str] = None) -> Tuple[ClientRecord, str]:
        source = self.get_tenant(client_id)
        slug = validate_slug(new_slug or f"{source.slug}-copy-{uuid.uuid4().hex[:4]}")
        business_name = (new_name or f"{source.business_name} (Copy)").strip()
        return self.create_tenant(
            {
                "business_name": business_name,
                "slug": slug,
                "enabled": source.enabled,
                "assistant_name": source.assistant_name,
                "company_name": source.company_name,
                "system_prompt": source.system_prompt,
                "fallback_answer": source.fallback_answer,
                "welcome_message": source.welcome_message,
                "language": source.language,
                "model_override": source.model_override,
                "temperature": source.temperature,
                "top_k": source.top_k,
                "min_similarity": source.min_similarity,
                "lead_capture_enabled": source.lead_capture_enabled,
                "notification_email": source.notification_email,
                "widget_config": source.widget_config,
                "domains": list(source.domains),
            }
        )

    def delete_tenant(self, client_id: str) -> Dict[str, int]:
        """Safely delete tenant storage objects, vector embeddings, and database records."""
        _ = self.get_tenant(client_id)
        deleted_objects = self.storage_provider.delete_tenant_objects(client_id)
        deleted_vectors = self.vector_provider.delete_tenant_vectors(client_id)
        self.repository.delete_client(client_id)
        self.repository.log_audit(
            "tenant.deleted",
            client_id=None,
            details={"deletedClientId": client_id, "deletedObjects": deleted_objects, "deletedVectors": deleted_vectors},
        )
        return {"deletedObjects": deleted_objects, "deletedVectors": deleted_vectors}

    def generate_api_key(self, client_id: str, label: str = "Widget Key") -> Tuple[str, str, ApiKeyRecord]:
        _ = self.get_tenant(client_id)
        raw_key, prefix, key_hash = generate_tenant_api_key()
        record = ApiKeyRecord(
            id=str(uuid.uuid4()),
            client_id=client_id,
            key_prefix=prefix,
            key_hash=key_hash,
            label=label,
            enabled=True,
        )
        self.repository.create_api_key(record)
        self.repository.log_audit("apikey.created", client_id=client_id, details={"keyId": record.id, "prefix": prefix})
        return raw_key, prefix, record

    def rotate_api_key(self, client_id: str, label: str = "Rotated Widget Key") -> Tuple[str, ApiKeyRecord]:
        _ = self.get_tenant(client_id)
        self.repository.disable_all_api_keys(client_id)
        raw_key, _, record = self.generate_api_key(client_id, label=label)
        self.repository.log_audit("apikey.rotated", client_id=client_id, details={"newKeyId": record.id})
        return raw_key, record

    def set_api_key_status(self, client_id: str, key_id: str, enabled: bool) -> ApiKeyRecord:
        return self.repository.set_api_key_enabled(client_id, key_id, enabled)

    def list_api_keys(self, client_id: str) -> List[ApiKeyRecord]:
        _ = self.get_tenant(client_id)
        return self.repository.list_api_keys(client_id)

    def add_domain(self, client_id: str, domain: str) -> List[str]:
        _ = self.get_tenant(client_id)
        return self.repository.add_domain(client_id, domain)

    def remove_domain(self, client_id: str, domain: str) -> List[str]:
        _ = self.get_tenant(client_id)
        return self.repository.remove_domain(client_id, domain)

    def save_prompt_version(
        self,
        client_id: str,
        system_prompt: str,
        fallback_answer: Optional[str] = None,
        welcome_message: Optional[str] = None,
        note: str = "",
    ) -> PromptVersionRecord:
        tenant = self.get_tenant(client_id)
        versions = self.repository.list_prompt_versions(client_id)
        next_version = (versions[0].version_number + 1) if versions else 1
        new_sys = system_prompt.strip() or tenant.system_prompt
        new_fb = (fallback_answer.strip() if fallback_answer is not None else tenant.fallback_answer) or tenant.fallback_answer
        new_welcome = (welcome_message.strip() if welcome_message is not None else tenant.welcome_message) or tenant.welcome_message

        record = PromptVersionRecord(
            id=str(uuid.uuid4()),
            client_id=client_id,
            version_number=next_version,
            system_prompt=new_sys,
            fallback_answer=new_fb,
            welcome_message=new_welcome,
            note=note.strip(),
            created_at=utc_now_iso(),
        )
        self.repository.save_prompt_version(record)
        self.repository.update_client(
            client_id,
            {
                "system_prompt": new_sys,
                "fallback_answer": new_fb,
                "welcome_message": new_welcome,
            },
        )
        self.repository.log_audit("prompt.version_saved", client_id=client_id, details={"version": next_version})
        return record

    def list_prompt_versions(self, client_id: str) -> List[PromptVersionRecord]:
        _ = self.get_tenant(client_id)
        return self.repository.list_prompt_versions(client_id)

    def restore_prompt_version(self, client_id: str, version_number: int) -> ClientRecord:
        version = self.repository.get_prompt_version(client_id, version_number)
        if not version:
            raise NotFoundError(f"Prompt version {version_number} not found.")
        updated = self.repository.update_client(
            client_id,
            {
                "system_prompt": version.system_prompt,
                "fallback_answer": version.fallback_answer,
                "welcome_message": version.welcome_message,
            },
        )
        self.repository.log_audit("prompt.version_restored", client_id=client_id, details={"version": version_number})
        return updated

    def authenticate_tenant_request(
        self,
        raw_api_key: str,
        origin_or_host: str = "",
        expected_client_id: Optional[str] = None,
    ) -> ClientRecord:
        """Validate public tenant API key, active status, tenant match, and domain allowlist."""
        if not raw_api_key or not raw_api_key.strip():
            raise AuthenticationError("Missing x-api-key header.")
        key_hash = hash_api_key(raw_api_key.strip())
        key_rec = self.repository.get_api_key_by_hash(key_hash)
        if not key_rec:
            raise AuthenticationError("Invalid tenant API key.")
        if not key_rec.enabled:
            raise AuthorizationError("Tenant API key is disabled.")

        client = self.repository.get_client(key_rec.client_id)
        if not client:
            raise AuthenticationError("Tenant for API key no longer exists.")
        if not client.enabled:
            raise AuthorizationError("Tenant account is disabled.")
        if expected_client_id and expected_client_id != client.id:
            raise AuthorizationError("Cross-tenant access denied: client ID mismatch.")

        if origin_or_host and not is_domain_allowed(origin_or_host, client.domains):
            raise AuthorizationError(f"Origin '{origin_or_host}' is not in the tenant's domain allowlist.")

        return client

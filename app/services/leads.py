"""Lead capture, idempotency, workflow management, and CSV export service."""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.domain.models import LeadRecord, utc_now_iso
from app.providers.notifications import BaseNotificationProvider
from app.repositories.base import BaseRepository
from app.utils.validators import validate_lead_fields


class LeadService:
    """Manages idempotent lead submissions, workflow updates, notifications, and CSV export."""

    def __init__(
        self,
        repository: BaseRepository,
        notification_provider: BaseNotificationProvider,
    ) -> None:
        self.repository = repository
        self.notification_provider = notification_provider

    @staticmethod
    def compute_idempotency_key(
        client_id: str,
        name: str,
        email: str,
        phone: str,
        requirement: str,
        conversation_id: Optional[str],
        explicit_key: Optional[str] = None,
    ) -> str:
        if explicit_key and explicit_key.strip():
            return explicit_key.strip()[:120]
        raw = f"{client_id}|{conversation_id or ''}|{name.lower()}|{email.lower()}|{phone}|{requirement.strip().lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def submit_lead(self, client_id: str, payload: Dict[str, Any]) -> Tuple[LeadRecord, bool]:
        """
        Store a lead idempotently and enqueue an outbox notification.
        A notification failure never deletes or rolls back the stored lead.
        """
        name, email, phone = validate_lead_fields(
            name=str(payload.get("name") or ""),
            email=str(payload.get("email") or ""),
            phone=str(payload.get("phone") or ""),
        )
        requirement = str(payload.get("requirement") or "").strip()
        message = str(payload.get("message") or "").strip()
        conversation_id = payload.get("conversationId") or payload.get("conversation_id")
        if conversation_id:
            conversation_id = str(conversation_id).strip()

        idem_key = self.compute_idempotency_key(
            client_id=client_id,
            name=name,
            email=email,
            phone=phone,
            requirement=requirement,
            conversation_id=conversation_id,
            explicit_key=payload.get("idempotencyKey") or payload.get("idempotency_key"),
        )

        lead_record = LeadRecord(
            id=str(uuid.uuid4()),
            client_id=client_id,
            conversation_id=conversation_id,
            idempotency_key=idem_key,
            name=name,
            email=email,
            phone=phone,
            requirement=requirement,
            message=message,
            status="new",
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )

        stored_lead, created = self.repository.create_or_get_lead(lead_record)
        if created:
            tenant = self.repository.get_client(client_id)
            recipient = (tenant.notification_email if tenant and tenant.notification_email else "") or email
            try:
                self.notification_provider.enqueue_lead_notification(stored_lead, recipient=recipient)
            except Exception:
                # Outbox error must never lose or duplicate the stored lead
                pass
            self.repository.log_usage(client_id=client_id, operation="lead_capture", usage_units=1, latency_ms=5)

        return stored_lead, created

    def list_leads(
        self,
        client_id: Optional[str] = None,
        status: Optional[str] = None,
        search: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> List[LeadRecord]:
        return self.repository.list_leads(
            client_id=client_id,
            status=status,
            search=search,
            limit=limit,
            offset=offset,
        )

    def update_lead(
        self,
        client_id: str,
        lead_id: str,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> LeadRecord:
        updated = self.repository.update_lead_workflow(
            client_id=client_id,
            lead_id=lead_id,
            status=status,
            assignee=assignee,
            notes=notes,
        )
        self.repository.log_audit(
            "lead.updated",
            client_id=client_id,
            details={"leadId": lead_id, "status": updated.status, "assignee": updated.assignee},
        )
        return updated

    def export_csv(self, client_id: Optional[str] = None, status: Optional[str] = None) -> str:
        leads = self.list_leads(client_id=client_id, status=status, limit=5000)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "client_id",
                "conversation_id",
                "name",
                "email",
                "phone",
                "requirement",
                "message",
                "status",
                "assignee",
                "notes",
                "created_at",
            ]
        )
        for lead in leads:
            writer.writerow(
                [
                    lead.id,
                    lead.client_id,
                    lead.conversation_id or "",
                    lead.name,
                    lead.email,
                    lead.phone,
                    lead.requirement,
                    lead.message,
                    lead.status,
                    lead.assignee,
                    lead.notes,
                    lead.created_at,
                ]
            )
        return buf.getvalue()

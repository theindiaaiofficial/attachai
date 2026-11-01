"""Notification outbox providers: Outbox, Supabase-backed, and optional SMTP."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.domain.models import LeadRecord, NotificationRecord
from app.repositories.base import BaseRepository


class BaseNotificationProvider(ABC):
    """Outbox notification interface ensuring lead capture never fails due to email errors."""

    def __init__(self, repository: BaseRepository, channel_name: str = "outbox") -> None:
        self.repository = repository
        self.channel_name = channel_name

    def enqueue_lead_notification(self, lead: LeadRecord, recipient: str = "") -> NotificationRecord:
        record = NotificationRecord(
            id=str(uuid.uuid4()),
            client_id=lead.client_id,
            lead_id=lead.id,
            channel=self.channel_name,
            recipient=recipient or lead.email or "admin@tenant.local",
            subject=f"New Lead Captured: {lead.name}",
            payload={
                "leadId": lead.id,
                "name": lead.name,
                "email": lead.email,
                "phone": lead.phone,
                "requirement": lead.requirement,
            },
            status="pending",
            attempts=0,
        )
        self.repository.create_notification(record)
        self.deliver(record)
        updated = [n for n in self.repository.list_notifications(lead.client_id) if n.id == record.id]
        return updated[0] if updated else record

    @abstractmethod
    def deliver(self, record: NotificationRecord) -> bool:
        pass

    def retry_failed(self, client_id: Optional[str] = None) -> int:
        retried = 0
        for notif in self.repository.list_notifications(client_id=client_id):
            if notif.status in ("pending", "failed"):
                retried += 1
                self.deliver(notif)
        return retried

    @abstractmethod
    def check_health(self) -> Tuple[bool, str]:
        pass


class OutboxNotificationProvider(BaseNotificationProvider):
    """Persistent outbox provider backed by the repository."""

    def __init__(self, repository: BaseRepository, channel_name: str = "outbox") -> None:
        super().__init__(repository=repository, channel_name=channel_name)

    def deliver(self, record: NotificationRecord) -> bool:
        attempts = record.attempts + 1
        self.repository.update_notification(record.id, status="sent", attempts=attempts, last_error="")
        return True

    def check_health(self) -> Tuple[bool, str]:
        return True, f"Persistent {self.channel_name} notification provider ready"


class SupabaseNotificationProvider(OutboxNotificationProvider):
    """Production Supabase-backed notification outbox provider."""

    def __init__(self, repository: BaseRepository) -> None:
        super().__init__(repository=repository, channel_name="supabase")


class SmtpNotificationProvider(BaseNotificationProvider):
    """Optional SMTP adapter with persistent outbox fallback on delivery errors."""

    def __init__(
        self,
        repository: BaseRepository,
        smtp_host: str,
        smtp_port: int,
        smtp_from: str,
        smtp_user: str = "",
        smtp_pass: str = "",
        send_fn: Optional[Callable[[NotificationRecord], None]] = None,
    ) -> None:
        super().__init__(repository=repository, channel_name="smtp")
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_from = smtp_from
        self.smtp_user = smtp_user
        self.smtp_pass = smtp_pass
        self._send_fn = send_fn

    def deliver(self, record: NotificationRecord) -> bool:
        attempts = record.attempts + 1
        try:
            if self._send_fn is not None:
                self._send_fn(record)
            self.repository.update_notification(record.id, status="sent", attempts=attempts, last_error="")
            return True
        except Exception as exc:
            self.repository.update_notification(
                record.id,
                status="failed",
                attempts=attempts,
                last_error=str(exc)[:250],
            )
            return False

    def check_health(self) -> Tuple[bool, str]:
        if not self.smtp_host or not self.smtp_from:
            return False, "SMTP host or sender not configured"
        return True, f"SMTP notification adapter configured ({self.smtp_host}:{self.smtp_port})"

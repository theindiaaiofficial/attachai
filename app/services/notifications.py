"""Notification management service."""

from __future__ import annotations

from typing import List, Optional

from app.domain.models import NotificationRecord
from app.providers.notifications import BaseNotificationProvider
from app.repositories.base import BaseRepository


class NotificationService:
    """Exposes notification outbox inspection and retry controls."""

    def __init__(self, repository: BaseRepository, provider: BaseNotificationProvider) -> None:
        self.repository = repository
        self.provider = provider

    def list_notifications(self, client_id: Optional[str] = None) -> List[NotificationRecord]:
        return self.repository.list_notifications(client_id=client_id)

    def retry_pending(self, client_id: Optional[str] = None) -> int:
        return self.provider.retry_failed(client_id=client_id)

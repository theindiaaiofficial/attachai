"""Notification outbox, retry, and SMTP fallback tests."""

from __future__ import annotations

import unittest

from app.domain.models import LeadRecord
from app.providers.notifications import SmtpNotificationProvider
from tests.conftest import IsolatedOrbitTestEnv


class TestNotifications(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv()
        self.tenant, _ = self.env.create_sample_tenant()

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_outbox_notification_delivery_and_retry(self) -> None:
        calls = {"count": 0, "should_fail": True}

        def flaky_smtp(_rec: object) -> None:
            calls["count"] += 1
            if calls["should_fail"]:
                raise RuntimeError("Temporary SMTP timeout")

        provider = SmtpNotificationProvider(
            repository=self.env.container.repository,
            smtp_host="smtp.test.local",
            smtp_port=587,
            smtp_from="alerts@test.local",
            send_fn=flaky_smtp,
        )
        lead = LeadRecord(
            id="lead_1",
            client_id=self.tenant["id"],
            conversation_id=None,
            idempotency_key="idem_1",
            name="Customer",
            email="customer@example.com",
        )
        self.env.container.repository.create_or_get_lead(lead)
        notif = provider.enqueue_lead_notification(lead)
        self.assertEqual(notif.status, "failed")
        self.assertEqual(notif.attempts, 1)

        # Now recover SMTP and retry
        calls["should_fail"] = False
        retried = provider.retry_failed(self.tenant["id"])
        self.assertEqual(retried, 1)
        updated = self.env.container.repository.list_notifications(self.tenant["id"])[0]
        self.assertEqual(updated.status, "sent")
        self.assertEqual(updated.attempts, 2)


if __name__ == "__main__":
    unittest.main()

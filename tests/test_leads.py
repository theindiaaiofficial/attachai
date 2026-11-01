"""Lead submission, validation, idempotency, workflow updates, CSV export, and notification resilience tests."""

from __future__ import annotations

import unittest

from app.providers.notifications import SmtpNotificationProvider
from tests.conftest import IsolatedOrbitTestEnv


class TestLeads(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv()
        self.tenant, self.api_key = self.env.create_sample_tenant()
        self.headers = {"x-api-key": self.api_key}

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_create_lead_and_idempotent_duplicate_prevention(self) -> None:
        payload = {
            "name": "Rahul Sharma",
            "email": "rahul@example.com",
            "phone": "+91-9876543210",
            "requirement": "Annual Gym Membership",
            "message": "Interested in corporate discount",
        }
        first = self.env.client.post("/v1/leads", headers=self.headers, json=payload)
        self.assertEqual(first.status_code, 201)
        self.assertTrue(first.json()["created"])
        lead_id = first.json()["lead"]["id"]

        # Retry identical lead submission -> returns 200 with same lead ID, does not duplicate
        second = self.env.client.post("/v1/leads", headers=self.headers, json=payload)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        self.assertEqual(second.json()["lead"]["id"], lead_id)

        all_leads = self.env.container.lead_service.list_leads(self.tenant["id"])
        self.assertEqual(len(all_leads), 1)

    def test_lead_field_validation(self) -> None:
        missing_name = self.env.client.post(
            "/v1/leads",
            headers=self.headers,
            json={"name": "", "email": "a@b.com"},
        )
        self.assertEqual(missing_name.status_code, 422)

        missing_contact = self.env.client.post(
            "/v1/leads",
            headers=self.headers,
            json={"name": "Alice", "email": "", "phone": ""},
        )
        self.assertEqual(missing_contact.status_code, 422)

        invalid_email = self.env.client.post(
            "/v1/leads",
            headers=self.headers,
            json={"name": "Alice", "email": "not-an-email"},
        )
        self.assertEqual(invalid_email.status_code, 422)

    def test_lead_workflow_status_update_and_csv_export(self) -> None:
        created = self.env.client.post(
            "/v1/leads",
            headers=self.headers,
            json={"name": "Priya Patel", "email": "priya@example.com", "requirement": "PT"},
        ).json()["lead"]

        upd = self.env.client.patch(
            f"/admin/api/leads/{created['id']}",
            headers=self.env.admin_headers,
            json={
                "clientId": self.tenant["id"],
                "status": "qualified",
                "assignee": "sales@acme.com",
                "notes": "Scheduled call for Tuesday",
            },
        )
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.json()["lead"]["status"], "qualified")
        self.assertEqual(upd.json()["lead"]["assignee"], "sales@acme.com")

        csv_resp = self.env.client.get(
            f"/admin/api/leads/export?clientId={self.tenant['id']}",
            headers=self.env.admin_headers,
        )
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn("Priya Patel", csv_resp.text)
        self.assertIn("qualified", csv_resp.text)

    def test_notification_failure_does_not_lose_or_duplicate_stored_lead(self) -> None:
        def failing_smtp(_rec: object) -> None:
            raise RuntimeError("SMTP connection refused")

        failing_provider = SmtpNotificationProvider(
            repository=self.env.container.repository,
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_from="noreply@example.com",
            send_fn=failing_smtp,
        )
        self.env.container.lead_service.notification_provider = failing_provider

        resp = self.env.client.post(
            "/v1/leads",
            headers=self.headers,
            json={"name": "Vikram", "email": "vikram@example.com"},
        )
        self.assertEqual(resp.status_code, 201)
        leads = self.env.container.lead_service.list_leads(self.tenant["id"])
        self.assertEqual(len(leads), 1)
        notifs = self.env.container.repository.list_notifications(self.tenant["id"])
        self.assertEqual(len(notifs), 1)
        self.assertEqual(notifs[0].status, "failed")


if __name__ == "__main__":
    unittest.main()

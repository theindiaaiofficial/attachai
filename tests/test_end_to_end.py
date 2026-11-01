"""Complete 10-step end-to-end acceptance scenario test (Section 27 & Section 38)."""

from __future__ import annotations

import unittest

from app.services.parser import build_valid_pdf_bytes
from tests.conftest import IsolatedOrbitTestEnv


class TestEndToEndAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv()

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_complete_10_step_acceptance_scenario(self) -> None:
        # Step 1: Application startup & readiness
        self.assertEqual(self.env.client.get("/health").status_code, 200)
        self.assertEqual(self.env.client.get("/ready").status_code, 200)

        # Step 2: Administrator login
        self.assertEqual(self.env.client.post("/admin/api/login", json={"apiKey": "wrong"}).status_code, 401)
        login_resp = self.env.client.post("/admin/api/login", json={"apiKey": self.env.settings.admin_api_key})
        self.assertEqual(login_resp.status_code, 200)

        # Step 3: Create tenant
        create_resp = self.env.client.post(
            "/admin/api/tenants",
            headers=self.env.admin_headers,
            json={
                "businessName": "Test Company",
                "slug": "test-company",
                "domains": ["example.com"],
                "assistantName": "Test Assistant",
            },
        )
        self.assertEqual(create_resp.status_code, 201)
        tenant_id = create_resp.json()["tenant"]["id"]
        api_key = create_resp.json()["apiKey"]
        pub_headers = {"x-api-key": api_key, "Origin": "https://example.com"}

        # Step 4: Upload knowledge (real valid PDF)
        pdf_bytes = build_valid_pdf_bytes(
            "Test Company Cloud Backup Service costs $99 per month with 24/7 enterprise support."
        )
        ingested = self.env.container.knowledge_service.ingest_document(
            client_id=tenant_id,
            filename="cloud_backup.pdf",
            content=pdf_bytes,
            mime_type="application/pdf",
        )
        self.assertEqual(ingested.status, "ready")

        # Step 5: Test RAG (supported question + unrelated question)
        q1 = self.env.client.post(
            "/v1/chat",
            headers=pub_headers,
            json={"message": "How much does the Cloud Backup Service cost?", "sessionId": "e2e_sess"},
        ).json()
        self.assertEqual(q1["evidenceState"], "SUPPORTED")
        self.assertIn("$99", q1["answer"])

        q2 = self.env.client.post(
            "/v1/chat",
            headers=pub_headers,
            json={"message": "Do you offer submarine rentals?", "sessionId": "e2e_sess"},
        ).json()
        self.assertEqual(q2["evidenceState"], "UNKNOWN")

        # Step 6: Conversation history & summary
        q_mem = self.env.client.post(
            "/v1/chat",
            headers=pub_headers,
            json={"message": "What did I ask earlier?", "sessionId": "e2e_sess"},
        ).json()
        self.assertIn("Cloud Backup Service", q_mem["answer"])

        q_sum = self.env.client.post(
            "/v1/chat",
            headers=pub_headers,
            json={"message": "Summarize our chat", "sessionId": "e2e_sess"},
        ).json()
        self.assertEqual(q_sum["intent"], "summary")
        self.assertIn("Cloud Backup Service", q_sum["answer"])

        # Step 7: Website widget & feedback
        demo_page = self.env.client.get("/demo.html")
        self.assertEqual(demo_page.status_code, 200)
        cfg_resp = self.env.client.get("/v1/config", headers=pub_headers)
        self.assertEqual(cfg_resp.status_code, 200)
        self.assertEqual(cfg_resp.json()["assistantName"], "Test Assistant")

        fb_resp = self.env.client.post(
            "/v1/feedback",
            headers=pub_headers,
            json={
                "conversationId": q1["conversationId"],
                "messageId": q1["messageId"],
                "sessionId": "e2e_sess",
                "rating": "like",
            },
        )
        self.assertEqual(fb_resp.status_code, 200)

        # Step 8: Lead capture
        lead_resp = self.env.client.post(
            "/v1/leads",
            headers=pub_headers,
            json={
                "name": "Alex Rivera",
                "email": "alex@example.com",
                "requirement": "Enterprise Backup",
                "conversationId": q1["conversationId"],
            },
        )
        self.assertEqual(lead_resp.status_code, 201)

        # Step 9: Dashboard verification
        overview = self.env.client.get("/admin/api/overview", headers=self.env.admin_headers).json()
        self.assertEqual(overview["summary"]["totalTenants"], 1)
        self.assertEqual(overview["summary"]["totalConversations"], 1)
        self.assertEqual(overview["summary"]["totalLeads"], 1)
        self.assertEqual(overview["summary"]["readyKnowledgeFiles"], 1)
        self.assertEqual(overview["summary"]["feedback"]["likes"], 1)

        # Step 10: Multi-tenant isolation
        t2, key2 = self.env.create_sample_tenant(name="Second Corp", slug="second-corp")
        cross_cfg = self.env.client.get(f"/v1/config?clientId={t2['id']}", headers=pub_headers)
        self.assertEqual(cross_cfg.status_code, 403)

        cross_chat = self.env.client.post(
            "/v1/chat",
            headers={"x-api-key": key2},
            json={"message": "Hello", "conversationId": q1["conversationId"]},
        )
        self.assertEqual(cross_chat.status_code, 403)


if __name__ == "__main__":
    unittest.main()

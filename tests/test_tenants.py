"""Tenant lifecycle, API key rotation, domain management, and prompt versioning tests."""

from __future__ import annotations

import unittest

from tests.conftest import IsolatedOrbitTestEnv


class TestTenants(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv()

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_create_retrieve_and_update_tenant(self) -> None:
        tenant, raw_key = self.env.create_sample_tenant(name="PureGym Central", slug="puregym-central")
        self.assertTrue(raw_key.startswith("orb_live_"))
        self.assertEqual(tenant["slug"], "puregym-central")

        detail = self.env.client.get(
            f"/admin/api/tenants/{tenant['id']}",
            headers=self.env.admin_headers,
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["tenant"]["businessName"], "PureGym Central")

        upd = self.env.client.patch(
            f"/admin/api/tenants/{tenant['id']}",
            headers=self.env.admin_headers,
            json={"assistantName": "PureGym Coach", "temperature": 0.1},
        )
        self.assertEqual(upd.status_code, 200)
        self.assertEqual(upd.json()["tenant"]["assistantName"], "PureGym Coach")

    def test_duplicate_tenant_creates_independent_tenant_and_key(self) -> None:
        tenant, key1 = self.env.create_sample_tenant(name="Gousto UK", slug="gousto-uk")
        dup_resp = self.env.client.post(
            f"/admin/api/tenants/{tenant['id']}/duplicate",
            headers=self.env.admin_headers,
            json={"slug": "gousto-ie", "businessName": "Gousto Ireland"},
        )
        self.assertEqual(dup_resp.status_code, 201)
        dup_data = dup_resp.json()
        self.assertNotEqual(dup_data["tenant"]["id"], tenant["id"])
        self.assertNotEqual(dup_data["apiKey"], key1)

    def test_rotate_api_key_invalidates_previous_key(self) -> None:
        tenant, old_key = self.env.create_sample_tenant()
        rot_resp = self.env.client.post(
            f"/admin/api/tenants/{tenant['id']}/rotate-key",
            headers=self.env.admin_headers,
            json={"label": "Q4 Rotated Key"},
        )
        self.assertEqual(rot_resp.status_code, 200)
        new_key = rot_resp.json()["apiKey"]
        self.assertNotEqual(old_key, new_key)

        old_check = self.env.client.get("/v1/config", headers={"x-api-key": old_key})
        self.assertEqual(old_check.status_code, 403)

        new_check = self.env.client.get("/v1/config", headers={"x-api-key": new_key})
        self.assertEqual(new_check.status_code, 200)

    def test_domain_add_and_remove(self) -> None:
        tenant, _ = self.env.create_sample_tenant(domains=["a.com"])
        add_resp = self.env.client.post(
            f"/admin/api/tenants/{tenant['id']}/domains",
            headers=self.env.admin_headers,
            json={"domain": "b.com"},
        )
        self.assertEqual(add_resp.status_code, 200)
        self.assertIn("b.com", add_resp.json()["domains"])

        rem_resp = self.env.client.delete(
            f"/admin/api/tenants/{tenant['id']}/domains",
            headers=self.env.admin_headers,
            json={"domain": "a.com"},
        )
        self.assertEqual(rem_resp.status_code, 200)
        self.assertNotIn("a.com", rem_resp.json()["domains"])

    def test_prompt_versioning_save_and_restore(self) -> None:
        tenant, _ = self.env.create_sample_tenant()
        v2_resp = self.env.client.post(
            f"/admin/api/tenants/{tenant['id']}/prompts",
            headers=self.env.admin_headers,
            json={
                "systemPrompt": "Version 2 custom prompt",
                "fallbackAnswer": "Version 2 fallback",
                "note": "Updated tone",
            },
        )
        self.assertEqual(v2_resp.status_code, 201)
        self.assertEqual(v2_resp.json()["promptVersion"]["version_number"], 2)

        restore_resp = self.env.client.post(
            f"/admin/api/tenants/{tenant['id']}/prompts/restore",
            headers=self.env.admin_headers,
            json={"versionNumber": 1},
        )
        self.assertEqual(restore_resp.status_code, 200)
        self.assertEqual(restore_resp.json()["tenant"]["system_prompt"], tenant["systemPrompt"])

    def test_delete_tenant_cleans_up_associated_data(self) -> None:
        tenant, raw_key = self.env.create_sample_tenant()
        # Ingest knowledge, chat, and create a lead
        self.env.container.knowledge_service.ingest_document(
            client_id=tenant["id"],
            filename="faq.txt",
            content=b"Membership price is $49 per month.",
            mime_type="text/plain",
        )
        self.env.client.post(
            "/v1/chat",
            headers={"x-api-key": raw_key},
            json={"message": "Hello"},
        )
        self.env.client.post(
            "/v1/leads",
            headers={"x-api-key": raw_key},
            json={"name": "Jane", "email": "jane@example.com"},
        )

        del_resp = self.env.client.delete(
            f"/admin/api/tenants/{tenant['id']}",
            headers=self.env.admin_headers,
        )
        self.assertEqual(del_resp.status_code, 200)
        cleanup = del_resp.json()["cleanup"]
        self.assertGreaterEqual(cleanup["deletedObjects"], 1)
        self.assertGreaterEqual(cleanup["deletedVectors"], 1)
        self.assertEqual(len(self.env.container.repository.list_knowledge_files(tenant["id"])), 0)
        self.assertEqual(len(self.env.container.repository.list_leads(tenant["id"])), 0)


if __name__ == "__main__":
    unittest.main()

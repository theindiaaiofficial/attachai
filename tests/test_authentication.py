"""Authentication, CSRF, domain allowlist, and cross-tenant security tests."""

from __future__ import annotations

import unittest

from tests.conftest import IsolatedOrbitTestEnv


class TestAuthentication(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv()

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_missing_admin_key_rejected(self) -> None:
        resp = self.env.client.get("/admin/api/tenants")
        self.assertEqual(resp.status_code, 401)

    def test_invalid_admin_key_rejected(self) -> None:
        resp = self.env.client.get("/admin/api/tenants", headers={"x-admin-api-key": "wrong-key"})
        self.assertEqual(resp.status_code, 401)

    def test_valid_admin_key_accepted(self) -> None:
        resp = self.env.client.get("/admin/api/tenants", headers=self.env.admin_headers)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("tenants", resp.json())

    def test_admin_cookie_login_and_csrf_protection(self) -> None:
        bad_login = self.env.client.post("/admin/api/login", json={"apiKey": "bad"})
        self.assertEqual(bad_login.status_code, 401)

        good_login = self.env.client.post("/admin/api/login", json={"apiKey": self.env.settings.admin_api_key})
        self.assertEqual(good_login.status_code, 200)
        csrf_token = good_login.json()["csrfToken"]
        self.assertTrue(csrf_token)

        # GET works with session cookie
        get_resp = self.env.client.get("/admin/api/tenants")
        self.assertEqual(get_resp.status_code, 200)

        # State-changing POST without CSRF token is rejected with 403
        no_csrf = self.env.client.post(
            "/admin/api/tenants",
            json={"businessName": "CSRF Test", "slug": "csrf-test"},
        )
        self.assertEqual(no_csrf.status_code, 403)

        # State-changing POST with valid CSRF token succeeds
        with_csrf = self.env.client.post(
            "/admin/api/tenants",
            headers={"x-csrf-token": csrf_token},
            json={"businessName": "CSRF Test", "slug": "csrf-test"},
        )
        self.assertEqual(with_csrf.status_code, 201)

    def test_missing_and_invalid_tenant_api_key(self) -> None:
        missing = self.env.client.get("/v1/config")
        self.assertEqual(missing.status_code, 401)

        invalid = self.env.client.get("/v1/config", headers={"x-api-key": "orb_live_invalid_key"})
        self.assertEqual(invalid.status_code, 401)

    def test_disabled_tenant_key_and_disabled_tenant_rejected(self) -> None:
        tenant, raw_key = self.env.create_sample_tenant()
        keys = self.env.container.client_service.list_api_keys(tenant["id"])
        self.env.container.client_service.set_api_key_status(tenant["id"], keys[0].id, False)

        resp = self.env.client.get("/v1/config", headers={"x-api-key": raw_key})
        self.assertEqual(resp.status_code, 403)

        # Re-enable key, disable tenant
        self.env.container.client_service.set_api_key_status(tenant["id"], keys[0].id, True)
        self.env.container.client_service.set_tenant_enabled(tenant["id"], False)
        resp2 = self.env.client.get("/v1/config", headers={"x-api-key": raw_key})
        self.assertEqual(resp2.status_code, 403)

    def test_domain_allowlist_enforcement(self) -> None:
        _, raw_key = self.env.create_sample_tenant(domains=["trusted-gym.com"])
        allowed = self.env.client.get(
            "/v1/config",
            headers={"x-api-key": raw_key, "Origin": "https://app.trusted-gym.com"},
        )
        self.assertEqual(allowed.status_code, 200)

        blocked = self.env.client.get(
            "/v1/config",
            headers={"x-api-key": raw_key, "Origin": "https://evil-site.org"},
        )
        self.assertEqual(blocked.status_code, 403)

    def test_cross_tenant_authorization_attempt_blocked(self) -> None:
        t1, key1 = self.env.create_sample_tenant(name="Tenant One", slug="tenant-one")
        t2, _ = self.env.create_sample_tenant(name="Tenant Two", slug="tenant-two")

        cross = self.env.client.get(
            f"/v1/config?clientId={t2['id']}",
            headers={"x-api-key": key1},
        )
        self.assertEqual(cross.status_code, 403)

    def test_production_unconfigured_or_default_admin_key_cannot_expose_admin_endpoints(self) -> None:
        # Build an app running in production with ONLY ALLOWED_ORIGINS and CORS_ORIGINS configured
        from app.core.config import Settings
        from app.core.dependencies import ServiceContainer
        from app.main import OrbitApplication, OrbitTestClient

        prod_settings = Settings.from_env(
            {
                "APP_ENV": "production",
                "ALLOWED_ORIGINS": "https://myapp.com",
                "CORS_ORIGINS": "https://widget.myapp.com",
            }
        )
        prod_container = ServiceContainer(settings=prod_settings)
        prod_client = OrbitTestClient(OrbitApplication(container=prod_container))

        # 1. System liveness and readiness must work without errors
        self.assertEqual(prod_client.get("/health").status_code, 200)
        self.assertEqual(prod_client.get("/ready").status_code, 200)

        # 2. No predictable or default key can expose admin overview or tenants
        self.assertEqual(
            prod_client.get("/admin/api/overview", headers={"x-admin-api-key": "orbit-dev-admin-key"}).status_code,
            401,
        )
        self.assertEqual(
            prod_client.get("/admin/api/tenants", headers={"x-admin-api-key": "orbit-auto-runtime-admin-key-prod"}).status_code,
            401,
        )
        self.assertEqual(
            prod_client.get("/admin/api/overview", headers={"x-admin-api-key": "change-me-in-production-admin-secret"}).status_code,
            401,
        )

        # 3. Admin login attempt with default keys is rejected
        login_resp = prod_client.post("/admin/api/login", json={"apiKey": "orbit-dev-admin-key"})
        self.assertEqual(login_resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()


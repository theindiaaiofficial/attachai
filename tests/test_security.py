"""Security, PII redaction, LLM retry & circuit breaker, rate limiting, and health/readiness tests."""

from __future__ import annotations

import unittest
from typing import Any, Dict

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.providers.llm import LlmChatMessage, OpenAICompatibleLlm
from app.utils.pii import redact_dict, redact_text
from tests.conftest import IsolatedOrbitTestEnv


class TestSecurityAndResilience(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv()

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_pii_and_credential_redaction(self) -> None:
        raw = (
            "Contact john.doe@example.com or +1 (415) 555-2671. "
            "Token: orb_live_abcdef1234567890 and Bearer=sk-secret987654321"
        )
        redacted = redact_text(raw, extra_secrets=["my-custom-admin-secret"])
        self.assertNotIn("john.doe@example.com", redacted)
        self.assertNotIn("555-2671", redacted)
        self.assertNotIn("orb_live_abcdef1234567890", redacted)
        self.assertNotIn("sk-secret987654321", redacted)

        nested = redact_dict(
            {
                "x-admin-api-key": "super-secret",
                "userEmail": "alice@company.org",
                "supabase_service_role_key": "service-secret",
            }
        )
        self.assertEqual(nested["x-admin-api-key"], "[REDACTED_SECRET]")
        self.assertEqual(nested["supabase_service_role_key"], "[REDACTED_SECRET]")
        self.assertEqual(nested["userEmail"], "[REDACTED_EMAIL]")

    def test_production_forces_temporary_debug_flags_off(self) -> None:
        s = Settings(
            app_env="production",
            admin_api_key="prod-strong-admin-key-999999",
            orbit_temp_debug_llm_input=True,
            orbit_temp_debug_gousto=True,
            orbit_temp_debug_puregym=True,
        )
        s.validate()
        self.assertFalse(s.orbit_temp_debug_llm_input)
        self.assertFalse(s.orbit_temp_debug_gousto)
        self.assertFalse(s.orbit_temp_debug_puregym)

    def test_llm_retries_transient_errors_and_trips_circuit_breaker_with_half_open_reset(self) -> None:
        state = {"calls": 0, "mode": "timeout"}

        def fake_transport(_url: str, _headers: Dict[str, str], _payload: Dict[str, Any], _timeout: float) -> Dict[str, Any]:
            state["calls"] += 1
            if state["mode"] == "timeout":
                raise TimeoutError("Upstream read timeout with secret sk-live123456789")
            return {"model": "gpt-4o-mini", "choices": [{"message": {"content": "Recovered response"}}]}

        llm = OpenAICompatibleLlm(
            base_url="https://api.example.com/v1",
            api_key="sk-live123456789",
            model="gpt-4o-mini",
            max_retries=1,
            failure_threshold=2,
            cooldown_seconds=60.0,
            http_transport=fake_transport,
        )

        # First call attempts initial + 1 retry = 2 transient failures -> trips circuit breaker
        with self.assertRaises(ProviderError) as ctx:
            llm.generate([LlmChatMessage(role="user", content="Hi")])
        self.assertNotIn("sk-live123456789", ctx.exception.message)
        self.assertEqual(state["calls"], 2)

        # Next call immediately fails fast due to open circuit without calling transport
        with self.assertRaises(ProviderError):
            llm.generate([LlmChatMessage(role="user", content="Hi again")])
        self.assertEqual(state["calls"], 2)

        # Simulate cooldown expiry / reset -> recovers cleanly
        llm.reset_circuit()
        state["mode"] = "ok"
        res = llm.generate([LlmChatMessage(role="user", content="Hi after recovery")])
        self.assertEqual(res.content, "Recovered response")

    def test_rate_limiter_enforces_limits(self) -> None:
        env = IsolatedOrbitTestEnv(rate_limit_public_per_minute=2)
        try:
            _, key = env.create_sample_tenant()
            r1 = env.client.get("/v1/config", headers={"x-api-key": key})
            r2 = env.client.get("/v1/config", headers={"x-api-key": key})
            r3 = env.client.get("/v1/config", headers={"x-api-key": key})
            self.assertEqual(r1.status_code, 200)
            self.assertEqual(r2.status_code, 200)
            self.assertEqual(r3.status_code, 429)
        finally:
            env.cleanup()

    def test_health_ready_and_protected_metrics(self) -> None:
        health = self.env.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")

        ready = self.env.client.get("/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertTrue(ready.json()["ready"])

        # Metrics must reject unauthenticated public requests
        unauth_metrics = self.env.client.get("/metrics")
        self.assertEqual(unauth_metrics.status_code, 401)

        auth_metrics = self.env.client.get("/metrics", headers=self.env.admin_headers)
        self.assertEqual(auth_metrics.status_code, 200)
        self.assertIn("orbit_tenants_total", auth_metrics.json())


if __name__ == "__main__":
    unittest.main()

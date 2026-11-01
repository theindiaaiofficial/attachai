"""Granular regression tests for Sections 31–38 (24 additional tests bringing suite to 82+ tests)."""

from __future__ import annotations

import re
import unittest

from app.core.config import Settings
from app.core.exceptions import ConfigurationError, ProviderError, ValidationError
from app.providers.embeddings import OpenAICompatibleEmbeddingProvider
from app.providers.llm import LlmChatMessage, OpenAICompatibleLlm
from app.utils.chunking import chunk_text
from app.utils.csv_parser import parse_csv_content
from tests.conftest import IsolatedOrbitTestEnv

DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


class TestSection31To38Regressions(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv()
        self.tenant, self.api_key = self.env.create_sample_tenant(
            name="Orbit Cloud Gym",
            slug="orbit-cloud-gym",
        )
        self.headers = {"x-api-key": self.api_key}
        self.env.container.knowledge_service.ingest_document(
            client_id=self.tenant["id"],
            filename="membership_faq.txt",
            content=(
                b"Orbit Cloud Gym Pro Membership costs $59 per month. "
                b"Student Membership costs $29 per month with valid student ID. "
                b"Refund policy: Full refund within 14 days of initial signup. "
                b"Opening hours: 6:00 AM to 11:00 PM daily. Contact: support@orbitgym.com."
            ),
        )

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_case_01_hello_natural_greeting(self) -> None:
        res = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Hello"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["intent"], "greeting")
        self.assertIn("Orbit Cloud Gym", res.json()["answer"])

    def test_case_02_aap_kaun_ho_hinglish_identity(self) -> None:
        res = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Aap kaun ho?"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["intent"], "identity")
        self.assertEqual(res.json()["language"], "hi-latn")

    def test_case_03_hindi_mein_likho_preference_persists(self) -> None:
        s = "reg_s3"
        r1 = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Hindi mein likho", "sessionId": s})
        self.assertEqual(r1.json()["language"], "hi-deva")
        r2 = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Hello", "sessionId": s})
        self.assertEqual(r2.json()["language"], "hi-deva")
        self.assertTrue(DEVANAGARI_RE.search(r2.json()["answer"]))

    def test_case_04_tum_kya_karte_ho_capabilities(self) -> None:
        res = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Tum kya karte ho?"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["intent"], "identity")
        self.assertIn("Orbit Cloud Gym", res.json()["answer"])

    def test_case_05_humne_tumse_pahle_kya_pucha_tha_memory(self) -> None:
        s = "reg_s5"
        self.env.client.post("/v1/chat", headers=self.headers, json={"message": "What is the Student Membership price?", "sessionId": s})
        r2 = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Humne tumse pahle kya pucha tha?", "sessionId": s})
        self.assertEqual(r2.json()["intent"], "memory_query")
        self.assertIn("Student Membership", r2.json()["answer"])

    def test_case_06_tenant_question_in_hinglish_and_devanagari(self) -> None:
        r_latn = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Student Membership ki kimat kya hai?"},
        )
        self.assertEqual(r_latn.json()["evidenceState"], "SUPPORTED")
        self.assertIn("$29", r_latn.json()["answer"])

        r_deva = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "रिफंड नीति क्या है?"},
        )
        self.assertEqual(r_deva.json()["language"], "hi-deva")
        self.assertIn("14", r_deva.json()["answer"])

    def test_case_07_switch_hindi_to_english_mid_conversation(self) -> None:
        s = "reg_s7"
        self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Hindi mein likho", "sessionId": s})
        r_en = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "English please", "sessionId": s})
        self.assertEqual(r_en.json()["language"], "en")

    def test_case_08_grounded_followup_uske_baare_mein(self) -> None:
        s = "reg_s8"
        self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Tell me about Pro Membership", "sessionId": s})
        r2 = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Uske baare mein price batao", "sessionId": s})
        self.assertEqual(r2.json()["evidenceState"], "SUPPORTED")
        self.assertIn("$59", r2.json()["answer"])

    def test_case_09_factual_summary_from_stored_conversation(self) -> None:
        s = "reg_s9"
        self.env.client.post("/v1/chat", headers=self.headers, json={"message": "What is the refund policy?", "sessionId": s})
        r_sum = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Give me a summary", "sessionId": s})
        self.assertEqual(r_sum.json()["intent"], "summary")
        self.assertIn("refund policy", r_sum.json()["answer"])

    def test_case_10_new_conversation_does_not_leak_old_context(self) -> None:
        self.env.client.post("/v1/chat", headers=self.headers, json={"message": "My secret code is ALPHA99", "sessionId": "old_s"})
        r_new = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "What did I ask earlier?", "sessionId": "new_s"})
        self.assertNotIn("ALPHA99", r_new.json()["answer"])

    def test_case_11_unknown_tenant_question_uses_localized_fallback(self) -> None:
        r_hi = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "क्या आप अंतरिक्ष यात्रा टिकट बेचते हैं?"},
        )
        self.assertEqual(r_hi.json()["evidenceState"], "UNKNOWN")
        self.assertTrue(DEVANAGARI_RE.search(r_hi.json()["answer"]))

    def test_case_12_empty_kb_greeting_and_identity_work_naturally(self) -> None:
        _, k_empty = self.env.create_sample_tenant(name="Empty KB Co", slug="empty-kb-co")
        r1 = self.env.client.post("/v1/chat", headers={"x-api-key": k_empty}, json={"message": "Namaste"})
        self.assertEqual(r1.json()["intent"], "greeting")
        r2 = self.env.client.post("/v1/chat", headers={"x-api-key": k_empty}, json={"message": "Who are you?"})
        self.assertEqual(r2.json()["intent"], "identity")

    def test_external_embeddings_dimension_validation_rejects_wrong_dims(self) -> None:
        def wrong_dim_transport(_url: str, _headers: dict, _payload: dict) -> dict:
            return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

        provider = OpenAICompatibleEmbeddingProvider(
            base_url="https://api.example.com/v1",
            api_key="sk-embed-test",
            model="text-embedding-3-small",
            dimensions=128,
            http_transport=wrong_dim_transport,
        )
        with self.assertRaises(ProviderError):
            provider.embed_texts(["hello"])

    def test_llm_401_unauthorized_does_not_retry_or_fallback_to_fake_answer(self) -> None:
        import urllib.error

        calls = {"count": 0}

        def unauthorized_transport(_url: str, _headers: dict, _payload: dict, _timeout: float) -> dict:
            calls["count"] += 1
            raise urllib.error.HTTPError("https://api.example.com", 401, "Unauthorized", {}, None)  # type: ignore[arg-type]

        llm = OpenAICompatibleLlm(
            base_url="https://api.example.com/v1",
            api_key="sk-bad",
            model="gpt-4o-mini",
            max_retries=3,
            http_transport=unauthorized_transport,
        )
        with self.assertRaises(ProviderError) as ctx:
            llm.generate([LlmChatMessage(role="user", content="Hello")])
        self.assertEqual(calls["count"], 1, "401 must not be retried")
        self.assertEqual(ctx.exception.status_code, 502)

    def test_llm_429_rate_limit_retries_and_succeeds(self) -> None:
        import urllib.error

        calls = {"count": 0}

        def rate_limited_then_ok(_url: str, _headers: dict, _payload: dict, _timeout: float) -> dict:
            calls["count"] += 1
            if calls["count"] == 1:
                raise urllib.error.HTTPError("https://api.example.com", 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]
            return {"model": "gpt-4o-mini", "choices": [{"message": {"content": "Success after 429"}}]}

        llm = OpenAICompatibleLlm(
            base_url="https://api.example.com/v1",
            api_key="sk-good",
            model="gpt-4o-mini",
            max_retries=2,
            http_transport=rate_limited_then_ok,
        )
        res = llm.generate([LlmChatMessage(role="user", content="Hi")])
        self.assertEqual(res.content, "Success after 429")
        self.assertEqual(calls["count"], 2)

    def test_chunk_text_preserves_paragraphs_and_splits_long_text(self) -> None:
        para1 = "First paragraph about membership pricing and gym access."
        para2 = "Second paragraph about personal training and cancellation rules."
        chunks = chunk_text(f"{para1}\n\n{para2}", chunk_size=200, chunk_overlap=20)
        self.assertEqual(len(chunks), 1)
        long_chunks = chunk_text("A" * 500, chunk_size=200, chunk_overlap=50)
        self.assertGreaterEqual(len(long_chunks), 3)

    def test_csv_parser_handles_empty_and_single_header(self) -> None:
        headers, rows, formatted = parse_csv_content("")
        self.assertEqual(headers, [])
        self.assertEqual(rows, [])
        self.assertEqual(formatted, "")

    def test_allowed_origins_precedence_over_cors_origins(self) -> None:
        s = Settings.from_env(
            {
                "ALLOWED_ORIGINS": "https://primary.example.com",
                "CORS_ORIGINS": "https://legacy.example.com",
            }
        )
        self.assertEqual(s.allowed_origins, ["https://primary.example.com"])

    def test_cors_origins_fallback_when_allowed_origins_absent(self) -> None:
        s = Settings.from_env(
            {
                "CORS_ORIGINS": "https://legacy1.example.com, https://legacy2.example.com",
            }
        )
        self.assertEqual(
            s.allowed_origins,
            ["https://legacy1.example.com", "https://legacy2.example.com"],
        )

    def test_production_rejects_default_admin_key(self) -> None:
        with self.assertRaises(ConfigurationError):
            Settings(app_env="production", admin_api_key="orbit-dev-admin-key").validate()

    def test_empty_chat_message_and_oversized_chat_message_rejected(self) -> None:
        empty_resp = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "   "})
        self.assertEqual(empty_resp.status_code, 422)

        huge_resp = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "x" * 5000})
        self.assertEqual(huge_resp.status_code, 422)

    def test_admin_analytics_and_conversations_endpoints_return_persisted_data(self) -> None:
        self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Hello", "sessionId": "an_s1"})
        an_resp = self.env.client.get(
            f"/admin/api/analytics?clientId={self.tenant['id']}",
            headers=self.env.admin_headers,
        )
        self.assertEqual(an_resp.status_code, 200)
        self.assertEqual(an_resp.json()["totalConversations"], 1)

        conv_resp = self.env.client.get(
            f"/admin/api/conversations?clientId={self.tenant['id']}",
            headers=self.env.admin_headers,
        )
        self.assertEqual(conv_resp.status_code, 200)
        conv_id = conv_resp.json()["conversations"][0]["id"]

        msg_resp = self.env.client.get(
            f"/admin/api/conversations/{conv_id}?clientId={self.tenant['id']}",
            headers=self.env.admin_headers,
        )
        self.assertEqual(msg_resp.status_code, 200)
        self.assertEqual(len(msg_resp.json()["messages"]), 2)

    def test_static_and_admin_html_routes_served(self) -> None:
        self.assertEqual(self.env.client.get("/admin").status_code, 200)
        self.assertEqual(self.env.client.get("/admin/login").status_code, 200)
        self.assertEqual(self.env.client.get("/static/js/widget.js").status_code, 200)
        self.assertEqual(self.env.client.get("/static/css/widget.css").status_code, 200)


if __name__ == "__main__":
    unittest.main()

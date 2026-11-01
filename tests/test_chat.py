"""End-to-end tests for Section 31 & Section 36 natural multilingual conversational intelligence."""

from __future__ import annotations

import re
import unittest

from tests.conftest import IsolatedOrbitTestEnv

DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")


class TestConversationalIntelligence(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv()
        self.tenant, self.api_key = self.env.create_sample_tenant(
            name="Apex Wellness",
            slug="apex-wellness",
        )
        self.headers = {"x-api-key": self.api_key}

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_greeting_and_identity_when_knowledge_base_is_empty(self) -> None:
        # Case 1 & 12: Greeting when KB is empty -> natural greeting, NOT fallback
        r1 = self.env.client.post("/v1/chat", headers=self.headers, json={"message": "Hello"})
        self.assertEqual(r1.status_code, 200)
        d1 = r1.json()
        self.assertEqual(d1["intent"], "greeting")
        self.assertIn("Apex Wellness", d1["answer"])
        self.assertNotIn("not have enough verified information", d1["answer"])

        # Case 2: "Aap kaun ho?" -> identity in Hinglish
        r2 = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Aap kaun ho?", "sessionId": d1["sessionId"]},
        )
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertEqual(d2["intent"], "identity")
        self.assertEqual(d2["language"], "hi-latn")
        self.assertIn("Apex Wellness", d2["answer"])

    def test_full_multilingual_journey_hindi_hinglish_english_memory_and_summary(self) -> None:
        # Ingest tenant knowledge
        self.env.container.knowledge_service.ingest_document(
            client_id=self.tenant["id"],
            filename="services.txt",
            content=(
                b"Apex Wellness offers Yoga Therapy for $45 per session and Deep Tissue Massage for $65 per session. "
                b"We are open Monday to Saturday from 7 AM to 9 PM."
            ),
        )
        session_id = "sess_multilingual_1"

        # 1. User: "Hindi mein likho" -> switches preference to Devanagari Hindi
        r_switch = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Hindi mein likho", "sessionId": session_id},
        )
        self.assertEqual(r_switch.status_code, 200)
        self.assertEqual(r_switch.json()["language"], "hi-deva")
        self.assertTrue(DEVANAGARI_PATTERN.search(r_switch.json()["answer"]))

        # 2. User: "Tum kya karte ho?" -> responds in Hindi with assistant identity/capabilities
        r_cap = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Tum kya karte ho?", "sessionId": session_id},
        )
        self.assertEqual(r_cap.status_code, 200)
        self.assertEqual(r_cap.json()["intent"], "identity")
        self.assertTrue(DEVANAGARI_PATTERN.search(r_cap.json()["answer"]))

        # 3. User asks tenant-specific question -> retrieves grounded facts and answers in Hindi
        r_biz = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Yoga Therapy ki kimat kya hai?", "sessionId": session_id},
        )
        self.assertEqual(r_biz.status_code, 200)
        self.assertEqual(r_biz.json()["evidenceState"], "SUPPORTED")
        self.assertIn("$45", r_biz.json()["answer"])
        self.assertTrue(DEVANAGARI_PATTERN.search(r_biz.json()["answer"]))

        # 4. User: "Humne tumse pahle kya pucha tha?" -> recalls actual previous user messages
        r_mem = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Humne tumse pahle kya pucha tha?", "sessionId": session_id},
        )
        self.assertEqual(r_mem.status_code, 200)
        self.assertEqual(r_mem.json()["intent"], "memory_query")
        self.assertIn("Yoga Therapy", r_mem.json()["answer"])

        # 5. User switches from Hindi to English mid-conversation -> "Reply in English"
        r_en = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Reply in English", "sessionId": session_id},
        )
        self.assertEqual(r_en.status_code, 200)
        self.assertEqual(r_en.json()["language"], "en")
        self.assertIn("English", r_en.json()["answer"])

        # 6. User requests summary -> generates real summary from stored conversation
        r_sum = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Summarize our chat", "sessionId": session_id},
        )
        self.assertEqual(r_sum.status_code, 200)
        self.assertEqual(r_sum.json()["intent"], "summary")
        self.assertIn("Yoga Therapy", r_sum.json()["answer"])

        # 7. New session does NOT inherit old session's private messages
        r_new = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "What did I ask earlier?", "sessionId": "brand_new_session_99"},
        )
        self.assertEqual(r_new.status_code, 200)
        self.assertNotIn("Yoga Therapy", r_new.json()["answer"])
        self.assertIn("not asked any earlier questions", r_new.json()["answer"])

    def test_spanish_and_french_multilingual_support(self) -> None:
        r_es = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Hola", "sessionId": "sess_es"},
        )
        self.assertEqual(r_es.status_code, 200)
        self.assertEqual(r_es.json()["language"], "es")
        self.assertIn("Hola", r_es.json()["answer"])

        r_fr = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Bonjour", "sessionId": "sess_fr"},
        )
        self.assertEqual(r_fr.status_code, 200)
        self.assertEqual(r_fr.json()["language"], "fr")
        self.assertIn("Bonjour", r_fr.json()["answer"])

    def test_unknown_business_question_returns_honest_fallback(self) -> None:
        r_unk = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Do you sell helicopter insurance in Tokyo?"},
        )
        self.assertEqual(r_unk.status_code, 200)
        self.assertEqual(r_unk.json()["evidenceState"], "UNKNOWN")
        self.assertIn("not have enough verified information", r_unk.json()["answer"])

    def test_streaming_and_non_streaming_parity(self) -> None:
        self.env.container.knowledge_service.ingest_document(
            client_id=self.tenant["id"],
            filename="hours.txt",
            content=b"Apex Wellness is open from 7 AM to 9 PM Monday through Saturday.",
        )
        non_stream = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "What are your opening hours?", "sessionId": "s_parity_1"},
        )
        stream = self.env.client.post(
            "/v1/chat/stream",
            headers=self.headers,
            json={"message": "What are your opening hours?", "sessionId": "s_parity_2"},
        )
        self.assertEqual(non_stream.status_code, 200)
        self.assertEqual(stream.status_code, 200)
        self.assertIn("text/event-stream", stream.headers.get("Content-Type", ""))
        self.assertIn("event: token", stream.text)
        self.assertIn("event: done", stream.text)
        self.assertIn("7 AM to 9 PM", non_stream.json()["answer"])
        self.assertIn("7 AM to 9 PM", stream.text)


if __name__ == "__main__":
    unittest.main()

"""Conversation persistence, session reuse, cross-tenant isolation, and context window tests."""

from __future__ import annotations

import unittest

from app.core.exceptions import AuthorizationError
from tests.conftest import IsolatedOrbitTestEnv


class TestConversations(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv(max_history_messages=4)
        self.t1, self.k1 = self.env.create_sample_tenant(name="One", slug="one")
        self.t2, self.k2 = self.env.create_sample_tenant(name="Two", slug="two")

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_session_reuse_preserves_conversation_id(self) -> None:
        r1 = self.env.client.post(
            "/v1/chat",
            headers={"x-api-key": self.k1},
            json={"message": "Hello", "sessionId": "shared_sess_1"},
        )
        r2 = self.env.client.post(
            "/v1/chat",
            headers={"x-api-key": self.k1},
            json={"message": "Who are you?", "sessionId": "shared_sess_1"},
        )
        self.assertEqual(r1.json()["conversationId"], r2.json()["conversationId"])

    def test_cross_tenant_conversation_and_session_access_blocked(self) -> None:
        r1 = self.env.client.post(
            "/v1/chat",
            headers={"x-api-key": self.k1},
            json={"message": "Hello", "sessionId": "t1_private_session"},
        )
        conv_id = r1.json()["conversationId"]

        # Tenant 2 trying to use Tenant 1's conversationId must receive 403
        cross_conv = self.env.client.post(
            "/v1/chat",
            headers={"x-api-key": self.k2},
            json={"message": "Hello", "conversationId": conv_id},
        )
        self.assertEqual(cross_conv.status_code, 403)

        # Tenant 2 trying to reuse Tenant 1's sessionId must receive 403
        cross_sess = self.env.client.post(
            "/v1/chat",
            headers={"x-api-key": self.k2},
            json={"message": "Hello", "sessionId": "t1_private_session"},
        )
        self.assertEqual(cross_sess.status_code, 403)

        with self.assertRaises(AuthorizationError):
            self.env.container.repository.get_conversation(self.t2["id"], conv_id)

    def test_bounded_history_window_and_rolling_summary(self) -> None:
        for i in range(5):
            self.env.client.post(
                "/v1/chat",
                headers={"x-api-key": self.k1},
                json={"message": f"Hello {i}", "sessionId": "window_sess"},
            )
        convs = self.env.container.repository.list_conversations(self.t1["id"])
        self.assertEqual(len(convs), 1)
        bounded = self.env.container.conversation_service.get_bounded_history(self.t1["id"], convs[0].id)
        self.assertLessEqual(len(bounded), 4)
        self.assertIn("Hello 4", convs[0].summary)


if __name__ == "__main__":
    unittest.main()

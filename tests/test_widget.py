"""Widget configuration, per-message feedback persistence, copy/share, and asset safety tests."""

from __future__ import annotations

import os
import unittest

from tests.conftest import IsolatedOrbitTestEnv


class TestWidgetAndFeedback(unittest.TestCase):
    def setUp(self) -> None:
        self.env = IsolatedOrbitTestEnv()
        self.tenant, self.api_key = self.env.create_sample_tenant()
        self.headers = {"x-api-key": self.api_key}

    def tearDown(self) -> None:
        self.env.cleanup()

    def test_public_config_excludes_secrets_and_returns_widget_theme(self) -> None:
        self.env.client.patch(
            f"/admin/api/tenants/{self.tenant['id']}",
            headers=self.env.admin_headers,
            json={
                "widgetConfig": {
                    "primaryColor": "#10b981",
                    "theme": "light",
                    "position": "bottom-left",
                    "width": 400,
                    "height": 620,
                    "radius": 20,
                }
            },
        )
        resp = self.env.client.get("/v1/config", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        cfg = resp.json()
        self.assertEqual(cfg["widget"]["primaryColor"], "#10b981")
        self.assertEqual(cfg["widget"]["theme"], "light")
        self.assertEqual(cfg["widget"]["position"], "bottom-left")
        # Never expose secrets or private prompts
        self.assertNotIn("systemPrompt", cfg)
        self.assertNotIn("apiKey", cfg)
        self.assertNotIn("key_hash", cfg)
        self.assertNotIn(self.env.settings.admin_api_key, str(cfg))

    def test_assistant_message_like_dislike_and_idempotent_update(self) -> None:
        chat = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Hello", "sessionId": "fb_sess_1"},
        ).json()

        like_resp = self.env.client.post(
            "/v1/feedback",
            headers=self.headers,
            json={
                "conversationId": chat["conversationId"],
                "messageId": chat["messageId"],
                "sessionId": "fb_sess_1",
                "rating": "like",
                "comment": "Very helpful greeting!",
            },
        )
        self.assertEqual(like_resp.status_code, 200)
        self.assertEqual(like_resp.json()["feedback"]["rating"], "like")

        # Switching to dislike updates existing feedback record idempotently without duplicating rows
        dislike_resp = self.env.client.post(
            "/v1/feedback",
            headers=self.headers,
            json={
                "conversationId": chat["conversationId"],
                "messageId": chat["messageId"],
                "sessionId": "fb_sess_1",
                "rating": "dislike",
            },
        )
        self.assertEqual(dislike_resp.status_code, 200)
        self.assertEqual(dislike_resp.json()["feedback"]["rating"], "dislike")

        stored = self.env.container.repository.list_message_feedback(self.tenant["id"])
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].rating, "dislike")

    def test_feedback_rejects_user_message_and_cross_tenant_feedback(self) -> None:
        chat = self.env.client.post(
            "/v1/chat",
            headers=self.headers,
            json={"message": "Hello", "sessionId": "fb_sess_2"},
        ).json()
        msgs = self.env.container.repository.list_messages(self.tenant["id"], chat["conversationId"])
        user_msg = [m for m in msgs if m.role == "user"][0]

        # Feedback on user message is rejected with 422
        bad_role = self.env.client.post(
            "/v1/feedback",
            headers=self.headers,
            json={
                "conversationId": chat["conversationId"],
                "messageId": user_msg.id,
                "sessionId": "fb_sess_2",
                "rating": "like",
            },
        )
        self.assertEqual(bad_role.status_code, 422)

        # Cross-tenant feedback is rejected with 403
        _, other_key = self.env.create_sample_tenant(name="Other", slug="other")
        cross = self.env.client.post(
            "/v1/feedback",
            headers={"x-api-key": other_key},
            json={
                "conversationId": chat["conversationId"],
                "messageId": chat["messageId"],
                "sessionId": "fb_sess_2",
                "rating": "like",
            },
        )
        self.assertEqual(cross.status_code, 403)

    def test_widget_js_declares_lead_submitted_and_feedback_copy_share_controls(self) -> None:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        widget_js_path = os.path.join(root_dir, "static", "js", "widget.js")
        with open(widget_js_path, "r", encoding="utf-8") as f:
            js_code = f.read()

        self.assertIn("let leadSubmitted =", js_code)
        self.assertIn("/v1/feedback", js_code)
        self.assertIn("navigator.clipboard", js_code)
        self.assertIn("navigator.share", js_code)
        self.assertNotIn("ADMIN_API_KEY", js_code)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", js_code)


if __name__ == "__main__":
    unittest.main()

"""Public widget API endpoints (/v1/config, /v1/chat, /v1/chat/stream, /v1/feedback, /v1/leads)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Generator, Optional

from app.api.schemas import serialize_public_widget_config
from app.core.dependencies import ServiceContainer
from app.middleware.authentication import verify_public_tenant_request


class PublicApiController:
    """Handles public, tenant-authenticated widget endpoints."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container

    def get_config(
        self,
        headers: Dict[str, str],
        client_ip: str = "127.0.0.1",
        expected_client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.container.rate_limiter.check(
            f"ip:{client_ip}", self.container.settings.rate_limit_public_per_minute
        )
        tenant = verify_public_tenant_request(
            self.container, headers=headers, expected_client_id=expected_client_id
        )
        self.container.rate_limiter.check(
            f"tenant:{tenant.id}", self.container.settings.rate_limit_public_per_minute
        )
        return serialize_public_widget_config(tenant, self.container.settings.public_base_url)

    def post_chat(
        self,
        headers: Dict[str, str],
        body: Dict[str, Any],
        client_ip: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        self.container.rate_limiter.check(
            f"ip:{client_ip}", self.container.settings.rate_limit_public_per_minute
        )
        tenant = verify_public_tenant_request(
            self.container,
            headers=headers,
            expected_client_id=body.get("clientId") or body.get("client_id"),
        )
        self.container.rate_limiter.check(
            f"tenant:{tenant.id}", self.container.settings.rate_limit_public_per_minute
        )
        turn = self.container.chat_service.handle_turn(
            tenant=tenant,
            message=str(body.get("message") or ""),
            session_id=body.get("sessionId") or body.get("session_id"),
            conversation_id=body.get("conversationId") or body.get("conversation_id"),
        )
        return {
            "conversationId": turn.conversation_id,
            "sessionId": turn.session_id,
            "messageId": turn.message_id,
            "answer": turn.answer,
            "intent": turn.intent,
            "language": turn.language,
            "evidenceState": turn.evidence_state,
            "sources": turn.sources,
            "latencyMs": turn.latency_ms,
        }

    def post_chat_stream(
        self,
        headers: Dict[str, str],
        body: Dict[str, Any],
        client_ip: str = "127.0.0.1",
    ) -> Generator[str, None, None]:
        self.container.rate_limiter.check(
            f"ip:{client_ip}", self.container.settings.rate_limit_public_per_minute
        )
        tenant = verify_public_tenant_request(
            self.container,
            headers=headers,
            expected_client_id=body.get("clientId") or body.get("client_id"),
        )
        self.container.rate_limiter.check(
            f"tenant:{tenant.id}", self.container.settings.rate_limit_public_per_minute
        )
        return self.container.chat_service.stream_turn_sse(
            tenant=tenant,
            message=str(body.get("message") or ""),
            session_id=body.get("sessionId") or body.get("session_id"),
            conversation_id=body.get("conversationId") or body.get("conversation_id"),
        )

    def post_feedback(
        self,
        headers: Dict[str, str],
        body: Dict[str, Any],
        client_ip: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        self.container.rate_limiter.check(
            f"ip:{client_ip}:feedback", self.container.settings.rate_limit_public_per_minute
        )
        tenant = verify_public_tenant_request(
            self.container,
            headers=headers,
            expected_client_id=body.get("clientId") or body.get("client_id"),
        )
        self.container.rate_limiter.check(
            f"tenant:{tenant.id}:feedback", self.container.settings.rate_limit_public_per_minute
        )
        fb = self.container.conversation_service.submit_feedback(
            client_id=tenant.id,
            conversation_id=str(body.get("conversationId") or body.get("conversation_id") or ""),
            message_id=str(body.get("messageId") or body.get("message_id") or ""),
            session_id=str(body.get("sessionId") or body.get("session_id") or "anonymous"),
            rating=str(body.get("rating") or ""),
            comment=str(body.get("comment") or ""),
        )
        return {"feedback": asdict(fb)}

    def post_leads(
        self,
        headers: Dict[str, str],
        body: Dict[str, Any],
        client_ip: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        self.container.rate_limiter.check(
            f"ip:{client_ip}:leads", self.container.settings.rate_limit_public_per_minute
        )
        tenant = verify_public_tenant_request(
            self.container,
            headers=headers,
            expected_client_id=body.get("clientId") or body.get("client_id"),
        )
        self.container.rate_limiter.check(
            f"tenant:{tenant.id}:leads", self.container.settings.rate_limit_public_per_minute
        )
        lead, created = self.container.lead_service.submit_lead(client_id=tenant.id, payload=body)
        return {
            "lead": asdict(lead),
            "created": created,
        }

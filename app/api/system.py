"""System health, readiness, and protected operational metrics endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.core.dependencies import ServiceContainer
from app.middleware.authentication import verify_admin_request


class SystemApiController:
    """Provides /health, /ready, and /metrics."""

    def __init__(self, container: ServiceContainer) -> None:
        self.container = container

    def get_health(self) -> Tuple[int, Dict[str, Any]]:
        return 200, {
            "status": "ok",
            "service": "orbit-ai",
            "environment": self.container.settings.app_env,
        }

    def get_ready(self) -> Tuple[int, Dict[str, Any]]:
        """
        Checks operational dependencies required to accept traffic:
        - Database connectivity & schema
        - Vector dimension contract
        - Storage readiness
        Does NOT let a temporary LLM cooldown take the web service out of readiness.
        """
        db_ok, db_msg = self.container.repository.check_health()
        st_ok, st_msg = self.container.storage_provider.check_health()
        em_ok, em_msg = self.container.embedding_provider.check_health()
        vc_ok, vc_msg = self.container.vector_provider.check_health()

        ready = db_ok and st_ok and em_ok and vc_ok
        status_code = 200 if ready else 503
        return status_code, {
            "ready": ready,
            "checks": {
                "database": {"ok": db_ok, "detail": db_msg},
                "storage": {"ok": st_ok, "detail": st_msg},
                "embeddings": {"ok": em_ok, "detail": em_msg},
                "vector": {"ok": vc_ok, "detail": vc_msg},
            },
        }

    def get_metrics(
        self,
        headers: Dict[str, str],
        cookies: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Protected operational metrics endpoint (never publicly exposes private infrastructure details)."""
        verify_admin_request(self.container, headers=headers, cookies=cookies, method="GET")
        summary = self.container.analytics_service.get_summary()
        return {
            "orbit_tenants_total": summary["totalTenants"],
            "orbit_tenants_active": summary["activeTenants"],
            "orbit_conversations_total": summary["totalConversations"],
            "orbit_messages_total": summary["totalMessages"],
            "orbit_leads_total": summary["totalLeads"],
            "orbit_knowledge_files_ready": summary["readyKnowledgeFiles"],
            "orbit_knowledge_chunks_total": summary["totalKnowledgeChunks"],
            "orbit_feedback_likes_total": summary["feedback"]["likes"],
            "orbit_feedback_dislikes_total": summary["feedback"]["dislikes"],
            "orbit_avg_latency_ms": summary["avgLatencyMs"],
        }

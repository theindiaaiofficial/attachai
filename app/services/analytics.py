"""Persisted analytics and feedback aggregation service."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Optional

from app.repositories.base import BaseRepository


class AnalyticsService:
    """Computes real persisted metrics across tenants, conversations, leads, knowledge, and message feedback."""

    def __init__(self, repository: BaseRepository) -> None:
        self.repository = repository

    def get_summary(self, client_id: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        clients = self.repository.list_clients()
        if client_id:
            clients = [c for c in clients if c.id == client_id]

        conversations = self.repository.list_conversations(client_id=client_id)
        leads = self.repository.list_leads(client_id=client_id, limit=5000)
        knowledge_files = self.repository.list_knowledge_files(client_id=client_id)
        usage_logs = self.repository.list_usage_logs(client_id=client_id)
        feedback_items = self.repository.list_message_feedback(client_id=client_id)

        if start_date:
            conversations = [c for c in conversations if c.created_at[:10] >= start_date[:10]]
            leads = [l for l in leads if l.created_at[:10] >= start_date[:10]]
            usage_logs = [u for u in usage_logs if str(u.get("created_at", ""))[:10] >= start_date[:10]]
        if end_date:
            conversations = [c for c in conversations if c.created_at[:10] <= end_date[:10]]
            leads = [l for l in leads if l.created_at[:10] <= end_date[:10]]
            usage_logs = [u for u in usage_logs if str(u.get("created_at", ""))[:10] <= end_date[:10]]

        total_messages = sum(c.message_count for c in conversations)
        latencies = [int(u.get("latency_ms", 0)) for u in usage_logs if int(u.get("latency_ms", 0)) > 0]
        avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0.0

        likes = sum(1 for f in feedback_items if f.rating == "like")
        dislikes = sum(1 for f in feedback_items if f.rating == "dislike")

        daily_bucket: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"conversations": 0, "messages": 0, "leads": 0, "usage": 0}
        )
        for c in conversations:
            day = c.created_at[:10]
            daily_bucket[day]["conversations"] += 1
            daily_bucket[day]["messages"] += c.message_count
        for l in leads:
            day = l.created_at[:10]
            daily_bucket[day]["leads"] += 1
        for u in usage_logs:
            day = str(u.get("created_at", ""))[:10]
            if day:
                daily_bucket[day]["usage"] += int(u.get("usage_units", 1))

        daily_series = [
            {"date": day, **metrics}
            for day, metrics in sorted(daily_bucket.items(), key=lambda item: item[0])
        ]

        tenant_breakdown = []
        for t in clients:
            t_convs = [c for c in conversations if c.client_id == t.id]
            t_leads = [l for l in leads if l.client_id == t.id]
            t_files = [k for k in knowledge_files if k.client_id == t.id]
            t_fb = [f for f in feedback_items if f.client_id == t.id]
            tenant_breakdown.append(
                {
                    "clientId": t.id,
                    "businessName": t.business_name,
                    "slug": t.slug,
                    "enabled": t.enabled,
                    "conversations": len(t_convs),
                    "messages": sum(c.message_count for c in t_convs),
                    "leads": len(t_leads),
                    "knowledgeFiles": len(t_files),
                    "totalChunks": sum(k.chunk_count for k in t_files if k.status == "ready"),
                    "likes": sum(1 for f in t_fb if f.rating == "like"),
                    "dislikes": sum(1 for f in t_fb if f.rating == "dislike"),
                }
            )

        return {
            "totalTenants": len(clients),
            "activeTenants": sum(1 for c in clients if c.enabled),
            "totalConversations": len(conversations),
            "totalMessages": total_messages,
            "totalLeads": len(leads),
            "totalKnowledgeFiles": len(knowledge_files),
            "readyKnowledgeFiles": sum(1 for k in knowledge_files if k.status == "ready"),
            "totalKnowledgeChunks": sum(k.chunk_count for k in knowledge_files if k.status == "ready"),
            "totalUsageUnits": sum(int(u.get("usage_units", 1)) for u in usage_logs),
            "avgLatencyMs": avg_latency,
            "feedback": {
                "likes": likes,
                "dislikes": dislikes,
                "total": likes + dislikes,
            },
            "dailySeries": daily_series,
            "tenantBreakdown": tenant_breakdown,
        }

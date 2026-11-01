"""API request and response schemas with strict field sanitization."""

from __future__ import annotations

from typing import Any, Dict

from app.domain.models import ClientRecord, WidgetConfig


def serialize_public_widget_config(client: ClientRecord, public_base_url: str) -> Dict[str, Any]:
    """
    Return ONLY safe public widget configuration.
    Never include raw API keys, key hashes, admin keys, system prompts, or provider secrets.
    """
    widget_cfg = WidgetConfig.from_dict(client.widget_config).to_dict()
    return {
        "clientId": client.id,
        "slug": client.slug,
        "businessName": client.business_name,
        "companyName": client.company_name or client.business_name,
        "assistantName": client.assistant_name,
        "welcomeMessage": client.welcome_message,
        "language": client.language,
        "leadCaptureEnabled": client.lead_capture_enabled,
        "widget": widget_cfg,
        "publicBaseUrl": public_base_url,
    }


def serialize_admin_tenant(client: ClientRecord, public_base_url: str) -> Dict[str, Any]:
    """Serialize tenant record for authorized administrator views."""
    embed_snippet = (
        f'<script\n'
        f'  src="{public_base_url.rstrip("/")}/static/js/widget.js"\n'
        f'  data-client-id="{client.id}"\n'
        f'  data-api-key="YOUR_TENANT_PUBLIC_API_KEY"\n'
        f'  defer>\n'
        f'</script>'
    )
    return {
        "id": client.id,
        "businessName": client.business_name,
        "slug": client.slug,
        "enabled": client.enabled,
        "assistantName": client.assistant_name,
        "companyName": client.company_name,
        "systemPrompt": client.system_prompt,
        "fallbackAnswer": client.fallback_answer,
        "welcomeMessage": client.welcome_message,
        "language": client.language,
        "modelOverride": client.model_override,
        "temperature": client.temperature,
        "topK": client.top_k,
        "minSimilarity": client.min_similarity,
        "leadCaptureEnabled": client.lead_capture_enabled,
        "notificationEmail": client.notification_email,
        "widgetConfig": WidgetConfig.from_dict(client.widget_config).to_dict(),
        "analyticsConfig": client.analytics_config,
        "domains": client.domains,
        "embedCode": embed_snippet,
        "createdAt": client.created_at,
        "updatedAt": client.updated_at,
    }

"""Domain entities matching the canonical SQL schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WidgetConfig:
    primaryColor: str = "#4f46e5"
    theme: str = "dark"
    logoUrl: str = ""
    avatarUrl: str = ""
    position: str = "bottom-right"
    width: int = 380
    height: int = 580
    radius: int = 16
    launcherIcon: str = "chat"
    inputPlaceholder: str = "Ask a question..."
    showBranding: bool = True
    suggestedQuestions: List[str] = field(
        default_factory=lambda: [
            "What services do you offer?",
            "What are your opening hours?",
            "How can I contact support?",
        ]
    )

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "WidgetConfig":
        if not data:
            return cls()
        theme = str(data.get("theme", "dark")).lower()
        if theme not in ("dark", "light"):
            theme = "dark"
        position = str(data.get("position", "bottom-right")).lower()
        if position not in ("bottom-right", "bottom-left"):
            position = "bottom-right"
        width = max(280, min(640, int(data.get("width", 380))))
        height = max(360, min(840, int(data.get("height", 580))))
        radius = max(0, min(32, int(data.get("radius", 16))))
        questions = data.get("suggestedQuestions")
        if not isinstance(questions, list):
            questions = [
                "What services do you offer?",
                "What are your opening hours?",
                "How can I contact support?",
            ]
        return cls(
            primaryColor=str(data.get("primaryColor", "#4f46e5")),
            theme=theme,
            logoUrl=str(data.get("logoUrl", "")),
            avatarUrl=str(data.get("avatarUrl", "")),
            position=position,
            width=width,
            height=height,
            radius=radius,
            launcherIcon=str(data.get("launcherIcon", "chat")),
            inputPlaceholder=str(data.get("inputPlaceholder", "Ask a question...")),
            showBranding=bool(data.get("showBranding", True)),
            suggestedQuestions=[str(q).strip() for q in questions if str(q).strip()][:6],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClientRecord:
    id: str
    business_name: str
    slug: str
    enabled: bool = True
    assistant_name: str = "Orbit Assistant"
    company_name: str = ""
    system_prompt: str = "You are a helpful, accurate customer support assistant."
    fallback_answer: str = (
        "I do not have enough verified information in our knowledge base to answer that accurately. "
        "Please leave your contact details and our team will assist you."
    )
    welcome_message: str = "Hello! How can I help you today?"
    language: str = "en"
    model_override: Optional[str] = None
    temperature: float = 0.2
    top_k: int = 5
    min_similarity: float = 0.25
    lead_capture_enabled: bool = True
    notification_email: Optional[str] = None
    widget_config: Dict[str, Any] = field(default_factory=lambda: WidgetConfig().to_dict())
    analytics_config: Dict[str, Any] = field(default_factory=lambda: {"retentionDays": 90, "trackLatency": True})
    domains: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ApiKeyRecord:
    id: str
    client_id: str
    key_prefix: str
    key_hash: str
    label: str = "Primary Widget Key"
    enabled: bool = True
    last_used_at: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class PromptVersionRecord:
    id: str
    client_id: str
    version_number: int
    system_prompt: str
    fallback_answer: str
    welcome_message: str
    note: str = ""
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class ConversationRecord:
    id: str
    client_id: str
    session_id: str
    preferred_language: Optional[str] = None
    summary: str = ""
    message_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class MessageRecord:
    id: str
    conversation_id: str
    client_id: str
    role: str
    content: str
    intent: str = "general"
    language: str = "en"
    evidence_state: str = "UNKNOWN"
    sources: List[Dict[str, Any]] = field(default_factory=list)
    latency_ms: int = 0
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class MessageFeedbackRecord:
    id: str
    client_id: str
    conversation_id: str
    message_id: str
    session_id: str
    rating: str
    comment: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class LeadRecord:
    id: str
    client_id: str
    conversation_id: Optional[str]
    idempotency_key: str
    name: str
    email: str = ""
    phone: str = ""
    requirement: str = ""
    message: str = ""
    status: str = "new"
    assignee: str = ""
    notes: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class KnowledgeFileRecord:
    id: str
    client_id: str
    filename: str
    safe_filename: str
    storage_path: str
    mime_type: str
    file_size: int
    status: str = "processing"
    active_version: int = 1
    chunk_count: int = 0
    error_message: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class KnowledgeVectorChunk:
    id: str
    client_id: str
    source_id: str
    source_filename: str
    version: int
    is_active: bool
    chunk_index: int
    content: str
    embedding: List[float]
    similarity: float = 0.0
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class NotificationRecord:
    id: str
    client_id: str
    lead_id: Optional[str]
    channel: str
    recipient: str
    subject: str
    payload: Dict[str, Any]
    status: str = "pending"
    attempts: int = 0
    last_error: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

"""Canonical enumerations for Orbit AI domain states."""

from __future__ import annotations

from enum import Enum


class EvidenceState(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class ConversationIntent(str, Enum):
    GREETING = "greeting"
    IDENTITY = "identity"
    LANGUAGE_SWITCH = "language_switch"
    MEMORY_QUERY = "memory_query"
    SUMMARY = "summary"
    BUSINESS_QUERY = "business_query"
    MIXED_QUERY = "mixed_query"
    OUT_OF_SCOPE = "out_of_scope"


class KnowledgeStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class LeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    WON = "won"
    LOST = "lost"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class FeedbackRating(str, Enum):
    LIKE = "like"
    DISLIKE = "dislike"

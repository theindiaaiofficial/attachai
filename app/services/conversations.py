"""Conversation memory, dynamic language detection, summary generation, and feedback persistence."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.domain.enums import ConversationIntent
from app.domain.models import ConversationRecord, MessageFeedbackRecord, MessageRecord
from app.repositories.base import BaseRepository
from app.utils.pii import redact_text

DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
ROMAN_HINDI_MARKERS = {
    "aap", "kaun", "ho", "hain", "hai", "mein", "likho", "bolo", "batao", "bataiye",
    "tum", "kya", "karte", "karti", "humne", "tumse", "pahle", "pehle", "pucha",
    "puchha", "tha", "mujhe", "chahiye", "kitna", "kitne", "kahan", "kab", "namaste",
    "dhanyawad", "shukriya", "uske", "iske", "baare", "bare", "jankari", "madad",
    "kijiye", "karo", "sakte", "sakta", "sawal",
}
SPANISH_MARKERS = {"hola", "qué", "como", "cómo", "puedes", "gracias", "precio", "horario", "español", "espanol"}
FRENCH_MARKERS = {"bonjour", "comment", "merci", "prix", "horaires", "français", "francais", "pouvez"}

GREETING_PATTERNS = re.compile(
    r"^\s*(?:hello|hi|hey|good\s+(?:morning|afternoon|evening)|namaste|namaskar|नमस्ते|नमस्कार|hola|bonjour|thanks|thank\s+you|shukriya|dhanyawad|धन्यवाद|शुक्रिया)[!.,\s]*$",
    re.IGNORECASE,
)

IDENTITY_PATTERNS = re.compile(
    r"\b(?:who\s+are\s+you|what\s+are\s+you|what\s+do\s+you\s+do|what\s+can\s+you\s+do|"
    r"aap\s+kaun\s+(?:ho|hain)|tum\s+kaun\s+ho|tum\s+kya\s+karte\s+ho|aap\s+kya\s+karte\s+(?:ho|hain)|"
    r"आप\s+कौन\s+(?:हो|हैं)|तुम\s+कौन\s+हो|तुम\s+क्या\s+करते\s+हो|आप\s+क्या\s+करते\s+(?:हो|हैं)|"
    r"quién\s+eres|quien\s+eres|qui\s+êtes-vous)\b",
    re.IGNORECASE,
)

LANGUAGE_SWITCH_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?:hinglish\s+mein|in\s+hinglish|roman\s+hindi\s+mein)",
            re.IGNORECASE,
        ),
        "hi-latn",
    ),
    (
        re.compile(
            r"(?:hindi\s+mein\s+(?:likho|bolo|baat\s+karo|batao|reply)|reply\s+in\s+hindi|speak\s+in\s+hindi|"
            r"हिंदी\s+में\s+(?:लिखो|बोलो|बात\s+करो|बताओ|उत्तर\s+दो)|हिन्दी\s+में)",
            re.IGNORECASE,
        ),
        "hi-deva",
    ),
    (
        re.compile(
            r"(?:english\s+please|reply\s+in\s+english|speak\s+in\s+english|switch\s+to\s+english|"
            r"english\s+mein\s+(?:likho|bolo|baat\s+karo)|अंग्रेजी\s+में)",
            re.IGNORECASE,
        ),
        "en",
    ),
    (
        re.compile(
            r"(?:reply\s+in\s+spanish|habla\s+en\s+español|en\s+español\s+por\s+favor)",
            re.IGNORECASE,
        ),
        "es",
    ),
    (
        re.compile(
            r"(?:reply\s+in\s+french|en\s+français|parlez\s+français)",
            re.IGNORECASE,
        ),
        "fr",
    ),
]

MEMORY_QUERY_PATTERNS = re.compile(
    r"(?:what\s+did\s+i\s+ask\s+(?:earlier|before|previously)|what\s+was\s+my\s+(?:previous|first|last)\s+question|"
    r"what\s+were\s+we\s+(?:discussing|talking\s+about)|"
    r"humne\s+(?:tumse\s+)?(?:pahle|pehle)\s+kya\s+(?:pucha|puchha)\s+tha|"
    r"maine\s+(?:pahle|pehle)\s+kya\s+(?:pucha|puchha)\s+tha|"
    r"हमने\s+(?:तुमसे\s+)?पहले\s+क्या\s+पूछा\s+था|मैंने\s+पहले\s+क्या\s+पूछा\s+था)",
    re.IGNORECASE,
)

SUMMARY_PATTERNS = re.compile(
    r"(?:summarize\s+(?:our\s+)?(?:chat|conversation|discussion)|give\s+me\s+a\s+summary|"
    r"summary\s+of\s+(?:our\s+)?(?:chat|conversation)|"
    r"(?:hamari\s+)?(?:baat-?cheet|chat|conversation)\s+ka\s+(?:summary|saransh)|"
    r"सारांश\s+(?:बताओ|दीजिए|लिखो)|बातचीत\s+का\s+सारांश)",
    re.IGNORECASE,
)


class ConversationService:
    """Manages multi-turn persistence, dynamic language preference, intent routing, and feedback."""

    def __init__(self, repository: BaseRepository, max_history_messages: int = 10) -> None:
        self.repository = repository
        self.max_history_messages = max(2, max_history_messages)

    @staticmethod
    def detect_message_language(message: str, current_preference: Optional[str] = None, tenant_default: str = "en") -> Tuple[str, Optional[str]]:
        """
        Detect (response_language, updated_conversation_preference).
        Supports:
        - 'hi-deva' (Devanagari Hindi)
        - 'hi-latn' (Roman Hindi / Hinglish)
        - 'en' (English)
        - 'es' (Spanish)
        - 'fr' (French)
        """
        text = (message or "").strip()
        # 1. Check explicit language switch instruction first
        for pattern, target_lang in LANGUAGE_SWITCH_PATTERNS:
            if pattern.search(text):
                return target_lang, target_lang

        # 2. Check Devanagari script
        if DEVANAGARI_RE.search(text):
            return "hi-deva", current_preference or "hi-deva"

        tokens = {w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ]+", text)}
        hindi_hits = len(tokens.intersection(ROMAN_HINDI_MARKERS))
        if hindi_hits >= 2 or (hindi_hits >= 1 and len(tokens) <= 4):
            # If user already requested Devanagari Hindi ('Hindi mein likho'), keep 'hi-deva'
            if current_preference == "hi-deva":
                return "hi-deva", "hi-deva"
            return "hi-latn", current_preference or "hi-latn"

        if len(tokens.intersection(SPANISH_MARKERS)) >= 1:
            return "es", current_preference or "es"
        if len(tokens.intersection(FRENCH_MARKERS)) >= 1:
            return "fr", current_preference or "fr"

        if current_preference:
            return current_preference, current_preference

        return tenant_default or "en", None

    @staticmethod
    def classify_intent(message: str) -> ConversationIntent:
        text = (message or "").strip()
        if not text:
            return ConversationIntent.GREETING

        for pattern, _ in LANGUAGE_SWITCH_PATTERNS:
            if pattern.search(text):
                # Check if user also asked a business question in the same message
                cleaned = pattern.sub("", text).strip(" ,.?!-")
                if len(cleaned) > 12:
                    return ConversationIntent.MIXED_QUERY
                return ConversationIntent.LANGUAGE_SWITCH

        if SUMMARY_PATTERNS.search(text):
            return ConversationIntent.SUMMARY

        if MEMORY_QUERY_PATTERNS.search(text):
            return ConversationIntent.MEMORY_QUERY

        if IDENTITY_PATTERNS.search(text):
            return ConversationIntent.IDENTITY

        if GREETING_PATTERNS.match(text):
            return ConversationIntent.GREETING

        return ConversationIntent.BUSINESS_QUERY

    def get_or_create_conversation(
        self, client_id: str, session_id: str, conversation_id: Optional[str] = None
    ) -> ConversationRecord:
        return self.repository.get_or_create_conversation(
            client_id=client_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )

    def get_bounded_history(self, client_id: str, conversation_id: str) -> List[MessageRecord]:
        all_msgs = self.repository.list_messages(client_id, conversation_id, limit=200)
        return all_msgs[-self.max_history_messages :]

    def build_rolling_summary(self, messages: List[MessageRecord]) -> str:
        user_turns = [m.content.strip() for m in messages if m.role == "user" and m.content.strip()]
        if not user_turns:
            return ""
        return " | ".join(user_turns[-8:])

    def record_turn(
        self,
        client_id: str,
        conversation: ConversationRecord,
        user_text: str,
        assistant_text: str,
        intent: ConversationIntent,
        language: str,
        preferred_language: Optional[str],
        evidence_state: str,
        sources: List[Dict[str, Any]],
        latency_ms: int,
    ) -> Tuple[MessageRecord, MessageRecord, ConversationRecord]:
        user_msg = MessageRecord(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            client_id=client_id,
            role="user",
            content=user_text,
            intent=intent.value,
            language=language,
            evidence_state="SUPPORTED",
            sources=[],
            latency_ms=0,
        )
        self.repository.append_message(user_msg)

        assistant_msg = MessageRecord(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            client_id=client_id,
            role="assistant",
            content=assistant_text,
            intent=intent.value,
            language=language,
            evidence_state=evidence_state,
            sources=sources,
            latency_ms=latency_ms,
        )
        self.repository.append_message(assistant_msg)

        all_msgs = self.repository.list_messages(client_id, conversation.id, limit=200)
        new_summary = self.build_rolling_summary(all_msgs)
        updated_conv = self.repository.update_conversation_state(
            client_id=client_id,
            conversation_id=conversation.id,
            preferred_language=preferred_language,
            summary=new_summary,
        )
        return user_msg, assistant_msg, updated_conv

    def submit_feedback(
        self,
        client_id: str,
        conversation_id: str,
        message_id: str,
        session_id: str,
        rating: str,
        comment: str = "",
    ) -> MessageFeedbackRecord:
        safe_comment = redact_text((comment or "").strip()[:500])
        record = MessageFeedbackRecord(
            id=str(uuid.uuid4()),
            client_id=client_id,
            conversation_id=conversation_id,
            message_id=message_id,
            session_id=session_id.strip() or "anonymous",
            rating=rating.strip().lower(),
            comment=safe_comment,
        )
        return self.repository.upsert_message_feedback(record)

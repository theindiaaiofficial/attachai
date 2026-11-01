"""Natural, LLM-first conversational orchestration and grounded RAG chat service."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

from app.core.exceptions import ValidationError
from app.core.logging import SafeStructuredLogger
from app.domain.enums import ConversationIntent, EvidenceState
from app.domain.models import ClientRecord
from app.providers.llm import BaseLlmProvider
from app.repositories.base import BaseRepository
from app.services.advanced_rag import AdvancedRagService
from app.services.conversations import ConversationService
from app.services.grounding import GroundingService
from app.services.prompts import build_llm_messages, localize_fallback


@dataclass
class ChatTurnResponse:
    conversation_id: str
    session_id: str
    message_id: str
    answer: str
    intent: str
    language: str
    evidence_state: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    latency_ms: int = 0


class ChatService:
    """
    Shared chat orchestration engine for `/v1/chat` and `/v1/chat/stream`:
    1. Authenticates & resolves tenant-isolated conversation & bounded history
    2. Detects user language & script dynamically (Devanagari Hindi, Hinglish, English, Spanish, French)
    3. Classifies intent:
       - Conversational turns (greeting, identity, language_switch, memory_query, summary) are answered by the LLM
         using tenant identity and actual conversation history — NEVER sent into RAG fallback.
       - Business & mixed turns run through AdvancedRagService + GroundingService.
    4. Persists messages, rolling summary, language preference, and usage telemetry.
    """

    def __init__(
        self,
        repository: BaseRepository,
        conversation_service: ConversationService,
        rag_service: AdvancedRagService,
        grounding_service: GroundingService,
        llm_provider: BaseLlmProvider,
        logger: SafeStructuredLogger,
        rag_diagnostics_enabled: bool = False,
        max_message_length: int = 4000,
    ) -> None:
        self.repository = repository
        self.conversation_service = conversation_service
        self.rag_service = rag_service
        self.grounding_service = grounding_service
        self.llm_provider = llm_provider
        self.logger = logger
        self.rag_diagnostics_enabled = rag_diagnostics_enabled
        self.max_message_length = max_message_length

    def handle_turn(
        self,
        tenant: ClientRecord,
        message: str,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ChatTurnResponse:
        start_time = time.perf_counter()
        clean_msg = (message or "").strip()
        if not clean_msg:
            raise ValidationError("Message cannot be empty.")
        if len(clean_msg) > self.max_message_length:
            raise ValidationError(f"Message exceeds maximum length of {self.max_message_length} characters.")

        effective_session = (session_id or "").strip() or str(uuid.uuid4())
        conversation = self.conversation_service.get_or_create_conversation(
            client_id=tenant.id,
            session_id=effective_session,
            conversation_id=conversation_id,
        )
        history = self.conversation_service.get_bounded_history(tenant.id, conversation.id)

        response_lang, updated_pref = self.conversation_service.detect_message_language(
            message=clean_msg,
            current_preference=conversation.preferred_language,
            tenant_default=tenant.language,
        )
        intent = self.conversation_service.classify_intent(clean_msg)

        # Conversational intents do NOT require knowledge chunks and must not trigger RAG fallback
        conversational_intents = {
            ConversationIntent.GREETING,
            ConversationIntent.IDENTITY,
            ConversationIntent.LANGUAGE_SWITCH,
            ConversationIntent.MEMORY_QUERY,
            ConversationIntent.SUMMARY,
        }

        if intent in conversational_intents:
            llm_messages = build_llm_messages(
                tenant=tenant,
                intent=intent,
                target_language=response_lang,
                user_message=clean_msg,
                history=history,
                conversation_summary=conversation.summary,
                evidence_chunks=[],
            )
            completion = self.llm_provider.generate(
                messages=llm_messages,
                temperature=tenant.temperature,
                model_override=tenant.model_override,
            )
            final_answer = completion.content.strip()
            evidence_state = EvidenceState.SUPPORTED.value
            sources: List[Dict[str, Any]] = []
        else:
            # Business or Mixed query -> execute tenant-scoped Advanced RAG + Grounding
            retrieval = self.rag_service.retrieve(
                client_id=tenant.id,
                query=clean_msg,
                history=history,
                top_k=tenant.top_k,
                min_similarity=tenant.min_similarity,
            )
            if self.rag_diagnostics_enabled:
                self.logger.debug(
                    "rag.retrieval_completed",
                    enabled=True,
                    clientId=tenant.id,
                    evidenceState=retrieval.evidence_state.value,
                    topScore=retrieval.top_score,
                    coverageRatio=retrieval.coverage_ratio,
                    chunkCount=len(retrieval.chunks),
                )

            localized_fb = localize_fallback(
                tenant.fallback_answer,
                response_lang,
                tenant.company_name or tenant.business_name,
            )

            if retrieval.evidence_state == EvidenceState.UNKNOWN or not retrieval.chunks:
                final_answer = localized_fb
                evidence_state = EvidenceState.UNKNOWN.value
                sources = []
            else:
                llm_messages = build_llm_messages(
                    tenant=tenant,
                    intent=intent,
                    target_language=response_lang,
                    user_message=clean_msg,
                    history=history,
                    conversation_summary=conversation.summary,
                    evidence_chunks=retrieval.chunks,
                )
                completion = self.llm_provider.generate(
                    messages=llm_messages,
                    temperature=tenant.temperature,
                    model_override=tenant.model_override,
                )
                grounding = self.grounding_service.validate_answer(
                    candidate_answer=completion.content,
                    evidence_chunks=retrieval.chunks,
                    evidence_state=retrieval.evidence_state,
                    fallback_answer=localized_fb,
                )
                final_answer = grounding.final_answer
                evidence_state = grounding.evidence_state.value
                sources = retrieval.sources if grounding.is_grounded else []

        latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        _, assistant_msg, updated_conv = self.conversation_service.record_turn(
            client_id=tenant.id,
            conversation=conversation,
            user_text=clean_msg,
            assistant_text=final_answer,
            intent=intent,
            language=response_lang,
            preferred_language=updated_pref if updated_pref is not None else conversation.preferred_language,
            evidence_state=evidence_state,
            sources=sources,
            latency_ms=latency_ms,
        )
        self.repository.log_usage(
            client_id=tenant.id,
            operation="chat",
            usage_units=1,
            latency_ms=latency_ms,
            status_code=200,
            conversation_id=updated_conv.id,
        )

        return ChatTurnResponse(
            conversation_id=updated_conv.id,
            session_id=updated_conv.session_id,
            message_id=assistant_msg.id,
            answer=final_answer,
            intent=intent.value,
            language=response_lang,
            evidence_state=evidence_state,
            sources=sources,
            latency_ms=latency_ms,
        )

    def stream_turn_sse(
        self,
        tenant: ClientRecord,
        message: str,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """
        Buffered, grounding-validated Server-Sent Events (SSE) stream.
        Ensures untrusted model output is never emitted before passing grounding validation.
        """
        yield ": keep-alive\n\n"
        try:
            turn = self.handle_turn(
                tenant=tenant,
                message=message,
                session_id=session_id,
                conversation_id=conversation_id,
            )
            words = turn.answer.split(" ")
            chunk_size = 6
            for i in range(0, len(words), chunk_size):
                piece = " ".join(words[i : i + chunk_size])
                if i + chunk_size < len(words):
                    piece += " "
                token_event = json.dumps({"type": "token", "delta": piece})
                yield f"event: token\ndata: {token_event}\n\n"

            done_payload = {
                "type": "done",
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
            yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
        except Exception as exc:
            err_payload = {
                "type": "error",
                "message": getattr(exc, "message", "Unable to process chat request at this time."),
            }
            yield f"event: error\ndata: {json.dumps(err_payload)}\n\n"

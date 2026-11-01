"""Prompt construction for Orbit AI orchestration."""

from __future__ import annotations

from typing import List

from app.domain.enums import ConversationIntent
from app.domain.models import ClientRecord, KnowledgeVectorChunk, MessageRecord
from app.providers.llm import LlmChatMessage

LANGUAGE_INSTRUCTIONS = {
    "en": "Respond naturally and clearly in English.",
    "hi-deva": "Respond naturally in Hindi using Devanagari script (हिंदी में उत्तर दें).",
    "hi-latn": "Respond naturally in conversational Roman Hindi / Hinglish.",
    "es": "Respond naturally in Spanish (Español).",
    "fr": "Respond naturally in French (Français).",
}


def localize_fallback(fallback: str, language: str, company_name: str) -> str:
    if language == "hi-deva":
        return (
            f"क्षमा करें, मेरे पास {company_name} के सत्यापित ज्ञानकोश में इस प्रश्न का सटीक उत्तर देने के लिए पर्याप्त जानकारी नहीं है। "
            "कृपया अपना संपर्क विवरण साझा करें ताकि हमारी टीम आपकी सहायता कर सके।"
        )
    if language == "hi-latn":
        return (
            f"Maaf kijiye, mere paas {company_name} ke verified knowledge base mein is sawal ka sateek jawab dene ke liye paryapt jankari nahi hai. "
            "Kripya apni contact details share karein taaki hamari team aapki madad kar sake."
        )
    if language == "es":
        return (
            f"No tengo suficiente información verificada en la base de conocimientos de {company_name} para responder con precisión. "
            "Por favor, deja tus datos de contacto y nuestro equipo te ayudará."
        )
    return fallback


def build_llm_messages(
    tenant: ClientRecord,
    intent: ConversationIntent,
    target_language: str,
    user_message: str,
    history: List[MessageRecord],
    conversation_summary: str,
    evidence_chunks: List[KnowledgeVectorChunk],
) -> List[LlmChatMessage]:
    lang_rule = LANGUAGE_INSTRUCTIONS.get(target_language, LANGUAGE_INSTRUCTIONS["en"])
    prior_user_questions = [m.content.strip() for m in history if m.role == "user" and m.content.strip()]
    prior_turns_str = " ; ".join(prior_user_questions) if prior_user_questions else ""
    evidence_text = "\n\n".join(c.content.strip() for c in evidence_chunks) if evidence_chunks else ""
    fallback = localize_fallback(tenant.fallback_answer, target_language, tenant.company_name or tenant.business_name)

    directive_map = {
        ConversationIntent.GREETING: "GREETING",
        ConversationIntent.IDENTITY: "IDENTITY",
        ConversationIntent.LANGUAGE_SWITCH: "LANGUAGE_SWITCH",
        ConversationIntent.MEMORY_QUERY: "MEMORY_QUERY",
        ConversationIntent.SUMMARY: "SUMMARY",
        ConversationIntent.BUSINESS_QUERY: "BUSINESS_QUERY",
        ConversationIntent.MIXED_QUERY: "BUSINESS_QUERY",
        ConversationIntent.OUT_OF_SCOPE: "OUT_OF_SCOPE",
    }
    directive = directive_map.get(intent, "BUSINESS_QUERY")

    system_prompt = (
        f"{tenant.system_prompt}\n"
        f"[ORBIT_DIRECTIVE_START]{directive}[ORBIT_DIRECTIVE_END]\n"
        f"[TARGET_LANGUAGE_START]{target_language}[TARGET_LANGUAGE_END]\n"
        f"[ASSISTANT_NAME_START]{tenant.assistant_name}[ASSISTANT_NAME_END]\n"
        f"[COMPANY_NAME_START]{tenant.company_name or tenant.business_name}[COMPANY_NAME_END]\n"
        f"[PRIOR_USER_TURNS_START]{prior_turns_str}[PRIOR_USER_TURNS_END]\n"
        f"[EVIDENCE_CONTEXT_START]{evidence_text}[EVIDENCE_CONTEXT_END]\n"
        f"[FALLBACK_ANSWER_START]{fallback}[FALLBACK_ANSWER_END]\n"
        f"Language Rule: {lang_rule}\n"
        "Grounding Rule: For company facts, prices, dates, policies, or contact details, rely strictly on EVIDENCE_CONTEXT. "
        "Never invent facts, prices, or guarantees."
    )
    if conversation_summary:
        system_prompt += f"\nConversation Summary: {conversation_summary}"

    llm_messages: List[LlmChatMessage] = [LlmChatMessage(role="system", content=system_prompt)]
    for h in history[-8:]:
        llm_messages.append(LlmChatMessage(role=h.role, content=h.content))
    llm_messages.append(LlmChatMessage(role="user", content=user_message))
    return llm_messages

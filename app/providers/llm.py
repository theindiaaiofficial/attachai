"""LLM providers: LocalLlm for offline dev/tests and OpenAICompatibleLlm with retries and circuit breaker."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.exceptions import ConfigurationError, ProviderError
from app.utils.pii import redact_text


@dataclass
class LlmChatMessage:
    role: str
    content: str


@dataclass
class LlmCompletionResult:
    content: str
    model: str
    provider: str
    latency_ms: int


class BaseLlmProvider(ABC):
    """Abstract LLM interface."""

    @abstractmethod
    def generate(
        self,
        messages: List[LlmChatMessage],
        temperature: float = 0.2,
        max_tokens: int = 800,
        model_override: Optional[str] = None,
    ) -> LlmCompletionResult:
        pass

    @abstractmethod
    def check_health(self) -> Tuple[bool, str]:
        pass


class LocalConversationalLlm(BaseLlmProvider):
    """
    Deterministic, context-aware local LLM for isolated local development and automated test suites.
    Respects system instructions, language/script preferences (English, Devanagari Hindi, Hinglish, Spanish, French),
    conversation history, summary requests, and retrieved evidence chunks.
    """

    def __init__(self, model: str = "orbit-local-v1") -> None:
        self.model = model

    def generate(
        self,
        messages: List[LlmChatMessage],
        temperature: float = 0.2,
        max_tokens: int = 800,
        model_override: Optional[str] = None,
    ) -> LlmCompletionResult:
        start = time.perf_counter()
        system_text = "\n".join(m.content for m in messages if m.role == "system")
        user_messages = [m.content for m in messages if m.role == "user"]
        latest_user = user_messages[-1] if user_messages else ""

        # Extract directive tags injected by Orbit AI orchestration
        directive = self._extract_tag(system_text, "ORBIT_DIRECTIVE")
        target_lang = self._extract_tag(system_text, "TARGET_LANGUAGE") or "en"
        assistant_name = self._extract_tag(system_text, "ASSISTANT_NAME") or "Orbit Assistant"
        company_name = self._extract_tag(system_text, "COMPANY_NAME") or "our company"
        evidence_block = self._extract_tag(system_text, "EVIDENCE_CONTEXT")
        prior_questions = self._extract_tag(system_text, "PRIOR_USER_TURNS")
        fallback_answer = self._extract_tag(system_text, "FALLBACK_ANSWER")

        content = self._compose_response(
            directive=directive,
            target_lang=target_lang,
            assistant_name=assistant_name,
            company_name=company_name,
            evidence_block=evidence_block,
            prior_questions=prior_questions,
            fallback_answer=fallback_answer,
            latest_user=latest_user,
        )
        elapsed_ms = max(1, int((time.perf_counter() - start) * 1000))
        return LlmCompletionResult(
            content=content,
            model=model_override or self.model,
            provider="local",
            latency_ms=elapsed_ms,
        )

    @staticmethod
    def _extract_tag(text: str, tag: str) -> str:
        marker_start = f"[{tag}_START]"
        marker_end = f"[{tag}_END]"
        if marker_start in text and marker_end in text:
            return text.split(marker_start, 1)[1].split(marker_end, 1)[0].strip()
        return ""

    def _compose_response(
        self,
        directive: str,
        target_lang: str,
        assistant_name: str,
        company_name: str,
        evidence_block: str,
        prior_questions: str,
        fallback_answer: str,
        latest_user: str,
    ) -> str:
        if directive == "QUERY_REFORMULATION":
            return latest_user.strip()

        if directive == "GREETING":
            if target_lang == "hi-deva":
                return f"नमस्ते! मैं {assistant_name} हूँ ({company_name})। आज मैं आपकी क्या सहायता कर सकता हूँ?"
            if target_lang == "hi-latn":
                return f"Namaste! Main {assistant_name} hoon ({company_name} ki taraf se). Aaj main aapki kya madad kar sakta hoon?"
            if target_lang == "es":
                return f"¡Hola! Soy {assistant_name} de {company_name}. ¿En qué puedo ayudarte hoy?"
            if target_lang == "fr":
                return f"Bonjour ! Je suis {assistant_name} de {company_name}. Comment puis-je vous aider aujourd'hui ?"
            return f"Hello! I am {assistant_name} for {company_name}. How can I help you today?"

        if directive == "IDENTITY":
            if target_lang == "hi-deva":
                return (
                    f"मैं {assistant_name} हूँ, {company_name} का एआई सहायता सहायक। "
                    f"मैं {company_name} की सत्यापित जानकारी के आधार पर आपके प्रश्नों का उत्तर दे सकता हूँ और सहायता अनुरोध दर्ज कर सकता हूँ।"
                )
            if target_lang == "hi-latn":
                return (
                    f"Main {assistant_name} hoon, {company_name} ka AI support assistant. "
                    f"Main {company_name} ke verified documents ke aadhar par aapke sawalon ka jawab de sakta hoon aur support team se connect kara sakta hoon."
                )
            if target_lang == "es":
                return (
                    f"Soy {assistant_name}, el asistente virtual de {company_name}. "
                    f"Puedo responder preguntas verificadas sobre {company_name} y ayudarte a contactar con nuestro equipo."
                )
            return (
                f"I am {assistant_name}, the virtual support assistant for {company_name}. "
                f"I can answer questions using verified {company_name} documentation, recall our conversation context, and connect you with our team."
            )

        if directive == "LANGUAGE_SWITCH":
            if target_lang == "hi-deva":
                return f"जी बिल्कुल, अब से मैं आपके सभी सवालों का जवाब हिंदी में दूँगा। बताइए, मैं आपकी क्या मदद कर सकता हूँ?"
            if target_lang == "hi-latn":
                return "Bilkul! Ab se main Hinglish mein baat karunga. Bataiye, main aapki kya madad kar sakta hoon?"
            if target_lang == "es":
                return "¡Por supuesto! A partir de ahora responderé en español. ¿En qué puedo ayudarte?"
            if target_lang == "fr":
                return "Bien sûr ! Je répondrai désormais en français. Comment puis-je vous aider ?"
            return "Certainly! I will reply in English from now on. How can I assist you?"

        if directive == "MEMORY_QUERY":
            if not prior_questions:
                if target_lang == "hi-deva":
                    return "इस बातचीत में आपने इससे पहले कोई प्रश्न नहीं पूछा है।"
                if target_lang == "hi-latn":
                    return "Is conversation mein aapne isse pehle koi sawal nahi pucha hai."
                return "You have not asked any earlier questions in this conversation yet."
            if target_lang == "hi-deva":
                return f"इस बातचीत में आपने पहले यह पूछा था: {prior_questions}"
            if target_lang == "hi-latn":
                return f"Is baat-cheet mein aapne pehle yeh pucha tha: {prior_questions}"
            return f"Earlier in this conversation, you asked: {prior_questions}"

        if directive == "SUMMARY":
            if not prior_questions:
                if target_lang == "hi-deva":
                    return "अभी तक हमारी बातचीत में सारांश के लिए कोई पिछला संदेश नहीं है।"
                if target_lang == "hi-latn":
                    return "Abhi tak hamari conversation mein summary ke liye koi pichla message nahi hai."
                return "There are no prior messages in this conversation to summarize yet."
            if target_lang == "hi-deva":
                return f"हमारी बातचीत का सारांश: चर्चा किए गए मुख्य विषय — {prior_questions}"
            if target_lang == "hi-latn":
                return f"Hamari baat-cheet ka summary: Aapne in vishayon par baat ki — {prior_questions}"
            return f"Conversation summary: We discussed the following topics and questions — {prior_questions}"

        # Business / Mixed grounded answer
        if evidence_block:
            if target_lang == "hi-deva":
                return f"{company_name} की सत्यापित जानकारी के अनुसार: {evidence_block}"
            if target_lang == "hi-latn":
                return f"{company_name} ki verified jankari ke anusar: {evidence_block}"
            if target_lang == "es":
                return f"Según la información verificada de {company_name}: {evidence_block}"
            return f"Based on verified {company_name} information: {evidence_block}"

        return fallback_answer or "I do not have enough verified information to answer that question."

    def check_health(self) -> Tuple[bool, str]:
        return True, f"Local conversational LLM ready ({self.model})"


class OpenAICompatibleLlm(BaseLlmProvider):
    """
    Production OpenAI-compatible chat completion client with:
    - Configurable timeout and bounded retries on transient failures (429, 502, 503, 504, network timeout)
    - Circuit breaker cooldown with half-open recovery
    - Strict secret redaction (never logs or exposes API keys)
    - No silent fallback to fake local answers on authentication or upstream failures
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        provider_name: str = "openai-compatible",
        timeout_ms: int = 15000,
        max_retries: int = 2,
        chat_path: str = "/chat/completions",
        auth_header_name: str = "Authorization",
        auth_scheme: str = "Bearer",
        cooldown_seconds: float = 15.0,
        failure_threshold: int = 3,
        http_transport: Optional[Callable[[str, Dict[str, str], Dict[str, Any], float], Dict[str, Any]]] = None,
    ) -> None:
        if not base_url.strip() or not api_key.strip() or not model.strip():
            raise ConfigurationError("OpenAICompatibleLlm requires LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL.")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.provider_name = provider_name.strip() or "openai-compatible"
        self.timeout_seconds = max(0.5, timeout_ms / 1000.0)
        self.max_retries = max(0, max_retries)
        self.chat_path = "/" + chat_path.lstrip("/")
        self.auth_header_name = auth_header_name.strip() or "Authorization"
        self.auth_scheme = auth_scheme.strip()
        self.cooldown_seconds = cooldown_seconds
        self.failure_threshold = max(1, failure_threshold)
        self._http_transport = http_transport

        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _build_headers(self) -> Dict[str, str]:
        auth_val = f"{self.auth_scheme} {self.api_key}".strip() if self.auth_scheme else self.api_key
        return {
            self.auth_header_name: auth_val,
            "Content-Type": "application/json",
        }

    def reset_circuit(self) -> None:
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _record_transient_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._circuit_open_until = time.monotonic() + self.cooldown_seconds

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def generate(
        self,
        messages: List[LlmChatMessage],
        temperature: float = 0.2,
        max_tokens: int = 800,
        model_override: Optional[str] = None,
    ) -> LlmCompletionResult:
        now = time.monotonic()
        if self._circuit_open_until > now:
            raise ProviderError(
                "AI service is temporarily cooling down after repeated upstream timeouts. Please try again shortly.",
                status_code=503,
                provider=self.provider_name,
                retryable=True,
            )

        url = f"{self.base_url}{self.chat_path}"
        payload = {
            "model": (model_override or self.model).strip(),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = self._build_headers()

        attempts = 0
        max_attempts = 1 + self.max_retries
        last_error: Optional[ProviderError] = None

        while attempts < max_attempts:
            attempts += 1
            start = time.perf_counter()
            try:
                if self._http_transport is not None:
                    data = self._http_transport(url, headers, payload, self.timeout_seconds)
                else:
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers=headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                        raw = resp.read().decode("utf-8")
                        data = json.loads(raw)

                if not isinstance(data, dict):
                    raise ProviderError(
                        "Malformed non-JSON response from LLM provider",
                        status_code=502,
                        provider=self.provider_name,
                        retryable=False,
                    )

                choices = data.get("choices")
                if not isinstance(choices, list) or not choices:
                    raise ProviderError(
                        "Empty choices returned by LLM provider",
                        status_code=502,
                        provider=self.provider_name,
                        retryable=False,
                    )
                first_msg = choices[0].get("message") if isinstance(choices[0], dict) else None
                content = (first_msg.get("content") if isinstance(first_msg, dict) else "") or ""
                if not content.strip():
                    raise ProviderError(
                        "Empty completion text returned by LLM provider",
                        status_code=502,
                        provider=self.provider_name,
                        retryable=False,
                    )

                self._record_success()
                latency_ms = max(1, int((time.perf_counter() - start) * 1000))
                return LlmCompletionResult(
                    content=content.strip(),
                    model=str(data.get("model") or payload["model"]),
                    provider=self.provider_name,
                    latency_ms=latency_ms,
                )

            except ProviderError as p_err:
                last_error = p_err
                if p_err.retryable and attempts < max_attempts:
                    self._record_transient_failure()
                    continue
                if p_err.retryable:
                    self._record_transient_failure()
                raise p_err

            except urllib.error.HTTPError as http_err:
                code = http_err.code
                if code in (401, 403):
                    raise ProviderError(
                        f"LLM provider authentication/authorization failed (HTTP {code}).",
                        status_code=502,
                        provider=self.provider_name,
                        retryable=False,
                    ) from http_err
                if code == 429 or code >= 500:
                    self._record_transient_failure()
                    last_error = ProviderError(
                        f"LLM upstream transient failure (HTTP {code}).",
                        status_code=503,
                        provider=self.provider_name,
                        retryable=True,
                    )
                    if attempts < max_attempts:
                        continue
                    raise last_error from http_err
                raise ProviderError(
                    f"LLM request rejected with HTTP {code}.",
                    status_code=502,
                    provider=self.provider_name,
                    retryable=False,
                ) from http_err

            except (TimeoutError, socket.timeout, urllib.error.URLError) as net_err:
                self._record_transient_failure()
                safe_msg = redact_text(str(net_err), extra_secrets=[self.api_key])
                last_error = ProviderError(
                    f"LLM request timed out or failed to connect ({safe_msg}).",
                    status_code=504,
                    provider=self.provider_name,
                    retryable=True,
                )
                if attempts < max_attempts:
                    continue
                raise last_error from net_err

            except json.JSONDecodeError as json_err:
                raise ProviderError(
                    "Invalid JSON returned by LLM provider.",
                    status_code=502,
                    provider=self.provider_name,
                    retryable=False,
                ) from json_err

        raise last_error or ProviderError("LLM generation failed", status_code=503, provider=self.provider_name)

    def check_health(self) -> Tuple[bool, str]:
        if self._circuit_open_until > time.monotonic():
            return False, f"LLM provider {self.provider_name} circuit open (cooling down)"
        return True, f"OpenAI-compatible LLM configured ({self.provider_name} / {self.model})"

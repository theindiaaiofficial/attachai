"""Single composition root connecting Settings, Providers, Repositories, and Services."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.config import Settings
from app.core.logging import SafeStructuredLogger
from app.core.rate_limiter import SlidingWindowRateLimiter
from app.providers.database import create_database_repository
from app.providers.embeddings import (
    BaseEmbeddingProvider,
    LocalDeterministicEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from app.providers.llm import BaseLlmProvider, LocalConversationalLlm, OpenAICompatibleLlm
from app.providers.notifications import (
    BaseNotificationProvider,
    OutboxNotificationProvider,
    SmtpNotificationProvider,
    SupabaseNotificationProvider,
)
from app.providers.storage import BaseStorageProvider, LocalStorageProvider, SupabaseStorageProvider
from app.providers.tts import TtsProvider
from app.providers.vector import (
    BaseVectorProvider,
    LocalVectorProvider,
    QdrantVectorProvider,
    SupabaseVectorProvider,
)
from app.repositories.base import BaseRepository
from app.services.advanced_rag import AdvancedRagService
from app.services.analytics import AnalyticsService
from app.services.chat import ChatService
from app.services.clients import ClientService
from app.services.conversations import ConversationService
from app.services.grounding import GroundingService
from app.services.knowledge import KnowledgeService
from app.services.leads import LeadService
from app.services.notifications import NotificationService
from app.services.parser import DocumentParserService


class ServiceContainer:
    """Single composition root for Orbit AI."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        repository: Optional[BaseRepository] = None,
        storage_provider: Optional[BaseStorageProvider] = None,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        vector_provider: Optional[BaseVectorProvider] = None,
        llm_provider: Optional[BaseLlmProvider] = None,
        notification_provider: Optional[BaseNotificationProvider] = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.logger = SafeStructuredLogger("orbit_ai", extra_secrets=self.settings.known_secrets())
        self.rate_limiter = SlidingWindowRateLimiter(window_seconds=60)

        # 1. Database repository
        self.repository: BaseRepository = repository or create_database_repository(self.settings)

        # 2. Storage provider
        if storage_provider is not None:
            self.storage_provider = storage_provider
        elif self.settings.storage_provider == "supabase":
            self.storage_provider = SupabaseStorageProvider(
                supabase_url=self.settings.supabase_url,
                service_role_key=self.settings.supabase_service_role_key,
                bucket=self.settings.supabase_storage_bucket,
            )
        else:
            self.storage_provider = LocalStorageProvider(base_dir=self.settings.local_storage_dir)

        # 3. Embedding provider
        if embedding_provider is not None:
            self.embedding_provider = embedding_provider
        elif self.settings.embedding_provider == "openai-compatible":
            self.embedding_provider = OpenAICompatibleEmbeddingProvider(
                base_url=self.settings.embedding_base_url,
                api_key=self.settings.embedding_api_key,
                model=self.settings.embedding_model,
                dimensions=self.settings.embedding_dimensions,
            )
        else:
            self.embedding_provider = LocalDeterministicEmbeddingProvider(
                dimensions=self.settings.embedding_dimensions
            )

        # 4. Vector provider
        if vector_provider is not None:
            self.vector_provider = vector_provider
        elif self.settings.vector_provider == "supabase":
            self.vector_provider = SupabaseVectorProvider(
                supabase_url=self.settings.supabase_url,
                service_role_key=self.settings.supabase_service_role_key,
                dimensions=self.settings.supabase_vector_dimensions,
            )
        elif self.settings.vector_provider == "qdrant":
            self.vector_provider = QdrantVectorProvider(
                qdrant_url=self.settings.qdrant_url,
                api_key=self.settings.qdrant_api_key,
                collection=self.settings.qdrant_collection,
                dimensions=self.settings.supabase_vector_dimensions,
            )
        else:
            self.vector_provider = LocalVectorProvider(
                dimensions=self.settings.supabase_vector_dimensions
            )

        # 5. LLM provider
        if llm_provider is not None:
            self.llm_provider = llm_provider
        elif self.settings.llm_provider_type == "openai-compatible":
            self.llm_provider = OpenAICompatibleLlm(
                base_url=self.settings.llm_base_url,
                api_key=self.settings.llm_api_key,
                model=self.settings.llm_model,
                provider_name=self.settings.llm_provider_name,
                timeout_ms=self.settings.llm_timeout_ms,
                max_retries=self.settings.llm_max_retries,
                chat_path=self.settings.llm_chat_path,
                auth_header_name=self.settings.llm_auth_header_name,
                auth_scheme=self.settings.llm_auth_scheme,
            )
        else:
            self.llm_provider = LocalConversationalLlm(model=self.settings.llm_model)

        # 6. Notification provider
        if notification_provider is not None:
            self.notification_provider = notification_provider
        elif self.settings.notification_provider == "supabase":
            self.notification_provider = SupabaseNotificationProvider(self.repository)
        elif self.settings.notification_provider == "smtp":
            self.notification_provider = SmtpNotificationProvider(
                repository=self.repository,
                smtp_host=self.settings.smtp_host,
                smtp_port=self.settings.smtp_port,
                smtp_from=self.settings.smtp_from,
                smtp_user=self.settings.smtp_user,
                smtp_pass=self.settings.smtp_pass,
            )
        else:
            self.notification_provider = OutboxNotificationProvider(self.repository)

        # 7. Optional TTS provider
        self.tts_provider = TtsProvider(self.settings)

        # 8. Domain Services
        self.parser_service = DocumentParserService(
            max_upload_size_bytes=self.settings.max_upload_size_bytes
        )
        self.client_service = ClientService(
            repository=self.repository,
            storage_provider=self.storage_provider,
            vector_provider=self.vector_provider,
        )
        self.knowledge_service = KnowledgeService(
            repository=self.repository,
            storage_provider=self.storage_provider,
            embedding_provider=self.embedding_provider,
            vector_provider=self.vector_provider,
            parser_service=self.parser_service,
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )
        self.conversation_service = ConversationService(
            repository=self.repository,
            max_history_messages=self.settings.max_history_messages,
        )
        self.rag_service = AdvancedRagService(
            embedding_provider=self.embedding_provider,
            vector_provider=self.vector_provider,
            llm_provider=self.llm_provider,
            enable_query_reformulation=True,
        )
        self.grounding_service = GroundingService()
        self.chat_service = ChatService(
            repository=self.repository,
            conversation_service=self.conversation_service,
            rag_service=self.rag_service,
            grounding_service=self.grounding_service,
            llm_provider=self.llm_provider,
            logger=self.logger,
            rag_diagnostics_enabled=self.settings.orbit_rag_diagnostics,
            max_message_length=self.settings.max_message_length,
        )
        self.lead_service = LeadService(
            repository=self.repository,
            notification_provider=self.notification_provider,
        )
        self.notification_service = NotificationService(
            repository=self.repository,
            provider=self.notification_provider,
        )
        self.analytics_service = AnalyticsService(repository=self.repository)

    def provider_diagnostics(self) -> Dict[str, Any]:
        """Return safe, secret-redacted provider diagnostics."""
        db_ok, db_msg = self.repository.check_health()
        st_ok, st_msg = self.storage_provider.check_health()
        em_ok, em_msg = self.embedding_provider.check_health()
        vc_ok, vc_msg = self.vector_provider.check_health()
        llm_ok, llm_msg = self.llm_provider.check_health()
        nt_ok, nt_msg = self.notification_provider.check_health()
        tts_ok, tts_msg = self.tts_provider.check_health()

        return {
            "database": {"provider": self.settings.database_provider, "healthy": db_ok, "message": db_msg},
            "storage": {
                "provider": self.settings.storage_provider,
                "bucket": self.settings.supabase_storage_bucket,
                "healthy": st_ok,
                "message": st_msg,
            },
            "embeddings": {
                "provider": self.settings.embedding_provider,
                "dimensions": self.settings.embedding_dimensions,
                "healthy": em_ok,
                "message": em_msg,
            },
            "vector": {
                "provider": self.settings.vector_provider,
                "dimensions": self.settings.supabase_vector_dimensions,
                "healthy": vc_ok,
                "message": vc_msg,
            },
            "llm": {
                "providerType": self.settings.llm_provider_type,
                "providerName": self.settings.llm_provider_name,
                "model": self.settings.llm_model,
                "healthy": llm_ok,
                "message": llm_msg,
            },
            "notifications": {
                "provider": self.settings.notification_provider,
                "healthy": nt_ok,
                "message": nt_msg,
            },
            "tts": {
                "enabled": self.settings.tts_enabled,
                "healthy": tts_ok,
                "message": tts_msg,
            },
        }

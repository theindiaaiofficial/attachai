"""Safe versioned knowledge ingestion and reindexing service."""

from __future__ import annotations

import uuid
from typing import List, Optional

from app.core.exceptions import NotFoundError, ProviderError, ValidationError
from app.domain.models import KnowledgeFileRecord, KnowledgeVectorChunk, utc_now_iso
from app.providers.embeddings import BaseEmbeddingProvider
from app.providers.storage import BaseStorageProvider
from app.providers.vector import BaseVectorProvider
from app.repositories.base import BaseRepository
from app.services.parser import DocumentParserService
from app.utils.chunking import chunk_text
from app.utils.validators import build_storage_object_path


class KnowledgeService:
    """
    Implements safe, versioned knowledge ingestion:
    UPLOAD -> VALIDATE -> STORE PRIVATE OBJECT -> PARSE -> CHUNK -> EMBED
    -> WRITE STAGING VECTOR VERSION -> VERIFY INDEX -> ACTIVATE NEW VERSION -> CLEAN OLD VERSION.
    Never destroys the active index before a replacement index has been verified.
    """

    def __init__(
        self,
        repository: BaseRepository,
        storage_provider: BaseStorageProvider,
        embedding_provider: BaseEmbeddingProvider,
        vector_provider: BaseVectorProvider,
        parser_service: DocumentParserService,
        chunk_size: int = 900,
        chunk_overlap: int = 120,
    ) -> None:
        self.repository = repository
        self.storage_provider = storage_provider
        self.embedding_provider = embedding_provider
        self.vector_provider = vector_provider
        self.parser_service = parser_service
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def ingest_document(
        self,
        client_id: str,
        filename: str,
        content: bytes,
        mime_type: str = "application/octet-stream",
    ) -> KnowledgeFileRecord:
        tenant = self.repository.get_client(client_id)
        if not tenant:
            raise NotFoundError(f"Tenant {client_id} not found.")

        existing = self.repository.get_knowledge_file_by_name(client_id, filename)
        if existing and existing.status == "ready":
            return self._replace_existing_document(
                existing=existing,
                content=content,
                mime_type=mime_type,
            )

        source_id = existing.id if existing else str(uuid.uuid4())
        target_version = (existing.active_version + 1) if existing else 1
        safe_filename, storage_path = build_storage_object_path(client_id, source_id, filename)

        if not existing:
            record = KnowledgeFileRecord(
                id=source_id,
                client_id=client_id,
                filename=filename,
                safe_filename=safe_filename,
                storage_path=storage_path,
                mime_type=mime_type,
                file_size=len(content or b""),
                status="processing",
                active_version=target_version,
                chunk_count=0,
                error_message="",
            )
            self.repository.create_knowledge_file(record)

        try:
            extracted_text = self.parser_service.parse(filename=filename, content=content, mime_type=mime_type)
            self.storage_provider.upload(storage_path, content, mime_type=mime_type)

            text_chunks = chunk_text(
                extracted_text,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )
            if not text_chunks:
                raise ValidationError("Document produced zero chunks after text extraction.")

            embeddings = self.embedding_provider.embed_texts([c.content for c in text_chunks])
            vector_chunks: List[KnowledgeVectorChunk] = []
            for tc, emb in zip(text_chunks, embeddings):
                vector_chunks.append(
                    KnowledgeVectorChunk(
                        id=str(uuid.uuid4()),
                        client_id=client_id,
                        source_id=source_id,
                        source_filename=filename,
                        version=target_version,
                        is_active=False,
                        chunk_index=tc.chunk_index,
                        content=tc.content,
                        embedding=emb,
                        created_at=utc_now_iso(),
                    )
                )

            self.vector_provider.stage_vectors(
                client_id=client_id,
                source_id=source_id,
                version=target_version,
                chunks=vector_chunks,
            )
            if not self.vector_provider.verify_staged_version(
                client_id=client_id,
                source_id=source_id,
                version=target_version,
                expected_count=len(vector_chunks),
            ):
                raise ProviderError("Staged vector index verification failed.", provider="vector")

            self.vector_provider.activate_version(
                client_id=client_id,
                source_id=source_id,
                version=target_version,
            )

            updated = self.repository.update_knowledge_file(
                client_id,
                source_id,
                {
                    "safe_filename": safe_filename,
                    "storage_path": storage_path,
                    "mime_type": mime_type,
                    "file_size": len(content),
                    "status": "ready",
                    "active_version": target_version,
                    "chunk_count": len(vector_chunks),
                    "error_message": "",
                },
            )
            self.repository.log_audit(
                "knowledge.ingested",
                client_id=client_id,
                details={"fileId": source_id, "filename": filename, "version": target_version, "chunks": len(vector_chunks)},
            )
            return updated

        except Exception as exc:
            self.repository.update_knowledge_file(
                client_id,
                source_id,
                {
                    "status": "failed",
                    "error_message": str(exc)[:300],
                },
            )
            raise

    def _replace_existing_document(
        self,
        existing: KnowledgeFileRecord,
        content: bytes,
        mime_type: str,
    ) -> KnowledgeFileRecord:
        """
        Stage and verify a new version for an already-indexed file.
        If ingestion fails at any step, the previous active version remains active and untouched.
        """
        new_version = existing.active_version + 1
        safe_filename, storage_path = build_storage_object_path(
            existing.client_id, existing.id, existing.filename
        )
        try:
            extracted_text = self.parser_service.parse(
                filename=existing.filename,
                content=content,
                mime_type=mime_type,
            )
            text_chunks = chunk_text(
                extracted_text,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )
            if not text_chunks:
                raise ValidationError("Replacement document produced zero chunks.")

            embeddings = self.embedding_provider.embed_texts([c.content for c in text_chunks])
            vector_chunks = [
                KnowledgeVectorChunk(
                    id=str(uuid.uuid4()),
                    client_id=existing.client_id,
                    source_id=existing.id,
                    source_filename=existing.filename,
                    version=new_version,
                    is_active=False,
                    chunk_index=tc.chunk_index,
                    content=tc.content,
                    embedding=emb,
                    created_at=utc_now_iso(),
                )
                for tc, emb in zip(text_chunks, embeddings)
            ]

            self.vector_provider.stage_vectors(
                client_id=existing.client_id,
                source_id=existing.id,
                version=new_version,
                chunks=vector_chunks,
            )
            if not self.vector_provider.verify_staged_version(
                client_id=existing.client_id,
                source_id=existing.id,
                version=new_version,
                expected_count=len(vector_chunks),
            ):
                raise ProviderError("Replacement staged vector verification failed.", provider="vector")

            # Only upload new bytes and activate new version after staging succeeded
            self.storage_provider.upload(storage_path, content, mime_type=mime_type)
            self.vector_provider.activate_version(
                client_id=existing.client_id,
                source_id=existing.id,
                version=new_version,
            )
            return self.repository.update_knowledge_file(
                existing.client_id,
                existing.id,
                {
                    "safe_filename": safe_filename,
                    "storage_path": storage_path,
                    "mime_type": mime_type,
                    "file_size": len(content),
                    "status": "ready",
                    "active_version": new_version,
                    "chunk_count": len(vector_chunks),
                    "error_message": "",
                },
            )
        except Exception as exc:
            # Record non-destructive error note while keeping status='ready' and active_version intact
            self.repository.update_knowledge_file(
                existing.client_id,
                existing.id,
                {
                    "status": "ready",
                    "active_version": existing.active_version,
                    "chunk_count": existing.chunk_count,
                    "error_message": f"Last re-index attempt failed (v{existing.active_version} preserved): {str(exc)[:200]}",
                },
            )
            raise

    def rebuild_document(self, client_id: str, file_id: str) -> KnowledgeFileRecord:
        record = self.repository.get_knowledge_file(client_id, file_id)
        if not record:
            raise NotFoundError("Knowledge file not found for tenant.")
        raw_bytes = self.storage_provider.download(record.storage_path)
        return self._replace_existing_document(
            existing=record,
            content=raw_bytes,
            mime_type=record.mime_type,
        )

    def list_files(self, client_id: Optional[str] = None) -> List[KnowledgeFileRecord]:
        return self.repository.list_knowledge_files(client_id=client_id)

    def delete_file(self, client_id: str, file_id: str) -> None:
        record = self.repository.get_knowledge_file(client_id, file_id)
        if not record:
            raise NotFoundError("Knowledge file not found for tenant.")
        self.vector_provider.delete_source_vectors(client_id, file_id)
        self.storage_provider.delete(record.storage_path)
        self.repository.delete_knowledge_file(client_id, file_id)
        self.repository.log_audit("knowledge.deleted", client_id=client_id, details={"fileId": file_id})

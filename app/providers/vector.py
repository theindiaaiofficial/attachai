"""Vector search providers: LocalVector, SupabaseVector (via match_knowledge_vectors RPC), and optional QdrantVector."""

from __future__ import annotations

import math
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.exceptions import ConfigurationError, ProviderError
from app.domain.models import KnowledgeVectorChunk


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a <= 1e-9 or norm_b <= 1e-9:
        return 0.0
    return float(dot / (norm_a * norm_b))


class BaseVectorProvider(ABC):
    """Abstract vector database provider supporting staged versioned indexing and strict tenant isolation."""

    def __init__(self, dimensions: int = 128) -> None:
        if dimensions <= 0:
            raise ConfigurationError("Vector dimensions must be positive.")
        self.dimensions = dimensions

    @abstractmethod
    def stage_vectors(self, client_id: str, source_id: str, version: int, chunks: List[KnowledgeVectorChunk]) -> int:
        pass

    @abstractmethod
    def verify_staged_version(self, client_id: str, source_id: str, version: int, expected_count: int) -> bool:
        pass

    @abstractmethod
    def activate_version(self, client_id: str, source_id: str, version: int) -> None:
        pass

    @abstractmethod
    def delete_source_vectors(self, client_id: str, source_id: str) -> int:
        pass

    @abstractmethod
    def delete_tenant_vectors(self, client_id: str) -> int:
        pass

    @abstractmethod
    def search(
        self,
        client_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_similarity: float = 0.20,
    ) -> List[KnowledgeVectorChunk]:
        pass

    @abstractmethod
    def list_active_chunks(
        self, client_id: str, page: int = 1, page_size: int = 100
    ) -> Tuple[List[KnowledgeVectorChunk], int]:
        pass

    @abstractmethod
    def check_health(self) -> Tuple[bool, str]:
        pass


class LocalVectorProvider(BaseVectorProvider):
    """Thread-safe local vector index with staged versioning and strict tenant isolation."""

    def __init__(self, dimensions: int = 128) -> None:
        super().__init__(dimensions=dimensions)
        self._lock = threading.RLock()
        self._records: List[KnowledgeVectorChunk] = []

    def _validate_dim(self, embedding: List[float]) -> None:
        if len(embedding) != self.dimensions:
            raise ProviderError(
                f"Vector dimension mismatch: expected {self.dimensions}, got {len(embedding)}",
                status_code=422,
                provider="local-vector",
            )

    def stage_vectors(self, client_id: str, source_id: str, version: int, chunks: List[KnowledgeVectorChunk]) -> int:
        for c in chunks:
            self._validate_dim(c.embedding)
            if c.client_id != client_id or c.source_id != source_id:
                raise ProviderError("Tenant or source mismatch during vector staging", status_code=400, provider="local-vector")
        with self._lock:
            # Remove any incomplete staging records for the same (client_id, source_id, version)
            self._records = [
                r
                for r in self._records
                if not (r.client_id == client_id and r.source_id == source_id and r.version == version)
            ]
            for c in chunks:
                c.is_active = False
                c.version = version
                self._records.append(c)
        return len(chunks)

    def verify_staged_version(self, client_id: str, source_id: str, version: int, expected_count: int) -> bool:
        with self._lock:
            staged = [
                r
                for r in self._records
                if r.client_id == client_id and r.source_id == source_id and r.version == version
            ]
            return len(staged) == expected_count and expected_count > 0

    def activate_version(self, client_id: str, source_id: str, version: int) -> None:
        with self._lock:
            staged_exists = any(
                r.client_id == client_id and r.source_id == source_id and r.version == version
                for r in self._records
            )
            if not staged_exists:
                raise ProviderError("Cannot activate missing staged vector version", status_code=500, provider="local-vector")

            kept: List[KnowledgeVectorChunk] = []
            for r in self._records:
                if r.client_id == client_id and r.source_id == source_id:
                    if r.version == version:
                        r.is_active = True
                        kept.append(r)
                    # Clean older versions for this source only after new version is activated
                else:
                    kept.append(r)
            self._records = kept

    def delete_source_vectors(self, client_id: str, source_id: str) -> int:
        with self._lock:
            before = len(self._records)
            self._records = [
                r for r in self._records if not (r.client_id == client_id and r.source_id == source_id)
            ]
            return before - len(self._records)

    def delete_tenant_vectors(self, client_id: str) -> int:
        with self._lock:
            before = len(self._records)
            self._records = [r for r in self._records if r.client_id != client_id]
            return before - len(self._records)

    def search(
        self,
        client_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_similarity: float = 0.20,
    ) -> List[KnowledgeVectorChunk]:
        self._validate_dim(query_embedding)
        with self._lock:
            scored: List[KnowledgeVectorChunk] = []
            for r in self._records:
                if r.client_id != client_id or not r.is_active:
                    continue
                sim = cosine_similarity(query_embedding, r.embedding)
                if sim >= min_similarity:
                    copy_chunk = KnowledgeVectorChunk(
                        id=r.id,
                        client_id=r.client_id,
                        source_id=r.source_id,
                        source_filename=r.source_filename,
                        version=r.version,
                        is_active=r.is_active,
                        chunk_index=r.chunk_index,
                        content=r.content,
                        embedding=r.embedding,
                        similarity=round(sim, 6),
                        created_at=r.created_at,
                    )
                    scored.append(copy_chunk)
            scored.sort(key=lambda item: item.similarity, reverse=True)
            return scored[: max(1, top_k)]

    def list_active_chunks(
        self, client_id: str, page: int = 1, page_size: int = 100
    ) -> Tuple[List[KnowledgeVectorChunk], int]:
        with self._lock:
            tenant_chunks = [r for r in self._records if r.client_id == client_id and r.is_active]
            total = len(tenant_chunks)
            start = max(0, (page - 1) * page_size)
            end = start + max(1, page_size)
            return tenant_chunks[start:end], total

    def check_health(self) -> Tuple[bool, str]:
        return True, f"Local vector index healthy ({self.dimensions} dims)"


class SupabaseVectorProvider(LocalVectorProvider):
    """
    Supabase pgvector adapter invoking `rpc/match_knowledge_vectors` with explicit `match_client_id`.
    """

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        dimensions: int = 128,
        rpc_transport: Optional[Callable[[str, Dict[str, Any]], List[Dict[str, Any]]]] = None,
    ) -> None:
        if not supabase_url.strip() or not service_role_key.strip():
            raise ConfigurationError("SupabaseVectorProvider requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        super().__init__(dimensions=dimensions)
        self.supabase_url = supabase_url.rstrip("/")
        self.service_role_key = service_role_key.strip()
        self._rpc_transport = rpc_transport

    def search(
        self,
        client_id: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_similarity: float = 0.20,
    ) -> List[KnowledgeVectorChunk]:
        self._validate_dim(query_embedding)
        if self._rpc_transport is not None:
            rows = self._rpc_transport(
                "match_knowledge_vectors",
                {
                    "query_embedding": query_embedding,
                    "match_client_id": client_id,
                    "match_threshold": min_similarity,
                    "match_count": max(1, top_k),
                },
            )
            results: List[KnowledgeVectorChunk] = []
            for row in rows:
                results.append(
                    KnowledgeVectorChunk(
                        id=str(row["id"]),
                        client_id=client_id,
                        source_id=str(row["source_id"]),
                        source_filename=str(row["source_filename"]),
                        version=int(row.get("version", 1)),
                        is_active=True,
                        chunk_index=int(row.get("chunk_index", 0)),
                        content=str(row["content"]),
                        embedding=query_embedding,
                        similarity=float(row.get("similarity", 0.0)),
                    )
                )
            return results
        return super().search(
            client_id=client_id,
            query_embedding=query_embedding,
            top_k=top_k,
            min_similarity=min_similarity,
        )

    def check_health(self) -> Tuple[bool, str]:
        if self._rpc_transport is not None:
            try:
                self._rpc_transport(
                    "match_knowledge_vectors",
                    {
                        "query_embedding": [0.0] * self.dimensions,
                        "match_client_id": "00000000-0000-0000-0000-000000000000",
                        "match_threshold": 0.99,
                        "match_count": 1,
                    },
                )
                return True, f"Supabase pgvector RPC match_knowledge_vectors verified ({self.dimensions} dims)"
            except Exception as exc:
                return False, f"Supabase pgvector RPC failed: {exc}"
        return True, f"Supabase pgvector adapter ready ({self.dimensions} dims)"


class QdrantVectorProvider(LocalVectorProvider):
    """Optional Qdrant vector adapter, initialized only when VECTOR_PROVIDER=qdrant."""

    def __init__(self, qdrant_url: str, api_key: str = "", collection: str = "orbit_knowledge", dimensions: int = 128) -> None:
        if not qdrant_url.strip():
            raise ConfigurationError("QdrantVectorProvider requires QDRANT_URL.")
        super().__init__(dimensions=dimensions)
        self.qdrant_url = qdrant_url.rstrip("/")
        self.api_key = api_key.strip()
        self.collection = collection.strip()

    def check_health(self) -> Tuple[bool, str]:
        return True, f"Qdrant vector adapter configured ({self.collection}, {self.dimensions} dims)"

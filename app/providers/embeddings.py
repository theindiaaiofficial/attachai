"""Embedding providers: deterministic 128-dim local embeddings and OpenAI-compatible embeddings."""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional, Tuple

from app.core.exceptions import ConfigurationError, ProviderError

TOKEN_PATTERN = re.compile(r"[\w\u0900-\u097F]+", re.UNICODE)


class BaseEmbeddingProvider(ABC):
    """Abstract base class for embedding generation."""

    def __init__(self, dimensions: int = 128) -> None:
        if dimensions <= 0:
            raise ConfigurationError("Embedding dimensions must be positive.")
        self.dimensions = dimensions

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        pass

    def embed_query(self, text: str) -> List[float]:
        vectors = self.embed_texts([text or ""])
        return vectors[0]

    @abstractmethod
    def check_health(self) -> Tuple[bool, str]:
        pass


class LocalDeterministicEmbeddingProvider(BaseEmbeddingProvider):
    """
    Canonical 128-dimensional deterministic feature-hashing + character n-gram embedding provider.
    Works across English, Devanagari Hindi, Hinglish, and European scripts without external API keys.
    """

    def __init__(self, dimensions: int = 128) -> None:
        if dimensions != 128:
            raise ConfigurationError(f"LocalDeterministicEmbeddingProvider requires 128 dimensions, got {dimensions}")
        super().__init__(dimensions=128)

    def _embed_single(self, text: str) -> List[float]:
        vec = [0.0] * self.dimensions
        normalized = (text or "").strip().lower()
        if not normalized:
            vec[0] = 1.0
            return vec

        tokens = TOKEN_PATTERN.findall(normalized)
        features: List[Tuple[str, float]] = []
        for tok in tokens:
            features.append((f"tok:{tok}", 2.0))
            if len(tok) >= 3:
                for i in range(len(tok) - 2):
                    features.append((f"tri:{tok[i:i+3]}", 0.75))
        for i in range(len(tokens) - 1):
            features.append((f"bi:{tokens[i]}_{tokens[i+1]}", 1.5))

        if not features:
            features.append((f"raw:{normalized[:32]}", 1.0))

        for feat, weight in features:
            digest = hashlib.sha256(feat.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[idx] += sign * weight

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 1e-9:
            vec = [round(v / norm, 6) for v in vec]
        else:
            vec[0] = 1.0
        return vec

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        results = [self._embed_single(t) for t in texts]
        for vec in results:
            if len(vec) != self.dimensions:
                raise ProviderError(
                    f"Embedding dimension mismatch: expected {self.dimensions}, got {len(vec)}",
                    provider="local-embeddings",
                )
        return results

    def check_health(self) -> Tuple[bool, str]:
        sample = self.embed_query("health check")
        if len(sample) != self.dimensions:
            return False, "Local embedding dimension validation failed"
        return True, f"Local deterministic embeddings active ({self.dimensions} dims)"


class OpenAICompatibleEmbeddingProvider(BaseEmbeddingProvider):
    """External OpenAI-compatible embeddings provider with strict batch dimension validation."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int = 128,
        timeout_ms: int = 15000,
        http_transport: Optional[Callable[[str, dict, dict], Any]] = None,
    ) -> None:
        super().__init__(dimensions=dimensions)
        if not base_url.strip() or not api_key.strip() or not model.strip():
            raise ConfigurationError("OpenAICompatibleEmbeddingProvider requires base_url, api_key, and model.")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = max(1.0, timeout_ms / 1000.0)
        self._http_transport = http_transport

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model, "input": texts}
        try:
            if self._http_transport is not None:
                resp_data = self._http_transport(url, headers, payload)
            else:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise ProviderError(
                "External embeddings provider request failed",
                status_code=503,
                provider="openai-embeddings",
            ) from exc

        items = resp_data.get("data") if isinstance(resp_data, dict) else None
        if not isinstance(items, list) or len(items) != len(texts):
            raise ProviderError(
                "Malformed response from external embeddings provider",
                status_code=502,
                provider="openai-embeddings",
            )

        vectors: List[List[float]] = []
        for item in items:
            vec = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vec, list) or len(vec) != self.dimensions:
                actual = len(vec) if isinstance(vec, list) else "invalid"
                raise ProviderError(
                    f"External embedding vector dimension mismatch: expected {self.dimensions}, got {actual}. "
                    "Never silently truncate or pad vectors.",
                    status_code=502,
                    provider="openai-embeddings",
                )
            vectors.append([float(x) for x in vec])
        return vectors

    def check_health(self) -> Tuple[bool, str]:
        try:
            vec = self.embed_query("ping")
            return len(vec) == self.dimensions, f"External embeddings healthy ({self.dimensions} dims)"
        except Exception as exc:
            return False, f"External embeddings check failed: {exc}"

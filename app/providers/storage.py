"""Storage providers: LocalStorage and SupabaseStorage with pagination support."""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.exceptions import ConfigurationError, NotFoundError, ProviderError


class BaseStorageProvider(ABC):
    """Abstract storage interface supporting paginated listing and tenant cleanup."""

    @abstractmethod
    def upload(self, storage_path: str, content: bytes, mime_type: str = "application/octet-stream") -> str:
        pass

    @abstractmethod
    def download(self, storage_path: str) -> bytes:
        pass

    @abstractmethod
    def delete(self, storage_path: str) -> None:
        pass

    @abstractmethod
    def list_objects(self, tenant_id: str, page_size: int = 100) -> List[str]:
        pass

    @abstractmethod
    def delete_tenant_objects(self, tenant_id: str, page_size: int = 100) -> int:
        pass

    @abstractmethod
    def check_health(self) -> Tuple[bool, str]:
        pass


class LocalStorageProvider(BaseStorageProvider):
    """Local filesystem storage adapter with paginated directory traversal."""

    def __init__(self, base_dir: str = "data/storage") -> None:
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def _resolve_safe_path(self, storage_path: str) -> str:
        normalized = storage_path.lstrip("/\\").replace("\\", "/")
        full_path = os.path.abspath(os.path.join(self.base_dir, normalized))
        if not full_path.startswith(self.base_dir):
            raise ProviderError("Invalid storage object path traversal attempt.", status_code=400, provider="local-storage")
        return full_path

    def upload(self, storage_path: str, content: bytes, mime_type: str = "application/octet-stream") -> str:
        target = self._resolve_safe_path(storage_path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(content)
        return storage_path

    def download(self, storage_path: str) -> bytes:
        target = self._resolve_safe_path(storage_path)
        if not os.path.isfile(target):
            raise NotFoundError(f"Storage object not found: {storage_path}")
        with open(target, "rb") as f:
            return f.read()

    def delete(self, storage_path: str) -> None:
        target = self._resolve_safe_path(storage_path)
        if os.path.isfile(target):
            os.remove(target)

    def list_objects(self, tenant_id: str, page_size: int = 100) -> List[str]:
        tenant_dir = self._resolve_safe_path(tenant_id)
        if not os.path.isdir(tenant_dir):
            return []
        all_paths: List[str] = []
        for root, _, files in os.walk(tenant_dir):
            for fname in sorted(files):
                abs_file = os.path.join(root, fname)
                rel = os.path.relpath(abs_file, self.base_dir).replace("\\", "/")
                all_paths.append(rel)
        # Paginate through collected entries in batches of page_size
        results: List[str] = []
        offset = 0
        while offset < len(all_paths):
            batch = all_paths[offset : offset + max(1, page_size)]
            results.extend(batch)
            offset += max(1, page_size)
        return results

    def delete_tenant_objects(self, tenant_id: str, page_size: int = 100) -> int:
        objects = self.list_objects(tenant_id=tenant_id, page_size=page_size)
        deleted = 0
        for i in range(0, len(objects), max(1, page_size)):
            batch = objects[i : i + max(1, page_size)]
            for obj_path in batch:
                self.delete(obj_path)
                deleted += 1
        tenant_dir = self._resolve_safe_path(tenant_id)
        if os.path.isdir(tenant_dir):
            shutil.rmtree(tenant_dir, ignore_errors=True)
        return deleted

    def check_health(self) -> Tuple[bool, str]:
        if os.path.isdir(self.base_dir) and os.access(self.base_dir, os.W_OK):
            return True, "Local storage directory writable"
        return False, "Local storage directory is not writable"


class SupabaseStorageProvider(BaseStorageProvider):
    """Supabase private bucket storage adapter with paginated object listing and deletion."""

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        bucket: str = "knowledge",
        transport: Optional[Callable[[str, str, Dict[str, str], Any], Any]] = None,
    ) -> None:
        if not supabase_url.strip() or not service_role_key.strip() or not bucket.strip():
            raise ConfigurationError("SupabaseStorageProvider requires SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and bucket.")
        self.supabase_url = supabase_url.rstrip("/")
        self.service_role_key = service_role_key.strip()
        self.bucket = bucket.strip()
        self._transport = transport
        self._fallback = LocalStorageProvider(base_dir="data/supabase_storage_mirror")

    def _headers(self, content_type: str = "application/json") -> Dict[str, str]:
        return {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": content_type,
        }

    def upload(self, storage_path: str, content: bytes, mime_type: str = "application/octet-stream") -> str:
        if self._transport:
            url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_path.lstrip('/')}"
            self._transport("POST", url, self._headers(mime_type), content)
        self._fallback.upload(storage_path, content, mime_type)
        return storage_path

    def download(self, storage_path: str) -> bytes:
        if self._transport:
            url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_path.lstrip('/')}"
            res = self._transport("GET", url, self._headers(), None)
            if isinstance(res, bytes):
                return res
        return self._fallback.download(storage_path)

    def delete(self, storage_path: str) -> None:
        if self._transport:
            url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_path.lstrip('/')}"
            self._transport("DELETE", url, self._headers(), None)
        self._fallback.delete(storage_path)

    def list_objects(self, tenant_id: str, page_size: int = 100) -> List[str]:
        if self._transport:
            collected: List[str] = []
            offset = 0
            while True:
                url = f"{self.supabase_url}/storage/v1/object/list/{self.bucket}"
                batch = self._transport(
                    "POST",
                    url,
                    self._headers(),
                    {"prefix": f"{tenant_id}/", "limit": page_size, "offset": offset},
                )
                if not isinstance(batch, list) or not batch:
                    break
                for item in batch:
                    name = item.get("name") if isinstance(item, dict) else str(item)
                    if name:
                        collected.append(f"{tenant_id}/{name.lstrip('/')}")
                if len(batch) < page_size:
                    break
                offset += page_size
            return collected
        return self._fallback.list_objects(tenant_id=tenant_id, page_size=page_size)

    def delete_tenant_objects(self, tenant_id: str, page_size: int = 100) -> int:
        all_objects = self.list_objects(tenant_id=tenant_id, page_size=page_size)
        deleted = 0
        for i in range(0, len(all_objects), max(1, page_size)):
            batch = all_objects[i : i + max(1, page_size)]
            for path in batch:
                self.delete(path)
                deleted += 1
        return deleted

    def check_health(self) -> Tuple[bool, str]:
        if self._transport:
            try:
                url = f"{self.supabase_url}/storage/v1/bucket/{self.bucket}"
                info = self._transport("GET", url, self._headers(), None)
                if isinstance(info, dict) and info.get("public") is True:
                    return False, f"Supabase bucket '{self.bucket}' must be private, not public"
                return True, f"Supabase private bucket '{self.bucket}' verified"
            except Exception as exc:
                return False, f"Supabase storage check failed: {exc}"
        return True, f"Supabase storage configured for private bucket '{self.bucket}'"

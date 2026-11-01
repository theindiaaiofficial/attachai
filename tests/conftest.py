"""Shared test fixtures and isolated application builder."""

from __future__ import annotations

import shutil
import tempfile
from typing import Tuple

from app.core.config import Settings
from app.core.dependencies import ServiceContainer
from app.main import OrbitApplication, OrbitTestClient


class IsolatedOrbitTestEnv:
    """Provides a hermetic temporary SQLite + LocalStorage + LocalVector test environment."""

    def __init__(self, **setting_overrides: object) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="orbit_test_")
        base_kwargs = {
            "app_env": "development",
            "admin_api_key": "test-admin-secret-key-999",
            "database_provider": "sqlite",
            "storage_provider": "local",
            "vector_provider": "local",
            "sqlite_path": ":memory:",
            "local_storage_dir": f"{self.temp_dir}/storage",
            "embedding_provider": "local",
            "embedding_dimensions": 128,
            "supabase_vector_dimensions": 128,
            "llm_provider_type": "local",
            "llm_model": "orbit-local-v1",
            "notification_provider": "outbox",
            "rate_limit_public_per_minute": 120,
            "rate_limit_admin_per_minute": 240,
        }
        base_kwargs.update(setting_overrides)
        self.settings = Settings(**base_kwargs)  # type: ignore[arg-type]
        self.settings.validate()
        self.container = ServiceContainer(settings=self.settings)
        self.app = OrbitApplication(container=self.container)
        self.client = OrbitTestClient(self.app)

    @property
    def admin_headers(self) -> dict[str, str]:
        return {"x-admin-api-key": self.settings.admin_api_key}

    def create_sample_tenant(
        self,
        name: str = "Acme Fitness",
        slug: str = "acme-fitness",
        domains: list[str] | None = None,
    ) -> Tuple[dict, str]:
        resp = self.client.post(
            "/admin/api/tenants",
            headers=self.admin_headers,
            json={
                "businessName": name,
                "slug": slug,
                "assistantName": f"{name} Assistant",
                "companyName": name,
                "domains": domains or ["example.com"],
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        return data["tenant"], data["apiKey"]

    def cleanup(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

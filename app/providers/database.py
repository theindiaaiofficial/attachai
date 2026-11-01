"""Database provider factory."""

from __future__ import annotations

from typing import Any, Optional

from app.core.config import Settings
from app.repositories.base import BaseRepository
from app.repositories.sqlite import SQLiteRepository
from app.repositories.supabase import SupabaseRepository


def create_database_repository(settings: Settings, http_transport: Optional[Any] = None) -> BaseRepository:
    if settings.database_provider == "supabase":
        repo: BaseRepository = SupabaseRepository(
            supabase_url=settings.supabase_url,
            service_role_key=settings.supabase_service_role_key,
            vector_dimensions=settings.supabase_vector_dimensions,
            http_transport=http_transport,
        )
    else:
        repo = SQLiteRepository(db_path=settings.sqlite_path)
    repo.initialize()
    return repo

"""Application lifespan management for Orbit AI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from app.core.dependencies import ServiceContainer


@asynccontextmanager
async def orbit_lifespan(app: Any) -> AsyncGenerator[None, None]:
    container: ServiceContainer = getattr(app, "container", None) or ServiceContainer()
    app.container = container
    container.logger.info("orbit_ai.startup", environment=container.settings.app_env)
    try:
        yield
    finally:
        container.logger.info("orbit_ai.shutdown")

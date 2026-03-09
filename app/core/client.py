"""
HTTP client dependency injection.
Mirrors app/core/client.py from the architecture diagram.
"""

from __future__ import annotations

from typing import AsyncGenerator

import httpx
import structlog
from fastapi import Depends

from app.core.database import DatabaseManager, db_manager
from app.core.ollama_client import OllamaManager, ollama_manager
from app.core.polygon_client import PolygonManager, polygon_manager

logger = structlog.get_logger(__name__)


class ServiceContainer:
    """Dependency injection container for all services."""

    def __init__(
        self,
        db: DatabaseManager,
        llm: OllamaManager,
        polygon: PolygonManager,
    ):
        self.db = db
        self.llm = llm
        self.polygon = polygon


async def get_services() -> ServiceContainer:
    """FastAPI dependency — provides access to all initialized services."""
    return ServiceContainer(
        db=db_manager,
        llm=ollama_manager,
        polygon=polygon_manager,
    )


async def get_http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide a short-lived HTTP client for one-off requests."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client

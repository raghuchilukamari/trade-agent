"""
HTTP client dependency injection.
"""

from __future__ import annotations

from typing import AsyncGenerator

import httpx
import structlog

from app.core.database import DatabaseManager, db_manager

logger = structlog.get_logger(__name__)


class ServiceContainer:
    """Dependency injection container for all services."""

    def __init__(self, db: DatabaseManager):
        self.db = db


async def get_services() -> ServiceContainer:
    """FastAPI dependency — provides access to all initialized services."""
    return ServiceContainer(db=db_manager)


async def get_http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide a short-lived HTTP client for one-off requests."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client

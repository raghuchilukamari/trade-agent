"""Health check endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter

from app.core.database import db_manager
from app.core.ollama_client import ollama_manager
from app.core.polygon_client import polygon_manager
from app.schema.models import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])

_start_time = time.time()


@router.get("", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        services={
            #"database": db_manager._engine is not None,
            "ollama": ollama_manager.is_available,
            "polygon": polygon_manager.is_available,
        },
        uptime_seconds=round(time.time() - _start_time, 2),
    )

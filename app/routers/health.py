"""Health check endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter

from app.core.database import db_manager
from app.schema.models import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])

_start_time = time.time()


@router.get("", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        version="2.0.0",
        services={
            "database": db_manager._pool is not None,
        },
        uptime_seconds=round(time.time() - _start_time, 2),
    )

"""
Router registry — returns list of router factories.
Mirrors app/routers/get_routers.py from the architecture diagram.
"""

from __future__ import annotations

from fastapi import APIRouter


def get_routers() -> list[APIRouter]:
    """Returns all API routers to be registered on the FastAPI app."""
    from app.routers.analysis import router as analysis_router
    from app.routers.dashboard import router as dashboard_router
    from app.routers.health import router as health_router
    from app.routers.market import router as market_router
    from app.routers.websocket import router as ws_router

    return [
        health_router,
        analysis_router,
        market_router,
        dashboard_router,
        ws_router,
    ]

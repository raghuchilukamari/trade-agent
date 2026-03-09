"""
Trading Agent — FastAPI Application Entry Point

Architecture:
  User Request → FastAPI (main.py) → API Router → LangGraph StateGraph
  → Parallel Nodes (tools_check, intent_classification, analysis)
  → EdgeRouter (edge_router.py) → Sequential Nodes (generate_response)
  → Local LLM (Ollama) → Response
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import db_manager
from app.core.error_handling import mount_error_handling
from app.core.ollama_client import ollama_manager
from app.core.polygon_client import polygon_manager
from app.routers.get_routers import get_routers
from config.settings import settings

logger = structlog.get_logger(__name__)

PROJECT_NAME = "Trading Analysis Agent"
VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan — initialize and teardown shared resources.
    Mirrors the LIFESPAN pattern from Raghu's architecture diagram.
    """
    logger.info("starting_trading_agent", version=VERSION, env=settings.app_env)

    # ── Startup: initialize connections in parallel ──
    await asyncio.gather(
        db_manager.initialize(),
        ollama_manager.initialize(),
        polygon_manager.initialize(),
    )

    logger.info("all_services_initialized")
    yield

    # ── Shutdown: graceful teardown ──
    logger.info("shutting_down_trading_agent")
    await asyncio.gather(
        db_manager.shutdown(),
        ollama_manager.shutdown(),
        polygon_manager.shutdown(),
    )
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    """Factory function to create the FastAPI application."""
    app = FastAPI(
        title=PROJECT_NAME,
        version=VERSION,
        description="AI-powered options flow analysis with Agent-to-Agent architecture",
        lifespan=lifespan,
    )

    # ── CORS for dashboard integration ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Error handling (app/core/error_handling.py) ──
    mount_error_handling(app)

    # ── Register all routers (app/routers/get_routers.py) ──
    for router in get_routers():
        app.include_router(router)

    return app


app = create_app()


@app.get("/")
async def root():
    return {
        "service": PROJECT_NAME,
        "version": VERSION,
        "status": "operational",
        "agents": [
            "flow_analyst",
            "news_analyst",
            "opex_analyst",
            "coordinator",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        workers=1,  # Single worker — LangGraph manages concurrency internally
        log_level=settings.log_level.lower(),
    )

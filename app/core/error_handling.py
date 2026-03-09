"""
Error handling — registers exception handlers on the FastAPI app.
Mirrors app/core/error_handling.py from the architecture diagram.
"""

from __future__ import annotations

import traceback

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)


class AgentError(Exception):
    """Base exception for agent pipeline errors."""

    def __init__(self, message: str, agent: str | None = None, details: dict | None = None):
        self.message = message
        self.agent = agent
        self.details = details or {}
        super().__init__(message)


class FlowDataError(AgentError):
    """Error parsing or processing flow CSV data."""
    pass


class LLMError(AgentError):
    """Error communicating with Ollama LLM."""
    pass


class PolygonError(AgentError):
    """Error from Polygon.io API."""
    pass


class PipelineTimeoutError(AgentError):
    """Agent pipeline exceeded timeout."""
    pass


def mount_error_handling(app: FastAPI) -> None:
    """Register exception handlers on the FastAPI app."""

    @app.exception_handler(AgentError)
    async def agent_error_handler(request: Request, exc: AgentError) -> JSONResponse:
        logger.error(
            "agent_error",
            agent=exc.agent,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "agent_error",
                "message": exc.message,
                "agent": exc.agent,
                "details": exc.details,
            },
        )

    @app.exception_handler(FlowDataError)
    async def flow_data_error_handler(request: Request, exc: FlowDataError) -> JSONResponse:
        logger.error("flow_data_error", message=exc.message)
        return JSONResponse(
            status_code=422,
            content={"error": "flow_data_error", "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled_error",
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "An unexpected error occurred."},
        )

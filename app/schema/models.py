"""
Pydantic models for API request/response validation.
"""

from __future__ import annotations

from datetime import date
from pydantic import BaseModel, Field

class HealthResponse(BaseModel):
    """Service health check response."""
    status: str
    version: str
    services: dict[str, bool]
    uptime_seconds: float

class QuickStats(BaseModel):
    """
    Schema for high-level options flow statistics for a specific date.
    Used by FlowParser to provide a snapshot of market activity.
    """
    target_date: date = Field(..., description="The trading date for the stats")
    total_premium_m: float = Field(
        default=0.0,
        description="Total premium in millions of USD"
    )
    golden_sweeps_count: int = Field(
        default=0,
        description="Count of high-conviction golden sweep entries"
    )
    total_sweeps_count: int = Field(
        default=0,
        description="Count of standard sweep entries"
    )
    sexy_flow_count: int = Field(
        default=0,
        description="Count of entries from sexy-flow source"
    )
    trady_flow_count: int = Field(
        default=0,
        description="Count of entries from trady-flow source"
    )
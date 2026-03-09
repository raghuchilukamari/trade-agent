"""
Pydantic models for API request/response validation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Requests ─────────────────────────────────────────────────────────────────

class RunAnalysisRequest(BaseModel):
    """Trigger a daily analysis pipeline run."""
    target_date: date = Field(default_factory=date.today)
    analysis_type: Literal["weekday", "weekend"] = "weekday"
    flow_data_dir: str | None = None  # Override default path
    prior_summary_path: str | None = None
    force_rerun: bool = False


class ChatRequest(BaseModel):
    """Send a conversational query to the trading agent."""
    message: str
    context: dict[str, Any] | None = None
    session_id: str | None = None


class TickerLookupRequest(BaseModel):
    """Look up a specific ticker's flow + news data."""
    symbol: str
    target_date: date = Field(default_factory=date.today)
    include_price: bool = True
    include_options: bool = False


class WatchlistUpdateRequest(BaseModel):
    """Update the active watchlist."""
    additions: list[dict[str, str]] = []   # [{"symbol": "AAPL", "category": "WATCH", "notes": "..."}]
    removals: list[str] = []                # ["INTC", "BABA"]
    category_changes: list[dict[str, str]] = []  # [{"symbol": "MU", "category": "ADD"}]


# ── Responses ────────────────────────────────────────────────────────────────

class AnalysisStatus(BaseModel):
    """Status of an analysis pipeline run."""
    status: Literal["pending", "running", "completed", "failed"]
    target_date: date
    analysis_type: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    docx_path: str | None = None
    error: str | None = None


class QuickStats(BaseModel):
    """Quick market + flow statistics."""
    target_date: date
    total_premium_m: float
    golden_sweeps_count: int
    total_sweeps_count: int
    sexy_flow_count: int
    trady_flow_count: int
    top_ticker: str | None = None
    top_premium: str | None = None
    market_status: str | None = None


class TickerFlowSummary(BaseModel):
    """Summary of flow activity for a single ticker."""
    symbol: str
    total_premium_usd: float
    call_premium_usd: float
    put_premium_usd: float
    call_count: int
    put_count: int
    max_vol_oi: float | None = None
    sources: list[str]
    current_price: float | None = None
    deep_itm_flags: list[str] = []


class ChatResponse(BaseModel):
    """Response from the conversational agent."""
    response: str
    sources: list[str] = []
    suggested_actions: list[str] = []
    session_id: str | None = None


class HealthResponse(BaseModel):
    """Service health check response."""
    status: str
    version: str
    services: dict[str, bool]
    uptime_seconds: float

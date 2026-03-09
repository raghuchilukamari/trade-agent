"""
Agent state definitions for LangGraph workflows.

Mirrors app/schema/state.py from the architecture diagram:
  AgentState(TypedDict):
    messages: Sequence[BaseMessage]
    next_action: Optional[str]
    iteration_count: int
    context: Optional[Dict]
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Sequence

from langchain_core.messages import BaseMessage
from typing_extensions import Annotated, TypedDict

# ── Operator for message accumulation ────────────────────────────────────────


def add_messages(existing: Sequence[BaseMessage], new: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Accumulate messages across graph nodes."""
    return list(existing) + list(new)


# ── Core Agent State ─────────────────────────────────────────────────────────


class AgentState(TypedDict):
    """
    Central state object flowing through the LangGraph StateGraph.
    All agent nodes read from and write to this state.
    """

    # Message history (accumulated across nodes)
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Routing control
    next_action: str | None  # Which node to execute next
    iteration_count: int  # Safety counter to prevent infinite loops

    # Pipeline context
    context: PipelineContext | None

    # Individual agent results (populated by each agent node)
    flow_analysis: FlowAnalysisResult | None
    news_analysis: NewsAnalysisResult | None
    opex_analysis: OpexAnalysisResult | None

    # Final coordinated output
    final_report: FinalReport | None

    # Error tracking
    errors: list[str]


# ── Pipeline Context ─────────────────────────────────────────────────────────


class PipelineContext(TypedDict):
    """Input context for the analysis pipeline."""

    target_date: str  # YYYY-MM-DD
    analysis_type: Literal["weekday", "weekend"]
    flow_data_dir: str
    prior_summary_path: str | None

    # Loaded data (populated by data ingestion node)
    flow_entries: list[dict[str, Any]] | None
    news_entries: list[dict[str, Any]] | None
    golden_sweeps: list[dict[str, Any]] | None
    sweeps: list[dict[str, Any]] | None
    sexy_flow: list[dict[str, Any]] | None
    trady_flow: list[dict[str, Any]] | None

    # Market prices (populated by polygon tools)
    live_prices: dict[str, float] | None


# ── Agent Result Types ───────────────────────────────────────────────────────


class TickerVerdict(TypedDict):
    symbol: str
    marks: list[str]  # ["⭐", "🔥", "📈"]
    verdict: Literal["BULLISH", "BEARISH", "MIXED"]
    news_summary: str
    news_sentiment: float
    flow_summary: str
    flow_premium_usd: float
    alignment: Literal["ALIGNED", "DIVERGENT"]
    reasoning: str


class FlowAnalysisResult(TypedDict):
    """Output from the Flow Analyst agent."""
    ticker_verdicts: list[TickerVerdict]
    top_10_trades: list[dict[str, Any]]
    notable_flow: dict[str, list[dict[str, Any]]]  # By category
    total_premium_m: float
    flow_stats: dict[str, int]  # Counts by source
    vol_oi_outliers: list[dict[str, Any]]


class GeopoliticalItem(TypedDict):
    topic: str
    summary: str
    sentiment: Literal["BULLISH", "BEARISH"]
    score: float


class NewsAnalysisResult(TypedDict):
    """Output from the News Analyst agent."""
    geopolitical_bullish: list[GeopoliticalItem]
    geopolitical_bearish: list[GeopoliticalItem]
    market_implications: dict[str, str]  # sector -> implication
    policy_headlines: list[str]
    sector_momentum: dict[str, str]


class OpexAnalysisResult(TypedDict):
    """Output from the OPEX Analyst agent."""
    next_monthly_opex: str
    days_to_opex: int
    current_phase: Literal["pre_opex", "opex_week", "post_opex"]
    phase_label: str
    phase_implications: list[str]
    high_oi_strikes: list[dict[str, Any]]
    vix_expiration: str | None
    vix_days_away: int | None
    is_quad_witching: bool
    gamma_assessment: str


class WatchlistEntry(TypedDict):
    symbol: str
    category: Literal["HOLD", "ADD", "WATCH", "DOWNGRADE"]
    marks: list[str]
    notes: str


class RiskAssessment(TypedDict):
    category: str
    level: Literal["LOW", "MODERATE", "ELEVATED", "HIGH"]
    description: str


class FinalReport(TypedDict):
    """Coordinated output from the Coordinator agent."""
    executive_summary: str
    task1_correlation: list[TickerVerdict]
    task2_geopolitical: NewsAnalysisResult
    task3_top_trades: list[dict[str, Any]]
    task4_opex: OpexAnalysisResult
    watchlist: list[WatchlistEntry]
    risk_assessment: list[RiskAssessment]
    action_items: list[str]
    sources: list[str]

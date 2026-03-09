"""
Analysis router — triggers and manages daily analysis pipeline runs.
"""

from __future__ import annotations

import asyncio
from datetime import date

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.core.client import ServiceContainer, get_services
from app.schema.models import (
    AnalysisStatus,
    ChatRequest,
    ChatResponse,
    QuickStats,
    RunAnalysisRequest,
    TickerFlowSummary,
    TickerLookupRequest,
)
from app.workers.daily_pipeline import DailyPipeline

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])

# In-memory status tracking (replace with Redis/DB for production)
_pipeline_status: dict[str, AnalysisStatus] = {}


@router.post("/run", response_model=AnalysisStatus)
async def run_analysis(
    request: RunAnalysisRequest,
    background_tasks: BackgroundTasks,
    services: ServiceContainer = Depends(get_services),
):
    """
    Trigger a daily analysis pipeline run.
    Executes in background — poll /status/{date} for progress.
    """
    date_key = request.target_date.isoformat()

    if date_key in _pipeline_status and _pipeline_status[date_key].status == "running":
        raise HTTPException(409, f"Analysis already running for {date_key}")

    status = AnalysisStatus(
        status="pending",
        target_date=request.target_date,
        analysis_type=request.analysis_type,
    )
    _pipeline_status[date_key] = status

    pipeline = DailyPipeline(services)
    background_tasks.add_task(
        _execute_pipeline, pipeline, request, date_key
    )

    return status


async def _execute_pipeline(
    pipeline: DailyPipeline,
    request: RunAnalysisRequest,
    date_key: str,
):
    """Background task that executes the full LangGraph pipeline."""
    from datetime import datetime

    _pipeline_status[date_key].status = "running"
    _pipeline_status[date_key].started_at = datetime.utcnow()

    try:
        result = await pipeline.execute(
            target_date=request.target_date,
            analysis_type=request.analysis_type,
            flow_data_dir=request.flow_data_dir,
            prior_summary_path=request.prior_summary_path,
        )
        _pipeline_status[date_key].status = "completed"
        _pipeline_status[date_key].completed_at = datetime.utcnow()
        _pipeline_status[date_key].docx_path = result.get("docx_path")
    except Exception as e:
        logger.error("pipeline_failed", date=date_key, error=str(e))
        _pipeline_status[date_key].status = "failed"
        _pipeline_status[date_key].error = str(e)


@router.get("/status/{target_date}", response_model=AnalysisStatus)
async def get_analysis_status(target_date: date):
    """Check the status of an analysis pipeline run."""
    date_key = target_date.isoformat()
    if date_key not in _pipeline_status:
        raise HTTPException(404, f"No analysis found for {date_key}")
    return _pipeline_status[date_key]


@router.get("/quick-stats/{target_date}", response_model=QuickStats)
async def get_quick_stats(
    target_date: date,
    services: ServiceContainer = Depends(get_services),
):
    """Get quick statistics for a given trading date."""
    from app.services.flow_parser import FlowParser

    parser = FlowParser(services.db)
    stats = await parser.get_quick_stats(target_date)
    return stats


@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(
    request: ChatRequest,
    services: ServiceContainer = Depends(get_services),
):
    """
    Conversational interface to the trading agent.
    Supports natural language queries about flow, OPEX, watchlist, etc.
    """
    from app.agents.coordinator.graph import build_chat_graph

    graph = build_chat_graph(services)
    result = await graph.ainvoke({
        "messages": [{"role": "user", "content": request.message}],
        "context": request.context,
    })

    return ChatResponse(
        response=result.get("response", ""),
        sources=result.get("sources", []),
        suggested_actions=result.get("suggested_actions", []),
        session_id=request.session_id,
    )


@router.get("/ticker/{symbol}", response_model=TickerFlowSummary)
async def get_ticker_flow(
    symbol: str,
    target_date: date = None,
    services: ServiceContainer = Depends(get_services),
):
    """Get flow summary for a specific ticker."""
    target_date = target_date or date.today()
    from app.services.flow_parser import FlowParser

    parser = FlowParser(services.db)
    summary = await parser.get_ticker_summary(symbol.upper(), target_date)
    if not summary:
        raise HTTPException(404, f"No flow data for {symbol} on {target_date}")
    return summary


@router.get("/history", response_model=list[dict])
async def get_analysis_history(
    days: int = 10,
    services: ServiceContainer = Depends(get_services),
):
    """Get recent analysis tracker history."""
    return await services.db.get_recent_tracker(days)

"""
Coordinator Agent — Main LangGraph StateGraph orchestrator.

Architecture (from sequence diagram):
  User Request → FastAPI → API Router → LangGraph StateGraph
  → AgentState initialization
  → Parallel Nodes (tools_check, intent_classification, flow_analysis, news_analysis)
  → EdgeRouter (edge_router.py routing logic)
  → Sequential Nodes (opex_analysis, generate_response)
  → Local LLM (Ollama) → Response

This module builds two graphs:
  1. build_analysis_graph() — Full daily analysis pipeline (4 tasks)
  2. build_chat_graph() — Conversational trading assistant
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.core.client import ServiceContainer
from app.schema.state import AgentState, PipelineContext

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYSIS PIPELINE GRAPH
# ═══════════════════════════════════════════════════════════════════════════════


def build_analysis_graph(services: ServiceContainer) -> StateGraph:
    """
    Build the full daily analysis LangGraph pipeline.

    Node execution order:
      1. ingest_data (load CSVs + news)
      2. fetch_prices (Polygon API — parallel with ingest in future)
      3. [PARALLEL] flow_analysis + news_analysis
      4. opex_analysis
      5. coordinate_results (LLM synthesis)
      6. generate_report (docx creation)
    """

    graph = StateGraph(AgentState)

    # ── Define Nodes ─────────────────────────────────────────────────────

    graph.add_node("ingest_data", _node_ingest_data(services))
    graph.add_node("fetch_prices", _node_fetch_prices(services))
    graph.add_node("flow_analysis", _node_flow_analysis(services))
    graph.add_node("news_analysis", _node_news_analysis(services))
    graph.add_node("opex_analysis", _node_opex_analysis(services))
    graph.add_node("coordinate_results", _node_coordinate(services))
    graph.add_node("generate_report", _node_generate_report(services))
    graph.add_node("save_to_db", _node_save_to_db(services))

    # ── Define Edges ─────────────────────────────────────────────────────

    graph.set_entry_point("ingest_data")
    graph.add_edge("ingest_data", "fetch_prices")
    graph.add_edge("fetch_prices", "flow_analysis")
    graph.add_edge("fetch_prices", "news_analysis")
    graph.add_edge("flow_analysis", "opex_analysis")
    graph.add_edge("news_analysis", "opex_analysis")
    graph.add_edge("opex_analysis", "coordinate_results")
    graph.add_edge("coordinate_results", "generate_report")
    graph.add_edge("generate_report", "save_to_db")
    graph.add_edge("save_to_db", END)

    return graph.compile()


# ── Node Factories ───────────────────────────────────────────────────────────


def _node_ingest_data(services: ServiceContainer):
    """Node: Load all CSV data for the target date."""

    async def ingest(state: AgentState) -> dict:
        from app.services.flow_parser import (
            load_all_flow,
            load_golden_sweeps,
            load_sexy_flow,
            load_sweeps,
            load_trady_flow,
            load_walter_news,
        )
        from pathlib import Path

        ctx = state["context"]
        target_date = ctx["target_date"]
        data_dir = Path(ctx["flow_data_dir"])

        logger.info("ingesting_data", date=target_date, dir=str(data_dir))

        if ctx["analysis_type"] == "weekday":
            flow_entries = load_all_flow(data_dir, target_date)
            golden = load_golden_sweeps(data_dir, target_date)
            sweeps = load_sweeps(data_dir, target_date)
            sexy = load_sexy_flow(data_dir, target_date)
            trady = load_trady_flow(data_dir, target_date)
        else:
            flow_entries = []
            golden = sweeps = sexy = trady = []

        news_entries = load_walter_news(data_dir, target_date)

        # Store in DB
        if flow_entries:
            await services.db.insert_flow_entries(flow_entries)
        if news_entries:
            await services.db.insert_news_entries(news_entries)

        # Update context
        ctx["flow_entries"] = flow_entries
        ctx["news_entries"] = news_entries
        ctx["golden_sweeps"] = golden
        ctx["sweeps"] = sweeps
        ctx["sexy_flow"] = sexy
        ctx["trady_flow"] = trady

        logger.info(
            "data_ingested",
            flow_count=len(flow_entries),
            news_count=len(news_entries),
        )

        return {
            "context": ctx,
            "messages": [AIMessage(content=f"Data ingested: {len(flow_entries)} flow, {len(news_entries)} news")],
        }

    return ingest


def _node_fetch_prices(services: ServiceContainer):
    """Node: Fetch current prices from Polygon for Deep ITM Rule."""

    async def fetch(state: AgentState) -> dict:
        ctx = state["context"]
        flow_entries = ctx.get("flow_entries", [])

        # Extract unique symbols
        symbols = list({e["symbol"] for e in flow_entries if e.get("symbol")})

        if symbols and services.polygon.is_available:
            logger.info("fetching_prices", count=len(symbols))
            prices = await services.polygon.get_batch_prices(symbols[:50])  # API rate limit
            ctx["live_prices"] = prices
            logger.info("prices_fetched", count=len(prices))
        else:
            ctx["live_prices"] = {}

        return {"context": ctx}

    return fetch


def _node_flow_analysis(services: ServiceContainer):
    """Node: Run Flow Analyst agent (Task 1 + Task 3)."""

    async def analyze(state: AgentState) -> dict:
        from app.agents.flow_analyst.agent import FlowAnalystAgent

        agent = FlowAnalystAgent(services)
        result = await agent.analyze(state["context"])

        return {
            "flow_analysis": result,
            "messages": [AIMessage(content="Flow analysis complete")],
        }

    return analyze


def _node_news_analysis(services: ServiceContainer):
    """Node: Run News Analyst agent (Task 2)."""

    async def analyze(state: AgentState) -> dict:
        from app.agents.news_analyst.agent import NewsAnalystAgent

        agent = NewsAnalystAgent(services)
        result = await agent.analyze(state["context"])

        return {
            "news_analysis": result,
            "messages": [AIMessage(content="News analysis complete")],
        }

    return analyze


def _node_opex_analysis(services: ServiceContainer):
    """Node: Run OPEX Analyst agent (Task 4)."""

    async def analyze(state: AgentState) -> dict:
        from app.agents.opex_analyst.agent import OpexAnalystAgent

        agent = OpexAnalystAgent(services)
        result = await agent.analyze(state["context"])

        return {
            "opex_analysis": result,
            "messages": [AIMessage(content="OPEX analysis complete")],
        }

    return analyze


def _node_coordinate(services: ServiceContainer):
    """Node: Coordinate all agent results into a unified report using LLM."""

    async def coordinate(state: AgentState) -> dict:
        flow = state.get("flow_analysis")
        news = state.get("news_analysis")
        opex = state.get("opex_analysis")
        ctx = state["context"]

        # Build executive summary via LLM
        summary_prompt = _build_summary_prompt(flow, news, opex, ctx)

        if services.llm.is_available:
            executive_summary = await services.llm.chat(
                messages=[{"role": "user", "content": summary_prompt}],
                system=(
                    "You are an elite institutional equity research analyst. "
                    "Write a concise 2-3 sentence executive summary of today's "
                    "trading analysis. Be specific about key signals and actionable."
                ),
                temperature=0.2,
                max_tokens=512,
            )
        else:
            executive_summary = "Executive summary unavailable — LLM offline."

        # Build watchlist updates
        watchlist = _build_watchlist(flow, news)

        # Build risk assessment
        risk = _build_risk_assessment(flow, news, opex)

        final_report = {
            "executive_summary": executive_summary,
            "task1_correlation": flow.get("ticker_verdicts", []) if flow else [],
            "task2_geopolitical": news if news else {},
            "task3_top_trades": flow.get("top_10_trades", []) if flow else [],
            "task4_opex": opex if opex else {},
            "watchlist": watchlist,
            "risk_assessment": risk,
            "action_items": _generate_action_items(flow, news, opex),
            "sources": ["walter_openai.csv", "golden-sweeps.csv", "sweeps.csv",
                        "sexy-flow.csv", "trady-flow.csv", "Polygon.io"],
        }

        return {
            "final_report": final_report,
            "messages": [AIMessage(content="Coordination complete")],
        }

    return coordinate


def _node_generate_report(services: ServiceContainer):
    """Node: Generate the DOCX report."""

    async def generate(state: AgentState) -> dict:
        from app.workers.report_generator import generate_docx

        report = state.get("final_report")
        ctx = state["context"]

        if report:
            docx_path = await generate_docx(report, ctx)
            report["docx_path"] = docx_path
            logger.info("report_generated", path=docx_path)
        else:
            logger.warning("no_report_to_generate")

        return {"final_report": report}

    return generate


def _node_save_to_db(services: ServiceContainer):
    """Node: Persist analysis results and tracker entry to database."""

    async def save(state: AgentState) -> dict:
        report = state.get("final_report")
        ctx = state["context"]

        if report:
            # Save analysis result
            await services.db.save_analysis_result({
                "date": ctx["target_date"],
                "analysis_type": ctx["analysis_type"],
                "task1_json": json.dumps(report.get("task1_correlation", [])),
                "task2_json": json.dumps(report.get("task2_geopolitical", {})),
                "task3_json": json.dumps(report.get("task3_top_trades", [])),
                "task4_json": json.dumps(report.get("task4_opex", {})),
                "executive_summary": report.get("executive_summary"),
                "watchlist_json": json.dumps(report.get("watchlist", [])),
                "risk_json": json.dumps(report.get("risk_assessment", [])),
                "docx_path": report.get("docx_path"),
            })

            # Save tracker entry
            flow = state.get("flow_analysis", {})
            await services.db.save_tracker_entry({
                "date": ctx["target_date"],
                "day_of_week": datetime.strptime(ctx["target_date"], "%Y-%m-%d").strftime("%A"),
                "flow_stats": json.dumps(flow.get("flow_stats", {})) if flow else None,
                "top_sweeps": json.dumps(flow.get("top_10_trades", [])[:5]) if flow else None,
                "vol_oi_outliers": json.dumps(flow.get("vol_oi_outliers", [])) if flow else None,
                "notes": report.get("executive_summary", ""),
            })

            logger.info("results_saved_to_db", date=ctx["target_date"])

        return {"messages": [AIMessage(content="Results saved to database")]}

    return save


# ═══════════════════════════════════════════════════════════════════════════════
# CHAT GRAPH (Conversational Agent)
# ═══════════════════════════════════════════════════════════════════════════════


def build_chat_graph(services: ServiceContainer):
    """Build a simple conversational graph for trading Q&A."""

    async def process_chat(state: dict) -> dict:
        messages = state.get("messages", [])
        user_msg = messages[-1]["content"] if messages else ""

        system = (
            "You are an expert trading analysis assistant. You have deep knowledge of "
            "options flow analysis, OPEX mechanics, institutional positioning, and technical "
            "analysis. Answer questions about market conditions, flow data, OPEX timing, "
            "and trading strategy. Be specific and actionable. Reference the Deep ITM Rule "
            "when discussing put flow."
        )

        if services.llm.is_available:
            response = await services.llm.chat(
                messages=[{"role": "user", "content": user_msg}],
                system=system,
            )
        else:
            response = "LLM is currently offline. Please check Ollama status."

        return {
            "response": response,
            "sources": [],
            "suggested_actions": [],
        }

    return process_chat


# ── Helper Functions ─────────────────────────────────────────────────────────


def _build_summary_prompt(flow, news, opex, ctx) -> str:
    parts = [f"Date: {ctx['target_date']}, Analysis: {ctx['analysis_type']}"]

    if flow:
        stats = flow.get("flow_stats", {})
        parts.append(f"Total flow premium: ${stats.get('total_premium_m', 0):.2f}M")
        top = flow.get("top_10_trades", [])[:3]
        if top:
            top_str = ", ".join(
                f"{t.get('symbol', '?')} ({t.get('premium_formatted', '?')})"
                for t in top
            )
            parts.append(f"Top trades: {top_str}")

    if news:
        geo_b = len(news.get("geopolitical_bullish", []))
        geo_bear = len(news.get("geopolitical_bearish", []))
        parts.append(f"Geopolitical: {geo_b} bullish, {geo_bear} bearish signals")

    if opex:
        parts.append(f"OPEX: {opex.get('phase_label', 'unknown')} — {opex.get('gamma_assessment', '')}")

    return "\n".join(parts)


def _build_watchlist(flow, news) -> list[dict]:
    """Build updated watchlist from analysis results."""
    from app.services.watchlist import get_ticker_marks
    watchlist = []
    if flow and flow.get("ticker_verdicts"):
        for v in flow["ticker_verdicts"]:
            category = "HOLD" if v.get("verdict") == "BULLISH" else "WATCH"
            watchlist.append({
                "symbol": v["symbol"],
                "category": category,
                "marks": get_ticker_marks(v["symbol"]),
                "notes": v.get("reasoning", ""),
            })
    return watchlist


def _build_risk_assessment(flow, news, opex) -> list[dict]:
    """Build risk assessment from all agent outputs."""
    risks = []

    if opex:
        phase = opex.get("current_phase", "")
        if phase == "opex_week":
            risks.append({"category": "OPEX", "level": "HIGH", "description": opex.get("gamma_assessment", "")})
        elif phase == "pre_opex" and opex.get("days_to_opex", 99) <= 5:
            risks.append({"category": "OPEX", "level": "ELEVATED", "description": opex.get("gamma_assessment", "")})

    if news:
        bearish_count = len(news.get("geopolitical_bearish", []))
        if bearish_count >= 3:
            risks.append({"category": "Geopolitical", "level": "HIGH", "description": f"{bearish_count} bearish signals"})
        elif bearish_count >= 1:
            risks.append({"category": "Geopolitical", "level": "MODERATE", "description": f"{bearish_count} bearish signals"})

    return risks


def _generate_action_items(flow, news, opex) -> list[str]:
    """Generate actionable items from analysis."""
    items = []

    if opex:
        phase = opex.get("current_phase", "")
        if phase == "post_opex":
            items.append("Post-OPEX gamma release — best window for new directional positions")
        elif phase == "opex_week":
            items.append("OPEX week — reduce directional exposure, avoid fighting gamma pin")

    if flow:
        for v in (flow.get("ticker_verdicts", []) or [])[:3]:
            if v.get("verdict") == "BULLISH" and v.get("alignment") == "ALIGNED":
                items.append(f"Strong bullish signal: {v['symbol']} — news + flow aligned")

    return items

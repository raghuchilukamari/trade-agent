"""
Daily Pipeline Worker — orchestrates the full LangGraph analysis pipeline.

This is the main entry point for triggering daily analysis runs,
either via API, CLI, or scheduler.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import structlog
from langchain_core.messages import HumanMessage

from app.core.client import ServiceContainer
from app.schema.state import AgentState, PipelineContext
from config.settings import settings

logger = structlog.get_logger(__name__)


class DailyPipeline:
    """
    Orchestrates the daily trading analysis pipeline.

    Flow:
      1. Build pipeline context from inputs
      2. Compile the LangGraph analysis graph
      3. Invoke graph with initial state
      4. Return final report + docx path
    """

    def __init__(self, services: ServiceContainer):
        self.services = services

    async def execute(
        self,
        target_date: date,
        analysis_type: str = "weekday",
        flow_data_dir: str | None = None,
        prior_summary_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute the full analysis pipeline.

        Args:
            target_date: Date to analyze
            analysis_type: "weekday" (4 tasks) or "weekend" (news only)
            flow_data_dir: Override path to CSV files
            prior_summary_path: Path to prior day's PDF for continuity

        Returns:
            Dict with final report data and docx_path
        """
        logger.info(
            "pipeline_starting",
            date=target_date.isoformat(),
            type=analysis_type,
        )

        from app.agents.coordinator.graph import build_analysis_graph
        from app.routers.websocket import ws_manager

        # Broadcast status to connected dashboards
        await ws_manager.broadcast({
            "type": "status",
            "agent": "pipeline",
            "status": "starting",
            "date": target_date.isoformat(),
        })

        # Build context
        context: PipelineContext = {
            "target_date": target_date.isoformat(),
            "analysis_type": analysis_type,
            "flow_data_dir": flow_data_dir or settings.flow_data_dir,
            "prior_summary_path": prior_summary_path,
            "flow_entries": None,
            "news_entries": None,
            "golden_sweeps": None,
            "sweeps": None,
            "sexy_flow": None,
            "trady_flow": None,
            "live_prices": None,
        }

        # Build initial state
        initial_state: AgentState = {
            "messages": [
                HumanMessage(content=f"Run {analysis_type} analysis for {target_date.isoformat()}")
            ],
            "next_action": None,
            "iteration_count": 0,
            "context": context,
            "flow_analysis": None,
            "news_analysis": None,
            "opex_analysis": None,
            "final_report": None,
            "errors": [],
        }

        # Build and invoke graph
        graph = build_analysis_graph(self.services)

        try:
            final_state = await graph.ainvoke(initial_state)

            report = final_state.get("final_report", {})
            docx_path = report.get("docx_path") if report else None

            await ws_manager.broadcast({
                "type": "complete",
                "date": target_date.isoformat(),
                "docx_path": docx_path,
                "executive_summary": report.get("executive_summary", "") if report else "",
            })

            logger.info("pipeline_complete", date=target_date.isoformat(), docx=docx_path)

            return {
                "date": target_date.isoformat(),
                "analysis_type": analysis_type,
                "docx_path": docx_path,
                "report": report,
            }

        except Exception as e:
            logger.error("pipeline_error", date=target_date.isoformat(), error=str(e))
            await ws_manager.broadcast({
                "type": "error",
                "date": target_date.isoformat(),
                "message": str(e),
            })
            raise

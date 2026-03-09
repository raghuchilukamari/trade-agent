"""
OPEX Analyst Agent — Handles Task 4 (OPEX Context & Gamma Assessment).

This agent:
  1. Calculates days to next monthly OPEX
  2. Identifies current OPEX phase
  3. Flags VIX expiration proximity
  4. Identifies high-OI strikes from today's flow
  5. Provides gamma environment assessment
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

import structlog

from app.core.client import ServiceContainer
from app.schema.state import OpexAnalysisResult
from app.services.opex_calendar import get_full_opex_context

logger = structlog.get_logger(__name__)


class OpexAnalystAgent:
    """Specialized agent for OPEX mechanics and gamma analysis."""

    def __init__(self, services: ServiceContainer):
        self.services = services

    async def analyze(self, context: dict[str, Any]) -> OpexAnalysisResult:
        """Run the full OPEX analysis."""
        logger.info("opex_analyst_starting", date=context["target_date"])

        target = datetime.strptime(context["target_date"], "%Y-%m-%d").date()
        flow_entries = context.get("flow_entries", [])

        # Get core OPEX context
        opex_ctx = get_full_opex_context(target)

        # Identify high-OI strikes from flow data
        high_oi_strikes = self._find_high_oi_strikes(flow_entries)

        result: OpexAnalysisResult = {
            "next_monthly_opex": opex_ctx["next_monthly_opex"],
            "days_to_opex": opex_ctx["days_to_opex"],
            "current_phase": opex_ctx["current_phase"],
            "phase_label": opex_ctx["phase_label"],
            "phase_implications": opex_ctx["phase_implications"],
            "high_oi_strikes": high_oi_strikes,
            "vix_expiration": opex_ctx["vix_expiration"],
            "vix_days_away": opex_ctx["vix_days_away"],
            "is_quad_witching": opex_ctx["is_quad_witching"],
            "gamma_assessment": opex_ctx["gamma_assessment"],
        }

        logger.info(
            "opex_analysis_complete",
            phase=opex_ctx["current_phase"],
            days=opex_ctx["days_to_opex"],
            high_oi_count=len(high_oi_strikes),
        )

        return result

    def _find_high_oi_strikes(self, flow_entries: list[dict]) -> list[dict]:
        """
        Identify high-OI strikes from flow data.
        Groups by symbol+strike and looks for concentrated activity.
        """
        strike_activity: dict[str, dict] = defaultdict(lambda: {
            "count": 0,
            "total_premium": 0.0,
            "max_vol_oi": 0.0,
            "call_count": 0,
            "put_count": 0,
        })

        for e in flow_entries:
            symbol = e.get("symbol", "")
            strike = e.get("strike")
            if not symbol or not strike:
                continue

            key = f"{symbol} ${strike}"
            premium = e.get("premium_usd", 0) or 0
            vol_oi = e.get("vol_oi_ratio") or 0

            strike_activity[key]["count"] += 1
            strike_activity[key]["total_premium"] += premium
            strike_activity[key]["max_vol_oi"] = max(
                strike_activity[key]["max_vol_oi"], vol_oi
            )
            if e.get("call_put") == "CALL":
                strike_activity[key]["call_count"] += 1
            else:
                strike_activity[key]["put_count"] += 1

        # Filter to significant strikes (multiple hits or high premium)
        significant = []
        for key, data in strike_activity.items():
            if data["count"] >= 2 or data["total_premium"] >= 500_000:
                from app.services.premium_calculator import format_premium_m
                significant.append({
                    "strike_label": key,
                    "hit_count": data["count"],
                    "total_premium": format_premium_m(data["total_premium"]),
                    "max_vol_oi": round(data["max_vol_oi"], 1),
                    "call_put_ratio": (
                        f"{data['call_count']}C/{data['put_count']}P"
                    ),
                    "implication": self._strike_implication(data),
                })

        significant.sort(key=lambda x: x["hit_count"], reverse=True)
        return significant[:15]

    @staticmethod
    def _strike_implication(data: dict) -> str:
        """Determine implication of concentrated strike activity."""
        if data["call_count"] > data["put_count"] * 2:
            return "Strong call-side activity — potential gamma pinning above"
        elif data["put_count"] > data["call_count"] * 2:
            return "Strong put-side activity — potential support/magnet level"
        elif data["max_vol_oi"] > 50:
            return "Extreme Vol/OI — major institutional positioning"
        else:
            return "Mixed activity — watch for directional resolution"

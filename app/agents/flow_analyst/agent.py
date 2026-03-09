"""
Flow Analyst Agent — Handles Task 1 (News-Flow Correlation) and Task 3 (Top 10 Flow Trades).

This agent:
  1. Correlates news tickers with flow data to find aligned/divergent signals
  2. Ranks all flow by scoring criteria (premium, vol/oi, DTE, sweep type)
  3. Applies the Deep ITM Rule to all put positions
  4. Outputs structured verdicts per ticker + ranked top 10
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Any

import structlog

from app.core.client import ServiceContainer
from app.schema.state import FlowAnalysisResult, TickerVerdict
from app.services.deep_itm import apply_deep_itm_batch, check_deep_itm
from app.services.flow_parser import aggregate_by_symbol, get_flow_stats, get_vol_oi_outliers
from app.services.premium_calculator import format_premium_m, premium_significance
from app.services.watchlist import get_ticker_marks, get_ticker_marks_str

logger = structlog.get_logger(__name__)

# ── Scoring Weights ──────────────────────────────────────────────────────────

SCORE_WEIGHTS = {
    "premium": 0.25,
    "vol_oi": 0.20,
    "dte": 0.20,
    "sweep_type": 0.15,
    "repeated": 0.10,
    "news_correlation": 0.10,
}

SWEEP_TYPE_SCORES = {
    "golden_sweep": 1.0,
    "hot_contract": 0.75,
    "interval": 0.50,
    "sweep": 0.40,
    "sexy_flow": 0.35,
    "trady_flow": 0.25,
}


class FlowAnalystAgent:
    """
    Specialized agent for options flow analysis.
    Executes Task 1 (News-Flow Correlation) and Task 3 (Top 10 Flow Trades).
    """

    def __init__(self, services: ServiceContainer):
        self.services = services
        self.llm = services.llm
        self.polygon = services.polygon

    async def analyze(self, context: dict[str, Any]) -> FlowAnalysisResult:
        """Run the full flow analysis pipeline."""
        logger.info("flow_analyst_starting", date=context["target_date"])

        flow_entries = context.get("flow_entries", [])
        news_entries = context.get("news_entries", [])
        prices = context.get("live_prices", {})

        if not flow_entries:
            logger.warning("no_flow_data")
            return self._empty_result()

        # Step 1: Apply Deep ITM Rule to all entries
        enriched = await apply_deep_itm_batch(flow_entries, prices)

        # Step 2: Aggregate by symbol
        by_symbol = aggregate_by_symbol(enriched)

        # Step 3: News-Flow Correlation (Task 1)
        ticker_verdicts = await self._correlate_news_flow(
            by_symbol, news_entries, prices
        )

        # Step 4: Score and rank Top 10 (Task 3)
        top_10 = self._rank_top_trades(
            enriched, news_entries, prices
        )

        # Step 5: Notable flow by category
        notable = self._categorize_notable(enriched)

        # Step 6: Stats and outliers
        stats = get_flow_stats(enriched)
        outliers = get_vol_oi_outliers(enriched, threshold=10.0)

        result: FlowAnalysisResult = {
            "ticker_verdicts": ticker_verdicts,
            "top_10_trades": top_10,
            "notable_flow": notable,
            "total_premium_m": stats["total_premium_m"],
            "flow_stats": stats,
            "vol_oi_outliers": outliers,
        }

        logger.info(
            "flow_analysis_complete",
            verdicts=len(ticker_verdicts),
            top_10=len(top_10),
            total_premium=f"${stats['total_premium_m']:.2f}M",
        )

        return result

    async def _correlate_news_flow(
        self,
        by_symbol: dict[str, dict],
        news_entries: list[dict],
        prices: dict[str, float],
    ) -> list[TickerVerdict]:
        """Task 1: Find tickers with both news AND flow, determine alignment."""

        # Extract news tickers
        news_tickers: dict[str, list[dict]] = defaultdict(list)
        for n in news_entries:
            for t in n.get("tickers", []):
                news_tickers[t].append(n)

        # Find intersection
        flow_symbols = set(by_symbol.keys())
        news_symbols = set(news_tickers.keys())
        overlap = flow_symbols.intersection(news_symbols)

        verdicts = []
        for symbol in sorted(overlap):
            flow_data = by_symbol[symbol]
            news_items = news_tickers[symbol]

            # Determine news sentiment
            avg_sentiment = (
                sum(n.get("sentiment_score", 3.0) or 3.0 for n in news_items) / len(news_items)
            )
            news_summary = "; ".join(
                n.get("summary", "")[:100] for n in news_items[:3]
            )

            # Determine flow direction
            call_prem = flow_data["call_premium"]
            put_prem = flow_data["put_premium"]
            total_prem = flow_data["total_premium"]

            # Check for Deep ITM sold puts (these are bullish, not bearish)
            bullish_put_prem = 0
            for e in flow_data["entries"]:
                if e.get("deep_itm") and e["deep_itm"].get("signal") == "BULLISH":
                    bullish_put_prem += e.get("premium_usd", 0) or 0

            effective_bullish = call_prem + bullish_put_prem
            effective_bearish = put_prem - bullish_put_prem

            flow_direction = "BULLISH" if effective_bullish > effective_bearish else "BEARISH"
            news_direction = "BULLISH" if avg_sentiment >= 3.5 else ("BEARISH" if avg_sentiment <= 2.0 else "NEUTRAL")

            # Alignment
            if flow_direction == news_direction or news_direction == "NEUTRAL":
                alignment = "ALIGNED"
            else:
                alignment = "DIVERGENT"

            # Verdict
            if alignment == "ALIGNED" and flow_direction == "BULLISH":
                verdict = "BULLISH"
            elif alignment == "ALIGNED" and flow_direction == "BEARISH":
                verdict = "BEARISH"
            else:
                verdict = "MIXED"

            flow_summary = (
                f"Total: {format_premium_m(total_prem)}, "
                f"Calls: {format_premium_m(call_prem)} ({flow_data['call_count']}), "
                f"Puts: {format_premium_m(put_prem)} ({flow_data['put_count']}), "
                f"Sources: {', '.join(flow_data['sources'])}"
            )

            reasoning = (
                f"News sentiment {avg_sentiment:.1f}/5 ({news_direction}), "
                f"Flow {flow_direction} ({format_premium_m(effective_bullish)} bullish vs "
                f"{format_premium_m(effective_bearish)} bearish). "
                f"{'Deep ITM puts reclassified as sold (bullish).' if bullish_put_prem > 0 else ''}"
            )

            verdicts.append(TickerVerdict(
                symbol=symbol,
                marks=get_ticker_marks(symbol),
                verdict=verdict,
                news_summary=news_summary,
                news_sentiment=avg_sentiment,
                flow_summary=flow_summary,
                flow_premium_usd=total_prem,
                alignment=alignment,
                reasoning=reasoning,
            ))

        # Sort by premium
        verdicts.sort(key=lambda v: v["flow_premium_usd"], reverse=True)
        return verdicts

    def _rank_top_trades(
        self,
        entries: list[dict],
        news_entries: list[dict],
        prices: dict[str, float],
    ) -> list[dict]:
        """Task 3: Score and rank all flow entries, return top 10."""

        news_ticker_set = set()
        for n in news_entries:
            news_ticker_set.update(n.get("tickers", []))

        scored = []
        for e in entries:
            premium = e.get("premium_usd", 0) or 0
            if premium < 100_000:  # Skip noise
                continue

            score = self._calculate_score(e, news_ticker_set)

            # Deep ITM annotation
            deep_itm = e.get("deep_itm")
            itm_note = ""
            signal = "NEUTRAL"
            if deep_itm:
                signal = deep_itm.get("signal", "NEUTRAL")
                if deep_itm.get("classification") == "DEEP_ITM_SOLD":
                    itm_note = "⚠️ Deep ITM PUT — likely SOLD (BULLISH)"

            scored.append({
                "symbol": e["symbol"],
                "marks_str": get_ticker_marks_str(e["symbol"]),
                "call_put": e.get("call_put", ""),
                "strike": e.get("strike"),
                "expiration": e.get("expiration"),
                "dte": self._calc_dte(e.get("expiration")),
                "premium_usd": premium,
                "premium_formatted": format_premium_m(premium),
                "premium_significance": premium_significance(premium),
                "vol_oi": e.get("vol_oi_ratio"),
                "source": e["source"],
                "alert_type": e.get("alert_type", ""),
                "score": score,
                "signal": signal,
                "deep_itm_note": itm_note,
                "news_correlated": e["symbol"] in news_ticker_set,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        # Deduplicate by symbol (keep highest scored per symbol)
        seen = set()
        top_10 = []
        for s in scored:
            if s["symbol"] not in seen:
                seen.add(s["symbol"])
                top_10.append(s)
            if len(top_10) >= 10:
                break

        return top_10

    def _calculate_score(self, entry: dict, news_tickers: set) -> float:
        """Calculate composite score for a flow entry."""
        premium = entry.get("premium_usd", 0) or 0
        vol_oi = entry.get("vol_oi_ratio") or 0
        dte = self._calc_dte(entry.get("expiration"))

        # Premium score (log scale)
        import math
        prem_score = min(1.0, math.log10(max(premium, 1)) / 7)  # $10M = 1.0

        # Vol/OI score
        voi_score = min(1.0, vol_oi / 50.0) if vol_oi else 0

        # DTE score (14-90 preferred)
        if dte is not None and 14 <= dte <= 90:
            dte_score = 1.0
        elif dte is not None and (7 <= dte < 14 or 90 < dte <= 180):
            dte_score = 0.5
        else:
            dte_score = 0.2

        # Sweep type score
        sweep_score = SWEEP_TYPE_SCORES.get(entry.get("source", ""), 0.25)

        # News correlation
        news_score = 1.0 if entry.get("symbol", "") in news_tickers else 0.0

        # Repeated hits (approximated by source)
        repeat_score = 0.5  # Default; enhanced in aggregation

        return (
            prem_score * SCORE_WEIGHTS["premium"]
            + voi_score * SCORE_WEIGHTS["vol_oi"]
            + dte_score * SCORE_WEIGHTS["dte"]
            + sweep_score * SCORE_WEIGHTS["sweep_type"]
            + repeat_score * SCORE_WEIGHTS["repeated"]
            + news_score * SCORE_WEIGHTS["news_correlation"]
        )

    def _categorize_notable(self, entries: list[dict]) -> dict[str, list[dict]]:
        """Categorize notable flow by type."""
        categories: dict[str, list] = {
            "golden_sweeps": [],
            "high_vol_oi": [],
            "leaps": [],
            "deep_itm_puts": [],
        }

        for e in entries:
            premium = e.get("premium_usd", 0) or 0
            if premium < 250_000:
                continue

            entry_summary = {
                "symbol": e["symbol"],
                "premium": format_premium_m(premium),
                "strike": e.get("strike"),
                "call_put": e.get("call_put"),
                "expiration": e.get("expiration"),
            }

            if e["source"] == "golden_sweep":
                categories["golden_sweeps"].append(entry_summary)
            if (e.get("vol_oi_ratio") or 0) > 10:
                categories["high_vol_oi"].append({**entry_summary, "vol_oi": e["vol_oi_ratio"]})

            dte = self._calc_dte(e.get("expiration"))
            if dte and dte > 180:
                categories["leaps"].append(entry_summary)

            if e.get("deep_itm") and e["deep_itm"].get("classification") == "DEEP_ITM_SOLD":
                categories["deep_itm_puts"].append(entry_summary)

        return categories

    @staticmethod
    def _calc_dte(expiration: str | None) -> int | None:
        """Calculate days to expiration."""
        if not expiration:
            return None
        try:
            exp_date = datetime.strptime(expiration, "%Y-%m-%d")
            return (exp_date - datetime.now()).days
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _empty_result() -> FlowAnalysisResult:
        return {
            "ticker_verdicts": [],
            "top_10_trades": [],
            "notable_flow": {},
            "total_premium_m": 0.0,
            "flow_stats": {},
            "vol_oi_outliers": [],
        }

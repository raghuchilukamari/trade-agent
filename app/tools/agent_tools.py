"""
Agent Tools — LangGraph-compatible tools for use by agents.

These tools wrap service functions so agents can invoke them
during graph execution.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.database import db_manager
from app.core.polygon_client import polygon_manager
from app.services.deep_itm import check_deep_itm
from app.services.opex_calendar import get_full_opex_context
from app.services.watchlist import get_ticker_marks, is_watched


# ── Market Data Tools ────────────────────────────────────────────────────────


async def tool_get_price(symbol: str) -> dict[str, Any]:
    """Get current price for a symbol via Polygon."""
    price = await polygon_manager.get_last_price(symbol)
    prev = await polygon_manager.get_previous_close(symbol)
    return {"symbol": symbol, "price": price, "previous_close": prev}


async def tool_get_batch_prices(symbols: list[str]) -> dict[str, float]:
    """Get prices for multiple symbols."""
    return await polygon_manager.get_batch_prices(symbols)


async def tool_get_news(symbol: str | None = None) -> list[dict]:
    """Get latest news from Polygon."""
    return await polygon_manager.get_ticker_news(symbol)


# ── Analysis Tools ───────────────────────────────────────────────────────────


def tool_check_deep_itm(
    symbol: str, strike: float, current_price: float, call_put: str
) -> dict[str, Any]:
    """Apply Deep ITM Rule to a single position."""
    result = check_deep_itm(symbol, strike, current_price, call_put)
    return result.to_dict()


def tool_get_opex_context(target_date: date) -> dict[str, Any]:
    """Get full OPEX context for a date."""
    return get_full_opex_context(target_date)


def tool_get_watchlist_marks(symbol: str) -> dict[str, Any]:
    """Get watchlist marks and status for a ticker."""
    return {
        "symbol": symbol,
        "marks": get_ticker_marks(symbol),
        "is_watched": is_watched(symbol),
    }


# ── Database Tools ───────────────────────────────────────────────────────────


async def tool_get_flow_history(target_date: date) -> list[dict]:
    """Get historical flow data for a date."""
    return await db_manager.get_flow_by_date(target_date)


async def tool_get_tracker_history(days: int = 5) -> list[dict]:
    """Get recent tracker entries for continuity narrative."""
    return await db_manager.get_recent_tracker(days)


async def tool_semantic_search(query: str, limit: int = 5) -> list[dict]:
    """Search past analyses semantically."""
    from app.core.ollama_client import ollama_manager
    embedding = await ollama_manager.embed(query)
    return await db_manager.semantic_search(embedding, limit)

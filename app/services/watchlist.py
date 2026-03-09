"""
Watchlist management — JP Morgan Top 56, Strong Buys, IBD Top 15.
Provides ticker marking and categorization.
"""

from __future__ import annotations

from typing import Literal

# ── Static Watchlists ────────────────────────────────────────────────────────

JP_MORGAN_TOP_56: set[str] = {
    "GOOGL", "MSFT", "AMZN", "META", "CRM", "NOW", "PANW", "CRWD", "ZS", "FTNT",
    "AVGO", "AMD", "MRVL", "ON", "NXPI", "ADI", "MCHP", "TXN", "KLAC", "LRCX",
    "AMAT", "ASML", "TSM", "MU", "NVDA", "AAPL", "QCOM", "INTC", "WDC", "STX",
    "JPM", "GS", "MS", "BAC", "C", "WFC", "BLK", "SCHW", "AXP", "V", "MA", "PYPL",
    "UNH", "CVS", "CI", "HUM", "ELV", "LLY", "JNJ", "PFE", "MRK", "ABBV", "BMY",
    "CVX", "XOM", "SLB",
}

STRONG_BUYS: set[str] = {
    "DDOG", "NVDA", "AXON", "NOW", "UBER", "IRM", "VST", "AVGO", "AMD", "AMZN",
    "ANET", "MSI", "BSX", "MSFT", "AZO", "CRM",
}

IBD_TOP_15: set[str] = {
    "ANAB", "MU", "IAG", "TVTX", "RKLB", "PACS", "CDE", "GFI", "KGC", "AU", "PLTR",
}


def get_ticker_marks(symbol: str) -> list[str]:
    """Get all applicable marks for a ticker."""
    marks = []
    s = symbol.upper()
    if s in JP_MORGAN_TOP_56 or s == "GOOG":
        marks.append("⭐")
    if s in STRONG_BUYS:
        marks.append("🔥")
    if s in IBD_TOP_15:
        marks.append("📈")
    return marks


def get_ticker_marks_str(symbol: str) -> str:
    """Get marks as a concatenated string."""
    marks = get_ticker_marks(symbol)
    return "".join(marks) if marks else ""


def is_watched(symbol: str) -> bool:
    """Check if a ticker is on any watchlist."""
    s = symbol.upper()
    return s in JP_MORGAN_TOP_56 or s in STRONG_BUYS or s in IBD_TOP_15


def annotate_entries(entries: list[dict]) -> list[dict]:
    """Add marks to a list of flow entries."""
    for e in entries:
        e["marks"] = get_ticker_marks(e.get("symbol", ""))
        e["marks_str"] = get_ticker_marks_str(e.get("symbol", ""))
    return entries

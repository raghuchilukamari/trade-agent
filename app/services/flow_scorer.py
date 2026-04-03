"""
Shared flow scoring and direction classification.

Extracted from FlowAnalystAgent._calculate_score() and flow_aggregator.direction()
so both the agent and dashboard router can use them.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


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

# ── Sector Map ───────────────────────────────────────────────────────────────

SECTOR_MAP = {
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology",
    "META": "Technology", "DELL": "Technology", "ORCL": "Technology",
    "CRM": "SaaS", "NOW": "SaaS", "SHOP": "Technology", "DDOG": "SaaS",
    "SNOW": "SaaS", "CRWD": "SaaS", "ZS": "SaaS",
    "NVDA": "Semiconductors", "AMD": "Semiconductors", "MU": "Semiconductors",
    "TSM": "Semiconductors", "ASML": "Semiconductors", "AVGO": "Semiconductors",
    "INTC": "Semiconductors", "QCOM": "Semiconductors", "MRVL": "Semiconductors",
    "ARM": "Semiconductors", "ON": "Semiconductors",
    "LITE": "Fiber Optics", "ANET": "Fiber Optics", "GLW": "Fiber Optics",
    "OXY": "Energy", "XOM": "Energy", "CVX": "Energy", "SLB": "Energy",
    "USO": "Energy", "XLE": "Energy",
    "COIN": "Crypto", "MSTR": "Crypto", "BITO": "Crypto",
    "PLTR": "Defense/AI", "LMT": "Defense", "RTX": "Defense", "AXON": "Defense/AI",
    "PDD": "China/Retail", "BABA": "China/Retail", "JD": "China/Retail",
    "KWEB": "China/Retail",
    "TSLA": "Automotive/EV", "RIVN": "Automotive/EV", "NIO": "Automotive/EV",
    "GLD": "Precious Metals", "SLV": "Precious Metals", "GDX": "Precious Metals",
    "GOLD": "Precious Metals", "NEM": "Precious Metals",
    "JPM": "Financials", "GS": "Financials", "BAC": "Financials",
    "V": "Financials", "MA": "Financials",
    "UNH": "Healthcare", "JNJ": "Healthcare", "LLY": "Healthcare", "BSX": "Healthcare",
    "AMZN": "Consumer", "WMT": "Consumer", "COST": "Consumer",
    "EQIX": "Real Estate", "IRM": "Real Estate",
    "STX": "Storage", "WDC": "Storage",
    "SPY": "Index/ETF", "QQQ": "Index/ETF", "IWM": "Index/ETF",
    "VST": "Utilities", "NEE": "Utilities",
    "SNAP": "Social Media", "PINS": "Social Media",
    "NFLX": "Entertainment", "DIS": "Entertainment",
    "APP": "AdTech", "UBER": "Ride-sharing",
}


# ── Direction Classification ─────────────────────────────────────────────────

def classify_direction(entry: dict[str, Any]) -> str:
    """
    Determine BULLISH/BEARISH/NEUTRAL based on call/put and bid/ask side.

    For puts: if ask_pct > 70%, the put was likely SOLD (bullish signal).
    """
    cp = entry.get("call_put", "")
    ask = entry.get("ask_pct", 0) or 0

    if cp == "CALL":
        return "BULLISH"
    if cp == "PUT":
        if ask > 70:
            return "BULLISH"  # put sold at ask
        return "BEARISH"
    return "NEUTRAL"


def classify_net_direction(bull_premium: float, bear_premium: float) -> str:
    """Classify overall direction from bull/bear premium totals."""
    if bull_premium > bear_premium * 1.5:
        return "BULLISH"
    if bear_premium > bull_premium * 1.5:
        return "BEARISH"
    return "CONTESTED"


# ── Composite Scoring ────────────────────────────────────────────────────────

def calc_dte(expiration: str | None) -> int | None:
    """Calculate days to expiration."""
    if not expiration:
        return None
    try:
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        return (exp_date - datetime.now()).days
    except (ValueError, TypeError):
        return None


def calculate_composite_score(
    entry: dict[str, Any],
    news_tickers: set[str] | None = None,
    repeated_hits: set[str] | None = None,
) -> float:
    """
    Calculate composite score for a flow entry.

    Factors: premium (log-scale), vol/oi ratio, DTE sweet spot,
    sweep type, repeated ticker hits, news correlation.
    """
    premium = entry.get("premium_usd", 0) or 0
    vol_oi = entry.get("vol_oi_ratio") or 0
    dte = calc_dte(entry.get("expiration"))

    # Premium score (log scale, $10M = 1.0)
    prem_score = min(1.0, math.log10(max(premium, 1)) / 7)

    # Vol/OI score (50x = 1.0)
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
    news_score = 0.0
    if news_tickers and entry.get("symbol", "") in news_tickers:
        news_score = 1.0

    # Repeated hits
    repeat_score = 0.5
    if repeated_hits and entry.get("symbol", "") in repeated_hits:
        repeat_score = 1.0

    return (
        prem_score * SCORE_WEIGHTS["premium"]
        + voi_score * SCORE_WEIGHTS["vol_oi"]
        + dte_score * SCORE_WEIGHTS["dte"]
        + sweep_score * SCORE_WEIGHTS["sweep_type"]
        + repeat_score * SCORE_WEIGHTS["repeated"]
        + news_score * SCORE_WEIGHTS["news_correlation"]
    )


def get_sector(symbol: str) -> str:
    """Map a ticker to its sector."""
    return SECTOR_MAP.get(symbol.upper(), "Other")


# ── Sector Aggregation ───────────────────────────────────────────────────────

def aggregate_sectors(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Aggregate flow entries into sector-level bull/bear premium totals.

    Returns: {sector_name: {bull_premium, bear_premium, net_premium, signal, tickers}}
    """
    from collections import defaultdict

    sectors: dict[str, dict] = defaultdict(
        lambda: {"bull_premium": 0.0, "bear_premium": 0.0, "tickers": set()}
    )

    for e in entries:
        sym = e.get("symbol", "")
        sec = get_sector(sym)
        premium = e.get("premium_usd", 0) or 0
        d = classify_direction(e)

        sectors[sec]["tickers"].add(sym)
        if d == "BULLISH":
            sectors[sec]["bull_premium"] += premium
        else:
            sectors[sec]["bear_premium"] += premium

    result = {}
    for name, s in sectors.items():
        bull, bear = s["bull_premium"], s["bear_premium"]
        net = bull - bear
        if bull > bear * 2:
            signal = "BULLISH"
        elif bull > bear * 1.2:
            signal = "LEAN BULLISH"
        elif bear > bull * 2:
            signal = "BEARISH"
        elif bear > bull * 1.2:
            signal = "LEAN BEARISH"
        else:
            signal = "CONTESTED"

        result[name] = {
            "bull_premium": bull,
            "bear_premium": bear,
            "net_premium": net,
            "signal": signal,
            "tickers": sorted(s["tickers"]),
        }

    return dict(sorted(result.items(), key=lambda x: x[1]["bull_premium"] + x[1]["bear_premium"], reverse=True))

"""
Shared flow scoring and direction classification.

Extracted from FlowAnalystAgent._calculate_score() and flow_aggregator.direction()
so both the agent and dashboard router can use them.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.services.flow_parser import FlowParser
from app.services.flow_parser_v0 import load_all_flow, load_walter_news
from app.services.premium_calculator import format_premium_m
from scripts.run_equity_research import process_ticker

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
    Direction logic to capture refined Rule 2: Institutional Put Writing.
    Bullish: Call@Ask, Put@Bid, or Deep ITM Put@Bid.
    """
    cp = entry.get("call_put", "")
    ask_pct = entry.get("ask_pct", 0) or 0
    bid_pct = entry.get("bid_pct", 0) or 0
    otm_pct = entry.get("otm_pct", 0) or 0

    if cp == "CALL":
        return "BULLISH"
    if cp == "PUT":
        if bid_pct >  ask_pct:
            if otm_pct < -15:
                return "BULLISH (DEEP ITM PUT SELLING)"
            return "BULLISH (PUT SELLING)"  # put sold at ask
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


# ── Aggregation ──────────────────────────────────────────────────────────────

def aggregate(all_entries):
    tickers = defaultdict(lambda: {
        "total_premium": 0, "bull_premium": 0, "bear_premium": 0,
        "calls": 0, "puts": 0, "trades": 0, "channels": set(),
        "bull_count": 0, "bear_count": 0,
    })
    put_sellers = []

    for e in all_entries:
        sym = e["symbol"]
        premium = e.get("premium_usd", 0) or 0
        t = tickers[sym]
        t["trades"] += 1
        t["total_premium"] += premium
        t["channels"].add(e["source"])

        d = classify_direction(e)
        if e.get("call_put") == "CALL":
            t["calls"] += 1
        elif e.get("call_put") == "PUT":
            t["puts"] += 1

        if d == "BULLISH":
            t["bull_premium"] += premium
            t["bull_count"] += 1
        elif d == "BEARISH":
            t["bear_premium"] += premium
            t["bear_count"] += 1
        elif d == "BULLISH (DEEP ITM PUT SELLING)" or d == "BULLISH (PUT SELLING)":
            put_sellers.append({
                "symbol": sym, "strike": str(e.get("strike", "")),
                "expiration": e.get("expiration", ""), "premium": premium,
                "ask_pct": e.get("ask_pct", 0), "date": e.get("date", ""),
            })

        # elif e.get("call_put") == "PUT" and (e.get("ask_pct") or 0) > 70 and premium >= 500_000:
        #     put_sellers.append({
        #         "symbol": sym, "strike": str(e.get("strike", "")),
        #         "expiration": e.get("expiration", ""), "premium": premium,
        #         "ask_pct": e.get("ask_pct", 0), "date": e.get("date", ""),
        #     })

    # Net direction
    for t in tickers.values():
        b, br = t["bull_premium"], t["bear_premium"]
        t["direction"] = "BULLISH" if b > br * 1.5 else "BEARISH" if br > b * 1.5 else "CONTESTED"
        t["channels"] = sorted(t["channels"])
        t["bull_pct"] = round(t["bull_count"] / t["trades"] * 100) if t["trades"] else 0

    # Sectors
    sectors = defaultdict(lambda: {"bull": 0, "bear": 0, "tickers": set()})
    for sym, t in tickers.items():
        sec = SECTOR_MAP.get(sym, "Other")
        sectors[sec]["bull"] += t["bull_premium"]
        sectors[sec]["bear"] += t["bear_premium"]
        sectors[sec]["tickers"].add(sym)

    for s in sectors.values():
        s["tickers"] = sorted(s["tickers"])
        b, br = s["bull"], s["bear"]
        s["signal"] = (
            "BULLISH" if b > br * 2 else
            "LEAN BULLISH" if b > br * 1.2 else
            "BEARISH" if br > b * 2 else
            "LEAN BEARISH" if br > b * 1.2 else
            "CONTESTED"
        )

    return dict(tickers), dict(sectors), sorted(put_sellers, key=lambda x: x["premium"], reverse=True)



# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--output", help="Output JSON path (default: stdout)")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    DATA_DIR = os.getenv("FORMATTED_DIR")
    all_entries = load_all_flow(DATA_DIR, start_date=args.start, end_date=args.end)
    walter = load_walter_news(DATA_DIR, start_date=args.start, end_date=args.end)

    # 2. Environment Setup
    env_path = os.getenv("FORMATTED_DIR")
    data_path = Path(env_path) if env_path else Path(__file__).parent.parent.parent / "data"

    # 3. Determine Target Date (Default to Current: 2026-04-07)
    # Using the current date as the source of truth for Step 1 of your Daily Sequence
    # today = date.today().strftime("%Y-%m-%d")
    today = '2026-04-06'

    # Logic: If no range is provided, we strictly look for 'today'
    is_range = bool(args.start or args.end)
    target_date = today if not is_range else None

    print(f"--- Initialization: {today} ---")
    print(f"Data Path: {data_path}")

    tool = FlowParser()
    all_entries = tool.get_all_flow(target_date=today)
    walter = tool.get_news_flow(target_date=today)

    ch_counts = defaultdict(int)
    for e in all_entries:
        ch_counts[e["source"]] += 1

    tickers, sectors, put_sellers = aggregate(all_entries)
    sorted_t = sorted(tickers.items(), key=lambda x: x[1]["total_premium"], reverse=True)
    total_prem = sum(e.get("premium_usd", 0) or 0 for e in all_entries)

    fmt = format_premium_m

    out = {
        "meta": {
            "date_range": [args.start, args.end],
            "generated_at": datetime.now().isoformat(),
            "total_trades": len(all_entries),
            "total_premium": total_prem,
            "total_premium_fmt": fmt(total_prem),
            "channels": dict(ch_counts),
            "walter_news_count": len(walter),
        },
        "tickers": {},
        "sectors": {},
        "put_sellers": [
            {**ps, "premium_fmt": fmt(ps["premium"])} for ps in put_sellers[:20]
        ],
    }

    for sym, t in sorted_t[:args.top]:
        out["tickers"][sym] = {
            "total_premium": t["total_premium"],
            "total_premium_fmt": fmt(t["total_premium"]),
            "bull_premium": t["bull_premium"],
            "bull_premium_fmt": fmt(t["bull_premium"]),
            "bear_premium": t["bear_premium"],
            "bear_premium_fmt": fmt(t["bear_premium"]),
            "trades": t["trades"],
            "calls": t["calls"],
            "puts": t["puts"],
            "bull_count": t["bull_count"],
            "bear_count": t["bear_count"],
            "bull_pct": t["bull_pct"],
            "channels": t["channels"],
            "channel_count": len(t["channels"]),
            "direction": t["direction"],
        }

    sorted_s = sorted(sectors.items(), key=lambda x: x[1]["bull"] + x[1]["bear"], reverse=True)
    for name, s in sorted_s:
        net = s["bull"] - s["bear"]
        out["sectors"][name] = {
            "bull_premium": s["bull"], "bull_fmt": fmt(s["bull"]),
            "bear_premium": s["bear"], "bear_fmt": fmt(s["bear"]),
            "net": net, "net_fmt": ("+" if net >= 0 else "") + fmt(abs(net)),
            "signal": s["signal"], "tickers": s["tickers"],
        }

    result = json.dumps(out, indent=2, default=str)
    if args.output:
        with open(args.output, "w") as f:
            f.write(result)
        print(f"Saved: {args.output} ({len(all_entries)} trades, {fmt(total_prem)} premium, {len(walter)} news)", file=sys.stderr)
    else:
        print(result)




if __name__ == "__main__":
    main()

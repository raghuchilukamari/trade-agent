"""Cross-channel options flow aggregator.

Reuses app.services.flow_parser for loading/normalization and
app.services.premium_calculator for formatting. Adds put-seller
detection, direction classification, and sector mapping on top.

Usage:
    python scripts/flow_aggregator.py --start 2026-03-23 --end 2026-03-27
    python scripts/flow_aggregator.py --start 2026-03-23 --end 2026-03-27 --output /tmp/flow.json
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.services.flow_parser_v0 import load_all_flow, load_walter_news
from app.services.premium_calculator import format_premium_m
from dotenv import load_dotenv
import os

load_dotenv()

DATA_DIR = Path(os.getenv("FORMATTED_DIR"))

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


# ── Direction logic ──────────────────────────────────────────────────────────

def direction(entry):
    """Determine BULLISH/BEARISH based on call/put and bid/ask side."""
    cp = entry.get("call_put", "")
    ask_pct = entry.get("ask_pct", 0) or 0
    bid_pct = entry.get("bid_pct", 0) or 0
    otm_pct = entry.get("otm_pct", 0) or 0

    if cp == "CALL":
        return "BULLISH"
    if cp == "PUT":
        if bid_pct > ask_pct:
            if otm_pct < -15:
                return "BULLISH (DEEP ITM PUT SELLING)"
            return "BULLISH (PUT SELLING)"  # put sold at ask
        return "BEARISH"
    return "NEUTRAL"


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

        d = direction(e)
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--output", help="Output JSON path (default: stdout)")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    all_entries = load_all_flow(DATA_DIR, start_date=args.start, end_date=args.end)
    walter = load_walter_news(DATA_DIR, start_date=args.start, end_date=args.end)

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

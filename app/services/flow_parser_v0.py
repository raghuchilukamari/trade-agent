"""
Flow data parser — loads, normalizes, and aggregates options flow from all 4 CSV sources.

Handles pipe-delimited CSVs: golden-sweeps, sweeps, sexy-flow, trady-flow.
Applies ticker normalization (GOOG/GOOGL → Alphabet) and premium standardization.

Data Sources	Merges 4 pipe-delimited CSV sources (Golden, Sweep, Sexy, Trady).	load_all_flow
News Parsing	Extracts Geopolitical entities and sentiment from Walter News.	load_walter_news
Normalization	Forces GOOG/GOOGL and BRK consistency.	normalize_symbol
Aggregation	Calculates total, call, and put premiums per symbol.	aggregate_by_symbol
Smart Flags	Identifies Vol/OI outliers and "Extreme" institutional activity.	get_vol_oi_outliers

Scenario A: Strict Daily Audit (Current Date)
python3 -m app.services.flow_parser

Scenario B: Historical Range Analysis
python3 -m app.services.flow_parser --start 2026-03-01 --end 2026-03-31

Aggregated data
aggregate_by_symbol(all_flow)

Outlier Detection (Vol/OI Ratios):
get_vol_oi_outliers(all_flow, threshold=10.0)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from typing import Any
import os
from dotenv import load_dotenv
import structlog

from app.services.premium_calculator import parse_premium, format_premium_m

logger = structlog.get_logger(__name__)

# ── Ticker Normalization ─────────────────────────────────────────────────────

TICKER_ALIASES = {
    "GOOG": "GOOGL",     # Alphabet
    "BRK.A": "BRK.B",    # Berkshire
    "BRK/A": "BRK.B",
}


def normalize_symbol(symbol: str) -> str:
    """Normalize ticker symbols — combine GOOG/GOOGL, BRK.A/BRK.B, etc."""
    s = symbol.strip().upper()
    return TICKER_ALIASES.get(s, s)


# ── CSV Loaders ──────────────────────────────────────────────────────────────


def _load_pipe_csv(
    filepath: Path,
    target_date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Load a pipe-delimited CSV and optionally filter by date or date range."""
    if not filepath.exists():
        logger.warning("file_not_found", path=str(filepath))
        return []

    rows = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="|")
        for row in reader:
            d = row.get("Date", "").strip()
            if target_date and d != target_date:
                continue
            if start_date and d < start_date:
                continue
            if end_date and d > end_date:
                continue
            rows.append({k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()})

    logger.info("loaded_csv", file=filepath.name, rows=len(rows), date_filter=target_date or f"{start_date}..{end_date}")
    return rows


def load_golden_sweeps(data_dir: Path, target_date: str = None, *, start_date: str = None, end_date: str = None) -> list[dict[str, Any]]:
    """Load golden-sweeps.csv and normalize."""
    rows = _load_pipe_csv(data_dir / "golden-sweeps.csv", target_date, start_date, end_date)
    entries = []
    for r in rows:
        entries.append({
            "date": r.get("Date", target_date),
            "source": "golden_sweep",
            "symbol": normalize_symbol(r.get("Symbol", "")),
            "strike": _parse_float(r.get("Strike")),
            "expiration": _parse_date(r.get("Expiration")),
            "call_put": _infer_call_put(r.get("Description", "")),
            "premium_raw": r.get("Premiums", ""),
            "premium_usd": parse_premium(r.get("Premiums", "")),
            "vol_oi_ratio": None,
            "alert_type": "golden_sweep",
            "description": r.get("Description", ""),
            "oi": None,
        })
    return entries


def load_sweeps(data_dir: Path, target_date: str = None, *, start_date: str = None, end_date: str = None) -> list[dict[str, Any]]:
    """Load sweeps.csv and normalize."""
    rows = _load_pipe_csv(data_dir / "sweeps.csv", target_date, start_date, end_date)
    entries = []
    for r in rows:
        entries.append({
            "date": r.get("Date", target_date),
            "source": "sweep",
            "symbol": normalize_symbol(r.get("Symbol", "")),
            "strike": _parse_float(r.get("Strike")),
            "expiration": _parse_date(r.get("Expiration")),
            "call_put": r.get("Call_Put", "").upper(),
            "premium_raw": r.get("Premiums", ""),
            "premium_usd": parse_premium(r.get("Premiums", "")),
            "vol_oi_ratio": None,
            "alert_type": "sweep",
            "description": "",
            "oi": None,
        })
    return entries


def load_sexy_flow(data_dir: Path, target_date: str = None, *, start_date: str = None, end_date: str = None) -> list[dict[str, Any]]:
    """Load sexy-flow.csv and normalize."""
    rows = _load_pipe_csv(data_dir / "sexy-flow.csv", target_date, start_date, end_date)
    entries = []
    for r in rows:
        bid_pct, ask_pct = _parse_bid_ask(r.get("Bid_Ask_Pct", ""))
        entries.append({
            "date": r.get("Date", target_date or ""),
            "source": "sexy_flow",
            "symbol": normalize_symbol(r.get("Symbol", "")),
            "strike": _parse_float(r.get("Strike")),
            "expiration": _parse_date(r.get("Expiration")),
            "call_put": r.get("Call_Put", "").upper(),
            "premium_raw": r.get("Premium", ""),
            "premium_usd": parse_premium(r.get("Premium", "")),
            "vol_oi_ratio": _parse_float(r.get("Vol_OI_Ratio")),
            "alert_type": r.get("Alert_Type", ""),
            "description": "",
            "oi": None,
            "bid_pct": bid_pct,
            "ask_pct": ask_pct,
            "otm_pct": r.get("OTM_Pct", ""),
            "multileg_vol": r.get("Multileg_Vol", ""),
        })
    return entries


def load_trady_flow(data_dir: Path, target_date: str = None, *, start_date: str = None, end_date: str = None) -> list[dict[str, Any]]:
    """Load trady-flow.csv and normalize."""
    rows = _load_pipe_csv(data_dir / "trady-flow.csv", target_date, start_date, end_date)
    entries = []
    for r in rows:
        entries.append({
            "date": r.get("Date", target_date),
            "source": "trady_flow",
            "symbol": normalize_symbol(r.get("Symbol", "")),
            "strike": _parse_float(r.get("Strike")),
            "expiration": _parse_date(r.get("Expiration")),
            "call_put": r.get("Call_Put", "").upper(),
            "premium_raw": r.get("Total_Prems", ""),
            "premium_usd": parse_premium(r.get("Total_Prems", "")),
            "vol_oi_ratio": _parse_float(r.get("Vol_OI_Ratio")),
            "alert_type": r.get("Source", ""),
            "description": "",
            "oi": _parse_int(r.get("OI")),
        })
    return entries


def load_walter_news(data_dir: Path, target_date: str = None, *, start_date: str = None, end_date: str = None) -> list[dict[str, Any]]:
    """Load walter_openai.csv (news) and normalize."""
    rows = _load_pipe_csv(data_dir / "walter_openai.csv", target_date, start_date, end_date)
    entries = []
    for r in rows:
        tickers = _parse_tickers(r.get("key_entities_ticker", ""))
        entries.append({
            "date": r.get("Date", target_date),
            "summary": r.get("new_summary", ""),
            "sentiment_score": _parse_float(r.get("sentiment_score")),
            "tickers": tickers,
            "geopolitical_entities": _parse_list(r.get("key_entities_geopolitical", "")),
            "sectors": _parse_list(r.get("key_entities_sector", "")),
            "commodities": _parse_list(r.get("key_entities_commodity", "")),
        })
    return entries


def load_all_flow(data_dir: Path, target_date: str = None, *, start_date: str = None, end_date: str = None) -> list[dict[str, Any]]:
    """Load and merge all 4 flow sources for a given date or date range."""
    all_entries = []
    all_entries.extend(load_golden_sweeps(data_dir, target_date, start_date=start_date, end_date=end_date))
    all_entries.extend(load_sweeps(data_dir, target_date, start_date=start_date, end_date=end_date))
    all_entries.extend(load_sexy_flow(data_dir, target_date, start_date=start_date, end_date=end_date))
    all_entries.extend(load_trady_flow(data_dir, target_date, start_date=start_date, end_date=end_date))
    logger.info("all_flow_loaded", total=len(all_entries), date=target_date or f"{start_date}..{end_date}")
    return all_entries


# ── Aggregation ──────────────────────────────────────────────────────────────


def aggregate_by_symbol(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Aggregate flow entries by symbol.
    Returns: {symbol: {total_premium, call_premium, put_premium, entries, ...}}
    """
    agg: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "total_premium": 0.0,
        "call_premium": 0.0,
        "put_premium": 0.0,
        "call_count": 0,
        "put_count": 0,
        "entries": [],
        "sources": set(),
        "max_vol_oi": 0.0,
    })

    for e in entries:
        sym = e["symbol"]
        premium = e.get("premium_usd", 0) or 0
        agg[sym]["total_premium"] += premium
        agg[sym]["entries"].append(e)
        agg[sym]["sources"].add(e["source"])

        vol_oi = e.get("vol_oi_ratio") or 0
        if vol_oi > agg[sym]["max_vol_oi"]:
            agg[sym]["max_vol_oi"] = vol_oi

        if e.get("call_put") == "CALL":
            agg[sym]["call_premium"] += premium
            agg[sym]["call_count"] += 1
        elif e.get("call_put") == "PUT":
            agg[sym]["put_premium"] += premium
            agg[sym]["put_count"] += 1

    # Convert sets to lists for JSON serialization
    for sym in agg:
        agg[sym]["sources"] = list(agg[sym]["sources"])

    return dict(agg)


def get_flow_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate summary statistics for flow entries."""
    total_premium = sum(e.get("premium_usd", 0) or 0 for e in entries)
    by_source = defaultdict(int)
    for e in entries:
        by_source[e["source"]] += 1

    return {
        "total_premium_m": round(total_premium / 1_000_000, 2),
        "golden_sweeps_count": by_source.get("golden_sweep", 0),
        "total_sweeps_count": by_source.get("sweep", 0),
        "sexy_flow_count": by_source.get("sexy_flow", 0),
        "trady_flow_count": by_source.get("trady_flow", 0),
        "total_entries": len(entries),
    }


def get_vol_oi_outliers(entries: list[dict[str, Any]], threshold: float = 10.0) -> list[dict]:
    """Find entries with Vol/OI ratio above threshold."""
    outliers = []
    for e in entries:
        vol_oi = e.get("vol_oi_ratio") or 0
        if vol_oi >= threshold:
            outliers.append({
                "symbol": e["symbol"],
                "vol_oi": vol_oi,
                "strike": e.get("strike"),
                "call_put": e.get("call_put"),
                "premium": format_premium_m(e.get("premium_usd", 0)),
                "source": e["source"],
                "extreme": vol_oi >= 50.0,
            })
    return sorted(outliers, key=lambda x: x["vol_oi"], reverse=True)


def get_ticker_summary(entries: list[dict[str, Any]], symbol:str) -> dict | None:
    sym_entries = [e for e in entries if e.get("symbol") == symbol]
    if not sym_entries:
        return None
    agg = aggregate_by_symbol(sym_entries).get(symbol, {})
    return {
            "symbol": symbol,
            "total_premium_usd": agg.get("total_premium", 0),
            "call_premium_usd": agg.get("call_premium", 0),
            "put_premium_usd": agg.get("put_premium", 0),
            "call_count": agg.get("call_count", 0),
            "put_count": agg.get("put_count", 0),
            "max_vol_oi": agg.get("max_vol_oi"),
            "sources": agg.get("sources", []),
    }

# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_float(val: Any) -> float | None:
    if val is None or str(val).strip() == "":
        return None
    try:
        return float(str(val).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        return None


def _parse_int(val: Any) -> int | None:
    if val is None or str(val).strip() == "":
        return None
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return None


def _parse_date(val: Any) -> str | None:
    """Parse various date formats into YYYY-MM-DD."""
    if not val or str(val).strip() == "":
        return None
    s = str(val).strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def _parse_tickers(val: str) -> list[str]:
    """Parse comma-separated tickers, stripping $ signs."""
    if not val or val.strip() == "":
        return []
    tickers = []
    for t in val.split(","):
        t = t.strip().replace("$", "").upper()
        if t:
            tickers.append(normalize_symbol(t))
    return tickers


def _parse_list(val: str) -> list[str]:
    """Parse comma-separated values into list."""
    if not val or val.strip() == "":
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


def _parse_bid_ask(val: str) -> tuple[int, int]:
    """Parse bid/ask percentage string like '2/88' → (2, 88)."""
    if not val or "/" not in val:
        return 0, 0
    parts = val.split("/")
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 0, 0


def _infer_call_put(description: str) -> str:
    """Infer CALL/PUT from golden sweep description text."""
    desc = description.upper()
    if "CALL" in desc:
        return "CALL"
    elif "PUT" in desc:
        return "PUT"
    return ""


if __name__ == "__main__":
    import json
    from datetime import date

    load_dotenv()

    # 1. Parse Arguments for Date Range
    parser = argparse.ArgumentParser(description="Options Flow Parser Diagnostic Tool")
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    # 2. Environment Setup
    env_path = os.getenv("FORMATTED_DIR")
    data_path = Path(env_path) if env_path else Path(__file__).parent.parent.parent / "data"

    # 3. Determine Target Date (Default to Current: 2026-04-07)
    # Using the current date as the source of truth for Step 1 of your Daily Sequence
    #today = date.today().strftime("%Y-%m-%d")
    today = '2026-04-06'

    # Logic: If no range is provided, we strictly look for 'today'
    is_range = bool(args.start or args.end)
    target_date = today if not is_range else None

    print(f"--- Initialization: {today} ---")
    print(f"Data Path: {data_path}")

    # 4. Load Data
    try:
        all_flow = load_all_flow(
            data_path,
            target_date=target_date,
            start_date=args.start,
            end_date=args.end
        )

        news = load_walter_news(
            data_path,
            target_date=target_date,
            start_date=args.start,
            end_date=args.end)

        # 5. Strict Existence Check
        if not all_flow and not is_range:
            # Throwing error as requested if current date data is missing and no range provided
            raise FileNotFoundError(
                f"CRITICAL: No flow data found for current date ({today}). "
                "Verify CSV updates or provide a date range via --start/--end."
            )
        elif not all_flow:
            print(f"Warning: No data found for requested range: {args.start} to {args.end}")
            sys.exit(0)

        # 6. Execute Summary (Top 10 Flow & Rule 2 Interpretation)
        stats = get_flow_stats(all_flow)
        print(f"\n[DAILY SUMMARY - {target_date or 'RANGE'}]")
        print(f"Total Premium: ${stats['total_premium_m']}M | Entries: {stats['total_entries']}")

        aggregated = aggregate_by_symbol(all_flow)
        all_flow_agg_sorted = sorted(aggregated.items(), key=lambda x: x[1]['total_premium'], reverse=True)
        top_10 = sorted(aggregated.items(), key=lambda x: x[1]['total_premium'], reverse=True)[:10]

        print("\n[Full Flow INTERPRETATION]")
        for sym, data in all_flow_agg_sorted:
            print(
                f"{sym} | Calls: {data['call_count']:3} | Puts: {data['put_count']:3} | Total: ${data['total_premium']:12,.2f}")



    except FileNotFoundError as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[UNEXPECTED ERROR] {e}")
        sys.exit(1)
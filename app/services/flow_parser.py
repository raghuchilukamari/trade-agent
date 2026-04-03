"""
Flow data parser — loads, normalizes, and aggregates options flow from all 4 CSV sources.

Handles pipe-delimited CSVs: golden-sweeps, sweeps, sexy-flow, trady-flow.
Applies ticker normalization (GOOG/GOOGL → Alphabet) and premium standardization.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from typing import Any

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


# ── FlowParser class (for router dependency injection) ───────────────────────


class FlowParser:
    """High-level flow parser with DB integration."""

    def __init__(self, db):
        self.db = db

    async def get_quick_stats(self, target_date: date) -> dict[str, Any]:
        from app.schema.models import QuickStats
        entries = await self.db.get_flow_by_date(target_date)
        stats = get_flow_stats(entries) if entries else {
            "total_premium_m": 0, "golden_sweeps_count": 0,
            "total_sweeps_count": 0, "sexy_flow_count": 0,
            "trady_flow_count": 0,
        }
        return QuickStats(
            target_date=target_date,
            total_premium_m=stats["total_premium_m"],
            golden_sweeps_count=stats["golden_sweeps_count"],
            total_sweeps_count=stats["total_sweeps_count"],
            sexy_flow_count=stats["sexy_flow_count"],
            trady_flow_count=stats["trady_flow_count"],
        )

    async def get_ticker_summary(self, symbol: str, target_date: date) -> dict | None:
        entries = await self.db.get_flow_by_date(target_date)
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

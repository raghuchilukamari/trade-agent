#!/usr/bin/env python3
"""
run_equity_research.py — Offline batch equity research runner.

Processes tickers sequentially (Polygon rate limit: 5/min = 12s between calls).
Pulls fundamentals from Polygon, price/technicals from ta_daily,
insider/red-flag data from SEC EDGAR scripts, news from walter_openai.csv.
Generates 5-section HTML reports and upserts to dashboard.equity_research.

Usage:
    # Named tickers
    python3 scripts/run_equity_research.py --tickers MU TSM MSFT

    # From research queue (all priorities)
    python3 scripts/run_equity_research.py --from-queue /tmp/research_queue.json

    # P3 only, skip ETFs, stop at 30
    python3 scripts/run_equity_research.py \
        --from-queue /tmp/research_queue.json --priority 3 --skip-etfs --limit 30

    # Force re-run even if fresh
    python3 scripts/run_equity_research.py --tickers NVDA --force
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import date
from pathlib import Path

# ── project imports ───────────────────────────────────────────────────────────
# parents[4] = trading-agent/ (script is at .claude/skills/equity-research/scripts/)
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from config.settings import settings
from scripts.equity_research.db_utils import get_engine, is_fresh, upsert_report, get_ta_row
from scripts.equity_research.financial_fetcher import get_quarterly_financials, get_ticker_details
from scripts.equity_research.news_fetcher import get_ticker_news
from scripts.equity_research.report_builder import build_report

# ── SEC scripts ───────────────────────────────────────────────────────────────
SEC_SCRIPTS = ROOT / ".claude/skills/sec-filing-analysis/scripts"
sys.path.insert(0, str(SEC_SCRIPTS))

try:
    from edgar_fetcher import get_form4_transactions
    from insider_analysis import calculate_net_sentiment
    _INSIDER_AVAILABLE = True
except ImportError:
    _INSIDER_AVAILABLE = False
    print("[WARN] edgar_fetcher/insider_analysis not importable — insider data will be skipped", flush=True)

_REDFLAG_AVAILABLE = False  # red_flag_scan requires web searches; skip in offline mode

# ── ETF blocklist ─────────────────────────────────────────────────────────────
ETF_BLOCKLIST = {
    "SLV", "GLD", "SMH", "SIL", "XLE", "XLK", "TLT", "DIA", "GDX",
    "ARKK", "SOXL", "SOXX", "KWEB", "IGV", "EWY", "VOO", "IBIT",
    "AGQ", "SILJ", "BOIL", "HYG", "TMF", "DPST", "SPY", "QQQ",
    "IWM", "XLF", "XBI", "GDX", "GDXJ", "UVXY", "VXX",
}


# ─────────────────────────────────────────────────────────────────────────────

def load_queue(queue_path: str, priority: int | None, skip_etfs: bool) -> list[str]:
    """Load and filter tickers from research_queue.json."""
    data = json.loads(Path(queue_path).read_text())
    tickers = []
    for entry in data:
        sym = entry.get("ticker", "").upper()
        if not sym:
            continue
        p = entry.get("priority", 1)
        if priority is not None and p != priority:
            continue
        if skip_etfs and sym in ETF_BLOCKLIST:
            continue
        tickers.append(sym)
    # deduplicate while preserving order
    seen = set()
    result = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def get_insider_data(ticker: str) -> tuple[dict, list]:
    """Fetch insider transactions + red flags via SEC EDGAR scripts."""
    insider_result = {
        "sentiment": "NEUTRAL",
        "total_bought": 0,
        "total_sold": 0,
        "net_flow": 0,
        "transactions": [],
        "cluster_selling": False,
    }
    red_flags = []

    if _INSIDER_AVAILABLE:
        try:
            txns = get_form4_transactions(ticker, days=90)
            result_obj = calculate_net_sentiment(txns)
            insider_result = {
                "sentiment": result_obj.sentiment,
                "total_bought": result_obj.total_bought_value,
                "total_sold": result_obj.total_sold_value,
                "net_flow": result_obj.net_flow,
                "transactions": [t.__dict__ for t in result_obj.transactions],
                "cluster_selling": result_obj.cluster_selling_detected,
            }
        except Exception as e:
            print(f"    [WARN] insider fetch failed for {ticker}: {e}", flush=True)

    return insider_result, red_flags


def process_ticker(ticker: str, engine, force: bool = False) -> str:
    """
    Full pipeline for one ticker. Returns status string: 'DONE', 'SKIPPED', 'FAILED'.
    Polygon call is made inside; caller handles the 12s rate-limit sleep.
    """
    # 1. Freshness check
    if not force:
        existing = is_fresh(engine, "equity_research", ticker, max_age_days=7)
        if existing:
            return f"SKIPPED (fresh: {existing})"

    # 2. Polygon fundamentals (1 API call — rate limited by caller)
    quarters = get_quarterly_financials(ticker, limit=5)
    details = get_ticker_details(ticker)

    # 3. ta_daily (0 API calls)
    ta = get_ta_row(engine, ticker)

    # 4. SEC EDGAR: insider + red flags
    insider_result, red_flags = get_insider_data(ticker)

    # 5. News from walter CSV
    news = get_ticker_news(ticker, weeks=8)

    # 6. Build HTML report
    html = build_report(ticker, quarters, ta, details, insider_result, red_flags, news)

    # 7. Upsert to dashboard.equity_research
    run_date = date.today().isoformat()
    upsert_report(engine, "equity_research", ticker, run_date, html)

    chars = len(html)
    return f"DONE ({chars:,} chars, {len(quarters)} qtrs, flags={len(red_flags)})"


def main():
    parser = argparse.ArgumentParser(description="Offline batch equity research runner")
    parser.add_argument("--tickers", nargs="+", metavar="TICKER", help="Specific tickers to process")
    parser.add_argument("--from-queue", metavar="FILE", help="Path to research_queue.json")
    parser.add_argument("--priority", type=int, choices=[1, 2, 3], help="Filter queue by priority")
    parser.add_argument("--limit", type=int, default=0, help="Max tickers to process (0=unlimited)")
    parser.add_argument("--skip-fresh", action="store_true", help="Skip tickers with fresh reports")
    parser.add_argument("--skip-etfs", action="store_true", help="Skip ETF tickers")
    parser.add_argument("--force", action="store_true", help="Re-run even if report is fresh")
    args = parser.parse_args()

    # ── Build ticker list ─────────────────────────────────────────────────────
    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
        if args.skip_etfs:
            tickers = [t for t in tickers if t not in ETF_BLOCKLIST]
    elif args.from_queue:
        tickers = load_queue(args.from_queue, args.priority, args.skip_etfs)
    else:
        parser.error("Provide --tickers or --from-queue")
        return

    if args.limit and args.limit > 0:
        tickers = tickers[: args.limit]

    if not tickers:
        print("No tickers to process after filters.", flush=True)
        return

    engine = get_engine(settings.database_url_sync)

    total = len(tickers)
    est_min = total * 12 / 60
    print(f"\nEquity Research Runner — {date.today()}", flush=True)
    print(f"Tickers: {total}  |  Est. time: ~{est_min:.0f} min  |  force={args.force}", flush=True)
    if est_min > 10:
        print(f"[WARN] This batch will take ~{est_min:.0f} min (>{total*12}s). Consider --limit 30.", flush=True)
    print("─" * 60, flush=True)

    done = 0
    skipped = 0
    failed = 0
    _need_polygon_sleep = False  # first call has no prior call to sleep after

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i:>3}/{total}] {ticker:<8} ", end="", flush=True)
        try:
            # Rate-limit: sleep 12s BEFORE the Polygon call (except first ticker
            # if it was the very first call this session — financial_fetcher handles
            # the global _last_call timer internally, so this is safe either way)
            if _need_polygon_sleep:
                time.sleep(12.1)

            status = process_ticker(ticker, engine, force=args.force)
            _need_polygon_sleep = not status.startswith("SKIPPED")
            print(status, flush=True)

            if status.startswith("DONE"):
                done += 1
            else:
                skipped += 1

        except KeyboardInterrupt:
            print("\nInterrupted by user.", flush=True)
            break
        except Exception as e:
            failed += 1
            _need_polygon_sleep = True  # might have called Polygon before crashing
            print(f"FAILED — {e}", flush=True)
            traceback.print_exc()

    print("─" * 60, flush=True)
    print(f"Done: {done}  Skipped: {skipped}  Failed: {failed}", flush=True)
    print(f"Reports in: dashboard.equity_research", flush=True)


if __name__ == "__main__":
    main()

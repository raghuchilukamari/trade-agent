#!/usr/bin/env python3
"""
minervini_screener.py — Mark Minervini Trend Template Stock Screener

Screens stocks against all 8 SEPA Trend Template criteria:
  1. Price > 150-day MA AND Price > 200-day MA
  2. 150-day MA > 200-day MA
  3. 200-day MA trending up ≥ 1 month (22 trading days)
  4. 50-day MA > 150-day MA > 200-day MA (full alignment)
  5. Price > 50-day MA
  6. Price ≥ 30% above 52-week low
  7. Price within 25% of 52-week high
  8. Relative Strength (RS) ≥ 70 (vs SPY)

Usage:
    python3 minervini_screener.py                          # Screen all universes
    python3 minervini_screener.py --universe sp500         # S&P 500 only
    python3 minervini_screener.py --universe nasdaq100     # NASDAQ 100 only
    python3 minervini_screener.py --universe watchlist     # Raghu's watchlists only
    python3 minervini_screener.py --tickers AAPL,MSFT,NVDA # Custom tickers
    python3 minervini_screener.py --json                   # Output JSON (for dashboard)
    python3 minervini_screener.py --csv results.csv        # Output CSV file
"""

import sys
import json
import warnings
import argparse
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    print("ERROR: pip install yfinance pandas numpy")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────
# TICKER UNIVERSES — hardcoded in tickers.py (no web scraping)
# ─────────────────────────────────────────────────────────────────────

try:
    from scripts.tickers import get_universe, WATCHLIST_STRONG_BUYS, WATCHLIST_IBD15
except ImportError:
    # Direct execution: python3 scripts/minervini_screener.py
    import os, importlib.util
    _dir = os.path.dirname(os.path.abspath(__file__))
    _spec = importlib.util.spec_from_file_location("tickers", os.path.join(_dir, "tickers.py"))
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    get_universe = _mod.get_universe
    WATCHLIST_STRONG_BUYS = _mod.WATCHLIST_STRONG_BUYS
    WATCHLIST_IBD15 = _mod.WATCHLIST_IBD15


# ─────────────────────────────────────────────────────────────────────
# SCREENING ENGINE
# ─────────────────────────────────────────────────────────────────────

@dataclass
class MinerviniResult:
    """Result of screening a single ticker."""
    ticker: str
    price: float = 0.0
    ma_50: float = 0.0
    ma_150: float = 0.0
    ma_200: float = 0.0
    week_52_high: float = 0.0
    week_52_low: float = 0.0
    pct_above_low: float = 0.0
    pct_from_high: float = 0.0
    rs_rating: float = 0.0
    ma200_slope_22d: float = 0.0  # 200-day MA slope over 1 month

    # Criteria pass/fail
    c1_price_above_150_200: bool = False
    c2_ma150_above_ma200: bool = False
    c3_ma200_trending_up: bool = False
    c4_ma_alignment: bool = False  # 50 > 150 > 200
    c5_price_above_50: bool = False
    c6_above_low_30pct: bool = False
    c7_within_high_25pct: bool = False
    c8_rs_above_70: bool = False

    criteria_passed: int = 0
    total_criteria: int = 8
    passes_template: bool = False
    error: str = ""

    # Source tracking
    universe: str = ""
    scan_date: str = ""


def compute_rs_rating(stock_returns: float, all_stock_returns: list[float]) -> float:
    """
    Compute Relative Strength rating (1-99 percentile rank).

    Ranks the stock's 6-month return as a percentile among all screened stocks.
    """
    if not all_stock_returns:
        return 0.0

    # RS is percentile rank of stock's performance among all stocks
    count_below = sum(1 for r in all_stock_returns if r < stock_returns)
    percentile = (count_below / len(all_stock_returns)) * 100
    return round(percentile, 1)


def screen_ticker(ticker: str, hist: pd.DataFrame,
                  all_returns: list[float] = None) -> MinerviniResult:
    """
    Screen a single ticker against all 8 Minervini criteria.

    Args:
        ticker: Stock ticker
        hist: DataFrame with OHLCV data (≥252 rows)
        all_returns: List of all stock 6-month returns for RS percentile ranking
    """
    result = MinerviniResult(ticker=ticker, scan_date=datetime.now().strftime("%Y-%m-%d"))

    try:
        if hist is None or len(hist) < 200:
            result.error = f"Insufficient data ({len(hist) if hist is not None else 0} days)"
            return result

        close = hist["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

        current_price = float(close.iloc[-1])
        result.price = round(current_price, 2)

        # Moving averages
        result.ma_50 = round(float(close.rolling(50).mean().iloc[-1]), 2)
        result.ma_150 = round(float(close.rolling(150).mean().iloc[-1]), 2)
        result.ma_200 = round(float(close.rolling(200).mean().iloc[-1]), 2)

        # 52-week high/low
        week_52 = close.iloc[-252:] if len(close) >= 252 else close
        result.week_52_high = round(float(week_52.max()), 2)
        result.week_52_low = round(float(week_52.min()), 2)

        # Percentages
        if result.week_52_low > 0:
            result.pct_above_low = round(((current_price - result.week_52_low) / result.week_52_low) * 100, 1)
        if result.week_52_high > 0:
            result.pct_from_high = round(((result.week_52_high - current_price) / result.week_52_high) * 100, 1)

        # 200-day MA slope (over 22 trading days = ~1 month)
        ma200_series = close.rolling(200).mean()
        if len(ma200_series.dropna()) >= 22:
            ma200_now = float(ma200_series.iloc[-1])
            ma200_1mo_ago = float(ma200_series.iloc[-22])
            if ma200_1mo_ago > 0:
                result.ma200_slope_22d = round(((ma200_now - ma200_1mo_ago) / ma200_1mo_ago) * 100, 3)

        # 6-month stock return for RS
        if len(close) >= 126:
            stock_6m_return = ((current_price / float(close.iloc[-126])) - 1) * 100
        else:
            stock_6m_return = 0.0

        # RS Rating (percentile rank within screened universe)
        if all_returns:
            result.rs_rating = compute_rs_rating(stock_6m_return, all_returns)
        else:
            result.rs_rating = 0.0

        # ═══════════════════════════════════════════════════════════
        # 8 CRITERIA CHECKS
        # ═══════════════════════════════════════════════════════════

        # C1: Price > 150-day MA AND Price > 200-day MA
        result.c1_price_above_150_200 = (current_price > result.ma_150) and (current_price > result.ma_200)

        # C2: 150-day MA > 200-day MA
        result.c2_ma150_above_ma200 = result.ma_150 > result.ma_200

        # C3: 200-day MA trending up for ≥1 month
        result.c3_ma200_trending_up = result.ma200_slope_22d > 0

        # C4: 50-day MA > 150-day MA > 200-day MA (full alignment)
        result.c4_ma_alignment = (result.ma_50 > result.ma_150 > result.ma_200)

        # C5: Price > 50-day MA
        result.c5_price_above_50 = current_price > result.ma_50

        # C6: Price ≥ 30% above 52-week low
        result.c6_above_low_30pct = result.pct_above_low >= 30.0

        # C7: Price within 25% of 52-week high
        result.c7_within_high_25pct = result.pct_from_high <= 25.0

        # C8: RS ≥ 70
        result.c8_rs_above_70 = result.rs_rating >= 70.0

        # Count passed criteria
        criteria = [
            result.c1_price_above_150_200, result.c2_ma150_above_ma200,
            result.c3_ma200_trending_up, result.c4_ma_alignment,
            result.c5_price_above_50, result.c6_above_low_30pct,
            result.c7_within_high_25pct, result.c8_rs_above_70,
        ]
        result.criteria_passed = sum(criteria)
        result.passes_template = all(criteria)

    except Exception as e:
        result.error = str(e)

    return result


def run_screen(tickers: list[str], universe_label: str = "custom",
               progress_callback=None) -> list[MinerviniResult]:
    """
    Run the full Minervini screen on a list of tickers.

    Args:
        tickers: List of ticker symbols
        universe_label: Label for the universe (for tracking)
        progress_callback: Optional callable(msg: str) for progress updates

    Returns:
        List of MinerviniResult, sorted by criteria_passed desc then rs_rating desc
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg, file=sys.stderr)

    # Deduplicate
    tickers = list(set(t.upper().strip() for t in tickers if t.strip()))
    log(f"Screening {len(tickers)} tickers from [{universe_label}]...")

    # Batch download all tickers (yfinance handles batching efficiently)
    log(f"Batch downloading {len(tickers)} tickers (this may take 30-60 seconds)...")

    # Download in chunks to avoid timeout
    chunk_size = 50
    all_data = {}
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        log(f"  Downloading batch {i // chunk_size + 1}/{(len(tickers) + chunk_size - 1) // chunk_size}...")
        try:
            data = yf.download(chunk, period="1y", progress=False, auto_adjust=True, group_by="ticker")
            if len(chunk) == 1:
                all_data[chunk[0]] = data
            else:
                for t in chunk:
                    try:
                        ticker_data = data[t] if t in data.columns.get_level_values(0) else None
                        if ticker_data is not None and not ticker_data.empty:
                            all_data[t] = ticker_data
                    except (KeyError, TypeError):
                        pass
        except Exception as e:
            log(f"  Batch error: {e}")

    log(f"Downloaded data for {len(all_data)}/{len(tickers)} tickers")

    # First pass: compute 6-month returns for RS percentile ranking
    all_6m_returns = []
    for t, hist in all_data.items():
        try:
            close = hist["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            if len(close) >= 126:
                ret = ((float(close.iloc[-1]) / float(close.iloc[-126])) - 1) * 100
                all_6m_returns.append(ret)
        except Exception:
            pass

    # Second pass: screen each ticker
    log("Running Minervini criteria checks...")
    results = []
    for t in tickers:
        hist = all_data.get(t)
        result = screen_ticker(t, hist, all_6m_returns)
        result.universe = universe_label
        results.append(result)

    # Sort: passes first, then by criteria count desc, then RS desc
    results.sort(key=lambda r: (r.passes_template, r.criteria_passed, r.rs_rating), reverse=True)

    # Summary
    passers = sum(1 for r in results if r.passes_template)
    near_miss = sum(1 for r in results if r.criteria_passed >= 6 and not r.passes_template)
    errors = sum(1 for r in results if r.error)
    log(f"\n{'='*50}")
    log(f"RESULTS: {passers} pass all 8 | {near_miss} near-miss (6-7/8) | {errors} errors")
    log(f"{'='*50}")

    return results


# ─────────────────────────────────────────────────────────────────────
# OUTPUT FORMATTERS
# ─────────────────────────────────────────────────────────────────────

def to_json(results: list[MinerviniResult]) -> str:
    """Convert results to JSON string."""
    return json.dumps([asdict(r) for r in results], indent=2)


def to_csv(results: list[MinerviniResult], filepath: str):
    """Write results to CSV file."""
    df = pd.DataFrame([asdict(r) for r in results])
    df.to_csv(filepath, index=False)
    return filepath


def print_summary(results: list[MinerviniResult]):
    """Print a compact summary table."""
    print(f"\n{'Ticker':<8} {'Price':>8} {'50MA':>8} {'150MA':>8} {'200MA':>8} "
          f"{'RS':>5} {'%Low':>6} {'%Hi':>5} {'Pass':>4} {'Grade'}")
    print("-" * 85)

    for r in results:
        if r.error:
            print(f"{r.ticker:<8} {'ERROR':>8} — {r.error[:50]}")
            continue

        grade = "★ PASS" if r.passes_template else f"  {r.criteria_passed}/8"
        print(f"{r.ticker:<8} {r.price:>8.2f} {r.ma_50:>8.2f} {r.ma_150:>8.2f} {r.ma_200:>8.2f} "
              f"{r.rs_rating:>5.1f} {r.pct_above_low:>5.1f}% {r.pct_from_high:>4.1f}% {r.criteria_passed:>3}/8 {grade}")


# ─────────────────────────────────────────────────────────────────────
# STATE TRACKER
# ─────────────────────────────────────────────────────────────────────

TRACKER_PATH = "/media/SHARED/trade-data/minervini/tracker.json"


def save_scan(results: list[MinerviniResult], universe: str):
    """Save scan results to tracker for longitudinal tracking."""
    import os

    try:
        with open(TRACKER_PATH) as f:
            tracker = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        tracker = {"scans": []}

    scan = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "universe": universe,
        "total_screened": len(results),
        "total_passing": sum(1 for r in results if r.passes_template),
        "near_miss": sum(1 for r in results if r.criteria_passed >= 6 and not r.passes_template),
        "passers": [r.ticker for r in results if r.passes_template],
        "near_missers": [r.ticker for r in results if r.criteria_passed >= 6 and not r.passes_template],
    }

    tracker["scans"].append(scan)
    tracker["scans"] = tracker["scans"][-50:]  # Keep last 50 scans

    os.makedirs(os.path.dirname(TRACKER_PATH), exist_ok=True)
    with open(TRACKER_PATH, "w") as f:
        json.dump(tracker, f, indent=2)

    return scan


def get_new_passers(results: list[MinerviniResult]) -> tuple[list[str], list[str]]:
    """Compare current passers to last scan. Returns (new_passers, dropped_passers)."""
    try:
        with open(TRACKER_PATH) as f:
            tracker = json.load(f)
        if len(tracker.get("scans", [])) < 2:
            return [], []
        last = set(tracker["scans"][-2].get("passers", []))
        current = set(r.ticker for r in results if r.passes_template)
        return list(current - last), list(last - current)
    except (FileNotFoundError, json.JSONDecodeError):
        return [], []


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Minervini Trend Template Screener")
    parser.add_argument("--universe", default="all",
                        choices=["all", "sp500", "nasdaq100", "watchlist"],
                        help="Ticker universe to screen")
    parser.add_argument("--tickers", type=str, default="",
                        help="Comma-separated custom tickers")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--csv", type=str, default="", help="Output CSV to filepath")
    parser.add_argument("--save", action="store_true", help="Save to tracker")
    args = parser.parse_args()

    # Build ticker list
    if args.tickers:
        tickers = args.tickers.upper().split(",")
        universe = "custom"
    else:
        tickers = get_universe(args.universe)
        universe = args.universe

    if not tickers:
        print("ERROR: No tickers to screen")
        sys.exit(1)

    # Run screen
    results = run_screen(tickers, universe)

    # Output
    if args.json:
        print(to_json(results))
    elif args.csv:
        to_csv(results, args.csv)
        print(f"Saved to {args.csv}")
    else:
        print_summary(results)

    # Save to tracker
    if args.save:
        scan = save_scan(results, universe)
        print(f"\nSaved scan: {scan['total_passing']} passers, {scan['near_miss']} near-miss")

    return results


if __name__ == "__main__":
    main()

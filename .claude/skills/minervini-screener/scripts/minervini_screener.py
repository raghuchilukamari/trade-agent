#!/usr/bin/env python3
"""
minervini_screener.py — Mark Minervini Trend Template Stock Screener

Screens stocks against all 8 SEPA Trend Template criteria using pre-computed
ta_daily data in PostgreSQL (populated by update_technicals.py):

  1. Price > 150-day MA AND Price > 200-day MA
  2. 150-day MA > 200-day MA
  3. 200-day MA trending up ≥ 1 month (22 trading days)
  4. 50-day MA > 150-day MA > 200-day MA (full alignment)
  5. Price > 50-day MA
  6. Price ≥ 30% above 52-week low
  7. Price within 25% of 52-week high
  8. Relative Strength (RS) ≥ 70 (percentile rank of rs_vs_spy)

Usage:
    python3 minervini_screener.py                          # Screen all tickers in ta_daily
    python3 minervini_screener.py --tickers AAPL,MSFT,NVDA # Custom tickers
    python3 minervini_screener.py --json                   # Output JSON (for dashboard)
    python3 minervini_screener.py --csv results.csv        # Output CSV file
    python3 minervini_screener.py --save                   # Save to tracker JSON
"""

import sys
import json
import os
import warnings
import argparse
from datetime import datetime
from dataclasses import dataclass, asdict

warnings.filterwarnings("ignore")

try:
    import pandas as pd
    from sqlalchemy import create_engine, text
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: pip install pandas sqlalchemy psycopg2-binary python-dotenv")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────
# DB CONNECTION
# ─────────────────────────────────────────────────────────────────────

load_dotenv()

_DB_USER = os.getenv("PG_USER", os.getenv("POSTGRES_USER", ""))
_DB_PASS = os.getenv("PG_PASS", os.getenv("POSTGRES_PASSWORD", ""))
_DB_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
_DB_PORT = os.getenv("POSTGRES_PORT", "5432")
_DB_NAME = os.getenv("POSTGRES_DB", "postgres")

_PG_CONN = f"postgresql://{_DB_USER}:{_DB_PASS}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"


def get_engine():
    return create_engine(_PG_CONN)


# ─────────────────────────────────────────────────────────────────────
# RESULT DATACLASS
# ─────────────────────────────────────────────────────────────────────

@dataclass
class MinerviniResult:
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
    ma200_slope_22d: float = 0.0

    c1_price_above_150_200: bool = False
    c2_ma150_above_ma200: bool = False
    c3_ma200_trending_up: bool = False
    c4_ma_alignment: bool = False
    c5_price_above_50: bool = False
    c6_above_low_30pct: bool = False
    c7_within_high_25pct: bool = False
    c8_rs_above_70: bool = False

    criteria_passed: int = 0
    total_criteria: int = 8
    passes_template: bool = False
    error: str = ""

    universe: str = ""
    scan_date: str = ""


# ─────────────────────────────────────────────────────────────────────
# SCREENING ENGINE (PostgreSQL-backed)
# ─────────────────────────────────────────────────────────────────────

def load_ta_data(engine, tickers: list[str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load latest ta_daily rows + 22-days-ago sma200 for MA slope.
    Returns (latest_df, slope_df).
    """
    ticker_filter = ""
    params = {}
    if tickers:
        ticker_filter = "AND ticker = ANY(:tickers)"
        params["tickers"] = tickers

    # Latest date available in ta_daily — use most recent date with full coverage.
    # Guards against partial yfinance updates (e.g. today has 3 tickers, yesterday has 1472).
    # Pick the most recent date that has >= 90% of the max ticker count across any date.
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT date FROM ta_daily
            GROUP BY date
            HAVING COUNT(*) >= (
                SELECT MAX(cnt) * 0.9 FROM (SELECT COUNT(*) AS cnt FROM ta_daily GROUP BY date) sub
            )
            ORDER BY date DESC LIMIT 1
        """)).fetchone()
        latest_date = row[0] if row else None

    if latest_date is None:
        raise RuntimeError("ta_daily is empty — run update_technicals.py --mode init first")

    print(f"  Screening using ta_daily as of {latest_date}", file=sys.stderr)

    # Latest row for each ticker
    latest_sql = text(f"""
        SELECT ticker, close, sma50, sma150, sma200, week_52_high, week_52_low,
               rs_vs_spy, date
        FROM ta_daily
        WHERE date = :latest_date
        {ticker_filter}
    """)
    params["latest_date"] = latest_date

    # 22 trading days ago sma200 (for MA200 slope criterion)
    slope_sql = text(f"""
        SELECT ticker, sma200 AS sma200_22d
        FROM (
            SELECT ticker, sma200, date,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
            FROM ta_daily
            WHERE date < :latest_date
            {ticker_filter}
        ) sub
        WHERE rn = 22
    """)

    with engine.connect() as conn:
        latest_df = pd.read_sql(latest_sql, conn, params=params)
        slope_df  = pd.read_sql(slope_sql,  conn, params=params)

    return latest_df, slope_df


def compute_rs_percentile(rs_vs_spy_series: pd.Series) -> pd.Series:
    """Rank rs_vs_spy values as percentile (1-99) within the screened universe."""
    return rs_vs_spy_series.rank(pct=True) * 100


def screen_from_db(tickers: list[str] | None, universe_label: str,
                   log=None) -> list[MinerviniResult]:
    """
    Core screening function. Loads ta_daily from PostgreSQL, applies all 8 criteria.
    """
    if log is None:
        log = lambda msg: print(msg, file=sys.stderr)

    engine = get_engine()

    log(f"Loading ta_daily from PostgreSQL for [{universe_label}]...")
    latest_df, slope_df = load_ta_data(engine, tickers)

    if latest_df.empty:
        log("ERROR: No data found in ta_daily for the requested tickers")
        return []

    log(f"  {len(latest_df)} tickers loaded")

    # Merge 22d-ago sma200 for slope computation
    df = latest_df.merge(slope_df, on="ticker", how="left")

    # Compute RS percentile within this screened universe
    df["rs_rating"] = compute_rs_percentile(df["rs_vs_spy"].fillna(0))

    results = []
    scan_date = datetime.now().strftime("%Y-%m-%d")

    for _, row in df.iterrows():
        r = MinerviniResult(ticker=row["ticker"], scan_date=scan_date, universe=universe_label)

        try:
            price    = float(row["close"]) if pd.notna(row["close"]) else None
            ma50     = float(row["sma50"])   if pd.notna(row["sma50"])   else None
            ma150    = float(row["sma150"])  if pd.notna(row["sma150"])  else None
            ma200    = float(row["sma200"])  if pd.notna(row["sma200"])  else None
            hi52     = float(row["week_52_high"]) if pd.notna(row["week_52_high"]) else None
            lo52     = float(row["week_52_low"])  if pd.notna(row["week_52_low"])  else None
            ma200_22 = float(row["sma200_22d"])   if pd.notna(row.get("sma200_22d")) else None
            rs       = float(row["rs_rating"])

            if price is None or ma50 is None or ma150 is None or ma200 is None:
                r.error = "Missing indicator data"
                results.append(r)
                continue

            r.price        = round(price, 2)
            r.ma_50        = round(ma50, 2)
            r.ma_150       = round(ma150, 2)
            r.ma_200       = round(ma200, 2)
            r.week_52_high = round(hi52, 2) if hi52 else 0.0
            r.week_52_low  = round(lo52, 2) if lo52 else 0.0
            r.rs_rating    = round(rs, 1)

            if lo52 and lo52 > 0:
                r.pct_above_low = round(((price - lo52) / lo52) * 100, 1)
            if hi52 and hi52 > 0:
                r.pct_from_high = round(((hi52 - price) / hi52) * 100, 1)

            if ma200_22 and ma200_22 > 0:
                r.ma200_slope_22d = round(((ma200 - ma200_22) / ma200_22) * 100, 3)

            # ── 8 Criteria ──────────────────────────────────────────
            r.c1_price_above_150_200 = (price > ma150) and (price > ma200)
            r.c2_ma150_above_ma200   = ma150 > ma200
            r.c3_ma200_trending_up   = r.ma200_slope_22d > 0
            r.c4_ma_alignment        = (ma50 > ma150 > ma200)
            r.c5_price_above_50      = price > ma50
            r.c6_above_low_30pct     = r.pct_above_low >= 30.0
            r.c7_within_high_25pct   = r.pct_from_high <= 25.0
            r.c8_rs_above_70         = rs >= 70.0

            criteria = [
                r.c1_price_above_150_200, r.c2_ma150_above_ma200,
                r.c3_ma200_trending_up,   r.c4_ma_alignment,
                r.c5_price_above_50,      r.c6_above_low_30pct,
                r.c7_within_high_25pct,   r.c8_rs_above_70,
            ]
            r.criteria_passed  = sum(criteria)
            r.passes_template  = all(criteria)

        except Exception as e:
            r.error = str(e)

        results.append(r)

    results.sort(key=lambda r: (r.passes_template, r.criteria_passed, r.rs_rating), reverse=True)

    passers   = sum(1 for r in results if r.passes_template)
    near_miss = sum(1 for r in results if r.criteria_passed >= 6 and not r.passes_template)
    errors    = sum(1 for r in results if r.error)
    log(f"\n{'='*50}")
    log(f"RESULTS: {passers} pass all 8 | {near_miss} near-miss (6-7/8) | {errors} errors")
    log(f"{'='*50}")

    # Write is_minervini + minervini_score back to ta_daily for the latest date
    with engine.connect() as conn:
        _latest = conn.execute(text("SELECT MAX(date) FROM ta_daily")).scalar()
    _write_scores_to_db(engine, results, _latest)

    return results


def _write_scores_to_db(engine, results: list[MinerviniResult], latest_date):
    """UPDATE ta_daily SET is_minervini, minervini_score for the latest date."""
    rows = [
        {"ticker": r.ticker, "is_minervini": r.passes_template, "minervini_score": r.criteria_passed}
        for r in results if not r.error
    ]
    if not rows:
        return
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE ta_daily SET is_minervini = :is_minervini, minervini_score = :minervini_score
            WHERE ticker = :ticker AND date = :latest_date
        """), [{"ticker": r["ticker"], "is_minervini": r["is_minervini"],
                "minervini_score": r["minervini_score"], "latest_date": latest_date}
               for r in rows])
    print(f"  Written is_minervini + minervini_score for {len(rows)} tickers (date={latest_date})", file=sys.stderr)


# ─────────────────────────────────────────────────────────────────────
# OUTPUT FORMATTERS
# ─────────────────────────────────────────────────────────────────────

def to_json(results: list[MinerviniResult]) -> str:
    return json.dumps([asdict(r) for r in results], indent=2)


def to_csv(results: list[MinerviniResult], filepath: str):
    df = pd.DataFrame([asdict(r) for r in results])
    df.to_csv(filepath, index=False)
    return filepath


def print_summary(results: list[MinerviniResult]):
    print(f"\n{'Ticker':<8} {'Price':>8} {'50MA':>8} {'150MA':>8} {'200MA':>8} "
          f"{'RS':>5} {'%Low':>6} {'%Hi':>5} {'Pass':>4} {'Grade'}")
    print("-" * 85)
    for r in results:
        if r.error:
            print(f"{r.ticker:<8} {'ERROR':>8} — {r.error[:50]}")
            continue
        grade = "★ PASS" if r.passes_template else f"  {r.criteria_passed}/8"
        print(f"{r.ticker:<8} {r.price:>8.2f} {r.ma_50:>8.2f} {r.ma_150:>8.2f} {r.ma_200:>8.2f} "
              f"{r.rs_rating:>5.1f} {r.pct_above_low:>5.1f}% {r.pct_from_high:>4.1f}% "
              f"{r.criteria_passed:>3}/8 {grade}")


# ─────────────────────────────────────────────────────────────────────
# STATE TRACKER
# ─────────────────────────────────────────────────────────────────────

TRACKER_PATH = "/media/SHARED/trade-data/minervini/tracker.json"


def save_scan(results: list[MinerviniResult], universe: str, engine=None):
    scan_date = datetime.now().strftime("%Y-%m-%d")
    current_passers = [r.ticker for r in results if r.passes_template]

    new_additions = []
    new_removals = []
    scan = {}
    if engine:
        with engine.connect() as conn:
            # 1. Get the latest record before today
            prev_row = conn.execute(text("""
                SELECT passers FROM dashboard.minervini_tracker 
                WHERE scan_date < :current_date 
                ORDER BY scan_date DESC LIMIT 1
            """), {"current_date": scan_date}).fetchone()

            if prev_row:
                last_passers = set(prev_row[0])  # Extract the list from the row
                current_set = set(current_passers)
                new_additions = list(current_set - last_passers)
                new_removals = list(last_passers - current_set)

        # 2. Insert today's data with calculated deltas
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO dashboard.minervini_tracker
                    (scan_date, total_screened, total_passing, near_miss,
                     passers, new_additions, new_removals, results_json)
                VALUES (:scan_date, :total_screened, :total_passing, :near_miss,
                        :passers, :new_additions, :new_removals, :results_json)
                ON CONFLICT (scan_date) DO UPDATE SET
                    total_passing = EXCLUDED.total_passing,
                    passers = EXCLUDED.passers,
                    new_additions = EXCLUDED.new_additions,
                    new_removals = EXCLUDED.new_removals,
                    results_json = EXCLUDED.results_json
            """), {
                "scan_date": scan_date,
                "total_screened": len(results),
                "total_passing": len(current_passers),
                "near_miss": sum(1 for r in results if r.criteria_passed >= 6 and not r.passes_template),
                "passers": current_passers,
                "new_additions": new_additions,
                "new_removals": new_removals,
                "results_json": json.dumps([asdict(r) for r in results])
            })
            print(f"  Inserted scan for {scan_date} into dashboard.minervini_tracker", file=sys.stderr)

        scan = {
            "date": scan_date,
            "universe": universe,
            "total_screened": len(results),
            "total_passing": sum(1 for r in results if r.passes_template),
            "near_miss": sum(1 for r in results if r.criteria_passed >= 6 and not r.passes_template),
            "passers": [r.ticker for r in results if r.passes_template],
            "near_missers": [r.ticker for r in results if r.criteria_passed >= 6 and not r.passes_template],
            "new_additions": new_additions,
            "new_removals": new_removals
        }

    return scan



# def save_scan(results: list[MinerviniResult], universe: str, engine=None):
#     try:
#         with open(TRACKER_PATH) as f:
#             tracker = json.load(f)
#     except (FileNotFoundError, json.JSONDecodeError):
#         tracker = {"scans": []}
#
#     scan = {
#         "date": datetime.now().strftime("%Y-%m-%d"),
#         "universe": universe,
#         "total_screened": len(results),
#         "total_passing": sum(1 for r in results if r.passes_template),
#         "near_miss": sum(1 for r in results if r.criteria_passed >= 6 and not r.passes_template),
#         "passers": [r.ticker for r in results if r.passes_template],
#         "near_missers": [r.ticker for r in results if r.criteria_passed >= 6 and not r.passes_template],
#     }
#
#     tracker["scans"].append(scan)
#     tracker["scans"] = tracker["scans"][-50:]
#
#     os.makedirs(os.path.dirname(TRACKER_PATH), exist_ok=True)
#     with open(TRACKER_PATH, "w") as f:
#         json.dump(tracker, f, indent=2)
#
#     if engine:
#         # Save to dashboard.minervini_tracker table
#         with engine.begin() as conn:
#             conn.execute(text("""
#                 INSERT INTO dashboard.minervini_tracker
#                     (scan_date, total_screened, total_passing, near_miss,
#                      passers, new_additions, new_removals, results_json)
#                 VALUES (:scan_date, :total_screened, :total_passing, :near_miss,
#                         :passers, :new_additions, :new_removals, :results_json)
#                 ON CONFLICT (scan_date) DO UPDATE SET
#                     total_screened = EXCLUDED.total_screened,
#                     total_passing = EXCLUDED.total_passing,
#                     near_miss = EXCLUDED.near_miss,
#                     passers = EXCLUDED.passers,
#                     new_additions = EXCLUDED.new_additions,
#                     new_removals = EXCLUDED.new_removals,
#                     results_json = EXCLUDED.results_json
#             """), {
#                 "scan_date": scan["date"],
#                 "total_screened": scan["total_screened"],
#                 "total_passing": scan["total_passing"],
#                 "near_miss": scan["near_miss"],
#                 "passers": scan["passers"],
#                 "new_additions": [], # Optional: fill this later if we check state
#                 "new_removals": [],
#                 "results_json": json.dumps([asdict(r) for r in results])
#             })
#             print(f"  Inserted scan into dashboard.minervini_tracker", file=sys.stderr)
#
#     return scan


def get_new_passers(results: list[MinerviniResult]) -> tuple[list[str], list[str]]:
    try:
        with open(TRACKER_PATH) as f:
            tracker = json.load(f)
        if len(tracker.get("scans", [])) < 2:
            return [], []
        last    = set(tracker["scans"][-2].get("passers", []))
        current = set(r.ticker for r in results if r.passes_template)
        return list(current - last), list(last - current)
    except (FileNotFoundError, json.JSONDecodeError):
        return [], []

def check_already_run(engine, scan_date):
    """Rule: No redundant runs. Checks if today's date exists in the tracker."""
    with engine.connect() as conn:
        exists = conn.execute(text(
            "SELECT 1 FROM dashboard.minervini_tracker WHERE scan_date = :d"
        ), {"d": scan_date}).scalar()
    return bool(exists)

# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Minervini Trend Template Screener (PostgreSQL-backed)")
    parser.add_argument("--tickers", type=str, default="",
                        help="Comma-separated tickers to screen (default: all in ta_daily)")
    parser.add_argument("--json",   action="store_true", help="Output JSON")
    parser.add_argument("--csv",    type=str, default="", help="Output CSV to filepath")
    parser.add_argument("--save",   action="store_true", help="Save scan to tracker JSON")
    args = parser.parse_args()

    tickers   = [t.strip().upper() for t in args.tickers.split(",") if t.strip()] if args.tickers else None
    universe  = "custom" if tickers else "all_ta_daily"
    engine = get_engine()

    scan_date = datetime.now().strftime("%Y-%m-%d")

    # PRE-FLIGHT CHECK
    if check_already_run(engine, scan_date):
        print(f"[-] Minvervini Screen already ran for {scan_date}. Fetch results directly from db, Skipping run.", file=sys.stderr)
        return

    results = screen_from_db(tickers, universe)


    scan = save_scan(results, universe, engine)
    new_in, dropped = scan['new_additions'], scan['new_removals']
    print(f"\nSaved scan: {scan['total_passing']} passers, {scan['near_miss']} near-miss")
    if new_in:
        print(f"NEW ADDITIONS: {', '.join(new_in)}")
    if dropped:
        print(f"DROPPED FROM YESTERDAY: {', '.join(dropped)}")

    # if not results:
    #     print("No results.")
    #     sys.exit(1)
    #
    # if args.json:
    #     print(to_json(results))
    # elif args.csv:
    #     to_csv(results, args.csv)
    #     print(f"Saved to {args.csv}")
    # else:
    #     print_summary(results)
    #
    # if args.save:
    #     engine = get_engine()
    #     scan = save_scan(results, universe, engine)
    #     new_in, dropped = scan['new_additions'], scan['new_removals']
    #     print(f"\nSaved scan: {scan['total_passing']} passers, {scan['near_miss']} near-miss")
    #     if new_in:
    #         print(f"NEW: {', '.join(new_in)}")
    #     if dropped:
    #         print(f"DROPPED: {', '.join(dropped)}")

    return scan


if __name__ == "__main__":
    main()
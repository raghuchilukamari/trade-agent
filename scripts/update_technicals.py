#!/usr/bin/env python3
"""
update_technicals.py — Fetch OHLC via yfinance, compute TA indicators → ohlc_daily + ta_daily

Default universe: SP500 + DOW30 + IWM (Russell 2000 ETF) constituents/members.
Additional tickers can be passed via --tickers.

Two modes:
  --mode init    Truncate both tables, download ~2 years of OHLC + compute all indicators.
  --mode daily   Incremental: download latest bar and upsert.

Usage:
    python3 scripts/update_technicals.py --mode init
    python3 scripts/update_technicals.py --mode daily
    python3 scripts/update_technicals.py --mode daily --tickers TSEM OKLO ASTS
"""

import argparse
import os
import warnings

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

load_dotenv()

DB_USER = os.getenv("PG_USER", os.getenv("POSTGRES_USER", ""))
DB_PASS = os.getenv("PG_PASS", os.getenv("POSTGRES_PASSWORD", ""))
DB_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "postgres")

PG_CONN_STR = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

DOW_30 = [
    "AAPL", "AMGN", "AMZN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
    "GS", "HD", "HON", "IBM", "INTC", "JNJ", "JPM", "KO", "MCD", "MMM",
    "MRK", "MSFT", "NKE", "NVDA", "PG", "TRV", "UNH", "V", "VZ", "WMT",
]

# Always include these ETFs as benchmarks / for RS computation
BENCHMARKS = ["SPY", "QQQ", "DIA", "IWM"]


# ─────────────────────────────────────────────────────────────
# UNIVERSE LOADERS
# ─────────────────────────────────────────────────────────────

def get_sp500_tickers() -> list[str]:
    """Fetch current S&P 500 constituents from Wikipedia."""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = pd.read_html(requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15).text)
        tickers = tables[0]["Symbol"].tolist()
        tickers = [t.replace(".", "-") for t in tickers]
        print(f"  SP500: {len(tickers)} tickers from Wikipedia")
        return tickers
    except Exception as e:
        print(f"  [WARN] SP500 Wikipedia fetch failed: {e}")
        return []


def get_russell2000_tickers() -> list[str]:
    """Fetch Russell 2000 constituents from iShares IWM holdings CSV."""
    try:
        url = (
            "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/"
            "1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
        )
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        resp.raise_for_status()
        # iShares CSV has a few header rows before the actual data
        from io import StringIO
        lines = resp.text.splitlines()
        # Find the header row (contains "Ticker")
        header_idx = next((i for i, l in enumerate(lines) if "Ticker" in l), None)
        if header_idx is None:
            raise ValueError("Could not find Ticker column in IWM holdings CSV")
        df = pd.read_csv(StringIO("\n".join(lines[header_idx:])))
        tickers = df["Ticker"].dropna().tolist()
        # Filter out non-equity rows (cash, "-", etc.)
        tickers = [t.strip() for t in tickers if isinstance(t, str) and t.strip() and t != "-" and len(t) <= 6]
        tickers = [t.replace(".", "-") for t in tickers]
        print(f"  Russell2000: {len(tickers)} tickers from iShares IWM")
        return tickers
    except Exception as e:
        print(f"  [WARN] Russell 2000 iShares fetch failed: {e}")
        return []


def build_universe(extra_tickers: list[str]) -> list[str]:
    """Combine SP500 + DOW30 + Russell2000 + benchmarks + any extra tickers, deduplicated."""
    sp500 = get_sp500_tickers()
    r2000 = get_russell2000_tickers()
    universe = set(sp500) | set(r2000) | set(DOW_30) | set(BENCHMARKS) | set(extra_tickers)
    result = sorted(universe)
    print(f"  Universe: {len(result)} unique tickers (SP500={len(sp500)}, R2000={len(r2000)}, DOW30={len(DOW_30)}, extras={len(extra_tickers)})")
    return result


# ─────────────────────────────────────────────────────────────
# TA COMPUTATION
# ─────────────────────────────────────────────────────────────

def compute_macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    macd_hist = macd - macd_signal
    return macd, macd_signal, macd_hist


def compute_rsi(close: pd.Series, window=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=window - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=window - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_bb(close: pd.Series, window=20, num_std=2):
    mid = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower


def bb_position(close, upper, lower, mid):
    if pd.isna(close) or pd.isna(mid):
        return "NA"
    if not pd.isna(upper) and close > upper:
        return "above_upper"
    if not pd.isna(lower) and close < lower:
        return "below_lower"
    if close < mid:
        return "lower_half"
    return "upper_half"


def macd_state(hist):
    if pd.isna(hist):
        return "NA"
    if hist > 0:
        return "bullish"
    if hist < 0:
        return "bearish"
    return "neutral"


def bowtie_signal(row):
    e20, e30, s50 = row.get("ema20"), row.get("ema30"), row.get("sma50")
    pe20, pe30, ps50 = row.get("prev_ema20"), row.get("prev_ema30"), row.get("prev_sma50")
    if any(pd.isna(v) for v in [e20, e30, s50, pe20, pe30, ps50]):
        return "none"
    if e20 > e30 > s50 and e20 > pe20 and e30 > pe30 and s50 > ps50:
        return "bowtie_up"
    if e20 < e30 < s50 and e20 < pe20 and e30 < pe30 and s50 < ps50:
        return "bowtie_down"
    return "none"


def compute_ta(df: pd.DataFrame) -> pd.DataFrame:
    close = df["Close"]
    df["sma200"] = close.rolling(200).mean()
    df["sma150"] = close.rolling(150).mean()
    df["sma50"]  = close.rolling(50).mean()
    df["sma10"]  = close.rolling(10).mean()
    df["ema20"]  = close.ewm(span=20, adjust=False).mean()
    df["ema30"]  = close.ewm(span=30, adjust=False).mean()
    df["macd"], df["macd_signal"], df["macd_hist"] = compute_macd(close)
    df["rsi"]    = compute_rsi(close)
    df["bb_mid"], df["bb_upper"], df["bb_lower"] = compute_bb(close)
    df["week_52_high"] = close.rolling(252, min_periods=20).max()
    df["week_52_low"]  = close.rolling(252, min_periods=20).min()
    df["prev_ema20"] = df["ema20"].shift(1)
    df["prev_ema30"] = df["ema30"].shift(1)
    df["prev_sma50"] = df["sma50"].shift(1)
    return df


# ─────────────────────────────────────────────────────────────
# DATA FETCH
# ─────────────────────────────────────────────────────────────

BATCH_SIZE = 100  # yfinance handles ~100 tickers well per call

def fetch_ohlc(tickers: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    """Download adjusted OHLCV in batches. Returns {ticker: df}."""
    result: dict[str, pd.DataFrame] = {}
    batches = [tickers[i:i + BATCH_SIZE] for i in range(0, len(tickers), BATCH_SIZE)]
    print(f"  Downloading {len(tickers)} tickers in {len(batches)} batches (period={period})...")

    for b_idx, batch in enumerate(batches, 1):
        print(f"  Batch {b_idx}/{len(batches)} ({len(batch)} tickers)...", flush=True)
        try:
            raw = yf.download(
                batch,
                period=period,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as e:
            print(f"  [WARN] Batch {b_idx} download failed: {e}")
            continue

        if raw.empty:
            continue

        if len(batch) == 1:
            ticker = batch[0]
            df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
            df = df.dropna(subset=["Close"])
            df.index = pd.to_datetime(df.index).date
            if not df.empty:
                result[ticker] = df
        else:
            for ticker in batch:
                try:
                    df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close", "Volume"]].copy()
                    df = df.dropna(subset=["Close"])
                    df.index = pd.to_datetime(df.index).date
                    if not df.empty:
                        result[ticker] = df
                except Exception:
                    pass

    print(f"  Fetched data for {len(result)}/{len(tickers)} tickers")
    return result


# ─────────────────────────────────────────────────────────────
# RS (Relative Strength vs SPY/QQQ)
# ─────────────────────────────────────────────────────────────

def compute_rs(close_series: pd.Series, bench_series: pd.Series, window=21) -> pd.Series:
    t_ret = close_series.pct_change(window)
    b_ret = bench_series.reindex(close_series.index).pct_change(window)
    return t_ret - b_ret


# ─────────────────────────────────────────────────────────────
# BUILD OUTPUT ROWS
# ─────────────────────────────────────────────────────────────

def build_ta_rows(
    ticker: str,
    ohlc_df: pd.DataFrame,
    spy_close: pd.Series | None,
    qqq_close: pd.Series | None,
) -> tuple[list[dict], list[dict]]:
    df = ohlc_df.copy()
    df = compute_ta(df)

    rs_spy = compute_rs(df["Close"], spy_close, 21) if spy_close is not None else pd.Series(dtype=float)
    rs_qqq = compute_rs(df["Close"], qqq_close, 21) if qqq_close is not None else pd.Series(dtype=float)

    ohlc_rows, ta_rows = [], []

    for d, row in df.iterrows():
        close = row["Close"]
        if pd.isna(close):
            continue

        ohlc_rows.append({
            "ticker": ticker,
            "date": d,
            "open": row.get("Open"),
            "high": row.get("High"),
            "low": row.get("Low"),
            "close": close,
            "volume": row.get("Volume"),
            "adj_close": close,
        })

        ta_rows.append({
            "ticker": ticker,
            "date": d,
            "close": close,
            "sma200":      None if pd.isna(row["sma200"])      else float(row["sma200"]),
            "sma150":      None if pd.isna(row["sma150"])      else float(row["sma150"]),
            "sma10":       None if pd.isna(row["sma10"])       else float(row["sma10"]),
            "ema20":       None if pd.isna(row["ema20"])       else float(row["ema20"]),
            "ema30":       None if pd.isna(row["ema30"])       else float(row["ema30"]),
            "sma50":       None if pd.isna(row["sma50"])       else float(row["sma50"]),
            "week_52_high": None if pd.isna(row["week_52_high"]) else float(row["week_52_high"]),
            "week_52_low":  None if pd.isna(row["week_52_low"])  else float(row["week_52_low"]),
            "macd":        None if pd.isna(row["macd"])        else float(row["macd"]),
            "macd_signal": None if pd.isna(row["macd_signal"]) else float(row["macd_signal"]),
            "macd_hist":   None if pd.isna(row["macd_hist"])   else float(row["macd_hist"]),
            "macd_state":  macd_state(row["macd_hist"]),
            "rsi":         None if pd.isna(row["rsi"])         else float(row["rsi"]),
            "bb_mid":      None if pd.isna(row["bb_mid"])      else float(row["bb_mid"]),
            "bb_upper":    None if pd.isna(row["bb_upper"])    else float(row["bb_upper"]),
            "bb_lower":    None if pd.isna(row["bb_lower"])    else float(row["bb_lower"]),
            "bb_position": bb_position(close, row["bb_upper"], row["bb_lower"], row["bb_mid"]),
            "rs_vs_spy":   None if d not in rs_spy.index or pd.isna(rs_spy.get(d)) else float(rs_spy[d]),
            "rs_vs_qqq":   None if d not in rs_qqq.index or pd.isna(rs_qqq.get(d)) else float(rs_qqq[d]),
            "bowtie_signal":   bowtie_signal(row),
            "is_minervini":    False,
            "minervini_score": 0,
        })

    return ohlc_rows, ta_rows


# ─────────────────────────────────────────────────────────────
# DB WRITE
# ─────────────────────────────────────────────────────────────

def truncate_tables(engine):
    print("  Dropping ohlc_daily and ta_daily (will be recreated with correct schema)...")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS ohlc_daily"))
        conn.execute(text("DROP TABLE IF EXISTS ta_daily"))
    print("  Done.")


def write_ohlc(rows: list[dict], engine, replace: bool = False):
    if not rows:
        return
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    if replace:
        df.to_sql("ohlc_daily", engine, if_exists="replace", index=False)
        print(f"  ohlc_daily: {len(df)} rows written")
    else:
        dates = df["date"].unique().tolist()
        with engine.begin() as conn:
            for d in dates:
                conn.execute(text("DELETE FROM ohlc_daily WHERE date = :d"), {"d": d})
        df.to_sql("ohlc_daily", engine, if_exists="append", index=False)
        print(f"  ohlc_daily: upserted {len(df)} rows")


def write_ta(rows: list[dict], engine, replace: bool = False):
    if not rows:
        return
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    if replace:
        df.to_sql("ta_daily", engine, if_exists="replace", index=False)
        print(f"  ta_daily: {len(df)} rows written")
    else:
        dates = df["date"].unique().tolist()
        with engine.begin() as conn:
            for d in dates:
                conn.execute(text("DELETE FROM ta_daily WHERE date = :d"), {"d": d})
        df.to_sql("ta_daily", engine, if_exists="append", index=False)
        print(f"  ta_daily: upserted {len(df)} rows")


# ─────────────────────────────────────────────────────────────
# MODES
# ─────────────────────────────────────────────────────────────

def run_init(engine, extra_tickers: list[str]):
    tickers = build_universe(extra_tickers)
    truncate_tables(engine)

    ohlc_data = fetch_ohlc(tickers, period="2y")
    spy_close = ohlc_data.get("SPY", pd.DataFrame()).get("Close")
    qqq_close = ohlc_data.get("QQQ", pd.DataFrame()).get("Close")

    all_ohlc, all_ta = [], []
    for i, ticker in enumerate(tickers, 1):
        if ticker not in ohlc_data:
            continue
        o, t = build_ta_rows(ticker, ohlc_data[ticker], spy_close, qqq_close)
        all_ohlc.extend(o)
        all_ta.extend(t)
        if i % 50 == 0:
            print(f"  Computed TA for {i}/{len(tickers)} tickers...")

    write_ohlc(all_ohlc, engine, replace=True)
    write_ta(all_ta, engine, replace=True)
    print(f"[INIT] Done. {len(tickers)} tickers, {len(all_ta)} TA rows.")


def run_daily(engine, extra_tickers: list[str]):
    tickers = build_universe(extra_tickers)
    # Fetch 1y so rolling windows (SMA200) have enough history to compute correctly
    ohlc_data = fetch_ohlc(tickers, period="1y")
    spy_close = ohlc_data.get("SPY", pd.DataFrame()).get("Close")
    qqq_close = ohlc_data.get("QQQ", pd.DataFrame()).get("Close")

    all_ohlc, all_ta = [], []
    for ticker in tickers:
        if ticker not in ohlc_data or ohlc_data[ticker].empty:
            continue
        o, t = build_ta_rows(ticker, ohlc_data[ticker], spy_close, qqq_close)
        if o:
            all_ohlc.append(o[-1])
        if t:
            all_ta.append(t[-1])

    write_ohlc(all_ohlc, engine, replace=False)
    write_ta(all_ta, engine, replace=False)
    print(f"[DAILY] Done. {len(all_ta)} tickers updated.")


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Update OHLC + technicals in PostgreSQL via yfinance")
    parser.add_argument(
        "--mode",
        choices=["init", "daily"],
        default="daily",
        help="init = truncate + full 2yr rebuild, daily = incremental latest bar (default: daily)",
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=[],
        metavar="TICKER",
        help="Additional tickers to include beyond SP500+DOW30+benchmarks",
    )
    args = parser.parse_args()

    engine = create_engine(PG_CONN_STR)
    print(f"[update_technicals] mode={args.mode}, extra_tickers={args.tickers or 'none'}")

    if args.mode == "init":
        run_init(engine, args.tickers)
    else:
        run_daily(engine, args.tickers)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
update_technicals.py — Fetch OHLC via yfinance, compute TA indicators → ohlc_daily + ta_daily

Default universe: SP500 + DOW30 + IWM (Russell 2000 ETF) constituents/members.
Additional tickers can be passed via --tickers.

Two modes:
  --mode init    Truncate both tables, download ~2 years of OHLC + compute all indicators.
  --mode daily   Incremental: download latest bar and upsert.
  --mode scan    Runs scanners that picks momentum stocks

Usage:
    python3 scripts/update_technicals.py --mode init
    - Run all steps of the pipeline
    python3 scripts/update_technicals.py --mode daily --tickers TSEM OKLO ASTS
    python3 scripts/update_technicals.py --mode scan
"""

import argparse
import os
import warnings
from datetime import datetime
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

# Hedge / commodity / macro ETFs — always in universe for macro hedge allocation
HEDGE_ETFS = [
    "GLD", "SLV", "TLT", "IEF",   # Gold, Silver, Long-term bonds, Intermediate bonds
    "UUP", "USO", "XLE", "XLF",   # Dollar, Oil, Energy sector, Financials sector
    "XLV", "XLK", "XLI", "XLU",   # Healthcare, Tech, Industrials, Utilities
    "XLP", "XLY", "XLB", "XLRE",  # Staples, Discretionary, Materials, Real Estate
    "XLC",                          # Communication Services
    "VXX",                          # Volatility (VIX futures)
]


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
    universe = set(sp500) | set(r2000) | set(DOW_30) | set(BENCHMARKS) | set(HEDGE_ETFS) | set(extra_tickers)
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
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    df["sma200"] = close.rolling(200).mean()
    df["sma150"] = close.rolling(150).mean()
    df["sma113"] = close.rolling(113).mean()
    df["sma8"] = close.rolling(8).mean()
    df["sma50"]  = close.rolling(50).mean()
    df["sma10"]  = close.rolling(10).mean()
    df["ema20"]  = close.ewm(span=20, adjust=False).mean()
    df["ema30"]  = close.ewm(span=30, adjust=False).mean()
    df["macd"], df["macd_signal"], df["macd_hist"] = compute_macd(close)
    df["rsi"]    = compute_rsi(close)
    df["bb_mid"], df["bb_upper"], df["bb_lower"] = compute_bb(close)
    df["week_52_high"] = close.rolling(252, min_periods=20).max()
    df["week_52_low"]  = close.rolling(252, min_periods=20).min()
    df["prev_close"] = close.shift(1)
    df["prev_sma113"] = df["sma113"].shift(1)
    df["prev_sma8"] = df["sma8"].shift(1)
    df["prev_sma200"] = df["sma200"].shift(1)
    df["prev_ema20"] = df["ema20"].shift(1)
    df["prev_ema30"] = df["ema30"].shift(1)
    df["prev_sma50"] = df["sma50"].shift(1)

    # Slope
    df["sma50_slope"] = df["sma50"].diff(5)
    df["sma200_slope"] = df["sma200"].diff(5)


    # Volume & RVOL
    df["vol_sma50"] = volume.rolling(50).mean()

    # ATR (Average True Range)
    high_low = high - low
    high_close = np.abs(high - df["prev_close"])
    low_close = np.abs(low - df["prev_close"])
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df["atr_14"] = true_range.rolling(14).mean()

    # Daily Closing Range %
    df["close_range_pct"] = np.where(
        high != low,
        (close - low) / (high - low),
        0.5
    )

    # BB Width & Squeeze
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
    df["bb_width_6m_low"] = df["bb_width"].rolling(126).min()

    # MA Spread (Coil)
    ma_columns = ["sma8", "ema20", "sma50", "sma113", "sma200"]
    df["ma_max"] = df[ma_columns].max(axis=1)
    df["ma_min"] = df[ma_columns].min(axis=1)
    df["ma_spread_pct"] = np.where(
        df["ma_min"] > 0,
        (df["ma_max"] - df["ma_min"]) / df["ma_min"] * 100,
        np.nan
    )
    return df


# ─────────────────────────────────────────────────────────────
# DATA FETCH
# ─────────────────────────────────────────────────────────────

BATCH_SIZE = 100  # yfinance handles ~100 tickers well per call


def get_mcap(ticker: str) -> float:
    """Fetch market cap safely using a requests Session."""
    try:
        t = yf.Ticker(ticker)
        cap = 0

        # Check new fast_info attribute first
        if hasattr(t, "fast_info"):
            try:
                cap = getattr(t.fast_info, 'market_cap', 0)
            except Exception:
                pass

            if not cap:
                try:
                    cap = t.fast_info.get('marketCap', 0)
                except Exception:
                    pass

        # Fallback to standard info
        if not cap:
            try:
                cap = t.info.get('marketCap', 0)
            except Exception:
                pass

        return float(cap) if cap else 0
    except Exception:
        return 0


def fetch_ohlc_init(tickers: list[str], period: str = "2y") -> dict[str, pd.DataFrame]:
    """Download adjusted OHLCV in batches. Returns {ticker: df}."""
    result: dict[str, pd.DataFrame] = {}
    batches = [tickers[i:i + BATCH_SIZE] for i in range(0, len(tickers), BATCH_SIZE)]
    print(f"  Downloading {len(tickers)} tickers in {len(batches)} batches (period={period})...")
    min_cap: float = 1_000_000_000

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
            if ticker not in BENCHMARKS:
                cap = get_mcap(ticker)
                if not df.empty and cap > min_cap:
                    result[ticker] = df
            else:
                result[ticker] = df
        else:
            for ticker in batch:
                try:
                    df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close", "Volume"]].copy()
                    df = df.dropna(subset=["Close"])
                    df.index = pd.to_datetime(df.index).date
                    if ticker not in BENCHMARKS:
                        cap = get_mcap(ticker)
                        if not df.empty and cap > min_cap:
                            result[ticker] = df
                    else:
                        result[ticker] = df
                except Exception:
                    pass

    print(f"  Fetched data for {len(result)}/{len(tickers)} tickers")
    return result

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
                result[ticker] = df
        else:
            for ticker in batch:
                try:
                    df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close", "Volume"]].copy()
                    df = df.dropna(subset=["Close"])
                    df.index = pd.to_datetime(df.index).date
                    if not df.empty:
                        result[ticker] = df
                    else:
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

        # --- Reclaims ---
        price_reclaimed_113 = False
        if not pd.isna(row.get("prev_sma113")) and not pd.isna(row.get("sma113")):
            if row["prev_close"] < row["prev_sma113"] and close > row["sma113"]:
                price_reclaimed_113 = True

        sma8_reclaimed_200 = False
        if not pd.isna(row.get("prev_sma8")) and not pd.isna(row.get("prev_sma200")):
            if row["prev_sma8"] < row["prev_sma200"] and row["sma8"] > row["sma200"]:
                sma8_reclaimed_200 = True

        # --- Relative Volume ---
        rvol = 0.0
        if not pd.isna(row.get("Volume")) and not pd.isna(row.get("vol_sma50")) and row.get("vol_sma50") > 0:
            rvol = float(row["Volume"] / row["vol_sma50"])

        # --- Extensions & Trends ---
        dist_from_50_pct = 0.0
        if not pd.isna(row.get("sma50")) and row.get("sma50") != 0:
            dist_from_50_pct = float((close - row["sma50"]) / row["sma50"] * 100)

        dist_from_52w_high_pct = 0.0
        if not pd.isna(row.get("week_52_high")) and row.get("week_52_high") > 0:
            dist_from_52w_high_pct = float((close - row["week_52_high"]) / row["week_52_high"] * 100)

        perfect_trend = False
        if not any(pd.isna(v) for v in [row.get("sma8"), row.get("ema20"), row.get("sma50"), row.get("sma200")]):
            if close > row["sma8"] > row["ema20"] > row["sma50"] > row["sma200"]:
                perfect_trend = True

        sma50_is_rising = False
        if not pd.isna(row.get("sma50_slope")) and row["sma50_slope"] > 0:
            sma50_is_rising = True

        sma200_is_rising = False
        if not pd.isna(row.get("sma200_slope")) and row["sma200_slope"] > 0:
            sma200_is_rising = True

        # --- Action Flags (Inside/Gap/Squeeze/Coil) ---
        is_inside_day = False
        if not pd.isna(row.get("prev_high")) and not pd.isna(row.get("prev_low")):
            if row["High"] < row["prev_high"] and row["Low"] > row["prev_low"]:
                is_inside_day = True

        is_gap_up = False
        if not pd.isna(row.get("Low")) and not pd.isna(row.get("prev_high")):
            if row["Low"] > row["prev_high"]:
                is_gap_up = True

        bb_width = float(row.get("bb_width")) if not pd.isna(row.get("bb_width")) else 0.0
        is_bb_squeeze = False
        if not pd.isna(row.get("bb_width_6m_low")) and row.get("bb_width_6m_low") > 0:
            if bb_width <= (row["bb_width_6m_low"] * 1.05):
                is_bb_squeeze = True

        ma_spread_pct = float(row.get("ma_spread_pct")) if not pd.isna(row.get("ma_spread_pct")) else 0.0
        is_ma_coiled = False
        if 0 < ma_spread_pct <= 5.0:
            is_ma_coiled = True

        ta_rows.append({
            "ticker": ticker,
            "date": d,
            "close": close,
            "sma200":      None if pd.isna(row["sma200"])      else float(row["sma200"]),
            "sma150":      None if pd.isna(row["sma150"])      else float(row["sma150"]),
            "sma113":      None if pd.isna(row["sma113"])      else float(row["sma113"]),
            "sma8":      None if pd.isna(row["sma8"])      else float(row["sma8"]),
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

            # --- ADVANCED QUANT METRICS ---
            "price_reclaimed_113": price_reclaimed_113,
            "sma8_reclaimed_200": sma8_reclaimed_200,
            "rvol": rvol,
            "dist_from_50_pct": dist_from_50_pct,
            "dist_from_52w_high_pct": dist_from_52w_high_pct,
            "perfect_trend": perfect_trend,
            "sma50_is_rising": sma50_is_rising,
            "sma200_is_rising": sma200_is_rising,
            "atr_14": float(row["atr_14"]) if not pd.isna(row.get("atr_14")) else 0.0,
            "close_range_pct": float(row["close_range_pct"]) if not pd.isna(row.get("close_range_pct")) else 0.5,
            "is_inside_day": is_inside_day,
            "is_gap_up": is_gap_up,
            "bb_width": bb_width,
            "is_bb_squeeze": is_bb_squeeze,
            "ma_spread_pct": ma_spread_pct,
            "is_ma_coiled": is_ma_coiled,

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

    ohlc_data = fetch_ohlc_init(tickers, period="2y")
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

def get_existing_universe(engine) -> list[str]:
    """Fetch the distinct list of tickers currently in the database."""
    print("  Fetching existing universe from database...")
    try:
        with engine.connect() as conn:
            # Get unique tickers from the OHLC table
            result = conn.execute(text("SELECT DISTINCT ticker FROM ohlc_daily"))
            tickers = [row[0] for row in result]

        print(f"  Found {len(tickers)} existing tickers in database.")
        return tickers
    except Exception as e:
        print(f"  [WARN] Failed to fetch existing universe: {e}")
        return []

def get_latest_market_date() :
    """Fetch the most recent trading date from SPY to determine if we need an update."""
    print("  Checking Yahoo Finance for the latest available market date...")
    try:
        # Fetch just 5 days to guarantee we catch the last trading day, even over long weekends
        spy = yf.download("SPY", period="5d", interval="1d", progress=False, threads=False)
        if not spy.empty:
            return spy.index[-1].date()
    except Exception as e:
        print(f"  [WARN] Failed to fetch latest market date from yfinance: {e}")
    return None

def run_daily(engine, extra_tickers: list[str]):
    print("[DAILY] Starting incremental update...")

    try:
        # 1. Get the max date currently in the database
        with engine.connect() as conn:
            result = conn.execute(text("SELECT MAX(date) FROM ohlc_daily"))
            db_max_date = result.scalar()

        # 2. Get the latest actual trading date from Yahoo Finance
        yf_latest_date = get_latest_market_date()

        # 3. Compare them
        if db_max_date and yf_latest_date:
            if db_max_date >= yf_latest_date:
                print(
                    f"  [SKIP] Database is up to date (DB: {db_max_date}, Market: {yf_latest_date}). Halting execution.")
                return
            else:
                print(f"  [UPDATE REQUIRED] DB max date: {db_max_date}, Latest Market date: {yf_latest_date}.")
        elif not db_max_date:
            print("  [INFO] Database appears empty. Proceeding with update.")

    except Exception as e:
        print(f"  [WARN] Failed during date check logic: {e}")

    tickers = get_existing_universe(engine)
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

    # ── Partial-data guard ────────────────────────────────────────
    # yfinance sometimes returns data for only a handful of tickers
    # (network hiccup, rate-limit, market not yet closed).
    # If we wrote those rows, the Minervini screener would silently
    # use a date with <1% coverage instead of the previous full day.
    # Threshold: require at least 10% of the expected universe.
    MIN_COVERAGE = max(100, int(len(tickers) * 0.10))
    if len(all_ta) < MIN_COVERAGE:
        print(
            f"[DAILY] PARTIAL DATA DETECTED: only {len(all_ta)} tickers fetched "
            f"(expected >= {MIN_COVERAGE} of {len(tickers)} universe tickers)."
        )
        print(
            "[DAILY] Skipping write to ohlc_daily/ta_daily to preserve yesterday's "
            "full dataset. Re-run after market close or use --mode init to rebuild."
        )
        print("[DAILY] NEXT RUN: this step will be retried automatically next session.")
        return

    write_ohlc(all_ohlc, engine, replace=False)
    write_ta(all_ta, engine, replace=False)
    print(f"[DAILY] Done. {len(all_ta)} tickers updated.")


def run_scanners():
    """Run automated SQL scans against the updated database and print results."""
    print("\n" + "=" * 60)
    print("  MARKET SCANNERS (TODAY'S SIGNALS)")
    print("=" * 60)

    engine = create_engine(PG_CONN_STR)

    queries = {
        "🔥 1. Perfect Trend + Inside Day Breakout": """
            SELECT ticker, close, ROUND(rvol::numeric, 2) as rvol, ROUND(dist_from_52w_high_pct::numeric, 2) as pct_from_high, ROUND(atr_14::numeric, 2) as atr
            FROM ta_daily
            WHERE date = (SELECT MAX(date) FROM ta_daily)
              AND perfect_trend = TRUE
              AND sma50_is_rising = TRUE
              AND dist_from_52w_high_pct >= -15.0
              AND is_inside_day = TRUE
            ORDER BY dist_from_52w_high_pct DESC LIMIT 10;
        """,
        "🎯 2. Explosive Squeeze (BB or MA Coil)": """
            SELECT ticker, close, ROUND(rvol::numeric, 2) as rvol, ROUND(ma_spread_pct::numeric, 2) as ma_spread, ROUND(close_range_pct::numeric, 2) as close_rng
            FROM ta_daily
            WHERE date = (SELECT MAX(date) FROM ta_daily)
              AND (is_bb_squeeze = TRUE OR is_ma_coiled = TRUE)
              AND rvol > 1.5
              AND close_range_pct > 0.8
            ORDER BY rvol DESC LIMIT 10;
        """,
        "🚀 3. The 113 SMA Power Reclaim": """
            SELECT ticker, close, ROUND(rvol::numeric, 2) as rvol, ROUND(sma113::numeric, 2) as sma113, ROUND(close_range_pct::numeric, 2) as close_rng
            FROM ta_daily
            WHERE date = (SELECT MAX(date) FROM ta_daily)
              AND price_reclaimed_113 = TRUE
              AND sma50_is_rising = TRUE
              AND rvol > 1.2
              AND close_range_pct >= 0.5
            ORDER BY rvol DESC LIMIT 10;
        """,
        "⚡ 4. Gap & Go Momentum Scanner": """
            SELECT ticker, close, ROUND(rvol::numeric, 2) as rvol, ROUND(close_range_pct::numeric, 2) as close_rng, ROUND(dist_from_50_pct::numeric, 2) as ext_50
            FROM ta_daily
            WHERE date = (SELECT MAX(date) FROM ta_daily)
              AND is_gap_up = TRUE
              AND rvol > 2.0
              AND close_range_pct > 0.75
              AND dist_from_50_pct < 20.0
            ORDER BY rvol DESC LIMIT 10;
        """,
        "📈 5. The 8/200 SMA Macro Reclaim": """
                SELECT ticker, close, ROUND(rvol::numeric, 2) as rvol, ROUND(sma8::numeric, 2) as sma8, ROUND(sma200::numeric, 2) as sma200
                FROM ta_daily
                WHERE date = (SELECT MAX(date) FROM ta_daily)
                  AND sma8_reclaimed_200 = TRUE
                  AND rvol > 1.2
                  AND close_range_pct >= 0.5
                ORDER BY rvol DESC LIMIT 10;
            """,
        "💎 6. Quality at Discount (Dip-Buy Candidates)": """
                SELECT ticker, close,
                       ROUND(dist_from_52w_high_pct::numeric, 1) as pct_from_high,
                       ROUND(dist_from_50_pct::numeric, 1) as dist_50,
                       ROUND(rsi::numeric, 1) as rsi,
                       ROUND(rvol::numeric, 2) as rvol,
                       sma200_is_rising
                FROM ta_daily
                WHERE date = (SELECT MAX(date) FROM ta_daily)
                  AND close < sma50               -- Below 50-day MA (in pullback)
                  AND close > sma200              -- Still above 200-day MA (not broken)
                  AND sma200_is_rising = TRUE     -- Long-term uptrend intact
                  AND dist_from_52w_high_pct BETWEEN -25 AND -8  -- 8-25% off highs
                  AND rsi BETWEEN 30 AND 45       -- Oversold but not capitulating
                ORDER BY dist_from_52w_high_pct ASC LIMIT 15;
            """,
        "🔄 7. Mean Reversion Setup (Stretched Below MAs)": """
                SELECT ticker, close,
                       ROUND(dist_from_50_pct::numeric, 1) as dist_50,
                       ROUND(rsi::numeric, 1) as rsi,
                       bb_position,
                       ROUND(close_range_pct::numeric, 2) as close_rng
                FROM ta_daily
                WHERE date = (SELECT MAX(date) FROM ta_daily)
                  AND close < bb_lower            -- Below lower Bollinger Band
                  AND sma200_is_rising = TRUE     -- Long-term trend still up
                  AND rsi < 35                    -- Oversold
                  AND close_range_pct > 0.5       -- Closing in upper half of day's range (reversal candle)
                ORDER BY rsi ASC LIMIT 10;
            """
    }

    with engine.connect() as conn:
        for name, query in queries.items():
            print(f"\n{name}")
            print("-" * 60)
            try:
                df = pd.read_sql(text(query), conn)
                if df.empty:
                    print("  No setups found today.")
                else:
                    print(df.to_string(index=False))
            except Exception as e:
                print(f"  [Error running scanner]: {e}")

    print("\n" + "=" * 60 + "\n")

# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def drop_partial_date(engine, date_str: str):
    """Delete all ohlc_daily + ta_daily rows for a given date (YYYY-MM-DD).

    Use this to clean up a partial/broken daily run before retrying:
        python3 scripts/update_technicals.py --drop-partial 2026-04-07
    """
    from datetime import date as dt_date
    try:
        target = dt_date.fromisoformat(date_str)
    except ValueError:
        print(f"[DROP-PARTIAL] Invalid date '{date_str}'. Use YYYY-MM-DD format.")
        return

    with engine.begin() as conn:
        r1 = conn.execute(text("DELETE FROM ohlc_daily WHERE date::date = :d"), {"d": target})
        r2 = conn.execute(text("DELETE FROM ta_daily WHERE date::date = :d"), {"d": target})
    print(
        f"[DROP-PARTIAL] Removed {r1.rowcount} ohlc_daily rows and "
        f"{r2.rowcount} ta_daily rows for {target}."
    )
    print("[DROP-PARTIAL] You can now re-run: python3 scripts/update_technicals.py --mode daily")


def main():
    parser = argparse.ArgumentParser(description="Update OHLC + technicals in PostgreSQL via yfinance")
    parser.add_argument(
        "--mode",
        choices=["init", "daily", "scan"],
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
    parser.add_argument(
        "--drop-partial",
        metavar="DATE",
        default=None,
        help="Delete all ohlc_daily/ta_daily rows for DATE (YYYY-MM-DD) then exit. "
             "Use to clean up a partial run before retrying.",
    )
    args = parser.parse_args()

    engine = create_engine(PG_CONN_STR)
    print(f"[update_technicals] mode={args.mode}, extra_tickers={args.tickers or 'none'}")

    if args.drop_partial:
        drop_partial_date(engine, args.drop_partial)
        return

    if args.mode == "init":
        run_init(engine, args.tickers)
    elif args.mode == "scan":
        run_scanners()
    else:
        run_daily(engine, args.tickers)


if __name__ == "__main__":
    main()

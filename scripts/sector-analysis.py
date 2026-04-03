#!/usr/bin/env python3
"""
sector-analysis.py — Sector rotation vs benchmark correlation analysis.

Fetches sector-grouped returns at configurable frequency, computes correlation
matrix against a benchmark, and outputs a heatmap + CSV for dashboard consumption.

Supports multiple universes: sp500 (default), russell1000, nifty50 — add more
by extending UNIVERSES dict.

Usage:
    python scripts/sector-analysis.py                                    # sp500, daily, 1yr
    python scripts/sector-analysis.py --freq weekly --years 2
    python scripts/sector-analysis.py --freq monthly --years 5
    python scripts/sector-analysis.py --universe nifty50 --freq daily
    python scripts/sector-analysis.py --freq daily --no-plot --csv
"""

import argparse
import sys
import warnings
from pathlib import Path

import io
import urllib.request

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

YF_INTERVAL = {"daily": "1d", "weekly": "1wk", "monthly": "1mo"}
DEFAULT_YEARS = {"daily": 1, "weekly": 2, "monthly": 5}

# ── Universe definitions ────────────────────────────────────────────────────
# Each entry: (wikipedia_url, symbol_col, sector_col, benchmark_ticker, symbol_fixup)

UNIVERSES = {
    "sp500": {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "table_index": 0,
        "symbol_col": "Symbol",
        "sector_col": "GICS Sector",
        "benchmark": "SPY",
        "fixup": lambda s: s.replace(".", "-"),  # BRK.B → BRK-B for yfinance
    },
    "russell1000": {
        "url": "https://en.wikipedia.org/wiki/Russell_1000_Index",
        "table_index": 2,
        "symbol_col": "Ticker",
        "sector_col": "GICS Sector",
        "benchmark": "IWB",
        "fixup": lambda s: s.replace(".", "-"),
    },
    "nifty50": {
        "url": "https://en.wikipedia.org/wiki/NIFTY_50",
        "table_index": 1,
        "symbol_col": "Symbol",
        "sector_col": "Sector",
        "benchmark": "^NSEI",
        "fixup": lambda s: s + ".NS",  # append .NS for NSE tickers in yfinance
    },
}


def get_universe(name: str) -> tuple[pd.DataFrame, str]:
    """Fetch ticker-sector mapping from Wikipedia. Returns (df[ticker, sector], benchmark)."""
    cfg = UNIVERSES[name]
    print(f"Fetching {name} sector mapping from Wikipedia ...")
    req = urllib.request.Request(cfg["url"], headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req).read().decode("utf-8")
    tables = pd.read_html(io.StringIO(html))
    df = tables[cfg["table_index"]][[cfg["symbol_col"], cfg["sector_col"]]].copy()
    df.columns = ["ticker", "sector"]
    df["ticker"] = df["ticker"].astype(str).str.strip().apply(cfg["fixup"])
    df = df.dropna(subset=["sector"])
    print(f"  {len(df)} tickers across {df['sector'].nunique()} sectors")
    return df, cfg["benchmark"]


def fetch_returns(tickers: list[str], period_years: int, freq: str) -> pd.DataFrame:
    """Batch-download prices and compute period returns."""
    interval = YF_INTERVAL[freq]
    end = pd.Timestamp.now()
    start = end - pd.DateOffset(years=period_years)

    print(f"Downloading {len(tickers)} tickers | {freq} | {start.date()} → {end.date()} ...")
    prices = yf.download(
        tickers, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"),
        interval=interval, group_by="ticker", auto_adjust=True, progress=False,
    )

    if isinstance(prices.columns, pd.MultiIndex):
        close = prices.xs("Close", axis=1, level=1)
    else:
        close = prices[["Close"]].rename(columns={"Close": tickers[0]})

    returns = close.pct_change().iloc[1:]
    return returns.fillna(0)


def sector_correlation(
    sector_df: pd.DataFrame, returns: pd.DataFrame, benchmark: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Group ticker returns by sector, average, join benchmark, return correlation matrix."""
    valid = [t for t in sector_df["ticker"] if t in returns.columns]
    sector_map = sector_df.set_index("ticker")["sector"]

    sector_returns = returns[valid].T.groupby(sector_map[valid]).mean().T

    if benchmark in returns.columns:
        sector_returns[benchmark] = returns[benchmark]

    return sector_returns.corr(), sector_returns


def plot_heatmap(corr: pd.DataFrame, freq: str, universe: str):
    import matplotlib.pyplot as plt
    import seaborn as sns

    fig, ax = plt.subplots(figsize=(12, 9))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", linewidths=0.5,
                vmin=-1, vmax=1, ax=ax)
    ax.set_title(f"{universe.upper()} Sector Correlation ({freq.title()} Returns)")
    plt.tight_layout()
    plt.show()


def print_benchmark_correlations(corr: pd.DataFrame, benchmark: str):
    if benchmark not in corr.columns:
        return
    bm_corr = corr[benchmark].drop(benchmark, errors="ignore").sort_values(ascending=False)
    print(f"\n── Sector Correlation with {benchmark} (descending) ──")
    for sector, val in bm_corr.items():
        bar = "█" * int(abs(val) * 20)
        sign = "+" if val >= 0 else "-"
        print(f"  {sign}{val:6.3f}  {bar:20s}  {sector}")


def generate_rotation_charts(data_dir: Path, universe: str, freq: str):
    """Generate 4-panel sector rotation chart from saved CSV data."""
    import matplotlib.pyplot as plt
    import numpy as np

    ret = pd.read_csv(data_dir / f"sector_returns_{universe}_{freq}.csv", index_col=0, parse_dates=True)
    corr = pd.read_csv(data_dir / f"sector_correlation_{universe}_{freq}.csv", index_col=0)
    sectors = [c for c in ret.columns if c not in ("SPY", "IWB", "^NSEI")]
    benchmark = next(c for c in ret.columns if c not in sectors)

    cum = ((1 + ret).cumprod() - 1) * 100

    fig, axes = plt.subplots(2, 2, figsize=(18, 12))

    # 1. Cumulative returns
    ax = axes[0, 0]
    for s in sectors:
        ax.plot(cum.index, cum[s], label=s, linewidth=1.2)
    ax.plot(cum.index, cum[benchmark], label=benchmark, color="black", linewidth=2.5, linestyle="--")
    ax.set_title(f"Cumulative Sector Returns ({universe.upper()})", fontsize=13, fontweight="bold")
    ax.set_ylabel("Return %")
    ax.legend(fontsize=7, ncol=3)
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.grid(alpha=0.3)

    # 2. Last 3M bar chart
    ax = axes[0, 1]
    window = min(63, len(ret))
    recent = ret.iloc[-window:]
    r3m = ((1 + recent).cumprod().iloc[-1] - 1) * 100
    r3m_sorted = r3m[sectors].sort_values(ascending=True)
    colors = ["#22c55e" if v >= 0 else "#ef4444" for v in r3m_sorted]
    ax.barh(r3m_sorted.index, r3m_sorted.values, color=colors)
    ax.axvline(r3m[benchmark], color="black", linestyle="--", linewidth=1.5, label=f"{benchmark} {r3m[benchmark]:.1f}%")
    ax.set_title("Last 3-Month Return by Sector", fontsize=13, fontweight="bold")
    ax.set_xlabel("Return %")
    ax.legend()
    ax.grid(alpha=0.3, axis="x")

    # 3. Rotation rank change
    ax = axes[1, 0]
    total = cum.iloc[-1]
    rank_full = total[sectors].rank(ascending=False)
    rank_recent = r3m[sectors].rank(ascending=False)
    rank_shift = (rank_full - rank_recent).sort_values()
    colors = ["#22c55e" if v >= 0 else "#ef4444" for v in rank_shift]
    ax.barh(rank_shift.index, rank_shift.values, color=colors)
    ax.set_title("Sector Rotation Signal (Full vs 3M Rank)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Rank Change (positive = accelerating)")
    ax.axvline(0, color="gray", linewidth=0.5)
    ax.grid(alpha=0.3, axis="x")

    # 4. Correlation with benchmark
    ax = axes[1, 1]
    bm_corr = corr[benchmark].drop(benchmark, errors="ignore").sort_values(ascending=True)
    cmap_colors = plt.cm.coolwarm(np.linspace(0.1, 0.9, len(bm_corr)))
    ax.barh(bm_corr.index, bm_corr.values, color=cmap_colors)
    ax.set_title(f"Sector Correlation with {benchmark} ({freq.title()}, {universe.upper()})", fontsize=13, fontweight="bold")
    ax.set_xlabel("Correlation")
    ax.set_xlim(0, 1)
    ax.grid(alpha=0.3, axis="x")

    plt.tight_layout()
    out_path = data_dir / f"sector_rotation_{universe}_{freq}.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n  Chart saved: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Sector rotation correlation analysis")
    parser.add_argument("--universe", choices=list(UNIVERSES.keys()), default="sp500")
    parser.add_argument("--freq", choices=["daily", "weekly", "monthly"], default="daily")
    parser.add_argument("--years", type=int, default=None, help="Lookback period in years")
    parser.add_argument("--no-plot", action="store_true", help="Skip heatmap display")
    parser.add_argument("--chart", action="store_true", help="Generate 4-panel rotation chart PNG")
    parser.add_argument("--csv", action="store_true", help="Save correlation + returns to CSV")
    args = parser.parse_args()

    years = args.years or DEFAULT_YEARS[args.freq]

    # 1. Get universe
    sector_df, benchmark = get_universe(args.universe)

    # 2. Batch download
    all_tickers = sector_df["ticker"].tolist() + [benchmark]
    returns = fetch_returns(all_tickers, years, args.freq)
    print(f"  {returns.shape[0]} periods x {returns.shape[1]} tickers downloaded")

    # 3. Correlation matrix
    corr, sector_returns = sector_correlation(sector_df, returns, benchmark)

    # 4. Output
    print_benchmark_correlations(corr, benchmark)

    if args.csv:
        out_dir = Path(__file__).resolve().parent.parent / "data"
        out_dir.mkdir(exist_ok=True)
        tag = f"{args.universe}_{args.freq}"
        corr_path = out_dir / f"sector_correlation_{tag}.csv"
        ret_path = out_dir / f"sector_returns_{tag}.csv"
        corr.to_csv(corr_path)
        sector_returns.to_csv(ret_path)
        print(f"\n  Saved: {corr_path}")
        print(f"  Saved: {ret_path}")

    if not args.no_plot:
        plot_heatmap(corr, args.freq, args.universe)

    if args.chart and args.csv:
        generate_rotation_charts(out_dir, args.universe, args.freq)
    elif args.chart:
        out_dir = Path(__file__).resolve().parent.parent / "data"
        generate_rotation_charts(out_dir, args.universe, args.freq)

    return corr


if __name__ == "__main__":
    main()

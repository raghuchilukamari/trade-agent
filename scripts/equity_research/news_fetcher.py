"""
news_fetcher.py — Parse walter_openai.csv for per-ticker news sentiment.
No API calls. Reads CSV directly from disk.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

WALTER_CSV = Path("/media/SHARED/trade-data/formatted/walter_openai.csv")


def get_ticker_news(ticker: str, weeks: int = 4) -> list[dict]:
    """
    Return top-5 news items for ticker from the last N weeks.
    Sorted by |sentiment_score| descending.
    Returns list of {date, summary, sentiment_score, tickers}.
    """
    if not WALTER_CSV.exists():
        return []

    df = pd.read_csv(WALTER_CSV, sep="|", dtype=str, low_memory=False)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", format="mixed").dt.date
    df = df.dropna(subset=["Date"])

    cutoff = date.today() - timedelta(weeks=weeks)
    df = df[df["Date"] >= cutoff]

    # Filter rows where ticker appears in key_entities_ticker
    mask = df["key_entities_ticker"].fillna("").str.upper().str.contains(
        r"\b" + ticker.upper() + r"\b", regex=True
    )
    df = df[mask].copy()
    if df.empty:
        return []

    df["sentiment_score"] = pd.to_numeric(df["sentiment_score"], errors="coerce").fillna(0)
    df["abs_sentiment"] = df["sentiment_score"].abs()
    df = df.sort_values("abs_sentiment", ascending=False).head(5)

    results = []
    for _, row in df.iterrows():
        results.append({
            "date": str(row["Date"]),
            "summary": str(row.get("new_summary", ""))[:150],
            "sentiment_score": float(row["sentiment_score"]),
            "tickers": str(row.get("key_entities_ticker", "")),
        })
    return results


def get_week_sentiment(ticker: str, weeks: int = 4) -> float:
    """Average sentiment score for ticker over last N weeks."""
    news = get_ticker_news(ticker, weeks=weeks)
    if not news:
        return 0.0
    return round(sum(n["sentiment_score"] for n in news) / len(news), 2)

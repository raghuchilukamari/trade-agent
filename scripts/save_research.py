#!/usr/bin/env python3
"""
save_research.py — Persist HTML research reports to PostgreSQL.

Usage:
    python3 scripts/save_research.py <table> <symbol> <date> <html_path>

    table:    sec_filing_analysis | equity_research
    symbol:   ticker (e.g. NVDA)
    date:     ISO date (e.g. 2026-04-07)
    html_path: path to HTML file to upsert

Tables (all in dashboard schema):
    dashboard.sec_filing_analysis  — columns: symbol, run_date, html
    dashboard.equity_research      — columns: symbol, run_date, html
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ALLOWED_TABLES = {"sec_filing_analysis", "equity_research"}

DB_USER = os.getenv("PG_USER", os.getenv("POSTGRES_USER", ""))
DB_PASS = os.getenv("PG_PASS", os.getenv("POSTGRES_PASSWORD", ""))
DB_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "postgres")
PG_CONN_STR = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def main():
    if len(sys.argv) != 5:
        print("Usage: save_research.py <table> <symbol> <date> <html_path>")
        print("  table:     sec_filing_analysis | equity_research")
        print("  symbol:    e.g. NVDA")
        print("  date:      e.g. 2026-04-07")
        print("  html_path: path to HTML file")
        sys.exit(1)

    _, table, symbol, run_date, html_path = sys.argv

    if table not in ALLOWED_TABLES:
        print(f"ERROR: table must be one of {ALLOWED_TABLES}, got '{table}'")
        sys.exit(1)

    html_path = Path(html_path)
    if not html_path.exists():
        print(f"ERROR: file not found: {html_path}")
        sys.exit(1)

    html = html_path.read_text(encoding="utf-8")
    symbol = symbol.upper()

    engine = create_engine(PG_CONN_STR)
    with engine.begin() as conn:
        conn.execute(
            text(f"""
                INSERT INTO dashboard.{table} (symbol, run_date, html)
                VALUES (:symbol, :run_date, :html)
                ON CONFLICT (symbol, run_date) DO UPDATE SET html = EXCLUDED.html
            """),
            {"symbol": symbol, "run_date": run_date, "html": html},
        )

    print(f"[OK] Saved {symbol} to dashboard.{table} (run_date={run_date}, {len(html):,} chars)")


if __name__ == "__main__":
    main()

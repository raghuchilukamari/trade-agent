"""Minervini Trend Template Screener — Stock screening against Mark Minervini's 8 SEPA criteria."""
from .minervini_screener import (
    run_screen, screen_ticker, MinerviniResult,
    save_scan, get_new_passers, to_json, to_csv,
)
from .tickers import (
    get_universe, SP500, NASDAQ100,
)

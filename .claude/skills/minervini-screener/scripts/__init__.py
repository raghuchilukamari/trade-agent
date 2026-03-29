"""Minervini Trend Template Screener — Stock screening against Mark Minervini's 8 SEPA criteria."""
from .minervini_screener import (
    run_screen, screen_ticker, MinerviniResult,
    save_scan, get_new_passers, to_json, to_csv,
)
from .tickers import (
    get_universe, WATCHLIST_STRONG_BUYS, WATCHLIST_IBD15,
    SP500, NASDAQ100,
)

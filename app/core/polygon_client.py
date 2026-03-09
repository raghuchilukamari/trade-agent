"""
Polygon.io API client — real-time and historical market data.

Provides: stock quotes, options chain, aggregates, news, ticker details.
Used by agents for Deep ITM Rule checks and live price validation.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = structlog.get_logger(__name__)

POLYGON_BASE = "https://api.polygon.io"


class PolygonManager:
    """Async Polygon.io API client."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._available: bool = False

    async def initialize(self) -> None:
        logger.info("initializing_polygon")
        self._client = httpx.AsyncClient(
            base_url=POLYGON_BASE,
            timeout=httpx.Timeout(30.0, connect=10.0),
            params={"apiKey": settings.polygon_api_key},
        )

        if not settings.polygon_api_key:
            logger.warning("polygon_no_api_key", hint="Set POLYGON_API_KEY in .env")
            return

        try:
            resp = await self._client.get("/v3/reference/tickers", params={"limit": 1})
            if resp.status_code == 200:
                self._available = True
                logger.info("polygon_ready")
            else:
                logger.warning("polygon_auth_failed", status=resp.status_code)
        except Exception as e:
            logger.error("polygon_init_error", error=str(e))

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
        logger.info("polygon_shutdown")

    @property
    def is_available(self) -> bool:
        return self._available

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """Execute a GET request against Polygon API."""
        if not self._client:
            raise RuntimeError("Polygon not initialized")
        resp = await self._client.get(path, params=params or {})
        resp.raise_for_status()
        return resp.json()

    # ── Stock Price ──────────────────────────────────────────────────────

    async def get_last_price(self, symbol: str) -> float | None:
        """Get last trade price for a symbol (for Deep ITM Rule checks)."""
        try:
            data = await self._get(f"/v2/last/trade/{symbol.upper()}")
            return data.get("results", {}).get("p")
        except Exception as e:
            logger.warning("price_fetch_failed", symbol=symbol, error=str(e))
            return None

    async def get_previous_close(self, symbol: str) -> dict[str, Any] | None:
        """Get previous day's OHLCV for a symbol."""
        try:
            data = await self._get(f"/v2/aggs/ticker/{symbol.upper()}/prev")
            results = data.get("results", [])
            if results:
                r = results[0]
                return {
                    "open": r.get("o"),
                    "high": r.get("h"),
                    "low": r.get("l"),
                    "close": r.get("c"),
                    "volume": r.get("v"),
                    "vwap": r.get("vw"),
                }
        except Exception as e:
            logger.warning("prev_close_failed", symbol=symbol, error=str(e))
        return None

    async def get_batch_prices(self, symbols: list[str]) -> dict[str, float]:
        """Fetch last prices for multiple symbols concurrently."""
        tasks = {s: self.get_last_price(s) for s in symbols}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        prices = {}
        for symbol, result in zip(tasks.keys(), results):
            if isinstance(result, (int, float)) and result is not None:
                prices[symbol] = result
        return prices

    # ── Aggregates ───────────────────────────────────────────────────────

    async def get_aggregates(
        self,
        symbol: str,
        multiplier: int = 1,
        timespan: str = "day",
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        """Get aggregate bars (OHLCV) for a symbol."""
        if not from_date:
            from_date = (date.today() - timedelta(days=limit * 2)).isoformat()
        if not to_date:
            to_date = date.today().isoformat()

        data = await self._get(
            f"/v2/aggs/ticker/{symbol.upper()}/range/{multiplier}/{timespan}/{from_date}/{to_date}",
            params={"limit": limit, "sort": "asc"},
        )
        return data.get("results", [])

    # ── Options ──────────────────────────────────────────────────────────

    async def get_options_chain(
        self,
        underlying: str,
        expiration_date: str | None = None,
        contract_type: str | None = None,
        limit: int = 250,
    ) -> list[dict[str, Any]]:
        """Get options chain snapshot for an underlying symbol."""
        params: dict[str, Any] = {
            "underlying_ticker": underlying.upper(),
            "limit": limit,
        }
        if expiration_date:
            params["expiration_date"] = expiration_date
        if contract_type:
            params["contract_type"] = contract_type

        data = await self._get("/v3/snapshot/options/{underlying.upper()}", params=params)
        return data.get("results", [])

    # ── Market Status ────────────────────────────────────────────────────

    async def get_market_status(self) -> dict[str, Any]:
        """Check if the market is open/closed."""
        return await self._get("/v1/marketstatus/now")

    # ── News ─────────────────────────────────────────────────────────────

    async def get_ticker_news(
        self, symbol: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get latest news articles, optionally filtered by ticker."""
        params: dict[str, Any] = {"limit": limit, "sort": "published_utc", "order": "desc"}
        if symbol:
            params["ticker"] = symbol.upper()
        data = await self._get("/v2/reference/news", params=params)
        return data.get("results", [])

    # ── Ticker Details ───────────────────────────────────────────────────

    async def get_ticker_details(self, symbol: str) -> dict[str, Any] | None:
        """Get detailed info about a ticker (sector, market cap, etc.)."""
        try:
            data = await self._get(f"/v3/reference/tickers/{symbol.upper()}")
            return data.get("results")
        except Exception as e:
            logger.warning("ticker_details_failed", symbol=symbol, error=str(e))
            return None

    # ── Market Indices ───────────────────────────────────────────────────

    async def get_index_snapshot(self) -> dict[str, Any]:
        """Get snapshot of major indices (S&P 500, Dow, Nasdaq)."""
        indices = {"SPY": "S&P 500", "DIA": "Dow Jones", "QQQ": "Nasdaq 100"}
        results = {}
        for etf, name in indices.items():
            prev = await self.get_previous_close(etf)
            if prev:
                results[name] = prev
        return results


# Singleton
polygon_manager = PolygonManager()

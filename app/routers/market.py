"""
Market data router — live prices, options, and index data via Polygon.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.client import ServiceContainer, get_services

router = APIRouter(prefix="/api/v1/market", tags=["market"])


@router.get("/price/{symbol}")
async def get_price(symbol: str, services: ServiceContainer = Depends(get_services)):
    """Get current price for a symbol."""
    if not services.polygon.is_available:
        raise HTTPException(503, "Polygon API not available")
    price = await services.polygon.get_last_price(symbol)
    prev = await services.polygon.get_previous_close(symbol)
    return {"symbol": symbol.upper(), "last_price": price, "previous_close": prev}


@router.get("/prices")
async def get_batch_prices(
    symbols: str,  # Comma-separated
    services: ServiceContainer = Depends(get_services),
):
    """Get prices for multiple symbols. Pass symbols=AAPL,NVDA,MSFT"""
    if not services.polygon.is_available:
        raise HTTPException(503, "Polygon API not available")
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    prices = await services.polygon.get_batch_prices(symbol_list)
    return {"prices": prices}


@router.get("/status")
async def market_status(services: ServiceContainer = Depends(get_services)):
    """Check if market is currently open."""
    if not services.polygon.is_available:
        raise HTTPException(503, "Polygon API not available")
    return await services.polygon.get_market_status()


@router.get("/indices")
async def index_snapshot(services: ServiceContainer = Depends(get_services)):
    """Get snapshot of major indices (SPY, DIA, QQQ)."""
    if not services.polygon.is_available:
        raise HTTPException(503, "Polygon API not available")
    return await services.polygon.get_index_snapshot()


@router.get("/news")
async def get_news(
    symbol: str | None = None,
    limit: int = 20,
    services: ServiceContainer = Depends(get_services),
):
    """Get latest market news, optionally filtered by ticker."""
    if not services.polygon.is_available:
        raise HTTPException(503, "Polygon API not available")
    return await services.polygon.get_ticker_news(symbol, limit)


@router.get("/aggregates/{symbol}")
async def get_aggregates(
    symbol: str,
    timespan: str = "day",
    limit: int = 60,
    services: ServiceContainer = Depends(get_services),
):
    """Get OHLCV aggregate bars for a symbol."""
    if not services.polygon.is_available:
        raise HTTPException(503, "Polygon API not available")
    return await services.polygon.get_aggregates(symbol, timespan=timespan, limit=limit)

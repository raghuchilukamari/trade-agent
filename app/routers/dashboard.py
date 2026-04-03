"""
Dashboard API router — serves the trading dashboard frontend.

Endpoints:
  /api/v1/dashboard/command-center   — market pulse, OPEX, quick stats
  /api/v1/dashboard/flow-scanner     — scored, filtered, paginated flow
  /api/v1/dashboard/geopolitical     — entity heatmap, sentiment
  /api/v1/dashboard/sector-rotation  — sector bull/bear flow
  /api/v1/dashboard/screener/latest  — current Minervini passers
  /api/v1/dashboard/screener/history — longitudinal tracking
  /api/v1/dashboard/stock-intelligence/{symbol} — composite per-ticker view
  /api/v1/dashboard/alerts           — dynamic change alerts
  /api/v1/dashboard/market-events    — weekly events calendar
"""

from __future__ import annotations

import asyncio
import json as _json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog
import yfinance as yf
from fastapi import APIRouter, Query

from app.core.database import db_manager
from app.core.polygon_client import polygon_manager
from app.services.deep_itm import apply_deep_itm_batch
from app.services.flow_parser import load_all_flow, load_walter_news
from app.services.flow_scorer import (
    aggregate_sectors,
    calc_dte,
    calculate_composite_score,
    classify_direction,
    classify_net_direction,
    get_sector,
)
from app.services.opex_calendar import get_full_opex_context
from app.services.premium_calculator import format_premium_m, premium_significance
from app.services.watchlist import get_ticker_marks_str
from config.settings import settings

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

DATA_DIR = Path(settings.flow_data_dir)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _today_str() -> str:
    return date.today().isoformat()


def _parse_date_param(d: str | None) -> str:
    """Normalize date param — default to today."""
    if d:
        return d
    return _today_str()


_MASSIVE_NEWS_TICKERS = "SPY,QQQ,NVDA,AAPL,MSFT,META,TSLA,AMD,INTC,XOM,TSEM"

_SENTIMENT_SCORE_MAP = {"positive": 4.0, "neutral": 2.5, "negative": 1.0}


async def fetch_massive_news(limit: int = 50) -> list[dict]:
    """
    Fetch recent news from the Massive API and normalize to the same shape
    used by walter_openai articles so they can be merged in /geopolitical.

    Returns an empty list on any failure — never raises.
    """
    if not settings.massive_api_key:
        logger.warning("massive_news_skipped", reason="MASSIVE_API_KEY not set")
        return []

    url = "https://api.massive.com/v2/reference/news"
    params = {
        "ticker": _MASSIVE_NEWS_TICKERS,
        "limit": limit,
        "order": "desc",
    }
    headers = {"Authorization": f"Bearer {settings.massive_api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("massive_news_fetch_failed", error=str(exc))
        return []

    articles: list[dict] = []
    for item in data.get("results", []):
        # Parse insights for avg sentiment score
        raw_insights = item.get("insights") or []
        if isinstance(raw_insights, str):
            try:
                raw_insights = _json.loads(raw_insights)
            except Exception:
                raw_insights = []

        scores = [
            _SENTIMENT_SCORE_MAP.get(str(ins.get("sentiment", "")).lower(), 2.5)
            for ins in raw_insights
            if isinstance(ins, dict)
        ]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 2.5

        # Tickers list
        raw_tickers = item.get("tickers") or []
        if isinstance(raw_tickers, str):
            raw_tickers = [t.strip() for t in raw_tickers.split(",") if t.strip()]

        published = item.get("published_utc") or ""
        article_date = published[:10] if published else _today_str()

        articles.append({
            "date": article_date,
            "summary": item.get("description") or item.get("title") or "",
            "tickers": raw_tickers,
            "sentiment_score": avg_score,
            "source": "massive",
            "publisher": item.get("publisher_name") or "",
            # Fields expected by entity_counts loops — massive doesn't provide these
            "sectors": [],
            "geopolitical_entities": [],
            "commodities": [],
        })

    logger.info("massive_news_fetched", count=len(articles))
    return articles


# ── 1. Command Center ───────────────────────────────────────────────────────

@router.get("/command-center")
async def command_center():
    """
    Market pulse: live prices for SPY/QQQ/VIX, OPEX context,
    quick stats from raw flow data.
    """
    today = date.today()

    # Fetch live prices — try Polygon first, fall back to yfinance
    price_symbols = ["SPY", "QQQ", "^VIX", "DX-Y.NYB", "GC=F", "CL=F"]
    display_names = {"^VIX": "VIX", "DX-Y.NYB": "DXY", "GC=F": "GOLD", "CL=F": "OIL"}
    prices = {}
    prev_close = {}
    change_pct = {}
    if polygon_manager.is_available:
        prices = await polygon_manager.get_batch_prices(["SPY", "QQQ"])
    if not prices:
        try:
            loop = asyncio.get_event_loop()
            def _yf_fetch():
                data = {}
                pc = {}
                cp = {}
                tickers = yf.download(price_symbols, period="2d", interval="1d",
                                      auto_adjust=True, progress=False)
                close = tickers["Close"] if "Close" in tickers.columns.get_level_values(0) else tickers.xs("Close", axis=1, level=0)
                for sym in price_symbols:
                    name = display_names.get(sym, sym)
                    if sym in close.columns and len(close[sym].dropna()) >= 1:
                        vals = close[sym].dropna()
                        last = float(vals.iloc[-1])
                        prev = float(vals.iloc[-2]) if len(vals) >= 2 else last
                        data[name] = last
                        pc[name] = prev
                        cp[name] = round((last - prev) / prev * 100, 2) if prev else 0.0
                return data, pc, cp
            prices, prev_close, change_pct = await loop.run_in_executor(None, _yf_fetch)
        except Exception as e:
            logger.warning("price_fetch_failed", error=str(e))

    opex = get_full_opex_context(today)

    # Quick stats from CSV (today's date)
    today_str = today.isoformat()
    flow_entries = load_all_flow(DATA_DIR, target_date=today_str)
    if not flow_entries:
        # Fall back to most recent available date
        flow_entries = load_all_flow(DATA_DIR)
        if flow_entries:
            dates = sorted(set(e.get("date", "") for e in flow_entries if e.get("date")))
            if dates:
                latest = dates[-1]
                flow_entries = [e for e in flow_entries if e.get("date") == latest]
                today_str = latest

    total_premium = sum(e.get("premium_usd", 0) or 0 for e in flow_entries)
    by_source = defaultdict(int)
    for e in flow_entries:
        by_source[e["source"]] += 1

    # Alerts count
    alerts = await db_manager.get_stock_alerts(target_date=today, limit=100)

    return {
        "market_pulse": {
            "prices": prices,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "as_of": datetime.now().isoformat(),
        },
        "opex": opex,
        "quick_stats": {
            "date": today_str,
            "total_entries": len(flow_entries),
            "total_premium": total_premium,
            "total_premium_fmt": format_premium_m(total_premium),
            "golden_sweeps": by_source.get("golden_sweep", 0),
            "sweeps": by_source.get("sweep", 0),
            "sexy_flow": by_source.get("sexy_flow", 0),
            "trady_flow": by_source.get("trady_flow", 0),
        },
        "alerts_count": len(alerts),
        "alerts_high": sum(1 for a in alerts if a.get("severity") == "HIGH"),
    }


# ── 2. Flow Scanner ─────────────────────────────────────────────────────────

@router.get("/flow-scanner")
async def flow_scanner(
    target_date: str | None = Query(None, alias="date"),
    direction_filter: str | None = Query(None, alias="direction"),
    min_premium: float | None = Query(None),
    sector: str | None = Query(None),
    source: str | None = Query(None),
    sort_by: str = Query("score"),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
):
    """
    Full ranked flow scanner with scoring, Deep ITM, direction, sector, filtering.
    """
    date_str = _parse_date_param(target_date)

    # Load raw flow
    entries = load_all_flow(DATA_DIR, target_date=date_str)
    if not entries:
        return {"date": date_str, "total": 0, "entries": [], "sectors": {}}

    # Load news for correlation
    news = load_walter_news(DATA_DIR, target_date=date_str)
    news_tickers: set[str] = set()
    for n in news:
        news_tickers.update(n.get("tickers", []))

    # Repeated tickers (appear in 2+ sources)
    ticker_sources: dict[str, set[str]] = defaultdict(set)
    for e in entries:
        ticker_sources[e["symbol"]].add(e["source"])
    repeated = {s for s, srcs in ticker_sources.items() if len(srcs) >= 2}

    # Fetch prices for Deep ITM (if Polygon available)
    unique_symbols = list(set(e["symbol"] for e in entries))[:50]
    prices: dict[str, float] = {}
    if polygon_manager.is_available:
        prices = await polygon_manager.get_batch_prices(unique_symbols)

    # Apply Deep ITM
    entries = await apply_deep_itm_batch(entries, prices)

    # Score, classify, enrich
    scored = []
    for e in entries:
        premium = e.get("premium_usd", 0) or 0
        if premium < 50_000:  # Skip noise
            continue

        score = calculate_composite_score(e, news_tickers, repeated)
        d = classify_direction(e)
        sec = get_sector(e["symbol"])
        dte = calc_dte(e.get("expiration"))

        deep_itm = e.get("deep_itm")
        signal = "NEUTRAL"
        deep_itm_note = ""
        if deep_itm:
            signal = deep_itm.get("signal", "NEUTRAL")
            if deep_itm.get("classification") == "DEEP_ITM_SOLD":
                deep_itm_note = "Deep ITM PUT - likely SOLD (BULLISH)"

        scored.append({
            "symbol": e["symbol"],
            "marks": get_ticker_marks_str(e["symbol"]),
            "call_put": e.get("call_put", ""),
            "strike": e.get("strike"),
            "expiration": e.get("expiration"),
            "dte": dte,
            "premium_usd": premium,
            "premium_fmt": format_premium_m(premium),
            "significance": premium_significance(premium),
            "vol_oi": e.get("vol_oi_ratio"),
            "source": e["source"],
            "alert_type": e.get("alert_type", ""),
            "direction": d,
            "sector": sec,
            "score": round(score, 4),
            "signal": signal,
            "deep_itm_note": deep_itm_note,
            "news_correlated": e["symbol"] in news_tickers,
            "multi_channel": e["symbol"] in repeated,
            "date": e.get("date", date_str),
            "bid_pct": e.get("bid_pct"),
            "ask_pct": e.get("ask_pct"),
        })

    # Apply filters
    if direction_filter:
        scored = [s for s in scored if s["direction"] == direction_filter.upper()]
    if min_premium:
        scored = [s for s in scored if s["premium_usd"] >= min_premium]
    if sector:
        scored = [s for s in scored if s["sector"] == sector]
    if source:
        scored = [s for s in scored if s["source"] == source]

    # Sort
    if sort_by == "premium":
        scored.sort(key=lambda x: x["premium_usd"], reverse=True)
    elif sort_by == "vol_oi":
        scored.sort(key=lambda x: x["vol_oi"] or 0, reverse=True)
    else:
        scored.sort(key=lambda x: x["score"], reverse=True)

    total = len(scored)
    page = scored[offset: offset + limit]

    # Sector summary
    sectors = aggregate_sectors(entries)

    return {
        "date": date_str,
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": page,
        "sectors": {
            name: {
                "bull_premium_fmt": format_premium_m(s["bull_premium"]),
                "bear_premium_fmt": format_premium_m(s["bear_premium"]),
                "net_premium_fmt": format_premium_m(s["net_premium"]),
                "signal": s["signal"],
                "tickers": s["tickers"],
            }
            for name, s in list(sectors.items())[:15]
        },
    }


# ── 3. Geopolitical Dashboard ───────────────────────────────────────────────

@router.get("/geopolitical")
async def geopolitical(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
):
    """
    Entity heatmap, sentiment buckets from walter_openai news data + Massive API news.
    """
    kwargs = {}
    if start_date:
        kwargs["start_date"] = start_date
    if end_date:
        kwargs["end_date"] = end_date
    if not kwargs:
        kwargs["target_date"] = _today_str()

    walter_news = load_walter_news(DATA_DIR, **kwargs)
    if not walter_news:
        # Try loading all and using latest date
        all_news = load_walter_news(DATA_DIR)
        if all_news:
            dates = sorted(set(n.get("date", "") for n in all_news if n.get("date")))
            if dates:
                latest = dates[-1]
                walter_news = [n for n in all_news if n.get("date") == latest]

    # Fetch Massive API news concurrently with walter fallback resolution
    massive_articles = await fetch_massive_news(limit=50)

    # Deduplicate Massive articles against walter by title substring match
    walter_summaries = {n.get("summary", "").lower() for n in walter_news if n.get("summary")}
    deduped_massive: list[dict] = []
    for art in massive_articles:
        title_lower = art.get("summary", "").lower()
        # Skip if a walter article already contains this title (or vice versa)
        if not any(
            title_lower[:60] in ws or ws[:60] in title_lower
            for ws in walter_summaries
            if ws
        ):
            deduped_massive.append(art)

    # Merge and sort by date desc
    news = sorted(
        walter_news + deduped_massive,
        key=lambda x: x.get("date", ""),
        reverse=True,
    )

    # Entity frequency counts
    entity_counts: dict[str, dict[str, int]] = {
        "tickers": defaultdict(int),
        "sectors": defaultdict(int),
        "geopolitical": defaultdict(int),
        "commodities": defaultdict(int),
    }

    sentiment_buckets = {"bullish": 0, "neutral": 0, "bearish": 0}
    sentiments = []

    for n in news:
        score = n.get("sentiment_score") or 3.0
        sentiments.append(score)
        if score >= 3.5:
            sentiment_buckets["bullish"] += 1
        elif score <= 2.0:
            sentiment_buckets["bearish"] += 1
        else:
            sentiment_buckets["neutral"] += 1

        for t in n.get("tickers", []):
            entity_counts["tickers"][t] += 1
        for s in n.get("sectors", []):
            entity_counts["sectors"][s] += 1
        for g in n.get("geopolitical_entities", []):
            entity_counts["geopolitical"][g] += 1
        for c in n.get("commodities", []):
            entity_counts["commodities"][c] += 1

    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 3.0

    # Top entities per category
    def top_n(d: dict, n: int = 15) -> list[dict]:
        return [{"name": k, "count": v} for k, v in sorted(d.items(), key=lambda x: x[1], reverse=True)[:n]]

    return {
        "total_articles": len(news),
        "avg_sentiment": round(avg_sentiment, 2),
        "sentiment_buckets": sentiment_buckets,
        "sources": {
            "walter": len(walter_news),
            "massive": len(deduped_massive),
        },
        "entities": {
            "tickers": top_n(entity_counts["tickers"]),
            "sectors": top_n(entity_counts["sectors"]),
            "geopolitical": top_n(entity_counts["geopolitical"]),
            "commodities": top_n(entity_counts["commodities"]),
        },
        "recent_headlines": [
            {
                "summary": n.get("summary", "")[:200],
                "sentiment": n.get("sentiment_score"),
                "tickers": n.get("tickers", []),
                "date": n.get("date", ""),
                "source": n.get("source", "walter"),
                "publisher": n.get("publisher", ""),
            }
            for n in news[:20]
        ],
    }


# ── 4. Sector Rotation ──────────────────────────────────────────────────────

@router.get("/sector-rotation")
async def sector_rotation(
    target_date: str | None = Query(None, alias="date"),
    days: int = Query(5, le=30),
):
    """
    Sector-level bull/bear premium breakdown from flow data.
    If historical data exists in dashboard.sector_flow_history, include it.
    """
    date_str = _parse_date_param(target_date)

    # Current day from CSV
    entries = load_all_flow(DATA_DIR, target_date=date_str)
    if not entries:
        entries = load_all_flow(DATA_DIR)
        if entries:
            dates = sorted(set(e.get("date", "") for e in entries if e.get("date")))
            if dates:
                date_str = dates[-1]
                entries = [e for e in entries if e.get("date") == date_str]

    current = aggregate_sectors(entries)

    # Historical from DB
    history = await db_manager.get_sector_flow_history(days=days)

    return {
        "date": date_str,
        "current": {
            name: {
                "bull_premium": s["bull_premium"],
                "bull_premium_fmt": format_premium_m(s["bull_premium"]),
                "bear_premium": s["bear_premium"],
                "bear_premium_fmt": format_premium_m(s["bear_premium"]),
                "net_premium": s["net_premium"],
                "net_premium_fmt": format_premium_m(s["net_premium"]),
                "signal": s["signal"],
                "tickers": s["tickers"],
            }
            for name, s in current.items()
        },
        "history": [
            {
                "date": str(h.get("date", "")),
                "sector": h.get("sector", ""),
                "bull_premium": float(h.get("bull_premium", 0)),
                "bear_premium": float(h.get("bear_premium", 0)),
                "net_premium": float(h.get("net_premium", 0)),
                "signal": h.get("signal", ""),
            }
            for h in history
        ],
    }


# ── 5. Market Events ────────────────────────────────────────────────────────

@router.get("/market-events")
async def market_events():
    """
    Weekly market events from dashboard.skill_outputs (market-events-tracker skill).
    """
    rows = await db_manager.get_latest_skill_output("market-events-tracker", limit=4)
    return {
        "events": [
            {
                "run_date": str(r.get("run_date", "")),
                "output": r.get("output_json", {}),
            }
            for r in rows
        ],
    }


# ── 6. Minervini Screener ───────────────────────────────────────────────────

@router.get("/screener/latest")
async def screener_latest():
    """Current Minervini passers + near-misses."""
    history = await db_manager.get_minervini_history(days=2)
    if not history:
        return {"scan_date": None, "passers": [], "near_miss": [], "changes": {}}

    latest = history[0]
    previous = history[1] if len(history) > 1 else None

    return {
        "scan_date": str(latest.get("scan_date", "")),
        "total_screened": latest.get("total_screened", 0),
        "total_passing": latest.get("total_passing", 0),
        "near_miss": latest.get("near_miss", 0),
        "passers": latest.get("passers", []),
        "new_additions": latest.get("new_additions", []),
        "new_removals": latest.get("new_removals", []),
        "results": latest.get("results_json", {}),
        "previous_date": str(previous.get("scan_date", "")) if previous else None,
    }


@router.get("/screener/history")
async def screener_history(days: int = Query(30, le=90)):
    """Longitudinal Minervini tracking."""
    history = await db_manager.get_minervini_history(days=days)
    return {
        "history": [
            {
                "scan_date": str(h.get("scan_date", "")),
                "total_passing": h.get("total_passing", 0),
                "near_miss": h.get("near_miss", 0),
                "passers": h.get("passers", []),
                "new_additions": h.get("new_additions", []),
                "new_removals": h.get("new_removals", []),
            }
            for h in history
        ],
    }


# ── 7. Stock Intelligence ───────────────────────────────────────────────────

@router.get("/stock-intelligence/{symbol}")
async def stock_intelligence(symbol: str):
    """
    Composite intelligence view for a single ticker:
    Minervini grade, SEC filings, equity research, flow activity, alerts.
    """
    sym = symbol.upper()

    # Minervini status
    minervini = await db_manager.get_minervini_history(days=5)
    minervini_grade = None
    grade_history = []
    for scan in minervini:
        passers = scan.get("passers", [])
        results = scan.get("results_json", {})
        if sym in passers:
            if minervini_grade is None:
                minervini_grade = "8/8 FULL PASS"
                if results and sym in results:
                    minervini_grade = results[sym].get("grade", "8/8 FULL PASS")
            grade_history.append({
                "date": str(scan.get("scan_date", "")),
                "status": "PASSING",
            })
        else:
            grade_history.append({
                "date": str(scan.get("scan_date", "")),
                "status": "NOT PASSING",
            })

    # SEC filings
    sec = await db_manager.get_latest_skill_output("sec-filing-analysis", symbol=sym, limit=1)

    # Equity research
    research = await db_manager.get_latest_skill_output("equity-research", symbol=sym, limit=1)

    # Flow activity (recent)
    flow_alerts = await db_manager.get_latest_skill_output("flow_alerts", symbol=sym, limit=1)

    # Dynamic alerts
    alerts = await db_manager.get_stock_alerts(symbol=sym, limit=10)

    # Recent flow from CSV
    today_str = _today_str()
    all_flow = load_all_flow(DATA_DIR, target_date=today_str)
    symbol_flow = [e for e in all_flow if e.get("symbol") == sym]
    if not symbol_flow:
        # Try most recent date
        all_flow = load_all_flow(DATA_DIR)
        symbol_flow = [e for e in all_flow if e.get("symbol") == sym]
        if symbol_flow:
            dates = sorted(set(e.get("date", "") for e in symbol_flow))
            if dates:
                latest = dates[-1]
                symbol_flow = [e for e in symbol_flow if e.get("date") == latest]

    flow_summary = None
    if symbol_flow:
        total_prem = sum(e.get("premium_usd", 0) or 0 for e in symbol_flow)
        call_prem = sum(e.get("premium_usd", 0) or 0 for e in symbol_flow if e.get("call_put") == "CALL")
        put_prem = sum(e.get("premium_usd", 0) or 0 for e in symbol_flow if e.get("call_put") == "PUT")
        flow_summary = {
            "total_premium_fmt": format_premium_m(total_prem),
            "call_premium_fmt": format_premium_m(call_prem),
            "put_premium_fmt": format_premium_m(put_prem),
            "trades": len(symbol_flow),
            "direction": classify_net_direction(call_prem, put_prem),
            "sources": list(set(e["source"] for e in symbol_flow)),
        }

    return {
        "symbol": sym,
        "sector": get_sector(sym),
        "marks": get_ticker_marks_str(sym),
        "minervini": {
            "grade": minervini_grade,
            "history": grade_history,
        },
        "sec_filing": sec[0].get("output_json") if sec else None,
        "equity_research": research[0].get("output_json") if research else None,
        "flow_activity": flow_summary,
        "flow_alerts": flow_alerts[0].get("output_json") if flow_alerts else None,
        "alerts": [
            {
                "date": str(a.get("alert_date", "")),
                "type": a.get("alert_type", ""),
                "severity": a.get("severity", ""),
                "headline": a.get("headline", ""),
                "detail": a.get("detail_json", {}),
            }
            for a in alerts
        ],
    }


# ── 8. Alerts ────────────────────────────────────────────────────────────────

@router.get("/alerts")
async def alerts(
    target_date: str | None = Query(None, alias="date"),
    severity: str | None = Query(None),
    alert_type: str | None = Query(None, alias="type"),
    limit: int = Query(50, le=200),
):
    """Dynamic change alerts across all tickers."""
    d = date.fromisoformat(target_date) if target_date else None
    all_alerts = await db_manager.get_stock_alerts(target_date=d, limit=limit)

    if severity:
        all_alerts = [a for a in all_alerts if a.get("severity") == severity.upper()]
    if alert_type:
        all_alerts = [a for a in all_alerts if a.get("alert_type") == alert_type.upper()]

    return {
        "total": len(all_alerts),
        "alerts": [
            {
                "date": str(a.get("alert_date", "")),
                "symbol": a.get("symbol", ""),
                "type": a.get("alert_type", ""),
                "severity": a.get("severity", ""),
                "headline": a.get("headline", ""),
                "detail": a.get("detail_json", {}),
            }
            for a in all_alerts
        ],
    }

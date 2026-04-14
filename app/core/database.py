"""
PostgreSQL + PGVector database manager.

Tables:
  - flow_entries: Raw options flow data (daily ingest)
  - news_entries: Walter news data with sentiment
  - analysis_results: Completed analysis outputs
  - embeddings: PGVector embeddings for semantic search over flow patterns
  - flow_tracker: Daily metrics for pattern recognition (replaces JSON tracker)
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any

import asyncpg
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import settings

logger = structlog.get_logger(__name__)

# ── SQL Schema ───────────────────────────────────────────────────────────────

INIT_SQL = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Raw flow entries (all 4 sources unified)
CREATE TABLE IF NOT EXISTS flow_entries (
    id              BIGSERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    source          VARCHAR(32) NOT NULL,  -- golden_sweep, sweep, sexy_flow, trady_flow
    symbol          VARCHAR(16) NOT NULL,
    strike          NUMERIC(12,2),
    expiration      DATE,
    call_put        VARCHAR(4),
    premium_raw     VARCHAR(32),
    premium_usd     NUMERIC(18,2),
    vol_oi_ratio    NUMERIC(10,2),
    alert_type      VARCHAR(32),
    description     TEXT,
    oi              BIGINT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_flow_date ON flow_entries(date);
CREATE INDEX IF NOT EXISTS idx_flow_symbol ON flow_entries(symbol);
CREATE INDEX IF NOT EXISTS idx_flow_date_symbol ON flow_entries(date, symbol);

-- News entries (from walter_openai.csv)
CREATE TABLE IF NOT EXISTS news_entries (
    id                      BIGSERIAL PRIMARY KEY,
    date                    DATE NOT NULL,
    summary                 TEXT,
    sentiment_score         NUMERIC(3,1),
    tickers                 TEXT[],
    geopolitical_entities   TEXT[],
    sectors                 TEXT[],
    commodities             TEXT[],
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_date ON news_entries(date);

-- Analysis results (one per daily run)
CREATE TABLE IF NOT EXISTS analysis_results (
    id              BIGSERIAL PRIMARY KEY,
    date            DATE NOT NULL UNIQUE,
    analysis_type   VARCHAR(16) NOT NULL,  -- weekday, weekend
    task1_json      JSONB,                  -- news-flow correlation
    task2_json      JSONB,                  -- geopolitical
    task3_json      JSONB,                  -- top 10 flow
    task4_json      JSONB,                  -- OPEX context
    executive_summary TEXT,
    watchlist_json  JSONB,
    risk_json       JSONB,
    docx_path       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Daily flow tracker (replaces flow_pattern_tracker.json)
CREATE TABLE IF NOT EXISTS flow_tracker (
    id                  BIGSERIAL PRIMARY KEY,
    date                DATE NOT NULL UNIQUE,
    day_of_week         VARCHAR(12),
    market_data         JSONB,      -- sp500, dow, nasdaq, new_ath
    flow_stats          JSONB,      -- totals by source
    top_sweeps          JSONB,      -- top N sweeps
    vol_oi_outliers     JSONB,      -- >50x entries
    news_flow_aligned   TEXT[],
    news_flow_divergent TEXT[],
    sector_momentum     JSONB,
    commodities         JSONB,
    geopolitical_risk   VARCHAR(32),
    opex_context        JSONB,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- PGVector embeddings for semantic search over analysis history
CREATE TABLE IF NOT EXISTS analysis_embeddings (
    id              BIGSERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    content_type    VARCHAR(32),    -- flow_summary, news_summary, trade_idea
    content         TEXT NOT NULL,
    embedding       vector(768),    -- nomic-embed-text dimension
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_embed_date ON analysis_embeddings(date);

-- ── Dashboard Schema ────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS dashboard;

-- Skill outputs (SEC filings, equity research, market events)
CREATE TABLE IF NOT EXISTS dashboard.skill_outputs (
    id            BIGSERIAL PRIMARY KEY,
    skill_name    VARCHAR(64) NOT NULL,
    run_date      DATE NOT NULL,
    symbol        VARCHAR(16),
    output_json   JSONB NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_unique
    ON dashboard.skill_outputs(skill_name, run_date, COALESCE(symbol, '__GLOBAL__'));

-- Minervini screener longitudinal tracking
CREATE TABLE IF NOT EXISTS dashboard.minervini_tracker (
    id             BIGSERIAL PRIMARY KEY,
    scan_date      DATE NOT NULL UNIQUE,
    total_screened INT,
    total_passing  INT,
    near_miss      INT,
    passers        TEXT[],
    new_additions  TEXT[],
    new_removals   TEXT[],
    results_json   JSONB,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- SEC Filing Analysis
CREATE TABLE IF NOT EXISTS dashboard.sec_filing_analysis (
    id         BIGSERIAL PRIMARY KEY,
    symbol     VARCHAR(16) NOT NULL,
    run_date   DATE NOT NULL,
    html       TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, run_date)
);

-- Equity Research
CREATE TABLE IF NOT EXISTS dashboard.equity_research (
    id         BIGSERIAL PRIMARY KEY,
    symbol     VARCHAR(16) NOT NULL,
    run_date   DATE NOT NULL,
    html       TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, run_date)
);

-- Sector flow time-series
CREATE TABLE IF NOT EXISTS dashboard.sector_flow_history (
    id           BIGSERIAL PRIMARY KEY,
    date         DATE NOT NULL,
    sector       VARCHAR(64) NOT NULL,
    bull_premium NUMERIC(18,2),
    bear_premium NUMERIC(18,2),
    net_premium  NUMERIC(18,2),
    signal       VARCHAR(32),
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sector_date
    ON dashboard.sector_flow_history(date, sector);

-- Stock intelligence alerts (change detection)
CREATE TABLE IF NOT EXISTS dashboard.stock_alerts (
    id           BIGSERIAL PRIMARY KEY,
    alert_date   DATE NOT NULL,
    symbol       VARCHAR(16) NOT NULL,
    alert_type   VARCHAR(32) NOT NULL,
    severity     VARCHAR(16) NOT NULL,
    headline     TEXT NOT NULL,
    detail_json  JSONB,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alerts_date ON dashboard.stock_alerts(alert_date);
CREATE INDEX IF NOT EXISTS idx_alerts_symbol ON dashboard.stock_alerts(symbol);

-- Analyst consensus ratings (from Benzinga via Massive API)
CREATE TABLE IF NOT EXISTS dashboard.analyst_consensus (
    id             BIGSERIAL PRIMARY KEY,
    ticker         VARCHAR(16) NOT NULL,
    fetch_date     DATE NOT NULL,
    consensus      VARCHAR(32),        -- Strong Buy, Buy, Hold, Sell, Strong Sell
    target_low     NUMERIC(12,2),
    target_mean    NUMERIC(12,2),
    target_high    NUMERIC(12,2),
    total_analysts INT,
    buy_count      INT,
    hold_count     INT,
    sell_count     INT,
    raw_json       JSONB,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, fetch_date)
);
CREATE INDEX IF NOT EXISTS idx_consensus_ticker ON dashboard.analyst_consensus(ticker);

-- Adjusted portfolio weights (post-HRP thematic + macro overlay)
CREATE TABLE IF NOT EXISTS dashboard.portfolio_adjusted (
    id             BIGSERIAL PRIMARY KEY,
    run_date       DATE NOT NULL,
    ticker         VARCHAR(16) NOT NULL,
    strategy       VARCHAR(32) NOT NULL,   -- e.g. HRP_1M_adjusted
    hrp_weight     NUMERIC(8,6),           -- original HRP weight
    adj_weight     NUMERIC(8,6),           -- after overlay
    thematic_boost NUMERIC(8,4) DEFAULT 0, -- theme alignment score
    consensus_boost NUMERIC(8,4) DEFAULT 0,-- analyst consensus score
    hedge_flag     BOOLEAN DEFAULT FALSE,  -- is this a macro hedge position
    notes          TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(run_date, ticker, strategy)
);
"""


class DatabaseManager:
    """Async database connection manager with PGVector support."""

    def __init__(self):
        self._engine = None
        self._session_factory = None
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        """Create async engine and initialize schema."""
        logger.info("initializing_database", host=settings.postgres_host)

        self._engine = create_async_engine(
            settings.database_url,
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
            echo=settings.app_debug,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Raw asyncpg pool for bulk operations
        self._pool = await asyncpg.create_pool(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password,
            database=settings.postgres_db,
            min_size=5,
            max_size=settings.postgres_pool_size,
        )

        # Run schema init — each statement in its own transaction
        # so a failure (e.g., pgvector extension) doesn't cascade
        for statement in INIT_SQL.split(";"):
            stmt = statement.strip()
            if not stmt:
                continue
            try:
                async with self._engine.begin() as conn:
                    await conn.execute(text(stmt))
            except Exception as e:
                logger.warning("schema_init_skip", statement=stmt[:60], error=str(e)[:80])

        logger.info("database_initialized")

    async def shutdown(self) -> None:
        if self._engine:
            await self._engine.dispose()
        if self._pool:
            await self._pool.close()
        logger.info("database_shutdown")

    def get_session(self) -> AsyncSession:
        """Get a new async session."""
        if not self._session_factory:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._session_factory()

    @property
    def pool(self) -> asyncpg.Pool:
        if not self._pool:
            raise RuntimeError("Database pool not initialized.")
        return self._pool

    # ── Convenience Methods ──────────────────────────────────────────────

    async def insert_flow_entries(self, entries: list[dict[str, Any]]) -> int:
        """Bulk insert flow entries using asyncpg COPY for speed."""
        if not entries:
            return 0
        async with self._pool.acquire() as conn:
            result = await conn.executemany(
                """
                INSERT INTO flow_entries (date, source, symbol, strike, expiration,
                    call_put, premium_raw, premium_usd, vol_oi_ratio, alert_type, description, oi)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT DO NOTHING
                """,
                [
                    (
                        date.fromisoformat(e["date"]) if isinstance(e["date"], str) else e["date"],
                        e["source"], e["symbol"], e.get("strike"),
                        e.get("expiration"), e.get("call_put"), e.get("premium_raw"),
                        e.get("premium_usd"), e.get("vol_oi_ratio"), e.get("alert_type"),
                        e.get("description"), e.get("oi"),
                    )
                    for e in entries
                ],
            )
        return len(entries)

    async def insert_news_entries(self, entries: list[dict[str, Any]]) -> int:
        """Bulk insert news entries."""
        if not entries:
            return 0
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO news_entries (date, summary, sentiment_score, tickers,
                    geopolitical_entities, sectors, commodities)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT DO NOTHING
                """,
                [
                    (
                        date.fromisoformat(e["date"]) if isinstance(e["date"], str) else e["date"],
                        e.get("summary"), e.get("sentiment_score"),
                        e.get("tickers", []), e.get("geopolitical_entities", []),
                        e.get("sectors", []), e.get("commodities", []),
                    )
                    for e in entries
                ],
            )
        return len(entries)

    async def save_analysis_result(self, result: dict[str, Any]) -> None:
        """Upsert a daily analysis result."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO analysis_results (date, analysis_type, task1_json, task2_json,
                    task3_json, task4_json, executive_summary, watchlist_json, risk_json, docx_path)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (date) DO UPDATE SET
                    analysis_type = EXCLUDED.analysis_type,
                    task1_json = EXCLUDED.task1_json,
                    task2_json = EXCLUDED.task2_json,
                    task3_json = EXCLUDED.task3_json,
                    task4_json = EXCLUDED.task4_json,
                    executive_summary = EXCLUDED.executive_summary,
                    watchlist_json = EXCLUDED.watchlist_json,
                    risk_json = EXCLUDED.risk_json,
                    docx_path = EXCLUDED.docx_path
                """,
                result["date"], result["analysis_type"],
                result.get("task1_json"), result.get("task2_json"),
                result.get("task3_json"), result.get("task4_json"),
                result.get("executive_summary"),
                result.get("watchlist_json"), result.get("risk_json"),
                result.get("docx_path"),
            )

    async def save_tracker_entry(self, entry: dict[str, Any]) -> None:
        """Upsert a daily flow tracker entry."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO flow_tracker (date, day_of_week, market_data, flow_stats,
                    top_sweeps, vol_oi_outliers, news_flow_aligned, news_flow_divergent,
                    sector_momentum, commodities, geopolitical_risk, opex_context, notes)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (date) DO UPDATE SET
                    market_data = EXCLUDED.market_data,
                    flow_stats = EXCLUDED.flow_stats,
                    top_sweeps = EXCLUDED.top_sweeps,
                    vol_oi_outliers = EXCLUDED.vol_oi_outliers,
                    news_flow_aligned = EXCLUDED.news_flow_aligned,
                    news_flow_divergent = EXCLUDED.news_flow_divergent,
                    sector_momentum = EXCLUDED.sector_momentum,
                    commodities = EXCLUDED.commodities,
                    geopolitical_risk = EXCLUDED.geopolitical_risk,
                    opex_context = EXCLUDED.opex_context,
                    notes = EXCLUDED.notes
                """,
                entry["date"], entry.get("day_of_week"),
                entry.get("market_data"), entry.get("flow_stats"),
                entry.get("top_sweeps"), entry.get("vol_oi_outliers"),
                entry.get("news_flow_aligned", []), entry.get("news_flow_divergent", []),
                entry.get("sector_momentum"), entry.get("commodities"),
                entry.get("geopolitical_risk"), entry.get("opex_context"),
                entry.get("notes"),
            )

    async def get_flow_by_date(self, target_date: date) -> list[dict]:
        """Retrieve all flow entries for a given date."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM flow_entries WHERE date = $1 ORDER BY premium_usd DESC",
                target_date,
            )
            return [dict(r) for r in rows]

    async def get_recent_tracker(self, days: int = 5) -> list[dict]:
        """Get last N days of tracker data for continuity narrative."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM flow_tracker ORDER BY date DESC LIMIT $1",
                days,
            )
            return [dict(r) for r in rows]

    # ── Dashboard Schema Methods ──────────────────────────────────────────

    async def save_skill_output(
        self, skill_name: str, run_date: date, output_json: dict, symbol: str | None = None
    ) -> None:
        """Upsert a skill output row."""
        import json as _json
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO dashboard.skill_outputs (skill_name, run_date, symbol, output_json)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (skill_name, run_date, COALESCE(symbol, '__GLOBAL__'))
                DO UPDATE SET output_json = EXCLUDED.output_json, created_at = NOW()
                """,
                skill_name, run_date, symbol, _json.dumps(output_json),
            )

    async def get_latest_skill_output(
        self, skill_name: str, symbol: str | None = None, limit: int = 1
    ) -> list[dict]:
        """Get the most recent skill output(s)."""
        async with self._pool.acquire() as conn:
            if symbol:
                rows = await conn.fetch(
                    """
                    SELECT * FROM dashboard.skill_outputs
                    WHERE skill_name = $1 AND symbol = $2
                    ORDER BY run_date DESC LIMIT $3
                    """,
                    skill_name, symbol, limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM dashboard.skill_outputs
                    WHERE skill_name = $1 AND symbol IS NULL
                    ORDER BY run_date DESC LIMIT $2
                    """,
                    skill_name, limit,
                )
            return [dict(r) for r in rows]

    async def save_sec_filing_output(self, symbol: str, run_date: date, html: str) -> None:
        """Upsert SEC filing analysis HTML output."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO dashboard.sec_filing_analysis (symbol, run_date, html)
                VALUES ($1, $2, $3)
                ON CONFLICT (symbol, run_date)
                DO UPDATE SET html = EXCLUDED.html, created_at = NOW()
                """,
                symbol, run_date, html,
            )

    async def get_latest_sec_filing_output(self, symbol: str) -> str | None:
        """Get the most recent SEC filing analysis HTML for a ticker."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT html FROM dashboard.sec_filing_analysis
                WHERE symbol = $1
                ORDER BY run_date DESC LIMIT 1
                """,
                symbol,
            )
            return dict(row)["html"] if row else None

    async def save_equity_research_output(self, symbol: str, run_date: date, html: str) -> None:
        """Upsert equity research HTML output."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO dashboard.equity_research (symbol, run_date, html)
                VALUES ($1, $2, $3)
                ON CONFLICT (symbol, run_date)
                DO UPDATE SET html = EXCLUDED.html, created_at = NOW()
                """,
                symbol, run_date, html,
            )

    async def get_latest_equity_research_output(self, symbol: str) -> str | None:
        """Get the most recent equity research HTML for a ticker."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT html FROM dashboard.equity_research
                WHERE symbol = $1
                ORDER BY run_date DESC LIMIT 1
                """,
                symbol,
            )
            return dict(row)["html"] if row else None

    async def save_minervini_scan(self, entry: dict) -> None:
        """Upsert a Minervini scan result."""
        import json as _json
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO dashboard.minervini_tracker
                    (scan_date, total_screened, total_passing, near_miss,
                     passers, new_additions, new_removals, results_json)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                ON CONFLICT (scan_date) DO UPDATE SET
                    total_screened = EXCLUDED.total_screened,
                    total_passing = EXCLUDED.total_passing,
                    near_miss = EXCLUDED.near_miss,
                    passers = EXCLUDED.passers,
                    new_additions = EXCLUDED.new_additions,
                    new_removals = EXCLUDED.new_removals,
                    results_json = EXCLUDED.results_json
                """,
                entry["scan_date"], entry.get("total_screened", 0),
                entry.get("total_passing", 0), entry.get("near_miss", 0),
                entry.get("passers", []), entry.get("new_additions", []),
                entry.get("new_removals", []),
                _json.dumps(entry.get("results_json", {})),
            )

    async def get_minervini_history(self, days: int = 30) -> list[dict]:
        """Get recent Minervini scan history."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM dashboard.minervini_tracker
                ORDER BY scan_date DESC LIMIT $1
                """,
                days,
            )
            return [dict(r) for r in rows]

    async def save_sector_flow(self, rows: list[dict]) -> None:
        """Upsert sector flow history rows."""
        if not rows:
            return
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO dashboard.sector_flow_history
                    (date, sector, bull_premium, bear_premium, net_premium, signal)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (date, sector) DO UPDATE SET
                    bull_premium = EXCLUDED.bull_premium,
                    bear_premium = EXCLUDED.bear_premium,
                    net_premium = EXCLUDED.net_premium,
                    signal = EXCLUDED.signal
                """,
                [
                    (r["date"], r["sector"], r["bull_premium"],
                     r["bear_premium"], r["net_premium"], r["signal"])
                    for r in rows
                ],
            )

    async def get_sector_flow_history(self, days: int = 30) -> list[dict]:
        """Get recent sector flow history."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM dashboard.sector_flow_history
                ORDER BY date DESC, bull_premium + bear_premium DESC
                LIMIT $1
                """,
                days * 20,  # ~20 sectors per day
            )
            return [dict(r) for r in rows]

    async def save_stock_alert(self, alert: dict) -> None:
        """Insert a stock alert."""
        import json as _json
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO dashboard.stock_alerts
                    (alert_date, symbol, alert_type, severity, headline, detail_json)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """,
                alert["alert_date"], alert["symbol"], alert["alert_type"],
                alert["severity"], alert["headline"],
                _json.dumps(alert.get("detail_json", {})),
            )

    async def get_stock_alerts(
        self, target_date: date | None = None, symbol: str | None = None, limit: int = 50
    ) -> list[dict]:
        """Get stock alerts with optional filters."""
        async with self._pool.acquire() as conn:
            conditions = []
            params = []
            idx = 1
            if target_date:
                conditions.append(f"alert_date = ${idx}")
                params.append(target_date)
                idx += 1
            if symbol:
                conditions.append(f"symbol = ${idx}")
                params.append(symbol)
                idx += 1
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)
            rows = await conn.fetch(
                f"""
                SELECT * FROM dashboard.stock_alerts
                {where}
                ORDER BY alert_date DESC, severity ASC
                LIMIT ${idx}
                """,
                *params,
            )
            return [dict(r) for r in rows]

    async def get_analyst_consensus(self, ticker: str) -> dict | None:
        """Get latest analyst consensus for a ticker."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM dashboard.analyst_consensus
                WHERE ticker = $1
                ORDER BY fetch_date DESC LIMIT 1
                """,
                ticker,
            )
            return dict(row) if row else None

    async def get_portfolio_adjusted(self, run_date: date | None = None, strategy: str | None = None) -> list[dict]:
        """Get adjusted portfolio weights."""
        async with self._pool.acquire() as conn:
            conditions = []
            params = []
            idx = 1
            if run_date:
                conditions.append(f"run_date = ${idx}")
                params.append(run_date)
                idx += 1
            if strategy:
                conditions.append(f"strategy = ${idx}")
                params.append(strategy)
                idx += 1
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = await conn.fetch(
                f"""
                SELECT * FROM dashboard.portfolio_adjusted
                {where}
                ORDER BY adj_weight DESC
                """,
                *params,
            )
            return [dict(r) for r in rows]

    async def semantic_search(
        self, query_embedding: list[float], limit: int = 5, content_type: str | None = None
    ) -> list[dict]:
        """Semantic search over analysis embeddings using PGVector."""
        async with self._pool.acquire() as conn:
            if content_type:
                rows = await conn.fetch(
                    """
                    SELECT content, metadata, date,
                           embedding <=> $1::vector AS distance
                    FROM analysis_embeddings
                    WHERE content_type = $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                    """,
                    str(query_embedding), content_type, limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT content, metadata, date,
                           embedding <=> $1::vector AS distance
                    FROM analysis_embeddings
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                    """,
                    str(query_embedding), limit,
                )
            return [dict(r) for r in rows]


# Singleton
db_manager = DatabaseManager()

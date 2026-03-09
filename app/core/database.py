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

        # Run schema init
        async with self._engine.begin() as conn:
            for statement in INIT_SQL.split(";"):
                stmt = statement.strip()
                if stmt:
                    await conn.execute(text(stmt))

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
                        e["date"], e["source"], e["symbol"], e.get("strike"),
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
                        e["date"], e.get("summary"), e.get("sentiment_score"),
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

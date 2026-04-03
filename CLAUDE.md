# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Start the API server (dev)
uvicorn app.main:app --reload

# Run analysis for a specific date via CLI
python scripts/run_analysis.py --date 2026-03-06 --type weekday

# Refresh formatted CSV data into PostgreSQL (full replace)
bash scripts/pg_refresh.sh

# Fetch OHLC + technicals into ohlc_daily / ta_daily
python scripts/update_technicals.py --mode init   # full 2-year rebuild
python scripts/update_technicals.py --mode daily  # incremental append

# Aggregate flow data with scoring/direction/sectors
python scripts/flow_aggregator.py

# Start infrastructure (PostgreSQL)
docker compose up -d postgres

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run a single test class
pytest tests/test_services.py::TestDeepITMRule -v

# Lint & format
ruff check .
ruff format .

# Type check
mypy app/
```

## Architecture

**AI-powered options flow analysis agent** 


### API Routers

| Router | Prefix | Purpose |
|--------|--------|---------|
| `health.py` | `/health` | Readiness/liveness checks |
| `analysis.py` | `/api/v1/analysis` | Trigger LangGraph pipeline runs |
| `market.py` | `/api/v1/market` | Market data lookups |
| `dashboard.py` | `/api/v1/dashboard` | Trading dashboard (9 endpoints, see below) |
| `websocket.py` | `/ws` | Pipeline progress broadcast |

### Dashboard API (`/api/v1/dashboard/`)

| Endpoint | Description |
|----------|-------------|
| `GET /command-center` | Market pulse (live prices), OPEX context, quick stats, alert counts |
| `GET /flow-scanner` | Scored/filtered/paginated flow with Deep ITM detection, direction, sectors |
| `GET /geopolitical` | Entity heatmap, sentiment buckets, recent headlines |
| `GET /sector-rotation` | Sector bull/bear premium aggregation with signal badges |
| `GET /market-events` | Weekly events calendar from skill outputs |
| `GET /screener/latest` | Current Minervini passers and change detection |
| `GET /screener/history` | Longitudinal Minervini tracking |
| `GET /stock-intelligence/{symbol}` | Composite per-ticker view (Minervini grade, SEC filings, flow, alerts) |
| `GET /alerts` | Dynamic change alerts with severity filtering |

The dashboard frontend (at `/home/rchiluka/workspace/trade-dashboard`) uses **HTTP polling** (10s prices, 30s flow, 5min others) — not WebSockets.

### Agent Responsibilities

| Agent | File | Tasks |
|-------|------|-------|
| Flow Analyst | `app/agents/flow_analyst/agent.py` | News-Flow Correlation, Top 10 trades |
| News Analyst | `app/agents/news_analyst/agent.py` | Geopolitical analysis |
| OPEX Analyst | `app/agents/opex_analyst/agent.py` | OPEX context, gamma mechanics |
| Coordinator | `app/agents/coordinator/graph.py` | LLM synthesis, report assembly |

### Service Layer (`app/services/`)

- **flow_parser.py** — CSV loading, ticker normalization (`GOOG→GOOGL`, `BRK.A→BRK.B`), aggregation
- **flow_scorer.py** — Composite scoring (premium/vol_oi/DTE/sweep_type/repeated/news), direction classification, sector mapping, sector aggregation
- **deep_itm.py** — Deep ITM Rule engine: put strikes >15-20% ITM classified as SOLD (bullish)
- **premium_calculator.py** — Parses M/K premium strings (`$4.33M`, `500K`), significance tiers
- **opex_calendar.py** — OPEX date (3rd Friday), phase detection, quad witching, VIX expiration
- **watchlist.py** — JP Morgan/IBD/Strong Buy ticker classification

### Core Infrastructure (`app/core/`)

- **client.py** — `ServiceContainer` DI container; provides `db`, `llm`, `polygon`
- **database.py** — `DatabaseManager` (asyncpg + SQLAlchemy async, PGVector). Manages `public` schema (flow_entries, news_entries, analysis_results, flow_tracker, analysis_embeddings) and `dashboard` schema (skill_outputs, minervini_tracker, sector_flow_history, stock_alerts)
- **ollama_client.py** — `OllamaManager` for local LLM inference (dual-GPU, async)
- **polygon_client.py** — `PolygonManager` for market data

All three managers initialize in parallel during FastAPI lifespan startup.

### Scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| `pg_refresh.sh` | Full-refresh formatted CSVs into PostgreSQL tables |
| `update_technicals.py` | Fetch OHLC from yfinance, compute TA indicators → `ohlc_daily` + `ta_daily` |
| `flow_aggregator.py` | Cross-channel flow aggregation with scoring, direction, Deep ITM detection |
| `run_analysis.py` | CLI entry point for LangGraph analysis pipeline |
| `watchlist-load.py` | Load watchlist tickers into DB |
| `walter_dual_gpt_processing.py` | Dual-GPT news processing pipeline |
| `walter_enrich.py` | Enrich walter news data |
| `proofread_report.py` | LLM proofreading of generated DOCX reports |

### State (`app/schema/state.py`)

`AgentState` TypedDict flows through all LangGraph nodes:
- `context: PipelineContext` — input data (dates, loaded CSVs, live prices)
- `flow_analysis`, `news_analysis`, `opex_analysis` — per-agent results
- `final_report: FinalReport` — coordinated output

## Skills & Agents

### Skills (`.claude/skills/`)

Skills are invoked via `/skill-name` and write results directly to the `dashboard.skill_outputs` table in PostgreSQL. All file paths in SKILL.md are relative to the skill's directory — always resolve to absolute paths before executing.

| Skill | Purpose |
|-------|---------|
| `minervini-screener` | 8-criteria SEPA Trend Template screening against `ta_daily` |
| `sec-filing-analysis` | Form 4 insider trading, 10-K/10-Q risk factors, 13F ownership, red flags |
| `equity-research` | Fundamental + macro + catalyst analysis for buy/hold/sell decisions |
| `market-events-tracker` | Weekly market events calendar with outcomes tracking |

### Agents (`.claude/agents/`)

| Agent | Purpose |
|-------|---------|
| `discord-data-pipeline` | Export Discord channels → format into CSVs → run market-events-tracker skill |

## MCP Servers

Configured in `.mcp.json`. Secrets are referenced as `${VAR}` and resolved from `.env` at runtime.

| Server | Purpose |
|--------|---------|
| `massive` | Polygon.io + Benzinga data (prices, news, ratings, earnings, financials, short interest) |
| `postgres` | Direct PostgreSQL queries via MCP |

## Configuration

Settings loaded from `.env` via Pydantic Settings (`config/settings.py`):

```ini
POLYGON_API_KEY=
MASSIVE_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5:9b
POSTGRES_HOST=127.0.0.1
POSTGRES_USER=rchiluka
POSTGRES_PASSWORD=
POSTGRES_DB=postgres
PG_USER=rchiluka
PG_PASS=
FLOW_DATA_DIR=/media/SHARED/trade-data/formatted
SUMMARY_OUTPUT_DIR=/media/SHARED/trade-data/summaries/docx
```

## Data Flow

```
Discord channels → discord-data-pipeline agent → formatted CSVs (FLOW_DATA_DIR)
                                                         ↓
                                              pg_refresh.sh → PostgreSQL tables
                                                         ↓
                                              Dashboard API ← reads CSVs + DB
                                                         ↓
                                              trade-dashboard (React) ← HTTP polling
```

Watchlist tickers → `update_technicals.py` → `ohlc_daily` + `ta_daily` → Minervini screener skill

## Key Domain Rules

- **Deep ITM Rule**: Put strikes >15-20% ITM → treated as SOLD (bullish), not a bearish bet
- **GOOG/GOOGL Aggregation**: Always normalized to GOOGL as a single Alphabet entity
- **Vol/OI Thresholds**: >10x = significant, >50x = extreme
- **Premium Tiers**: >$5M = MASSIVE, >$3M = MAJOR, >$1M = SIGNIFICANT, >$500K = NOTABLE
- **OPEX Phases**: pre_opex (reduce directional), opex_week (gamma pin), post_opex (best entry window)
- **Flow Scoring Weights**: premium 25%, vol/oi 20%, DTE 20%, sweep_type 15%, repeated 10%, news 10%
- **Sweep Type Scores**: golden_sweep 1.0, hot_contract 0.75, interval 0.5, sweep 0.4, sexy_flow 0.35, trady_flow 0.25

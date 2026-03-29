# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Start the API server (dev)
uvicorn app.main:app --reload

# Run analysis for a specific date via CLI
python scripts/run_analysis.py --date 2026-03-06 --type weekday

# Start infrastructure (PostgreSQL + PGVector)
docker compose up -d postgres

# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run a single test class
pytest tests/test_services.py::TestDeepITMRule -v

# Lint
ruff check .

# Format
ruff format .

# Type check
mypy app/
```

## Architecture

This is an **AI-powered options flow analysis agent** built with LangGraph + FastAPI + Ollama + Polygon.io + PostgreSQL/PGVector.

### Request Flow

`HTTP Request → FastAPI (app/main.py) → Router → LangGraph StateGraph (app/agents/coordinator/graph.py) → Parallel Agent Nodes → Coordinator → DOCX Report → PostgreSQL`

### LangGraph Pipeline (Analysis Graph)

The main pipeline is a directed acyclic graph with these nodes in order:

1. **ingest_data** — loads CSV files from `FLOW_DATA_DIR` (golden-sweeps, sweeps, sexy-flow, trady-flow, walter_openai news)
2. **fetch_prices** — fetches live prices from Polygon.io for unique symbols (max 50, rate-limited)
3. **flow_analysis** + **news_analysis** — run in parallel via fan-out edges from `fetch_prices`
4. **opex_analysis** — waits for both parallel nodes to complete
5. **coordinate_results** — LLM synthesis via Ollama produces executive summary + watchlist + risk assessment
6. **generate_report** — creates DOCX in JP Morgan format
7. **save_to_db** — persists to PostgreSQL

### Agent Responsibilities

| Agent | File | Tasks |
|-------|------|-------|
| Flow Analyst | `app/agents/flow_analyst/agent.py` | Task 1 (News-Flow Correlation), Task 3 (Top 10 trades) |
| News Analyst | `app/agents/news_analyst/agent.py` | Task 2 (Geopolitical analysis) |
| OPEX Analyst | `app/agents/opex_analyst/agent.py` | Task 4 (OPEX context, gamma mechanics) |
| Coordinator | `app/agents/coordinator/graph.py` | LLM synthesis, report assembly |

### Service Layer (`app/services/`)

- **flow_parser.py** — CSV loading, ticker normalization (`GOOG→GOOGL`, `BRK.A→BRK.B`), aggregation
- **deep_itm.py** — Deep ITM Rule engine: put strikes >15-20% ITM are classified as SOLD (bullish signal)
- **premium_calculator.py** — Parses M/K premium strings (`$4.33M`, `500K`) and assigns significance tiers
- **opex_calendar.py** — OPEX date calculation (3rd Friday), phase detection (pre/opex_week/post), quad witching, VIX expiration
- **watchlist.py** — JP Morgan/IBD/Strong Buy ticker classification

### Core Infrastructure (`app/core/`)

- **client.py** — `ServiceContainer` DI container injected into all agents and routers; provides `db`, `llm`, `polygon`
- **database.py** — `DatabaseManager` (asyncpg + SQLAlchemy async, PGVector support)
- **ollama_client.py** — `OllamaManager` for local LLM inference (dual-GPU, async)
- **polygon_client.py** — `PolygonManager` for market data

All three managers are initialized in parallel during FastAPI lifespan startup.

### State (`app/schema/state.py`)

`AgentState` is the central TypedDict flowing through all LangGraph nodes. Key fields:
- `context: PipelineContext` — input data (dates, loaded CSVs, live prices)
- `flow_analysis`, `news_analysis`, `opex_analysis` — per-agent typed results
- `final_report: FinalReport` — coordinated output

### WebSocket Events

Pipeline progress is broadcast to `ws://localhost:8000/ws/pipeline`. The dashboard at `/home/rchiluka/workspace/trade-dashboard` consumes these events. CORS is pre-configured for `localhost:3000` and `localhost:5173`.

## Configuration

Settings are loaded from `.env` via Pydantic Settings (`config/settings.py`). Key env vars:

```ini
POLYGON_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5:9b
POSTGRES_PASSWORD=
FLOW_DATA_DIR=/media/SHARED/trade-data/formatted
SUMMARY_OUTPUT_DIR=/media/SHARED/trade-data/summaries/docx
```

Copy `.env.example` to `.env` to get started.

## Skill Execution Convention

When running a skill, all script and file paths referenced in SKILL.md are relative to that
skill's directory: `.claude/skills/<skill-name>/`. Always resolve them to absolute paths before
executing.

Example: `scripts/minervini_screener.py` in the minervini-screener skill resolves to:
`.claude/skills/minervini-screener/scripts/minervini_screener.py`

## Key Domain Rules

- **Deep ITM Rule**: Put strikes >15-20% ITM → treated as SOLD (bullish), not a bearish bet
- **GOOG/GOOGL Aggregation**: Always normalized to GOOGL as a single Alphabet entity
- **Vol/OI Thresholds**: >10x = significant, >50x = extreme
- **Premium Tiers**: >$5M = MASSIVE, >$3M = MAJOR, >$1M = SIGNIFICANT, >$500K = NOTABLE
- **OPEX Phases**: pre_opex (reduce directional), opex_week (gamma pin), post_opex (best entry window)

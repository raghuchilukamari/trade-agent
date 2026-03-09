# 🤖 Trading Analysis Agent

**AI-powered institutional options flow analysis with Agent-to-Agent architecture.**

Built with LangGraph + FastAPI + Ollama + Polygon.io + PostgreSQL/PGVector.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI (app/main.py)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ /health  │  │/analysis │  │ /market  │  │  /ws/pipeline     │  │
│  └──────────┘  └────┬─────┘  └──────────┘  └───────────────────┘  │
│                     │                                               │
│              ┌──────▼──────────────────────────────────┐            │
│              │      LangGraph StateGraph                │            │
│              │  ┌────────────────────────────────┐      │            │
│              │  │  1. ingest_data (CSV loader)   │      │            │
│              │  │  2. fetch_prices (Polygon API) │      │            │
│              │  │        ┌─────────┬─────────┐   │      │            │
│              │  │  3a.   │  Flow   │  News   │   │  PARALLEL        │
│              │  │        │ Analyst │ Analyst │   │      │            │
│              │  │        └────┬────┴────┬────┘   │      │            │
│              │  │  3b.  OPEX Analyst    │        │      │            │
│              │  │  4. Coordinator (LLM) │        │      │            │
│              │  │  5. Report Generator  │        │      │            │
│              │  │  6. Save to DB        │        │      │            │
│              │  └────────────────────────────────┘      │            │
│              └──────────────────────────────────────────┘            │
│                     │              │              │                  │
│              ┌──────▼──┐  ┌───────▼──┐  ┌───────▼──────┐           │
│              │ Ollama  │  │ Polygon  │  │ PostgreSQL   │           │
│              │ (2xGPU) │  │   API    │  │ + PGVector   │           │
│              └─────────┘  └──────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

### Agent-to-Agent Pipeline

| Agent | Responsibility | Tasks |
|-------|---------------|-------|
| **Flow Analyst** | Options flow parsing, Deep ITM Rule, scoring | Task 1 (News-Flow Correlation), Task 3 (Top 10) |
| **News Analyst** | Sentiment analysis, geopolitical classification | Task 2 (Geopolitical Analysis) |
| **OPEX Analyst** | Gamma mechanics, expiration timing | Task 4 (OPEX Context) |
| **Coordinator** | LLM synthesis, report generation, DB persistence | Executive Summary, Risk Assessment |

---

## Project Structure

```
trading-agent/
├── app/
│   ├── main.py                      # FastAPI entry point + lifespan
│   ├── core/
│   │   ├── database.py              # PostgreSQL + PGVector (asyncpg)
│   │   ├── ollama_client.py         # Ollama LLM (dual-GPU, async)
│   │   ├── polygon_client.py        # Polygon.io market data
│   │   ├── client.py                # Dependency injection container
│   │   ├── auth.py                  # Secrets/vault loader
│   │   └── error_handling.py        # Exception handlers
│   ├── schema/
│   │   ├── state.py                 # AgentState TypedDict (LangGraph state)
│   │   └── models.py               # Pydantic request/response models
│   ├── routers/
│   │   ├── get_routers.py           # Router registry
│   │   ├── analysis.py              # /api/v1/analysis/* endpoints
│   │   ├── market.py                # /api/v1/market/* endpoints
│   │   ├── health.py                # /health endpoint
│   │   └── websocket.py             # WebSocket for live updates
│   ├── agents/
│   │   ├── coordinator/graph.py     # Main LangGraph orchestrator
│   │   ├── flow_analyst/agent.py    # Flow analysis agent
│   │   ├── news_analyst/agent.py    # News analysis agent
│   │   └── opex_analyst/agent.py    # OPEX analysis agent
│   ├── services/
│   │   ├── flow_parser.py           # CSV loading & aggregation
│   │   ├── premium_calculator.py    # Premium M/K parsing
│   │   ├── deep_itm.py             # Deep ITM Rule engine
│   │   ├── watchlist.py            # JP Morgan/IBD/Strong Buy lists
│   │   └── opex_calendar.py        # OPEX dates & gamma mechanics
│   ├── tools/
│   │   └── agent_tools.py          # LangGraph-callable tool functions
│   └── workers/
│       ├── daily_pipeline.py        # Pipeline orchestrator
│       └── report_generator.py      # DOCX generation (JP Morgan format)
├── config/
│   └── settings.py                  # Pydantic settings from env
├── scripts/
│   └── run_analysis.py              # CLI runner
├── tests/
├── docker-compose.yml               # PostgreSQL + PGVector + Agent
├── Dockerfile
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Ollama** running locally with a model pulled (`llama3.1:70b` recommended)
- **PostgreSQL 16** with pgvector extension (or use Docker)
- **Polygon.io** API key (free tier works for delayed data)

### 1. Clone & Setup

```bash
git clone <repo-url> trading-agent
cd trading-agent

# Copy environment config
cp .env.example .env
# Edit .env with your API keys and paths
```

### 2. Start Infrastructure (Docker)

```bash
# Start PostgreSQL + PGVector
docker compose up -d postgres

# Optional: start pgAdmin for DB inspection
docker compose --profile tools up -d pgadmin
```

### 3. Install Dependencies

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install
pip install -e ".[dev]"
```

### 4. Pull Ollama Model

```bash
# Recommended for dual-GPU setup
ollama pull llama3.1:70b

# Lighter alternative
ollama pull llama3.1:8b

# Embedding model
ollama pull nomic-embed-text
```

### 5. Run the Agent

```bash
# Start the API server
uvicorn app.main:app --reload

# Or via CLI for a specific date
python scripts/run_analysis.py --date 2026-03-06 --type weekday
```

---

## API Endpoints

### Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/analysis/run` | Trigger daily analysis pipeline |
| `GET` | `/api/v1/analysis/status/{date}` | Check pipeline status |
| `GET` | `/api/v1/analysis/quick-stats/{date}` | Get flow quick stats |
| `POST` | `/api/v1/analysis/chat` | Conversational trading Q&A |
| `GET` | `/api/v1/analysis/ticker/{symbol}` | Get flow summary for a ticker |
| `GET` | `/api/v1/analysis/history` | Get tracker history |

### Market Data

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/market/price/{symbol}` | Get current price |
| `GET` | `/api/v1/market/prices?symbols=AAPL,NVDA` | Batch prices |
| `GET` | `/api/v1/market/status` | Market open/closed |
| `GET` | `/api/v1/market/indices` | SPY/DIA/QQQ snapshot |
| `GET` | `/api/v1/market/news` | Latest market news |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `ws://localhost:8000/ws/pipeline` | Real-time pipeline progress |
| `ws://localhost:8000/ws/market` | Live market data feed |

---

## Configuration

### Dual-GPU Settings

The Ollama client is configured for dual-GPU inference. Set these in `.env`:

```ini
OLLAMA_NUM_GPU=2           # Number of GPUs to use
OLLAMA_NUM_THREADS=16      # CPU threads for preprocessing
OLLAMA_CONTEXT_LENGTH=32768  # Context window size
```

### Data Paths

```ini
FLOW_DATA_DIR=/media/SHARED/trade-data/formatted
SUMMARY_OUTPUT_DIR=/media/SHARED/trade-data/summaries/docx
```

---

## Key Trading Rules (Built-In)

1. **Deep ITM Rule**: Put strikes >15-20% ITM are treated as SOLD (bullish), not bought
2. **GOOG/GOOGL Aggregation**: Always combined as single Alphabet entity
3. **Vol/OI Thresholds**: >10x = significant, >50x = extreme institutional move
4. **Premium Tiers**: >$5M = massive conviction, >$3M = major positioning
5. **DTE Preference**: 14-90 days preferred for medium-term positioning
6. **OPEX Phases**: Pre-OPEX (reduce directional), OPEX week (gamma pin), Post-OPEX (best entry)

---

## UI Integration

The agent exposes WebSocket and REST endpoints ready for dashboard integration. The planned dashboard lives at `/home/rchiluka/workspace/trade-dashboard`.

**WebSocket events pushed to UI:**
```json
{"type": "status", "agent": "flow_analyst", "status": "running"}
{"type": "progress", "agent": "news_analyst", "pct": 50}
{"type": "result", "agent": "opex_analyst", "data": {...}}
{"type": "complete", "docx_path": "...", "executive_summary": "..."}
{"type": "error", "message": "..."}
```

**CORS** is pre-configured for `localhost:3000` and `localhost:5173`.

---

## Development

```bash
# Run tests
pytest tests/ -v

# Lint
ruff check .

# Type check
mypy app/

# Format
ruff format .
```

---

## License

MIT

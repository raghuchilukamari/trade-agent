# Trading Dashboard — System Architecture

## High-Level Orchestration

```
                        ┌─────────────────────────────────────────────────┐
                        │           DISCORD CHANNELS (Source)             │
                        │  golden-sweeps | sweeps | sexy-flow | trady     │
                        │  walter (news)                                  │
                        └──────────────────────┬──────────────────────────┘
                                               │
                    ┌──────────────────────────▼──────────────────────────┐
                    │          discord-data-pipeline (Agent)               │
                    │                                                     │
                    │  Step 1: discord-export-optimized.sh                │
                    │  Step 2: run_fmt.sh → pipe-delimited CSVs           │
                    │  Step 2.5: refresh_raw_db.py → raw.* tables  ◄─NEW │
                    │  Step 3a: Flow counts tracker                       │
                    │  Step 3b: Walter enrichment (Ollama)                │
                    │  Step 3c: Geopolitical analysis                     │
                    │  Step 3d: Flow aggregator → /tmp/flow_data.json     │
                    │  Step 3e: Market events tracker                     │
                    │  Step 4: HTML report generation                     │
                    │  Step 5: Proofreading                               │
                    └──────────────────────┬──────────────────────────────┘
                                           │
              ┌────────────────────────────▼────────────────────────────┐
              │                    PostgreSQL                           │
              │                                                        │
              │  ┌─── raw schema ──────────────────────────────────┐   │
              │  │ golden_sweeps | sexy_flow | sweeps | trady_flow │   │
              │  │ walter                                          │   │
              │  └─────────────────────────────────────────────────┘   │
              │                                                        │
              │  ┌─── public schema ───────────────────────────────┐   │
              │  │ ohlc_daily | ta_daily (technicals, MAs, RSI)    │   │
              │  └─────────────────────────────────────────────────┘   │
              │                                                        │
              │  ┌─── dashboard schema (NEW) ──────────────────────┐   │
              │  │ skill_outputs       — SEC, equity, events JSON  │   │
              │  │ minervini_tracker   — daily passers + diffs      │   │
              │  │ sector_flow_history — bull/bear by sector/day    │   │
              │  │ stock_alerts        — dynamic change alerts      │   │
              │  └─────────────────────────────────────────────────┘   │
              └────────────────────────┬───────────────────────────────┘
                                       │
       ┌───────────────────────────────▼───────────────────────────────┐
       │                  FastAPI Backend                               │
       │                                                               │
       │  Existing Routers              New Router                     │
       │  ├─ /api/v1/analysis/*         ├─ /api/v1/dashboard/          │
       │  ├─ /api/v1/market/*           │   ├─ command-center          │
       │  └─ /health                    │   ├─ flow-scanner            │
       │                                │   ├─ geopolitical            │
       │  Existing Services             │   ├─ market-events           │
       │  ├─ flow_parser.py             │   ├─ sector-rotation         │
       │  ├─ premium_calculator.py      │   ├─ screener/latest         │
       │  ├─ opex_calendar.py           │   ├─ screener/history        │
       │  ├─ deep_itm.py               │   ├─ stock-intelligence/{sym}│
       │                                │   ├─ alerts                  │
       │  └─ flow_scorer.py (NEW)       │   └─ skill-output/{skill}   │
       │                                └──────────────────────────────│
       │  External: Polygon.io (live prices, snapshots)                │
       └───────────────────────────────┬───────────────────────────────┘
                                       │  HTTP polling (10-30s)
                                       │
       ┌───────────────────────────────▼───────────────────────────────┐
       │              React Dashboard (trade-dashboard)                │
       │                                                               │
       │  ┌─ services/api.ts ────── HTTP fetch to all endpoints        │
       │  ├─ hooks/usePolling.ts ── generic interval polling           │
       │  │                                                            │
       │  ├─ Header ──────────────── Market pulse, OPEX countdown      │
       │  ├─ CommandCenter ───────── Pipeline status, alerts, stats    │
       │  ├─ FlowScanner ────────── Full ranked flow + filters         │
       │  ├─ StockAnalysis ───────── Gemini-powered deep dive          │
       │  ├─ MinerviniPanel ──────── Screener + SEC + equity + alerts  │
       │  ├─ GeopoliticalDashboard ─ Entity heatmap + sentiment        │
       │  ├─ MyWatchlist ─────────── Sector-organized + live prices    │
       │  ├─ MarketCalendar ──────── Events + outcomes                 │
       │  └─ SectorRotation ──────── Bull/bear flow by sector          │
       └──────────────────────────────────────────────────────────────┘
```

---

## Minervini Intelligence Pipeline (Daily)

```
┌──────────────────────────────────────────────────────────────────────┐
│                 run_stock_intelligence.py (daily)                     │
│                                                                      │
│  STEP 1: SCREEN                                                      │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ minervini_screener.py --universe all --save-db              │     │
│  │                                                             │     │
│  │ Input:  yfinance OHLCV for ~600 tickers (252 days each)    │     │
│  │ Output: MinerviniResult per ticker                          │     │
│  │         passers: [NVDA, AVGO, AXON, ...]                   │     │
│  │         near_miss: [AMD, CRM, ...]                         │     │
│  │         new_additions: [AXON]  (vs yesterday)              │     │
│  │         new_removals: [PLTR]   (vs yesterday)              │     │
│  │                                                             │     │
│  │ Writes → dashboard.minervini_tracker                       │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                              │                                       │
│  STEP 2: DEEP DIVE (for each passer)                                │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ For NVDA, AVGO, AXON, AMD, CRM, ...                        │     │
│  │                                                             │     │
│  │ ┌─ SEC Filing Analysis (skill) ──────────────────────┐     │     │
│  │ │  Input:  Web search "NVDA Form 4 SEC filing 2026"  │     │     │
│  │ │  Output: insider_sentiment: BUYING                 │     │     │
│  │ │          red_flags: []                              │     │     │
│  │ │          insider_net_flow: +$12.3M                  │     │     │
│  │ │          institutional_pct: 72%                     │     │     │
│  │ │  Writes → dashboard.skill_outputs                   │     │     │
│  │ └────────────────────────────────────────────────────┘     │     │
│  │                                                             │     │
│  │ ┌─ Equity Research (skill) ──────────────────────────┐     │     │
│  │ │  Input:  Web search fundamentals + peer comparison │     │     │
│  │ │  Output: recommendation: BUY                       │     │     │
│  │ │          confidence: HIGH                           │     │     │
│  │ │          pe_forward: 28.5                           │     │     │
│  │ │          revenue_growth: +94% YoY                   │     │     │
│  │ │          catalysts: ["GTC Conference", "B200 ramp"] │     │     │
│  │ │  Writes → dashboard.skill_outputs                   │     │     │
│  │ └────────────────────────────────────────────────────┘     │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                              │                                       │
│  STEP 3: OPTION FLOW OVERLAY                                        │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ Query raw.* WHERE Symbol IN (passers) AND Date = today     │     │
│  │                                                             │     │
│  │ For NVDA:                                                   │     │
│  │   sexy_flow: 8 trades, $4.2M total, 6 CALL / 2 PUT        │     │
│  │   golden_sweeps: 2 call sweeps, $1.8M                      │     │
│  │   Vol/OI outlier: 340C 2/21 → 43.6x Vol/OI                │     │
│  │   Put seller detected: 300P at ask (82%), $750K → BULLISH  │     │
│  │                                                             │     │
│  │ Writes → dashboard.stock_alerts (if thresholds exceeded)    │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                              │                                       │
│  STEP 4: CHANGE DETECTION                                           │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │ Compare today vs yesterday:                                 │     │
│  │                                                             │     │
│  │  AXON: NEW to 8/8 list    → BREAKOUT_CANDIDATE (HIGH)      │     │
│  │  PLTR: DROPPED from 8/8   → WEAKENING (MEDIUM)             │     │
│  │  NVDA: Flow premium 3x    → FLOW_SURGE (HIGH)              │     │
│  │  AVGO: Form 4 cluster buy → INSIDER_CONVICTION (HIGH)      │     │
│  │  AMD:  RS 82→71           → MOMENTUM_FADE (MEDIUM)         │     │
│  │                                                             │     │
│  │ Writes → dashboard.stock_alerts                             │     │
│  └─────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoint Data Flows

### `/api/v1/dashboard/command-center`

```
Request:  GET /api/v1/dashboard/command-center

Pipeline:
  Polygon.get_batch_prices(["SPY","QQQ","VIX","BTC-USD","DXY"])
  + opex_calendar.get_full_opex_context(2026-04-01)
  + SELECT count(*), max("Date") FROM raw.sexy_flow
  + SELECT count(*) FROM dashboard.stock_alerts WHERE alert_date = today AND severity = 'HIGH'

Response:
{
  "market_pulse": [
    {"symbol": "SPY", "price": 478.45, "change": 1.25, "change_pct": 0.26},
    {"symbol": "QQQ", "price": 412.12, "change": -2.34, "change_pct": -0.56},
    {"symbol": "VIX", "price": 13.45, "change": 0.45, "change_pct": 3.46},
    {"symbol": "BTC-USD", "price": 98450.00, "change": 1240.00, "change_pct": 1.27},
    {"symbol": "DXY", "price": 102.45, "change": -0.05, "change_pct": -0.05}
  ],
  "opex": {
    "next_monthly_opex": "2026-04-17",
    "days_to_opex": 16,
    "current_phase": "pre_opex",
    "gamma_assessment": "MODERATE",
    "is_quad_witching": false
  },
  "quick_stats": {
    "latest_date": "2026-03-27",
    "total_flow_entries": 342,
    "golden_sweeps": 28,
    "sexy_flow": 115,
    "sweeps": 164,
    "trady_flow": 35
  },
  "active_alerts": 3,
  "timestamp": "2026-04-01T14:30:00Z"
}
```

### `/api/v1/dashboard/flow-scanner`

```
Request:  GET /api/v1/dashboard/flow-scanner?date=2026-01-15&direction=ALL&sort_by=score&limit=3

Pipeline:
  1. UNION query across raw.golden_sweeps, raw.sexy_flow, raw.sweeps, raw.trady_flow
     WHERE "Date" = '2026-01-15'
  2. For each row → flow_scorer.calculate_composite_score()
  3. For each row → flow_scorer.classify_direction()
  4. For puts  → deep_itm.check_deep_itm()

Sample Input Row (raw.sexy_flow):
  Date=2026-01-15 | Symbol=ASML | Strike=1340.0 | Call_Put=PUT
  Premium=1.43M | Vol_OI_Ratio=null | Bid_Ask_Pct=18/67 | OTM_Pct=0%

After scoring:
  premium_usd=1,430,000 | direction=BEARISH (ask 67% < 70 threshold)
  score=62.4 (premium=80*.4 + vol_oi=5*.2 + dte=30*.1 + aggression=50*.1 + repeated=20*.1 + news=0*.1)
  significance=SIGNIFICANT | sector=Semiconductors | marks=[]

Response:
{
  "total_count": 342,
  "filtered_count": 342,
  "entries": [
    {
      "symbol": "TSM",
      "source": "golden_sweep",
      "strike": 345.0,
      "expiration": "2026-01-23",
      "call_put": "CALL",
      "premium_usd": 840000,
      "premium_fmt": "$840K",
      "significance": "NOTABLE",
      "vol_oi_ratio": null,
      "direction": "BULLISH",
      "score": 71.2,
      "sector": "Semiconductors",
      "marks": ["JP_MORGAN"],
      "deep_itm": null,
      "description": "call golden sweep"
    },
    {
      "symbol": "ASML",
      "source": "sexy_flow",
      "strike": 1340.0,
      "expiration": "2026-01-16",
      "call_put": "PUT",
      "premium_usd": 1430000,
      "premium_fmt": "$1.43M",
      "significance": "SIGNIFICANT",
      "vol_oi_ratio": null,
      "bid_ask_pct": "18/67",
      "direction": "BEARISH",
      "score": 62.4,
      "sector": "Semiconductors",
      "marks": [],
      "deep_itm": null
    },
    {
      "symbol": "UBER",
      "source": "sexy_flow",
      "strike": 86.0,
      "expiration": "2026-01-16",
      "call_put": "CALL",
      "premium_usd": 217000,
      "premium_fmt": "$217K",
      "significance": "MINOR",
      "vol_oi_ratio": 1.25,
      "bid_ask_pct": "27/70",
      "direction": "BULLISH",
      "score": 38.7,
      "sector": "Technology",
      "marks": ["STRONG_BUY"],
      "deep_itm": null
    }
  ],
  "put_sellers": [
    {
      "symbol": "MU",
      "strike": 280.0,
      "premium_fmt": "$1.2M",
      "ask_pct": 88,
      "listed_as": "PUT",
      "actually": "BULLISH (sold at ask)"
    }
  ]
}
```

### `/api/v1/dashboard/stock-intelligence/{symbol}`

```
Request:  GET /api/v1/dashboard/stock-intelligence/NVDA

Pipeline:
  1. dashboard.minervini_tracker → latest grade for NVDA
  2. dashboard.skill_outputs WHERE skill_name='sec_filing' AND symbol='NVDA'
  3. dashboard.skill_outputs WHERE skill_name='equity_research' AND symbol='NVDA'
  4. raw.* WHERE Symbol='NVDA' AND Date = latest → flow summary
  5. dashboard.stock_alerts WHERE symbol='NVDA' AND alert_date >= today-7

Response:
{
  "symbol": "NVDA",
  "minervini": {
    "grade": "8/8",
    "passes_template": true,
    "price": 152.30,
    "ma_50": 142.80,
    "ma_150": 128.40,
    "ma_200": 118.90,
    "rs_rating": 94.2,
    "pct_from_high": 4.1,
    "pct_above_low": 112.5,
    "first_passed": "2025-11-12",
    "consecutive_days": 98,
    "criteria": {
      "c1_price_above_150_200": true,
      "c2_ma150_above_ma200": true,
      "c3_ma200_trending_up": true,
      "c4_ma_alignment": true,
      "c5_price_above_50": true,
      "c6_above_low_30pct": true,
      "c7_within_high_25pct": true,
      "c8_rs_above_70": true
    }
  },
  "sec_filing": {
    "run_date": "2026-04-01",
    "insider_sentiment": "BUYING",
    "insider_net_flow": "+$12.3M (90 days)",
    "form4_summary": "CEO sold $2.1M (planned 10b5-1), CFO bought $850K open market",
    "red_flags": [],
    "institutional_ownership_pct": 72.4,
    "top_holders_change": "Vanguard +1.2%, BlackRock unchanged, ARK -0.8%"
  },
  "equity_research": {
    "run_date": "2026-04-01",
    "recommendation": "BUY",
    "confidence": "HIGH",
    "timeframe": "6-12 months",
    "key_metrics": {
      "pe_forward": 28.5,
      "ev_ebitda": 35.2,
      "revenue_growth_yoy": "+94%",
      "fcf_margin": "42%",
      "debt_to_equity": 0.41
    },
    "bull_case": ["Data center demand accelerating", "B200 ramp cycle", "AI inference TAM"],
    "bear_case": ["Valuation premium to peers", "China export controls risk"],
    "catalysts": [
      {"event": "GTC Conference", "date": "2026-05-15", "impact": "HIGH"},
      {"event": "Q1 Earnings", "date": "2026-05-28", "impact": "HIGH"}
    ]
  },
  "flow_activity": {
    "latest_date": "2026-03-27",
    "total_premium": "$6.0M",
    "direction": "BULLISH",
    "bull_premium": "$5.2M",
    "bear_premium": "$0.8M",
    "channels": ["golden_sweep", "sexy_flow", "sweeps"],
    "vol_oi_outliers": [
      {"strike": 160, "exp": "2026-04-17", "ratio": 43.6, "type": "CALL"}
    ],
    "put_sellers": [
      {"strike": 140, "premium": "$750K", "ask_pct": 82}
    ]
  },
  "alerts": [
    {
      "date": "2026-04-01",
      "type": "FLOW_SURGE",
      "severity": "HIGH",
      "headline": "NVDA flow premium 3x vs prior day ($6M vs $2M avg)"
    }
  ]
}
```

### `/api/v1/dashboard/alerts`

```
Request:  GET /api/v1/dashboard/alerts?date=2026-04-01

Response:
{
  "alerts": [
    {
      "symbol": "AXON",
      "type": "BREAKOUT_CANDIDATE",
      "severity": "HIGH",
      "headline": "AXON passed 8/8 Minervini criteria — NEW addition today",
      "detail": {"prev_grade": "7/8", "new_grade": "8/8", "criteria_gained": "c8_rs_above_70"}
    },
    {
      "symbol": "NVDA",
      "type": "FLOW_SURGE",
      "severity": "HIGH",
      "headline": "NVDA flow premium 3x vs prior day ($6M vs $2M avg)",
      "detail": {"today_premium": 6000000, "avg_premium": 2000000, "direction": "BULLISH"}
    },
    {
      "symbol": "AVGO",
      "type": "INSIDER_CONVICTION",
      "severity": "HIGH",
      "headline": "AVGO: 3 insider buys totaling $4.2M in past 7 days",
      "detail": {"insider_buys": 3, "total_value": 4200000, "period_days": 7}
    },
    {
      "symbol": "PLTR",
      "type": "WEAKENING",
      "severity": "MEDIUM",
      "headline": "PLTR dropped from 8/8 to 7/8 — lost c7 (>25% from high)",
      "detail": {"prev_grade": "8/8", "new_grade": "7/8", "criteria_lost": "c7_within_high_25pct"}
    },
    {
      "symbol": "AMD",
      "type": "MOMENTUM_FADE",
      "severity": "MEDIUM",
      "headline": "AMD RS rating declined 82 → 71 over 5 sessions",
      "detail": {"rs_current": 71, "rs_5d_ago": 82, "rs_change": -11}
    }
  ]
}
```

### `/api/v1/dashboard/sector-rotation`

```
Request:  GET /api/v1/dashboard/sector-rotation?days=5

Response:
{
  "sectors": [
    {
      "sector": "Semiconductors",
      "history": [
        {"date": "2026-03-23", "bull": 45200000, "bear": 12100000, "signal": "BULLISH"},
        {"date": "2026-03-24", "bull": 38700000, "bear": 15300000, "signal": "LEAN BULLISH"},
        {"date": "2026-03-25", "bull": 52100000, "bear": 8900000,  "signal": "BULLISH"},
        {"date": "2026-03-26", "bull": 41000000, "bear": 19500000, "signal": "LEAN BULLISH"},
        {"date": "2026-03-27", "bull": 61300000, "bear": 7200000,  "signal": "BULLISH"}
      ],
      "latest_signal": "BULLISH",
      "tickers": ["NVDA", "AMD", "AVGO", "TSM", "MU", "ASML"]
    },
    {
      "sector": "Energy",
      "history": [
        {"date": "2026-03-23", "bull": 8100000,  "bear": 12400000, "signal": "BEARISH"},
        {"date": "2026-03-27", "bull": 6500000,  "bear": 14200000, "signal": "BEARISH"}
      ],
      "latest_signal": "BEARISH",
      "tickers": ["XOM", "CVX", "OXY", "SLB"]
    }
  ]
}
```

---

## Data Refresh Timing

```
DAILY SCHEDULE
──────────────────────────────────────────────────────────────────

06:00  ┌─ Minervini Screener (pre-market)
       │   Screen all universes → dashboard.minervini_tracker
       │   Diff vs yesterday → stock_alerts (BREAKOUT/WEAKENING)
       │
06:30  ├─ Stock Intelligence Pipeline
       │   For each 8/8 + 7/8 passer:
       │     SEC filing analysis → dashboard.skill_outputs
       │     Equity research     → dashboard.skill_outputs
       │
09:30  ├─ Market Opens ─────────────────────────────────
       │   Dashboard polls /command-center every 10s
       │   Dashboard polls /flow-scanner every 30s
       │
       │   (Discord channels producing flow data throughout day)
       │
16:00  ├─ Market Closes ────────────────────────────────
       │
17:00  ├─ discord-data-pipeline (post-market)
       │   Export → Format → refresh_raw_db.py → raw.*
       │   Walter enrichment → geopolitical analysis
       │   Flow aggregator → sector_flow_history
       │   Market events update
       │   Report generation + proofreading
       │
17:30  └─ Flow Overlay + Change Detection
          Query raw.* for passer tickers
          Generate FLOW_SURGE / MOMENTUM_FADE alerts
          Dashboard auto-refreshes all panels

SUNDAY NIGHT
──────────────────────────────────────────────────────────────────
       ┌─ Market Events Tracker (upcoming week)
       │   Web search → dashboard.skill_outputs
       └─ Dashboard shows events on Monday morning
```

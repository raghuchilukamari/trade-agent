---
name: minervini-screener
description: >
  Screen stocks against Mark Minervini's SEPA Trend Template — the 8-criteria technical
  checklist that identifies Stage 2 uptrend stocks with superperformance potential. Use this
  skill whenever Raghu asks to run a Minervini screen, find trend template stocks, identify
  Stage 2 uptrends, screen for MA alignment, check if a stock passes Minervini criteria,
  find stocks near 52-week highs with strong relative strength, or any variation of
  "Minervini", "trend template", "SEPA", "Stage 2 screen", "MA alignment screen",
  "superperformance", or "which stocks are in uptrends". Also trigger when Raghu asks
  to screen his watchlists or a universe (S&P 500, NASDAQ 100) for technically strong stocks,
  or asks "what's setting up" or "which stocks look good technically". Run this screener
  BEFORE considering any new position entry — it's a first-pass filter.
---

# Minervini Trend Template Screener

Screen stocks against Mark Minervini's 8 SEPA criteria to identify confirmed Stage 2 uptrends.

**Note that all scripts and references paths are relative to current skill directory

## THE 8 CRITERIA (Raghu's specification)

A stock must meet **virtually all** of these to qualify:

| # | Criterion | Formula | Threshold |
|---|-----------|---------|-----------|
| C1 | Price above key MAs | Price > 150-day SMA AND Price > 200-day SMA | Both must pass |
| C2 | MA trend alignment | 150-day SMA > 200-day SMA | Confirms uptrend |
| C3 | 200-day MA trending up | 200-day SMA today > 200-day SMA 22 trading days ago | ≥1 month (prefer 4-5 months) |
| C4 | Full MA stack | 50-day SMA > 150-day SMA > 200-day SMA | All three aligned |
| C5 | Price above 50-day | Price > 50-day SMA | Near-term strength |
| C6 | Above 52-week low | (Price - 52w Low) / 52w Low ≥ 30% | **30% minimum** (Raghu's stricter threshold) |
| C7 | Near 52-week high | (52w High - Price) / 52w High ≤ 25% | Within striking distance |
| C8 | High relative strength | RS percentile rank ≥ 70 | Outperforming 70% of stocks |

**Grading:** 8/8 = FULL PASS (Stage 2 confirmed) | 6-7/8 = NEAR MISS (monitor) | <6 = FAIL

---

## TWO EXECUTION MODES

### Mode 1: Local Execution (large universes — 100+ tickers)

For screening S&P 500, NASDAQ 100, or Russell 1000:

```bash
# Install once
pip install yfinance pandas numpy

# Screen all universes (S&P 500 + NASDAQ 100 + watchlists)
python3 scripts/minervini_screener.py --universe all --json > results.json

# Screen specific universe
python3 scripts/minervini_screener.py --universe sp500

# Screen custom tickers
python3 scripts/minervini_screener.py --tickers NVDA,AAPL,MSFT,PLTR

# Output CSV for pipeline integration
python3 scripts/minervini_screener.py --universe all --csv /data/minervini/scan.csv --save
```

**The script handles everything:** batch yfinance download, all 8 criteria, RS percentile ranking, result sorting, tracker JSON persistence.

**Run this on Raghu's local machine** — yfinance is blocked in Claude's sandbox. For 500+ tickers, expect 30-60 seconds.

**Note that above scripts paths are relative to current skill directory

### Mode 2: Chat Execution (targeted screening — <30 tickers)

When Raghu asks to screen specific tickers or his watchlists in chat:

1. **Web search for each ticker's technical data** (MA values, 52w range)
   - Search: `"TICKER" stock 50-day 200-day moving average 52-week`
   - Best sources: StockAnalysis.com, Barchart, TipRanks, GuruFocus
   - Or `web_fetch` from known good URLs

2. **Extract from search results:**
   - Current price
   - 50-day SMA, 150-day SMA, 200-day SMA
   - 52-week high and 52-week low
   - RS rating (if available) or compute from 6-month performance vs SPY

3. **Apply all 8 criteria** per the table above

4. **Render dashboard** via `visualize:show_widget`

**For chat mode, search in batches of 3-5 tickers** to be efficient. Prioritize the watchlist tickers first, then expand.

---

## TICKER UNIVERSES

### Raghu's Watchlists (always included)
**Strong Buys:** DDOG, NVDA, AXON, NOW, UBER, IRM, VST, AVGO, AMD, AMZN, ANET, MSI, BSX, MSFT, AZO, CRM
**IBD15:** ANAB, MU, IAG, TVTX, RKLB, PACS, CDE, GFI, KGC, AU, PLTR

### Expandable Universes
- **S&P 500:** Fetched from Wikipedia (script handles this)
- **NASDAQ 100:** Fetched from Wikipedia (script handles this)
- **Custom:** Any comma-separated list

---

## RELATIVE STRENGTH CALCULATION

RS Rating = percentile rank of stock's 6-month return vs all screened stocks.

```
stock_6m_return = (price_today / price_126_days_ago - 1) × 100
RS = (count of stocks with lower 6m return / total stocks) × 100
```

- RS ≥ 70 = outperforming 70% of the universe → PASS
- RS 50-69 = average → NEAR MISS
- RS < 50 = underperforming → FAIL

**In chat mode:** If exact RS isn't available, use IBD RS Rating from search results, or estimate from 6-month price performance vs SPY.

---

## WORKFLOW

### When Raghu says "Run Minervini screen":

1. **Determine universe** — watchlists only? S&P 500? All?
2. **Determine mode** — local (recommend for 100+) or chat (for <30)
3. **Execute screen** — script or web search per mode
4. **Rank results** — sort by: passes_template DESC, criteria_passed DESC, RS DESC
5. **Render dashboard** — interactive widget with:
   - Summary cards: Total screened, Full passes, Near misses
   - Sortable results table with pass/fail per criterion
   - Drill-down per ticker (sendPrompt buttons)
   - Color coding: green = pass, red = fail, amber = near miss
6. **Save to tracker** — `{APP_HOME}/data/minervini/tracker.json`
7. **Compare to prior scan** — highlight new passers and dropped passers

### When Raghu asks "Does TICKER pass Minervini?":

1. Web search for ticker's technical data
2. Apply all 8 criteria
3. Show pass/fail table with values
4. Verdict: PASS / NEAR MISS (which criteria failed?) / FAIL

---

## DASHBOARD STRUCTURE (visualize:show_widget)

```
┌─────────────────────────────────────────────────────────────────┐
│  Minervini Trend Template Screen — [Universe] — [Date]          │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┬──────────┬──────────┬──────────┐                  │
│  │ Screened │ Passing  │ Near Miss│ Failed   │  ← Summary cards  │
│  │   527    │    23    │    41    │   463    │                  │
│  └──────────┴──────────┴──────────┴──────────┘                  │
├─────────────────────────────────────────────────────────────────┤
│  [Full Passes] [Near Misses (6-7/8)] [All Results]  ← Tabs      │
├─────────────────────────────────────────────────────────────────┤
│  Ticker │ Price │ 50MA │ 150MA │ 200MA │ RS │ C1-C8 │ Grade    │
│  NVDA   │ 195   │ 186  │  175  │  174  │ 85 │ ✓✓✓✓✓✓✓✓ │ 8/8 ★ │
│  AXON   │ 650   │ 620  │  580  │  540  │ 92 │ ✓✓✓✓✓✓✓✓ │ 8/8 ★ │
│  PLTR   │ 110   │ 95   │  72   │  58   │ 88 │ ✓✓✓✓✓✓✓✓ │ 8/8 ★ │
│  MU     │ 425   │ 350  │  260  │  220  │ 78 │ ✓✓✓✓✓✓✓✗ │ 7/8   │
├─────────────────────────────────────────────────────────────────┤
│  [Analyze NVDA setup ↗]  [Run VCP scan ↗]  [Compare to last ↗]  │
└─────────────────────────────────────────────────────────────────┘
```

### Color system:
| Signal | Background | Text |
|--------|------------|------|
| PASS (8/8) | `var(--color-background-success)` | `#1D9E75` |
| Near miss (6-7) | `var(--color-background-warning)` | `#BA7517` |
| Fail (<6) | none | `var(--color-text-secondary)` |
| Individual criterion pass | — | `#1D9E75` |
| Individual criterion fail | — | `#E24B4A` |

---

## STATE TRACKING

After each scan, save to: `{APP_HOME}/data/minervini/tracker.json`

```json
{
  "scans": [
    {
      "date": "2026-03-14",
      "universe": "all",
      "total_screened": 527,
      "total_passing": 23,
      "near_miss": 41,
      "passers": ["NVDA", "AXON", "PLTR", ...],
      "near_missers": ["MU", "DDOG", ...]
    }
  ]
}
```

**Longitudinal signals:**
- Passers count increasing over time → market breadth improving (bullish)
- Passers count decreasing → fewer stocks in uptrends (bearish warning)
- New ticker appearing in passers → potential entry candidate
- Ticker dropping from passers → trend deteriorating, review position

---

## QUALITY CHECKLIST

- [ ] All 8 criteria checked for every ticker (no shortcuts)
- [ ] 30% above low used (not 25% — Raghu's stricter threshold)
- [ ] RS computed as percentile rank (not raw return)
- [ ] 200-day MA uptrend checked over 22+ trading days (not just current slope)
- [ ] Results sorted by pass count then RS
- [ ] Dashboard rendered via `visualize:show_widget`
- [ ] sendPrompt() buttons for drill-down analysis
- [ ] Tracker updated for longitudinal monitoring
- [ ] Near misses highlighted (which criteria failed?)

---

## REFERENCE FILES

For the Minervini methodology background and Stage Analysis context:
→ Read `references/minervini_reference.md`

For the screener script:
→ Run `python3 scripts/minervini_screener.py --help`


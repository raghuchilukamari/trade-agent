---
name: equity-research
description: >
  Equity research analysis combining fundamental, macro, and catalyst perspectives for
  medium-to-long-term investment decisions. Use when Raghu asks to analyze a company,
  build a bull/bear case, evaluate whether to buy/hold/sell a stock, assess fundamentals,
  check valuation, review a position, or any variation of "research TICKER", "analyze TICKER",
  "what do you think of TICKER", "should I buy TICKER", "investment thesis for TICKER",
  "deep dive on TICKER", "fundamental analysis", "equity report", "bull case / bear case",
  "valuation check", or "is TICKER worth buying". Also triggers for multi-company comparisons
  ("compare AAPL vs MSFT") or sector-level assessments ("which cloud stocks look best").
  Goal: capital preservation, steady growth, non-risky bets.
---

# Equity Research Report

Deliver a structured, institutional-grade equity research report for one or more companies.

**Investment philosophy:** Medium-to-long-term with steady growth in mind. Prioritize capital preservation, safety, and non-risky bets. Prefer companies with strong fundamentals, proven cash flow, and defensible competitive positions.

**SUPPORTS MULTI-TICKER ANALYSIS** — When multiple tickers are provided, execute web searches in parallel batches and render a comparative summary at the end.

---

## REPORT STRUCTURE

For each company, deliver all 5 sections below. Do not skip sections.

### Section 1: Fundamental Analysis

Research and present:

- **Revenue & Growth:** trailing 12-month revenue, YoY growth rate, 3-year CAGR, sequential trends
- **Margins:** gross margin, operating margin, net margin — current + directional trend (expanding/contracting)
- **Free Cash Flow:** TTM FCF, FCF margin, FCF yield, trend vs prior years
- **Valuation vs Peers:** P/E (fwd & trailing), EV/EBITDA, P/S, PEG ratio — compare to 3-5 sector peers
- **Balance Sheet:** debt-to-equity, net cash/debt position, current ratio, interest coverage
- **Insider Activity:** recent Form 4 filings (buys/sells), insider ownership %, any cluster buying/selling
- **Shareholder Returns:** dividend yield (if any), buyback program, total shareholder return
- **Analyst Consensus:** consensus rating (Strong Buy/Buy/Hold/Sell), mean/low/high price targets, total analyst count, recent upgrades/downgrades (last 90 days). Source: Benzinga via `mcp__massive__list_benzinga_consensus_ratings` and `mcp__massive__list_benzinga_ratings`

**Data sources (search in this order):**
0. Postrges will have preloaded fundamental data for a lot of tickers - dashboard.equity_fundamentals & dashboard.equity_fundamental_flags have a lot of data. Check that data first before doing any websearch for fundamentals
1. `"TICKER financials revenue margin"` → Macrotrends, StockAnalysis.com, WisesheetHQ
2. `"TICKER valuation P/E EV/EBITDA vs peers"` → GuruFocus, FinViz, SimplyWall.St
3. `"TICKER insider trading Form 4 2026"` → SEC EDGAR
4. `"TICKER free cash flow balance sheet"` → Macrotrends, StockAnalysis.com
5. **Benzinga Consensus (MCP):** Use `mcp__massive__list_benzinga_consensus_ratings` with `ticker=TICKER` to get analyst consensus rating, price targets, and analyst count. Also use `mcp__massive__list_benzinga_ratings` with `ticker=TICKER, limit=5` for recent individual analyst actions (upgrades/downgrades).

### Section 2: Thesis Validation

- **3 Bull Arguments:** concrete, evidence-backed reasons the stock could outperform
- **2 Bear Arguments / Key Risks:** what could go wrong — be specific (regulatory, competitive, macro, execution)
- **Final Verdict:** Bullish / Bearish / Neutral — with a 2-3 sentence justification grounded in the data above

### Section 3: Sector & Macro View

- **Sector Overview:** current state of the sector (growth, headwinds, tailwinds)
- **Macro Trends:** relevant macroeconomic factors (rates, inflation, GDP, consumer spending, trade policy) - `kb/macro/weekly/*` will have weekly regime changes. 
- **Competitive Positioning:** where the company sits vs peers — market share, moat, differentiation

**Data sources:**
1. `"TICKER sector outlook 2026"` → Morningstar, Seeking Alpha, Reuters
2. `"SECTOR industry trends"` → IBISWorld, McKinsey, Deloitte sector reports

### Section 4: Catalyst Watch

- **Near-Term (0-3 months):** earnings dates, product launches, FDA decisions, contract announcements
- **Medium-Term (3-12 months):** regulatory changes, expansion plans, M&A potential, guidance revisions
- **Long-Term (1-3 years):** TAM expansion, secular trends, market share trajectory

**Data sources:**
1. `"TICKER upcoming earnings catalyst 2026"` → Earnings Whispers, Benzinga, MarketBeat
2. `"TICKER news catalyst"` → Google News, Reuters, Bloomberg

### Section 5: Investment Summary

Deliver exactly:

1. **5-Bullet Thesis:** concise investment thesis (one sentence per bullet)
2. **Recommendation:** Buy / Hold / Sell
3. **Confidence Level:** High / Medium / Low
4. **Expected Timeframe:** e.g., 6-12 months, 1-2 years
5. **Risk Rating:** Low / Medium / High (probability of >20% drawdown)

---

## EXECUTION WORKFLOW

### Single ticker: "Analyze NVDA"

1. **MCP data fetch** (before web searches):
   - `mcp__massive__list_benzinga_consensus_ratings(ticker=TICKER)` — consensus + price targets
   - `mcp__massive__list_benzinga_ratings(ticker=TICKER, limit=5)` — recent analyst actions
   - `mcp__massive__list_stock_financials(ticker=TICKER, limit=4)` — quarterly financials if available
2. **Web search in parallel** (3-4 searches simultaneously):
   - Financials + margins + FCF
   - Valuation + peer comparison
   - Insider activity + institutional ownership
   - Recent news + catalysts
3. **Synthesize data** into the 5-section report
3. **Cross-reference** with other skills if relevant:
   - Run SEC filing analysis if insider activity is notable → `sec-filing-analysis` skill
   - Run Minervini screen if user also wants technical confirmation → `minervini-screener` skill
4. **Deliver report** in the structured format above

### Multiple tickers: "Compare AAPL vs MSFT vs GOOGL"

1. **Search in parallel batches** (3-5 tickers per batch)
2. **Deliver individual reports** for each ticker
3. **Add comparative summary table:**

```
| Metric        | AAPL    | MSFT    | GOOGL   |
|---------------|---------|---------|---------|
| Fwd P/E       | 28x     | 32x     | 22x     |
| Revenue Growth| 8%      | 14%     | 12%     |
| FCF Margin    | 26%     | 33%     | 22%     |
| Recommendation| Hold    | Buy     | Buy     |
| Confidence    | Medium  | High    | High    |
```

4. **Rank tickers** by investment attractiveness given Raghu's conservative philosophy

### Multi-ticker sweep: "Review these positions"

When Raghu provides a list of tickers, deliver abbreviated reports (summary + recommendation only) with a ranking table.

---

## QUALITY CHECKLIST

- [ ] All 5 sections completed for every ticker (no sections skipped)
- [ ] Valuation compared to at least 3 sector peers
- [ ] Both bull AND bear cases presented (avoid one-sided analysis)
- [ ] Data sourced from multiple sources (not just one website)
- [ ] Insider activity checked (Form 4s within last 6 months)
- [ ] Recommendation aligned with Raghu's conservative philosophy
- [ ] Confidence level honestly reflects data quality and uncertainty
- [ ] Catalysts include specific dates where possible (not vague "soon")
- [ ] Risk rating accounts for macro environment, not just company-specific factors

---

## RECOMMENDATION FRAMEWORK

Given Raghu's capital-preservation priority:

| Signal | Leans Toward |
|--------|-------------|
| Strong FCF + low debt + expanding margins | Buy |
| High valuation vs peers + slowing growth | Hold or Sell |
| Insider cluster buying + undervaluation | Buy (high confidence) |
| Insider heavy selling + rich valuation | Sell or avoid |
| Secular tailwind + early-stage growth | Buy (if valuation reasonable) |
| Cyclical peak + margin compression | Hold or reduce |
| High short interest + negative catalysts | Avoid |
| Dividend grower + fortress balance sheet | Buy (conservative pick) |
| Strong Buy consensus + price target >15% upside | Buy (analyst-confirmed) |
| Consensus downgrade trend + target cuts | Hold or reduce |
| Wide analyst disagreement (high/low targets diverge >50%) | Extra due diligence needed |

**Bias toward:** quality companies at fair-to-cheap valuations with visible catalysts.
**Bias against:** speculative growth, turnaround stories, heavily leveraged companies, momentum-only plays.

---

## DATABASE PERSISTENCE

After completing every equity research analysis, persist the output to PostgreSQL.

### Before running analysis — check for existing entry:
```sql
SELECT symbol, run_date FROM dashboard.equity_research
WHERE symbol = '{TICKER}' ORDER BY run_date DESC LIMIT 1;
```
- If an entry exists within the last 7 days AND no material news/earnings/catalyst has occurred since that date, **skip the analysis** and inform the user the existing report is still current.
- If new material events exist (earnings release, guidance change, analyst upgrade/downgrade, major news) since the last run_date, run a fresh analysis.

### After analysis — save to DB:
Generate a self-contained HTML report (same style as SEC filing analysis — inline styles, no external dependencies) and upsert:

```sql
INSERT INTO dashboard.equity_research (symbol, run_date, html)
VALUES ('{TICKER}', '{TODAY}', '{HTML_BLOB}')
ON CONFLICT (symbol, run_date) DO UPDATE SET html = EXCLUDED.html;
```

Use the MCP postgres tool to execute the insert.

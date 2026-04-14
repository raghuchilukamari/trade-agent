# Knowledge Base Compiler

Maintain a structured markdown knowledge base at `kb/` that compounds trading analysis over time. Claude Code is the compiler -- read source data from PostgreSQL and filesystem, synthesize into modular markdown files.

**Triggers:** "update kb", "compile knowledge base", "refresh wiki", "kb status", or automatically as Step 7 of the daily workflow.

## Principles

1. **Append, never replace** -- `log.md` files are append-only. Other files are updated in-place but preserve historical context.
2. **Synthesize, don't copy** -- Extract insights from HTML blobs and raw data. Never paste raw HTML or CSV data into the KB.
3. **Always update indexes** -- Every file change must propagate to the relevant INDEX.md file(s).
4. **Frontmatter is required** -- Every file has YAML frontmatter with at minimum: ticker/theme and last_updated date.
5. **Link everything** -- Use relative markdown links between files. Tickers link to themes. Themes link back to tickers.

## Directory Structure

```
kb/
├── INDEX.md              # Master index -- session bootstrap, <100 lines
├── DECISION_LOG.md       # Chronological recommendations + outcomes
├── tickers/
│   ├── INDEX.md          # All tracked tickers, one-line status each
│   └── {TICKER}/
│       ├── profile.md    # Thesis, bull/bear, competitive position
│       ├── fundamentals.md # Revenue, margins, FCF, valuation
│       ├── technicals.md # Minervini status, MA levels, RS, stage
│       ├── flow.md       # Options flow patterns, bias, notable prints
│       ├── catalysts.md  # Upcoming events with dates
│       └── log.md        # Append-only chronological updates
├── themes/
│   ├── INDEX.md          # Active themes with linked tickers
│   └── {theme-name}.md
├── macro/
│   ├── regime.md         # Current market regime summary
│   └── weekly/
│       └── {YYYY-WNN}.md # Weekly macro digest
└── templates/            # Reference templates for new entries
```

## Execution Modes

### Mode 1: Daily Compilation (Step 7)

1. Read `kb/INDEX.md` for current state
2. Check what's new today:
   ```sql
   SELECT symbol, run_date FROM dashboard.equity_research WHERE run_date = CURRENT_DATE;
   SELECT symbol, run_date FROM dashboard.sec_filing_analysis WHERE run_date = CURRENT_DATE;
   SELECT scan_date FROM dashboard.minervini_tracker WHERE scan_date = CURRENT_DATE;
   ```
   Also check: flow_entries for today, market events HTML timestamps.
3. For each ticker with new data:
   - Read the source (PG HTML blob, flow data, Minervini results)
   - Update the relevant .md file(s) in `kb/tickers/{TICKER}/`
   - Append a dated entry to `log.md`
   - If ticker directory doesn't exist, create it from templates
4. Update cross-references:
   - If themes are affected, update theme files
   - Update `kb/macro/` if market events changed
5. Rebuild indexes: `kb/tickers/INDEX.md`, `kb/themes/INDEX.md`, `kb/INDEX.md`
6. Update `DECISION_LOG.md` if any ratings changed
7. If no new data found, report "No new data to compile" and skip

### Mode 2: Seed (first run)

Query all existing data from PG and filesystem. Create ticker directories for every ticker with equity_research or sec_filing_analysis entries. Build complete index and theme structure from scratch.

### Mode 3: Status Check

Read and display `kb/INDEX.md`. Report:
- Tickers tracked, last update per ticker
- Stale entries (>7 days without update)
- Decision log accuracy (outcomes of past recommendations)

## File Creation Rules

When creating a new ticker directory:
1. Create `kb/tickers/{TICKER}/`
2. Generate each file with proper frontmatter (see templates/ for structure)
3. `profile.md` -- from equity research: thesis, bull/bear, competitive position
4. `fundamentals.md` -- from equity research: metrics, valuation, margins
5. `technicals.md` -- from Minervini data: 8 criteria, MA levels, RS, stage
6. `flow.md` -- from flow_entries: recent signals, pattern, bias
7. `catalysts.md` -- from equity research: dated events, risk/reward
8. `log.md` -- start with creation entry
9. Add to `kb/tickers/INDEX.md` and `kb/INDEX.md`

## What NOT to Store

- Raw CSV data (stays in `/media/SHARED/trade-data/formatted/`)
- HTML blobs (stay in PG tables)
- OHLC price data (stays in `ta_daily` / `ohlc_daily`)
- Full SEC filing text (stays in PG or EDGAR)
- Market events HTML (stays in `/media/SHARED/trade-data/market-events/`)

The KB stores **synthesized insights only**. If someone needs raw data, they go to the source. The KB tells you what the data means.

## Quality Checklist

- [ ] Every updated file has frontmatter with current `last_updated` date
- [ ] `log.md` entries include date header and source attribution
- [ ] INDEX.md files reflect current state of all tracked tickers
- [ ] No raw data pasted -- only synthesized insights
- [ ] Cross-references use relative markdown links
- [ ] `DECISION_LOG.md` updated when ratings change

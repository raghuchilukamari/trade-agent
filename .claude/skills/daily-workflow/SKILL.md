# Daily Workflow Runner

Execute the full daily trading analysis pipeline. Each step checks existing state before running — idempotent by design.

**ALWAYS read `kb/INDEX.md` first** for current market context before starting.

---

## Pre-Flight State Check

Run these queries to determine what needs to run today:

```bash
# 1. Check flow data in DB (should have today's date)
# If flow_entries is empty or max date < today → run Discord pipeline

# 2. Check ta_daily freshness
# If max(date by count) < today → run update_technicals

# 3. Check Minervini last scan
# If scan_date < today → run screener after ta_daily refresh

# 4. Check market events file
# ls /media/SHARED/trade-data/market-events/ | grep current week

# 5. Check research freshness
# SELECT symbol, run_date FROM dashboard.equity_research ORDER BY run_date DESC LIMIT 10;
```

**Quick state summary query:**
```sql
SELECT
  (SELECT MAX(date) FROM flow_entries) as flow_date,
  (SELECT date FROM ta_daily GROUP BY date HAVING COUNT(*) >= (SELECT MAX(cnt)*0.9 FROM (SELECT COUNT(*) cnt FROM ta_daily GROUP BY date) s) ORDER BY date DESC LIMIT 1) as ta_date,
  (SELECT MAX(scan_date) FROM dashboard.minervini_tracker) as minervini_date,
  (SELECT MAX(run_date) FROM dashboard.equity_research) as research_date;
```

---

## Step 1: Discord Data Pipeline

Check flow-counts-tracker for today's date:
```bash
tail -3 .claude/agent-memory/discord-data-pipeline/flow-counts-tracker.csv
```

If today's date is missing → launch discord-data-pipeline agent (runs all steps 1-5 including walter_enrich and market events update).

**Agent does:** Export Discord → Format CSVs → walter_enrich → Generate daily report → Update market events

---

## Step 2: Market Events (included in Step 1)

- File location: `/media/SHARED/trade-data/market-events/`
- Check if this week's file exists and has today's outcomes updated
- The discord-data-pipeline agent handles this automatically (Step 3e)
- Run independently only if discord pipeline was skipped

---

## Step 3: pg_refresh + Post-Processing

```bash
# Fix carriage returns first (always safe to run)
sed -i 's/\r//g' /media/SHARED/trade-data/formatted/*.csv

# Load all 6 CSVs into PostgreSQL + run post-refresh scripts
bash scripts/pg_refresh.sh
```

**Expected output:** 
- Loads: golden_sweeps, sweeps, trady_flow, sexy_flow, walter, walter_openai
- Post-processing: persist_sector_flow.py, generate_alerts.py

**Known bugs (fixed Apr 7, 2026):**
- `flow_parser.py:21` — fixed: `from app.services.premium_calculator import ...`
- `generate_alerts.py:45` — fixed: `CAST(:detail AS jsonb)` instead of `:detail::jsonb`

---

## Step 4: Update Technicals

```bash
conda run -n tradingbot python3 scripts/update_technicals.py 
```

**Freshness check:** Uses `MAX(date) FROM ohlc_daily`. If only a few rows exist for today (partial yfinance update), the screener will use the most-covered date automatically.

**If partial rows exist for today (ta_daily shows <100 rows for today's date):**

`update_technicals.py` now auto-detects partial data (< 10% of universe) and **refuses to write** — the existing full day is preserved automatically. If a partial day was already written by mistake, drop it with:

```bash
# Drop partial date and retry
conda run -n tradingbot python3 scripts/update_technicals.py --drop-partial $(date +%Y-%m-%d)
conda run -n tradingbot python3 scripts/update_technicals.py --mode daily
```

**Note when Minervini data is missing (partial run):** Fall back to latest full scan:
```sql
SELECT * FROM dashboard.minervini_tracker
WHERE scan_date = (
  SELECT date FROM ta_daily GROUP BY date
  HAVING COUNT(*) >= (SELECT MAX(cnt)*0.9 FROM (SELECT COUNT(*) cnt FROM ta_daily GROUP BY date) s)
  ORDER BY date DESC LIMIT 1
) LIMIT 50;
```

**Note:** yfinance sometimes doesn't have same-day close data until evening. If NaN for today, use prior day's data — the screener handles this automatically with the ≥90% coverage query.

---

## Step 5: Minervini Screener

```bash
cd .claude/skills/minervini-screener
conda run -n tradingbot python3 scripts/minervini_screener.py --json --save
```

**If "already ran" message appears but prior run had bad data:**
```bash
source /path/to/.env
PGPASSWORD="${PG_PASS}" psql -h "${POSTGRES_HOST}" -U "${PG_USER}" -d "${POSTGRES_DB}" \
  -c "DELETE FROM dashboard.minervini_tracker WHERE scan_date::date = 'TODAY';"
# Then rerun
```

**After screen runs — check rotation analysis:**
```sql
SELECT new_additions, new_removals FROM dashboard.minervini_tracker
WHERE scan_date = (SELECT MAX(scan_date) FROM dashboard.minervini_tracker);
```

Then run Rotation_prompt: `.claude/skills/minervini-screener/Rotation_prompt`

---

## Step 6: Fundamental & Sec Filing Analysis

**Priority order for research:**
1. 4-channel bullish/bearish flow tickers (max conviction)
2. Heavy flow (>$5M) with no research in last 7 days
3. New Minervini passers from today's scan
4. Tracked tickers with new material events (earnings, upgrades, news)

**Freshness check before running:**
```sql
SELECT symbol, run_date FROM dashboard.equity_research
WHERE symbol IN ('TICKER1','TICKER2') ORDER BY run_date DESC;
-- Skip if < 7 days old with no new material info
```

- For Fundamental data, query postgres to see if data is available for a specific ticker - `dashboard.equity_fundamentals & dashboard.equity_fundamental_flags`
- If data is not present for any ticker, use `.claude/skills/equity-research/scripts/fundamentals_base.py` for fundamental analysis 

- After fundamental analysis you can run sec-filing-analysis using `python3 .claude/skills/sec-filing-analysis/scripts/run_sec_analysis.py --ticker {ticker} --analysis full` for any ticker 
- check the stdout to get the path of full analysis output

### Flow Aggregator — Full Display

Run this to read and display all flow aggregator output (top tickers, sectors, put sellers):

```bash
conda run -n tradingbot python3 -m scripts.flow_aggregator \
  --start $(date +%Y-%m-%d) --end $(date +%Y-%m-%d) --output /tmp/flow_data.json 2>/dev/null

python3 -c "
import json
with open('/tmp/flow_data.json') as f:
    d = json.load(f)

print('META:')
print(json.dumps(d['meta'], indent=2))
print()
print('TOP TICKERS (by total premium):')
tickers = sorted(d['tickers'].items(), key=lambda x: x[1]['total_premium'], reverse=True)[:25]
for sym, t in tickers:
    print(f'  {sym}: total=\${t[\"total_premium\"]/1e6:.2f}M dir={t[\"direction\"]} ch={t[\"channel_count\"]} bull={t[\"bull_pct\"]}%')
print()
print('PUT SELLERS (top 10):')
for ps in d.get('put_sellers', [])[:10]:
    print(f'  {ps}')
"
```

**Shortcut — just top tickers (no file write):**
```bash
conda run -n tradingbot python3 -m scripts.flow_aggregator \
  --start $(date +%Y-%m-%d) --end $(date +%Y-%m-%d) 2>/dev/null \
  | python3 -c "
import sys, json
raw = sys.stdin.read(); d = json.loads(raw[raw.find('{'):])
for t,v in sorted(d['tickers'].items(), key=lambda x: x[1]['total_premium'], reverse=True)[:15]:
    print(f\"{t}: \${v['total_premium']/1e6:.2f}M {v['direction']} ch={v['channel_count']} bull={v['bull_pct']}%\")
"
```

### Walter News — Sector & Ticker Breakdown

Full sector counts + top tickers in today's news:

```bash
conda run -n tradingbot python3 -c "
from pathlib import Path
from app.services.flow_parser_v0 import load_walter_news
import datetime

today = datetime.date.today().isoformat()
walter = load_walter_news(Path('/media/SHARED/trade-data/formatted'), start_date=today, end_date=today)

sector_counts, all_tickers = {}, {}
for e in walter:
    if not e.get('summary'):
        continue
    for s in e.get('sectors', []):
        s_norm = s.strip().title()
        sector_counts[s_norm] = sector_counts.get(s_norm, 0) + 1
    for t in e.get('tickers', []):
        all_tickers[t] = all_tickers.get(t, 0) + 1

print('Sectors mentioned:')
for s, c in sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
    print(f'  {s}: {c}')
print()
print('Top tickers in news:')
for t, c in sorted(all_tickers.items(), key=lambda x: x[1], reverse=True)[:20]:
    print(f'  {t}: {c}')
" 2>&1 | grep -v "^\[" | grep -v "^$(date +%Y)-"
```

### Walter News — Sentiment Buckets

Display news by sentiment bucket (use for daily macro narrative):

```bash
conda run -n tradingbot python3 -c "
from pathlib import Path
from app.services.flow_parser_v0 import load_walter_news
import datetime

today = datetime.date.today().isoformat()
walter = load_walter_news(Path('/media/SHARED/trade-data/formatted'), start_date=today, end_date=today)

buckets = {'BULLISH': [], 'SLIGHTLY_BULLISH': [], 'BEARISH': []}
for e in walter:
    score = e.get('sentiment_score', 2.5)
    if score is None: continue
    try: score = float(score)
    except: continue
    summary = e.get('summary', '').strip()
    ts = e.get('timestamp', '')
    if not summary: continue
    if score >= 3.5:   buckets['BULLISH'].append((ts, score, summary))
    elif score == 3.0: buckets['SLIGHTLY_BULLISH'].append((ts, score, summary))
    elif score <= 2.0: buckets['BEARISH'].append((ts, score, summary))

for label, items in buckets.items():
    print(f'=== {label} ({len(items)} items) ===')
    for ts, sc, sm in sorted(items)[-10:]:
        print(f'  [{ts}] ({sc}) {sm[:120]}')
    print()
" 2>&1 | grep -v "^\[" | grep -v "^$(date +%Y)-"
```

**Sentiment buckets:** BULLISH ≥3.5 | SLIGHTLY BULLISH =3.0 | NEUTRAL =2.5 (not listed) | BEARISH ≤2.0

**Save research after analysis:**
```bash
conda run -n tradingbot python3 scripts/save_research.py equity_research TICKER YYYY-MM-DD /tmp/ticker_report.html
conda run -n tradingbot python3 scripts/save_research.py sec_filing_analysis TICKER YYYY-MM-DD /tmp/ticker_sec.html
```

---

## Step 7: Knowledge Base Update

Run `/knowledge-base` skill after all data steps complete.

Key files to update:
- `kb/INDEX.md` — Quick status table, macro regime, recent decisions
- `kb/tickers/INDEX.md` — Per-ticker status
- `kb/tickers/{TICKER}/log.md` — Append today's events (never overwrite)
- `kb/macro/regime.md` — Market regime update
- `kb/macro/weekly/YYYY-WXX.md` — Weekly digest

---

## Common Bugs & Fixes

| Bug | Fix |
|-----|-----|
| `persist_sector_flow.py` fails with `No module named premium_calculator` | Fixed in `app/services/flow_parser.py:21` — use `from app.services.premium_calculator import` |
| `generate_alerts.py` SQL syntax error with `:detail::jsonb` | Fixed — use `CAST(:detail AS jsonb)` |
| Minervini screener uses wrong date (3 tickers instead of 1400+) | Fixed — screener now uses date with ≥90% ticker coverage, not MAX(date) |
| `update_technicals.py` writes only 3 rows for today | Auto-blocked now: partial guard rejects writes < 10% of universe. Use `--drop-partial YYYY-MM-DD` to clean any that slipped through. |
| `flow_aggregator.py` fails with `No module named app` | Run as `python3 -m scripts.flow_aggregator` from project root |
| `save_research.py` not found | Script is at `scripts/save_research.py` — was created Apr 7, 2026 |

---

## Output Checklist

After completing all steps, verify:
- [ ] `flow-counts-tracker.csv` has today's date
- [ ] `pg_refresh.sh` loaded all 6 CSVs without errors
- [ ] `ta_daily` has >1000 tickers for latest covered date
- [ ] `dashboard.minervini_tracker` has today's scan
- [ ] Equity research saved for all 4-channel tickers
- [ ] `kb/INDEX.md` updated with today's signals and decisions

---

## Data Locations Reference

| Data | Location |
|------|----------|
| Flow CSVs | `/media/SHARED/trade-data/formatted/` |
| Market events HTML | `/media/SHARED/trade-data/market-events/` |
| Daily summary HTML | `/media/SHARED/trade-data/summaries/` |
| Flow counts tracker | `.claude/agent-memory/discord-data-pipeline/flow-counts-tracker.csv` |
| Knowledge base | `kb/` |
| HRP outputs | `app/services/bot_outputs/` |

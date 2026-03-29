---
name: sec-filing-analysis
description: >
  SEC filing analysis for equity research. Use for: Form 4 insider trading, 10-K/10-Q risk factors,
  13F institutional ownership, red flag detection (NT filings, auditor changes, restatements),
  YoY 10-K comparison, DSO analysis, and GREEN CHANNEL P/S VALUATION (historical P/S bands +
  insider conviction). Triggers: "SEC filings", "insider selling", "Form 4", "10-K analysis",
  "risk factors", "13F", "red flags", "auditor change", "green channel", "P/S ratio", "undervalued",
  "fair value", "revenue valuation", or any filing type (8-K, S-1, 13D, DEF 14A).
---

# SEC Filing Analysis — Comprehensive Research Skill

This skill provides systematic, forensic-grade analysis of SEC filings for equity research.
It identifies red flags, tracks insider sentiment, surfaces buried risks, and produces
actionable intelligence from regulatory disclosures.

**SUPPORTS PARALLEL MULTI-TICKER ANALYSIS** — When multiple tickers are provided, execute
web searches in parallel batches and render a comparative dashboard.

## Directory Layout

```
sec-filing-analysis/
├── SKILL.md                     ← You are here
├── scripts/                     ← Executable Python modules
│   ├── __init__.py
│   ├── fetch_filings.py         ← SEC EDGAR search patterns, URL builders
│   ├── insider_analysis.py      ← Form 4 parsing, transaction classification
│   ├── risk_factor_diff.py      ← 10-K Item 1A YoY comparison
│   ├── dso_analysis.py          ← Accounts receivable & DSO calculations
│   ├── institutional_flow.py    ← 13F parsing, accumulation/reduction detection
│   ├── red_flag_scan.py         ← NT, 4.01, 4.02, going concern detection
│   └── generate_report.py       ← Orchestrator for batch processing
└── references/                  ← Context docs (read as needed)
    ├── quick-reference.md       ← Filing cheat sheet, transaction codes, deadlines
    ├── filing_taxonomy.md       ← Complete filing type reference by tier
    └── red_flag_guide.md        ← Severity levels, action triggers
```

---

## BEFORE ANYTHING ELSE

1. **Identify the ticker(s)** — single stock deep-dive or multi-ticker comparison?
2. **If multiple tickers provided** — use PARALLEL EXECUTION workflow (see below)
3. **Identify the analysis type** — quick scan, earnings prep, full forensic, or specific filing?
4. **Check for time sensitivity** — earnings date, OPEX proximity, 13F deadline, proxy meeting?
5. **Web search is REQUIRED** — this skill depends on fetching current SEC filings from EDGAR

---

## PARALLEL MULTI-TICKER EXECUTION

When Raghu provides multiple tickers (e.g., "run SEC analysis for JNJ, PFE, MRK, ABBV"):

### Step 1: Batch Web Searches in Parallel

Execute ALL searches for ALL tickers simultaneously in a single tool call batch:

```
For each ticker, fire these searches in parallel:
- "[TICKER] SEC EDGAR filings 2025 2026"
- "[TICKER] Form 4 insider trading 2026"
- "[TICKER] 10-K risk factors litigation"
- "[TICKER] 13F institutional ownership"
- "[TICKER] NT filing auditor change restatement red flag"
```

**Example for 4 tickers = 20 parallel searches** (5 searches × 4 tickers)

### Step 2: Aggregate Results by Ticker

After parallel searches complete, organize findings into per-ticker structures:

```json
{
  "JNJ": {
    "red_flags": [],
    "insider_sentiment": "SELLING",
    "insider_net_flow": -119600000,
    "institutional_flow": "+85%",
    "risk_score": 6.2,
    "key_risks": ["Talc litigation 67K cases", "STELARA biosimilar"],
    "verdict": "CAUTION"
  },
  "PFE": { ... },
  "MRK": { ... },
  "ABBV": { ... }
}
```

### Step 3: Render Comparative Dashboard

Use `visualize:show_widget` to render an interactive comparison dashboard with:

1. **Summary grid** — All tickers with risk scores, insider sentiment, red flag counts
2. **Comparative metrics** — Side-by-side insider flow, institutional accumulation
3. **Red flag matrix** — Which tickers have which warning types
4. **Drill-down tabs** — Click any ticker for detailed view
5. **Action buttons** — `sendPrompt()` for deeper analysis on specific ticker

### Dashboard Structure (Multi-Ticker)

```
┌─────────────────────────────────────────────────────────────────┐
│  SEC Filing Comparison — JNJ, PFE, MRK, ABBV                    │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────┬─────────┬─────────┬─────────┐                      │
│  │   JNJ   │   PFE   │   MRK   │  ABBV   │  ← Ticker cards      │
│  │  ⚠ 6.2  │  ✓ 3.1  │  ✓ 4.0  │  ⚠ 5.5  │  ← Risk scores      │
│  │ Selling │ Neutral │ Buying  │ Selling │  ← Insider sentiment │
│  └─────────┴─────────┴─────────┴─────────┘                      │
├─────────────────────────────────────────────────────────────────┤
│  Red Flag Matrix                                                │
│  ┌─────────┬─────┬─────┬─────┬─────┐                            │
│  │ Flag    │ JNJ │ PFE │ MRK │ABBV │                            │
│  ├─────────┼─────┼─────┼─────┼─────┤                            │
│  │ NT 10-K │  -  │  -  │  -  │  -  │                            │
│  │ Audit Δ │  -  │  -  │  -  │  -  │                            │
│  │ Litig.  │ 67K │  2K │  -  │  5K │                            │
│  │ Insider │ ↓↓↓ │  -  │ ↑↑  │ ↓↓  │                            │
│  └─────────┴─────┴─────┴─────┴─────┘                            │
├─────────────────────────────────────────────────────────────────┤
│  [Deep dive JNJ ↗]  [Deep dive PFE ↗]  [Compare insiders ↗]     │
└─────────────────────────────────────────────────────────────────┘
```

### Efficiency Guidelines

- **Max 5 tickers per batch** — Beyond 5, split into multiple batches
- **Prioritize red flag searches** — If time-constrained, skip institutional 13F
- **Cache common data** — Industry-wide risks (e.g., drug pricing) apply to all pharma tickers
- **Use comparative framing** — "JNJ insider selling is 3x worse than peer average"

---

## FILING TAXONOMY — KNOW WHAT TO PULL

### Tier 1: Core Filings (Always Check)

| Filing | What It Reveals | Timing |
|--------|-----------------|--------|
| **10-K** | Full-year financials, risk factors (Item 1A), MD&A, legal proceedings | Within 60 days of fiscal year-end |
| **10-Q** | Quarterly update, interim risks, liquidity changes | Within 40 days of quarter-end |
| **8-K** | Material events: earnings, deals, executive changes, litigation | Within 4 business days of event |

### Tier 2: Insider & Ownership (Track Sentiment)

| Filing | Who Files | What It Reveals | Timing |
|--------|-----------|-----------------|--------|
| **Form 4** | Officers, Directors, 10%+ owners | Buys/sells, option exercises | Within 2 business days |
| **Form 3** | New insiders | Initial ownership disclosure | Within 10 days |
| **Form 144** | Insiders | *Intent* to sell restricted stock | Same day or before sale |
| **Schedule 13D** | 5%+ activist owners | Stake + intentions/plans | Within 10 days of crossing 5% |
| **Schedule 13G** | 5%+ passive owners | Stake (passive, no activist intent) | Within 45 days of year-end |
| **13F-HR** | Institutions ($100M+ AUM) | Quarterly portfolio holdings | Within 45 days of quarter-end |

### Tier 3: Proxy & Governance

| Filing | What It Reveals | Timing |
|--------|-----------------|--------|
| **DEF 14A** | Exec compensation, board composition, related-party transactions | Before annual meeting |
| **DEFA 14A** | Supplemental proxy materials | As needed |
| **8-K Item 5.07** | Shareholder vote results | Within 4 days of meeting |

### Tier 4: Offerings & Debt

| Filing | What It Reveals | Timing |
|--------|-----------------|--------|
| **S-1** | IPO registration, full business disclosure | Before IPO |
| **S-3** | Shelf registration (ability to issue quickly) | Ongoing |
| **424B** | Actual offering terms (price, size) | At offering |
| **Form D** | Private placement to accredited investors | Within 15 days |
| **8-K Item 2.03** | New debt obligations, credit facilities | Within 4 days |

### Tier 5: Red Flag Filings (Monitor Always)

| Filing | What It Signals |
|--------|-----------------|
| **NT 10-K / NT 10-Q** | Late filing notice — accounting issues, internal control problems |
| **8-K Item 4.01** | Auditor resignation/dismissal |
| **8-K Item 4.02** | Prior financials can't be relied upon — restatement coming |
| **8-K Item 2.04** | Restructuring charges — layoffs, write-downs |
| **8-K Item 2.06** | Material impairment — asset values collapsing |
| **Going concern** | Auditor doubts company survival (in 10-K audit opinion) |

---

## ANALYSIS WORKFLOWS

### Workflow 1: Pre-Earnings Deep Dive

**Use when:** Preparing for earnings on a position or watchlist ticker

**Steps:**
1. **Web search** latest 10-Q and most recent 8-Ks (last 90 days)
2. **Pull Form 4s** for last 90 days — calculate net insider sentiment
3. **Check 10-K Item 1A** — identify NEW or EXPANDED risk language vs. prior year
4. **Calculate DSO** — is A/R growing faster than revenue?
5. **Review DEF 14A** — executive compensation alignment with performance
6. **Check 13F changes** — who's accumulating vs. exiting?

**Output format:**
```
## [TICKER] — Pre-Earnings Filing Analysis
**Earnings Date:** [Date] | **Days Until:** [X]

### 🚨 Red Flags
[List any NT filings, auditor changes, restatements, insider selling clusters]

### 📊 Insider Activity (90 Days)
| Executive | Transaction | Shares | Value | Date | 10b5-1? |
Net Insider Sentiment: [BUYING / SELLING / NEUTRAL]

### ⚠️ Risk Factor Changes (10-K YoY)
**NEW:** [List new language]
**EXPANDED:** [List expanded language]
**REMOVED:** [List removed language — sometimes bullish]

### 📈 Balance Sheet Signal: DSO
| Period | A/R | Revenue (TTM) | DSO | YoY Change |
Verdict: [STABLE / DETERIORATING / IMPROVING]

### 🏛️ Institutional Flow (Latest 13F)
**Accumulating:** [List funds]
**Reducing:** [List funds]
**New Positions:** [List funds]

### 📋 Upcoming Events
- Earnings: [Date]
- Proxy Meeting: [Date]
- 13F Deadline: [Date]
- OPEX: [Date]
```

---

### Workflow 2: Form 4 Insider Analysis

**Use when:** "Check insider trading", "Are insiders selling?", "Form 4 analysis"

**Steps:**
1. **Web search** Form 4 filings for last 90 days (or specified period)
2. **Classify each transaction** by code:
   - **P** = Open market purchase → BULLISH (discretionary buy)
   - **S** = Open market sale → Context-dependent
   - **M** = Option exercise → Neutral (often paired with S for taxes)
   - **A** = Grant/Award → Neutral (compensation)
   - **F** = Tax withholding → Neutral
   - **G** = Gift → Neutral
3. **Flag 10b5-1 plans** — pre-arranged, NOT indicative of near-term sentiment
4. **Calculate net sentiment** — sum of P transactions vs. S transactions by value
5. **Identify clusters** — multiple insiders selling simultaneously = red flag

**Key distinctions:**
- **Open market purchases (P)** are the ONLY true bullish signal
- **10b5-1 sales** are pre-programmed — check footnotes for plan adoption date
- **Option exercises + same-day sales** are routine, not bearish
- **Cluster selling without 10b5-1** = genuine concern

**Output format:**
```
## [TICKER] — Insider Transaction Analysis (Last 90 Days)

### Summary
| Metric | Value |
|--------|-------|
| Total Bought (Open Market) | $X |
| Total Sold | $X |
| Net Insider Flow | $X |
| Transactions via 10b5-1 | X% |

### Transaction Detail
| Date | Insider | Title | Type | Code | Shares | Price | Value | 10b5-1? |

### 🚨 Red Flags
[X] Cluster selling (3+ insiders within 2 weeks)
[X] New 10b5-1 plan adoption (potential timing signal)
[X] CEO/CFO selling outside of 10b5-1

### Verdict
**Insider Sentiment:** [BULLISH / BEARISH / NEUTRAL]
**Confidence:** [HIGH / MEDIUM / LOW]
**Rationale:** [Explanation]
```

---

### Workflow 3: 10-K Risk Factor Comparison (YoY)

**Use when:** "Compare risk factors", "What's new in the 10-K", "Risk factor diff"

**Steps:**
1. **Fetch current 10-K Item 1A** (Risk Factors section)
2. **Fetch prior year 10-K Item 1A**
3. **Identify:**
   - **NEW risks** — language that didn't exist before
   - **EXPANDED risks** — existing risks with added detail
   - **REMOVED risks** — sometimes bullish (risk resolved)
   - **REORDERED risks** — priority changes are meaningful
4. **Cross-reference with earnings calls** — did management address these?

**Focus areas for 10-K Item 1A:**
- Regulatory/antitrust language
- Liquidity/cash flow warnings
- Customer concentration changes
- Supply chain dependencies
- Cybersecurity incidents
- Going concern language
- Litigation updates

**Output format:**
```
## [TICKER] — 10-K Risk Factor Analysis (FY[Year] vs FY[Year-1])

### 🆕 NEW Risk Language
> "[Exact quote from 10-K]"
**Implication:** [Analysis]

### 📈 EXPANDED Risk Language
**Previous:** "[Old language]"
**Current:** "[New language]"
**Delta:** [What changed and why it matters]

### ✅ REMOVED Risk Language
> "[Language that was removed]"
**Implication:** [Possibly bullish — risk resolved?]

### 🔄 REORDERED Risks
[Note if key risks moved up/down in priority order]

### 📢 Management Commentary Gap
**10-K says:** [Risk disclosed]
**Earnings call said:** [What management emphasized or minimized]
**Gap:** [What they're not talking about]
```

---

### Workflow 4: Balance Sheet — DSO & A/R Analysis

**Use when:** "Check DSO", "Accounts receivable analysis", "Revenue quality"

**Steps:**
1. **Pull quarterly A/R (net)** from last 8 quarters (10-Q/10-K)
2. **Pull quarterly revenue** for same periods
3. **Calculate DSO:** `(A/R ÷ Revenue) × Days in Period`
4. **Calculate A/R growth vs. Revenue growth** — divergence is the signal
5. **Check allowance for doubtful accounts** — is it increasing?

**DSO Interpretation:**
| Trend | Signal |
|-------|--------|
| DSO stable, A/R grows with revenue | Healthy |
| DSO rising, A/R outpacing revenue | ⚠️ Collection issues or channel stuffing |
| DSO falling | Tightening credit or better collections |
| Allowance increasing faster than A/R | ⚠️ Credit quality deteriorating |

**Channel stuffing indicators:**
- A/R growth >> Revenue growth for 3+ quarters
- Quarter-end spikes in shipments
- Increasing returns/allowances
- Customer concentration changes

**Output format:**
```
## [TICKER] — Days Sales Outstanding Analysis

### Trend Data
| Quarter | A/R (Net) | Revenue | DSO (Days) | A/R YoY% | Rev YoY% | Delta |

### Verdict
**DSO Trend:** [STABLE / RISING / FALLING]
**A/R vs Revenue:** [ALIGNED / DIVERGENT]
**Channel Stuffing Risk:** [LOW / MEDIUM / HIGH]

### Allowance for Doubtful Accounts
| Quarter | Allowance | % of A/R | Change |

### Analysis
[Explanation of what DSO trend means for this specific company]
```

---

### Workflow 5: 13F Institutional Ownership Analysis

**Use when:** "Who owns the stock?", "Institutional holders", "13F analysis", "Hedge fund positions"

**Steps:**
1. **Web search** latest 13F-HR filings mentioning the ticker
2. **Identify major changes:**
   - New positions (didn't own before)
   - Increased positions (accumulating)
   - Decreased positions (trimming)
   - Closed positions (exited entirely)
3. **Note the 45-day lag** — 13Fs are backward-looking
4. **Cross-reference with stock price** — did smart money buy the dip or sell the rip?

**Key funds to watch:**
- Berkshire Hathaway (Buffett)
- Bridgewater Associates
- Renaissance Technologies
- Tiger Global
- Coatue Management
- Dragoneer Investment
- Lone Pine Capital

**Output format:**
```
## [TICKER] — Institutional Ownership Analysis

### 13F Snapshot (As of [Quarter End])
**Total Institutional Ownership:** X%
**Number of Institutional Holders:** X

### Notable Changes
| Fund | Action | Shares | Change % | Value |
| Berkshire Hathaway | NEW POSITION | X | +100% | $X |
| Tiger Global | REDUCED | X | -25% | $X |

### Smart Money Signal
**Accumulating:** [List]
**Reducing:** [List]
**Net Sentiment:** [BULLISH / BEARISH / MIXED]

### ⚠️ Caveats
- 13F data is 45 days old
- Does not show short positions
- Smaller funds (<$100M AUM) not required to file
```

---

### Workflow 6: Red Flag Scan

**Use when:** "Check for red flags", "Any problems with this stock?", "Due diligence"

**Steps:**
1. **Search for NT 10-K / NT 10-Q** — late filing notices
2. **Search for 8-K Item 4.01** — auditor changes
3. **Search for 8-K Item 4.02** — financial restatements
4. **Search for 8-K Item 2.04** — restructuring charges
5. **Search for 8-K Item 2.06** — material impairments
6. **Check 10-K audit opinion** — going concern language?
7. **Check Form 4 cluster selling** — 3+ insiders in 2 weeks?
8. **Check 13D amendments** — activist changing strategy?

**Red flag severity:**
| Flag | Severity | Action |
|------|----------|--------|
| NT filing | 🔴 HIGH | Investigate immediately |
| Auditor change | 🔴 HIGH | Why did they leave? |
| Restatement (4.02) | 🔴 HIGH | What's being restated? |
| Going concern | 🔴 CRITICAL | Survival in question |
| Cluster insider selling | 🟡 MEDIUM | Check if 10b5-1 |
| Single restructuring | 🟡 MEDIUM | One-time or recurring? |
| 13D amendment | 🟡 MEDIUM | Activist exit? |

**Output format:**
```
## [TICKER] — Red Flag Scan

### 🚨 Critical Flags (Immediate Action)
[List any NT filings, auditor changes, restatements, going concern]

### ⚠️ Warning Flags (Monitor)
[List restructuring, impairments, insider selling clusters]

### ✅ Clear
[List what was checked and found clean]

### Overall Risk Assessment
**Risk Level:** [LOW / MEDIUM / HIGH / CRITICAL]
**Recommendation:** [PROCEED / PROCEED WITH CAUTION / INVESTIGATE FURTHER / AVOID]
```

---

### Workflow 7: Full Forensic Due Diligence

**Use when:** "Full analysis", "Deep dive", "Forensic due diligence", "Everything on [TICKER]"

**Run ALL of the above workflows in sequence:**
1. Pre-Earnings Deep Dive
2. Form 4 Insider Analysis
3. 10-K Risk Factor Comparison
4. DSO & A/R Analysis
5. 13F Institutional Analysis
6. Red Flag Scan
7. Green Channel Revenue Valuation (Workflow 8)

**Additional forensic checks:**
- **Related party transactions** (DEF 14A)
- **Executive compensation vs. performance** (DEF 14A)
- **Debt covenants** (10-K/10-Q notes)
- **Off-balance-sheet obligations** (10-K Item 7)
- **Customer concentration** (10-K Item 1)
- **Geographic revenue mix** (10-K segment reporting)

**Output:** Consolidated report with all sections, executive summary, and final verdict.

---

### Workflow 8: Green Channel Revenue Valuation

**Use when:** "Is the stock undervalued?", "Fair value analysis", "Revenue vs price", "Green channel", 
"YoY revenue comparison", "Price divergence", "Value opportunity", "Fallen through revenue floor",
"P/S ratio analysis", "historical valuation"

This workflow identifies potential value opportunities by analyzing the stock's Price-to-Sales ratio
relative to its historical range, then cross-referencing with insider buying conviction. The "Green
Channel" is a valuation band derived from historical P/S ratios — when price falls below the band,
it signals potential undervaluation.

---

#### The Green Channel Concept

The Green Channel is a **P/S-based valuation band** that defines where a stock "should" trade based
on its revenue and historical P/S multiple range. Think of it like a rubber band — the P/S ratio
tends to revert toward historical averages over time.

```
                PREMIUM ZONE (P/S > 12x)
    ═══════════════════════════════════════════════  ← Historical Max P/S
                    
                 FAIR VALUE ZONE
    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  ← 5-Year Avg P/S
    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓ GREEN CHANNEL ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  
    ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  ← 10-Year Median P/S
                    
              DEEP VALUE ZONE (P/S < 8x)
    ───────────────────────────────────────────────  ← Historical Min P/S
    
    SIGNAL: If current P/S is significantly below historical average,
            the stock may be undervalued — ESPECIALLY if insiders are buying.
```

---

#### Data Required

1. **TTM Revenue** — Trailing Twelve Months revenue (sum of last 4 quarters)
2. **Shares Outstanding** — From latest 10-Q or market data
3. **Current Stock Price** — Real-time quote
4. **Historical P/S Ratios** — 5-year avg, 10-year median, 10-year min/max
5. **Quarterly Revenue (8 quarters)** — For trend visualization
6. **Form 4 Open Market Purchases** — C-Suite and Director buys during price drop

---

#### Step-by-Step Calculation

**Step 1: Get Revenue Per Share (TTM)**

The TTM (Trailing Twelve Months) is the sum of the last 4 quarters of revenue.

```
Revenue Per Share = TTM Revenue ÷ Shares Outstanding
```

Web search queries:
```
"[TICKER] revenue per share TTM trailing twelve months"
"[TICKER] quarterly revenue Q4 Q3 Q2 Q1"
"[TICKER] shares outstanding"
```

**Example (MSFT):**
```
TTM Revenue = $305.45B
Shares Outstanding = 7.43B
Revenue Per Share = $305.45B ÷ 7.43B = $41.11
```

---

**Step 2: Get Historical P/S Ratio Range**

The Price-to-Sales ratio tells you how much investors pay per dollar of revenue.
You need the historical range to define the Green Channel boundaries.

Web search query:
```
"[TICKER] historical price to sales ratio P/S 5 year 10 year range"
```

**Extract these metrics:**

| Metric | Description | Source |
|--------|-------------|--------|
| 10-Year Minimum | Lowest P/S in 10 years (deep value floor) | GuruFocus, MacroTrends |
| 10-Year Median | Middle of 10-year range (fair value anchor) | GuruFocus |
| 5-Year Average | Recent trading norm | FinanceCharts |
| 10-Year Maximum | Highest P/S in 10 years (premium ceiling) | GuruFocus |
| Current P/S | Today's valuation | Calculated or search |

**Example (MSFT):**
```
10-Year Min P/S    = 4.49x
10-Year Median P/S = 10.26x
5-Year Avg P/S     = 11.88x
10-Year Max P/S    = 14.77x
Current P/S        = 9.43x
```

---

**Step 3: Calculate Implied Price at Each P/S Level**

The formula is:
```
Implied Price = Revenue Per Share × P/S Ratio
```

Calculate each boundary:

| Zone | P/S Multiple | Implied Price | Formula |
|------|--------------|---------------|---------|
| Deep Value Floor | 10Y Min (e.g., 4.49x) | $184 | $41.11 × 4.49 |
| Fair Value Anchor | 10Y Median (e.g., 10.26x) | $422 | $41.11 × 10.26 |
| 5-Year Average | 5Y Avg (e.g., 11.88x) | $488 | $41.11 × 11.88 |
| Premium Ceiling | 10Y Max (e.g., 14.77x) | $607 | $41.11 × 14.77 |

---

**Step 4: Define Green Channel Zones**

Based on the historical P/S range, define three zones:

| Zone | P/S Range | Price Range | Interpretation |
|------|-----------|-------------|----------------|
| **DEEP VALUE** | Min to ~0.8× Median | Floor to ~$340 | Historically cheap, rare opportunity |
| **FAIR VALUE** (Green Channel) | 0.8× Median to 1.2× Avg | ~$340 to ~$585 | Normal trading range |
| **PREMIUM** | >1.2× Avg | >$585 | Historically expensive, multiple expansion |

**Zone boundaries formula:**
```
Deep Value Ceiling = Revenue Per Share × (10Y Median × 0.8)
Fair Value Ceiling = Revenue Per Share × (5Y Avg × 1.2)
```

---

**Step 5: Verify Current P/S Calculation**

Always double-check the P/S ratio yourself:

**Method 1: Per-Share Basis**
```
P/S Ratio = Current Stock Price ÷ Revenue Per Share (TTM)
```

**Method 2: Total Company Basis**
```
P/S Ratio = Market Cap ÷ TTM Revenue
```

**Example (MSFT at $381.87):**
```
Method 1: $381.87 ÷ $41.11 = 9.29x ✓
Method 2: $2,837B ÷ $305.45B = 9.29x ✓
```

---

**Step 6: Determine Current Position in Channel**

```
Current Price: $381.87
Current P/S: 9.29x

Position Analysis:
├── vs 10Y Median (10.26x): -9.5% below → UNDERVALUED relative to median
├── vs 5Y Average (11.88x): -21.8% below → SIGNIFICANTLY UNDERVALUED
├── vs 10Y Max (14.77x): -37.1% below → NOT in premium territory
└── vs 10Y Min (4.49x): +107% above → NOT in distress

Zone: LOWER FAIR VALUE (Green Channel)
Signal: P/S multiple compressed, potential mean reversion upside
```

---

**Step 7: Calculate Upside/Downside Scenarios**

```
Upside to 5-Year Average P/S:
    Target Price = $41.11 × 11.88 = $488
    Upside = ($488 - $382) / $382 = +27.7%

Upside to 10-Year Median P/S:
    Target Price = $41.11 × 10.26 = $422
    Upside = ($422 - $382) / $382 = +10.5%

Downside to 10-Year Min P/S (bear case):
    Target Price = $41.11 × 4.49 = $185
    Downside = ($185 - $382) / $382 = -51.6%
```

---

**Step 8: Cross-Reference Insider Conviction**

This is the KEY confirmation signal. P/S compression alone isn't enough — insiders
must confirm with open market purchases.

Look for:
- **Open Market Purchases (P code)** by CEO, CFO, Directors during price drop
- **Timing**: Buys occurring AFTER P/S fell below historical average
- **Size**: Meaningful dollar amounts ($100K+ for officers, $25K+ for directors)

```
IF Current_P/S < 5Y_Avg_P/S AND Insider_Open_Market_Buys > 0:
    Conviction = "HIGH" → Smart money confirming undervaluation
    
IF Current_P/S < 5Y_Avg_P/S AND Insider_Open_Market_Buys = 0:
    Conviction = "LOW" → No insider confirmation, proceed with caution
    
IF Current_P/S > 5Y_Avg_P/S AND Insider_Open_Market_Sells > Normal:
    Conviction = "BEARISH" → Insiders reducing at premium valuations
```

---

#### Output Format

```
## [TICKER] — Green Channel Revenue Valuation

### 📊 P/S Calculation (Step-by-Step)
| Input | Value | Source |
|-------|-------|--------|
| TTM Revenue | $XXX.XXB | Latest 10-Q/8-K |
| Shares Outstanding | X.XXB | SEC filing |
| Revenue Per Share | $XX.XX | Calculated |
| Current Stock Price | $XXX.XX | Market |
| Current P/S Ratio | X.XXx | Price ÷ Rev/Share |

### 📈 Historical P/S Range
| Metric | P/S Multiple | Implied Price |
|--------|--------------|---------------|
| 10-Year Maximum | XX.XXx | $XXX (Premium Ceiling) |
| 5-Year Average | XX.XXx | $XXX (Fair Value High) |
| 10-Year Median | XX.XXx | $XXX (Fair Value Anchor) |
| **Current** | **X.XXx** | **$XXX** |
| 10-Year Minimum | XX.XXx | $XXX (Deep Value Floor) |

### 🎯 Green Channel Position
| Zone | P/S Range | Price Range | Status |
|------|-----------|-------------|--------|
| Premium | >XX.Xx | >$XXX | ○ |
| Fair Value (Upper) | XX.Xx - XX.Xx | $XXX - $XXX | ○ |
| Fair Value (Lower) | XX.Xx - XX.Xx | $XXX - $XXX | ● CURRENT |
| Deep Value | <XX.Xx | <$XXX | ○ |

**Current Position:** [Zone name]
**vs 5Y Average:** [+X% above / -X% below]
**vs 10Y Median:** [+X% above / -X% below]

### 📉 Revenue Trend (8 Quarters)
[SEE VISUAL BELOW]

### 🎯 Insider Conviction Check
| Date | Insider | Title | Type | Value |
|------|---------|-------|------|-------|
| ... | ... | ... | P/S | $XXX,XXX |

**Open Market Buys During Compression:** $XXX,XXX
**Conviction Level:** [HIGH / MEDIUM / LOW]

### Upside/Downside Scenarios
| Scenario | Target P/S | Target Price | Return |
|----------|------------|--------------|--------|
| Bull (5Y Avg reversion) | XX.Xx | $XXX | +XX% |
| Base (10Y Median) | XX.Xx | $XXX | +XX% |
| Bear (10Y Min) | XX.Xx | $XXX | -XX% |

### Verdict
**P/S Position:** [DEEP VALUE / LOWER FAIR VALUE / UPPER FAIR VALUE / PREMIUM]
**Mean Reversion Potential:** [HIGH / MEDIUM / LOW]
**Insider Confirmation:** [YES / NO / PARTIAL]
**Action:** [BUY / ACCUMULATE / HOLD / TRIM / SELL]
```

---

#### Green Channel Dashboard Widget

When rendering via `visualize:show_widget`, include these components:

##### Component 1: Revenue Trend Bar Chart (8 Quarters)

Show quarterly revenue progression with YoY comparison arrows. This visualizes whether
revenue is growing, flat, or declining — critical context for the P/S analysis.

```javascript
// Revenue bars - 8 quarters side by side
// Green bars = revenue growing YoY
// Red bars = revenue declining YoY
// Show $ value and YoY % on each bar

const revenueData = [
  { quarter: 'Q1 24', revenue: 61.9, yoy: +17 },
  { quarter: 'Q2 24', revenue: 64.7, yoy: +18 },
  { quarter: 'Q3 24', revenue: 64.2, yoy: +16 },
  { quarter: 'Q4 24', revenue: 66.1, yoy: +15 },
  { quarter: 'Q1 25', revenue: 69.6, yoy: +12 },
  { quarter: 'Q2 25', revenue: 75.0, yoy: +16 },
  { quarter: 'Q3 25', revenue: 79.1, yoy: +23 },
  { quarter: 'Q4 25', revenue: 81.3, yoy: +23 },
];
```

**Visual spec:**
- Bar height proportional to revenue
- Color: Green if YoY growth positive, Red if negative
- Label on each bar: "$XX.XB" and "+XX% YoY"
- Y-axis: Revenue in billions
- Show trend line connecting bar tops

##### Component 2: P/S Channel Visualization

Show current price position relative to the P/S-implied valuation bands.

```
┌─────────────────────────────────────────────────────────────────┐
│  Price-to-Sales Channel — [TICKER]                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  $607 ┤ ─────────────────────────────────  10Y Max (14.77x)     │
│       │ ░░░░░░░ PREMIUM ZONE ░░░░░░░░░                          │
│  $488 ┤ ═════════════════════════════════  5Y Avg (11.88x)      │
│       │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                         │
│  $422 ┤ ▓▓▓▓▓▓▓ GREEN CHANNEL ▓▓▓▓▓▓▓▓▓  10Y Median (10.26x)   │
│       │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                         │
│  $382 ┤ ●══════════════════════════════════ CURRENT PRICE       │
│       │                                                         │
│  $185 ┤ ───────────────────────────────────  10Y Min (4.49x)    │
│       │   DEEP VALUE ZONE                                       │
│       └─────────────────────────────────────────────────────────│
├─────────────────────────────────────────────────────────────────┤
│  Current P/S: 9.29x │ Position: LOWER FAIR VALUE                │
│  vs 5Y Avg: -21.8%  │ vs 10Y Median: -9.5%                      │
├─────────────────────────────────────────────────────────────────┤
│  Upside to 5Y Avg: +27.7% ($488)                                │
│  Upside to 10Y Median: +10.5% ($422)                            │
└─────────────────────────────────────────────────────────────────┘
```

##### Component 3: Insider Conviction Timeline

Overlay insider purchases on the price chart to show conviction timing.

```
Price │
      │     ╭───╮
$550  │    ╱     ╲        ATH
      │   ╱       ╲
$450  │  ╱         ╲
      │ ╱           ╲
$400  │╱             ╲    ● Director buys $1.99M @ $397
      │               ╲  ╱
$382  │                ●╱  ← CURRENT
      └──────────────────────────────────────────────
       Oct    Nov    Dec    Jan    Feb    Mar
```

##### Component 4: Summary Card

```
┌─────────────────────────────────────────────────────────────────┐
│  GREEN CHANNEL VERDICT                                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   P/S Position:    ████████░░░░░░░░  LOWER FAIR VALUE          │
│                    ↑ Current (9.3x)                             │
│                                                                 │
│   Mean Reversion:  +27.7% to 5Y Avg                             │
│   Insider Signal:  ✓ CONFIRMED (Director buy at $397)           │
│                                                                 │
│   VERDICT: ACCUMULATE                                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

##### Full Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Green Channel Revenue Valuation — [TICKER]          [VERDICT]  │
├─────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────┐ ┌─────────────────────────────┐ │
│ │ REVENUE TREND (8 Quarters)  │ │ P/S CHANNEL POSITION        │ │
│ │                             │ │                             │ │
│ │  $81.3B ▓▓▓▓▓▓▓▓▓▓▓ +17%   │ │  Premium ░░░░░░░░░░░ $607   │ │
│ │  $79.1B ▓▓▓▓▓▓▓▓▓▓░ +23%   │ │  5Y Avg  ═══════════ $488   │ │
│ │  $75.0B ▓▓▓▓▓▓▓▓░░░ +16%   │ │  Median  ▓▓▓▓▓▓▓▓▓▓ $422   │ │
│ │  $69.6B ▓▓▓▓▓▓▓░░░░ +12%   │ │  CURRENT ●───────── $382   │ │
│ │  $66.1B ▓▓▓▓▓▓░░░░░ +15%   │ │  10Y Min ─────────── $185   │ │
│ │  $64.2B ▓▓▓▓▓░░░░░░ +16%   │ │                             │ │
│ │  $64.7B ▓▓▓▓▓░░░░░░ +18%   │ │  Upside to 5Y Avg: +27.7%   │ │
│ │  $61.9B ▓▓▓▓░░░░░░░ +17%   │ │                             │ │
│ └─────────────────────────────┘ └─────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ P/S CALCULATION                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Revenue/Share: $41.11 │ Price: $382 │ P/S: 9.29x            │ │
│ │ vs 5Y Avg (11.88x): -21.8% │ vs 10Y Median (10.26x): -9.5% │ │
│ └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ INSIDER CONVICTION                                              │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Feb 18: John Stanton (Director) — BUY $1.99M @ $397.35      │ │
│ │ Signal: ✓ HIGH CONVICTION — Open market buy during pullback │ │
│ └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  [Run full SEC analysis ↗]  [Compare to sector peers ↗]        │
└─────────────────────────────────────────────────────────────────┘
```

#### Trigger Phrases

Add to skill description triggers:
- "green channel"
- "revenue valuation"
- "undervalued"
- "fair value"
- "price vs revenue"
- "YoY revenue"
- "fallen through"
- "value opportunity"
- "revenue divergence"
- "P/S ratio"
- "price to sales"
- "historical valuation"
- "mean reversion"
- "multiple compression"
- "implied price"
- "revenue per share"

#### Key Learnings — Green Channel

1. **P/S ratio acts as a rubber band** — it tends to revert toward historical averages over time
2. **Use TTM (Trailing Twelve Months)** for revenue per share, not quarterly × 4
3. **Always verify P/S calculation yourself** — Price ÷ Revenue Per Share
4. **10-year median is the fair value anchor** — not the average (skewed by extremes)
5. **5-year average reflects recent trading norm** — useful for near-term targets
6. **Insider buying is THE confirmation signal** — P/S compression alone isn't enough
7. **Show the work** — always display the step-by-step calculation so user can verify
8. **Revenue trend matters** — declining revenue makes low P/S a value trap, not an opportunity

---

## EDGAR SEARCH PATTERNS

When using web search to find filings, use these query patterns:

```
# Recent filings
"[TICKER] SEC EDGAR filings"
"[TICKER] 10-K 2025 SEC filing"
"[TICKER] Form 4 insider transactions"

# Specific filing types
"[TICKER] 8-K material event SEC"
"[TICKER] DEF 14A proxy statement"
"[TICKER] 13F institutional holders"
"[TICKER] Schedule 13D activist investor"

# Red flag searches
"[TICKER] NT 10-K late filing"
"[TICKER] auditor change 8-K"
"[TICKER] restatement 8-K 4.02"
"[TICKER] going concern audit opinion"

# Green Channel Revenue Valuation searches
"[TICKER] quarterly revenue Q4 2025 Q4 2024 YoY"
"[TICKER] earnings revenue growth fiscal quarter"
"[TICKER] Form 4 open market purchase CEO CFO director"
"[TICKER] insider buying 2026"
"[TICKER] price sales ratio historical"
```

**Direct EDGAR URLs:**
- Company filings: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=[TICKER]&type=&dateb=&owner=include&count=40`
- Full-text search: `https://efts.sec.gov/LATEST/search-index?q=[SEARCH_TERM]`

---

## OUTPUT STANDARDS — INTERACTIVE DASHBOARD (NOT HTML FILES)

**DO NOT generate HTML file artifacts for SEC analysis.** Use `visualize:show_widget` to render
interactive dashboards directly in the conversation.

### Single Ticker Dashboard Structure

```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo] TICKER — Company Name                      [VERDICT]    │
│         Exchange · Sector · Price                               │
├─────────────────────────────────────────────────────────────────┤
│  Risk Score Gauge: [████████░░] 6.2/10                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┬──────────┬──────────┬──────────┐                  │
│  │Red Flags │ Insider  │ Inst Flow│ Lawsuits │  ← Metric cards  │
│  │    0     │ Selling  │   +85%   │  67.2K   │                  │
│  └──────────┴──────────┴──────────┴──────────┘                  │
├─────────────────────────────────────────────────────────────────┤
│  [Red Flags] [Insiders] [10-K Risks] [Institutions] ← Tabs      │
├─────────────────────────────────────────────────────────────────┤
│  Tab Content Area (switches based on selection)                 │
├─────────────────────────────────────────────────────────────────┤
│  [Analyze deeper ↗]  [Compare to peers ↗]  ← sendPrompt buttons │
└─────────────────────────────────────────────────────────────────┘
```

### Multi-Ticker Comparison Dashboard Structure

```
┌─────────────────────────────────────────────────────────────────┐
│  SEC Filing Comparison — [TICKERS]                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────┬─────────┬─────────┬─────────┐                      │
│  │ TICK1   │ TICK2   │ TICK3   │ TICK4   │  ← Clickable cards   │
│  │ ⚠ 6.2   │ ✓ 3.1   │ ✓ 4.0   │ ⚠ 5.5   │  ← Risk scores      │
│  │ Selling │ Neutral │ Buying  │ Selling │  ← Sentiment         │
│  └─────────┴─────────┴─────────┴─────────┘                      │
├─────────────────────────────────────────────────────────────────┤
│  Comparative Bar Chart (Insider Flow / Institutional %)         │
├─────────────────────────────────────────────────────────────────┤
│  Red Flag Matrix Table (tickers × flag types)                   │
├─────────────────────────────────────────────────────────────────┤
│  [Deep dive TICK1 ↗]  [Deep dive TICK2 ↗]  ...                  │
└─────────────────────────────────────────────────────────────────┘
```

### Risk Score Calculation

Calculate a 1-10 risk score based on:

| Factor | Weight | Scoring |
|--------|--------|---------|
| Red flags (NT, 4.01, 4.02, going concern) | 30% | Each = +2.5 points |
| Insider sentiment | 20% | Heavy selling = +2, neutral = +1, buying = 0 |
| Litigation exposure | 20% | >$5B potential = +2, >$1B = +1 |
| 10-K risk factor changes | 15% | New critical risks = +1.5 |
| Institutional flow | 15% | Net reduction = +1.5, accumulation = 0 |

**Verdicts:**
- 1-3: ✅ PROCEED
- 4-5: 🟡 PROCEED WITH CAUTION
- 6-7: ⚠️ CAUTION
- 8-10: 🚨 AVOID / INVESTIGATE

### Color System (CSS Variables)

Use these CSS variables for proper light/dark mode support:

| Signal | Background | Text/Border |
|--------|------------|-------------|
| Bullish/Clear | `var(--color-background-success)` | `#1D9E75` / `#085041` |
| Bearish/Danger | `var(--color-background-danger)` | `#E24B4A` / `#791F1F` |
| Warning/Caution | `var(--color-background-warning)` | `#BA7517` / `#633806` |
| Info/Neutral | `var(--color-background-info)` | `var(--color-text-info)` |

### Interactive Elements

1. **Tabs** — Switch between Red Flags, Insiders, 10-K Risks, Institutions
2. **Charts** — Use Chart.js for institutional flow visualization
3. **sendPrompt() buttons** — Enable drill-down:
   - "Deep dive into [TICKER] talc litigation"
   - "Compare [TICKER] insider activity to peers"
   - "Show me [TICKER] Form 4 details"

### Signal Markers (in dashboard)
| Marker | Meaning |
|--------|---------|
| 🚨 | Critical red flag — immediate attention |
| ⚠ | Warning — monitor closely |
| ✓ | Clear — no issues found |
| ↑↑ | Strong accumulation / buying |
| ↓↓ | Heavy reduction / selling |

---

## QUALITY CHECKLIST

Before finalizing any filing analysis:

- [ ] Web search executed for each filing type mentioned
- [ ] Filing dates and item numbers cited accurately
- [ ] Insider transactions classified by transaction code (P, S, M, etc.)
- [ ] 10b5-1 status noted for all insider sales
- [ ] DSO calculated with correct formula and periods
- [ ] 13F lag (45 days) acknowledged
- [ ] Red flags explicitly searched for, not assumed absent
- [ ] Verified facts distinguished from inferences
- [ ] Caveats and limitations stated
- [ ] Actionable verdict provided
- [ ] **Dashboard rendered via visualize:show_widget (NOT HTML file)**
- [ ] **sendPrompt() buttons included for drill-down actions**

---

## KEY LEARNINGS

1. **Open market purchases (P) are the only true bullish insider signal** — everything else is noise
2. **10b5-1 sales are pre-programmed** — check adoption date for timing signals
3. **13F data is 45 days stale** — hedge funds may have already exited
4. **NT filings are serious** — companies don't miss deadlines without reason
5. **Auditor changes require explanation** — "disagreement" vs. "fee dispute" matters
6. **DSO rising while revenue grows** could indicate channel stuffing or credit issues
7. **10-K risk factors that move UP in order** are becoming more material
8. **Management silence on 10-K risks** during earnings calls is itself a signal
9. **Schedule 13D amendments** often signal activist strategy shifts before announcements
10. **Going concern language** in audit opinion is the most severe red flag
11. **Parallel execution** — For multi-ticker, batch all web searches in single tool call

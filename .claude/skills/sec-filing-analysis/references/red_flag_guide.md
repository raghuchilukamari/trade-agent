# Red Flag Detection Guide

Systematic approach to identifying warning signs in SEC filings.

---

## Severity Levels

| Level | Color | Action |
|-------|-------|--------|
| 🔴 CRITICAL | Red | Immediate investigation, consider exiting position |
| 🔴 HIGH | Red | Deep investigation required before any action |
| 🟡 MEDIUM | Yellow | Monitor closely, investigate context |
| 🟢 LOW | Green | Note for awareness, no immediate action |

---

## Red Flag Categories

### Category 1: Filing Irregularities

| Flag | Filing | Severity | What to Do |
|------|--------|----------|------------|
| Late filing | NT 10-K / NT 10-Q | 🔴 HIGH | Check reason code. "Internal controls" = very bad. |
| Missed deadline without NT | No filing | 🔴 CRITICAL | Company may be in crisis. |
| Repeated NT filings | Multiple NT | 🔴 CRITICAL | Systemic accounting problems. |
| Filing amendment | 10-K/A, 10-Q/A | 🟡 MEDIUM | What was corrected? Material? |

### Category 2: Auditor Issues

| Flag | Filing | Severity | What to Do |
|------|--------|----------|------------|
| Auditor resignation | 8-K Item 4.01 | 🔴 HIGH | Read the 4.01 carefully. "Disagreement" is worse than "fees". |
| Auditor dismissal | 8-K Item 4.01 | 🔴 HIGH | Why fire the auditor? |
| Restatement | 8-K Item 4.02 | 🔴 HIGH | What periods? Revenue? Expenses? |
| Going concern opinion | 10-K Audit Opinion | 🔴 CRITICAL | Auditor doubts 12-month survival. |
| Qualified opinion | 10-K Audit Opinion | 🔴 HIGH | What did auditor object to? |
| Material weakness | 10-K Item 9A | 🟡 MEDIUM | Internal control failure. Check if remediated. |

### Category 3: Insider Activity

| Flag | Filing | Severity | What to Do |
|------|--------|----------|------------|
| Cluster selling | Multiple Form 4 | 🟡 MEDIUM | 3+ insiders within 2 weeks. Check if 10b5-1. |
| CEO/CFO selling outside 10b5-1 | Form 4 | 🟡 MEDIUM | Discretionary sale = bearish signal. |
| New 10b5-1 plan adoption | Form 4 footnote | 🟡 MEDIUM | May signal timing awareness. |
| 10b5-1 plan termination | Form 4 footnote | 🟡 MEDIUM | Why stop selling? |
| No insider purchases for 12+ months | Absence of Form 4 P | 🟢 LOW | Not buying their own stock. |

### Category 4: Balance Sheet Signals

| Flag | Source | Severity | What to Do |
|------|--------|----------|------------|
| DSO rising faster than revenue | 10-Q/10-K | 🟡 MEDIUM | Collection issues or channel stuffing. |
| Allowance for doubtful accounts spiking | 10-Q/10-K Notes | 🟡 MEDIUM | Credit quality deteriorating. |
| Inventory buildup | 10-Q/10-K | 🟡 MEDIUM | Demand slowing? |
| Goodwill impairment | 8-K Item 2.06 | 🟡 MEDIUM | Overpaid for acquisitions. |
| Debt covenant violation | 10-Q/10-K Notes | 🔴 HIGH | May trigger acceleration. |
| Liquidity warning | 10-K Item 7 | 🔴 HIGH | Cash burn concerns. |

### Category 5: Risk Factor Changes

| Flag | Source | Severity | What to Do |
|------|--------|----------|------------|
| NEW risk factor | 10-K Item 1A | 🟡 MEDIUM | What emerged since last year? |
| Risk factor moved UP in order | 10-K Item 1A | 🟡 MEDIUM | Priority increased = more material. |
| "Substantial doubt" language | 10-K anywhere | 🔴 HIGH | Going concern adjacent. |
| Regulatory investigation NEW | 10-K Item 1A or 8-K | 🟡 MEDIUM | DOJ, SEC, FTC? |
| Customer concentration increased | 10-K Item 1 | 🟡 MEDIUM | Single customer dependency. |

### Category 6: Governance Issues

| Flag | Source | Severity | What to Do |
|------|--------|----------|------------|
| Related party transaction | DEF 14A | 🟡 MEDIUM | Self-dealing concerns. |
| CEO/Chairman same person | DEF 14A | 🟢 LOW | Governance purists dislike. |
| Board independence low | DEF 14A | 🟡 MEDIUM | <50% independent = concern. |
| Executive compensation vs. performance divergence | DEF 14A | 🟡 MEDIUM | Pay up, performance down. |
| Shareholder proposal on governance | DEF 14A | 🟡 MEDIUM | What are activists pushing? |

### Category 7: Activist Involvement

| Flag | Source | Severity | What to Do |
|------|--------|----------|------------|
| New 13D filing | Schedule 13D | 🟡 MEDIUM | Who's accumulating? Read "Purpose". |
| 13D amendment with new purpose | 13D/A | 🟡 MEDIUM | Strategy shift. |
| 13D → 13G conversion | Schedule 13G | 🟢 LOW | Activist going passive. |
| 13G → 13D conversion | Schedule 13D | 🟡 MEDIUM | Passive going activist. |
| Multiple activists | Multiple 13D | 🟡 MEDIUM | Pressure building. |

---

## Red Flag Combinations (Compounding Risk)

These combinations are worse than individual flags:

| Combination | Severity | Interpretation |
|-------------|----------|----------------|
| NT + Auditor change | 🔴 CRITICAL | Accounting crisis |
| Insider selling + Earnings miss | 🔴 HIGH | Insiders knew |
| DSO rising + Revenue decelerating | 🔴 HIGH | Channel stuffing suspected |
| Going concern + Debt maturity | 🔴 CRITICAL | Liquidity crisis |
| Risk factor addition + 8-K litigation | 🟡 MEDIUM | Material legal exposure |
| CEO departure + NT filing | 🔴 CRITICAL | Leadership crisis |

---

## False Positives (Context Matters)

Not everything that looks bad is bad:

| Flag | May Not Be Red If... |
|------|----------------------|
| Auditor change | Big 4 → Big 4 for cost savings |
| Insider selling | 100% via 10b5-1, adopted 12+ months ago |
| DSO rising | Company shifted to enterprise (longer cycles) |
| NT filing | Acquisition accounting complexity |
| Goodwill impairment | Industry-wide downturn |
| CEO departure | Planned retirement, strong successor |

---

## Detection Workflow

### Step 1: Quick Scan

Run these searches for any ticker:

```
"[TICKER] NT 10-K"
"[TICKER] NT 10-Q"
"[TICKER] 8-K 4.01 auditor"
"[TICKER] 8-K 4.02 restatement"
"[TICKER] going concern"
```

### Step 2: Insider Check

```
"[TICKER] Form 4 SEC EDGAR"
"[TICKER] insider selling"
```

### Step 3: Institutional Check

```
"[TICKER] 13D activist"
"[TICKER] 13F institutional"
```

### Step 4: Deep Dive (if flags found)

- Pull full 10-K, read Item 1A word-for-word
- Pull DEF 14A, check Related Party Transactions
- Calculate DSO from last 8 quarters
- Read earnings call transcript for management spin

---

## Output Format for Red Flag Scan

```
## [TICKER] — Red Flag Scan

### 🔴 CRITICAL Flags
[List or "None found"]

### 🔴 HIGH Flags
[List or "None found"]

### 🟡 MEDIUM Flags
[List or "None found"]

### ✅ Cleared Checks
- NT filings: None found
- Auditor changes: None found
- Restatements: None found
- Going concern: None found
- Cluster insider selling: None found

### Overall Risk Assessment
**Risk Level:** [LOW / MEDIUM / HIGH / CRITICAL]
**Recommendation:** [PROCEED / PROCEED WITH CAUTION / INVESTIGATE FURTHER / AVOID]
```

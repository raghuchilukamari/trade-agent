# SEC Filing Quick Reference Card

## Filing → Question Mapping

| Question | Filing to Check |
|----------|-----------------|
| Are insiders selling? | **Form 4** |
| Is it a pre-planned sale? | **Form 4 footnotes** (10b5-1) |
| What are the real risks? | **10-K Item 1A** |
| What's hidden in footnotes? | **10-K/10-Q Notes to Financial Statements** |
| Are hedge funds buying? | **13F-HR** (45-day lag) |
| Is an activist involved? | **Schedule 13D** |
| How much are executives paid? | **DEF 14A** |
| Any new debt? | **8-K Item 2.03, 10-Q liquidity** |
| Did they miss filing deadline? | **NT 10-K / NT 10-Q** |
| Are prior financials reliable? | **8-K Item 4.02** |
| Is there a merger? | **8-K Item 1.01, DEFM 14A** |
| What did shareholders vote for? | **8-K Item 5.07** |

---

## Form 4 Transaction Codes

| Code | Meaning | Signal |
|------|---------|--------|
| **P** | Open market purchase | 🟢 BULLISH — discretionary buy |
| **S** | Open market sale | 🟡 Context-dependent |
| **M** | Option exercise | ⚪ Neutral |
| **A** | Grant/Award | ⚪ Neutral |
| **F** | Tax withholding | ⚪ Neutral |
| **G** | Gift | ⚪ Neutral |

---

## Red Flag Filings

| Filing | Signal | Severity |
|--------|--------|----------|
| **NT 10-K/10-Q** | Can't file on time | 🔴 HIGH |
| **8-K Item 4.01** | Auditor change | 🔴 HIGH |
| **8-K Item 4.02** | Restatement coming | 🔴 HIGH |
| **8-K Item 2.04** | Restructuring | 🟡 MEDIUM |
| **8-K Item 2.06** | Asset impairment | 🟡 MEDIUM |
| **Going concern** | Survival doubts | 🔴 CRITICAL |
| **Cluster selling** | 3+ insiders in 2 weeks | 🟡 MEDIUM |

---

## Filing Deadlines

| Filing | Deadline |
|--------|----------|
| 10-K | 60 days after fiscal year-end |
| 10-Q | 40 days after quarter-end |
| 8-K | 4 business days after event |
| Form 4 | 2 business days after transaction |
| 13F-HR | 45 days after quarter-end |
| Schedule 13D | 10 days after crossing 5% |
| DEF 14A | Before annual meeting |

---

## DSO Formula

```
DSO = (Accounts Receivable ÷ Revenue) × Days in Period

Quarterly: DSO = (A/R ÷ Quarterly Revenue) × 91.25
Annual: DSO = (A/R ÷ Annual Revenue) × 365
```

**Warning signs:**
- DSO rising faster than revenue growth
- A/R growth >> Revenue growth for 3+ quarters
- Allowance for doubtful accounts increasing

---

## 10-K Key Sections

| Item | Section | What to Look For |
|------|---------|------------------|
| 1 | Business | Customer concentration, competitive position |
| 1A | Risk Factors | NEW or EXPANDED language vs. prior year |
| 7 | MD&A | Management spin vs. actual numbers |
| 8 | Financial Statements | Footnotes = real story |
| — | Commitments & Contingencies | Hidden liabilities |
| — | Segment Reporting | Which business makes money? |

---

## DEF 14A Key Sections

- **Executive Compensation Tables** — Pay vs. performance
- **Related Party Transactions** — Conflicts of interest
- **Shareholder Proposals** — What activists want
- **Stock Ownership Table** — Who controls the company
- **CD&A** — What metrics drive bonuses

---

## EDGAR Search URLs

```
# Company filings
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=[TICKER]

# Full-text search
https://efts.sec.gov/LATEST/search-index?q=[SEARCH]

# Form 4 lookup
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=[TICKER]&type=4

# 13F lookup
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=[TICKER]&type=13F
```

---

## Third-Party Tools

| Tool | Best For | URL |
|------|----------|-----|
| OpenInsider | Form 4 screening | openinsider.com |
| WhaleWisdom | 13F analysis | whalewisdom.com |
| Bamsec | Clean filing viewer | bamsec.com |
| Last10K | 10-K comparisons | last10k.com |
| SEC EDGAR | Official source | sec.gov/edgar |

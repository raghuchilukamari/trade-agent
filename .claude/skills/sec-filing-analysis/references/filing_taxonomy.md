# SEC Filing Taxonomy — Complete Reference

All SEC filings organized by tier of importance for equity research.

---

## Tier 1: Core Filings (Always Check)

| Filing | What It Reveals | Timing | Key Sections |
|--------|-----------------|--------|--------------|
| **10-K** | Full-year financials, risk factors, business description, legal proceedings | Within 60 days of fiscal year-end | Item 1 (Business), Item 1A (Risk Factors), Item 7 (MD&A), Item 8 (Financials) |
| **10-Q** | Quarterly update, interim risks, liquidity changes | Within 40 days of quarter-end | Part I Item 1 (Financials), Part I Item 2 (MD&A), Part II Item 1A (Risk Updates) |
| **8-K** | Material events: earnings, deals, executive changes, litigation | Within 4 business days of event | See 8-K Item Reference below |

### 8-K Item Reference

| Item | Trigger | Significance |
|------|---------|--------------|
| 1.01 | Material Definitive Agreement | Deals, partnerships, major contracts |
| 1.02 | Bankruptcy or Receivership | 🔴 CRITICAL |
| 2.01 | Acquisition/Disposition | M&A activity |
| 2.02 | Results of Operations | Earnings release |
| 2.03 | Direct Financial Obligation | New debt |
| 2.04 | Restructuring | Layoffs, write-downs |
| 2.05 | Exit Activities | Store closures, segment discontinuation |
| 2.06 | Material Impairment | Asset writedowns |
| 4.01 | Auditor Change | 🔴 Why did they leave? |
| 4.02 | Non-Reliance on Prior Financials | 🔴 Restatement coming |
| 5.02 | Departure/Appointment of Officers | Executive turnover |
| 5.07 | Shareholder Vote Results | Proxy meeting outcomes |
| 7.01 | Regulation FD Disclosure | Guidance, presentations |
| 8.01 | Other Events | Catch-all (often bad news) |

---

## Tier 2: Insider & Ownership Filings

| Filing | Who Files | What It Reveals | Timing |
|--------|-----------|-----------------|--------|
| **Form 4** | Officers, Directors, 10%+ owners | Insider buys/sells, option exercises | Within 2 business days |
| **Form 3** | New insiders | Initial ownership disclosure | Within 10 days |
| **Form 5** | Insiders | Annual catch-up for unreported transactions | Within 45 days of fiscal year-end |
| **Form 144** | Insiders | *Intent* to sell restricted stock | Same day or before sale |
| **Schedule 13D** | 5%+ activist owners | Ownership stake + intentions/plans | Within 10 days of crossing 5% |
| **Schedule 13G** | 5%+ passive owners | Ownership stake (passive intent) | Within 45 days of year-end |
| **13F-HR** | Institutions ($100M+ AUM) | Quarterly portfolio holdings | Within 45 days of quarter-end |

### Form 4 Transaction Codes

| Code | Meaning | Signal |
|------|---------|--------|
| **P** | Open market purchase | 🟢 BULLISH — discretionary buy |
| **S** | Open market sale | 🟡 Context-dependent |
| **M** | Option exercise | ⚪ Neutral |
| **A** | Grant/Award | ⚪ Neutral (compensation) |
| **F** | Tax withholding | ⚪ Neutral |
| **G** | Gift | ⚪ Neutral |
| **J** | Other acquisition/disposition | Context-dependent |
| **C** | Conversion of derivative | ⚪ Neutral |

---

## Tier 3: Proxy & Governance

| Filing | What It Reveals | Timing |
|--------|-----------------|--------|
| **DEF 14A** | Executive compensation, board composition, related-party transactions, shareholder proposals | Before annual meeting |
| **DEFA 14A** | Additional proxy materials, management responses | As needed |
| **PRE 14A** | Preliminary proxy (draft) | Before DEF 14A |
| **8-K Item 5.07** | Shareholder vote results | Within 4 days of meeting |

### DEF 14A Key Sections

1. **Executive Compensation Tables** — Summary compensation, pay vs. performance
2. **Related Party Transactions** — Conflicts of interest
3. **Shareholder Proposals** — What activists are pushing
4. **Stock Ownership Table** — Who controls the company
5. **Compensation Discussion & Analysis (CD&A)** — What metrics drive bonuses
6. **Board Independence** — Governance quality

---

## Tier 4: Offerings & Debt

| Filing | What It Reveals | Timing |
|--------|-----------------|--------|
| **S-1** | IPO registration, full business disclosure | Before IPO |
| **S-3** | Shelf registration (ability to issue quickly) | Ongoing |
| **S-4** | Business combination registration | M&A transactions |
| **424B** | Prospectus supplement (actual terms) | At offering |
| **Form D** | Private placement to accredited investors | Within 15 days |
| **8-K Item 2.03** | New debt obligations, credit facilities | Within 4 days |

### Dilution Warning Signs

- S-3 filed → company *can* issue at any time
- S-3 + 424B → offering is happening NOW
- Form D → private placement (less dilutive but signifies cash need)
- Shelf registration increase → planning larger raise

---

## Tier 5: Red Flag Filings

| Filing | What It Signals | Severity |
|--------|-----------------|----------|
| **NT 10-K / NT 10-Q** | Can't file on time — accounting issues | 🔴 HIGH |
| **8-K Item 4.01** | Auditor resignation/dismissal | 🔴 HIGH |
| **8-K Item 4.02** | Prior financials unreliable — restatement | 🔴 HIGH |
| **8-K Item 2.04** | Restructuring charges | 🟡 MEDIUM |
| **8-K Item 2.06** | Material impairment | 🟡 MEDIUM |
| **Going concern** | Auditor doubts survival (in 10-K) | 🔴 CRITICAL |
| **Form 15** | Deregistration — going dark | 🔴 HIGH |
| **Schedule 13E-3** | Going private transaction | 🟡 MEDIUM |

---

## Filing Deadlines

### Regular Filings (Large Accelerated Filers)

| Filing | Deadline |
|--------|----------|
| 10-K | 60 days after fiscal year-end |
| 10-Q | 40 days after quarter-end |
| 8-K | 4 business days after event |
| Form 4 | 2 business days after transaction |
| 13F-HR | 45 days after quarter-end |
| Schedule 13D | 10 days after crossing 5% |
| DEF 14A | 20+ days before annual meeting |

### Quarter-End Calendar

```
Quarter End (e.g., Dec 31)
    │
    ├── +4 days: 8-K with earnings release
    │
    ├── +40 days: 10-Q due (or 10-K if fiscal year-end)
    │
    └── +45 days: 13F-HR due
```

---

## EDGAR Access Patterns

### Direct URLs

```
# Company filings page
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=[TICKER]&type=&dateb=&owner=include&count=40

# Specific filing type
https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=[TICKER]&type=[FORM_TYPE]

# Full-text search
https://efts.sec.gov/LATEST/search-index?q=[SEARCH_TERM]
```

### Common Filing Type Codes

| Search For | Use Type= |
|------------|-----------|
| Annual reports | 10-K |
| Quarterly reports | 10-Q |
| Current reports | 8-K |
| Insider transactions | 4 |
| Institutional holdings | 13F |
| Activist positions | 13D |
| Proxy statements | DEF 14A |
| Late filing notice | NT |

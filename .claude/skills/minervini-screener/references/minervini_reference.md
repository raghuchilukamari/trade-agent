# Minervini SEPA Methodology Reference

## Stage Analysis (Stan Weinstein framework, refined by Minervini)

| Stage | Description | MA Behavior | Action |
|-------|-------------|-------------|--------|
| **Stage 1** | Basing/accumulation | Price choppy around flat 200-day MA | No action — wait |
| **Stage 2** | Advancing/uptrend | Price > rising 200-day MA, MAs stacked bullishly | **BUY zone** — Trend Template stocks live here |
| **Stage 3** | Topping/distribution | Price crosses below 50-day MA, MAs start to flatten | Tighten stops, reduce position |
| **Stage 4** | Declining/markdown | Price < declining 200-day MA | Avoid — no longs |

**The Trend Template identifies stocks in Stage 2 only.** This is the ONLY stage where you want to initiate new positions.

---

## The 8 Criteria — Detailed Interpretation

### C1: Price > 150-day SMA AND Price > 200-day SMA
**Why:** The stock must be trading above its long-term trend lines. This confirms the trend is up, not just a short-term bounce within a downtrend. If price is below the 200-day, the stock is not in Stage 2.

### C2: 150-day SMA > 200-day SMA
**Why:** The intermediate trend (150-day) being above the long-term trend (200-day) confirms a sustained advance — not just a quick pop. This golden cross of the longer MAs takes time to develop and is hard to fake.

### C3: 200-day SMA trending up for ≥1 month
**Why:** A flat or declining 200-day MA means the long-term trend hasn't turned. Even if price is above it, the uptrend isn't confirmed until the 200-day itself is rising. Minervini prefers 4-5 months of upward slope for highest confidence.

**How to check:** Compare 200-day SMA today vs 200-day SMA 22 trading days ago. If positive, it's trending up. For stronger signals, check 110 trading days ago (~5 months).

### C4: 50-day SMA > 150-day SMA > 200-day SMA
**Why:** Full moving average alignment ("stacking") is the strongest possible confirmation of an uptrend. When all three MAs are properly ordered, the stock has momentum at every timeframe. This is the signature of institutional accumulation.

### C5: Price > 50-day SMA
**Why:** The stock needs near-term strength — it's not just in a long-term uptrend but is also currently healthy. A stock below its 50-day while above the 200-day may be in an intermediate correction, which is not ideal for new entries.

### C6: Price ≥ 30% above 52-week low
**Why (Raghu's 30% threshold):** The standard Minervini threshold is 25%, but Raghu uses 30% for additional confirmation. A stock 30%+ above its low has clearly broken out of its base and established a meaningful uptrend. Stocks near their lows are in Stage 1 or 4.

### C7: Price within 25% of 52-week high
**Why:** The best stocks to buy are near their highs, not their lows. A stock within 25% of its high is showing relative strength. Stocks far below their highs are damaged and often take months/years to recover.

**Counter-intuitive:** Most people want to "buy low." Minervini's research shows the biggest winners are bought near highs and go higher.

### C8: Relative Strength ≥ 70
**Why:** The stock must be outperforming 70% of all other stocks. RS measures price performance relative to the market/universe. High RS = institutional demand is driving the stock higher faster than average. Low RS stocks are being ignored or sold by institutions.

---

## Volatility Contraction Pattern (VCP) — Extension

After identifying a Trend Template stock, the ideal entry is at a VCP:

**What it is:** A series of price contractions (T1 > T2 > T3) where each pullback is shallower than the last, and volume dries up during the contraction. This shows supply is being absorbed.

**Pattern:**
```
   T1: -25% correction (wide)
       T2: -15% correction (tighter)
           T3: -8% correction (tight)
              → Pivot/breakout point
```

**Ideal entry:** Buy at the pivot point where price breaks above the VCP resistance on increased volume.

**VCP criteria (if implementing):**
- At least 2-3 contractions
- Each contraction shallower than the last
- Volume declining during base, expanding on breakout
- Base duration: 3-65 weeks typically

---

## Common Failure Patterns

| What It Looks Like | What It Actually Is | Danger |
|---------------------|---------------------|--------|
| Stock passes 7/8 — only fails C3 (200-day flat) | Stock in early Stage 2 transition | Wait for 200-day to confirm upward slope |
| Passes all 8 but RS declining | Momentum fading, institutions reducing | Tighten stop, don't add |
| Passes all 8 after a 100%+ run | Extended, high risk of Stage 3 top | Only enter on VCP, tight stop |
| Passes template but in a weak sector | Individual strength, sector headwind | Lower position size |


## Data Sources for Chat Mode

| Source | URL Pattern | Best For                         |
|--------|-------------|----------------------------------|
| StockAnalysis | stockanalysis.com/stocks/TICKER/financials/ | 5 year balance sheet             |
| Barchart | barchart.com/stocks/quotes/TICKER/technical-analysis | MA data (5,20,50,100,200)        |
| TipRanks | tipranks.com/stocks/TICKER/technical-analysis | Technical Analysis like RS, MACD |
| Finviz | finviz.com/quote.ashx?t=TICKER | Fundamentals + 20,50,200 SMAs    |add 
| TradingView | tradingview.com/symbols/NASDAQ-TICKER/ | 52-week range, MAs               |

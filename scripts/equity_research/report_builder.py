"""
report_builder.py — 5-section equity research HTML report generator.

Uses the same light-theme CSS as jnj_sec_analysis_2026-03-14.html (canonical template).
No web searches. No Claude API. Pure deterministic signal logic.
"""
from __future__ import annotations

from datetime import date
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# CSS — matches generate_report.py / jnj_sec_analysis_2026-03-14.html
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        line-height: 1.6; color: #1f2937;
        max-width: 960px; margin: 0 auto; padding: 24px; background: #f9fafb;
    }
    .title { font-size: 26px; font-weight: 700; color: #1a365d; margin-bottom: 4px; }
    .subtitle { font-size: 13px; color: #1e40af; margin-bottom: 20px; }
    h1 { font-size: 17px; font-weight: 600; color: #1e40af;
         border-bottom: 2px solid #e5e7eb; padding-bottom: 6px; margin: 22px 0 14px; }
    h2 { font-size: 14px; font-weight: 600; color: #374151; margin: 14px 0 6px; }
    h3 { font-size: 13px; font-weight: 600; color: #374151; margin: 10px 0 4px; }
    p { margin-bottom: 10px; font-size: 13px; }
    table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 12px; }
    th, td { padding: 8px 10px; text-align: left; border: 1px solid #e5e7eb; }
    th { background: #4b5563; color: white; font-weight: 600; }
    tr:nth-child(even) { background: #f9fafb; }
    .exec-summary { background: #dbeafe; border-left: 5px solid #2563eb;
                    padding: 14px; margin: 14px 0; }
    .red-flag-box { background: #fee2e2; border-left: 5px solid #dc2626;
                    padding: 14px; margin: 14px 0; }
    .warning-box  { background: #fef3c7; border-left: 5px solid #ea580c;
                    padding: 14px; margin: 14px 0; }
    .bullish-box  { background: #dcfce7; border-left: 5px solid #166534;
                    padding: 14px; margin: 14px 0; }
    .info-box { background: #dbeafe; border: 1px solid #2563eb;
                border-radius: 6px; padding: 14px; margin: 14px 0; }
    .disclaimer { background: #f3f4f6; border-left: 5px solid #9ca3af;
                  padding: 10px; margin: 20px 0; font-size: 11px; color: #6b7280; }
    .bullish { color: #166534; font-weight: 600; }
    .bearish { color: #dc2626; font-weight: 600; }
    .neutral { color: #92400e; font-weight: 600; }
    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 12px 0; }
    .grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin: 12px 0; }
    .metric-card { background: white; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; }
    .metric-label { font-size: 11px; color: #6b7280; text-transform: uppercase;
                    letter-spacing: .04em; margin-bottom: 4px; }
    .metric-value { font-size: 20px; font-weight: 700; color: #1a365d; }
    .metric-sub { font-size: 11px; color: #6b7280; margin-top: 2px; }
    ul, ol { margin: 6px 0 6px 20px; font-size: 13px; }
    li { margin-bottom: 3px; }
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{ticker} — Equity Research — {date}</title>
<style>{css}</style>
</head>
<body>
<div class="title">{company_name} ({ticker})</div>
<div class="subtitle">{exchange} · {sector} · Equity Research · {date} · Offline runner</div>
{body}
<div class="disclaimer">
  Generated offline by scripts/run_equity_research.py on {date}. Data: Polygon REST API,
  SEC EDGAR, walter_openai.csv, PostgreSQL ta_daily. No web searches.
  Analyst consensus not available (Benzinga plan required). Not financial advice.
</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_b(val: float) -> str:
    if val == 0:
        return "—"
    if abs(val) >= 1e9:
        return f"${val/1e9:.2f}B"
    elif abs(val) >= 1e6:
        return f"${val/1e6:.1f}M"
    return f"${val:,.0f}"


def _pct(val: float) -> str:
    return f"{val:+.1f}%" if val != 0 else "—"


def _yoy(curr: float, prev: float) -> str:
    if prev and prev != 0:
        return _pct((curr - prev) / abs(prev) * 100)
    return "—"


def _signal(val: float, good_above: float = 0, bad_below: float | None = None) -> str:
    """Return CSS class for a value."""
    if bad_below is not None and val < bad_below:
        return "bearish"
    if val >= good_above:
        return "bullish"
    return "neutral"


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Fundamentals
# ─────────────────────────────────────────────────────────────────────────────

def build_fundamentals(
    ticker: str,
    quarters: list[dict],
    ta: dict,
    details: dict,
) -> str:
    if not quarters:
        return "<div class='warning-box'><h2>Fundamentals</h2><p>No quarterly financial data available from Polygon API.</p></div>"

    q = quarters[0]  # Most recent quarter

    # Revenue trend table
    rows = []
    for i, qtr in enumerate(quarters):
        prev_rev = quarters[i + 1]["revenue"] if i + 1 < len(quarters) else None
        yoy = _yoy(qtr["revenue"], prev_rev) if prev_rev else "—"
        fcf_margin = round(qtr["fcf_approx"] / qtr["revenue"] * 100, 1) if qtr["revenue"] else 0
        rows.append(f"""
        <tr>
            <td>{qtr['fiscal_year']} {qtr['period']}</td>
            <td>{_fmt_b(qtr['revenue'])}</td>
            <td class="{_signal(qtr['gross_margin'], 40)}">{qtr['gross_margin']:.1f}%</td>
            <td class="{_signal(qtr['op_margin'], 15)}">{qtr['op_margin']:.1f}%</td>
            <td class="{_signal(qtr['net_margin'], 10)}">{qtr['net_margin']:.1f}%</td>
            <td>{_fmt_b(qtr['fcf_approx'])}</td>
            <td class="{_signal(fcf_margin, 10)}">{fcf_margin:.1f}%</td>
            <td>{qtr['eps_diluted']:.2f}</td>
            <td>{yoy}</td>
        </tr>""")

    # Balance sheet metrics
    de = round(q["long_term_debt"] / q["equity"], 2) if q.get("equity") and q["equity"] > 0 else 0
    net_cash = q.get("current_assets", 0) - q.get("long_term_debt", 0)

    # Technical data from ta_daily
    price = ta.get("close", 0)
    sma200 = ta.get("sma200", 0)
    sma50 = ta.get("sma50", 0)
    rsi = ta.get("rsi", 0)
    week52h = ta.get("week_52_high", 0)
    week52l = ta.get("week_52_low", 0)
    rs_spy = ta.get("rs_vs_spy", 0)
    is_minervini = ta.get("is_minervini", False)
    minervini_score = ta.get("minervini_score", 0)

    # P/S using market cap from Polygon
    market_cap = details.get("market_cap", 0)
    ttm_rev = sum(qtr["revenue"] for qtr in quarters[:4])
    ps_ratio = round(market_cap / ttm_rev, 1) if ttm_rev > 0 and market_cap > 0 else 0

    price_vs_sma200 = round((price / sma200 - 1) * 100, 1) if sma200 else 0
    pct_from_52wh = round((price / week52h - 1) * 100, 1) if week52h else 0

    return f"""
<h1>Section 1 — Fundamental Analysis</h1>

<div class="grid3">
  <div class="metric-card">
    <div class="metric-label">TTM Revenue</div>
    <div class="metric-value">{_fmt_b(ttm_rev)}</div>
    <div class="metric-sub">Last 4 quarters combined</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">Latest Gross Margin</div>
    <div class="metric-value">{q['gross_margin']:.1f}%</div>
    <div class="metric-sub">{q['fiscal_year']} {q['period']}</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">Latest Net Margin</div>
    <div class="metric-value">{q['net_margin']:.1f}%</div>
    <div class="metric-sub">{q['fiscal_year']} {q['period']}</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">Price</div>
    <div class="metric-value">${price:.2f}</div>
    <div class="metric-sub">vs SMA200: <span class="{_signal(price_vs_sma200, 0)}">{price_vs_sma200:+.1f}%</span></div>
  </div>
  <div class="metric-card">
    <div class="metric-label">RSI</div>
    <div class="metric-value">{rsi:.1f}</div>
    <div class="metric-sub">{'Overbought' if rsi > 70 else 'Oversold' if rsi < 30 else 'Neutral'}</div>
  </div>
  <div class="metric-card">
    <div class="metric-label">Minervini</div>
    <div class="metric-value">{'✓ ' if is_minervini else '✗ '}{minervini_score}/8</div>
    <div class="metric-sub">SEPA Trend Template score</div>
  </div>
</div>

<h2>Quarterly Financial Trend</h2>
<table>
  <tr><th>Quarter</th><th>Revenue</th><th>Gross Margin</th><th>Op. Margin</th>
      <th>Net Margin</th><th>Op. Cash Flow</th><th>FCF Margin</th><th>EPS (dil.)</th><th>YoY Rev</th></tr>
  {''.join(rows)}
</table>

<div class="grid2" style="margin-top:14px">
  <div>
    <h2>Balance Sheet — {q['fiscal_year']} {q['period']}</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Total Assets</td><td>{_fmt_b(q['total_assets'])}</td></tr>
      <tr><td>Current Assets</td><td>{_fmt_b(q['current_assets'])}</td></tr>
      <tr><td>Current Liabilities</td><td>{_fmt_b(q['current_liabilities'])}</td></tr>
      <tr><td>Current Ratio</td><td class="{_signal(q['current_ratio'], 1.5)}">{q['current_ratio']:.2f}x</td></tr>
      <tr><td>Long-term Debt</td><td>{_fmt_b(q['long_term_debt'])}</td></tr>
      <tr><td>Total Equity</td><td>{_fmt_b(q['equity'])}</td></tr>
      <tr><td>Debt / Equity</td><td class="{_signal(-de, -1.0)}">{de:.2f}x</td></tr>
      <tr><td>Net Cash (est.)</td><td>{_fmt_b(net_cash)}</td></tr>
    </table>
  </div>
  <div>
    <h2>Technical Position (ta_daily)</h2>
    <table>
      <tr><th>Metric</th><th>Value</th></tr>
      <tr><td>Price</td><td>${price:.2f}</td></tr>
      <tr><td>SMA 50</td><td>{"$%.2f" % sma50 if sma50 else "—"}</td></tr>
      <tr><td>SMA 200</td><td>{"$%.2f" % sma200 if sma200 else "—"}</td></tr>
      <tr><td>Price vs SMA200</td><td class="{_signal(price_vs_sma200, 0)}">{price_vs_sma200:+.1f}%</td></tr>
      <tr><td>52-Week High</td><td>{"$%.2f" % week52h if week52h else "—"}</td></tr>
      <tr><td>% from 52W High</td><td class="{_signal(pct_from_52wh, -10)}">{pct_from_52wh:+.1f}%</td></tr>
      <tr><td>RSI</td><td>{rsi:.1f}</td></tr>
      <tr><td>RS vs SPY</td><td class="{_signal(rs_spy if rs_spy else 0, 0)}">{"%.1f" % rs_spy if rs_spy else "—"}</td></tr>
      <tr><td>P/S Ratio (TTM)</td><td>{ps_ratio:.1f}x</td></tr>
    </table>
  </div>
</div>

<div class="disclaimer" style="margin-top:10px">
  Analyst consensus not available (Benzinga plan upgrade required).
  Insider activity and red flags appear in Section 2.
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: Thesis (with SEC data)
# ─────────────────────────────────────────────────────────────────────────────

def build_thesis(
    ticker: str,
    quarters: list[dict],
    ta: dict,
    insider_result: Any,
    red_flags: list[Any],
    news: list[dict],
) -> str:
    # ── derive signals ──────────────────────────────────────────────────────
    q = quarters[0] if quarters else {}
    q_prev = quarters[1] if len(quarters) > 1 else {}

    gm_expanding = q.get("gross_margin", 0) > q_prev.get("gross_margin", 0) if q_prev else False
    fcf_margin = q.get("fcf_approx", 0) / q.get("revenue", 1) * 100 if q.get("revenue") else 0
    de = q.get("long_term_debt", 0) / q.get("equity", 1) if q.get("equity", 0) > 0 else 99

    # Insider sentiment
    insider_label = "NEUTRAL"
    insider_color = "neutral"
    if insider_result:
        s = getattr(insider_result, "overall_sentiment", "NEUTRAL")
        insider_label = str(s).upper()
        insider_color = "bullish" if "BULL" in insider_label else ("bearish" if "BEAR" in insider_label else "neutral")

    # Red flags summary
    critical_flags = [f for f in red_flags if getattr(f, "severity", "") == "CRITICAL"]
    high_flags = [f for f in red_flags if getattr(f, "severity", "") == "HIGH"]
    medium_flags = [f for f in red_flags if getattr(f, "severity", "") == "MEDIUM"]

    # Recommendation logic (conservative Raghu framework)
    if critical_flags or len(high_flags) >= 2:
        rec = "CAUTION / AVOID"
        rec_color = "bearish"
        confidence = "LOW"
    elif high_flags or (de > 2.0 and fcf_margin < 5):
        rec = "HOLD"
        rec_color = "neutral"
        confidence = "MEDIUM"
    elif fcf_margin > 15 and gm_expanding and not critical_flags:
        rec = "BUY"
        rec_color = "bullish"
        confidence = "HIGH" if fcf_margin > 25 else "MEDIUM"
    elif fcf_margin > 5 and de < 1.5:
        rec = "BUY"
        rec_color = "bullish"
        confidence = "MEDIUM"
    else:
        rec = "HOLD"
        rec_color = "neutral"
        confidence = "MEDIUM"

    # News sentiment
    avg_sentiment = sum(n["sentiment_score"] for n in news) / len(news) if news else 0
    sentiment_label = "Bullish" if avg_sentiment > 1 else ("Bearish" if avg_sentiment < -1 else "Neutral")
    sentiment_color = "bullish" if avg_sentiment > 1 else ("bearish" if avg_sentiment < -1 else "neutral")

    # Bull/bear bullets
    bulls = []
    bears = []

    if fcf_margin > 20:
        bulls.append(f"Exceptional FCF margin of {fcf_margin:.1f}% — self-funding growth without debt dependence.")
    elif fcf_margin > 10:
        bulls.append(f"Solid FCF margin of {fcf_margin:.1f}% — supports organic investment and shareholder returns.")

    if gm_expanding:
        bulls.append(f"Gross margin expanding ({q_prev.get('gross_margin', 0):.1f}% → {q.get('gross_margin', 0):.1f}%) — pricing power or mix improvement.")

    if de < 0.3:
        bulls.append(f"Fortress balance sheet: D/E of {de:.2f}x. Near-zero leverage = resilience to rate/credit cycles.")
    elif de < 0.8:
        bulls.append(f"Conservative leverage (D/E {de:.2f}x) — debt manageable relative to equity base.")

    if ta.get("is_minervini") and ta.get("minervini_score", 0) >= 6:
        bulls.append(f"Minervini SEPA pass ({ta['minervini_score']}/8) — confirms Stage 2 uptrend with institutional sponsorship.")

    if ta.get("rs_vs_spy", 0) and ta["rs_vs_spy"] > 1.0:
        bulls.append(f"RS vs SPY: {ta['rs_vs_spy']:.1f} — outperforming the market on a relative basis.")

    if avg_sentiment > 1.5:
        bulls.append(f"News flow is bullish (avg sentiment {avg_sentiment:+.2f}) — positive macro/corporate catalysts in recent weeks.")

    # Bears
    if q.get("gross_margin", 0) < 30:
        bears.append(f"Gross margin of {q.get('gross_margin', 0):.1f}% is below 30% — limited pricing power or commoditized business.")
    if not gm_expanding and q_prev:
        bears.append(f"Gross margin flat/contracting ({q_prev.get('gross_margin', 0):.1f}% → {q.get('gross_margin', 0):.1f}%) — watch for margin compression trend.")
    if de > 1.5:
        bears.append(f"Elevated leverage (D/E {de:.2f}x) — vulnerability if rates remain high or revenue disappoints.")
    if fcf_margin < 5 and q.get("revenue", 0) > 0:
        bears.append(f"Low FCF margin ({fcf_margin:.1f}%) — limited cash generation; heavy reinvestment or margin pressure.")
    if avg_sentiment < -1:
        bears.append(f"Bearish news sentiment ({avg_sentiment:+.2f}) — recent negative catalysts or macro headwinds in coverage.")
    if high_flags:
        bears.append(f"{len(high_flags)} HIGH-severity SEC red flag(s) detected — see Section 2 Red Flag detail below.")

    # Cap to 3 bulls, 2 bears
    while len(bulls) < 3:
        bulls.append("Requires additional data — check SEC filings and earnings transcript for further evidence.")
    bulls = bulls[:3]

    while len(bears) < 2:
        bears.append("Standard market risk: macro slowdown, competition, or execution miss could pressure estimates.")
    bears = bears[:2]

    bull_html = "".join(f"<li>{b}</li>" for b in bulls)
    bear_html = "".join(f"<li>{b}</li>" for b in bears)

    # Red flag summary
    rf_html = ""
    if critical_flags or high_flags or medium_flags:
        rf_items = []
        for f in critical_flags:
            rf_items.append(f"<li class='bearish'>🚨 CRITICAL: {getattr(f, 'flag_type', str(f))}</li>")
        for f in high_flags:
            rf_items.append(f"<li class='bearish'>⚠ HIGH: {getattr(f, 'flag_type', str(f))}</li>")
        for f in medium_flags:
            rf_items.append(f"<li class='neutral'>~ MEDIUM: {getattr(f, 'flag_type', str(f))}</li>")
        rf_html = f"""
<div class="red-flag-box">
  <h2>🚨 SEC Red Flags Detected</h2>
  <ul>{''.join(rf_items)}</ul>
</div>"""
    else:
        rf_html = """<div class="bullish-box"><h2>✅ Red Flag Scan: CLEAR</h2>
        <p>No NT filings, auditor changes, restatements, or going concern language detected.</p></div>"""

    # Insider html
    if insider_result:
        total_bought = getattr(insider_result, "total_bought_value", 0)
        total_sold = getattr(insider_result, "total_sold_value", 0)
        pct_10b5 = getattr(insider_result, "pct_via_10b5_1", 0)
        insider_html = f"""
<h2>Insider Activity (Last 90 Days)</h2>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Open Market Buys</td><td class="bullish">{_fmt_b(total_bought)}</td></tr>
  <tr><td>Total Sold</td><td>{_fmt_b(total_sold)}</td></tr>
  <tr><td>via 10b5-1 Plan</td><td>{pct_10b5:.0f}%</td></tr>
  <tr><td>Net Sentiment</td><td class="{insider_color}">{insider_label}</td></tr>
</table>"""
    else:
        insider_html = "<p style='color:#6b7280;font-size:12px'>Insider data unavailable — EDGAR timeout or no recent Form 4 filings.</p>"

    # News html
    if news:
        news_rows = "".join(
            f"<tr><td>{n['date']}</td><td>{n['summary'][:120]}</td>"
            f"<td class='{_signal(n['sentiment_score'], 1, -1)}'>{n['sentiment_score']:+.1f}</td></tr>"
            for n in news
        )
        news_html = f"""
<h2>News Sentiment (walter_openai.csv)</h2>
<p>Average sentiment: <span class="{sentiment_color}">{sentiment_label} ({avg_sentiment:+.2f})</span></p>
<table><tr><th>Date</th><th>Summary</th><th>Sentiment</th></tr>{news_rows}</table>"""
    else:
        news_html = "<p style='color:#6b7280;font-size:12px'>No recent news found in walter_openai.csv for this ticker.</p>"

    box_class = "bullish-box" if rec == "BUY" else ("red-flag-box" if "AVOID" in rec else "warning-box")

    return f"""
<h1>Section 2 — Thesis Validation & Risk Assessment</h1>

<div class="{box_class}">
  <h2>🎯 Verdict: <span class="{rec_color}">{rec}</span> | Confidence: {confidence}</h2>
  <p style="font-size:12px;margin-top:6px">
    FCF margin {fcf_margin:.1f}% | GM {'expanding ↑' if gm_expanding else 'flat/contracting ↓'} |
    D/E {de:.2f}x | Insider: <span class="{insider_color}">{insider_label}</span> |
    News: <span class="{sentiment_color}">{sentiment_label}</span>
  </p>
</div>

<div class="grid2">
  <div>
    <h2>🐂 Bull Case (3 Arguments)</h2>
    <ul>{bull_html}</ul>
  </div>
  <div>
    <h2>🐻 Bear Case / Key Risks (2 Arguments)</h2>
    <ul>{bear_html}</ul>
  </div>
</div>

{rf_html}
{insider_html}
{news_html}"""


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: Sector & Macro
# ─────────────────────────────────────────────────────────────────────────────

def build_sector_macro(ticker: str, details: dict, ta: dict) -> str:
    sector = details.get("sic_description", "Unknown sector")
    desc = details.get("description", "No description available.")
    rs_spy = ta.get("rs_vs_spy", 0) or 0
    rs_qqq = ta.get("rs_vs_qqq", 0) or 0

    return f"""
<h1>Section 3 — Sector & Macro View</h1>

<h2>Company Profile</h2>
<p><strong>Sector:</strong> {sector}</p>
<p style="font-size:12px;color:#374151">{desc}</p>

<div class="grid2" style="margin-top:12px">
  <div>
    <h2>Relative Strength</h2>
    <table>
      <tr><th>Benchmark</th><th>RS Score</th><th>Signal</th></tr>
      <tr><td>vs SPY (S&amp;P 500)</td>
          <td class="{'bullish' if rs_spy > 1 else 'bearish' if rs_spy < 0 else 'neutral'}">{rs_spy:.2f}</td>
          <td>{'Outperforming' if rs_spy > 1 else 'Underperforming' if rs_spy < 0 else 'Inline'}</td></tr>
      <tr><td>vs QQQ (Nasdaq)</td>
          <td class="{'bullish' if rs_qqq > 1 else 'bearish' if rs_qqq < 0 else 'neutral'}">{rs_qqq:.2f}</td>
          <td>{'Outperforming' if rs_qqq > 1 else 'Underperforming' if rs_qqq < 0 else 'Inline'}</td></tr>
    </table>
  </div>
  <div>
    <div class="info-box">
      <h2>Macro Context (April 2026)</h2>
      <ul style="font-size:12px">
        <li>Fed: Holding 4.25–4.50%, strong jobs data delays cuts</li>
        <li>Trade: U.S.-China tariff tensions elevated; H20/chip export controls active</li>
        <li>Oil: Brent $108–112, Iran/Hormuz structural floor (Energy tailwind)</li>
        <li>AI Capex: Hyperscalers committing $300B+ annually through 2027</li>
        <li>Full macro detail: <code>kb/macro/regime.md</code></li>
      </ul>
    </div>
  </div>
</div>

<p class="disclaimer">For deep sector analysis and competitive positioning, run
<code>/equity-research {ticker}</code> interactively to access web search and analyst reports.</p>"""


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: Catalyst Watch
# ─────────────────────────────────────────────────────────────────────────────

def build_catalysts(ticker: str, news: list[dict]) -> str:
    news_html = ""
    if news:
        news_rows = "".join(
            f"<tr><td>{n['date']}</td><td>{n['summary'][:130]}</td>"
            f"<td class='{_signal(n['sentiment_score'], 1, -1)}'>{n['sentiment_score']:+.1f}</td></tr>"
            for n in news[:5]
        )
        news_html = f"""
<h2>Recent News (walter_openai.csv)</h2>
<table><tr><th>Date</th><th>Summary</th><th>Sentiment</th></tr>{news_rows}</table>"""

    return f"""
<h1>Section 4 — Catalyst Watch</h1>

<div class="info-box">
  <h2>⚠️ Automated Catalyst Data Limitations</h2>
  <p style="font-size:12px">Earnings dates, guidance revisions, and product announcements require
  real-time data sources (Benzinga, Bloomberg) not available in offline mode.
  Use <code>/equity-research {ticker}</code> or check
  <code>kb/tickers/{ticker}/catalysts.md</code> for current catalyst tracking.</p>
</div>

{news_html}

<h2>Standard Catalyst Framework for {ticker}</h2>
<table>
  <tr><th>Timeframe</th><th>Catalyst Type</th><th>Where to Check</th></tr>
  <tr><td>0–3 months</td><td>Quarterly earnings, guidance update</td><td>Investor relations page, Benzinga</td></tr>
  <tr><td>3–12 months</td><td>Product launches, M&amp;A, regulatory decisions</td><td>8-K filings, press releases</td></tr>
  <tr><td>1–3 years</td><td>TAM expansion, secular trend positioning</td><td>10-K strategic outlook</td></tr>
</table>"""


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: Investment Summary
# ─────────────────────────────────────────────────────────────────────────────

def build_summary(
    ticker: str,
    quarters: list[dict],
    ta: dict,
    details: dict,
    insider_result: Any,
    red_flags: list[Any],
    news: list[dict],
) -> str:
    q = quarters[0] if quarters else {}
    q_prev = quarters[1] if len(quarters) > 1 else {}

    gm_expanding = q.get("gross_margin", 0) > q_prev.get("gross_margin", 0) if q_prev else False
    fcf_margin = q.get("fcf_approx", 0) / q.get("revenue", 1) * 100 if q.get("revenue") else 0
    de = q.get("long_term_debt", 0) / q.get("equity", 1) if q.get("equity", 0) > 0 else 99

    critical_flags = [f for f in red_flags if getattr(f, "severity", "") == "CRITICAL"]
    high_flags = [f for f in red_flags if getattr(f, "severity", "") == "HIGH"]

    if critical_flags or len(high_flags) >= 2:
        rec, confidence, risk = "CAUTION / AVOID", "LOW", "HIGH"
        box_class = "red-flag-box"
    elif high_flags or (de > 2.0 and fcf_margin < 5):
        rec, confidence, risk = "HOLD", "MEDIUM", "MEDIUM"
        box_class = "warning-box"
    elif fcf_margin > 15 and gm_expanding:
        rec, confidence, risk = "BUY", "HIGH" if fcf_margin > 25 else "MEDIUM", "LOW"
        box_class = "bullish-box"
    elif fcf_margin > 5 and de < 1.5:
        rec, confidence, risk = "BUY", "MEDIUM", "MEDIUM"
        box_class = "bullish-box"
    else:
        rec, confidence, risk = "HOLD", "MEDIUM", "MEDIUM"
        box_class = "warning-box"

    timeframe = "6–12 months" if rec == "BUY" else "12–18 months"

    market_cap = details.get("market_cap", 0)
    ttm_rev = sum(qtr["revenue"] for qtr in quarters[:4])
    ps_ratio = round(market_cap / ttm_rev, 1) if ttm_rev > 0 and market_cap > 0 else 0
    ttm_net_income = sum(qtr["net_income"] for qtr in quarters[:4])
    pe_ratio = round(market_cap / ttm_net_income, 1) if ttm_net_income > 0 and market_cap > 0 else 0

    return f"""
<h1>Section 5 — Investment Summary</h1>

<div class="{box_class}">
  <h2>Recommendation: {rec} | Confidence: {confidence} | Risk: {risk}</h2>
  <p style="font-size:12px;margin-top:4px">
    Timeframe: {timeframe} | P/S: {ps_ratio:.1f}x | P/E (TTM): {pe_ratio:.1f}x |
    FCF Margin: {fcf_margin:.1f}% | D/E: {de:.2f}x
  </p>
</div>

<h2>5-Bullet Investment Thesis</h2>
<ol>
  <li>Revenue quality: TTM revenue of {_fmt_b(ttm_rev)} with {q.get('gross_margin', 0):.1f}% gross margins
      {'(expanding ↑)' if gm_expanding else '(watch compression ↓)'}.</li>
  <li>Cash generation: FCF margin {fcf_margin:.1f}% — {'strong cash machine supporting reinvestment.' if fcf_margin > 15 else 'adequate but room for improvement.'}
  </li>
  <li>Balance sheet: D/E {de:.2f}x — {'fortress-grade balance sheet.' if de < 0.3 else 'conservative leverage.' if de < 1 else 'moderate leverage, monitor in rate environment.'}</li>
  <li>Technical posture: {'Minervini SEPA pass' if ta.get('is_minervini') else 'Not Minervini-qualified'}
      ({ta.get('minervini_score', 0)}/8 criteria) —
      price {'above' if (ta.get('close', 0) or 0) > (ta.get('sma200', 0) or 0) else 'below'} SMA200.</li>
  <li>Risk posture: {'No SEC red flags detected.' if not critical_flags and not high_flags else f'{len(critical_flags)} critical + {len(high_flags)} high-severity SEC flags — proceed with caution.'}</li>
</ol>

<div class="exec-summary" style="margin-top:14px">
  <h2>Quick-Reference Metrics</h2>
  <table>
    <tr><th>Metric</th><th>Value</th><th>Signal</th></tr>
    <tr><td>TTM Revenue</td><td>{_fmt_b(ttm_rev)}</td><td>—</td></tr>
    <tr><td>Gross Margin</td><td>{q.get('gross_margin', 0):.1f}%</td>
        <td class="{_signal(q.get('gross_margin', 0), 40)}">{'↑ Expanding' if gm_expanding else '→ Stable/↓'}</td></tr>
    <tr><td>FCF Margin</td><td>{fcf_margin:.1f}%</td>
        <td class="{_signal(fcf_margin, 15)}">{'Strong' if fcf_margin > 20 else 'Adequate' if fcf_margin > 8 else 'Weak'}</td></tr>
    <tr><td>D/E Ratio</td><td>{de:.2f}x</td>
        <td class="{_signal(-de, -1.5)}">{'Low leverage ✓' if de < 0.5 else 'Moderate' if de < 1.5 else 'High ⚠'}</td></tr>
    <tr><td>P/S Ratio</td><td>{ps_ratio:.1f}x</td><td>—</td></tr>
    <tr><td>P/E Ratio (TTM)</td><td>{pe_ratio:.1f}x</td><td>—</td></tr>
    <tr><td>SEC Red Flags</td><td>{len(critical_flags)} critical, {len(high_flags)} high</td>
        <td class="{'bearish' if critical_flags or high_flags else 'bullish'}">{'⚠ Investigate' if critical_flags or high_flags else '✓ Clean'}</td></tr>
  </table>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Assemble full report
# ─────────────────────────────────────────────────────────────────────────────

def build_report(
    ticker: str,
    quarters: list[dict],
    ta: dict,
    details: dict,
    insider_result: Any,
    red_flags: list[Any],
    news: list[dict],
    run_date: str | None = None,
) -> str:
    """Assemble all 5 sections into a complete self-contained HTML report."""
    today = run_date or str(date.today())
    company_name = details.get("name", ticker)
    exchange = details.get("primary_exchange", "NASDAQ")
    sector = details.get("sic_description", "Semiconductors")

    s1 = build_fundamentals(ticker, quarters, ta, details)
    s2 = build_thesis(ticker, quarters, ta, insider_result, red_flags, news)
    s3 = build_sector_macro(ticker, details, ta)
    s4 = build_catalysts(ticker, news)
    s5 = build_summary(ticker, quarters, ta, details, insider_result, red_flags, news)

    body = s1 + s2 + s3 + s4 + s5

    return HTML_TEMPLATE.format(
        ticker=ticker.upper(),
        company_name=company_name,
        exchange=exchange,
        sector=sector,
        date=today,
        css=CSS,
        body=body,
    )

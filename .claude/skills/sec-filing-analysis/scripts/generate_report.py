"""
generate_report.py — SEC Filing Analysis Report Generator

Orchestrator module that assembles all analysis components into a final
HTML or markdown report.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


# =============================================================================
# REPORT STRUCTURE
# =============================================================================

@dataclass
class FilingAnalysisReport:
    """Complete filing analysis report."""
    ticker: str
    report_date: str
    analysis_type: str  # 'pre_earnings', 'insider', 'red_flag', 'full', etc.
    
    # Section contents (HTML/markdown strings)
    executive_summary: str
    red_flags_section: Optional[str]
    insider_section: Optional[str]
    risk_factors_section: Optional[str]
    dso_section: Optional[str]
    institutional_section: Optional[str]
    upcoming_events_section: Optional[str]
    
    # Metadata
    sources: list[str]
    caveats: list[str]


# =============================================================================
# HTML TEMPLATE
# =============================================================================

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{ticker} SEC Filing Analysis - {date}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            max-width: 900px;
            margin: 0 auto;
            padding: 24px;
            background: #f9fafb;
        }}
        
        .title {{
            font-size: 28px;
            font-weight: 700;
            color: #1a365d;
            margin-bottom: 4px;
        }}
        
        .subtitle {{
            font-size: 14px;
            color: #1e40af;
            margin-bottom: 24px;
        }}
        
        h1 {{
            font-size: 18px;
            font-weight: 600;
            color: #1e40af;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 8px;
            margin: 24px 0 16px 0;
        }}
        
        h2 {{
            font-size: 14px;
            font-weight: 600;
            color: #374151;
            margin: 16px 0 8px 0;
        }}
        
        h3 {{
            font-size: 13px;
            font-weight: 600;
            color: #374151;
            margin: 12px 0 6px 0;
        }}
        
        p {{ margin-bottom: 12px; }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 12px 0;
            font-size: 13px;
        }}
        
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border: 1px solid #e5e7eb;
        }}
        
        th {{
            background: #4b5563;
            color: white;
            font-weight: 600;
        }}
        
        tr:nth-child(even) {{ background: #f9fafb; }}
        
        /* Signal boxes */
        .exec-summary {{
            background: #dbeafe;
            border-left: 5px solid #2563eb;
            padding: 16px;
            margin: 16px 0;
        }}
        
        .red-flag-box {{
            background: #fee2e2;
            border-left: 5px solid #dc2626;
            padding: 16px;
            margin: 16px 0;
        }}
        
        .warning-box {{
            background: #fef3c7;
            border-left: 5px solid #ea580c;
            padding: 16px;
            margin: 16px 0;
        }}
        
        .bullish-box {{
            background: #dcfce7;
            border-left: 5px solid #166534;
            padding: 16px;
            margin: 16px 0;
        }}
        
        .info-box {{
            background: #dbeafe;
            border: 2px solid #2563eb;
            border-radius: 8px;
            padding: 16px;
            margin: 16px 0;
        }}
        
        .disclaimer {{
            background: #f3f4f6;
            border-left: 5px solid #9ca3af;
            padding: 12px;
            margin: 24px 0;
            font-size: 12px;
            color: #6b7280;
        }}
        
        /* Inline signals */
        .bullish {{ color: #166534; font-weight: 600; }}
        .bearish {{ color: #dc2626; font-weight: 600; }}
        .mixed {{ color: #ea580c; font-weight: 600; }}
        
        /* Table row highlights */
        .tier1 {{ background: #dcfce7; }}
        .tier2 {{ background: #fef3c7; }}
        .tier3 {{ background: #fee2e2; }}
        
        ul, ol {{
            margin: 8px 0 8px 24px;
        }}
        
        li {{
            margin-bottom: 4px;
        }}
        
        .sources {{
            font-size: 12px;
            color: #6b7280;
            margin-top: 24px;
        }}
        
        .caveats {{
            font-size: 12px;
            color: #6b7280;
            background: #fef3c7;
            padding: 12px;
            border-radius: 4px;
            margin: 16px 0;
        }}
    </style>
</head>
<body>
    <div class="title">{ticker} SEC Filing Analysis</div>
    <div class="subtitle">{date} — {analysis_type}</div>
    
    {content}
    
    <div class="disclaimer">
        <strong>Disclaimer:</strong> This analysis is for informational purposes only and does not constitute 
        investment advice. SEC filings should be read in their entirety. Data may have 45-day lag (13F) or 
        2-day lag (Form 4). Always verify information directly from SEC EDGAR.
    </div>
</body>
</html>
"""


# =============================================================================
# SECTION BUILDERS
# =============================================================================

def build_executive_summary(ticker: str, key_findings: list[str], verdict: str) -> str:
    """
    Build executive summary section.
    
    Args:
        ticker: Stock ticker
        key_findings: List of key findings
        verdict: Overall verdict
        
    Returns:
        HTML string for executive summary
    """
    findings_html = "\n".join(f"<li>{f}</li>" for f in key_findings)
    
    return f"""
<div class="exec-summary">
    <h2>Executive Summary</h2>
    <ul>
        {findings_html}
    </ul>
    <p><strong>Verdict:</strong> {verdict}</p>
</div>
"""


def build_red_flag_section(flags: list, cleared: list) -> str:
    """
    Build red flags section HTML.
    
    Args:
        flags: List of detected red flags
        cleared: List of cleared checks
        
    Returns:
        HTML string for red flags section
    """
    if not flags:
        return f"""
<h1>🛡️ Red Flag Scan</h1>
<div class="bullish-box">
    <strong>✅ All Clear</strong>
    <p>No red flags detected in recent filings.</p>
    <p>Cleared checks: {', '.join(cleared)}</p>
</div>
"""
    
    flag_items = ""
    for flag in flags:
        severity_class = 'red-flag-box' if flag.get('severity') in ['CRITICAL', 'HIGH'] else 'warning-box'
        flag_items += f"""
<div class="{severity_class}">
    <strong>{flag.get('type', 'Unknown')}</strong> — {flag.get('severity', 'MEDIUM')}
    <p>{flag.get('description', '')}</p>
    <p><em>Action: {flag.get('action', 'Investigate')}</em></p>
</div>
"""
    
    return f"""
<h1>🚨 Red Flag Scan</h1>
{flag_items}
"""


def build_insider_section(transactions: list, summary: dict) -> str:
    """
    Build insider activity section HTML.
    
    Args:
        transactions: List of insider transactions
        summary: Summary dict with totals
        
    Returns:
        HTML string for insider section
    """
    # Build transaction table
    rows = ""
    for t in transactions[:15]:  # Limit to 15 most recent
        signal = '🟢' if t.get('code') == 'P' else ('🔴' if t.get('code') == 'S' else '⚪')
        rows += f"""
<tr>
    <td>{t.get('date', '')}</td>
    <td>{t.get('name', '')}</td>
    <td>{t.get('title', '')}</td>
    <td>{t.get('code', '')} {signal}</td>
    <td>${t.get('value', 0):,.0f}</td>
    <td>{'Yes' if t.get('is_10b5_1') else 'No'}</td>
</tr>
"""
    
    sentiment = summary.get('sentiment', 'NEUTRAL')
    sentiment_class = 'bullish' if sentiment == 'BULLISH' else ('bearish' if sentiment == 'BEARISH' else 'mixed')
    
    return f"""
<h1>📊 Insider Activity (Last 90 Days)</h1>

<table>
    <tr>
        <th>Metric</th>
        <th>Value</th>
    </tr>
    <tr>
        <td>Total Bought (Open Market)</td>
        <td class="bullish">${summary.get('total_bought', 0):,.0f}</td>
    </tr>
    <tr>
        <td>Total Sold</td>
        <td>${summary.get('total_sold', 0):,.0f}</td>
    </tr>
    <tr>
        <td>Net Insider Flow</td>
        <td class="{sentiment_class}">${summary.get('net_flow', 0):,.0f}</td>
    </tr>
    <tr>
        <td>Sales via 10b5-1</td>
        <td>{summary.get('pct_10b5_1', 0):.0f}%</td>
    </tr>
</table>

<h2>Recent Transactions</h2>
<table>
    <tr>
        <th>Date</th>
        <th>Insider</th>
        <th>Title</th>
        <th>Code</th>
        <th>Value</th>
        <th>10b5-1?</th>
    </tr>
    {rows}
</table>

<p><strong>Insider Sentiment:</strong> <span class="{sentiment_class}">{sentiment}</span> — {summary.get('rationale', '')}</p>
"""


def build_dso_section(quarters: list, analysis: dict) -> str:
    """
    Build DSO analysis section HTML.
    
    Args:
        quarters: List of quarterly data
        analysis: Analysis summary dict
        
    Returns:
        HTML string for DSO section
    """
    rows = ""
    for q in quarters:
        rows += f"""
<tr>
    <td>{q.get('period', '')}</td>
    <td>${q.get('ar', 0)/1e9:.1f}B</td>
    <td>${q.get('revenue', 0)/1e9:.1f}B</td>
    <td>{q.get('dso', 0):.1f}</td>
    <td>{q.get('ar_yoy', '')}</td>
    <td>{q.get('rev_yoy', '')}</td>
</tr>
"""
    
    risk = analysis.get('risk', 'LOW')
    risk_class = 'bearish' if risk == 'HIGH' else ('mixed' if risk == 'MEDIUM' else 'bullish')
    
    return f"""
<h1>📈 Balance Sheet: DSO Analysis</h1>

<table>
    <tr>
        <th>Period</th>
        <th>A/R (Net)</th>
        <th>Revenue</th>
        <th>DSO (Days)</th>
        <th>A/R YoY%</th>
        <th>Rev YoY%</th>
    </tr>
    {rows}
</table>

<div class="{'red-flag-box' if risk == 'HIGH' else 'info-box'}">
    <strong>DSO Trend:</strong> {analysis.get('trend', 'STABLE')}<br>
    <strong>A/R vs Revenue:</strong> {analysis.get('alignment', 'ALIGNED')}<br>
    <strong>Channel Stuffing Risk:</strong> <span class="{risk_class}">{risk}</span><br>
    <strong>Verdict:</strong> {analysis.get('verdict', '')}
</div>
"""


def build_upcoming_events_section(events: list) -> str:
    """
    Build upcoming events section HTML.
    
    Args:
        events: List of event dicts with date, type, description
        
    Returns:
        HTML string for events section
    """
    rows = ""
    for e in events:
        rows += f"""
<tr>
    <td>{e.get('date', '')}</td>
    <td>{e.get('type', '')}</td>
    <td>{e.get('description', '')}</td>
</tr>
"""
    
    return f"""
<h1>📅 Upcoming Events</h1>
<table>
    <tr>
        <th>Date</th>
        <th>Event Type</th>
        <th>Description</th>
    </tr>
    {rows}
</table>
"""


def build_sources_section(sources: list, caveats: list) -> str:
    """
    Build sources and caveats section.
    
    Args:
        sources: List of source strings
        caveats: List of caveat strings
        
    Returns:
        HTML string for sources section
    """
    source_items = "\n".join(f"<li>{s}</li>" for s in sources)
    caveat_items = "\n".join(f"<li>{c}</li>" for c in caveats)
    
    html = f"""
<h1>📚 Sources & Citations</h1>
<ul class="sources">
    {source_items}
</ul>
"""
    
    if caveats:
        html += f"""
<div class="caveats">
    <strong>⚠️ Caveats:</strong>
    <ul>
        {caveat_items}
    </ul>
</div>
"""
    
    return html


# =============================================================================
# REPORT ASSEMBLY
# =============================================================================

def assemble_report(report: FilingAnalysisReport) -> str:
    """
    Assemble all sections into final HTML report.
    
    Args:
        report: FilingAnalysisReport object
        
    Returns:
        Complete HTML string
    """
    sections = []
    
    # Add sections in order
    if report.executive_summary:
        sections.append(report.executive_summary)
    
    if report.red_flags_section:
        sections.append(report.red_flags_section)
    
    if report.insider_section:
        sections.append(report.insider_section)
    
    if report.risk_factors_section:
        sections.append(report.risk_factors_section)
    
    if report.dso_section:
        sections.append(report.dso_section)
    
    if report.institutional_section:
        sections.append(report.institutional_section)
    
    if report.upcoming_events_section:
        sections.append(report.upcoming_events_section)
    
    # Add sources
    sections.append(build_sources_section(report.sources, report.caveats))
    
    content = "\n".join(sections)
    
    return HTML_TEMPLATE.format(
        ticker=report.ticker,
        date=report.report_date,
        analysis_type=report.analysis_type.replace('_', ' ').title(),
        content=content
    )


def write_report(html: str, ticker: str, output_dir: str = "/media/SHARED/trade-data/sec-analysis/") -> str:
    """
    Write report to file.
    
    Args:
        html: HTML content
        ticker: Stock ticker
        output_dir: Output directory
        
    Returns:
        Path to written file
    """
    from datetime import datetime
    import os
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{ticker.lower()}_sec_analysis_{date_str}.html"
    filepath = os.path.join(output_dir, filename)
    
    os.makedirs(output_dir, exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return filepath

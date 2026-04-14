#!/usr/bin/env python3
"""
run_sec_analysis.py — Local CLI for SEC filing analysis.

Uses EDGAR REST API (no API key required) + existing analysis modules.

Usage:
    python3 run_sec_analysis.py --ticker NVDA --analysis red_flags
    python3 run_sec_analysis.py --ticker PLTR --analysis insider --days 90
    python3 run_sec_analysis.py --ticker CRM  --analysis dso --quarters 8
    python3 run_sec_analysis.py --ticker DDOG --analysis full
    python3 run_sec_analysis.py --ticker MSFT --analysis risk_factors
    python3 run_sec_analysis.py --ticker AXON --analysis institutional

Install:
    pip install requests
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# ── imports ───────────────────────────────────────────────────────────────────

def _load_module(name: str):
    import importlib.util
    _dir = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(name, os.path.join(_dir, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


try:
    from scripts.edgar_fetcher import (
        get_cik, get_recent_filings, get_filing_text,
        get_form4_transactions, get_financial_facts, get_filings_text,
    )
    from scripts.red_flag_scan import (
        scan_text_for_flags, assess_overall_risk,
        generate_scan_result, format_red_flag_report,
    )
    from scripts.insider_analysis import (
        calculate_net_sentiment, format_analysis_summary,
        format_transaction_table,
    )
    from scripts.dso_analysis import (
        analyze_dso_trend, format_dso_analysis,
    )
    from fundamentals import (
        run_fundamentals
    )
    from scripts.generate_report import build_executive_summary
except ImportError:
    _ef = _load_module("edgar_fetcher")
    _rf = _load_module("red_flag_scan")
    _ia = _load_module("insider_analysis")
    _da = _load_module("dso_analysis")
    _gr = _load_module("generate_report")
    _fn = _load_module("fundamentals")

    get_cik                  = _ef.get_cik
    get_recent_filings       = _ef.get_recent_filings
    get_filing_text          = _ef.get_filing_text
    get_form4_transactions   = _ef.get_form4_transactions
    get_financial_facts      = _ef.get_financial_facts
    get_filings_text         = _ef.get_filings_text

    scan_text_for_flags      = _rf.scan_text_for_flags
    assess_overall_risk      = _rf.assess_overall_risk
    generate_scan_result     = _rf.generate_scan_result
    format_red_flag_report   = _rf.format_red_flag_report

    calculate_net_sentiment  = _ia.calculate_net_sentiment
    format_analysis_summary  = _ia.format_analysis_summary
    format_transaction_table = _ia.format_transaction_table

    analyze_dso_trend        = _da.analyze_dso_trend
    format_dso_analysis      = _da.format_dso_analysis

    build_executive_summary  = _gr.build_executive_summary
    run_fundamentals = _fn.run_fundamentals


DEFAULT_OUTPUT_DIR = "/media/SHARED/trade-data/sec-analysis"


# ─────────────────────────────────────────────────────────────────────────────
# Analysis runners
# ─────────────────────────────────────────────────────────────────────────────

def run_red_flags(ticker: str) -> tuple[str, list]:
    """Scan recent 8-K, 10-K, 10-Q filings for red flags."""
    print(f"  Fetching recent 8-K / 10-K / 10-Q filings for {ticker}...")
    filings = get_filings_text(ticker, form_types=["8-K", "10-K", "10-Q"], n_per_type=5)

    all_flags = []
    checks = []
    for f in filings:
        flags = scan_text_for_flags(
            text=f["text"],
            ticker=ticker,
            filing_type=f["form"],
            filing_date=f["filed"],
        )
        all_flags.extend(flags)
        checks.append(f"{f['form']} ({f['filed']})")

    # Deduplicate: an ongoing investigation or impairment mentioned in every
    # filing is one issue, not N issues.  Keep only the most recent per type.
    seen = {}
    for f in sorted(all_flags, key=lambda x: x.filing_date, reverse=True):
        if f.flag_type not in seen:
            seen[f.flag_type] = f
    all_flags = list(seen.values())

    result = generate_scan_result(ticker, all_flags, checks)
    report_md = format_red_flag_report(result)

    print(f"  Red flag scan: {len(all_flags)} flags found | "
          f"Overall risk: {result.overall_risk}")
    return report_md, all_flags


def run_insider(ticker: str, days: int = 90) -> tuple[str, object]:
    """Fetch and analyze Form 4 insider transactions."""
    print(f"  Fetching Form 4 transactions for {ticker} (last {days} days)...")
    txns = get_form4_transactions(ticker, days=days)
    print(f"  Found {len(txns)} transactions")

    if not txns:
        return f"No Form 4 transactions found for {ticker} in the last {days} days.", None

    result = calculate_net_sentiment(txns, ticker=ticker)
    table  = format_transaction_table(txns)
    summary = format_analysis_summary(result)

    report_md = f"## {ticker} — Insider Transaction Analysis\n\n{table}\n\n{summary}"
    return report_md, result


def run_dso(ticker: str, quarters: int = 8) -> tuple[str, object]:
    """Fetch financial facts and run DSO trend analysis."""
    print(f"  Fetching XBRL financial data for {ticker} ({quarters} quarters)...")
    quarter_data = get_financial_facts(ticker, quarters=quarters)
    print(f"  Retrieved {len(quarter_data)} quarters of AR/Revenue data")

    if len(quarter_data) < 2:
        return f"Insufficient financial data for DSO analysis on {ticker}.", None

    result = analyze_dso_trend(quarter_data, ticker=ticker)
    report_md = format_dso_analysis(result)
    return report_md, result


def run_full(ticker: str, days: int = 90, quarters: int = 8) -> str:
    """Run all analyses and assemble a consolidated report."""
    print(f"\n{'='*60}")
    print(f"  FULL SEC ANALYSIS: {ticker}")
    print(f"{'='*60}\n")

    red_flag_md, flags = run_red_flags(ticker)
    insider_md, insider_result = run_insider(ticker, days=days)
    dso_md, dso_result = run_dso(ticker, quarters=quarters)
    f_md , f_res  = run_fundamentals(ticker)

    # Build key findings for executive summary
    key_findings = []
    if flags:
        critical = [f for f in flags if hasattr(f, "severity") and
                    str(f.severity).endswith("CRITICAL")]
        if critical:
            key_findings.append(f"{len(critical)} CRITICAL red flag(s) detected")
        key_findings.append(f"{len(flags)} total red flag(s) across recent filings")
    else:
        key_findings.append("No red flags detected in recent filings")

    if insider_result:
        key_findings.append(
            f"Insider sentiment: {getattr(insider_result, 'sentiment', 'UNKNOWN')} "
            f"(net flow ${getattr(insider_result, 'net_flow', 0)/1e6:.1f}M)"
        )

    if dso_result:
        key_findings.append(
            f"DSO trend: {getattr(dso_result, 'dso_trend', 'N/A')} | "
            f"Channel stuffing risk: {getattr(dso_result, 'channel_stuffing_risk', 'N/A')}"
        )

    # Determine overall risk from red flags first, then escalate based on DSO
    overall_risk = "LOW"
    if flags:
        _, overall_risk = assess_overall_risk(flags)

    # Bug 1 fix: escalate overall risk if DSO signals are worse than red flag risk
    if dso_result:
        dso_risk = getattr(dso_result, 'channel_stuffing_risk', 'LOW')
        risk_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        if risk_order.get(dso_risk, 0) > risk_order.get(overall_risk, 0):
            overall_risk = dso_risk

    exec_summary = build_executive_summary(ticker, key_findings, overall_risk)

    full_report = (
        f"# {ticker} — Full SEC Filing Analysis\n"
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
        f"{exec_summary}\n\n"
        f"---\n\n"
        f"## Red Flags\n\n{red_flag_md}\n\n"
        f"---\n\n"
        f"## Insider Activity\n\n{insider_md}\n\n"
        f"---\n\n"
        f"## DSO / Revenue Quality\n\n{dso_md}\n"
        f"---\n\n"
        f"## Fundamental Analysis\n\n{f_md}\n"
    )
    return full_report


# ─────────────────────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────────────────────

def save_report(content: str, ticker: str, analysis: str, output_dir: str) -> str:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = out / f"{ticker}_{analysis}_{date_str}.md"
    filename.write_text(content)
    return str(filename)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Local SEC filing analysis via EDGAR REST API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run_sec_analysis.py --ticker NVDA --analysis red_flags
  python3 run_sec_analysis.py --ticker PLTR --analysis insider --days 90
  python3 run_sec_analysis.py --ticker CRM  --analysis dso --quarters 8
  python3 run_sec_analysis.py --ticker DDOG --analysis full
        """,
    )
    parser.add_argument("--ticker", required=True,
                        help="Stock ticker (e.g. NVDA)")
    parser.add_argument(
        "--analysis",
        choices=["red_flags", "insider", "dso", "fundamentals", "full"],
        default="full",
        help="Analysis type (default: full)",
    )
    parser.add_argument("--days", type=int, default=90,
                        help="Lookback window for insider analysis (default: 90)")
    parser.add_argument("--quarters", type=int, default=8,
                        help="Quarters for DSO analysis (default: 8)")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--print", action="store_true",
                        help="Print report to stdout instead of saving")
    args = parser.parse_args()

    ticker = args.ticker.upper().strip()

    # Resolve CIK first to fail fast on bad tickers
    try:
        cik = get_cik(ticker)
        print(f"{ticker} → CIK {cik}")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Run analysis
    if args.analysis == "red_flags":
        report, _ = run_red_flags(ticker)
    elif args.analysis == "insider":
        report, _ = run_insider(ticker, days=args.days)
    elif args.analysis == "dso":
        report, _ = run_dso(ticker, quarters=args.quarters)
    elif args.analysis == "fundamentals":
        report, _ = run_fundamentals(ticker)
    else:  # full
        report = run_full(ticker, days=args.days, quarters=args.quarters)

    # Output
    if args.print:
        print("\n" + report)
    else:
        path = save_report(report, ticker, args.analysis, args.output_dir)
        print(f"\nReport saved: {path}")

        # Also print summary to terminal
        lines = report.split("\n")
        print("\n" + "\n".join(lines[:30]))
        if len(lines) > 30:
            print(f"  ... ({len(lines) - 30} more lines in report file)")


if __name__ == "__main__":
    main()
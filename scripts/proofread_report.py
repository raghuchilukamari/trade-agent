"""Proofread a market update HTML report against flow aggregator data.

Validates premium claims, trade counts, directions, ticker coverage,
and date accuracy by cross-referencing with flow_aggregator JSON output.

Usage:
    python scripts/proofread_report.py --report /path/to/report.html --data /path/to/flow.json
    python scripts/proofread_report.py --report /path/to/report.html --start 2026-03-23 --end 2026-03-27
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime


def load_flow_data(args):
    """Load flow data from JSON file or run aggregator."""
    if args.data:
        with open(args.data) as f:
            return json.load(f)
    if args.start and args.end:
        result = subprocess.run(
            ["python3", "-m", "scripts.flow_aggregator", "--start", args.start, "--end", args.end],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"FAIL: flow_aggregator failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        return json.loads(result.stdout)
    print("ERROR: provide --data or --start/--end", file=sys.stderr)
    sys.exit(1)


def extract_premiums_near_ticker(html, ticker):
    """Find the PRIMARY premium claim for a ticker in the report.

    Looks for the ticker's total premium in two reliable patterns:
    1. Table rows: <td><strong>TICKER</strong></td> ... <td><strong>$XX.XXM</strong></td>
    2. Inline bold: TICKER ... $XX.XXM (first match only, within same HTML element)

    Ignores individual trade amounts (like "$3.43M at 92% ask") that appear
    in justification text — those are sub-trade details, not total premium claims.
    """
    found = []

    # Pattern 1: Table row — most reliable. Ticker in one <td>, premium in next <td>
    #   Handles both <td><strong>$XX.XXM</strong></td> and <td>$XX.XXM</td>
    table_pat = re.compile(
        rf'<td><strong>{re.escape(ticker)}</strong></td>\s*<td>(?:<strong>)?\$([0-9.]+)(M|K|B)(?:</strong>)?</td>',
        re.IGNORECASE,
    )
    for m in table_pat.finditer(html):
        val = float(m.group(1))
        suffix = m.group(2).upper()
        found.append(val * {"M": 1e6, "K": 1e3, "B": 1e9}[suffix])

    # Pattern 2: Inline "TICKER $XX.XXM" or "TICKER ... $XX.XXM" within same line
    #   Only match the FIRST dollar amount (total premium), not sub-trade details
    if not found:
        inline_pat = re.compile(
            rf'\b{re.escape(ticker)}\b[^<\n]{{0,30}}?\$([0-9.]+)(M|K|B)',
            re.IGNORECASE,
        )
        m = inline_pat.search(html)
        if m:
            val = float(m.group(1))
            suffix = m.group(2).upper()
            found.append(val * {"M": 1e6, "K": 1e3, "B": 1e9}[suffix])

    return found


def check_day_of_week(html):
    """Verify the day of week in the report matches the date."""
    issues = []
    # Find patterns like "Monday, April 1, 2026"
    m = re.search(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+(\w+ \d+,\s*\d{4})', html)
    if m:
        claimed_day = m.group(1)
        date_str = m.group(2)
        try:
            parsed = datetime.strptime(date_str.replace(" ", " ").strip(), "%B %d, %Y")
            actual_day = parsed.strftime("%A")
            if claimed_day != actual_day:
                issues.append(f"FAIL: Day of week wrong — says {claimed_day} but {date_str} is a {actual_day}")
            else:
                issues.append(f"PASS: Day of week correct ({claimed_day}, {date_str})")
        except ValueError:
            issues.append(f"WARN: Could not parse date: {date_str}")
    else:
        issues.append("WARN: No day-of-week found in report")
    return issues


def check_premiums(html, data):
    """Check that ticker premiums in the report match flow data."""
    issues = []
    tolerance = 0.10  # 10% tolerance for rounding

    for ticker, info in data["tickers"].items():
        actual = info["total_premium"]
        found = extract_premiums_near_ticker(html, ticker)

        if not found and actual >= 5e6:
            issues.append(f"WARN: {ticker} ({info['total_premium_fmt']}) not found in report — top {list(data['tickers'].keys()).index(ticker) + 1} by premium")
            continue

        for claimed in found:
            if actual > 0:
                pct_diff = abs(claimed - actual) / actual
                if pct_diff > tolerance and abs(claimed - actual) > 1e6:
                    issues.append(
                        f"FAIL: {ticker} premium — report says ${claimed/1e6:.2f}M, "
                        f"actual is ${actual/1e6:.2f}M (off by ${abs(claimed-actual)/1e6:.1f}M, {pct_diff*100:.0f}%)"
                    )
                elif pct_diff <= tolerance:
                    issues.append(f"PASS: {ticker} premium ${actual/1e6:.2f}M")
                    break
    return issues


def check_total_premium(html, data):
    """Check total premium claim."""
    issues = []
    actual = data["meta"]["total_premium"]
    # Look for "total" near a dollar amount
    m = re.search(r'totale?d?\s+.{0,50}\$([0-9.]+)(M|B|K)', html, re.IGNORECASE)
    if m:
        val = float(m.group(1)) * {"M": 1e6, "K": 1e3, "B": 1e9}[m.group(2).upper()]
        if abs(val - actual) / actual > 0.15:
            issues.append(f"FAIL: Total premium — report ~${val/1e6:.0f}M, actual ${actual/1e6:.0f}M")
        else:
            issues.append(f"PASS: Total premium ~${actual/1e6:.0f}M")
    return issues


def check_trade_count(html, data):
    """Check trade count claim."""
    issues = []
    actual = data["meta"]["total_trades"]
    m = re.search(r'([0-9,]+)\s+(?:tracked\s+)?transactions?\b|([0-9,]+)\s+trades?\s+scored', html)
    if m:
        claimed = int((m.group(1) or m.group(2)).replace(",", ""))
        if claimed != actual:
            issues.append(f"FAIL: Trade count — report says {claimed}, actual {actual}")
        else:
            issues.append(f"PASS: Trade count {actual}")
    return issues


def check_walter_count(html, data):
    """Check walter enriched items count."""
    issues = []
    actual = data["meta"]["walter_news_count"]
    m = re.search(r'(\d+)\s+enriched\s+items?', html)
    if m:
        claimed = int(m.group(1))
        if claimed != actual:
            issues.append(f"FAIL: Walter count — report says {claimed}, actual {actual}")
        else:
            issues.append(f"PASS: Walter count {actual}")
    return issues


def check_directions(html, data):
    """Check that direction claims match flow data."""
    issues = []
    for ticker, info in list(data["tickers"].items())[:15]:
        actual_dir = info["direction"]
        # Check if the ticker is labeled with a contradicting direction
        # Find direction spans near ticker
        pattern = re.compile(
            rf'\b{re.escape(ticker)}\b.{{0,500}}class="(bullish|bearish|mixed)"[^>]*>([^<]+)',
            re.DOTALL | re.IGNORECASE,
        )
        for m in pattern.finditer(html):
            css_class = m.group(1).upper()
            label = m.group(2).strip().upper()
            if "BULLISH" in label and actual_dir == "BEARISH":
                issues.append(f"WARN: {ticker} labeled BULLISH in report but data says {actual_dir} ({info['bull_pct']}% bull)")
            elif "BEARISH" in label and actual_dir == "BULLISH":
                issues.append(f"WARN: {ticker} labeled BEARISH in report but data says {actual_dir} ({info['bull_pct']}% bull)")
            break  # first match is enough
    return issues


def check_no_internal_filenames(html):
    """Check that internal file names aren't exposed."""
    issues = []
    for name in ["walter_openai", "walter.csv", "sexy-flow", "golden-sweeps", "trady-flow", "sweeps.csv"]:
        if name.lower() in html.lower():
            issues.append(f"FAIL: Internal filename '{name}' found in report — should use 'institutional flow data' etc.")
    return issues


def check_goog_normalization(html, data):
    """Check that GOOG is not referenced separately from GOOGL (excluding URLs)."""
    issues = []
    # Strip URLs before checking
    text_only = re.sub(r'href="[^"]*"', '', html)
    if re.search(r'\bGOOG\b(?!L)', text_only):
        issues.append("WARN: 'GOOG' appears separately in report — should be normalized to GOOGL")
    else:
        issues.append("PASS: GOOG properly normalized to GOOGL")
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True, help="Path to HTML report")
    ap.add_argument("--data", help="Path to flow_aggregator JSON output")
    ap.add_argument("--start", help="Start date (runs aggregator if --data not given)")
    ap.add_argument("--end", help="End date")
    args = ap.parse_args()

    with open(args.report) as f:
        html = f.read()

    data = load_flow_data(args)

    print("=" * 70)
    print("MARKET UPDATE PROOFREADING REPORT")
    print("=" * 70)

    all_issues = []
    checks = [
        ("Date/Day Accuracy", check_day_of_week(html)),
        ("Trade Count", check_trade_count(html, data)),
        ("Total Premium", check_total_premium(html, data)),
        ("Walter News Count", check_walter_count(html, data)),
        ("Ticker Premiums", check_premiums(html, data)),
        ("Direction Labels", check_directions(html, data)),
        ("GOOG Normalization", check_goog_normalization(html, data)),
        ("Internal Filenames", check_no_internal_filenames(html)),
    ]

    fails = 0
    warns = 0
    passes = 0

    for section, issues in checks:
        print(f"\n--- {section} ---")
        for issue in issues:
            print(f"  {issue}")
            if issue.startswith("FAIL"):
                fails += 1
            elif issue.startswith("WARN"):
                warns += 1
            elif issue.startswith("PASS"):
                passes += 1

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {passes} passed, {warns} warnings, {fails} failures")
    if fails > 0:
        print("STATUS: NEEDS FIXES")
    elif warns > 0:
        print("STATUS: REVIEW WARNINGS")
    else:
        print("STATUS: ALL CLEAR")
    print("=" * 70)

    sys.exit(1 if fails > 0 else 0)


if __name__ == "__main__":
    main()

"""
red_flag_scan.py — SEC Filing Red Flag Detection

This module scans for warning signs in SEC filings including late filings,
auditor changes, restatements, and going concern language.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RedFlagSeverity(Enum):
    """Severity levels for red flags."""
    CRITICAL = ("🔴", "CRITICAL", "Immediate investigation required")
    HIGH = ("🔴", "HIGH", "Serious concern - deep investigation needed")
    MEDIUM = ("🟡", "MEDIUM", "Monitor closely")
    LOW = ("🟢", "LOW", "Note for awareness")
    CLEAR = ("✅", "CLEAR", "No issues found")


@dataclass
class RedFlag:
    """Single red flag detected in filings."""
    flag_type: str
    severity: RedFlagSeverity
    source_filing: str
    filing_date: str
    description: str
    action_required: str


@dataclass
class RedFlagScanResult:
    """Result of comprehensive red flag scan."""
    ticker: str
    scan_date: str
    flags: list[RedFlag]
    cleared_checks: list[str]
    overall_risk: str  # LOW, MEDIUM, HIGH, CRITICAL
    recommendation: str  # PROCEED, CAUTION, INVESTIGATE, AVOID


# =============================================================================
# RED FLAG DEFINITIONS
# =============================================================================

RED_FLAG_PATTERNS = {
    # ── NT/late filing: the form type IS the red flag ─────────────────────────
    'nt_filing': {
        'keywords': ['NT 10-K', 'NT 10-Q', 'notification of late filing', 'form 12b-25'],
        'filing_types': None,   # any filing
        'severity': RedFlagSeverity.HIGH,
        'description': 'Late filing notice - company unable to file on time',
        'action': 'Check reason code. "Internal controls" = very concerning.'
    },
    # ── 8-K Item 4.01 — only meaningful as an actual event in an 8-K ─────────
    'auditor_change': {
        'keywords': ['change in registrant\'s certifying accountant',
                     'auditor has resigned', 'auditor was dismissed',
                     'dismissed the registrant\'s independent'],
        'filing_types': ['8-K'],
        'severity': RedFlagSeverity.HIGH,
        'description': 'Auditor resignation or dismissal',
        'action': 'Read 4.01 carefully. "Disagreement" is worse than "fees".'
    },
    # ── 8-K Item 4.02 — actual non-reliance event ─────────────────────────────
    'restatement': {
        'keywords': ['non-reliance on previously issued financial statements',
                     'restatement of previously issued financial',
                     'previously filed financial statements should not be relied upon'],
        'filing_types': ['8-K'],
        'severity': RedFlagSeverity.HIGH,
        'description': 'Prior financials cannot be relied upon',
        'action': 'Determine what periods affected and materiality.'
    },
    # ── Going concern: require auditor-specific phrasing ──────────────────────
    'going_concern': {
        'keywords': ['raise substantial doubt about',
                     'substantial doubt exists about',
                     'ability to continue as a going concern'],
        'filing_types': None,
        'severity': RedFlagSeverity.CRITICAL,
        'description': 'Auditor doubts company can survive 12 months',
        'action': 'Review liquidity position immediately. Consider exit.'
    },
    # ── Material weakness: require disclosed-fact language (not risk boilerplate)
    # Removed generic noun phrases ("material weakness in internal control")
    # that fire on every 10-K risk-factor section. Kept only past/present-perfect
    # phrasing that asserts the weakness as an actual disclosed fact.
    'material_weakness': {
        'keywords': ['we have identified a material weakness',
                     'management identified a material weakness',
                     'management concluded that a material weakness exists',
                     'management determined that a material weakness'],
        'filing_types': None,
        'severity': RedFlagSeverity.MEDIUM,
        'description': 'Internal control weakness identified',
        'action': 'Check if remediated. Ongoing weakness is concerning.'
    },
    # ── Restructuring: 8-K Item 2.05 / actual announcement phrases ───────────
    'restructuring': {
        'keywords': ['announced a restructuring', 'workforce reduction of',
                     'reducing our workforce', 'elimination of positions'],
        'filing_types': None,
        'severity': RedFlagSeverity.MEDIUM,
        'description': 'Restructuring charges announced',
        'action': 'Assess if one-time or recurring. Check cash impact.'
    },
    # ── Impairment: new event-disclosure phrases only, 10-K/8-K only ─────────
    # Restricted to 10-K/8-K: quarterly filings routinely reference annual
    # impairments already captured in the 10-K (not new events).
    # "impairment of goodwill" removed — too generic, fires on risk-factor
    # boilerplate. Kept only past-tense event-disclosure phrases.
    'impairment': {
        'keywords': ['recorded a goodwill impairment charge',
                     'recognized a goodwill impairment',
                     'recorded an impairment charge of',
                     'recognized an impairment of'],
        'filing_types': ['10-K', '8-K'],
        'severity': RedFlagSeverity.MEDIUM,
        'description': 'Material asset impairment recorded',
        'action': 'Assess which assets and why. Overpaid for acquisition?'
    },
    # ── Executive departures: 8-K Item 5.02 only ─────────────────────────────
    'ceo_departure': {
        'keywords': ['resignation of', 'has resigned as chief executive',
                     'stepped down as chief executive', 'departure of the chief executive'],
        'filing_types': ['8-K'],
        'severity': RedFlagSeverity.MEDIUM,
        'description': 'CEO departure announced',
        'action': 'Check reason. Planned retirement vs sudden departure.'
    },
    'cfo_departure': {
        'keywords': ['has resigned as chief financial', 'stepped down as chief financial',
                     'departure of the chief financial'],
        'filing_types': ['8-K'],
        'severity': RedFlagSeverity.MEDIUM,
        'description': 'CFO departure announced',
        'action': 'CFO departures can signal accounting concerns.'
    },
    # ── Regulatory investigations: require specific disclosed-fact phrases ─────
    'sec_investigation': {
        'keywords': ['received a formal order of investigation from the sec',
                     'received a subpoena from the sec',
                     'sec has commenced an investigation',
                     'we are the subject of an sec investigation'],
        'filing_types': None,
        'severity': RedFlagSeverity.HIGH,
        'description': 'SEC investigation disclosed',
        'action': 'Monitor for Wells notice or enforcement action.'
    },
    'doj_investigation': {
        # Broad path: subpoena/grand jury (criminal) — any filing
        # Narrow path: active DOJ/AG antitrust/civil investigation disclosed in 10-K
        # (e.g. GOOGL's ongoing DOJ search/ad-tech cases)
        'keywords': ['received a subpoena from the department of justice',
                     'doj has commenced an investigation',
                     'subject of a grand jury investigation',
                     'criminal investigation by the department of justice',
                     'the department of justice filed a lawsuit',
                     'the department of justice has filed suit',
                     'the doj filed a complaint',
                     'subject to an investigation by the department of justice',
                     'department of justice (doj)',
                     'antitrust lawsuits',
                     'united states v.'],
        'filing_types': None,
        'severity': RedFlagSeverity.HIGH,
        'description': 'DOJ investigation or antitrust lawsuit disclosed',
        'action': 'Check for antitrust, fraud, or criminal exposure. Assess financial impact.'
    },
    # ── Covenant violation: require actual breach language, not risk disclosure
    'covenant_violation': {
        'keywords': ['we were not in compliance with', 'we failed to comply with',
                     'breach of covenant', 'event of default has occurred',
                     'received a waiver from our lenders'],
        'filing_types': None,
        'severity': RedFlagSeverity.HIGH,
        'description': 'Debt covenant violation',
        'action': 'Check if waiver obtained. May trigger acceleration.'
    },
    'liquidity_warning': {
        'keywords': ['working capital deficiency', 'may not have sufficient liquidity',
                     'may be unable to meet our obligations'],
        'filing_types': None,
        'severity': RedFlagSeverity.HIGH,
        'description': 'Liquidity warning in MD&A',
        'action': 'Review cash runway and debt maturities.'
    }
}


# =============================================================================
# SCANNING FUNCTIONS
# =============================================================================

def scan_text_for_flags(text: str, ticker: str = "", filing_type: str = "", filing_date: str = "") -> list[RedFlag]:
    """
    Scan filing text for red flag patterns.

    Patterns with a `filing_types` list are only evaluated against matching
    filing types (e.g. auditor_change only fires on 8-K). This prevents
    risk-factor boilerplate in 10-K/10-Q from generating false positives.
    """
    flags = []
    text_lower = text.lower()
    form = filing_type.upper().split()[0] if filing_type else ""

    for flag_type, pattern in RED_FLAG_PATTERNS.items():
        # Respect filing-type filter
        allowed = pattern.get('filing_types')
        if allowed is not None and form not in [f.upper() for f in allowed]:
            continue

        for keyword in pattern['keywords']:
            if keyword.lower() in text_lower:
                flags.append(RedFlag(
                    flag_type=flag_type,
                    severity=pattern['severity'],
                    source_filing=filing_type,
                    filing_date=filing_date,
                    description=pattern['description'],
                    action_required=pattern['action']
                ))
                break  # one flag per type per filing

    return flags


def build_search_queries_for_red_flags(ticker: str) -> list[str]:
    """
    Build web search queries to find potential red flags.
    
    Args:
        ticker: Stock ticker
        
    Returns:
        List of search queries
    """
    return [
        f"{ticker} NT 10-K NT 10-Q late filing SEC",
        f"{ticker} 8-K Item 4.01 auditor change",
        f"{ticker} 8-K Item 4.02 restatement non-reliance",
        f"{ticker} going concern audit opinion",
        f"{ticker} SEC investigation subpoena",
        f"{ticker} DOJ investigation",
        f"{ticker} material weakness internal controls",
        f"{ticker} covenant violation default",
    ]


def assess_overall_risk(flags: list[RedFlag]) -> tuple[str, str]:
    """
    Assess overall risk level based on detected flags.
    
    Args:
        flags: List of detected RedFlag objects
        
    Returns:
        Tuple of (risk_level, recommendation)
    """
    if not flags:
        return "LOW", "PROCEED"
    
    # Count by severity
    critical_count = sum(1 for f in flags if f.severity == RedFlagSeverity.CRITICAL)
    high_count = sum(1 for f in flags if f.severity == RedFlagSeverity.HIGH)
    medium_count = sum(1 for f in flags if f.severity == RedFlagSeverity.MEDIUM)
    
    if critical_count > 0:
        return "CRITICAL", "AVOID"
    elif high_count >= 2:
        return "HIGH", "AVOID"
    elif high_count == 1:
        return "HIGH", "INVESTIGATE FURTHER"
    elif medium_count >= 3:
        return "MEDIUM", "PROCEED WITH CAUTION"
    elif medium_count > 0:
        return "MEDIUM", "PROCEED WITH CAUTION"
    else:
        return "LOW", "PROCEED"


def generate_scan_result(ticker: str, flags: list[RedFlag], checks_performed: list[str]) -> RedFlagScanResult:
    """
    Generate comprehensive scan result.
    
    Args:
        ticker: Stock ticker
        flags: Detected red flags
        checks_performed: List of checks that were run
        
    Returns:
        RedFlagScanResult object
    """
    from datetime import datetime
    
    # Determine which flag types were NOT triggered (cleared)
    flagged_types = {f.flag_type for f in flags}
    cleared = sorted(set(RED_FLAG_PATTERNS.keys()) - flagged_types)
    
    overall_risk, recommendation = assess_overall_risk(flags)
    
    return RedFlagScanResult(
        ticker=ticker,
        scan_date=datetime.now().strftime("%Y-%m-%d"),
        flags=flags,
        cleared_checks=cleared,
        overall_risk=overall_risk,
        recommendation=recommendation
    )


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

def format_red_flag_report(result: RedFlagScanResult) -> str:
    """
    Format red flag scan as markdown report.
    
    Args:
        result: RedFlagScanResult object
        
    Returns:
        Markdown report string
    """
    risk_emoji = {
        'CRITICAL': '🔴',
        'HIGH': '🔴',
        'MEDIUM': '🟡',
        'LOW': '🟢'
    }.get(result.overall_risk, '⚪')
    
    report = f"""## {result.ticker} — Red Flag Scan
**Scan Date:** {result.scan_date}

"""
    
    # Group flags by severity
    critical_flags = [f for f in result.flags if f.severity == RedFlagSeverity.CRITICAL]
    high_flags = [f for f in result.flags if f.severity == RedFlagSeverity.HIGH]
    medium_flags = [f for f in result.flags if f.severity == RedFlagSeverity.MEDIUM]
    
    if critical_flags:
        report += "### 🔴 CRITICAL Flags\n"
        for f in critical_flags:
            report += f"- **{f.flag_type.upper()}** ({f.source_filing} - {f.filing_date})\n"
            report += f"  - {f.description}\n"
            report += f"  - ⚡ Action: {f.action_required}\n\n"
    
    if high_flags:
        report += "### 🔴 HIGH Flags\n"
        for f in high_flags:
            report += f"- **{f.flag_type.upper()}** ({f.source_filing} - {f.filing_date})\n"
            report += f"  - {f.description}\n"
            report += f"  - ⚡ Action: {f.action_required}\n\n"
    
    if medium_flags:
        report += "### 🟡 MEDIUM Flags\n"
        for f in medium_flags:
            report += f"- **{f.flag_type.upper()}** ({f.source_filing} - {f.filing_date})\n"
            report += f"  - {f.description}\n"
            report += f"  - ⚡ Action: {f.action_required}\n\n"
    
    if not result.flags:
        report += "### ✅ No Red Flags Detected\n\n"
    
    # Cleared checks
    if result.cleared_checks:
        report += "### ✅ Cleared Checks\n"
        for check in result.cleared_checks:
            check_name = check.replace('_', ' ').title()
            report += f"- {check_name}: Clear\n"
        report += "\n"
    
    # Overall assessment
    report += f"""### Overall Risk Assessment
| Metric | Value |
|--------|-------|
| Risk Level | {risk_emoji} {result.overall_risk} |
| Recommendation | {result.recommendation} |
"""
    
    return report


# =============================================================================
# STANDARD CHECKS LIST
# =============================================================================

STANDARD_CHECKS = [
    'nt_filing',
    'auditor_change',
    'restatement',
    'going_concern',
    'material_weakness',
    'restructuring',
    'impairment',
    'ceo_departure',
    'cfo_departure',
    'sec_investigation',
    'covenant_violation'
]

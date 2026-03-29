"""
dso_analysis.py — Days Sales Outstanding & Accounts Receivable Analysis

This module calculates DSO trends and identifies potential channel stuffing
or collection issues from 10-K/10-Q balance sheet data.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class QuarterlyData:
    """Single quarter's data for DSO calculation."""
    period: str  # e.g., "Q3 2025"
    date: str  # e.g., "2025-09-30"
    accounts_receivable: float  # Net A/R
    revenue: float  # Quarterly revenue
    allowance_for_doubtful: Optional[float] = None  # If available
    
    @property
    def dso(self) -> float:
        """Calculate Days Sales Outstanding."""
        if self.revenue <= 0:
            return 0
        return (self.accounts_receivable / self.revenue) * 91.25  # Avg days per quarter


@dataclass
class DSOAnalysisResult:
    """Result of DSO analysis."""
    ticker: str
    quarters: list[QuarterlyData]
    dso_trend: str  # RISING, FALLING, STABLE
    ar_vs_revenue_aligned: bool  # Is A/R growth aligned with revenue growth?
    channel_stuffing_risk: str  # LOW, MEDIUM, HIGH
    verdict: str
    details: str


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def calculate_dso(ar: float, revenue: float, days: float = 91.25) -> float:
    """
    Calculate Days Sales Outstanding.
    
    Formula: DSO = (Accounts Receivable / Revenue) × Days
    
    Args:
        ar: Accounts receivable (net)
        revenue: Revenue for the period
        days: Days in period (91 for quarterly, 365 for annual)
        
    Returns:
        DSO in days
    """
    if revenue <= 0:
        return 0
    return (ar / revenue) * days


def calculate_growth_rate(current: float, prior: float) -> float:
    """
    Calculate YoY growth rate as percentage.
    
    Args:
        current: Current period value
        prior: Prior period value
        
    Returns:
        Growth rate as percentage (e.g., 15.5 for 15.5%)
    """
    if prior <= 0:
        return 0
    return ((current - prior) / prior) * 100


def analyze_dso_trend(quarters: list[QuarterlyData], ticker: str = "") -> DSOAnalysisResult:
    """
    Analyze DSO trend across multiple quarters.
    
    Args:
        quarters: List of QuarterlyData, sorted chronologically (oldest first)
        
    Returns:
        DSOAnalysisResult with full analysis
    """
    if len(quarters) < 2:
        return DSOAnalysisResult(
            ticker=ticker,
            quarters=quarters,
            dso_trend="INSUFFICIENT_DATA",
            ar_vs_revenue_aligned=True,
            channel_stuffing_risk="UNKNOWN",
            verdict="Insufficient data for trend analysis",
            details="Need at least 2 quarters of data"
        )
    
    # Calculate DSO for each quarter
    dso_values = [q.dso for q in quarters]
    
    # Calculate trend
    first_half_avg = sum(dso_values[:len(dso_values)//2]) / (len(dso_values)//2)
    second_half_avg = sum(dso_values[len(dso_values)//2:]) / (len(dso_values) - len(dso_values)//2)
    
    dso_change = second_half_avg - first_half_avg
    
    if dso_change > 3:
        dso_trend = "RISING"
    elif dso_change < -3:
        dso_trend = "FALLING"
    else:
        dso_trend = "STABLE"
    
    # Compare A/R growth vs Revenue growth (YoY if 4+ quarters available)
    ar_vs_revenue_aligned = True
    ar_growth = 0
    rev_growth = 0
    
    if len(quarters) >= 4:
        # Compare latest quarter to same quarter last year
        current_q = quarters[-1]
        prior_year_q = quarters[-4] if len(quarters) >= 4 else quarters[0]
        
        ar_growth = calculate_growth_rate(current_q.accounts_receivable, prior_year_q.accounts_receivable)
        rev_growth = calculate_growth_rate(current_q.revenue, prior_year_q.revenue)
        
        # Red flag if A/R growing much faster than revenue
        if ar_growth > rev_growth + 10:  # 10% threshold
            ar_vs_revenue_aligned = False
    
    # Assess channel stuffing risk
    if not ar_vs_revenue_aligned and dso_trend == "RISING":
        channel_stuffing_risk = "HIGH"
        verdict = "⚠️ WARNING: A/R growing faster than revenue with rising DSO"
    elif dso_trend == "RISING" and dso_change > 5:
        channel_stuffing_risk = "MEDIUM"
        verdict = "Caution: DSO rising — may indicate collection issues or credit extension"
    elif not ar_vs_revenue_aligned:
        channel_stuffing_risk = "MEDIUM"
        verdict = "Caution: A/R growth outpacing revenue growth"
    else:
        channel_stuffing_risk = "LOW"
        verdict = "Healthy: DSO stable/falling, A/R aligned with revenue"
    
    # Build details
    details = f"""
DSO Trend: {dso_trend} (change: {dso_change:+.1f} days)
Latest DSO: {dso_values[-1]:.1f} days
A/R Growth (YoY): {ar_growth:+.1f}%
Revenue Growth (YoY): {rev_growth:+.1f}%
A/R vs Revenue: {'ALIGNED' if ar_vs_revenue_aligned else 'DIVERGENT'}
"""
    
    return DSOAnalysisResult(
        ticker="",
        quarters=quarters,
        dso_trend=dso_trend,
        ar_vs_revenue_aligned=ar_vs_revenue_aligned,
        channel_stuffing_risk=channel_stuffing_risk,
        verdict=verdict,
        details=details.strip()
    )


def check_allowance_trend(quarters: list[QuarterlyData]) -> Optional[str]:
    """
    Check trend in allowance for doubtful accounts.
    
    Args:
        quarters: List of QuarterlyData with allowance data
        
    Returns:
        Warning message if allowance is trending up, None otherwise
    """
    quarters_with_allowance = [q for q in quarters if q.allowance_for_doubtful is not None]
    
    if len(quarters_with_allowance) < 2:
        return None
    
    # Calculate allowance as % of A/R for each quarter
    allowance_pcts = [
        (q.allowance_for_doubtful / q.accounts_receivable * 100) 
        for q in quarters_with_allowance
        if q.accounts_receivable > 0
    ]
    
    if len(allowance_pcts) < 2:
        return None
    
    # Check if trending up
    if allowance_pcts[-1] > allowance_pcts[0] * 1.2:  # 20% increase
        return (
            f"⚠️ Allowance for doubtful accounts increased from "
            f"{allowance_pcts[0]:.1f}% to {allowance_pcts[-1]:.1f}% of A/R — "
            f"credit quality may be deteriorating"
        )
    
    return None


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

def format_dso_table(quarters: list[QuarterlyData]) -> str:
    """
    Format DSO data as markdown table.
    
    Args:
        quarters: List of QuarterlyData
        
    Returns:
        Markdown table string
    """
    if not quarters:
        return "No data available."
    
    lines = [
        "| Period | A/R (Net) | Revenue | DSO (Days) | A/R YoY% | Rev YoY% | Delta |",
        "|--------|-----------|---------|------------|----------|----------|-------|"
    ]
    
    for i, q in enumerate(quarters):
        ar_yoy = ""
        rev_yoy = ""
        delta = ""
        
        # Calculate YoY if we have prior year data
        if i >= 4:
            prior = quarters[i - 4]
            ar_growth = calculate_growth_rate(q.accounts_receivable, prior.accounts_receivable)
            rev_growth = calculate_growth_rate(q.revenue, prior.revenue)
            ar_yoy = f"{ar_growth:+.1f}%"
            rev_yoy = f"{rev_growth:+.1f}%"
            delta = f"{ar_growth - rev_growth:+.1f}%"
        
        lines.append(
            f"| {q.period} | ${q.accounts_receivable/1e9:.1f}B | "
            f"${q.revenue/1e9:.1f}B | {q.dso:.1f} | {ar_yoy} | {rev_yoy} | {delta} |"
        )
    
    return "\n".join(lines)


def format_dso_analysis(result: DSOAnalysisResult) -> str:
    """
    Format DSO analysis as markdown report.
    
    Args:
        result: DSOAnalysisResult object
        
    Returns:
        Markdown report string
    """
    risk_emoji = {
        'LOW': '🟢',
        'MEDIUM': '🟡',
        'HIGH': '🔴',
        'UNKNOWN': '⚪'
    }.get(result.channel_stuffing_risk, '⚪')
    
    trend_emoji = {
        'RISING': '📈',
        'FALLING': '📉',
        'STABLE': '➖',
        'INSUFFICIENT_DATA': '❓'
    }.get(result.dso_trend, '❓')
    
    report = f"""## Days Sales Outstanding Analysis

### Trend Data
{format_dso_table(result.quarters)}

### Summary
| Metric | Value |
|--------|-------|
| DSO Trend | {trend_emoji} {result.dso_trend} |
| A/R vs Revenue | {'✅ ALIGNED' if result.ar_vs_revenue_aligned else '⚠️ DIVERGENT'} |
| Channel Stuffing Risk | {risk_emoji} {result.channel_stuffing_risk} |

### Verdict
{result.verdict}

### Details
{result.details}
"""
    
    # Add allowance warning if applicable
    allowance_warning = check_allowance_trend(result.quarters)
    if allowance_warning:
        report += f"\n### Allowance Alert\n{allowance_warning}\n"
    
    return report


# =============================================================================
# INTERPRETATION GUIDE
# =============================================================================

DSO_INTERPRETATION = """
## DSO Interpretation Guide

### What DSO Tells You
- **DSO = How long it takes to collect payment** after a sale
- Rising DSO = customers taking longer to pay OR company extending more credit
- Falling DSO = faster collections OR tighter credit terms

### Warning Signs
| Signal | Interpretation |
|--------|----------------|
| DSO rising + Revenue flat | Collection problems |
| DSO rising + Revenue growing | May be OK (enterprise shift) or may be stuffing |
| A/R growth >> Revenue growth | 🚨 Potential channel stuffing |
| Allowance increasing | Credit quality deteriorating |

### Context Matters
- **SaaS/Enterprise companies** naturally have higher DSO (longer payment cycles)
- **Consumer companies** should have lower DSO
- **Seasonal businesses** may have quarterly DSO swings
- Compare to industry peers, not absolute numbers

### Red Flags to Escalate
1. A/R growth > Revenue growth for 3+ consecutive quarters
2. DSO rising > 10 days YoY without business model explanation
3. Allowance for doubtful accounts increasing as % of A/R
4. Quarter-end revenue spikes (check 10-Q footnotes)
"""

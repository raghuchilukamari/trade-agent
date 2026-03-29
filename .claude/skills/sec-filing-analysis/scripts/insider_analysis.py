"""
insider_analysis.py — Form 4 Parsing & Insider Transaction Analysis

This module analyzes insider transactions from Form 4 filings to determine
net insider sentiment and identify red flags like cluster selling.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum


class TransactionCode(Enum):
    """Form 4 transaction codes with signal classification."""
    P = ("Open market purchase", "BULLISH")
    S = ("Open market sale", "CONTEXT")
    M = ("Option exercise", "NEUTRAL")
    A = ("Grant/Award", "NEUTRAL")
    F = ("Tax withholding", "NEUTRAL")
    G = ("Gift", "NEUTRAL")
    J = ("Other acquisition/disposition", "CONTEXT")
    C = ("Conversion of derivative", "NEUTRAL")
    
    def __init__(self, description: str, signal: str):
        self.description = description
        self.signal = signal


@dataclass
class InsiderTransaction:
    """Single insider transaction from Form 4."""
    date: str
    insider_name: str
    insider_title: str
    transaction_code: str
    shares: float
    price: float
    value: float
    is_10b5_1: bool = False
    direct_indirect: str = "D"  # D = direct, I = indirect
    
    @property
    def code_info(self) -> TransactionCode:
        """Get transaction code enum."""
        try:
            return TransactionCode[self.transaction_code.upper()]
        except KeyError:
            return None
    
    @property
    def is_open_market_buy(self) -> bool:
        """True if this is a discretionary open-market purchase."""
        return self.transaction_code.upper() == 'P'
    
    @property
    def is_sale(self) -> bool:
        """True if this is a sale."""
        return self.transaction_code.upper() == 'S'


@dataclass
class InsiderAnalysisResult:
    """Result of insider transaction analysis."""
    ticker: str
    period_days: int
    total_bought_value: float
    total_sold_value: float
    net_flow: float
    transactions: list[InsiderTransaction]
    pct_via_10b5_1: float
    cluster_selling_detected: bool
    cluster_details: Optional[str]
    sentiment: str  # BULLISH, BEARISH, NEUTRAL
    confidence: str  # HIGH, MEDIUM, LOW
    rationale: str


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def classify_transaction(txn: InsiderTransaction) -> dict:
    """
    Classify a single transaction with signal and context.
    
    Args:
        txn: InsiderTransaction object
        
    Returns:
        Dict with classification details
    """
    code = txn.transaction_code.upper()
    
    if code == 'P':
        return {
            'signal': 'BULLISH',
            'weight': 1.0,
            'reason': 'Open market purchase - discretionary buy with own money'
        }
    
    if code == 'S':
        if txn.is_10b5_1:
            return {
                'signal': 'NEUTRAL',
                'weight': 0.0,
                'reason': '10b5-1 pre-programmed sale - not indicative of sentiment'
            }
        else:
            return {
                'signal': 'BEARISH',
                'weight': 0.7,
                'reason': 'Discretionary sale outside 10b5-1 plan'
            }
    
    if code == 'M':
        return {
            'signal': 'NEUTRAL',
            'weight': 0.0,
            'reason': 'Option exercise - routine compensation event'
        }
    
    if code in ('A', 'F', 'G'):
        return {
            'signal': 'NEUTRAL',
            'weight': 0.0,
            'reason': 'Grant, tax withholding, or gift - not trading signal'
        }
    
    return {
        'signal': 'UNKNOWN',
        'weight': 0.0,
        'reason': f'Unknown transaction code: {code}'
    }


def detect_cluster_selling(transactions: list[InsiderTransaction], 
                           window_days: int = 14,
                           min_insiders: int = 3) -> tuple[bool, Optional[str]]:
    """
    Detect cluster selling - multiple insiders selling within a short window.
    
    Args:
        transactions: List of transactions
        window_days: Window to check for clustering
        min_insiders: Minimum unique insiders to trigger cluster alert
        
    Returns:
        Tuple of (is_cluster_detected, details_string)
    """
    # Filter to sales only
    sales = [t for t in transactions if t.transaction_code.upper() == 'S']
    
    if len(sales) < min_insiders:
        return False, None
    
    # Sort by date
    sales_sorted = sorted(sales, key=lambda x: x.date)
    
    # Check each window
    for i, sale in enumerate(sales_sorted):
        sale_date = datetime.strptime(sale.date, "%Y-%m-%d")
        window_end = sale_date + timedelta(days=window_days)
        
        # Find all sales in window
        window_sales = [
            s for s in sales_sorted
            if sale_date <= datetime.strptime(s.date, "%Y-%m-%d") <= window_end
        ]
        
        # Count unique insiders
        unique_insiders = set(s.insider_name for s in window_sales)
        
        if len(unique_insiders) >= min_insiders:
            total_value = sum(s.value for s in window_sales)
            insider_list = ", ".join(unique_insiders)
            details = (
                f"CLUSTER DETECTED: {len(unique_insiders)} insiders sold "
                f"${total_value:,.0f} within {window_days} days "
                f"({sale.date} - {window_end.strftime('%Y-%m-%d')}). "
                f"Insiders: {insider_list}"
            )
            return True, details
    
    return False, None


def calculate_net_sentiment(transactions: list[InsiderTransaction], ticker: str = "") -> InsiderAnalysisResult:
    """
    Calculate overall insider sentiment from transactions.
    
    Args:
        transactions: List of InsiderTransaction objects
        
    Returns:
        InsiderAnalysisResult with full analysis
    """
    if not transactions:
        return InsiderAnalysisResult(
            ticker="",
            period_days=0,
            total_bought_value=0,
            total_sold_value=0,
            net_flow=0,
            transactions=[],
            pct_via_10b5_1=0,
            cluster_selling_detected=False,
            cluster_details=None,
            sentiment="NEUTRAL",
            confidence="LOW",
            rationale="No transactions found"
        )
    
    # Calculate totals
    buys = [t for t in transactions if t.transaction_code.upper() == 'P']
    sales = [t for t in transactions if t.transaction_code.upper() == 'S']
    
    total_bought = sum(t.value for t in buys)
    total_sold = sum(t.value for t in sales)
    net_flow = total_bought - total_sold
    
    # Calculate 10b5-1 percentage
    sales_10b5_1 = [t for t in sales if t.is_10b5_1]
    pct_10b5_1 = (sum(t.value for t in sales_10b5_1) / total_sold * 100) if total_sold > 0 else 0
    
    # Detect cluster selling
    cluster_detected, cluster_details = detect_cluster_selling(transactions)
    
    # Determine sentiment
    if total_bought > 0 and total_sold == 0:
        sentiment = "BULLISH"
        confidence = "HIGH"
        rationale = f"Pure buying: ${total_bought:,.0f} purchased, no sales"
    elif total_bought > total_sold:
        sentiment = "BULLISH"
        confidence = "MEDIUM"
        rationale = f"Net buying: ${total_bought:,.0f} bought vs ${total_sold:,.0f} sold"
    elif total_sold > total_bought and pct_10b5_1 > 80:
        sentiment = "NEUTRAL"
        confidence = "MEDIUM"
        rationale = f"Selling primarily via 10b5-1 ({pct_10b5_1:.0f}%) - pre-programmed, not indicative"
    elif total_sold > total_bought and cluster_detected:
        sentiment = "BEARISH"
        confidence = "HIGH"
        rationale = f"Cluster selling detected: {cluster_details}"
    elif total_sold > total_bought:
        sentiment = "BEARISH"
        confidence = "MEDIUM"
        rationale = f"Net selling: ${total_sold:,.0f} sold vs ${total_bought:,.0f} bought"
    else:
        sentiment = "NEUTRAL"
        confidence = "LOW"
        rationale = "Balanced or minimal activity"
    
    # Adjust confidence based on transaction count
    if len(transactions) < 3:
        confidence = "LOW"
    
    return InsiderAnalysisResult(
        ticker=ticker,
        period_days=90,  # Default
        total_bought_value=total_bought,
        total_sold_value=total_sold,
        net_flow=net_flow,
        transactions=transactions,
        pct_via_10b5_1=pct_10b5_1,
        cluster_selling_detected=cluster_detected,
        cluster_details=cluster_details,
        sentiment=sentiment,
        confidence=confidence,
        rationale=rationale
    )


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

def format_transaction_table(transactions: list[InsiderTransaction]) -> str:
    """
    Format transactions as a markdown table.
    
    Args:
        transactions: List of transactions
        
    Returns:
        Markdown table string
    """
    if not transactions:
        return "No transactions found."
    
    lines = [
        "| Date | Insider | Title | Code | Shares | Price | Value | 10b5-1? |",
        "|------|---------|-------|------|--------|-------|-------|---------|"
    ]
    
    for t in sorted(transactions, key=lambda x: x.date, reverse=True):
        code_signal = classify_transaction(t)['signal']
        signal_emoji = {'BULLISH': '🟢', 'BEARISH': '🔴', 'NEUTRAL': '⚪'}.get(code_signal, '⚪')
        
        lines.append(
            f"| {t.date} | {t.insider_name} | {t.insider_title} | "
            f"{t.transaction_code} {signal_emoji} | {t.shares:,.0f} | "
            f"${t.price:.2f} | ${t.value:,.0f} | {'Yes' if t.is_10b5_1 else 'No'} |"
        )
    
    return "\n".join(lines)


def format_analysis_summary(result: InsiderAnalysisResult) -> str:
    """
    Format analysis result as markdown summary.
    
    Args:
        result: InsiderAnalysisResult object
        
    Returns:
        Markdown summary string
    """
    sentiment_emoji = {
        'BULLISH': '📈',
        'BEARISH': '📉',
        'NEUTRAL': '➖'
    }.get(result.sentiment, '❓')
    
    summary = f"""## Insider Transaction Analysis (Last {result.period_days} Days)

### Summary
| Metric | Value |
|--------|-------|
| Total Bought (Open Market) | ${result.total_bought_value:,.0f} |
| Total Sold | ${result.total_sold_value:,.0f} |
| Net Insider Flow | ${result.net_flow:,.0f} |
| Sales via 10b5-1 | {result.pct_via_10b5_1:.0f}% |
| Cluster Selling | {'🔴 YES' if result.cluster_selling_detected else '✅ No'} |

### Verdict
**Insider Sentiment:** {sentiment_emoji} {result.sentiment}
**Confidence:** {result.confidence}
**Rationale:** {result.rationale}
"""
    
    if result.cluster_selling_detected:
        summary += f"\n### 🚨 Cluster Selling Alert\n{result.cluster_details}\n"
    
    return summary

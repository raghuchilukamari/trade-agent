"""
fetch_filings.py — SEC EDGAR Search Patterns & URL Builders

This module provides URL patterns and search strategies for fetching SEC filings.
Use with web_search and web_fetch tools.
"""

from typing import Optional
from datetime import datetime, timedelta


# =============================================================================
# EDGAR URL BUILDERS
# =============================================================================

def edgar_company_filings(ticker: str, filing_type: str = "", count: int = 40) -> str:
    """
    Build URL for company filings on EDGAR.
    
    Args:
        ticker: Stock ticker (e.g., "AAPL")
        filing_type: Specific form type (e.g., "10-K", "8-K", "4")
        count: Number of filings to return
        
    Returns:
        EDGAR URL for company filings
    """
    base = "https://www.sec.gov/cgi-bin/browse-edgar"
    params = f"?action=getcompany&CIK={ticker}&type={filing_type}&dateb=&owner=include&count={count}"
    return base + params


def edgar_full_text_search(query: str) -> str:
    """
    Build URL for EDGAR full-text search.
    
    Args:
        query: Search terms
        
    Returns:
        EDGAR full-text search URL
    """
    return f"https://efts.sec.gov/LATEST/search-index?q={query}"


# =============================================================================
# SEARCH QUERY PATTERNS
# =============================================================================

def build_search_queries(ticker: str, analysis_type: str) -> list[str]:
    """
    Build optimized search queries for different analysis types.
    
    Args:
        ticker: Stock ticker
        analysis_type: One of 'insider', '10k', '13f', 'red_flag', 'full'
        
    Returns:
        List of search queries to execute
    """
    queries = {
        'insider': [
            f"{ticker} Form 4 SEC EDGAR insider transactions",
            f"{ticker} insider buying selling 2025 2026",
            f"site:sec.gov {ticker} Form 4",
        ],
        '10k': [
            f"{ticker} 10-K annual report SEC filing",
            f"{ticker} risk factors Item 1A",
            f"site:sec.gov {ticker} 10-K",
        ],
        '10q': [
            f"{ticker} 10-Q quarterly report SEC",
            f"site:sec.gov {ticker} 10-Q",
        ],
        '8k': [
            f"{ticker} 8-K material event SEC",
            f"site:sec.gov {ticker} 8-K",
        ],
        '13f': [
            f"{ticker} 13F institutional holders",
            f"{ticker} institutional ownership hedge fund",
            f"{ticker} 13F-HR filings",
        ],
        '13d': [
            f"{ticker} Schedule 13D activist investor",
            f"{ticker} 13D SEC filing",
        ],
        'proxy': [
            f"{ticker} DEF 14A proxy statement",
            f"{ticker} executive compensation proxy",
        ],
        'red_flag': [
            f"{ticker} NT 10-K late filing",
            f"{ticker} NT 10-Q late filing",
            f"{ticker} 8-K auditor change Item 4.01",
            f"{ticker} 8-K restatement Item 4.02",
            f"{ticker} going concern audit opinion",
        ],
        'full': [
            f"{ticker} SEC EDGAR filings",
            f"{ticker} 10-K 10-Q 8-K SEC",
            f"{ticker} Form 4 insider transactions",
            f"{ticker} 13F institutional ownership",
            f"{ticker} DEF 14A proxy",
        ]
    }
    
    return queries.get(analysis_type, queries['full'])


# =============================================================================
# FILING DATE UTILITIES
# =============================================================================

def get_filing_deadlines(fiscal_year_end: str = "12-31") -> dict:
    """
    Calculate filing deadlines for a company.
    
    Args:
        fiscal_year_end: Month-day of fiscal year end (e.g., "12-31")
        
    Returns:
        Dict with filing types and their deadlines
    """
    return {
        '10-K': '60 days after fiscal year-end',
        '10-Q': '40 days after quarter-end',
        '8-K': '4 business days after event',
        'Form 4': '2 business days after transaction',
        '13F-HR': '45 days after quarter-end',
        'Schedule 13D': '10 days after crossing 5% ownership',
        'DEF 14A': '20+ days before annual meeting',
    }


def get_quarter_end_dates(year: int) -> list[str]:
    """
    Get quarter-end dates for a given year.
    
    Args:
        year: Calendar year
        
    Returns:
        List of quarter-end dates in YYYY-MM-DD format
    """
    return [
        f"{year}-03-31",  # Q1
        f"{year}-06-30",  # Q2
        f"{year}-09-30",  # Q3
        f"{year}-12-31",  # Q4
    ]


def calculate_13f_deadline(quarter_end: str) -> str:
    """
    Calculate 13F filing deadline (45 days after quarter-end).
    
    Args:
        quarter_end: Quarter-end date in YYYY-MM-DD format
        
    Returns:
        13F deadline in YYYY-MM-DD format
    """
    qe = datetime.strptime(quarter_end, "%Y-%m-%d")
    deadline = qe + timedelta(days=45)
    return deadline.strftime("%Y-%m-%d")


# =============================================================================
# THIRD-PARTY TOOL URLS
# =============================================================================

THIRD_PARTY_TOOLS = {
    'openinsider': {
        'url': 'https://openinsider.com/screener',
        'description': 'Form 4 screening and insider transaction aggregation',
        'best_for': 'Insider buying/selling patterns',
    },
    'whalewisdom': {
        'url': 'https://whalewisdom.com',
        'description': '13F analysis and institutional ownership tracking',
        'best_for': 'Hedge fund positions and changes',
    },
    'bamsec': {
        'url': 'https://bamsec.com',
        'description': 'Clean, readable SEC filing viewer',
        'best_for': 'Reading 10-K, 10-Q, 8-K filings',
    },
    'last10k': {
        'url': 'https://last10k.com',
        'description': '10-K comparison and diff tools',
        'best_for': 'YoY risk factor changes',
    },
    'sec_edgar': {
        'url': 'https://www.sec.gov/edgar/searchedgar/companysearch',
        'description': 'Official SEC EDGAR search',
        'best_for': 'Authoritative source for all filings',
    },
}


def get_tool_url(tool_name: str, ticker: Optional[str] = None) -> str:
    """
    Get URL for a third-party filing analysis tool.
    
    Args:
        tool_name: Name of tool (openinsider, whalewisdom, etc.)
        ticker: Optional ticker to include in URL
        
    Returns:
        URL for the tool
    """
    tool = THIRD_PARTY_TOOLS.get(tool_name.lower())
    if not tool:
        return ""
    
    base_url = tool['url']
    
    # Add ticker-specific paths where supported
    if ticker:
        if tool_name == 'openinsider':
            return f"https://openinsider.com/search?q={ticker}"
        elif tool_name == 'whalewisdom':
            return f"https://whalewisdom.com/stock/{ticker}"
        elif tool_name == 'bamsec':
            return f"https://bamsec.com/companies/{ticker}"
    
    return base_url


# =============================================================================
# FILING TYPE DETECTION
# =============================================================================

def classify_filing(filing_text: str) -> dict:
    """
    Classify a filing based on its content/title.
    
    Args:
        filing_text: Text of filing title or description
        
    Returns:
        Dict with filing_type, severity, and description
    """
    text_lower = filing_text.lower()
    
    # Red flag filings
    if 'nt 10-k' in text_lower or 'nt 10-q' in text_lower:
        return {
            'filing_type': 'NT',
            'severity': 'HIGH',
            'description': 'Late filing notice - potential accounting issues'
        }
    
    if '4.01' in text_lower or 'auditor' in text_lower:
        return {
            'filing_type': '8-K 4.01',
            'severity': 'HIGH',
            'description': 'Auditor change'
        }
    
    if '4.02' in text_lower or 'restatement' in text_lower or 'non-reliance' in text_lower:
        return {
            'filing_type': '8-K 4.02',
            'severity': 'HIGH',
            'description': 'Financial restatement'
        }
    
    # Standard filings
    if '10-k' in text_lower:
        return {'filing_type': '10-K', 'severity': 'INFO', 'description': 'Annual report'}
    
    if '10-q' in text_lower:
        return {'filing_type': '10-Q', 'severity': 'INFO', 'description': 'Quarterly report'}
    
    if '8-k' in text_lower:
        return {'filing_type': '8-K', 'severity': 'INFO', 'description': 'Current report'}
    
    if 'form 4' in text_lower or 'statement of changes' in text_lower:
        return {'filing_type': 'Form 4', 'severity': 'INFO', 'description': 'Insider transaction'}
    
    if '13f' in text_lower:
        return {'filing_type': '13F', 'severity': 'INFO', 'description': 'Institutional holdings'}
    
    if '13d' in text_lower:
        return {'filing_type': '13D', 'severity': 'MEDIUM', 'description': 'Activist position'}
    
    if 'def 14a' in text_lower or 'proxy' in text_lower:
        return {'filing_type': 'DEF 14A', 'severity': 'INFO', 'description': 'Proxy statement'}
    
    return {'filing_type': 'UNKNOWN', 'severity': 'INFO', 'description': 'Unknown filing type'}

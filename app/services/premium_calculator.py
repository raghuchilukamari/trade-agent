"""
Premium value parsing and formatting.
Handles $, M, K suffixes. Standardizes to USD and formatted millions.
"""

from __future__ import annotations

import re
from typing import Any


def parse_premium(val: Any) -> float:
    """
    Parse a premium string into USD float.

    Examples:
        "$4.33M" → 4_330_000.0
        "$500K"  → 500_000.0
        "$1,234" → 1_234.0
        "2.5M"   → 2_500_000.0
    """
    if val is None:
        return 0.0
    s = str(val).strip().replace("$", "").replace(",", "")
    if not s:
        return 0.0

    try:
        if s.upper().endswith("M"):
            return float(s[:-1]) * 1_000_000
        elif s.upper().endswith("K"):
            return float(s[:-1]) * 1_000
        elif s.upper().endswith("B"):
            return float(s[:-1]) * 1_000_000_000
        else:
            return float(s)
    except (ValueError, TypeError):
        return 0.0


def format_premium_m(usd: float | None) -> str:
    """Format a USD amount to millions string (e.g., '$4.33M')."""
    if not usd or usd == 0:
        return "$0"
    if abs(usd) >= 1_000_000:
        return f"${usd / 1_000_000:.2f}M"
    elif abs(usd) >= 1_000:
        return f"${usd / 1_000:.1f}K"
    else:
        return f"${usd:,.0f}"


def premium_significance(usd: float) -> str:
    """Classify premium significance per the trading system rules."""
    if usd >= 5_000_000:
        return "MASSIVE"
    elif usd >= 3_000_000:
        return "MAJOR"
    elif usd >= 1_000_000:
        return "SIGNIFICANT"
    elif usd >= 500_000:
        return "NOTABLE"
    else:
        return "MINOR"

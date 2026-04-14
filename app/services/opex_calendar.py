"""
OPEX Calendar & Mechanics — calculates OPEX dates, phases, and gamma context.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

# ── 2026 OPEX Dates ──────────────────────────────────────────────────────────

MONTHLY_OPEX_2026 = {
    1: date(2026, 1, 16),
    2: date(2026, 2, 20),
    3: date(2026, 3, 20),   # Quad Witching
    4: date(2026, 4, 17),
    5: date(2026, 5, 15),
    6: date(2026, 6, 19),   # Quad Witching
    7: date(2026, 7, 17),
    8: date(2026, 8, 21),
    9: date(2026, 9, 18),   # Quad Witching
    10: date(2026, 10, 16),
    11: date(2026, 11, 20),
    12: date(2026, 12, 18),  # Quad Witching
}

QUAD_WITCHING_MONTHS = {3, 6, 9, 12}

MARKET_HOLIDAYS_2026 = [
    date(2026, 1, 1),    # New Year
    date(2026, 1, 19),   # MLK
    date(2026, 2, 16),   # Presidents
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),   # Memorial
    date(2026, 6, 19),   # Juneteenth
    date(2026, 7, 3),    # Independence
    date(2026, 9, 7),    # Labor Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
]


def get_third_friday(year: int, month: int) -> date:
    """Calculate the 3rd Friday of a given month."""
    # Find the first day of the month
    first = date(year, month, 1)
    # Find first Friday
    days_until_friday = (4 - first.weekday()) % 7
    first_friday = first + timedelta(days=days_until_friday)
    # Third Friday is 14 days later
    return first_friday + timedelta(days=14)


def get_next_monthly_opex(from_date: date) -> date:
    """Get the next monthly OPEX date from a given date."""
    year = from_date.year
    for month in range(from_date.month, 13):
        opex = MONTHLY_OPEX_2026.get(month) or get_third_friday(year, month)
        if opex >= from_date:
            return opex
    # Next year
    return get_third_friday(year + 1, 1)


def get_vix_expiration(monthly_opex: date) -> date:
    """VIX expires on Wednesday before monthly OPEX (2 days before)."""
    return monthly_opex - timedelta(days=2)


def get_opex_phase(
    current_date: date, next_opex: date
) -> tuple[Literal["pre_opex", "opex_week", "post_opex"], str]:
    """
    Determine current OPEX phase.

    Returns: (phase_key, phase_label)
    """
    days_to_opex = (next_opex - current_date).days

    if days_to_opex < 0:
        # Post-OPEX (Monday after expiration)
        return "post_opex", "Post-OPEX (Gamma Release)"
    elif days_to_opex <= 5:
        return "opex_week", f"OPEX Week ({days_to_opex} days)"
    elif days_to_opex <= 10:
        return "pre_opex", f"Pre-OPEX ({days_to_opex} days)"
    else:
        return "pre_opex", f"Pre-OPEX ({days_to_opex} days away)"


def get_full_opex_context(current_date: date) -> dict:
    """
    Get complete OPEX context for a given date.

    Returns dict with all OPEX-related information for the analysis.
    """
    next_opex = get_next_monthly_opex(current_date)
    days_to_opex = (next_opex - current_date).days
    phase_key, phase_label = get_opex_phase(current_date, next_opex)
    vix_exp = get_vix_expiration(next_opex)
    vix_days = (vix_exp - current_date).days
    is_quad = next_opex.month in QUAD_WITCHING_MONTHS

    implications = get_phase_implications(phase_key, days_to_opex, is_quad)

    return {
        "next_monthly_opex": next_opex.isoformat(),
        "days_to_opex": days_to_opex,
        "current_phase": phase_key,
        "phase_label": phase_label,
        "phase_implications": implications,
        "vix_expiration": vix_exp.isoformat(),
        "vix_days_away": vix_days,
        "is_quad_witching": is_quad,
        "is_market_holiday": current_date in MARKET_HOLIDAYS_2026,
        "gamma_assessment": get_gamma_assessment(phase_key, days_to_opex, is_quad),
    }


def get_phase_implications(
    phase: str, days: int, is_quad: bool
) -> list[str]:
    """Get trading implications for the current OPEX phase."""
    implications = []

    if phase == "post_opex":
        implications.extend([
            "Gamma release in effect — hedging positions unwinding",
            "Watch for directional breakouts from pinned levels",
            "Best window for new directional positions",
            "Expect increased volatility as gamma constraints lift",
        ])
    elif phase == "opex_week":
        implications.extend([
            "Maximum gamma pinning — price likely range-bound near high-OI strikes",
            "Avoid fighting the pin with directional bets",
            "Dealer hedging at maximum intensity",
            "Consider reducing position sizes",
        ])
        if is_quad:
            implications.append("⚠️ QUAD WITCHING — expect EXTREME volume and volatility")
    elif phase == "pre_opex":
        if days <= 5:
            implications.extend([
                "Gamma effects intensifying — identify high-OI strikes",
                "Reduce directional bets near key strike levels",
                "Watch for institutional roll activity",
            ])
        else:
            implications.extend([
                "Early pre-OPEX — time to identify key OI levels",
                "Normal gamma environment — directional trades okay with awareness",
            ])

    return implications


def get_gamma_assessment(phase: str, days: int, is_quad: bool) -> str:
    """Get a text assessment of current gamma environment."""
    if phase == "post_opex":
        return "LOW — Gamma release, reduced hedging pressure. Favorable for directional trades."
    elif phase == "opex_week":
        if is_quad:
            return "EXTREME — Quad Witching week. Maximum gamma pinning + record volume expected."
        return "HIGH — Peak gamma pinning. Price gravitating toward max-pain strikes."
    elif days <= 5:
        return "ELEVATED — Gamma effects building. Hedging flows becoming dominant."
    elif days <= 10:
        return "MODERATE — Early gamma buildup. Monitor high-OI strikes."
    else:
        return "NORMAL — Minimal OPEX-related gamma effects."

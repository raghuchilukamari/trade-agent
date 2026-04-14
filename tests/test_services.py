"""
Tests for core trading analysis services.
"""

import pytest
from datetime import date


class TestPremiumCalculator:
    def test_parse_millions(self):
        from app.services.premium_calculator import parse_premium
        assert parse_premium("$4.33M") == 4_330_000.0
        assert parse_premium("2.5M") == 2_500_000.0

    def test_parse_thousands(self):
        from app.services.premium_calculator import parse_premium
        assert parse_premium("$500K") == 500_000.0
        assert parse_premium("250K") == 250_000.0

    def test_parse_raw(self):
        from app.services.premium_calculator import parse_premium
        assert parse_premium("$1,234") == 1234.0
        assert parse_premium("5000") == 5000.0

    def test_parse_edge_cases(self):
        from app.services.premium_calculator import parse_premium
        assert parse_premium(None) == 0.0
        assert parse_premium("") == 0.0
        assert parse_premium("abc") == 0.0

    def test_format_millions(self):
        from app.services.premium_calculator import format_premium_m
        assert format_premium_m(4_330_000) == "$4.33M"
        assert format_premium_m(500_000) == "$500.0K"
        assert format_premium_m(0) == "$0"

    def test_significance(self):
        from app.services.premium_calculator import premium_significance
        assert premium_significance(6_000_000) == "MASSIVE"
        assert premium_significance(4_000_000) == "MAJOR"
        assert premium_significance(2_000_000) == "SIGNIFICANT"
        assert premium_significance(750_000) == "NOTABLE"
        assert premium_significance(100_000) == "MINOR"


class TestDeepITMRule:
    def test_deep_itm_put_bullish(self):
        """Deep ITM put (>15% ITM) should be classified as SOLD = BULLISH."""
        from app.services.deep_itm import check_deep_itm
        result = check_deep_itm("INTC", 30.0, 24.0, "PUT")
        assert result.classification == "DEEP_ITM_SOLD"
        assert result.signal == "BULLISH"

    def test_near_atm_put_bearish(self):
        """Near-ATM put (within 5%) should be genuine BEARISH."""
        from app.services.deep_itm import check_deep_itm
        result = check_deep_itm("AAPL", 150.0, 148.0, "PUT")
        assert result.classification == "NEAR_ATM"
        assert result.signal == "BEARISH"

    def test_otm_put_hedge(self):
        """OTM put (>5% below price) should be classified as HEDGE."""
        from app.services.deep_itm import check_deep_itm
        result = check_deep_itm("NVDA", 100.0, 130.0, "PUT")
        assert result.classification == "OTM_HEDGE"
        assert result.signal == "HEDGE"

    def test_call_always_bullish(self):
        from app.services.deep_itm import check_deep_itm
        result = check_deep_itm("MSFT", 400.0, 420.0, "CALL")
        assert result.signal == "BULLISH"

    def test_zero_price(self):
        from app.services.deep_itm import check_deep_itm
        result = check_deep_itm("X", 50.0, 0, "PUT")
        assert result.classification == "UNKNOWN"


class TestOPEXCalendar:
    def test_next_opex_from_jan(self):
        from app.services.opex_calendar import get_next_monthly_opex
        d = date(2026, 1, 5)
        opex = get_next_monthly_opex(d)
        assert opex == date(2026, 1, 16)

    def test_next_opex_after_jan_opex(self):
        from app.services.opex_calendar import get_next_monthly_opex
        d = date(2026, 1, 17)
        opex = get_next_monthly_opex(d)
        assert opex == date(2026, 2, 20)

    def test_opex_phase_week(self):
        from app.services.opex_calendar import get_opex_phase
        phase, label = get_opex_phase(date(2026, 1, 14), date(2026, 1, 16))
        assert phase == "opex_week"

    def test_opex_phase_post(self):
        from app.services.opex_calendar import get_opex_phase
        phase, label = get_opex_phase(date(2026, 1, 19), date(2026, 1, 16))
        assert phase == "post_opex"

    def test_quad_witching(self):
        from app.services.opex_calendar import get_full_opex_context
        ctx = get_full_opex_context(date(2026, 3, 15))
        assert ctx["is_quad_witching"] is True

    def test_vix_expiration(self):
        from app.services.opex_calendar import get_vix_expiration
        vix = get_vix_expiration(date(2026, 1, 16))
        assert vix == date(2026, 1, 14)



class TestFlowParser:
    def test_normalize_symbol(self):
        from app.services.flow_parser_v0 import normalize_symbol
        assert normalize_symbol("GOOG") == "GOOGL"
        assert normalize_symbol("BRK.A") == "BRK.B"
        assert normalize_symbol("NVDA") == "NVDA"

    def test_parse_tickers(self):
        from app.services.flow_parser_v0 import _parse_tickers
        result = _parse_tickers("$NVDA, $AMD, $GOOG")
        assert "NVDA" in result
        assert "AMD" in result
        assert "GOOGL" in result  # Normalized
        assert "GOOG" not in result

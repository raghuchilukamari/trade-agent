
I"""
Deep ITM Rule — CRITICAL analysis rule for proper put interpretation.

Rule: If a put strike is >15-20% in-the-money, treat it as SOLD (bullish), not bought.

Deep ITM puts are often SOLD to collect premium, which is actually BULLISH positioning.
This module provides the check and annotates flow entries accordingly.
"""

from __future__ import annotations

from typing import Any, Literal


class DeepITMResult:
    """Result of a Deep ITM analysis."""

    def __init__(
        self,
        symbol: str,
        strike: float,
        current_price: float,
        call_put: str,
        itm_pct: float,
        classification: Literal["DEEP_ITM_SOLD", "NEAR_ATM", "OTM_HEDGE", "CALL", "UNKNOWN"],
        signal: Literal["BULLISH", "BEARISH", "HEDGE", "NEUTRAL"],
    ):
        self.symbol = symbol
        self.strike = strike
        self.current_price = current_price
        self.call_put = call_put
        self.itm_pct = itm_pct
        self.classification = classification
        self.signal = signal

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strike": self.strike,
            "current_price": self.current_price,
            "call_put": self.call_put,
            "itm_pct": round(self.itm_pct, 2),
            "classification": self.classification,
            "signal": self.signal,
        }


def check_deep_itm(
    symbol: str,
    strike: float,
    current_price: float,
    call_put: str,
    deep_threshold: float = 0.15,  # 15%
) -> DeepITMResult:
    """
    Apply the Deep ITM Rule to a single flow entry.

    Args:
        symbol: Ticker symbol
        strike: Option strike price
        current_price: Current stock price
        call_put: "CALL" or "PUT"
        deep_threshold: Threshold for deep ITM classification (default 15%)

    Returns:
        DeepITMResult with classification and signal

    Logic for PUTs:
        - Strike > price by >15%: Deep ITM → likely SOLD → BULLISH
        - Strike within 5% of price: Near ATM → genuine bearish
        - Strike < price by 5-15%: OTM → hedging
    """
    if current_price <= 0 or strike <= 0:
        return DeepITMResult(
            symbol=symbol, strike=strike, current_price=current_price,
            call_put=call_put, itm_pct=0.0,
            classification="UNKNOWN", signal="NEUTRAL",
        )

    if call_put.upper() == "PUT":
        # For puts: ITM when strike > price
        # We check how deep ITM: (strike - price) / price
        itm_pct = (strike - current_price) / current_price

        if itm_pct > deep_threshold:
            # Deep ITM put → likely SOLD → BULLISH
            return DeepITMResult(
                symbol=symbol, strike=strike, current_price=current_price,
                call_put="PUT", itm_pct=itm_pct,
                classification="DEEP_ITM_SOLD", signal="BULLISH",
            )
        elif abs(itm_pct) <= 0.05:
            # Near ATM → genuine bearish bet
            return DeepITMResult(
                symbol=symbol, strike=strike, current_price=current_price,
                call_put="PUT", itm_pct=itm_pct,
                classification="NEAR_ATM", signal="BEARISH",
            )
        elif itm_pct < -0.05:
            # OTM put → hedging
            return DeepITMResult(
                symbol=symbol, strike=strike, current_price=current_price,
                call_put="PUT", itm_pct=itm_pct,
                classification="OTM_HEDGE", signal="HEDGE",
            )
        else:
            # Slightly ITM but not deep
            return DeepITMResult(
                symbol=symbol, strike=strike, current_price=current_price,
                call_put="PUT", itm_pct=itm_pct,
                classification="NEAR_ATM", signal="BEARISH",
            )

    elif call_put.upper() == "CALL":
        itm_pct = (current_price - strike) / current_price
        return DeepITMResult(
            symbol=symbol, strike=strike, current_price=current_price,
            call_put="CALL", itm_pct=itm_pct,
            classification="CALL", signal="BULLISH",
        )

    return DeepITMResult(
        symbol=symbol, strike=strike, current_price=current_price,
        call_put=call_put, itm_pct=0.0,
        classification="UNKNOWN", signal="NEUTRAL",
    )


async def apply_deep_itm_batch(
    entries: list[dict[str, Any]],
    prices: dict[str, float],
) -> list[dict[str, Any]]:
    """
    Apply Deep ITM Rule to a batch of flow entries.
    Enriches each entry with deep_itm_result.

    Args:
        entries: List of flow entry dicts
        prices: Dict of {symbol: current_price}
    """
    for entry in entries:
        symbol = entry.get("symbol", "")
        strike = entry.get("strike") or 0
        call_put = entry.get("call_put", "")
        price = prices.get(symbol, 0)

        if price > 0 and strike > 0 and call_put:
            result = check_deep_itm(symbol, strike, price, call_put)
            entry["deep_itm"] = result.to_dict()
        else:
            entry["deep_itm"] = None

    return entries

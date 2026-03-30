"""fx.py — FX normalization for price pipeline.

Phase A: pluggable stub with hardcoded fallback rates.
Phase A+: replace provider via FX_PROVIDER env var or config.

Usage:
    from fx import convert_to_rub, FX_PROVIDER_NAME

    rub = convert_to_rub(225.0, "EUR")   # → ~21375.0
    rub = convert_to_rub(68.25, "AED")   # → ~1635.0
    rub = convert_to_rub(None, "EUR")    # → None (amount missing)

To plug in a real provider:
    Set env var FX_PROVIDER=cbr  (or exchangerate_api)
    and ensure the relevant credentials/config are available.

The original currency + amount are ALWAYS preserved in the evidence bundle.
RUB conversion is only added when available — never replaces original data.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# ── Provider selection ───────────────────────────────────────────────────────────

FX_PROVIDER_NAME: str = os.environ.get("FX_PROVIDER", "stub")

# Stub rates (approximate, updated 2026-03-25).
# Replace with live lookup when FX_PROVIDER is set.
_STUB_RATES_TO_RUB: dict[str, float] = {
    "USD": 88.0,
    "EUR": 95.0,
    "GBP": 112.0,
    "AED": 24.0,
    "CNY": 12.2,
    "CHF": 98.0,
    "PLN": 22.0,
    "CZK": 3.9,
    "RUB": 1.0,
}


def _stub_convert(amount: float, currency: str) -> Optional[float]:
    rate = _STUB_RATES_TO_RUB.get(currency.upper())
    if rate is None:
        log.debug(f"fx stub: no rate for {currency}")
        return None
    return round(amount * rate, 2)


def _cbr_convert(amount: float, currency: str) -> Optional[float]:
    """Placeholder: CBR XML API (cbr.ru/scripts/XML_daily.asp).

    Not implemented in Phase A. Falls back to stub.
    """
    log.debug("fx: CBR provider not implemented, falling back to stub")
    return _stub_convert(amount, currency)


def _exchangerate_api_convert(amount: float, currency: str) -> Optional[float]:
    """Placeholder: exchangerate-api.com.

    Not implemented in Phase A. Falls back to stub.
    """
    log.debug("fx: exchangerate_api provider not implemented, falling back to stub")
    return _stub_convert(amount, currency)


# ── Public API ───────────────────────────────────────────────────────────────────

def convert_to_rub(
    amount: Optional[float],
    currency: Optional[str],
    provider: str = FX_PROVIDER_NAME,
) -> Optional[float]:
    """Convert amount in currency to RUB.

    Returns None if:
      - amount is None or zero
      - currency is None or unknown
      - provider fails and no fallback available

    Never raises — failures are logged and return None.
    """
    if not amount or not currency:
        return None
    if currency.upper() == "RUB":
        return round(float(amount), 2)
    try:
        if provider == "cbr":
            return _cbr_convert(float(amount), currency)
        if provider == "exchangerate_api":
            return _exchangerate_api_convert(float(amount), currency)
        return _stub_convert(float(amount), currency)
    except Exception as e:
        log.warning(f"fx convert_to_rub failed ({currency} → RUB): {e}")
        return None


def fx_meta(currency: Optional[str], provider: str = FX_PROVIDER_NAME) -> dict:
    """Return FX metadata for evidence bundle trace."""
    return {
        "fx_provider": provider,
        "fx_currency_source": currency,
        "fx_rate_stub": _STUB_RATES_TO_RUB.get((currency or "").upper()),
    }

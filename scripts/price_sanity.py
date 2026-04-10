"""price_sanity.py — Price sanity validator for enrichment pipeline.

Runs AFTER price extraction, BEFORE writing to evidence bundle.
Catches: AED/exotic currency mis-conversions, box/pack prices taken as
unit prices, extreme outliers, round-number suspicion.

Returns PriceSanityResult(status, flags) where status is:
  PASS    — write as-is
  WARNING — write price but attach price_warnings to evidence
  REJECT  — do NOT write price; set price_status = "rejected_sanity_check"

Deterministic — no API calls, no live data. Always testable in isolation.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Optional

# Stub USD rate (same as fx.py _STUB_RATES_TO_RUB["USD"])
_RUB_PER_USD: float = 88.0

# Exotic currencies that need extra scrutiny (often wrong FX or unit basis)
_EXOTIC_CURRENCIES: frozenset[str] = frozenset(
    {"AED", "SAR", "BHD", "KWD", "QAR", "OMR", "JOD"}
)

# Absolute price bounds (USD-equivalent)
_EXTREME_HIGH_USD: float = 50_000.0
_EXTREME_LOW_USD: float = 0.01

# Threshold above which "piece" unit_basis is suspicious
_HIGH_PIECE_PRICE_USD: float = 10.0

# Cross-reference multiplier thresholds
_CROSS_REF_FACTOR: float = 5.0

# Minimum price for round-number suspicion (box/case heuristic)
_ROUND_NUMBER_MIN_USD: float = 5.0


@dataclass
class PriceSanityResult:
    status: str  # "PASS" | "WARNING" | "REJECT"
    flags: list[str] = field(default_factory=list)

    def is_pass(self) -> bool:
        return self.status == "PASS"

    def is_warning(self) -> bool:
        return self.status == "WARNING"

    def is_reject(self) -> bool:
        return self.status == "REJECT"

    def to_dict(self) -> dict:
        return {"sanity_status": self.status, "sanity_flags": self.flags}


def _estimate_usd(
    raw_price: Optional[float],
    currency: Optional[str],
    rub_price: Optional[float],
) -> Optional[float]:
    """Convert raw price to USD estimate using stub rates.

    Priority:
      1. If currency is USD → raw_price directly.
      2. If rub_price available → rub_price / _RUB_PER_USD.
      3. Cannot estimate → None.
    """
    if raw_price is None:
        return None
    if currency and currency.upper() == "USD":
        return float(raw_price)
    if rub_price is not None and rub_price > 0:
        return round(rub_price / _RUB_PER_USD, 4)
    return None


def check_price_sanity(
    price_usd: Optional[float],
    pn: str,
    brand: str,
    source_currency: Optional[str],
    unit_basis: Optional[str],
    existing_prices_usd: Optional[list[float]] = None,
    rub_price: Optional[float] = None,
    raw_price: Optional[float] = None,
) -> PriceSanityResult:
    """Run sanity checks on a price before recording it in evidence.

    Args:
        price_usd:            Price expressed in USD (or USD-equivalent).
                              Pass None if unknown — returns WARNING.
        pn:                   Part number (for logging context only).
        brand:                Brand (for logging context only).
        source_currency:      Original currency code (e.g. "AED", "USD").
        unit_basis:           "piece" | "box" | "pack" | "case" | "unknown".
        existing_prices_usd:  List of other known USD prices for the same PN
                              (used for cross-reference check).
        rub_price:            RUB-converted price (optional, used to estimate USD
                              when price_usd is not already in USD).
        raw_price:            Raw price in source currency (used together with
                              rub_price for internal USD estimation if needed).

    Returns:
        PriceSanityResult with status PASS | WARNING | REJECT and list of flags.
    """
    # If price_usd was passed as None but we have rub_price, try to estimate
    effective_usd = price_usd
    if effective_usd is None and rub_price is not None:
        effective_usd = _estimate_usd(raw_price, source_currency, rub_price)

    if effective_usd is None:
        # Cannot validate — surface as WARNING so downstream can decide
        return PriceSanityResult("WARNING", ["NO_PRICE_USD: cannot estimate USD equivalent"])

    flags: list[str] = []

    # ── Rule 1: Absolute bounds ────────────────────────────────────────────────
    if effective_usd > _EXTREME_HIGH_USD:
        flags.append(f"EXTREME_HIGH: ${effective_usd:,.2f} > $50,000 per unit")
    if effective_usd < _EXTREME_LOW_USD:
        flags.append(f"EXTREME_LOW: ${effective_usd:.4f} < $0.01 per unit")

    # ── Rule 2: Exotic currency penalty ───────────────────────────────────────
    if source_currency and source_currency.upper() in _EXOTIC_CURRENCIES:
        flags.append(
            f"EXOTIC_CURRENCY: {source_currency} — verify FX rate and unit basis"
        )

    # ── Rule 3: High unit price suspicion (box/pack pricing) ──────────────────
    # Only apply for exotic currencies — non-exotic USD/EUR prices are FX-exact
    # and high-value industrial products are common ($1000+ sensors, $20k+ systems).
    if (
        unit_basis in ("piece", "unknown", None)
        and effective_usd > _HIGH_PIECE_PRICE_USD
        and source_currency
        and source_currency.upper() in _EXOTIC_CURRENCIES
    ):
        flags.append(
            f"HIGH_PIECE_PRICE_EXOTIC: ${effective_usd:.2f}/unit in {source_currency}"
            " — verify not box/pack price"
        )

    # ── Rule 4: Cross-reference with other known prices for this PN ───────────
    if existing_prices_usd and len(existing_prices_usd) >= 2:
        valid_others = [p for p in existing_prices_usd if p and p > 0]
        if valid_others:
            med = statistics.median(valid_others)
            if med > 0:
                if effective_usd > med * _CROSS_REF_FACTOR:
                    flags.append(
                        f"5X_ABOVE_MEDIAN: ${effective_usd:.2f} vs median ${med:.2f}"
                    )
                elif effective_usd < med / _CROSS_REF_FACTOR:
                    flags.append(
                        f"5X_BELOW_MEDIAN: ${effective_usd:.2f} vs median ${med:.2f}"
                    )

    # ── Rule 5: Round number suspicion (common for box/case prices) ───────────
    if (
        effective_usd >= _ROUND_NUMBER_MIN_USD
        and effective_usd == int(effective_usd)
        and source_currency
        and source_currency.upper() in _EXOTIC_CURRENCIES
    ):
        flags.append(
            f"ROUND_NUMBER_EXOTIC: ${effective_usd:.0f} in {source_currency}"
            " — possible box/case price"
        )

    # ── Decision ──────────────────────────────────────────────────────────────
    if any("EXTREME_" in f for f in flags):
        return PriceSanityResult("REJECT", flags)
    if flags:
        return PriceSanityResult("WARNING", flags)
    return PriceSanityResult("PASS", [])


def apply_sanity_to_price_info(
    price_info: dict,
    pn: str,
    brand: str,
    existing_prices_usd: Optional[list[float]] = None,
) -> dict:
    """Apply check_price_sanity to a price_info dict from the pipeline.

    Mutates a copy of price_info and returns it with sanity fields added.

    If REJECT:
      - price_usd → None
      - rub_price → None
      - price_status → "rejected_sanity_check"
      - price_sanity_status → "REJECT"
      - price_sanity_flags → [...]

    If WARNING:
      - price preserved as-is
      - price_sanity_status → "WARNING"
      - price_warnings → [...]

    If PASS:
      - price preserved as-is
      - price_sanity_status → "PASS"
    """
    raw_price = price_info.get("price_usd")    # stored as native currency value
    currency = price_info.get("currency")
    rub_price = price_info.get("rub_price")
    unit_basis = price_info.get("offer_unit_basis", "unknown")

    # Convert native currency to USD estimate
    estimated_usd = _estimate_usd(raw_price, currency, rub_price)

    result = check_price_sanity(
        price_usd=estimated_usd,
        pn=pn,
        brand=brand,
        source_currency=currency,
        unit_basis=unit_basis,
        existing_prices_usd=existing_prices_usd,
        rub_price=rub_price,
        raw_price=raw_price,
    )

    updated = dict(price_info)
    updated["price_sanity_status"] = result.status
    updated["price_sanity_flags"] = result.flags

    if result.is_reject():
        updated["price_usd"] = None
        updated["rub_price"] = None
        updated["price_status"] = "rejected_sanity_check"
        updated["price_warnings"] = result.flags
    elif result.is_warning():
        updated["price_warnings"] = result.flags
    else:
        updated.setdefault("price_warnings", [])

    return updated

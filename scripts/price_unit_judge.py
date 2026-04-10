"""price_unit_judge.py — Determine if a found price is per-unit or per-pack/lot.

Strict triggers ONLY (avoids false positives on normal B2B pricing):
- pack/box/set/lot/kit markers in surrounding text
- quantity patterns (e.g. "5 pcs", "x10", "pack of 12")
- exotic currency at very high price (RUB > 50000, USD > 1000)
- unit_phrase conflict (e.g. "цена за упаковку")

Does NOT trigger on:
- Price > some threshold alone (normal for industrial B2B)
- Round numbers (normal for B2B)
- High price in RUB for industrial equipment

Sonnet (expensive) called ONLY when triggers fire (~15-20% of SKUs).
Falls back to "per_unit" with low confidence when no triggers.

Usage:
    from price_unit_judge import judge_price_unit_basis, UnitBasisResult
    result = judge_price_unit_basis(price=1500.0, currency="RUB",
                                    context_text="Цена за упаковку 10 шт", pn="153711")
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# ── Trigger patterns ─────────────────────────────────────────────────────────

_PACK_MARKERS_RU = re.compile(
    r"\b(?:упак(?:овк[аи])?|коробк[аи]|набор|комплект|лот|пачк[аи]|рулон|бухт[аи])\b",
    re.IGNORECASE,
)
_PACK_MARKERS_EN = re.compile(
    r"\b(?:pack|box|lot|kit|set|bundle|reel|roll|case|carton|bulk)\b",
    re.IGNORECASE,
)
_QUANTITY_PATTERNS = re.compile(
    r"(?:"
    r"\d+\s*(?:шт|pcs|pieces|pc|units?|ea|each)"  # "10 шт", "5 pcs"
    r"|x\s*\d+"  # "x10", "x 5"
    r"|pack\s+of\s+\d+"  # "pack of 12"
    r"|цена\s+за\s+(?:\d+|упак|коробк)"  # "цена за 10", "цена за упаковку"
    r"|per\s+\d+"  # "per 10"
    r")",
    re.IGNORECASE,
)
_UNIT_PHRASE_CONFLICT = re.compile(
    r"(?:"
    r"цена\s+за\s+упак|price\s+per\s+(?:pack|box|lot|roll)|"
    r"стоимость\s+упаковки|цена\s+упаковки"
    r")",
    re.IGNORECASE,
)


def _has_pack_trigger(text: str) -> tuple[bool, str]:
    """Return (triggered, reason) if any pack/quantity trigger fires."""
    if _UNIT_PHRASE_CONFLICT.search(text):
        return True, "unit_phrase_conflict"
    if _QUANTITY_PATTERNS.search(text):
        return True, "quantity_pattern"
    if _PACK_MARKERS_RU.search(text):
        return True, "pack_marker_ru"
    if _PACK_MARKERS_EN.search(text):
        return True, "pack_marker_en"
    return False, ""


def _has_exotic_currency_trigger(price: float, currency: str) -> tuple[bool, str]:
    """Flag unusual price/currency combos — NOT just high price alone."""
    currency = (currency or "").upper()
    if currency == "RUB" and price > 500_000:
        return True, "exotic_rub_very_high"
    if currency == "USD" and price > 5_000:
        return True, "exotic_usd_high"
    if currency not in ("RUB", "USD", "EUR", "GBP", "", "RU"):
        return True, "exotic_currency"
    return False, ""


@dataclass
class UnitBasisResult:
    unit_basis: str  # "per_unit" | "per_pack" | "unknown"
    confidence: str  # "high" | "medium" | "low"
    triggered: bool = False
    trigger_reason: str = ""
    pack_qty: Optional[int] = None  # extracted quantity if per_pack
    llm_used: bool = False
    llm_raw: Optional[str] = None


def judge_price_unit_basis(
    price: float,
    currency: str,
    context_text: str,
    pn: str = "",
    brand: str = "",
    use_llm: bool = True,
    api_key: str = "",
) -> UnitBasisResult:
    """Determine if price is per-unit or per-pack.

    Algorithm:
    1. Check text triggers (pack markers, quantity patterns, phrase conflicts)
    2. Check currency/price triggers
    3. If any trigger: call Sonnet for confirmation (if use_llm=True)
    4. No trigger: return per_unit/high-confidence without LLM call

    Args:
        price: Extracted price value.
        currency: Currency code ("RUB", "USD", etc.).
        context_text: Surrounding page text (~500-1000 chars around price).
        pn: Product number (for LLM context).
        brand: Brand name (for LLM context).
        use_llm: Whether to call LLM when triggers fire.
        api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env).

    Returns:
        UnitBasisResult with unit_basis, confidence, trigger info.
    """
    text = context_text or ""

    # Check triggers
    pack_triggered, pack_reason = _has_pack_trigger(text)
    currency_triggered, currency_reason = _has_exotic_currency_trigger(price, currency)
    triggered = pack_triggered or currency_triggered
    trigger_reason = pack_reason or currency_reason

    if not triggered:
        return UnitBasisResult(
            unit_basis="per_unit",
            confidence="high",
            triggered=False,
        )

    # Trigger fired — try to extract quantity
    qty_match = re.search(r"(\d+)\s*(?:шт|pcs|pieces|pc|units?)", text, re.IGNORECASE)
    pack_qty = int(qty_match.group(1)) if qty_match else None

    if not use_llm:
        return UnitBasisResult(
            unit_basis="unknown",
            confidence="low",
            triggered=True,
            trigger_reason=trigger_reason,
            pack_qty=pack_qty,
        )

    # Call LLM for confirmation
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not api_key:
        return UnitBasisResult(
            unit_basis="unknown",
            confidence="low",
            triggered=True,
            trigger_reason=trigger_reason,
            pack_qty=pack_qty,
        )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            f"Product: {pn} ({brand})\n"
            f"Price: {price} {currency}\n"
            f"Context: {text[:800]}\n\n"
            f"Is this price per individual unit or per pack/set/lot?\n"
            f'Reply ONLY JSON: {{"unit_basis": "per_unit"|"per_pack"|"unknown", "confidence": "high"|"medium"|"low", "pack_qty": null|<number>}}'
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text if response.content else ""
        import json as _json
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            data = _json.loads(m.group())
            return UnitBasisResult(
                unit_basis=data.get("unit_basis", "unknown"),
                confidence=data.get("confidence", "low"),
                triggered=True,
                trigger_reason=trigger_reason,
                pack_qty=data.get("pack_qty") or pack_qty,
                llm_used=True,
                llm_raw=raw[:500],
            )
    except Exception as exc:
        log.warning(f"price_unit_judge: LLM call failed ({exc})")

    return UnitBasisResult(
        unit_basis="unknown",
        confidence="low",
        triggered=True,
        trigger_reason=trigger_reason,
        pack_qty=pack_qty,
        llm_used=False,
    )


if __name__ == "__main__":
    # Smoke tests
    tests = [
        (1500.0, "RUB", "Стальной кабель, цена за метр"),
        (1500.0, "RUB", "Упаковка 10 шт, цена за упаковку"),
        (250.0, "RUB", "pack of 12 connectors"),
        (45_000.0, "RUB", "Клапан Honeywell V5011R1000"),
        (1_200_000.0, "RUB", "Цена за единицу"),
    ]
    for price, currency, text in tests:
        result = judge_price_unit_basis(price, currency, text, use_llm=False)
        print(f"  price={price} cur={currency!r}: {result.unit_basis}/{result.confidence} "
              f"triggered={result.triggered} reason={result.trigger_reason!r}")

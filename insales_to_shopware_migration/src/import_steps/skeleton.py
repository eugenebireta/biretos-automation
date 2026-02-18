from __future__ import annotations

import uuid
from typing import Any, Dict

from clients import ShopwareClient
from import_steps import ProductImportState, StepState


def run(
    client: ShopwareClient,
    registry: Any,
    snapshot_product: Dict[str, Any],
    state: ProductImportState,
    context: Dict[str, Any],
) -> ProductImportState:
    dry_run: bool = context.get("dry_run", True)
    variant: Dict[str, Any] = context.get("variant") or _extract_primary_variant(snapshot_product)

    sku = str(variant.get("sku") or snapshot_product.get("sku") or snapshot_product.get("id") or "").strip()
    if not sku:
        state.set_step("skeleton", StepState.ERROR, "РќРµ СѓРґР°Р»РѕСЃСЊ РѕРїСЂРµРґРµР»РёС‚СЊ SKU РёР· snapshot")
        return state

    state.sku = sku
    product_name = (snapshot_product.get("title") or variant.get("title") or sku).strip()
    price_value = _safe_float(variant.get("price") or snapshot_product.get("price"))
    stock_value = _safe_int(variant.get("quantity") or 0)
    tax_id = context.get("tax_id") or client.get_standard_tax_id()
    currency_id = context.get("currency_id") or client.get_system_currency_id()

    payload = {
        "productNumber": sku,
        "name": product_name,
        "active": bool(snapshot_product.get("available", True)),
        "stock": stock_value,
        "taxId": tax_id,
        "price": [
            {
                "currencyId": currency_id,
                "gross": price_value,
                "net": price_value,
                "linked": False,
            }
        ],
        "description": snapshot_product.get("description") or snapshot_product.get("short_description") or "",
    }

    existing_id = state.product_id or client.find_product_by_number(sku)
    state.product_id = existing_id

    if dry_run:
        message = "Dry-run: С‚РѕРІР°СЂ СЃСѓС‰РµСЃС‚РІСѓРµС‚" if existing_id else "Dry-run: С‚РѕРІР°СЂ Р±СѓРґРµС‚ СЃРѕР·РґР°РЅ"
        state.set_step("skeleton", StepState.SUCCESS if existing_id else StepState.FALSE, message)
        return state

    try:
        if existing_id:
            client._request("PATCH", f"/api/product/{existing_id}", json=payload)
            state.set_step("skeleton", StepState.SUCCESS, f"РћР±РЅРѕРІР»С‘РЅ С‚РѕРІР°СЂ {existing_id}")
        else:
            product_id = uuid.uuid4().hex
            payload["id"] = product_id
            client._request("POST", "/api/product", json=payload)
            state.product_id = product_id
            state.set_step("skeleton", StepState.SUCCESS, f"РЎРѕР·РґР°РЅ С‚РѕРІР°СЂ {product_id}")
    except Exception as exc:
        state.set_step("skeleton", StepState.ERROR, f"РћС€РёР±РєР° СЃРѕР·РґР°РЅРёСЏ/РѕР±РЅРѕРІР»РµРЅРёСЏ С‚РѕРІР°СЂР°: {exc}")

    return state


def _extract_primary_variant(snapshot_product: Dict[str, Any]) -> Dict[str, Any]:
    variants = snapshot_product.get("variants") or []
    if variants and isinstance(variants, list):
        return variants[0] or {}
    return {}


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0

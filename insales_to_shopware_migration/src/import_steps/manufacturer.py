from __future__ import annotations

from typing import Any, Dict, Optional

from canon_registry import CanonRegistry
from clients import ShopwareClient
from import_steps import ProductImportState, StepState


def run(
    client: ShopwareClient,
    registry: CanonRegistry,
    snapshot_product: Dict[str, Any],
    state: ProductImportState,
    context: Dict[str, Any],
) -> ProductImportState:
    dry_run: bool = context.get("dry_run", True)
    variant: Dict[str, Any] = context.get("variant") or {}

    brand = _extract_brand(snapshot_product)
    if not brand:
        state.set_step("manufacturer", StepState.SUCCESS, "Skip manufacturer: brand missing in snapshot")
        return state

    manufacturer_number = _extract_manufacturer_number(snapshot_product, variant)

    if dry_run:
        message = f"Dry-run: brand={brand}, manufacturerNumber={'yes' if manufacturer_number else 'no'}"
        state.set_step("manufacturer", StepState.SUCCESS, message)
        return state

    if not state.product_id:
        state.set_step("manufacturer", StepState.ERROR, "product_id РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РїРѕСЃР»Рµ skeleton")
        return state

    try:
        manufacturer_id = registry.get_canonical_manufacturer_id(brand)
        payload: Dict[str, Any] = {"manufacturerId": manufacturer_id}
        if manufacturer_number:
            payload["manufacturerNumber"] = manufacturer_number.strip()

        client._request("PATCH", f"/api/product/{state.product_id}", json=payload)
        state.set_step("manufacturer", StepState.SUCCESS, f"manufacturerId={manufacturer_id}")
    except Exception as exc:
        state.set_step("manufacturer", StepState.ERROR, f"РћС€РёР±РєР° СѓСЃС‚Р°РЅРѕРІРєРё РїСЂРѕРёР·РІРѕРґРёС‚РµР»СЏ: {exc}")

    return state


def _extract_brand(snapshot_product: Dict[str, Any]) -> Optional[str]:
    properties = snapshot_product.get("properties") or []
    characteristics = snapshot_product.get("characteristics") or []
    brand_property_ids = {
        prop.get("id")
        for prop in properties
        if (prop.get("permalink") or "").strip().lower() == "brand"
        or (prop.get("title") or "").strip().lower() == "Р±СЂРµРЅРґ"
    }
    if not brand_property_ids:
        return None

    for char in characteristics:
        if char.get("property_id") in brand_property_ids:
            value = (char.get("title") or "").strip()
            if value:
                return value
    return None


def _extract_manufacturer_number(snapshot_product: Dict[str, Any], variant: Dict[str, Any]) -> Optional[str]:
    properties = snapshot_product.get("properties") or []
    characteristics = snapshot_product.get("characteristics") or []

    part_number_ids = {
        prop.get("id")
        for prop in properties
        if (prop.get("permalink") or "").strip().lower() in {"partnomer", "manufacturer_number"}
        or (prop.get("title") or "").strip().lower() in {"РїР°СЂС‚РЅРѕРјРµСЂ"}
    }

    for char in characteristics:
        if char.get("property_id") in part_number_ids:
            value = (char.get("title") or "").strip()
            if value:
                return value

    fallback = (
        variant.get("manufacturer_number")
        or variant.get("mpn")
        or snapshot_product.get("manufacturer_number")
        or snapshot_product.get("part_number")
    )
    if fallback:
        return str(fallback).strip()
    return None

from __future__ import annotations

from typing import Any, Dict

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
    variant: Dict[str, Any] = context.get("variant") or {}
    marketplace_price = _safe_float(variant.get("price2"))
    if marketplace_price <= 0:
        state.set_step("prices", StepState.FALSE, "Marketplace price РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РІ snapshot")
        return state

    dry_run: bool = context.get("dry_run", True)
    currency_id = context.get("currency_id") or client.get_system_currency_id()

    if dry_run:
        state.set_step("prices", StepState.SUCCESS, f"Dry-run: marketplace price={marketplace_price}")
        return state

    if not state.product_id:
        state.set_step("prices", StepState.ERROR, "product_id РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РїРѕСЃР»Рµ skeleton")
        return state

    try:
        rule_id = registry.ensure_marketplace_rule()
    except Exception as exc:
        state.set_step("prices", StepState.ERROR, f"РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕР»СѓС‡РёС‚СЊ rule_id: {exc}")
        return state

    try:
        client.delete_all_product_prices(state.product_id)
        payload = {
            "productId": state.product_id,
            "ruleId": rule_id,
            "quantityStart": 1,
            "price": [
                {
                    "currencyId": currency_id,
                    "gross": marketplace_price,
                    "net": marketplace_price,
                    "linked": False,
                }
            ],
        }
        client._request("POST", "/api/product-price", json=payload)
        state.set_step("prices", StepState.SUCCESS, f"ruleId={rule_id}")
    except Exception as exc:
        state.set_step("prices", StepState.ERROR, f"РћС€РёР±РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ С†РµРЅ: {exc}")

    return state


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

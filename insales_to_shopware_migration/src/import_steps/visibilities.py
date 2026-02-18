from __future__ import annotations

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
    sales_channel_id = context.get("sales_channel_id") or client.get_storefront_sales_channel_id()
    if not sales_channel_id:
        state.set_step("visibilities", StepState.ERROR, "РќРµ СѓРґР°Р»РѕСЃСЊ РѕРїСЂРµРґРµР»РёС‚СЊ salesChannelId")
        return state

    dry_run: bool = context.get("dry_run", True)
    if dry_run:
        state.set_step("visibilities", StepState.SUCCESS, f"Dry-run: salesChannelId={sales_channel_id}")
        return state

    if not state.product_id:
        state.set_step("visibilities", StepState.ERROR, "product_id РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РїРѕСЃР»Рµ skeleton")
        return state

    deleted = client.delete_all_product_visibilities(state.product_id)

    payload = {
        "visibilities": [
            {
                "salesChannelId": sales_channel_id,
                "visibility": 30,
            }
        ]
    }

    try:
        client._request("PATCH", f"/api/product/{state.product_id}", json=payload)
        detail = f"Sales channel visibility РѕР±РЅРѕРІР»С‘РЅ ({sales_channel_id})"
        if deleted:
            detail = f"{detail}, deleted old: {deleted}"
        state.set_step("visibilities", StepState.SUCCESS, detail)
    except Exception as exc:
        state.set_step("visibilities", StepState.ERROR, f"РћС€РёР±РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ visibilities: {exc}")

    return state

from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    category_map: Dict[str, str] = context.get("category_map") or {}
    category_parents: Dict[str, Optional[str]] = context.get("category_parents") or {}

    insales_category_id = _resolve_insales_category_id(snapshot_product)
    if not insales_category_id:
        state.set_step("categories", StepState.FALSE, "Р’ snapshot РЅРµС‚ category_id")
        return state

    try:
        chain_insales = _build_insales_chain(str(insales_category_id), category_parents)
    except ValueError as exc:
        state.set_step("categories", StepState.ERROR, str(exc))
        return state

    try:
        chain_shopware = [_map_category(cat_id, category_map) for cat_id in chain_insales]
    except KeyError as exc:
        state.set_step("categories", StepState.ERROR, f"category_id {exc} РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РІ migration_map")
        return state

    if dry_run:
        message = f"Dry-run: categories={len(chain_shopware)} leaf={chain_shopware[-1]}"
        state.set_step("categories", StepState.SUCCESS, message)
        return state

    if not state.product_id:
        state.set_step("categories", StepState.ERROR, "product_id РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РїРѕСЃР»Рµ skeleton")
        return state

    payload = {"categories": [{"id": cat_id} for cat_id in chain_shopware]}
    try:
        client._request("PATCH", f"/api/product/{state.product_id}", json=payload)
        verified = _verify_categories(client, state.product_id, chain_shopware)
        status = StepState.SUCCESS if verified else StepState.FALSE
        message = "РљР°С‚РµРіРѕСЂРёРё РїСЂРёРјРµРЅРµРЅС‹" if verified else "РљР°С‚РµРіРѕСЂРёРё РїСЂРёРјРµРЅРµРЅС‹, РЅРѕ РІРµСЂРёС„РёРєР°С†РёСЏ РЅРµ РїСЂРѕС€Р»Р°"
        state.set_step("categories", status, message)
    except Exception as exc:
        state.set_step("categories", StepState.ERROR, f"РћС€РёР±РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ РєР°С‚РµРіРѕСЂРёР№: {exc}")

    return state


def _resolve_insales_category_id(snapshot_product: Dict[str, Any]) -> Optional[int]:
    category_id = snapshot_product.get("category_id")
    if category_id:
        return category_id
    collections = snapshot_product.get("collections_ids") or []
    if collections:
        return collections[0]
    return None


def _build_insales_chain(
    leaf_category_id: str,
    parents: Dict[str, Optional[str]],
) -> List[str]:
    chain: List[str] = []
    current: Optional[str] = leaf_category_id
    visited: set[str] = set()

    while current:
        if current in visited:
            raise ValueError(f"РћР±РЅР°СЂСѓР¶РµРЅ С†РёРєР» РІ РєР°С‚РµРіРѕСЂРёРё {current}")
        visited.add(current)
        chain.append(current)
        current = parents.get(current)

    chain.reverse()
    return chain


def _map_category(category_id: str, category_map: Dict[str, str]) -> str:
    mapped = category_map.get(str(category_id))
    if not mapped:
        raise KeyError(category_id)
    return mapped


def _verify_categories(client: ShopwareClient, product_id: str, expected_chain: List[str]) -> bool:
    try:
        response = client._request("GET", f"/api/product/{product_id}/categories")
    except Exception:
        return False

    data = response.get("data", []) if isinstance(response, dict) else []
    fetched = [item.get("id") for item in data if item.get("id")]
    if not fetched:
        return False

    expected_set = set(expected_chain)
    fetched_set = set(fetched)
    return expected_set.issubset(fetched_set)

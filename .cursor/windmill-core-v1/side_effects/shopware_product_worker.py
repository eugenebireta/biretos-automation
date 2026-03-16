import logging
from typing import Any, Dict, List

from config import get_config
try:
    from shopware_api_client import ShopwareApiClient, ShopwareApiError
    from shopware_idempotency import (
        insert_shopware_operation_idempotent,
        mark_shopware_operation_status,
    )
    from shopware_payload_builder import CDMProduct, build_shopware_product_payload
except ImportError:
    from ru_worker.shopware_api_client import ShopwareApiClient, ShopwareApiError
    from ru_worker.shopware_idempotency import (
        insert_shopware_operation_idempotent,
        mark_shopware_operation_status,
    )
    from ru_worker.shopware_payload_builder import CDMProduct, build_shopware_product_payload

_CONFIG = get_config()
logger = logging.getLogger(__name__)


def _normalize_media_urls(raw_media_urls: Any) -> List[str]:
    if raw_media_urls is None:
        return []
    if isinstance(raw_media_urls, str):
        values = [raw_media_urls]
    elif isinstance(raw_media_urls, list):
        values = raw_media_urls
    else:
        raise ValueError("media_urls must be list[str] or string")

    seen: set[str] = set()
    normalized: List[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        media_url = value.strip()
        if not media_url or media_url in seen:
            continue
        seen.add(media_url)
        normalized.append(media_url)
    return normalized


def _get_media_mapping(db_conn, product_number: str, media_url: str) -> str | None:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT shopware_media_id
            FROM shopware_media_map
            WHERE product_number = %s
              AND media_url = %s
            LIMIT 1
            """,
            (product_number, media_url),
        )
        row = cursor.fetchone()
        if not row:
            return None
        media_id = row[0]
        if isinstance(media_id, str) and media_id:
            return media_id
        return None
    finally:
        cursor.close()


def _upsert_media_mapping(
    db_conn,
    product_number: str,
    media_url: str,
    shopware_media_id: str,
    position: int,
) -> None:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO shopware_media_map (
                product_number,
                media_url,
                shopware_media_id,
                position
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (product_number, media_url)
            DO UPDATE
               SET shopware_media_id = EXCLUDED.shopware_media_id,
                   position = EXCLUDED.position,
                   updated_at = NOW()
            """,
            (product_number, media_url, shopware_media_id, position),
        )
    finally:
        cursor.close()


def _resolve_media_ids(
    db_conn,
    client: ShopwareApiClient,
    product_number: str,
    media_urls: List[str],
) -> List[str]:
    media_ids: List[str] = []
    for position, media_url in enumerate(media_urls, start=1):
        existing = _get_media_mapping(db_conn, product_number, media_url)
        media_id = existing or client.ensure_media_for_url(media_url)
        _upsert_media_mapping(
            db_conn=db_conn,
            product_number=product_number,
            media_url=media_url,
            shopware_media_id=media_id,
            position=position,
        )
        media_ids.append(media_id)
    return media_ids


def _resolve_stock_from_snapshot(db_conn, payload: dict, fallback_stock: int) -> int:
    """
    Phase 2 (v2.1):
    Shopware stock projection SHOULD come from availability_snapshot when available.
    Backward-compatible fallback keeps old payload-provided stock.
    """
    product_id = payload.get("availability_product_id")
    warehouse_code = payload.get("availability_warehouse_code")
    if not product_id or not warehouse_code:
        return fallback_stock

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT quantity_available
            FROM availability_snapshot
            WHERE product_id = %s
              AND warehouse_code = %s
            LIMIT 1
            """,
            (str(product_id), str(warehouse_code)),
        )
        row = cursor.fetchone()
        if not row:
            return fallback_stock
        try:
            return max(0, int(row[0]))
        except Exception:
            return fallback_stock
    finally:
        cursor.close()


def execute_shopware_product_sync(payload: dict, db_conn) -> dict:
    product_number = payload.get("product_number")
    cdm_product_raw = payload.get("cdm_product") or {}
    trace_id = payload.get("_trace_id")

    if not product_number:
        raise ValueError("product_number is required in payload")
    if not isinstance(cdm_product_raw, dict):
        raise ValueError("cdm_product must be a dict")

    resolved_stock = _resolve_stock_from_snapshot(db_conn, payload, int(cdm_product_raw["stock"]))
    media_urls = _normalize_media_urls(
        cdm_product_raw.get("media_urls") or payload.get("media_urls")
    )
    attributes = cdm_product_raw.get("attributes")
    if attributes is not None and not isinstance(attributes, dict):
        raise ValueError("cdm_product.attributes must be a dict")

    client = ShopwareApiClient(_CONFIG, logger)
    try:
        media_ids = _resolve_media_ids(
            db_conn=db_conn,
            client=client,
            product_number=product_number,
            media_urls=media_urls,
        )

        cdm_product = CDMProduct(
            product_number=product_number,
            name=cdm_product_raw["name"],
            description=cdm_product_raw["description"],
            price_gross=float(cdm_product_raw["price_gross"]),
            currency_id=cdm_product_raw["currency_id"],
            tax_id=cdm_product_raw["tax_id"],
            stock=resolved_stock,
            active=bool(cdm_product_raw["active"]),
            media_ids=media_ids,
            attributes=attributes,
        )
        shopware_payload = build_shopware_product_payload(cdm_product)

        operation = insert_shopware_operation_idempotent(
            db_conn=db_conn,
            product_number=product_number,
            payload=shopware_payload,
        )
        operation_id = operation["operation_id"]

        if operation["mode"] == "skip":
            return {"status": "skipped", "operation_id": operation_id}

        try:
            client.upsert_product(shopware_payload)
        except ShopwareApiError as exc:
            mark_shopware_operation_status(db_conn, operation_id, "failed", str(exc))
            raise

        mark_shopware_operation_status(db_conn, operation_id, "confirmed")
        if trace_id:
            logger.debug("shopware sync confirmed", extra={"trace_id": trace_id, "operation_id": operation_id})
        return {"status": "confirmed", "operation_id": operation_id}
    finally:
        client.close()

import logging

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

    cdm_product = CDMProduct(
        product_number=product_number,
        name=cdm_product_raw["name"],
        description=cdm_product_raw["description"],
        price_gross=float(cdm_product_raw["price_gross"]),
        currency_id=cdm_product_raw["currency_id"],
        tax_id=cdm_product_raw["tax_id"],
        stock=resolved_stock,
        active=bool(cdm_product_raw["active"]),
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

    client = ShopwareApiClient(_CONFIG, logger)
    try:
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

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

SEND_INVOICE_POLICY_HASH = "send-invoice-day2-min-safe-v1"


def _parse_jsonb(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return {}


def _coerce_total_amount(order_total_minor: Any, metadata: Dict[str, Any]) -> Optional[float]:
    if order_total_minor is not None:
        try:
            return round(float(order_total_minor) / 100.0, 2)
        except (TypeError, ValueError):
            pass

    raw = metadata.get("totalAmount")
    if raw is None:
        return None
    try:
        return round(float(raw), 2)
    except (TypeError, ValueError):
        return None


def _fetch_single_order(db_conn: Any, *, insales_order_id: str) -> Optional[Dict[str, Any]]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                order_id::text,
                insales_order_id,
                customer_data,
                delivery_data,
                metadata,
                order_total_minor
            FROM order_ledger
            WHERE insales_order_id = %s
            LIMIT 1
            """,
            (insales_order_id,),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()

    if not row:
        return None

    return {
        "order_id": str(row[0]),
        "insales_order_id": str(row[1]),
        "customer_data": _parse_jsonb(row[2]),
        "delivery_data": _parse_jsonb(row[3]),
        "metadata": _parse_jsonb(row[4]),
        "order_total_minor": row[5],
    }


def _fetch_line_items(db_conn: Any, *, order_id: str) -> List[Dict[str, Any]]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                line_seq,
                product_id,
                sku_snapshot,
                name_snapshot,
                quantity,
                price_unit_minor,
                tax_rate_bps
            FROM order_line_items
            WHERE order_id = %s::uuid
            ORDER BY line_seq ASC
            LIMIT 2
            """,
            (order_id,),
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()

    items: List[Dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "line_seq": int(row[0]),
                "product_id": str(row[1]) if row[1] is not None else None,
                "sku_snapshot": str(row[2]),
                "name_snapshot": str(row[3]),
                "quantity": int(row[4]),
                "price_unit_minor": int(row[5]),
                "tax_rate_bps": int(row[6] or 0),
            }
        )
    return items


def _insufficient_context(
    *,
    trace_id: str,
    insales_order_id: Optional[str],
    reason: str,
    message: str,
    required_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "status": "insufficient_context",
        "error_class": "BUSINESS_RULE",
        "severity": "WARNING",
        "retriable": True,
        "error": reason,
        "message": message,
        "intent_type": "send_invoice",
        "trace_id": trace_id,
        "insales_order_id": insales_order_id,
        "required_fields": list(required_fields or []),
        "manual_intervention_required": True,
    }


def _review_required(
    *,
    trace_id: str,
    insales_order_id: str,
    reason: str,
    message: str,
) -> Dict[str, Any]:
    return {
        "status": "review_required",
        "error_class": "BUSINESS_RULE",
        "severity": "WARNING",
        "retriable": False,
        "error": reason,
        "message": message,
        "intent_type": "send_invoice",
        "trace_id": trace_id,
        "insales_order_id": insales_order_id,
        "manual_intervention_required": True,
    }


def resolve_send_invoice_request(
    db_conn: Any,
    *,
    trace_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    insales_order_id = str(payload.get("insales_order_id") or "").strip()
    if not insales_order_id:
        return _insufficient_context(
            trace_id=trace_id,
            insales_order_id=None,
            reason="send_invoice_requires_insales_order_id",
            message="Для выставления счёта нужен явный номер заказа. Напишите, например: выставить счёт ORDER-12345.",
            required_fields=["insales_order_id"],
        )

    try:
        order = _fetch_single_order(db_conn, insales_order_id=insales_order_id)
    except Exception:
        return _review_required(
            trace_id=trace_id,
            insales_order_id=insales_order_id,
            reason="send_invoice_order_context_unavailable",
            message="Сейчас не могу безопасно собрать контекст заказа для выставления счёта. Нужна ручная обработка.",
        )
    if order is None:
        return _insufficient_context(
            trace_id=trace_id,
            insales_order_id=insales_order_id,
            reason="send_invoice_order_not_found",
            message=f"Не нашёл заказ {insales_order_id}. Проверьте номер заказа и попробуйте ещё раз.",
            required_fields=["insales_order_id"],
        )

    customer_data = dict(order["customer_data"])
    payer_inn = str(customer_data.get("inn") or "").strip()
    if not payer_inn:
        return _review_required(
            trace_id=trace_id,
            insales_order_id=insales_order_id,
            reason="send_invoice_missing_customer_inn",
            message=f"По заказу {insales_order_id} нет ИНН плательщика. Автоматически выставить счёт небезопасно, нужна ручная обработка.",
        )

    total_amount = _coerce_total_amount(order.get("order_total_minor"), order["metadata"])
    if total_amount is None or total_amount <= 0:
        return _review_required(
            trace_id=trace_id,
            insales_order_id=insales_order_id,
            reason="send_invoice_missing_total_amount",
            message=f"По заказу {insales_order_id} не хватает суммы заказа. Автоматически выставить счёт нельзя.",
        )

    try:
        line_items = _fetch_line_items(db_conn, order_id=order["order_id"])
    except Exception:
        return _review_required(
            trace_id=trace_id,
            insales_order_id=insales_order_id,
            reason="send_invoice_order_context_unavailable",
            message="Сейчас не могу безопасно собрать контекст заказа для выставления счёта. Нужна ручная обработка.",
        )
    if not line_items:
        return _review_required(
            trace_id=trace_id,
            insales_order_id=insales_order_id,
            reason="send_invoice_missing_line_items",
            message=f"По заказу {insales_order_id} нет сохранённых позиций. Нужна ручная обработка перед выставлением счёта.",
        )
    if len(line_items) != 1:
        return _review_required(
            trace_id=trace_id,
            insales_order_id=insales_order_id,
            reason="send_invoice_multiple_line_items_unsupported",
            message=f"Заказ {insales_order_id} слишком сложный для безопасного авто-выставления счёта. Нужна ручная обработка.",
        )

    line_item = line_items[0]
    quantity = int(line_item["quantity"])
    if quantity <= 0:
        return _review_required(
            trace_id=trace_id,
            insales_order_id=insales_order_id,
            reason="send_invoice_invalid_line_quantity",
            message=f"По заказу {insales_order_id} повреждён line item snapshot. Нужна ручная обработка.",
        )

    line_total = round((float(line_item["price_unit_minor"]) * quantity) / 100.0, 2)
    delivery_cost = round(total_amount - line_total, 2)
    if delivery_cost < -0.01:
        return _review_required(
            trace_id=trace_id,
            insales_order_id=insales_order_id,
            reason="send_invoice_negative_delivery_delta",
            message=f"По заказу {insales_order_id} сумма заказа не совпадает с line item snapshot. Нужна ручная обработка.",
        )
    if delivery_cost < 0:
        delivery_cost = 0.0

    invoice_payload = {
        "trace_id": trace_id,
        "_trace_id": trace_id,
        "insales_order_id": insales_order_id,
        "customer_data": customer_data,
        "delivery_data": dict(order["delivery_data"]),
        "product": {
            "id": line_item["product_id"] or line_item["sku_snapshot"],
            "sku": line_item["sku_snapshot"],
            "name": line_item["name_snapshot"],
            "price": line_total,
            "tax_rate_bps": line_item["tax_rate_bps"],
        },
        "delivery_cost": delivery_cost,
        "total_amount": total_amount,
        "currency": str(order["metadata"].get("currency") or "RUB"),
    }

    return {
        "status": "ready",
        "trace_id": trace_id,
        "intent_type": "send_invoice",
        "insales_order_id": insales_order_id,
        "order_id": order["order_id"],
        "invoice_payload": invoice_payload,
        "resolution_context": {
            "line_seq": line_item["line_seq"],
            "line_total": line_total,
            "delivery_cost": delivery_cost,
            "contract": "explicit_insales_order_id + single_line_item + inn + total_amount",
        },
    }


def execute_send_invoice(
    db_conn: Any,
    *,
    trace_id: str,
    payload: Dict[str, Any],
    invoice_executor: Optional[Callable[[Dict[str, Any], Any], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    resolved = resolve_send_invoice_request(db_conn, trace_id=trace_id, payload=payload)
    if resolved["status"] != "ready":
        return resolved

    if invoice_executor is None:
        from side_effects.invoice_worker import execute_invoice_create

        executor = execute_invoice_create
    else:
        executor = invoice_executor
    try:
        execution_result = executor(dict(resolved["invoice_payload"]), db_conn)
    except Exception as exc:
        return {
            "status": "error",
            "error_class": "TRANSIENT",
            "severity": "ERROR",
            "retriable": True,
            "error": str(exc),
            "intent_type": "send_invoice",
            "trace_id": trace_id,
            "insales_order_id": resolved["insales_order_id"],
        }

    result = dict(execution_result)
    result["worker_status"] = execution_result.get("status")
    result["status"] = "success"
    result["intent_type"] = "send_invoice"
    result["trace_id"] = trace_id
    result["insales_order_id"] = resolved["insales_order_id"]
    result["order_id"] = resolved["order_id"]
    result.setdefault("provider_document_id", execution_result.get("tbank_invoice_id"))
    return result

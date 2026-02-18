"""
Invoice worker (Phase 2 / Contract Pack v2.1).

Core logic:
- deterministic document generation key by content hash
- backward-compatible order_ledger updates
- provider interactions delegated to adapters
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any, Dict
from uuid import UUID, uuid4

from psycopg2.extras import RealDictCursor

from config import get_config
from domain.document_service import (
    attach_provider_result_atomic,
    upsert_document_by_content_hash_atomic,
)
from domain.ports import InvoiceCreateRequest
from side_effects.adapters.factory import (
    get_order_source_adapter,
    get_payment_invoice_adapter,
)

_CONFIG = get_config()


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


def _deterministic_invoice_number(generation_key: str) -> str:
    digest = sha256(generation_key.encode("utf-8")).hexdigest()[:12].upper()
    return f"INV-{digest}"


def _build_invoice_content_snapshot(
    *,
    order_id: UUID,
    product: Dict[str, Any],
    total_amount: float,
    delivery_cost: float,
    currency: str,
    customer_data: Dict[str, Any],
) -> Dict[str, Any]:
    product_price = float(product.get("price", 0))
    subtotal_minor = int(round(product_price * 100))
    shipping_minor = int(round(delivery_cost * 100))
    total_minor = int(round(total_amount * 100))
    tax_minor = max(0, total_minor - subtotal_minor - shipping_minor)
    return {
        "_schema_version": "2.0",
        "order_id": str(order_id),
        "currency": currency,
        "line_items": [
            {
                "line_seq": 1,
                "sku_snapshot": str(product.get("sku") or product.get("id") or "line-1"),
                "name_snapshot": str(product.get("name") or "Товар"),
                "quantity": 1,
                "price_unit_minor": subtotal_minor,
                "tax_rate_bps": int(product.get("tax_rate_bps", 0) or 0),
            }
        ],
        "subtotal_minor": subtotal_minor,
        "tax_minor": tax_minor,
        "shipping_minor": shipping_minor,
        "total_minor": total_minor,
        "payer_name": customer_data.get("companyName") or customer_data.get("name") or "Клиент",
        "payer_inn": customer_data.get("inn"),
    }


def execute_invoice_create(payload: Dict[str, Any], db_conn) -> Dict[str, Any]:
    insales_order_id = payload.get("insales_order_id")
    customer_data = payload.get("customer_data", {})
    delivery_data = payload.get("delivery_data", {})
    product = payload.get("product", {})
    delivery_cost = float(payload.get("delivery_cost", 0))
    total_amount = float(payload.get("total_amount", 0))
    currency = payload.get("currency", "RUB")
    trace_id = payload.get("_trace_id") or payload.get("trace_id")
    execution_mode = (payload.get("execution_mode") or _CONFIG.execution_mode or "LIVE").upper()

    if not insales_order_id:
        raise Exception("insales_order_id is required in payload")
    if not customer_data:
        raise Exception("customer_data is required in payload")
    if not product:
        raise Exception("product is required in payload")
    if not total_amount:
        raise Exception("total_amount is required in payload")
    payer_inn = customer_data.get("inn")
    if not payer_inn:
        raise Exception("Customer INN is required for T-Bank invoice")

    cursor = db_conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(
            """
            SELECT * FROM order_ledger
            WHERE insales_order_id = %s
            LIMIT 1
            FOR UPDATE
            """,
            (insales_order_id,),
        )
        existing_order = cursor.fetchone()
        order_id = UUID(str(existing_order["order_id"])) if existing_order else uuid4()
        metadata = _parse_jsonb(existing_order.get("metadata")) if existing_order else {}
        metadata["totalAmount"] = total_amount
        metadata["currency"] = currency

        bootstrap_key = metadata.get("invoice_request_key") or f"invoice-bootstrap:{order_id}"
        cursor.execute(
            """
            INSERT INTO order_ledger (
                order_id, insales_order_id, invoice_request_key, state, metadata,
                customer_data, delivery_data, state_history, error_log, trace_id,
                status_changed_at, order_total_minor
            )
            VALUES (
                %s::uuid, %s::text, %s::text, %s::text, %s::jsonb,
                %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::uuid,
                NOW(), %s
            )
            ON CONFLICT (insales_order_id) DO UPDATE SET
                state = CASE
                    WHEN order_ledger.state IN ('draft', 'pending_invoice')
                    THEN EXCLUDED.state
                    ELSE order_ledger.state
                END,
                metadata = EXCLUDED.metadata,
                customer_data = EXCLUDED.customer_data,
                delivery_data = EXCLUDED.delivery_data,
                order_total_minor = EXCLUDED.order_total_minor,
                trace_id = COALESCE(order_ledger.trace_id, EXCLUDED.trace_id),
                status_changed_at = CASE
                    WHEN order_ledger.state IN ('draft', 'pending_invoice')
                         AND order_ledger.state <> EXCLUDED.state
                    THEN NOW()
                    ELSE order_ledger.status_changed_at
                END,
                updated_at = NOW()
            RETURNING *
            """,
            (
                str(order_id),
                insales_order_id,
                bootstrap_key,
                "pending_invoice",
                json.dumps(metadata, ensure_ascii=False),
                json.dumps(customer_data, ensure_ascii=False),
                json.dumps(delivery_data, ensure_ascii=False),
                json.dumps([], ensure_ascii=False),
                json.dumps([], ensure_ascii=False),
                trace_id,
                int(round(total_amount * 100)),
            ),
        )
        cursor.fetchone()

        content_snapshot = _build_invoice_content_snapshot(
            order_id=order_id,
            product=product,
            total_amount=total_amount,
            delivery_cost=delivery_cost,
            currency=currency,
            customer_data=customer_data,
        )
        doc = upsert_document_by_content_hash_atomic(
            db_conn,
            order_id=order_id,
            trace_id=trace_id,
            document_type="invoice",
            document_number=f"ORDER-{order_id}",
            status="issued",
            provider_code="tbank",
            amount_minor=content_snapshot["total_minor"],
            currency=currency,
            content_snapshot=content_snapshot,
            metadata={"insales_order_id": insales_order_id},
        )
        generation_key = doc["generation_key"]
        invoice_number = metadata.get("invoiceNumber") or _deterministic_invoice_number(generation_key)
        metadata["invoiceNumber"] = invoice_number
        metadata["invoice_request_key"] = generation_key

        # ensure order_ledger cache values remain backward-compatible
        cursor.execute(
            """
            UPDATE order_ledger
            SET invoice_request_key = %s,
                metadata = %s::jsonb,
                updated_at = NOW()
            WHERE order_id = %s
            """,
            (generation_key, json.dumps(metadata, ensure_ascii=False), str(order_id)),
        )

        # If invoice already bound to external id, return idempotent success.
        cursor.execute(
            """
            SELECT provider_document_id, pdf_url
            FROM documents
            WHERE id = %s
            LIMIT 1
            """,
            (doc["document_id"],),
        )
        existing_doc = cursor.fetchone()
        if existing_doc and existing_doc["provider_document_id"]:
            db_conn.commit()
            return {
                "job_type": "invoice_create",
                "status": "completed",
                "ok": True,
                "order_id": str(order_id),
                "insales_order_id": insales_order_id,
                "tbank_invoice_id": existing_doc["provider_document_id"],
                "invoice_number": invoice_number,
                "pdf_url": existing_doc.get("pdf_url"),
                "message": "Invoice already exists",
                "generation_key": generation_key,
            }

        due_date = (datetime.utcnow() + timedelta(days=3)).strftime("%Y-%m-%d")
        adapter = get_payment_invoice_adapter(
            execution_mode=execution_mode,
            db_conn=db_conn,
            trace_id=trace_id,
        )
        adapter_resp = adapter.create_invoice(
            InvoiceCreateRequest(
                invoice_number=invoice_number,
                due_date=due_date,
                payer_name=content_snapshot["payer_name"],
                payer_inn=content_snapshot["payer_inn"],
                items=[
                    {
                        "name": content_snapshot["line_items"][0]["name_snapshot"],
                        "price": round(content_snapshot["line_items"][0]["price_unit_minor"] / 100.0, 2),
                        "amount": 1,
                        "unit": "шт",
                        "vat": "None",
                    },
                    *(
                        [
                            {
                                "name": "Доставка",
                                "price": round(content_snapshot["shipping_minor"] / 100.0, 2),
                                "amount": 1,
                                "unit": "услуга",
                                "vat": "None",
                            }
                        ]
                        if content_snapshot["shipping_minor"] > 0
                        else []
                    ),
                ],
                trace_id=trace_id,
            )
        )

        attach_provider_result_atomic(
            db_conn,
            document_id=UUID(str(doc["document_id"])),
            provider_document_id=adapter_resp.provider_document_id,
            pdf_url=adapter_resp.pdf_url,
            raw_provider_response=adapter_resp.raw_response,
        )

        cursor.execute(
            """
            UPDATE order_ledger
            SET tbank_invoice_id = %s,
                metadata = metadata || %s::jsonb,
                updated_at = NOW()
            WHERE order_id = %s
            """,
            (
                adapter_resp.provider_document_id,
                json.dumps(
                    {
                        "invoiceNumber": invoice_number,
                        "invoice_request_key": generation_key,
                        "totalAmount": total_amount,
                        "currency": currency,
                    },
                    ensure_ascii=False,
                ),
                str(order_id),
            ),
        )

        event_id = uuid4()
        order_event_payload = {
            "event_id": str(event_id),
            "source": "tbank",
            "event_type": "INVOICE_CREATED",
            "external_id": adapter_resp.provider_document_id,
            "occurred_at": datetime.utcnow().isoformat() + "Z",
            "payload": {
                "invoice_id": adapter_resp.provider_document_id,
                "invoice_number": invoice_number,
                "pdf_url": adapter_resp.pdf_url,
            },
            "order_id": str(order_id),
        }
        cursor.execute(
            """
            INSERT INTO job_queue (id, job_type, payload, status, idempotency_key, trace_id)
            VALUES (gen_random_uuid(), %s, %s, 'pending', %s, %s::uuid)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                "order_event",
                json.dumps(order_event_payload, ensure_ascii=False),
                f"order_event:tbank:INVOICE_CREATED:{adapter_resp.provider_document_id}",
                trace_id,
            ),
        )
        fsm_job_row = cursor.fetchone()
        fsm_job_id = str(fsm_job_row[0]) if fsm_job_row else None
        db_conn.commit()

        # Best effort side-effect (adapter-only, outside core transaction).
        try:
            get_order_source_adapter(execution_mode=execution_mode).set_order_custom_field(
                external_order_id=insales_order_id,
                field_handle="tbank_invoice_id",
                value=adapter_resp.provider_document_id,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "event": "invoice_create_insales_update_failed",
                        "order_id": str(order_id),
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
            )

        return {
            "job_type": "invoice_create",
            "status": "completed",
            "ok": True,
            "order_id": str(order_id),
            "insales_order_id": insales_order_id,
            "tbank_invoice_id": adapter_resp.provider_document_id,
            "invoice_number": invoice_number,
            "pdf_url": adapter_resp.pdf_url,
            "fsm_job_id": fsm_job_id,
            "generation_key": generation_key,
        }
    except Exception:
        db_conn.rollback()
        raise
    finally:
        cursor.close()


from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Iterable, Tuple

from config import get_config
try:
    from policy_hash import current_policy_context
except ImportError:
    from .policy_hash import current_policy_context  # type: ignore

_CONFIG = get_config()

PII_FIELD_REGISTRY: Tuple[Tuple[str, str, str, str], ...] = (
    ("order_ledger", "customer_data", "$.name", "PII_DEPENDENT"),
    ("order_ledger", "customer_data", "$.phone", "PII_DEPENDENT"),
    ("order_ledger", "customer_data", "$.email", "PII_DEPENDENT"),
    ("order_ledger", "customer_data", "$.address", "PII_DEPENDENT"),
    ("order_ledger", "customer_data", "$.inn", "PII_DEPENDENT"),
    ("order_ledger", "delivery_data", "$.name", "PII_DEPENDENT"),
    ("order_ledger", "delivery_data", "$.phone", "PII_DEPENDENT"),
    ("order_ledger", "delivery_data", "$.email", "PII_DEPENDENT"),
    ("order_ledger", "delivery_data", "$.address", "PII_DEPENDENT"),
    ("shipments", "address_snapshot", "$.recipient_name", "PII_DEPENDENT"),
    ("shipments", "address_snapshot", "$.recipient_phone", "PII_DEPENDENT"),
    ("shipments", "address_snapshot", "$.raw", "PII_DEPENDENT"),
)

_SUPPORTED_KEYS = {"name", "phone", "email", "address", "inn", "recipient_name", "recipient_phone", "raw"}


def _parse_jsonb(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _redact_value(value: Any, *, salt: str) -> str:
    digest = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()
    return f"REDACTED:{digest}"


def _redact_dict_fields(source: Dict[str, Any], *, fields: Iterable[str], salt: str) -> Dict[str, Any]:
    redacted = dict(source)
    for key in fields:
        if key in redacted and redacted[key] not in (None, ""):
            redacted[key] = _redact_value(redacted[key], salt=salt)
    return redacted


def _insert_redaction_decision(db_conn, trace_id: str, payload: Dict[str, Any]) -> None:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT COALESCE(MAX(decision_seq), 0) + 1
            FROM control_decisions
            WHERE trace_id = %s::uuid
            """,
            (trace_id,),
        )
        seq = int(cursor.fetchone()[0])
        policy_context = current_policy_context(_CONFIG)
        cursor.execute(
            """
            INSERT INTO control_decisions (
                trace_id,
                decision_seq,
                gate_name,
                verdict,
                schema_version,
                policy_hash,
                decision_context
            )
            VALUES (
                %s::uuid,
                %s,
                'pii_redaction',
                'APPLIED',
                %s,
                %s,
                %s::jsonb
            )
            """,
            (
                trace_id,
                seq,
                _CONFIG.gate_chain_version,
                policy_context["policy_hash"],
                json.dumps(payload, ensure_ascii=False),
            ),
        )
    finally:
        cursor.close()


def redact_trace(
    db_conn,
    *,
    trace_id: str,
    legal_basis: str,
    requested_by: str = "system",
    salt: str | None = None,
) -> Dict[str, Any]:
    """
    Redacts PII for one trace in a single DB transaction.
    No partial redaction is allowed: failures trigger full rollback.
    """
    if not trace_id:
        raise ValueError("trace_id is required")
    if getattr(db_conn, "autocommit", False):
        raise RuntimeError("redact_trace requires autocommit=False")

    redaction_salt = salt or os.getenv("PII_REDACTION_SALT") or "biretos-pii-salt"
    if not redaction_salt:
        raise RuntimeError("PII redaction salt is required")

    cursor = db_conn.cursor()
    try:
        # Lock all affected rows first.
        cursor.execute(
            """
            SELECT order_id, customer_data, delivery_data
            FROM order_ledger
            WHERE trace_id = %s::uuid
            FOR UPDATE
            """,
            (trace_id,),
        )
        order_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT id, address_snapshot
            FROM shipments
            WHERE trace_id = %s::uuid
            FOR UPDATE
            """,
            (trace_id,),
        )
        shipment_rows = cursor.fetchall()

        order_updates = 0
        shipment_updates = 0

        for order_id, customer_data, delivery_data in order_rows:
            customer = _parse_jsonb(customer_data)
            delivery = _parse_jsonb(delivery_data)
            customer_redacted = _redact_dict_fields(
                customer,
                fields=("name", "phone", "email", "address", "inn"),
                salt=redaction_salt,
            )
            delivery_redacted = _redact_dict_fields(
                delivery,
                fields=("name", "phone", "email", "address"),
                salt=redaction_salt,
            )
            if customer_redacted != customer or delivery_redacted != delivery:
                cursor.execute(
                    """
                    UPDATE order_ledger
                    SET customer_data = %s::jsonb,
                        delivery_data = %s::jsonb,
                        updated_at = NOW()
                    WHERE order_id = %s::uuid
                    """,
                    (
                        json.dumps(customer_redacted, ensure_ascii=False),
                        json.dumps(delivery_redacted, ensure_ascii=False),
                        str(order_id),
                    ),
                )
                order_updates += 1

        for shipment_id, address_snapshot in shipment_rows:
            snapshot = _parse_jsonb(address_snapshot)
            snapshot_redacted = _redact_dict_fields(
                snapshot,
                fields=("recipient_name", "recipient_phone", "raw"),
                salt=redaction_salt,
            )
            if snapshot_redacted != snapshot:
                cursor.execute(
                    """
                    UPDATE shipments
                    SET address_snapshot = %s::jsonb,
                        updated_at = NOW()
                    WHERE id = %s::uuid
                    """,
                    (json.dumps(snapshot_redacted, ensure_ascii=False), str(shipment_id)),
                )
                shipment_updates += 1

        _insert_redaction_decision(
            db_conn,
            trace_id,
            payload={
                "legal_basis": legal_basis,
                "requested_by": requested_by,
                "order_updates": order_updates,
                "shipment_updates": shipment_updates,
                "supported_keys": sorted(_SUPPORTED_KEYS),
            },
        )
        db_conn.commit()
        return {
            "status": "redacted",
            "trace_id": trace_id,
            "order_updates": order_updates,
            "shipment_updates": shipment_updates,
            "legal_basis": legal_basis,
        }
    except Exception:
        db_conn.rollback()
        raise
    finally:
        cursor.close()


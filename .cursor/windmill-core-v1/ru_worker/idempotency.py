#!/usr/bin/env python3
"""
Persistent idempotency helpers for side-effect actions.

Variant 2: single source of truth in action_idempotency_log.
"""

import hashlib
import json
import time
from typing import Any, Dict, Optional
from uuid import uuid4


READ_ONLY_ACTIONS = {"tbank_invoice_status", "tbank_invoices_list"}
IDEMPOTENT_ACTIONS = {"ship_paid", "cdek_shipment", "tbank_payment"}

EXCLUDED_HASH_KEYS = {
    "trace_id",
    "timestamp",
    "source",
    "metadata",
    "worker_id",
    "retry_count",
    "chat_id",
    "user_id",
}


def _log_event(event: str, data: Dict[str, Any]) -> None:
    entry = {"event": event, "timestamp": time.time(), **data}
    print(json.dumps(entry), flush=True)


def _normalize_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return {}


def _normalize_amount(amount: Any) -> Optional[str]:
    if amount is None:
        return None
    text = str(amount).strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except Exception:
        return None
    if numeric <= 0:
        return None
    return text


def _strip_non_business_fields(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, val in value.items():
            if key in EXCLUDED_HASH_KEYS:
                continue
            cleaned[key] = _strip_non_business_fields(val)
        return cleaned
    if isinstance(value, list):
        return [_strip_non_business_fields(item) for item in value]
    return value


def _sha256_json(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_idempotency_key(action: Dict[str, Any]) -> Optional[str]:
    action_type = action.get("action_type")
    payload = _normalize_payload(action.get("payload"))

    if action_type in READ_ONLY_ACTIONS:
        return None

    if action_type == "auto_ship_all_paid":
        return None

    if action_type == "ship_paid":
        invoice_id = str(payload.get("invoice_id", "")).strip()
        if not invoice_id:
            return None
        return f"ship_paid:{invoice_id}"

    if action_type == "cdek_shipment":
        invoice_id = str(payload.get("invoice_id", "")).strip()
        if invoice_id:
            return f"cdek_shipment:{invoice_id}"
        canonical_payload = _strip_non_business_fields(payload)
        return f"cdek_shipment:{_sha256_json(canonical_payload)}"

    if action_type == "tbank_payment":
        amount = _normalize_amount(payload.get("amount"))
        currency = str(payload.get("currency", "")).strip().upper()
        if not amount or not currency:
            return None
        return f"tbank_payment:{amount}:{currency}"

    return None


def compute_request_hash(action_type: str, payload: Dict[str, Any]) -> str:
    normalized_payload = _normalize_payload(payload)

    if action_type == "ship_paid":
        canonical = {"invoice_id": str(normalized_payload.get("invoice_id", "")).strip()}
        return _sha256_json(canonical)

    if action_type == "tbank_payment":
        canonical = {
            "amount": _normalize_amount(normalized_payload.get("amount")),
            "currency": str(normalized_payload.get("currency", "")).strip().upper(),
        }
        return _sha256_json(canonical)

    if action_type == "cdek_shipment":
        invoice_id = str(normalized_payload.get("invoice_id", "")).strip()
        if invoice_id:
            canonical = {"invoice_id": invoice_id}
        else:
            canonical = _strip_non_business_fields(normalized_payload)
        return _sha256_json(canonical)

    canonical_default = _strip_non_business_fields(normalized_payload)
    return _sha256_json(canonical_default)


def acquire_action_lock(
    db_conn,
    idempotency_key: str,
    action_type: str,
    request_hash: str,
    trace_id: Optional[str],
    ttl_seconds: int = 300,
) -> Dict[str, Any]:
    if ttl_seconds < 1:
        ttl_seconds = 1

    lease_token = str(uuid4())
    cursor = db_conn.cursor()

    try:
        # Step 1: optimistic insert.
        cursor.execute(
            """
            INSERT INTO action_idempotency_log (
                idempotency_key,
                action_type,
                request_hash,
                status,
                lease_token,
                acquired_at,
                expires_at,
                attempt_count,
                trace_id,
                created_at,
                updated_at
            )
            VALUES (
                %s,
                %s,
                %s,
                'processing',
                %s::uuid,
                NOW(),
                NOW() + (%s * INTERVAL '1 second'),
                1,
                %s::uuid,
                NOW(),
                NOW()
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            """,
            (idempotency_key, action_type, request_hash, lease_token, ttl_seconds, trace_id),
        )

        if cursor.rowcount == 1:
            db_conn.commit()
            _log_event(
                "action_lock_acquired",
                {
                    "idempotency_key": idempotency_key,
                    "action_type": action_type,
                    "attempt_count": 1,
                    "trace_id": trace_id,
                    "lock_status": "acquired",
                },
            )
            return {"status": "ACQUIRED", "lease_token": lease_token, "attempt_count": 1}

        # Step 2: deterministic branch under row-level lock.
        cursor.execute(
            """
            SELECT status, expires_at, result_ref, last_error, attempt_count
            FROM action_idempotency_log
            WHERE idempotency_key = %s
            FOR UPDATE
            """,
            (idempotency_key,),
        )
        row = cursor.fetchone()
        if not row:
            db_conn.rollback()
            raise RuntimeError(f"Idempotency row disappeared for key: {idempotency_key}")

        status, expires_at, result_ref, last_error, attempt_count = row

        cursor.execute("SELECT NOW()")
        now_ts = cursor.fetchone()[0]

        if status == "succeeded":
            db_conn.rollback()
            _log_event(
                "action_duplicate_detected",
                {
                    "idempotency_key": idempotency_key,
                    "action_type": action_type,
                    "existing_status": "succeeded",
                    "trace_id": trace_id,
                },
            )
            return {
                "status": "DUPLICATE_SUCCEEDED",
                "result_ref": result_ref,
                "attempt_count": attempt_count,
            }

        if status == "failed":
            db_conn.rollback()
            _log_event(
                "action_duplicate_detected",
                {
                    "idempotency_key": idempotency_key,
                    "action_type": action_type,
                    "existing_status": "failed",
                    "trace_id": trace_id,
                },
            )
            return {
                "status": "DUPLICATE_FAILED",
                "last_error": last_error,
                "attempt_count": attempt_count,
            }

        if status != "processing":
            db_conn.rollback()
            raise RuntimeError(f"Unexpected idempotency status for {idempotency_key}: {status}")

        if expires_at >= now_ts:
            db_conn.rollback()
            _log_event(
                "action_duplicate_detected",
                {
                    "idempotency_key": idempotency_key,
                    "action_type": action_type,
                    "existing_status": "processing",
                    "trace_id": trace_id,
                },
            )
            return {
                "status": "DUPLICATE_PROCESSING",
                "attempt_count": attempt_count,
            }

        new_lease_token = str(uuid4())
        next_attempt = int(attempt_count or 0) + 1
        cursor.execute(
            """
            UPDATE action_idempotency_log
            SET lease_token = %s::uuid,
                expires_at = NOW() + (%s * INTERVAL '1 second'),
                attempt_count = %s,
                request_hash = %s,
                trace_id = %s::uuid,
                updated_at = NOW()
            WHERE idempotency_key = %s
              AND status = 'processing'
            """,
            (new_lease_token, ttl_seconds, next_attempt, request_hash, trace_id, idempotency_key),
        )
        if cursor.rowcount != 1:
            db_conn.rollback()
            raise RuntimeError(f"Failed stale-lock takeover for key: {idempotency_key}")

        db_conn.commit()
        _log_event(
            "action_stale_lock_takeover",
            {
                "idempotency_key": idempotency_key,
                "action_type": action_type,
                "attempt_count": next_attempt,
                "trace_id": trace_id,
            },
        )
        _log_event(
            "action_lock_acquired",
            {
                "idempotency_key": idempotency_key,
                "action_type": action_type,
                "attempt_count": next_attempt,
                "trace_id": trace_id,
                "lock_status": "stale_takeover",
            },
        )
        if next_attempt > 3:
            _log_event(
                "action_excessive_retakes",
                {
                    "idempotency_key": idempotency_key,
                    "action_type": action_type,
                    "attempt_count": next_attempt,
                    "trace_id": trace_id,
                },
            )

        return {
            "status": "STALE_TAKEOVER",
            "lease_token": new_lease_token,
            "attempt_count": next_attempt,
        }
    except Exception:
        db_conn.rollback()
        raise
    finally:
        cursor.close()


def complete_action(
    db_conn,
    idempotency_key: str,
    lease_token: str,
    status: str,
    result_ref: Optional[Dict[str, Any]] = None,
    last_error: Optional[str] = None,
) -> bool:
    if status not in {"succeeded", "failed"}:
        raise ValueError(f"Unsupported completion status: {status}")

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE action_idempotency_log
            SET status = %s,
                result_ref = %s::jsonb,
                last_error = %s,
                expires_at = '1970-01-01 00:00:00+00'::timestamptz,
                updated_at = NOW()
            WHERE idempotency_key = %s
              AND status = 'processing'
              AND lease_token = %s::uuid
            """,
            (
                status,
                json.dumps(result_ref, ensure_ascii=False) if result_ref is not None else None,
                last_error,
                idempotency_key,
                lease_token,
            ),
        )

        if cursor.rowcount == 1:
            db_conn.commit()
            _log_event(
                "action_completed",
                {"idempotency_key": idempotency_key, "outcome_status": status},
            )
            return True

        db_conn.rollback()
        _log_event(
            "action_zombie_completion_ignored",
            {
                "idempotency_key": idempotency_key,
                "lease_token": lease_token,
                "attempted_status": status,
            },
        )
        return False
    except Exception:
        db_conn.rollback()
        raise
    finally:
        cursor.close()


def sweep_expired_locks(db_conn) -> int:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE action_idempotency_log
            SET status = 'failed',
                last_error = 'lock_expired_by_sweeper',
                lease_token = gen_random_uuid(),
                updated_at = NOW()
            WHERE status = 'processing'
              AND expires_at < NOW()
            RETURNING idempotency_key, action_type, attempt_count, trace_id
            """
        )
        rows = cursor.fetchall()
        db_conn.commit()

        for key, action_type, attempt_count, trace_id in rows:
            _log_event(
                "action_lock_expired",
                {
                    "idempotency_key": key,
                    "action_type": action_type,
                    "attempt_count": attempt_count,
                    "trace_id": str(trace_id) if trace_id is not None else None,
                },
            )
        return len(rows)
    except Exception:
        db_conn.rollback()
        raise
    finally:
        cursor.close()

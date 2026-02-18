from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional
from uuid import UUID


HASH_ALGORITHM_VERSION = "v1"
_EXCLUDED_HASH_KEYS = {"_schema_version", "generated_at", "document_id"}


def _ensure_tx_connection(db_conn) -> None:
    if getattr(db_conn, "autocommit", False):
        raise RuntimeError("DocumentService requires autocommit=False")


def _normalize_number(value: float | int | Decimal) -> int | float:
    if isinstance(value, int):
        return value
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return float(value)
    quantized = dec.quantize(Decimal("0.01"))
    if quantized == quantized.to_integral():
        return int(quantized)
    # Keep numeric form in canonical JSON, no scientific notation.
    return float(format(quantized, "f"))


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: Dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in _EXCLUDED_HASH_KEYS:
                continue
            normalized[str(key)] = _canonicalize(value[key])
        return normalized
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (int, float, Decimal)):
        return _normalize_number(value)
    return value


def canonical_json_for_hash(content_snapshot: Dict[str, Any]) -> str:
    normalized = _canonicalize(content_snapshot)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_content_hash(content_snapshot: Dict[str, Any]) -> str:
    payload = canonical_json_for_hash(content_snapshot)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_generation_key(order_id: UUID, content_snapshot: Dict[str, Any]) -> str:
    short_hash = compute_content_hash(content_snapshot)[:16]
    return f"invoice:{order_id}:{short_hash}"


def upsert_document_by_content_hash_atomic(
    db_conn,
    *,
    order_id: UUID,
    trace_id: Optional[str],
    document_type: str,
    document_number: str,
    status: str,
    provider_code: Optional[str],
    amount_minor: Optional[int],
    currency: Optional[str],
    content_snapshot: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    UC-4 (v2.1):
    generation_key must be deterministic and content-hash based.
    """
    _ensure_tx_connection(db_conn)
    generation_key = build_generation_key(order_id, content_snapshot)

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, revision, status, generation_key
            FROM documents
            WHERE generation_key = %s
            LIMIT 1
            FOR UPDATE
            """,
            (generation_key,),
        )
        existing = cursor.fetchone()
        if existing:
            return {
                "action": "duplicate",
                "document_id": str(existing[0]),
                "revision": int(existing[1]),
                "status": str(existing[2]),
                "generation_key": str(existing[3]),
                "hash_algorithm_version": HASH_ALGORITHM_VERSION,
            }

        cursor.execute(
            """
            SELECT COALESCE(MAX(revision), 0)
            FROM documents
            WHERE order_id = %s
              AND document_type = %s
            FOR UPDATE
            """,
            (str(order_id), document_type),
        )
        next_revision = int(cursor.fetchone()[0]) + 1

        cursor.execute(
            """
            INSERT INTO documents (
                order_id, trace_id, document_type, document_number, revision, status,
                provider_code, generation_key, hash_algorithm_version, amount_minor, currency,
                content_snapshot, metadata, created_at, updated_at
            )
            VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW(), NOW())
            RETURNING id
            """,
            (
                str(order_id),
                trace_id,
                document_type,
                document_number,
                next_revision,
                status,
                provider_code,
                generation_key,
                HASH_ALGORITHM_VERSION,
                amount_minor,
                currency,
                json.dumps(content_snapshot, ensure_ascii=False),
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        document_id = str(cursor.fetchone()[0])

        if status == "issued":
            cursor.execute(
                """
                UPDATE documents
                SET status = 'superseded',
                    updated_at = NOW()
                WHERE order_id = %s
                  AND document_type = %s
                  AND status = 'issued'
                  AND id <> %s
                """,
                (str(order_id), document_type, document_id),
            )

        cursor.execute(
            """
            UPDATE order_ledger
            SET invoice_request_key = CASE
                WHEN %s = 'invoice' THEN %s
                ELSE invoice_request_key
            END,
                revision = CASE
                WHEN %s = 'invoice' THEN %s
                ELSE revision
            END,
                updated_at = NOW()
            WHERE order_id = %s
            """,
            (document_type, generation_key, document_type, next_revision, str(order_id)),
        )

        return {
            "action": "created",
            "document_id": document_id,
            "revision": next_revision,
            "status": status,
            "generation_key": generation_key,
            "hash_algorithm_version": HASH_ALGORITHM_VERSION,
        }
    finally:
        cursor.close()


def attach_provider_result_atomic(
    db_conn,
    *,
    document_id: UUID,
    provider_document_id: str,
    pdf_url: Optional[str],
    raw_provider_response: Dict[str, Any],
) -> None:
    _ensure_tx_connection(db_conn)
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE documents
            SET provider_document_id = %s,
                pdf_url = %s,
                raw_provider_response = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
            """,
            (provider_document_id, pdf_url, json.dumps(raw_provider_response, ensure_ascii=False), str(document_id)),
        )
    finally:
        cursor.close()


from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

MAX_RETRIES = 3


def compute_content_hash(payload: dict) -> str:
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _require_tx_connection(db_conn):
    if getattr(db_conn, "autocommit", False):
        raise RuntimeError("autocommit connection is not allowed")


def insert_shopware_operation_idempotent(
    db_conn,
    product_number: str,
    payload: dict,
) -> Dict[str, Any]:
    _require_tx_connection(db_conn)
    content_hash = compute_content_hash(payload)
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=10)

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO shopware_operations (
                id,
                product_number,
                content_hash,
                status,
                error,
                attempt,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, 'pending', NULL, 0, %s, %s)
            ON CONFLICT (product_number, content_hash)
            DO NOTHING
            RETURNING id
            """,
            (str(uuid4()), product_number, content_hash, now, now),
        )
        inserted_row = cursor.fetchone()
        if inserted_row:
            return {"mode": "new", "operation_id": str(inserted_row[0])}

        cursor.execute(
            """
            SELECT id, status, attempt, updated_at
            FROM shopware_operations
            WHERE product_number = %s AND content_hash = %s
            LIMIT 1
            """,
            (product_number, content_hash),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("shopware operation conflict without visible row")

        existing_id, status, attempt, updated_at = row
        if status == "pending" and updated_at is not None:
            if getattr(updated_at, "tzinfo", None) is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            if updated_at < stale_before:
                cursor.execute(
                    """
                    UPDATE shopware_operations
                    SET status = 'pending',
                        attempt = attempt + 1,
                        error = NULL
                    WHERE id = %s
                    RETURNING id
                    """,
                    (existing_id,),
                )
                takeover_row = cursor.fetchone()
                if takeover_row:
                    return {"mode": "takeover", "operation_id": str(takeover_row[0])}

        if status == "failed":
            attempt_value = int(attempt or 0)
            if attempt_value < MAX_RETRIES:
                cursor.execute(
                    """
                    UPDATE shopware_operations
                    SET status = 'pending',
                        attempt = attempt + 1,
                        error = NULL
                    WHERE id = %s
                    RETURNING id
                    """,
                    (existing_id,),
                )
                retry_row = cursor.fetchone()
                if retry_row:
                    return {"mode": "takeover", "operation_id": str(retry_row[0])}

        return {"mode": "skip", "operation_id": str(existing_id)}
    finally:
        cursor.close()


def mark_shopware_operation_status(
    db_conn,
    operation_id: str,
    status: str,
    error: Optional[str] = None,
) -> None:
    _require_tx_connection(db_conn)
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE shopware_operations
            SET status = %s,
                error = %s
            WHERE id = %s
            """,
            (status, error, operation_id),
        )
    finally:
        cursor.close()

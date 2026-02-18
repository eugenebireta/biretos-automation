"""
RFQ idempotency helpers for ADR-008.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


logger = logging.getLogger(__name__)

TRACE_ID_PAYLOAD_KEY = "_trace_id"
RFQ_ID_PAYLOAD_KEY = "rfq_id"


@dataclass(frozen=True)
class RFQExecutionMode:
    mode: str  # "full" | "re_enrich"
    trace_id: UUID
    existing_rfq_id: Optional[UUID] = None


@dataclass(frozen=True)
class RFQInsertResult:
    rfq_id: UUID
    is_new: bool


def _require_tx_connection(db_conn, location: str) -> None:
    if db_conn.autocommit:
        raise RuntimeError(f"{location} requires autocommit=False")


def _parse_uuid(value: Any, field_name: str) -> Optional[UUID]:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except Exception as e:
        raise RuntimeError(f"Invalid UUID in payload field '{field_name}': {value}") from e


def _select_rfq_id_by_trace_id(db_conn, trace_id: UUID) -> Optional[UUID]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id
            FROM rfq_requests
            WHERE trace_id = %s
            LIMIT 1
            """,
            (trace_id,),
        )
        row = cursor.fetchone()
        return UUID(str(row[0])) if row else None
    finally:
        cursor.close()


def _ensure_rfq_exists(db_conn, rfq_id: UUID) -> None:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id
            FROM rfq_requests
            WHERE id = %s
            LIMIT 1
            """,
            (rfq_id,),
        )
        if not cursor.fetchone():
            raise RuntimeError(f"rfq_id not found: {rfq_id}")
    finally:
        cursor.close()


def resolve_execution_mode(db_conn, payload: Dict[str, Any]) -> RFQExecutionMode:
    """
    Resolve full vs re-enrich execution mode.

    IMPORTANT:
    - Read-only function (no commit/rollback).
    - No payload mutation.
    """
    _require_tx_connection(db_conn, "resolve_execution_mode")

    if not isinstance(payload, dict):
        raise RuntimeError("payload must be a dict")

    payload_trace_id = _parse_uuid(payload.get(TRACE_ID_PAYLOAD_KEY), TRACE_ID_PAYLOAD_KEY)
    payload_rfq_id = _parse_uuid(payload.get(RFQ_ID_PAYLOAD_KEY), RFQ_ID_PAYLOAD_KEY)

    if payload_rfq_id is not None:
        _ensure_rfq_exists(db_conn, payload_rfq_id)
        return RFQExecutionMode(
            mode="re_enrich",
            trace_id=payload_trace_id or uuid4(),
            existing_rfq_id=payload_rfq_id,
        )

    if payload_trace_id is not None:
        existing_rfq_id = _select_rfq_id_by_trace_id(db_conn, payload_trace_id)
        if existing_rfq_id is not None:
            return RFQExecutionMode(
                mode="re_enrich",
                trace_id=payload_trace_id,
                existing_rfq_id=existing_rfq_id,
            )
        return RFQExecutionMode(mode="full", trace_id=payload_trace_id, existing_rfq_id=None)

    return RFQExecutionMode(mode="full", trace_id=uuid4(), existing_rfq_id=None)


def insert_rfq_idempotent(
    db_conn,
    rfq_id: UUID,
    source: str,
    raw_text: str,
    parsed_json: Dict[str, Any],
    trace_id: UUID,
) -> RFQInsertResult:
    """
    Idempotent insert into rfq_requests.

    SQL pattern (MANDATORY):
    - INSERT ... ON CONFLICT(trace_id) DO NOTHING RETURNING id
    - SELECT fallback
    - Single retry on phantom conflict

    This function MUST NOT commit.
    """
    _require_tx_connection(db_conn, "insert_rfq_idempotent")

    serialized_parsed_json = (
        parsed_json if isinstance(parsed_json, str) else json.dumps(parsed_json, ensure_ascii=False)
    )
    cursor = db_conn.cursor()
    try:
        insert_sql = """
            INSERT INTO rfq_requests (id, source, raw_text, parsed_json, status, trace_id)
            VALUES (%s, %s, %s, %s, 'processed', %s)
            ON CONFLICT (trace_id) WHERE trace_id IS NOT NULL
            DO NOTHING
            RETURNING id
        """

        def _attempt_insert(insert_id: UUID) -> Optional[UUID]:
            cursor.execute(
                insert_sql,
                (insert_id, source, raw_text, serialized_parsed_json, trace_id),
            )
            row = cursor.fetchone()
            return UUID(str(row[0])) if row else None

        inserted_id = _attempt_insert(rfq_id)
        if inserted_id is not None:
            return RFQInsertResult(rfq_id=inserted_id, is_new=True)

        existing_rfq_id = _select_rfq_id_by_trace_id(db_conn, trace_id)
        if existing_rfq_id is not None:
            return RFQInsertResult(rfq_id=existing_rfq_id, is_new=False)

        inserted_id_retry = _attempt_insert(rfq_id)
        if inserted_id_retry is not None:
            return RFQInsertResult(rfq_id=inserted_id_retry, is_new=True)

        existing_rfq_id_retry = _select_rfq_id_by_trace_id(db_conn, trace_id)
        if existing_rfq_id_retry is not None:
            return RFQInsertResult(rfq_id=existing_rfq_id_retry, is_new=False)

        raise RuntimeError(
            "insert_rfq_idempotent: irrecoverable state (conflict without visible row)"
        )
    finally:
        cursor.close()


def insert_price_log(db_conn, rfq_id: UUID, price_result: Dict[str, Any]) -> bool:
    """
    Persist price audit as append-only rfq_price_log row.

    Manages its own transaction:
    - commit on success
    - rollback + structured log on failure
    """
    _require_tx_connection(db_conn, "insert_price_log")

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO rfq_price_log (
                id,
                rfq_id,
                run_at,
                status,
                items_total,
                items_found,
                error,
                audit_data
            )
            VALUES (
                gen_random_uuid(),
                %s,
                NOW(),
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                rfq_id,
                price_result.get("price_status", "error"),
                int(price_result.get("price_items_total", 0) or 0),
                int(price_result.get("price_items_found", 0) or 0),
                price_result.get("price_error"),
                json.dumps(price_result.get("price_audit"), ensure_ascii=False),
            ),
        )
        db_conn.commit()
        return True
    except Exception as e:
        try:
            db_conn.rollback()
        except Exception:
            pass
        logger.error(
            "RFQ_PRICE_LOG_PERSIST_FAILURE",
            extra={
                "event": "RFQ_PRICE_LOG_PERSIST_FAILURE",
                "rfq_id": str(rfq_id),
                "trace_id": price_result.get(TRACE_ID_PAYLOAD_KEY),
                "error": str(e),
            },
        )
        return False
    finally:
        cursor.close()

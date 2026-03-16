#!/usr/bin/env python3
"""
Phase C: Shopware Sync Orchestrator.

Consumes shopware_outbound_queue and applies side-effects to Shopware API with
retry/backoff and per-row idempotent queue keys.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

from config import get_config
from ru_worker.shopware_api_client import ShopwareApiClient, ShopwareApiError

logger = logging.getLogger(__name__)


def _instance_config(instance: str) -> Any:
    cfg = get_config()
    suffix = "RU" if instance == "ru" else "INT"
    url = (os.getenv(f"SHOPWARE_{suffix}_URL") or "").strip()
    client_id = (os.getenv(f"SHOPWARE_{suffix}_CLIENT_ID") or "").strip()
    client_secret = (os.getenv(f"SHOPWARE_{suffix}_CLIENT_SECRET") or "").strip()
    missing = []
    if not url:
        missing.append(f"SHOPWARE_{suffix}_URL")
    if not client_id:
        missing.append(f"SHOPWARE_{suffix}_CLIENT_ID")
    if not client_secret:
        missing.append(f"SHOPWARE_{suffix}_CLIENT_SECRET")
    if missing:
        raise RuntimeError(f"Instance isolation violation, missing credentials: {', '.join(missing)}")
    return SimpleNamespace(
        shopware_url=url,
        shopware_client_id=client_id,
        shopware_client_secret=client_secret,
        shopware_timeout_seconds=cfg.shopware_timeout_seconds,
        shopware_enable_dry_run=cfg.shopware_enable_dry_run,
    )


def _next_retry_time(attempt_count: int) -> datetime:
    # 5s, 30s, 120s, 300s...
    schedule = [5, 30, 120, 300]
    idx = min(max(0, attempt_count - 1), len(schedule) - 1)
    return datetime.now(timezone.utc) + timedelta(seconds=schedule[idx])


def _claim_batch(db_conn, batch_size: int) -> List[Dict[str, Any]]:
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, instance, entity_type, entity_id, payload, attempt_count
            FROM shopware_outbound_queue
            WHERE status IN ('pending', 'failed')
              AND next_retry_at <= NOW()
            ORDER BY created_at ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (batch_size,),
        )
        rows = cur.fetchall() or []
        claimed: List[Dict[str, Any]] = []
        for row in rows:
            queue_id, instance, entity_type, entity_id, payload, attempt_count = row
            cur.execute(
                """
                UPDATE shopware_outbound_queue
                SET status = 'processing',
                    updated_at = NOW()
                WHERE id = %s::uuid
                """,
                (str(queue_id),),
            )
            if isinstance(payload, str):
                payload = json.loads(payload)
            claimed.append(
                {
                    "id": str(queue_id),
                    "instance": instance,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "payload": payload if isinstance(payload, dict) else {},
                    "attempt_count": int(attempt_count or 0),
                }
            )
        return claimed
    finally:
        cur.close()


def _mark_confirmed(db_conn, queue_id: str, attempt_count: int) -> None:
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            UPDATE shopware_outbound_queue
            SET status = 'confirmed',
                attempt_count = %s,
                last_error = NULL,
                updated_at = NOW()
            WHERE id = %s::uuid
            """,
            (attempt_count, queue_id),
        )
    finally:
        cur.close()


def _mark_failed(db_conn, queue_id: str, attempt_count: int, error: str) -> None:
    next_retry = _next_retry_time(attempt_count)
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            UPDATE shopware_outbound_queue
            SET status = 'failed',
                attempt_count = %s,
                last_error = %s,
                next_retry_at = %s,
                updated_at = NOW()
            WHERE id = %s::uuid
            """,
            (attempt_count, error[:2000], next_retry, queue_id),
        )
    finally:
        cur.close()


def _dispatch_row(client: ShopwareApiClient, row: Dict[str, Any]) -> None:
    entity_type = row["entity_type"]
    payload = row["payload"]

    if entity_type in {"product", "price", "stock"}:
        client.upsert_product(payload)
        return
    if entity_type == "order_status":
        client.sync_order_state(
            order_number=str(payload.get("order_number") or row["entity_id"]),
            target_core_state=str(payload.get("target_core_state") or "pending_payment"),
        )
        return
    raise ShopwareApiError(f"Unsupported outbound entity_type: {entity_type}")


def run_shopware_sync_orchestrator(db_conn, *, batch_size: int = 20) -> Dict[str, Any]:
    rows = _claim_batch(db_conn, batch_size=batch_size)
    confirmed = 0
    failed = 0

    for row in rows:
        cfg = _instance_config(str(row["instance"]))
        client = ShopwareApiClient(cfg, logger=logger)
        try:
            _dispatch_row(client, row)
            _mark_confirmed(db_conn, row["id"], row["attempt_count"] + 1)
            confirmed += 1
        except Exception as exc:  # noqa: BLE001
            _mark_failed(db_conn, row["id"], row["attempt_count"] + 1, str(exc))
            failed += 1
        finally:
            client.close()

    db_conn.commit()
    return {"processed": len(rows), "confirmed": confirmed, "failed": failed}

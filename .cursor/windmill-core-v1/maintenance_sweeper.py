from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Dict, Iterable, List
from uuid import UUID, uuid4

from psycopg2.pool import SimpleConnectionPool

from config import get_config
from domain import observability_service as observability
from domain import reconciliation_service as reconciliation
from side_effects.adapters.cdek_adapter import CDEKShipmentAdapter
from side_effects.adapters.tbank_adapter import TBankInvoiceAdapter
from ru_worker.lib_integrations import log_event


TERMINAL_STATES = ("completed", "cancelled", "failed")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _build_pool() -> SimpleConnectionPool:
    config = get_config()
    db_pool_min = _env_int("MAINTENANCE_DB_POOL_MIN", 1)
    db_pool_max = max(db_pool_min, _env_int("MAINTENANCE_DB_POOL_MAX", 3))
    return SimpleConnectionPool(
        minconn=db_pool_min,
        maxconn=db_pool_max,
        host=config.postgres_host or "localhost",
        port=config.postgres_port or 5432,
        dbname=config.postgres_db or "biretos_automation",
        user=config.postgres_user or "biretos_user",
        password=config.postgres_password,
    )


def _run_select(conn, query: str, params=()) -> List[tuple]:
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        return list(cursor.fetchall())
    finally:
        cursor.close()


def _log_verdict(verdict: Dict[str, object]) -> None:
    log_event("phase25_invariant_verdict", verdict)


def _run_rc(conn, *, event_name: str, fn, kwargs: Dict[str, object]) -> Dict[str, object]:
    try:
        result = fn(conn, **kwargs)
        if hasattr(conn, "commit"):
            conn.commit()
        log_event(event_name, {"result": result, "trace_id": kwargs.get("trace_id")})
        return {"ok": True, "result": result}
    except Exception as exc:
        if hasattr(conn, "rollback"):
            conn.rollback()
        payload = {"error": str(exc), "trace_id": kwargs.get("trace_id"), "rc": event_name}
        log_event("phase25_reconciliation_error", payload)
        return {"ok": False, "error": str(exc)}


def _scan_active_orders(conn, *, limit: int) -> List[UUID]:
    rows = _run_select(
        conn,
        """
        SELECT order_id
        FROM order_ledger
        WHERE state NOT IN %s
        ORDER BY updated_at DESC NULLS LAST
        LIMIT %s
        """,
        (TERMINAL_STATES, limit),
    )
    return [UUID(str(row[0])) for row in rows]


def _scan_stock_targets(conn, *, limit: int) -> List[tuple[UUID, str]]:
    rows = _run_select(
        conn,
        """
        SELECT product_id, warehouse_code
        FROM availability_snapshot
        ORDER BY updated_at DESC NULLS LAST
        LIMIT %s
        """,
        (limit,),
    )
    return [(UUID(str(row[0])), str(row[1])) for row in rows]


def _scan_line_items(conn, *, order_id: UUID, limit: int) -> List[UUID]:
    rows = _run_select(
        conn,
        """
        SELECT id
        FROM order_line_items
        WHERE order_id = %s
          AND line_status IN ('reserved', 'allocated')
        ORDER BY line_seq ASC
        LIMIT %s
        """,
        (str(order_id), limit),
    )
    return [UUID(str(row[0])) for row in rows]


def _scan_active_shipments(conn, *, order_id: UUID, limit: int) -> List[UUID]:
    rows = _run_select(
        conn,
        """
        SELECT id
        FROM shipments
        WHERE order_id = %s
          AND carrier_code = 'cdek'
          AND current_status NOT IN ('cancelled', 'delivered', 'returned')
          AND carrier_external_id IS NOT NULL
        ORDER BY updated_at DESC NULLS LAST
        LIMIT %s
        """,
        (str(order_id), limit),
    )
    return [UUID(str(row[0])) for row in rows]


def _process_order(
    conn,
    *,
    order_id: UUID,
    trace_id: str,
    cdek_adapter: CDEKShipmentAdapter,
) -> None:
    verdicts = observability.collect_order_invariant_verdicts(
        conn,
        order_id=order_id,
        trace_id=trace_id,
    )
    for verdict in verdicts:
        _log_verdict(verdict)

    for line_item_id in _scan_line_items(
        conn,
        order_id=order_id,
        limit=_env_int("MAINTENANCE_LINE_ITEM_CHECK_LIMIT", 50),
    ):
        verdict = observability.check_reservation_line_item_consistency(
            conn,
            order_id=order_id,
            line_item_id=line_item_id,
            trace_id=trace_id,
        )
        _log_verdict(verdict)

    for verdict in verdicts:
        if verdict.get("check_name") == "IC-1" and verdict.get("verdict") == "FAIL":
            _run_rc(
                conn,
                event_name="phase25_rc1_reconcile_payment_cache",
                fn=reconciliation.reconcile_payment_cache,
                kwargs={"order_id": order_id, "trace_id": trace_id},
            )
        elif verdict.get("check_name") == "IC-2" and verdict.get("verdict") == "FAIL":
            _run_rc(
                conn,
                event_name="phase25_rc2_reconcile_shipment_cache",
                fn=reconciliation.reconcile_shipment_cache,
                kwargs={"order_id": order_id, "trace_id": trace_id},
            )
        elif verdict.get("check_name") == "IC-5" and verdict.get("verdict") == "FAIL":
            _run_rc(
                conn,
                event_name="phase25_rc5_reconcile_document_key",
                fn=reconciliation.reconcile_document_key,
                kwargs={"order_id": order_id, "trace_id": trace_id},
            )
        elif verdict.get("check_name") == "IC-7" and verdict.get("verdict") == "STALE":
            for shipment_id in _scan_active_shipments(
                conn,
                order_id=order_id,
                limit=_env_int("MAINTENANCE_SHIPMENT_SYNC_LIMIT", 5),
            ):
                _run_rc(
                    conn,
                    event_name="phase25_rc7_sync_shipment_status",
                    fn=reconciliation.sync_shipment_status,
                    kwargs={
                        "shipment_id": shipment_id,
                        "adapter": cdek_adapter,
                        "trace_id": trace_id,
                    },
                )


def _run_cycle(
    pool: SimpleConnectionPool,
    *,
    tbank_adapter: TBankInvoiceAdapter,
    cdek_adapter: CDEKShipmentAdapter,
) -> None:
    conn = pool.getconn()
    try:
        conn.autocommit = False
        trace_id = str(uuid4())
        now_ts = datetime.now(timezone.utc)

        ic8 = observability.check_zombie_reservations(conn, trace_id=trace_id, now_ts=now_ts)
        _log_verdict(ic8)
        ic9 = observability.check_orphan_payment_transactions(conn, trace_id=trace_id, now_ts=now_ts)
        _log_verdict(ic9)

        _run_rc(
            conn,
            event_name="phase25_rc4_expire_reservations",
            fn=reconciliation.expire_reservations,
            kwargs={
                "trace_id": trace_id,
                "batch_limit": _env_int("MAINTENANCE_RC4_BATCH_LIMIT", 100),
                "now": now_ts,
            },
        )

        if ic9.get("verdict") == "STALE":
            for tx in (ic9.get("details") or {}).get("sample", []):
                tx_id = tx.get("transaction_id")
                if not tx_id:
                    continue
                _run_rc(
                    conn,
                    event_name="phase25_rc6_resolve_pending_payment",
                    fn=reconciliation.resolve_pending_payment,
                    kwargs={
                        "payment_transaction_id": UUID(str(tx_id)),
                        "adapter": tbank_adapter,
                        "trace_id": trace_id,
                    },
                )

        active_order_limit = _env_int("MAINTENANCE_ACTIVE_ORDER_LIMIT", 100)
        for order_id in _scan_active_orders(conn, limit=active_order_limit):
            _process_order(
                conn,
                order_id=order_id,
                trace_id=trace_id,
                cdek_adapter=cdek_adapter,
            )

        stock_target_limit = _env_int("MAINTENANCE_STOCK_CHECK_LIMIT", 100)
        for product_id, warehouse_code in _scan_stock_targets(conn, limit=stock_target_limit):
            verdict = observability.check_stock_snapshot_integrity(
                conn,
                product_id=product_id,
                warehouse_code=warehouse_code,
                trace_id=trace_id,
            )
            _log_verdict(verdict)
            if verdict.get("verdict") == "FAIL":
                _run_rc(
                    conn,
                    event_name="phase25_rc3_rebuild_stock_snapshot",
                    fn=reconciliation.rebuild_stock_snapshot,
                    kwargs={
                        "product_id": product_id,
                        "warehouse_code": warehouse_code,
                        "trace_id": trace_id,
                    },
                )
    finally:
        pool.putconn(conn)


def main() -> None:
    interval_sec = _env_int("MAINTENANCE_SWEEP_INTERVAL", 60)
    pool = _build_pool()
    tbank_adapter = TBankInvoiceAdapter()
    cdek_adapter = CDEKShipmentAdapter()
    log_event(
        "phase25_sweeper_started",
        {
            "interval_sec": interval_sec,
            "active_order_limit": _env_int("MAINTENANCE_ACTIVE_ORDER_LIMIT", 100),
            "stock_check_limit": _env_int("MAINTENANCE_STOCK_CHECK_LIMIT", 100),
        },
    )
    try:
        while True:
            started = time.time()
            try:
                _run_cycle(
                    pool,
                    tbank_adapter=tbank_adapter,
                    cdek_adapter=cdek_adapter,
                )
            except Exception as exc:
                log_event("phase25_cycle_error", {"error": str(exc)})

            elapsed = time.time() - started
            delay = max(0.0, interval_sec - elapsed)
            time.sleep(delay)
    finally:
        pool.closeall()


if __name__ == "__main__":
    main()


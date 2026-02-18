#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from uuid import uuid4

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
_SMOKE_DEBUG_LOG_PATH = os.environ.get("SMOKE_DEBUG_LOG_PATH")
DEBUG_LOG_PATH = Path(_SMOKE_DEBUG_LOG_PATH) if _SMOKE_DEBUG_LOG_PATH else Path(
    r"c:\cursor_project\biretos-automation\.cursor\.cursor\debug.log"
)
MIGRATIONS_DIR = ROOT / "migrations"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "ru_worker") not in sys.path:
    sys.path.insert(0, str(ROOT / "ru_worker"))

psycopg2.extras.register_uuid()


def emit_debug(run_id: str, hypothesis_id: str, location: str, message: str, data: Dict[str, Any]) -> None:
    entry = {
        "id": f"log_{int(time.time() * 1000)}_{uuid4().hex[:8]}",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_db_env() -> Dict[str, str]:
    values = dotenv_values(ROOT / ".env")

    # CI uses environment variables; local runs can keep using .env.
    def pick(name: str, default: str) -> str:
        v = os.environ.get(name)
        if v:
            return v
        v2 = values.get(name)
        return str(v2) if v2 else default

    return {
        "host": pick("POSTGRES_HOST", "localhost"),
        "port": pick("POSTGRES_PORT", "5432"),
        "dbname": pick("POSTGRES_DB", "biretos_automation"),
        "user": pick("POSTGRES_USER", "biretos_user"),
        "password": pick("POSTGRES_PASSWORD", ""),
    }


def get_conn() -> psycopg2.extensions.connection:
    env = load_db_env()
    conn = psycopg2.connect(
        host=env["host"],
        port=env["port"],
        dbname=env["dbname"],
        user=env["user"],
        password=env["password"],
    )
    conn.autocommit = False
    return conn


def sql_all(conn, query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()


def sql_one(conn, query: str, params: Tuple[Any, ...] = ()) -> Dict[str, Any]:
    rows = sql_all(conn, query, params)
    return rows[0] if rows else {}


def prepare_env_for_imports() -> None:
    os.environ.setdefault("TBANK_API_TOKEN", "live-token")
    os.environ.setdefault("CDEK_API_TOKEN", "live-cdek-token")
    os.environ.setdefault("INSALES_API_USER", "live_user")
    os.environ.setdefault("INSALES_API_PASSWORD", "live_pass")
    os.environ.setdefault("REPLAY_TBANK_API_TOKEN", "replay-token")
    os.environ.setdefault("REPLAY_CDEK_API_TOKEN", "replay-cdek-token")
    os.environ.setdefault("REPLAY_INSALES_API_USER", "replay_user")
    os.environ.setdefault("REPLAY_INSALES_API_PASSWORD", "replay_pass")
    os.environ.setdefault("MAX_PRICE_DEVIATION", "0.10")
    os.environ.setdefault("ROUNDING_TOLERANCE", "1")
    os.environ.setdefault("MAX_INPUT_SIZE_BYTES", "102400")
    os.environ.setdefault("EXPECTED_TAX_RATES", '{"rates":[0,10,20]}')
    os.environ.setdefault("GATE_CHAIN_VERSION", "v3-final-smoke")
    os.environ.setdefault("EXECUTION_MODE", "LIVE")


def ensure_test_order_with_reservation(
    conn,
    *,
    order_id: str,
    trace_id: str,
    invoice_id: str,
    qty: int,
    product_id: str,
    line_item_id: str,
    warehouse_code: str = "MSK",
) -> None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO order_ledger (
                order_id, insales_order_id, invoice_request_key, tbank_invoice_id,
                state, state_history, customer_data, delivery_data, error_log, metadata, trace_id,
                created_at, updated_at
            ) VALUES (
                %s::uuid, %s, %s, %s, 'paid', %s::jsonb, %s::jsonb, %s::jsonb, '[]'::jsonb, %s::jsonb, %s::uuid,
                NOW(), NOW()
            )
            ON CONFLICT (order_id) DO UPDATE SET
                tbank_invoice_id = EXCLUDED.tbank_invoice_id,
                state = 'paid',
                trace_id = EXCLUDED.trace_id,
                updated_at = NOW()
            """,
            (
                order_id,
                f"ins-{order_id[:8]}",
                f"req-{order_id[:8]}",
                invoice_id,
                json.dumps([{"state": "paid", "timestamp": now_iso()}], ensure_ascii=False),
                json.dumps({"name": "Smoke User", "phone": "+70000000000", "email": "smoke@example.com", "inn": "7700000000"}, ensure_ascii=False),
                json.dumps({"name": "Smoke User", "address": "Smoke Addr"}, ensure_ascii=False),
                json.dumps({"totalAmount": 1000}, ensure_ascii=False),
                trace_id,
            ),
        )
        cur.execute(
            """
            INSERT INTO order_line_items (
                id, order_id, line_seq, product_id, sku_snapshot, name_snapshot,
                attributes_snapshot, quantity, price_unit_minor, tax_rate_bps, line_status, metadata, created_at, updated_at
            ) VALUES (
                %s::uuid, %s::uuid, 1, %s::uuid, %s, %s, '{}'::jsonb, %s, 10000, 2000, 'reserved', '{}'::jsonb, NOW(), NOW()
            )
            ON CONFLICT (id) DO NOTHING
            """,
            (line_item_id, order_id, product_id, f"SKU-{product_id[:8]}", "Smoke Product", qty),
        )
        cur.execute(
            """
            INSERT INTO availability_snapshot (
                product_id, warehouse_code, sku, quantity_on_hand, quantity_reserved, quantity_available, snapshot_at, updated_at
            ) VALUES (%s::uuid, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (product_id, warehouse_code) DO UPDATE SET
                quantity_on_hand = EXCLUDED.quantity_on_hand,
                quantity_reserved = EXCLUDED.quantity_reserved,
                quantity_available = EXCLUDED.quantity_available,
                updated_at = NOW()
            """,
            (product_id, warehouse_code, f"SKU-{product_id[:8]}", qty * 2, qty, qty),
        )
        cur.execute(
            """
            INSERT INTO reservations (
                id, order_id, line_item_id, product_id, sku_snapshot, warehouse_code,
                quantity, status, fulfillment_event_id, trace_id, idempotency_key, expires_at, metadata, created_at, updated_at
            ) VALUES (
                gen_random_uuid(), %s::uuid, %s::uuid, %s::uuid, %s, %s, %s, 'active',
                gen_random_uuid(), %s::uuid, %s, NOW() + INTERVAL '1 day', '{}'::jsonb, NOW(), NOW()
            )
            """,
            (order_id, line_item_id, product_id, f"SKU-{product_id[:8]}", warehouse_code, qty, trace_id, f"reservation:{order_id}:{line_item_id}:{uuid4()}"),
        )
    finally:
        cur.close()


def run_precheck(report: Dict[str, Any]) -> None:
    prepare_env_for_imports()

    migration_012 = (MIGRATIONS_DIR / "012_create_control_decisions.sql").exists()
    migration_013 = (MIGRATIONS_DIR / "013_create_config_snapshots.sql").exists()
    migrations_applied = False
    partitioning_ok = False
    snapshot_insert_on_startup = False
    evidence: Dict[str, Any] = {}

    conn = get_conn()
    try:
        has_control = sql_one(
            conn,
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name='control_decisions'
            ) AS ok
            """,
        ).get("ok", False)
        has_snap = sql_one(
            conn,
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='public' AND table_name='config_snapshots'
            ) AS ok
            """,
        ).get("ok", False)
        migrations_applied = bool(migration_012 and migration_013 and has_control and has_snap)

        partitioning_ok = bool(
            sql_one(
                conn,
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_partitioned_table p
                    JOIN pg_class c ON c.oid = p.partrelid
                    WHERE c.relname='control_decisions'
                ) AS ok
                """,
            ).get("ok", False)
        )

        pk_ok = bool(
            sql_one(
                conn,
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = 'config_snapshots'::regclass
                      AND contype = 'p'
                      AND pg_get_constraintdef(oid) ILIKE '%%policy_hash%%'
                ) AS ok
                """,
            ).get("ok", False)
        )
        evidence["config_snapshots_pk_policy_hash"] = pk_ok

        # Start worker shortly in LIVE mode to trigger startup snapshot.
        before_count = sql_one(conn, "SELECT COUNT(*)::int AS c FROM config_snapshots").get("c", 0)
        conn.commit()
        env = os.environ.copy()
        env["EXECUTION_MODE"] = "LIVE"
        env["PYTHONPATH"] = str(ROOT)
        proc = subprocess.Popen(
            [sys.executable, "ru_worker/ru_worker.py"],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        time.sleep(4)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        out = proc.stdout.read() if proc.stdout else ""

        after_count = sql_one(conn, "SELECT COUNT(*)::int AS c FROM config_snapshots").get("c", 0)
        snapshot_insert_on_startup = after_count >= before_count + 1 or "policy_snapshot_ready" in out
        evidence["worker_bootstrap_stdout_tail"] = out[-1000:]
        evidence["config_snapshots_count_before_after"] = {"before": before_count, "after": after_count}

        # #region agent log
        emit_debug(
            run_id="precheck",
            hypothesis_id="H5",
            location="runtime_smoke_runner_v3.py:run_precheck",
            message="Precheck completed",
            data={
                "migrations_012_013_exist": migration_012 and migration_013,
                "migrations_applied": migrations_applied,
                "partitioning_ok": partitioning_ok,
                "snapshot_insert_on_startup": snapshot_insert_on_startup,
            },
        )
        # #endregion

        conn.commit()
    finally:
        conn.close()

    report["environment"] = {
        "migrations_applied": migrations_applied,
        "partitioning_ok": partitioning_ok,
        "snapshot_insert_on_startup": snapshot_insert_on_startup,
        "evidence": evidence,
    }


def run_s1(report: Dict[str, Any]) -> None:
    prepare_env_for_imports()
    from ru_worker import ru_worker as rw

    order_id = str(uuid4())
    trace_id = str(uuid4())
    product_id = str(uuid4())
    line_item_id = str(uuid4())
    invoice_id = "TEST-INV-001"

    conn = get_conn()
    critical_failures: List[str] = []
    major_failures: List[str] = []
    warnings: List[str] = []
    evidence: Dict[str, Any] = {}
    try:
        cleanup_cur = conn.cursor()
        cleanup_cur.execute("DELETE FROM order_ledger WHERE tbank_invoice_id=%s", (invoice_id,))
        cleanup_cur.close()
        conn.commit()

        ensure_test_order_with_reservation(
            conn,
            order_id=order_id,
            trace_id=trace_id,
            invoice_id=invoice_id,
            qty=1,
            product_id=product_id,
            line_item_id=line_item_id,
        )

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            INSERT INTO job_queue (id, job_type, payload, status, idempotency_key, trace_id, created_at, updated_at)
            VALUES (gen_random_uuid(), 'tbank_invoice_paid', %s::jsonb, 'pending', %s, %s::uuid, NOW(), NOW())
            RETURNING id
            """,
            (
                json.dumps(
                    {
                        "invoice_id": invoice_id,
                        "invoice_number": "INV-SMOKE-001",
                        "paid_at": now_iso(),
                        "amount_minor": 100000,
                        "currency": "RUB",
                    },
                    ensure_ascii=False,
                ),
                f"tbank:invoice_paid:{invoice_id}:{uuid4()}",
                trace_id,
            ),
        )
        job_id = str(cur.fetchone()["id"])
        cur.execute("UPDATE job_queue SET status='processing', updated_at=NOW() WHERE id=%s::uuid", (job_id,))
        conn.commit()

        cur.execute("SELECT * FROM job_queue WHERE id=%s::uuid", (job_id,))
        job = dict(cur.fetchone())
        result = rw.process_job(job, conn)

        cur.execute(
            "UPDATE job_queue SET status='completed', result=%s::jsonb, updated_at=NOW() WHERE id=%s::uuid",
            (json.dumps(result, ensure_ascii=False), job_id),
        )
        conn.commit()

        v11 = sql_one(conn, "SELECT policy_hash, created_at FROM config_snapshots ORDER BY created_at DESC LIMIT 1")
        v12 = sql_one(
            conn,
            """
            SELECT id, status, result FROM job_queue
            WHERE job_type='tbank_invoice_paid' AND payload->>'invoice_id'=%s
            ORDER BY created_at DESC LIMIT 1
            """,
            (invoice_id,),
        )
        v13 = sql_one(
            conn,
            "SELECT order_id, state, state_history FROM order_ledger WHERE tbank_invoice_id=%s",
            (invoice_id,),
        )
        v14 = sql_all(
            conn,
            "SELECT id, status, quantity FROM reservations WHERE order_id=%s::uuid AND status='active'",
            (order_id,),
        )
        cd_count = sql_one(
            conn,
            "SELECT COUNT(*)::int AS c FROM control_decisions WHERE trace_id=%s::uuid",
            (trace_id,),
        ).get("c", 0)

        if not v11:
            critical_failures.append("V1.1: config_snapshots empty")
        if v12.get("status") != "completed":
            critical_failures.append("V1.2: job_queue status is not completed")
        if v13.get("state") != "paid":
            major_failures.append(f"V1.3: expected state='paid', got {v13.get('state')}")
        if len(v14) != 1:
            major_failures.append("V1.4: expected exactly one active reservation for test order")
        if cd_count != 0:
            major_failures.append(f"INV-2 violated: control_decisions count for S1 trace is {cd_count} (expected 0)")

        state_history = v13.get("state_history") or []
        if not isinstance(state_history, list) or len(state_history) != 1:
            major_failures.append("INV-3 violated: state_history changed on idempotent skip")

        # #region agent log
        emit_debug(
            run_id="S1",
            hypothesis_id="H5",
            location="runtime_smoke_runner_v3.py:run_s1",
            message="LIVE success scenario checks",
            data={
                "job_status": v12.get("status"),
                "fsm_state": v13.get("state"),
                "active_reservations": len(v14),
                "control_decisions_for_trace": cd_count,
            },
        )
        # #endregion

        evidence = {"V1.1": v11, "V1.2": v12, "V1.3": v13, "V1.4": v14, "control_decisions_count": cd_count}
        status = "PASS" if not critical_failures and not major_failures else "FAIL"
    finally:
        conn.close()

    report["scenarios"]["S1"] = {
        "status": status,
        "critical_failures": critical_failures,
        "major_failures": major_failures,
        "warnings": warnings,
        "evidence": evidence,
        "ids": {"order_id": order_id, "trace_id": trace_id, "invoice_id": invoice_id},
    }


def run_s2(report: Dict[str, Any]) -> None:
    prepare_env_for_imports()
    from ru_worker.dispatch_action import dispatch_action
    from ru_worker.ru_worker import execute_order_event

    order_id = str(uuid4())
    trace_id = str(uuid4())
    product_id = str(uuid4())
    line_item_id = str(uuid4())
    csg_invoice_id = f"CSG-INV-{order_id[:8]}"

    conn = get_conn()
    critical_failures: List[str] = []
    major_failures: List[str] = []
    warnings: List[str] = []
    evidence: Dict[str, Any] = {}
    try:
        ensure_test_order_with_reservation(
            conn,
            order_id=order_id,
            trace_id=trace_id,
            invoice_id=f"CSG-INV-{order_id[:8]}",
            qty=5,
            product_id=product_id,
            line_item_id=line_item_id,
        )
        conn.commit()

        action = {
            "action_type": "ship_paid",
            "payload": {
                "invoice_id": csg_invoice_id,
                "total_amount": 1000,
                "reference_price": 800,
                "net_minor": 80000,
                "tax_minor": 20000,
                "tax_rate": 20,
            },
            "source": "smoke_test",
            "metadata": {"trace_id": trace_id},
        }
        action_result = dispatch_action(action, mode="REAL", db_conn=conn, trace_id=trace_id, execution_mode="LIVE")

        hold_result = execute_order_event(
            {
                "order_id": order_id,
                "source": "system",
                "event_type": "CSG_HOLD",
                "occurred_at": now_iso(),
                "payload": {"gate_name": "commercial_sanity", "reason": "price_anomaly"},
            },
            conn,
            trace_id=trace_id,
        )
        timeout_result = execute_order_event(
            {
                "order_id": order_id,
                "source": "system",
                "event_type": "HUMAN_DECISION_TIMEOUT",
                "occurred_at": now_iso(),
                "payload": {"reason": "human_decision_timeout"},
            },
            conn,
            trace_id=trace_id,
        )

        v21 = sql_all(
            conn,
            """
            SELECT id, trace_id, gate_name, verdict, decision_context, reference_snapshot, policy_hash
            FROM control_decisions
            WHERE trace_id=%s::uuid
            ORDER BY created_at
            """,
            (trace_id,),
        )
        v22 = sql_all(
            conn,
            """
            SELECT cd.policy_hash, cs.policy_hash IS NOT NULL AS snapshot_exists
            FROM control_decisions cd
            LEFT JOIN config_snapshots cs ON cs.policy_hash = cd.policy_hash
            WHERE cd.trace_id = %s::uuid
            """,
            (trace_id,),
        )
        v23 = sql_one(conn, "SELECT state, state_history FROM order_ledger WHERE order_id=%s::uuid", (order_id,))
        v24 = sql_all(conn, "SELECT id, status, quantity FROM reservations WHERE order_id=%s::uuid", (order_id,))
        v25 = sql_one(
            conn,
            "SELECT quantity_on_hand, quantity_reserved, quantity_available FROM availability_snapshot WHERE product_id=%s::uuid",
            (product_id,),
        )
        v26 = sql_all(
            conn,
            """
            SELECT id, change_type, quantity_delta, idempotency_key, metadata
            FROM stock_ledger_entries
            WHERE reference_type='reservation' AND idempotency_key LIKE 'release:%%'
            ORDER BY created_at DESC
            """,
        )

        # Idempotency re-check (V2.7)
        from domain.availability_service import release_reservations_for_order_atomic

        second_release = release_reservations_for_order_atomic(
            conn,
            order_id=uuid4() if False else __import__("uuid").UUID(order_id),
            trace_id=trace_id,
            reason="fsm_terminal:human_decision_timeout",
        )
        conn.commit()

        if action_result.get("status") != "pending_approval":
            critical_failures.append(f"INV-4 violated: expected pending_approval, got {action_result}")
        if v23.get("state") != "human_decision_timeout":
            critical_failures.append(f"C1 violated: expected terminal state human_decision_timeout, got {v23.get('state')}")
        if any(r.get("status") == "active" for r in v24):
            critical_failures.append("C1 violated: active reservations remained after timeout terminal transition")
        if not any(row.get("snapshot_exists") for row in v22):
            major_failures.append("INV-5 violated: control_decisions.policy_hash missing in config_snapshots")
        if second_release.get("action") != "noop":
            warnings.append(f"INV-6 warning: second release action={second_release}")

        # #region agent log
        emit_debug(
            run_id="S2",
            hypothesis_id="H1",
            location="runtime_smoke_runner_v3.py:run_s2",
            message="CSG hold and timeout release checks",
            data={
                "dispatch_status": action_result.get("status"),
                "terminal_state": v23.get("state"),
                "active_reservations_after_timeout": sum(1 for r in v24 if r.get("status") == "active"),
                "second_release_action": second_release.get("action"),
            },
        )
        # #endregion

        evidence = {
            "dispatch_action_result": action_result,
            "hold_result": hold_result,
            "timeout_result": timeout_result,
            "V2.1": v21,
            "V2.2": v22,
            "V2.3": v23,
            "V2.4": v24,
            "V2.5": v25,
            "V2.6": v26[:5],
            "V2.7": second_release,
        }
        status = "PASS" if not critical_failures and not major_failures else "FAIL"
    finally:
        conn.close()

    report["scenarios"]["S2"] = {
        "status": status,
        "critical_failures": critical_failures,
        "major_failures": major_failures,
        "warnings": warnings,
        "evidence": evidence,
        "ids": {"order_id": order_id, "trace_id": trace_id, "product_id": product_id},
    }


def run_s3(report: Dict[str, Any]) -> None:
    prepare_env_for_imports()
    from ru_worker.dispatch_action import dispatch_action
    from ru_worker.ru_worker import _release_reservations_safe, _resolve_order_id_for_cleanup

    order_id = str(uuid4())
    trace_id = str(uuid4())
    product_id = str(uuid4())
    line_item_id = str(uuid4())

    conn = get_conn()
    critical_failures: List[str] = []
    major_failures: List[str] = []
    warnings: List[str] = []
    evidence: Dict[str, Any] = {}
    try:
        ensure_test_order_with_reservation(
            conn,
            order_id=order_id,
            trace_id=trace_id,
            invoice_id=f"CRASH-INV-{order_id[:8]}",
            qty=2,
            product_id=product_id,
            line_item_id=line_item_id,
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            INSERT INTO job_queue (id, job_type, payload, status, idempotency_key, trace_id, created_at, updated_at)
            VALUES (gen_random_uuid(), 'tbank_invoice_paid', %s::jsonb, 'pending', %s, %s::uuid, NOW(), NOW())
            RETURNING id
            """,
            (json.dumps({"order_id": order_id, "invoice_id": f"CRASH-INV-{order_id[:8]}"}, ensure_ascii=False), f"crash:{order_id}", trace_id),
        )
        job_id = str(cur.fetchone()["id"])
        conn.commit()

        cur.execute("SELECT * FROM job_queue WHERE id=%s::uuid", (job_id,))
        job = dict(cur.fetchone())
        payload = job.get("payload", {}) if isinstance(job.get("payload"), dict) else json.loads(job.get("payload") or "{}")
        job_type = job.get("job_type")
        cur.execute("UPDATE job_queue SET status='processing', updated_at=NOW() WHERE id=%s::uuid", (job_id,))
        conn.commit()

        cleanup_order_id = _resolve_order_id_for_cleanup(job_type, payload, conn)
        job_failed = False
        try:
            dispatch_action(
                {
                    "action_type": "unknown_action",
                    "payload": {"order_id": order_id, "amount_minor": 10},
                    "metadata": {"trace_id": trace_id},
                    "source": "smoke_crash",
                },
                mode="REAL",
                db_conn=conn,
                trace_id=trace_id,
                execution_mode="LIVE",
            )
            raise RuntimeError("simulated_crash")
        except Exception as e:
            job_failed = True
            cur.execute(
                "UPDATE job_queue SET status='failed', error=%s, updated_at=NOW() WHERE id=%s::uuid",
                (str(e), job_id),
            )
            conn.commit()
        finally:
            if job_failed and cleanup_order_id is not None:
                _release_reservations_safe(
                    conn,
                    order_id=cleanup_order_id,
                    trace_id=trace_id,
                    reason="job_processor_failure_cleanup",
                )
                conn.commit()

        v31 = sql_one(conn, "SELECT id, status, error FROM job_queue WHERE id=%s::uuid", (job_id,))
        v32 = sql_one(conn, "SELECT state FROM order_ledger WHERE order_id=%s::uuid", (order_id,))
        v33 = sql_all(conn, "SELECT id, status, metadata FROM reservations WHERE order_id=%s::uuid", (order_id,))
        v34 = sql_all(
            conn,
            """
            SELECT change_type, quantity_delta, idempotency_key, metadata
            FROM stock_ledger_entries
            WHERE idempotency_key LIKE 'release:%%'
              AND metadata->>'reason'='job_processor_failure_cleanup'
            ORDER BY created_at DESC
            """,
        )

        from domain.availability_service import release_reservations_for_order_atomic

        second_release = release_reservations_for_order_atomic(
            conn,
            order_id=__import__("uuid").UUID(order_id),
            trace_id=trace_id,
            reason="job_processor_failure_cleanup",
        )
        conn.commit()

        if v31.get("status") != "failed":
            critical_failures.append("INV-11 violated: job status is not failed")
        if "simulated_crash" not in str(v31.get("error")):
            major_failures.append(f"V3.1 unexpected error payload: {v31.get('error')}")
        if v32.get("state") != "paid":
            critical_failures.append(f"INV-10 violated: FSM state changed unexpectedly to {v32.get('state')}")
        if any(r.get("status") == "active" for r in v33):
            critical_failures.append("C1 violated: active reservations remain after crash cleanup")
        if not v34:
            critical_failures.append("C2 violated: no release entry with reason=job_processor_failure_cleanup")
        if second_release.get("action") != "noop":
            warnings.append(f"V3.5 warning: second release expected noop, got {second_release}")

        # #region agent log
        emit_debug(
            run_id="S3",
            hypothesis_id="H1",
            location="runtime_smoke_runner_v3.py:run_s3",
            message="Crash cleanup scenario checks",
            data={
                "job_status": v31.get("status"),
                "fsm_state_after_crash": v32.get("state"),
                "release_entries": len(v34),
                "second_release_action": second_release.get("action"),
            },
        )
        # #endregion

        evidence = {"V3.1": v31, "V3.2": v32, "V3.3": v33, "V3.4": v34[:5], "V3.5": second_release}
        status = "PASS" if not critical_failures and not major_failures else "FAIL"
    finally:
        conn.close()

    report["scenarios"]["S3"] = {
        "status": status,
        "critical_failures": critical_failures,
        "major_failures": major_failures,
        "warnings": warnings,
        "evidence": evidence,
        "ids": {"order_id": order_id, "trace_id": trace_id, "job_id": job_id},
    }


def run_s4(report: Dict[str, Any]) -> None:
    prepare_env_for_imports()
    from ru_worker.dispatch_action import dispatch_action
    from side_effects.adapters.factory import (
        get_order_source_adapter,
        get_payment_invoice_adapter,
        get_shipment_adapter,
    )

    replay_trace = str(uuid4())
    missing_hash = "hash_that_does_not_exist"

    conn = get_conn()
    critical_failures: List[str] = []
    major_failures: List[str] = []
    warnings: List[str] = []
    evidence: Dict[str, Any] = {}
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO control_decisions (
                trace_id, decision_seq, gate_name, verdict, schema_version, policy_hash,
                decision_context, reference_snapshot, replay_config_status
            ) VALUES (
                %s::uuid, 1, 'commercial_sanity', 'ALLOW', 'v3', %s, '{}'::jsonb, '{}'::jsonb, NULL
            )
            """,
            (replay_trace, missing_hash),
        )
        cur.execute("DELETE FROM config_snapshots WHERE policy_hash=%s", (missing_hash,))
        conn.commit()

        action = {
            "action_type": "unknown_action",
            "payload": {"invoice_id": "REPLAY-INV", "amount_minor": 10000},
            "source": "replay_test",
            "metadata": {"trace_id": replay_trace, "policy_hash": missing_hash},
        }
        dispatch_result = dispatch_action(action, mode="REAL", db_conn=conn, trace_id=replay_trace, execution_mode="REPLAY")

        adapter_payment = get_payment_invoice_adapter(execution_mode="REPLAY", db_conn=conn, trace_id=replay_trace).__class__.__name__
        adapter_ship = get_shipment_adapter(execution_mode="REPLAY", db_conn=conn, trace_id=replay_trace).__class__.__name__
        adapter_order = get_order_source_adapter(execution_mode="REPLAY").__class__.__name__

        v41 = sql_one(
            conn,
            """
            SELECT id, verdict, replay_config_status, decision_context
            FROM control_decisions
            WHERE trace_id=%s::uuid AND gate_name='commercial_sanity'
            ORDER BY created_at DESC LIMIT 1
            """,
            (replay_trace,),
        )
        v42 = sql_all(
            conn,
            """
            SELECT verdict, replay_config_status
            FROM control_decisions
            WHERE trace_id=%s::uuid
              AND replay_config_status='REPLAY_CONFIG_UNAVAILABLE'
            """,
            (replay_trace,),
        )
        v43 = sql_one(conn, "SELECT COUNT(*)::int AS count FROM config_snapshots WHERE policy_hash=%s", (missing_hash,))
        v44 = sql_one(conn, "SELECT policy_hash FROM config_snapshots ORDER BY created_at DESC LIMIT 1")

        if v41.get("verdict") != "SKIPPED_MISSING_CONFIG":
            critical_failures.append(f"C8 violated: expected SKIPPED_MISSING_CONFIG, got {v41.get('verdict')}")
        if v41.get("replay_config_status") != "REPLAY_CONFIG_UNAVAILABLE":
            critical_failures.append("INV-14 violated: replay_config_status is not REPLAY_CONFIG_UNAVAILABLE")
        if v43.get("count") != 0:
            major_failures.append(f"V4.3 expected missing hash count=0, got {v43.get('count')}")
        if adapter_payment.startswith("Replay") is False or adapter_ship.startswith("Replay") is False or adapter_order.startswith("Replay") is False:
            critical_failures.append(f"C4 violated: replay adapters not used ({adapter_payment}, {adapter_ship}, {adapter_order})")
        if v41.get("verdict") in {"REJECT", "NEEDS_HUMAN"}:
            critical_failures.append(f"C8 violated: verdict should not be {v41.get('verdict')} in replay missing snapshot")

        # #region agent log
        emit_debug(
            run_id="S4",
            hypothesis_id="H2",
            location="runtime_smoke_runner_v3.py:run_s4",
            message="Replay missing snapshot CSG verdict",
            data={
                "verdict": v41.get("verdict"),
                "replay_config_status": v41.get("replay_config_status"),
                "dispatch_status": dispatch_result.get("status"),
            },
        )
        # #endregion
        # #region agent log
        emit_debug(
            run_id="S4",
            hypothesis_id="H3",
            location="runtime_smoke_runner_v3.py:run_s4",
            message="Replay adapter isolation check",
            data={
                "payment_adapter": adapter_payment,
                "shipment_adapter": adapter_ship,
                "order_adapter": adapter_order,
            },
        )
        # #endregion

        evidence = {
            "dispatch_action_result": dispatch_result,
            "V4.1": v41,
            "V4.2": v42,
            "V4.3": v43,
            "V4.4": v44,
            "adapter_classes": {
                "payment": adapter_payment,
                "shipment": adapter_ship,
                "order_source": adapter_order,
            },
        }
        status = "PASS" if not critical_failures and not major_failures else "FAIL"
    finally:
        conn.close()

    report["scenarios"]["S4"] = {
        "status": status,
        "critical_failures": critical_failures,
        "major_failures": major_failures,
        "warnings": warnings,
        "evidence": evidence,
        "ids": {"trace_id": replay_trace, "missing_policy_hash": missing_hash},
    }


def run_s5(report: Dict[str, Any]) -> None:
    prepare_env_for_imports()
    from ru_worker.pii_redactor import redact_trace
    from ru_worker.pii_dependency_registry import PII_STEP_CLASSIFICATIONS

    pii_trace = str(uuid4())
    order_id = str(uuid4())
    shipment_idempotency = f"ship-redact-{uuid4()}"
    same_plain_name = "Alice Same"

    conn = get_conn()
    critical_failures: List[str] = []
    major_failures: List[str] = []
    warnings: List[str] = []
    evidence: Dict[str, Any] = {}
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO order_ledger (
                order_id, insales_order_id, invoice_request_key, state, state_history,
                customer_data, delivery_data, error_log, metadata, trace_id, created_at, updated_at
            ) VALUES (
                %s::uuid, %s, %s, 'paid', %s::jsonb, %s::jsonb, %s::jsonb, '[]'::jsonb, '{}'::jsonb, %s::uuid, NOW(), NOW()
            )
            """,
            (
                order_id,
                f"ins-{order_id[:8]}",
                f"req-{order_id[:8]}",
                json.dumps([{"state": "paid", "timestamp": now_iso()}], ensure_ascii=False),
                json.dumps({"name": same_plain_name, "phone": "+70001112233", "email": "alice@example.com", "address": "Street 1", "inn": "7700000000"}, ensure_ascii=False),
                json.dumps({"name": same_plain_name, "phone": "+70001112233", "email": "alice@example.com", "address": "Street 1"}, ensure_ascii=False),
                pii_trace,
            ),
        )
        cur.execute(
            """
            INSERT INTO shipments (
                id, order_id, trace_id, shipment_seq, carrier_code, carrier_external_id, current_status,
                status_changed_at, packages, address_snapshot, status_history, carrier_metadata, metadata,
                idempotency_key, created_at, updated_at
            ) VALUES (
                gen_random_uuid(), %s::uuid, %s::uuid, 1, 'cdek', %s, 'created', NOW(),
                '[]'::jsonb, %s::jsonb, '[]'::jsonb, '{}'::jsonb, '{}'::jsonb, %s, NOW(), NOW()
            )
            """,
            (
                order_id,
                pii_trace,
                f"ext-{order_id[:8]}",
                json.dumps({"recipient_name": same_plain_name, "recipient_phone": "+70001112233", "raw": "Street 1"}, ensure_ascii=False),
                shipment_idempotency,
            ),
        )
        cur.execute(
            """
            INSERT INTO tasks (id, trace_id, task_type, status, payload, error, created_at, updated_at)
            VALUES (gen_random_uuid(), %s::uuid, 'execute_invoice_create', 'failed', '{}'::jsonb, 'seed for replay', NOW(), NOW())
            """,
            (pii_trace,),
        )
        cur.execute(
            """
            INSERT INTO job_queue (id, job_type, payload, status, idempotency_key, trace_id, result, created_at, updated_at)
            VALUES (
                gen_random_uuid(), 'execute_invoice_create', '{}'::jsonb, 'completed', %s, %s::uuid, %s::jsonb, NOW(), NOW()
            )
            """,
            (f"replay-seed:{pii_trace}", pii_trace, json.dumps({"recorded": True}, ensure_ascii=False)),
        )
        conn.commit()

        redaction_result = redact_trace(
            conn,
            trace_id=pii_trace,
            legal_basis="gdpr_art17",
            requested_by="runtime_smoke",
            salt="smoke-salt",
        )

        before_counts = {
            "job_queue_for_trace": sql_one(conn, "SELECT COUNT(*)::int AS c FROM job_queue WHERE trace_id=%s::uuid", (pii_trace,)).get("c", 0),
            "control_decisions_for_trace": sql_one(conn, "SELECT COUNT(*)::int AS c FROM control_decisions WHERE trace_id=%s::uuid", (pii_trace,)).get("c", 0),
        }
        conn.commit()

        env = os.environ.copy()
        replay_proc = subprocess.run(
            [sys.executable, "cli/replay.py", pii_trace, "--force"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        replay_output = (replay_proc.stdout or "") + (replay_proc.stderr or "")

        after_counts = {
            "job_queue_for_trace": sql_one(conn, "SELECT COUNT(*)::int AS c FROM job_queue WHERE trace_id=%s::uuid", (pii_trace,)).get("c", 0),
            "control_decisions_for_trace": sql_one(conn, "SELECT COUNT(*)::int AS c FROM control_decisions WHERE trace_id=%s::uuid", (pii_trace,)).get("c", 0),
        }

        v51 = sql_all(
            conn,
            "SELECT id, verdict, decision_context FROM control_decisions WHERE trace_id=%s::uuid AND gate_name='pii_redaction'",
            (pii_trace,),
        )
        v52 = sql_one(
            conn,
            """
            SELECT customer_data->>'name' AS name_value,
                   customer_data->>'phone' AS phone_value,
                   customer_data->>'email' AS email_value
            FROM order_ledger WHERE trace_id=%s::uuid
            """,
            (pii_trace,),
        )
        v53 = sql_one(
            conn,
            """
            SELECT address_snapshot->>'recipient_name' AS name,
                   address_snapshot->>'recipient_phone' AS phone
            FROM shipments WHERE trace_id=%s::uuid
            """,
            (pii_trace,),
        )
        v54 = sql_one(
            conn,
            "SELECT COUNT(*)::int AS c FROM control_decisions WHERE trace_id=%s::uuid AND gate_name!='pii_redaction'",
            (pii_trace,),
        )
        v55 = sql_one(
            conn,
            """
            SELECT id, (result IS NOT NULL) AS has_result
            FROM job_queue
            WHERE trace_id=%s::uuid AND status='completed'
            ORDER BY updated_at DESC LIMIT 1
            """,
            (pii_trace,),
        )

        pii_dependent_skip_expected = PII_STEP_CLASSIFICATIONS.get("execute_invoice_create") == "PII_DEPENDENT"
        pii_independent_not_skip_expected = PII_STEP_CLASSIFICATIONS.get("execute_rfq_v1_from_ocr") != "PII_DEPENDENT"

        if replay_proc.returncode != 0:
            critical_failures.append(f"S5 replay.py exited with code {replay_proc.returncode}")
        if "REPLAY_SKIPPED_MATCH" not in replay_output:
            major_failures.append("INV-20 violated: REPLAY_SKIPPED_MATCH not emitted")
        if "partial_replay: true" not in replay_output:
            major_failures.append("S5 expected output missing: partial_replay: true")
        if not str(v52.get("name_value", "")).startswith("REDACTED:"):
            critical_failures.append("C5/C6 violated: customer_data.name is not redacted")
        if not str(v53.get("name", "")).startswith("REDACTED:"):
            critical_failures.append("C5 violated: shipments.address_snapshot.recipient_name is not redacted")
        if v52.get("name_value") != v53.get("name"):
            major_failures.append("INV-21 violated: deterministic pseudonymization mismatch for same input+salt")
        if after_counts["job_queue_for_trace"] != before_counts["job_queue_for_trace"]:
            critical_failures.append("C6 violated: synthetic job_queue mutation detected during replay")
        if after_counts["control_decisions_for_trace"] != before_counts["control_decisions_for_trace"]:
            critical_failures.append("C6 violated: synthetic control_decisions mutation detected during replay")
        if not pii_dependent_skip_expected:
            major_failures.append("INV-17 setup invalid: execute_invoice_create is not marked PII_DEPENDENT")
        if not pii_independent_not_skip_expected:
            major_failures.append("INV-18 setup invalid: execute_rfq_v1_from_ocr unexpectedly PII_DEPENDENT")

        # #region agent log
        emit_debug(
            run_id="S5",
            hypothesis_id="H4",
            location="runtime_smoke_runner_v3.py:run_s5",
            message="PII redacted replay checks",
            data={
                "replay_returncode": replay_proc.returncode,
                "has_replay_skipped_match": "REPLAY_SKIPPED_MATCH" in replay_output,
                "job_queue_count_before_after": [before_counts["job_queue_for_trace"], after_counts["job_queue_for_trace"]],
                "control_decisions_before_after": [before_counts["control_decisions_for_trace"], after_counts["control_decisions_for_trace"]],
            },
        )
        # #endregion

        evidence = {
            "redaction_result": redaction_result,
            "replay_output_tail": replay_output[-1200:],
            "V5.1": v51,
            "V5.2": v52,
            "V5.3": v53,
            "V5.4": v54,
            "V5.5": v55,
            "counts_before": before_counts,
            "counts_after": after_counts,
        }
        status = "PASS" if not critical_failures and not major_failures else "FAIL"
    finally:
        conn.close()

    report["scenarios"]["S5"] = {
        "status": status,
        "critical_failures": critical_failures,
        "major_failures": major_failures,
        "warnings": warnings,
        "evidence": evidence,
        "ids": {"trace_id": pii_trace, "order_id": order_id},
    }


def build_critical_summary(report: Dict[str, Any]) -> Dict[str, str]:
    s1 = report["scenarios"]["S1"]
    s2 = report["scenarios"]["S2"]
    s3 = report["scenarios"]["S3"]
    s4 = report["scenarios"]["S4"]
    s5 = report["scenarios"]["S5"]

    def has_crit(scn: Dict[str, Any], token: str) -> bool:
        return any(token in x for x in scn.get("critical_failures", []))

    c = {
        "C1": "PASS" if not has_crit(s2, "C1") and not has_crit(s3, "C1") else "FAIL",
        "C2": "PASS" if not has_crit(s3, "C2") else "FAIL",
        "C3": "PASS" if not has_crit(s4, "C3") else "FAIL",
        "C4": "PASS" if not has_crit(s4, "C4") else "FAIL",
        "C5": "PASS" if not has_crit(s5, "C5") else "FAIL",
        "C6": "PASS" if not has_crit(s5, "C6") else "FAIL",
        "C7": "PASS" if report["environment"]["snapshot_insert_on_startup"] else "FAIL",
        "C8": "PASS" if not has_crit(s4, "C8") else "FAIL",
    }
    return c


def main() -> int:
    report: Dict[str, Any] = {"environment": {}, "scenarios": {}}

    run_precheck(report)
    run_s1(report)
    run_s2(report)
    run_s3(report)
    run_s4(report)
    run_s5(report)

    critical = build_critical_summary(report)
    report["critical"] = critical
    report["final_verdict"] = "GO" if all(v == "PASS" for v in critical.values()) else "NO-GO"

    out_json = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    print(out_json)

    report_path_raw = os.environ.get("SMOKE_REPORT_PATH")
    if report_path_raw:
        report_path = Path(report_path_raw)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(out_json + "\n", encoding="utf-8")

    return 0 if report["final_verdict"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())

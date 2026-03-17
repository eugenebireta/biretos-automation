# JUDGE_SUBMISSION_FULL_stage1_v1_1

## A) Header
- generated_at_utc: 2026-02-28T19:42:09.117467+00:00
- repo_root: C:/cursor_project/biretos-automation
- branch: master
- last_commit: 4d81d4c docs: complete Tier-3 worker system with enhanced logging, error handling, and tests.

## B) JUDGE_PACKAGE_stage1_v1_1.md (full)

# JUDGE PACKAGE вЂ” Stage 1 v1.1

## Canonical references (paths only)
- PROJECT_DNA.md
- MASTER_PLAN_v1_8_0.md
- EXECUTION_ROADMAP_v2_2.md

## PRECHECK snapshot (short)
- repo_root: C:\cursor_project\biretos-automation
- branch: master
- last_commit: 4d81d4c docs: complete Tier-3 worker system with enhanced logging, error handling, and tests.
- full snapshot artifact: docs/_governance/run_state_pre.md

## Diff bundle (Tier-1 target files)
- docs/_governance/diff_reconciliation_service.txt
- docs/_governance/diff_maintenance_sweeper.txt
- docs/_governance/diff_tier1_hashes.txt
- docs/_governance/diff_reconciliation_service.txt: HAS_DIFF
- docs/_governance/diff_maintenance_sweeper.txt: HAS_DIFF
- docs/_governance/diff_tier1_hashes.txt: EMPTY_DIFF

## Pytest summary
- status: PASS
- exit_code: 0
- output artifact: docs/_governance/pytest_output.txt

### Last ~30 pytest lines
```
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("startup")

tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset
  C:\Users\Eugene\AppData\Local\Programs\Python\Python312\Lib\site-packages\fastapi\applications.py:4547: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    return self.router.on_event(event_type)

tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset
  C:\cursor_project\biretos-automation\.cursor\windmill-core-v1\webhook_service\main.py:263: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("shutdown")

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 128 passed, 8 warnings in 0.82s =======================

PYTEST_EXIT_CODE=0
```

## Hash proof summary
- total_entries: 19
- match_count: 19
- mismatch_count: 0
- hash artifact: docs/_governance/hash_proof.txt

### MISMATCH/MISSING paths
- none

## Untracked files referenced by manifest
- artifact: docs/_governance/untracked_referenced_by_manifest.txt
- .cursor/windmill-core-v1/retention_policy.py
- .cursor/windmill-core-v1/domain/reconciliation_verify.py
- .cursor/windmill-core-v1/domain/reconciliation_alerts.py
- .cursor/windmill-core-v1/domain/structural_checks.py
- .cursor/windmill-core-v1/migrations/016_create_reconciliation_audit_log.sql
- .cursor/windmill-core-v1/migrations/017_create_reconciliation_suppressions.sql
- .cursor/windmill-core-v1/migrations/018_create_reconciliation_alerts.sql
- .cursor/windmill-core-v1/migrations/019_add_retention_indexes.sql
- .cursor/windmill-core-v1/docs/RETENTION_INVARIANT.md
- .cursor/windmill-core-v1/tests/validation/test_phase3_alert_emission.py
- .cursor/windmill-core-v1/tests/validation/test_phase3_cache_read_model_contract.py
- .cursor/windmill-core-v1/tests/validation/test_phase3_l3_structural_checks.py
- .cursor/windmill-core-v1/tests/validation/test_phase3_replay_verify.py
- .cursor/windmill-core-v1/tests/validation/test_phase3_structural_safety_contract.py

## SCOPE LOCK
### IN
- .cursor/windmill-core-v1/domain/reconciliation_service.py
- .cursor/windmill-core-v1/maintenance_sweeper.py
- .cursor/windmill-core-v1/.tier1-hashes.sha256
- .cursor/windmill-core-v1/CREDENTIALS_FOUND.md (index removal only)
- .env (index removal only)
- price-checker/.env (index removal only)
- .gitignore
- docs/_governance/*
### OUT
- .cursor/windmill-core-v1/migrations/020_create_stg_catalog_jobs.sql
- .cursor/windmill-core-v1/migrations/021_create_stg_catalog_imports.sql
- .cursor/windmill-core-v1/workers/catalog_worker.py
- .cursor/windmill-core-v1/tests/validation/test_r1_catalog_pipeline.py
- .cursor/rules/lot-structure-analysis.mdc
- scripts/lot_scoring/**
- tmp/runtime_smoke_runner_v3.py
- MASTER_PLAN_v1_8_0.md
- EXECUTION_ROADMAP_v2_2.md
- PROJECT_DNA.md
- BP-Verification-Checklist.md

## Decision request
- APPROVE / REJECT / MODIFY

## STOP-POINT 1
РќР• РєРѕРјРјРёС‚РёС‚СЊ/РќР• РїСѓС€РёС‚СЊ/РќР• РїРµСЂРµСЃС‡РёС‚С‹РІР°С‚СЊ С…СЌС€Рё РґРѕ РІРµСЂРґРёРєС‚Р° JUDGE.

## C) Diff files (full)

### `docs/_governance/diff_reconciliation_service.txt`
```diff
﻿diff --git a/.cursor/windmill-core-v1/domain/reconciliation_service.py b/.cursor/windmill-core-v1/domain/reconciliation_service.py
index a385406..2ed7f0f 100644
--- a/.cursor/windmill-core-v1/domain/reconciliation_service.py
+++ b/.cursor/windmill-core-v1/domain/reconciliation_service.py
@@ -281,6 +281,183 @@ def reconcile_document_key(
         cursor.close()
 
 
+def escalate_reservation_deficit(
+    db_conn,
+    *,
+    order_id: UUID,
+    line_item_id: UUID,
+    ic_verdict: Dict[str, Any],
+    trace_id: Optional[str],
+) -> Dict[str, Any]:
+    """
+    RC-4b (v2): Reservation deficit escalation with suppression + open-case dedupe.
+
+    Contract:
+      - No stock ledger writes.
+      - No FSM transitions.
+      - Only updates allowed: order_line_items.line_status (pending->reserved correction).
+      - Case creation via governance_workflow.create_review_case (non-ledger table).
+    """
+    _ensure_tx_connection(db_conn)
+
+    entity_type = "order_line_item"
+    entity_id = f"{order_id}:{line_item_id}"
+
+    cursor = db_conn.cursor()
+    try:
+        # 1) Suppression check (active + not expired).
+        cursor.execute(
+            """
+            SELECT 1
+            FROM reconciliation_suppressions
+            WHERE entity_type = %s
+              AND entity_id = %s
+              AND check_code = 'IC-4'
+              AND suppression_state = 'active'
+              AND (expires_at IS NULL OR expires_at > NOW())
+            LIMIT 1
+            """,
+            (entity_type, entity_id),
+        )
+        if cursor.fetchone():
+            return {"action": "suppressed", "order_id": str(order_id), "line_item_id": str(line_item_id), "trace_id": trace_id}
+
+        # 2) Lock line item and recompute deficit inside the same tx.
+        cursor.execute(
+            """
+            SELECT quantity, line_status
+            FROM order_line_items
+            WHERE id = %s
+              AND order_id = %s
+            LIMIT 1
+            FOR UPDATE
+            """,
+            (str(line_item_id), str(order_id)),
+        )
+        row = cursor.fetchone()
+        if not row:
+            return {
+                "action": "noop",
+                "reason": "line_item_not_found",
+                "order_id": str(order_id),
+                "line_item_id": str(line_item_id),
+                "trace_id": trace_id,
+            }
+        line_quantity = int(row[0] or 0)
+        line_status = str(row[1] or "pending")
+
+        cursor.execute(
+            """
+            SELECT COALESCE(SUM(quantity), 0)
+            FROM reservations
+            WHERE order_id = %s
+              AND line_item_id = %s
+              AND status = 'active'
+            """,
+            (str(order_id), str(line_item_id)),
+        )
+        active_reserved = int(cursor.fetchone()[0])
+
+        # If reserves are sufficient but line_status is stale, correct it.
+        if line_status == "pending" and active_reserved >= line_quantity:
+            cursor.execute(
+                """
+                UPDATE order_line_items
+                SET line_status = 'reserved',
+                    updated_at = NOW()
+                WHERE id = %s
+                  AND order_id = %s
+                """,
+                (str(line_item_id), str(order_id)),
+            )
+            return {
+                "action": "line_status_corrected",
+                "order_id": str(order_id),
+                "line_item_id": str(line_item_id),
+                "trace_id": trace_id,
+            }
+
+        # If deficit disappeared due to race/live processing, do nothing.
+        if active_reserved >= line_quantity:
+            return {
+                "action": "noop",
+                "reason": "deficit_resolved",
+                "order_id": str(order_id),
+                "line_item_id": str(line_item_id),
+                "line_status": line_status,
+                "line_quantity": line_quantity,
+                "active_reserved": active_reserved,
+                "trace_id": trace_id,
+            }
+
+        # 3) Open case dedupe (one active case per order+gate_name).
+        cursor.execute(
+            """
+            SELECT 1
+            FROM review_cases
+            WHERE order_id = %s::uuid
+              AND gate_name = 'rc4b_reservation_deficit'
+              AND status IN ('open', 'assigned', 'approved', 'executing')
+            LIMIT 1
+            """,
+            (str(order_id),),
+        )
+        if cursor.fetchone():
+            return {
+                "action": "noop",
+                "reason": "case_pending",
+                "order_id": str(order_id),
+                "line_item_id": str(line_item_id),
+                "trace_id": trace_id,
+            }
+
+        # 4) Escalate via governance review_case (requires trace_id).
+        if trace_id is None or str(trace_id).strip() == "":
+            return {
+                "action": "noop",
+                "reason": "trace_id_required_for_escalation",
+                "order_id": str(order_id),
+                "line_item_id": str(line_item_id),
+                "trace_id": trace_id,
+            }
+
+        # Local import to avoid adding runtime coupling at module import time.
+        from ru_worker import governance_workflow  # type: ignore
+
+        action_snapshot = {
+            "schema_version": 1,
+            "rc_code": "RC-4b",
+            "check_code": "IC-4",
+            "order_id": str(order_id),
+            "line_item_id": str(line_item_id),
+            "line_status": line_status,
+            "line_quantity": line_quantity,
+            "active_reserved": active_reserved,
+            "ic_verdict": ic_verdict,
+        }
+        result = governance_workflow.create_review_case(
+            db_conn,
+            trace_id=str(trace_id),
+            order_id=str(order_id),
+            gate_name="rc4b_reservation_deficit",
+            original_verdict="NEEDS_HUMAN",
+            original_decision_seq=1,
+            policy_hash="rc4b_reservation_deficit:v1",
+            action_snapshot=action_snapshot,
+            resume_context=None,
+            sla_deadline_at=None,
+        )
+        return {
+            "action": "escalated",
+            "order_id": str(order_id),
+            "line_item_id": str(line_item_id),
+            "case_id": result.get("case_id"),
+            "trace_id": trace_id,
+        }
+    finally:
+        cursor.close()
+
+
 def _expire_one_reservation_atomic(
     db_conn,
     *,
```

### `docs/_governance/diff_maintenance_sweeper.txt`
```diff
﻿diff --git a/.cursor/windmill-core-v1/maintenance_sweeper.py b/.cursor/windmill-core-v1/maintenance_sweeper.py
index 33f240f..afa7976 100644
--- a/.cursor/windmill-core-v1/maintenance_sweeper.py
+++ b/.cursor/windmill-core-v1/maintenance_sweeper.py
@@ -1,16 +1,20 @@
 from __future__ import annotations
 
+import json
 import os
 import time
 from datetime import datetime, timezone
-from typing import Dict, Iterable, List
+from typing import Dict, Iterable, List, Optional
 from uuid import UUID, uuid4
 
 from psycopg2.pool import SimpleConnectionPool
 
 from config import get_config
 from domain import observability_service as observability
+from domain import reconciliation_alerts as alerts
 from domain import reconciliation_service as reconciliation
+from domain import structural_checks
+from retention_policy import run_retention_cleanup
 from side_effects.adapters.cdek_adapter import CDEKShipmentAdapter
 from side_effects.adapters.tbank_adapter import TBankInvoiceAdapter
 from ru_worker.lib_integrations import log_event
@@ -18,6 +22,19 @@ from ru_worker.lib_integrations import log_event
 
 TERMINAL_STATES = ("completed", "cancelled", "failed")
 
+RC_AUDIT_META = {
+    "phase25_rc1_reconcile_payment_cache": ("RC-1", "L1", "order"),
+    "phase25_rc2_reconcile_shipment_cache": ("RC-2", "L1", "order"),
+    "phase25_rc3_rebuild_stock_snapshot": ("RC-3", "L1", "stock"),
+    "phase25_rc4_expire_reservations": ("RC-4", "L2", "reservation"),
+    "phase25_rc4b_escalate_reservation_deficit": ("RC-4b", "L2", "order_line_item"),
+    "phase25_rc5_reconcile_document_key": ("RC-5", "L1", "order"),
+    "phase25_rc6_resolve_pending_payment": ("RC-6", "L2", "payment_transaction"),
+    "phase25_rc7_sync_shipment_status": ("RC-7", "L2", "shipment"),
+}
+
+_CYCLE_COUNT = 0
+
 
 def _env_int(name: str, default: int) -> int:
     raw = os.getenv(name)
@@ -58,21 +75,246 @@ def _log_verdict(verdict: Dict[str, object]) -> None:
     log_event("phase25_invariant_verdict", verdict)
 
 
-def _run_rc(conn, *, event_name: str, fn, kwargs: Dict[str, object]) -> Dict[str, object]:
+def _derive_entity_id(event_name: str, kwargs: Dict[str, object]) -> str:
+    if event_name == "phase25_rc4b_escalate_reservation_deficit":
+        order_id = kwargs.get("order_id")
+        line_item_id = kwargs.get("line_item_id")
+        if order_id is not None and line_item_id is not None:
+            return f"{order_id}:{line_item_id}"
+        return "unknown"
+
+    if event_name == "phase25_rc3_rebuild_stock_snapshot":
+        product_id = kwargs.get("product_id")
+        warehouse_code = kwargs.get("warehouse_code")
+        if product_id is not None and warehouse_code is not None:
+            return f"{product_id}:{warehouse_code}"
+        return "unknown"
+
+    for key in ("order_id", "shipment_id", "payment_transaction_id"):
+        value = kwargs.get(key)
+        if value is not None:
+            return str(value)
+
+    return "unknown"
+
+
+def _log_audit_intent(
+    audit_conn,
+    *,
+    sweep_trace_id: str,
+    rc_code: str,
+    layer: str,
+    entity_type: str,
+    entity_id: str,
+    ic_verdict_before: Optional[Dict[str, object]] = None,
+) -> Optional[str]:
+    cursor = audit_conn.cursor()
+    try:
+        cursor.execute(
+            """
+            INSERT INTO reconciliation_audit_log (
+                sweep_trace_id, rc_code, layer, entity_type, entity_id,
+                phase, ic_verdict_before, action_result, outcome, error_detail
+            )
+            VALUES (
+                %s::uuid, %s, %s, %s, %s,
+                'INTENT', %s::jsonb, NULL, 'pending', NULL
+            )
+            RETURNING id
+            """,
+            (
+                str(sweep_trace_id),
+                str(rc_code),
+                str(layer),
+                str(entity_type),
+                str(entity_id),
+                json.dumps(ic_verdict_before, ensure_ascii=False) if ic_verdict_before is not None else None,
+            ),
+        )
+        row = cursor.fetchone()
+        return str(row[0]) if row else None
+    except Exception as exc:
+        log_event(
+            "phase25_audit_intent_error",
+            {
+                "error": str(exc),
+                "trace_id": str(sweep_trace_id),
+                "rc": str(rc_code),
+                "entity_type": str(entity_type),
+                "entity_id": str(entity_id),
+            },
+        )
+        return None
+    finally:
+        cursor.close()
+
+
+def _log_audit_outcome(
+    audit_conn,
+    *,
+    audit_row_id: str,
+    outcome: str,
+    action_result: Optional[Dict[str, object]] = None,
+    error_detail: Optional[str] = None,
+) -> None:
+    cursor = audit_conn.cursor()
+    try:
+        cursor.execute(
+            """
+            UPDATE reconciliation_audit_log
+            SET phase = 'OUTCOME',
+                outcome = %s,
+                action_result = %s::jsonb,
+                error_detail = %s
+            WHERE id = %s::uuid
+            """,
+            (
+                str(outcome),
+                json.dumps(action_result, ensure_ascii=False) if action_result is not None else None,
+                error_detail,
+                str(audit_row_id),
+            ),
+        )
+    except Exception as exc:
+        log_event(
+            "phase25_audit_outcome_error",
+            {
+                "error": str(exc),
+                "audit_row_id": str(audit_row_id),
+                "outcome": str(outcome),
+            },
+        )
+    finally:
+        cursor.close()
+
+
+def _sweep_orphaned_intents(audit_conn) -> None:
+    cursor = audit_conn.cursor()
+    try:
+        cursor.execute(
+            """
+            UPDATE reconciliation_audit_log
+            SET phase = 'OUTCOME',
+                outcome = 'crash'
+            WHERE phase = 'INTENT'
+              AND outcome = 'pending'
+              AND created_at < (NOW() - INTERVAL '5 minutes')
+            """,
+        )
+    except Exception as exc:
+        log_event("phase25_audit_orphan_sweep_error", {"error": str(exc)})
+    finally:
+        cursor.close()
+
+
+def _run_rc(
+    conn,
+    *,
+    event_name: str,
+    fn,
+    kwargs: Dict[str, object],
+    audit_conn=None,
+    sweep_trace_id: Optional[str] = None,
+    ic_verdict: Optional[Dict[str, object]] = None,
+) -> Dict[str, object]:
+    audit_row_id: Optional[str] = None
+    if audit_conn is not None and sweep_trace_id is not None:
+        meta = RC_AUDIT_META.get(event_name)
+        if meta is not None:
+            rc_code, layer, entity_type = meta
+            entity_id = _derive_entity_id(event_name, kwargs)
+            audit_row_id = _log_audit_intent(
+                audit_conn,
+                sweep_trace_id=str(sweep_trace_id),
+                rc_code=str(rc_code),
+                layer=str(layer),
+                entity_type=str(entity_type),
+                entity_id=str(entity_id),
+                ic_verdict_before=ic_verdict,
+            )
+
     try:
         result = fn(conn, **kwargs)
         if hasattr(conn, "commit"):
             conn.commit()
+
+        if audit_conn is not None and audit_row_id is not None:
+            action = result.get("action") if isinstance(result, dict) else None
+            outcome = "noop" if action in {"noop", "duplicate"} else "success"
+            _log_audit_outcome(
+                audit_conn,
+                audit_row_id=str(audit_row_id),
+                outcome=outcome,
+                action_result=result if isinstance(result, dict) else None,
+                error_detail=None,
+            )
+
         log_event(event_name, {"result": result, "trace_id": kwargs.get("trace_id")})
         return {"ok": True, "result": result}
     except Exception as exc:
         if hasattr(conn, "rollback"):
             conn.rollback()
+
+        if audit_conn is not None and audit_row_id is not None:
+            _log_audit_outcome(
+                audit_conn,
+                audit_row_id=str(audit_row_id),
+                outcome="rollback",
+                action_result=None,
+                error_detail=str(exc),
+            )
+
         payload = {"error": str(exc), "trace_id": kwargs.get("trace_id"), "rc": event_name}
         log_event("phase25_reconciliation_error", payload)
         return {"ok": False, "error": str(exc)}
 
 
+def _run_l3_checks(check_conn, *, sweep_trace_id: str, trace_id: str) -> None:
+    results = [
+        structural_checks.check_stock_ledger_non_negative(check_conn, trace_id=trace_id),
+        structural_checks.check_reservations_for_terminal_orders(check_conn, trace_id=trace_id),
+    ]
+
+    for res in results:
+        check_code = str(res.get("check_code") or "L3-UNKNOWN")
+        severity = str(res.get("severity") or "MEDIUM")
+        verdict = str(res.get("verdict") or "UNKNOWN")
+        problems = res.get("problems") if isinstance(res.get("problems"), list) else []
+
+        if verdict != "FAIL":
+            continue
+
+        total = len(problems)
+        if total > 10:
+            sample = problems[:10]
+            try:
+                alerts.emit_batch_alert(
+                    check_conn,
+                    sweep_trace_id=sweep_trace_id,
+                    check_code=check_code,
+                    severity=severity,
+                    sample=sample,
+                    total_count=total,
+                )
+            except Exception as exc:
+                log_event("phase25_l3_alert_error", {"error": str(exc), "trace_id": trace_id, "check_code": check_code})
+            continue
+
+        for p in problems:
+            try:
+                alerts.emit_alert(
+                    check_conn,
+                    sweep_trace_id=sweep_trace_id,
+                    check_code=check_code,
+                    entity_type=str(p.get("entity_type") or "unknown"),
+                    entity_id=str(p.get("entity_id") or "unknown"),
+                    severity=severity,
+                    verdict_snapshot={"check_code": check_code, "problem": p},
+                )
+            except Exception as exc:
+                log_event("phase25_l3_alert_error", {"error": str(exc), "trace_id": trace_id, "check_code": check_code})
+
+
 def _scan_active_orders(conn, *, limit: int) -> List[UUID]:
     rows = _run_select(
         conn,
@@ -142,6 +384,9 @@ def _process_order(
     order_id: UUID,
     trace_id: str,
     cdek_adapter: CDEKShipmentAdapter,
+    audit_conn=None,
+    sweep_trace_id: Optional[str] = None,
+    rc4b_budget: Optional[Dict[str, int]] = None,
 ) -> None:
     verdicts = observability.collect_order_invariant_verdicts(
         conn,
@@ -164,6 +409,30 @@ def _process_order(
         )
         _log_verdict(verdict)
 
+        if verdict.get("verdict") == "FAIL":
+            limit = int((rc4b_budget or {}).get("limit", 0))
+            used = int((rc4b_budget or {}).get("used", 0))
+            if limit > 0 and used >= limit:
+                continue
+
+            rc4b = _run_rc(
+                conn,
+                event_name="phase25_rc4b_escalate_reservation_deficit",
+                fn=reconciliation.escalate_reservation_deficit,
+                kwargs={
+                    "order_id": order_id,
+                    "line_item_id": line_item_id,
+                    "ic_verdict": verdict,
+                    "trace_id": trace_id,
+                },
+                audit_conn=audit_conn,
+                sweep_trace_id=sweep_trace_id,
+                ic_verdict=verdict,
+            )
+            if rc4b_budget is not None and rc4b.get("ok") and isinstance(rc4b.get("result"), dict):
+                if rc4b["result"].get("action") == "escalated":
+                    rc4b_budget["used"] = int(rc4b_budget.get("used", 0)) + 1
+
     for verdict in verdicts:
         if verdict.get("check_name") == "IC-1" and verdict.get("verdict") == "FAIL":
             _run_rc(
@@ -171,6 +440,9 @@ def _process_order(
                 event_name="phase25_rc1_reconcile_payment_cache",
                 fn=reconciliation.reconcile_payment_cache,
                 kwargs={"order_id": order_id, "trace_id": trace_id},
+                audit_conn=audit_conn,
+                sweep_trace_id=sweep_trace_id,
+                ic_verdict=verdict,
             )
         elif verdict.get("check_name") == "IC-2" and verdict.get("verdict") == "FAIL":
             _run_rc(
@@ -178,6 +450,9 @@ def _process_order(
                 event_name="phase25_rc2_reconcile_shipment_cache",
                 fn=reconciliation.reconcile_shipment_cache,
                 kwargs={"order_id": order_id, "trace_id": trace_id},
+                audit_conn=audit_conn,
+                sweep_trace_id=sweep_trace_id,
+                ic_verdict=verdict,
             )
         elif verdict.get("check_name") == "IC-5" and verdict.get("verdict") == "FAIL":
             _run_rc(
@@ -185,6 +460,9 @@ def _process_order(
                 event_name="phase25_rc5_reconcile_document_key",
                 fn=reconciliation.reconcile_document_key,
                 kwargs={"order_id": order_id, "trace_id": trace_id},
+                audit_conn=audit_conn,
+                sweep_trace_id=sweep_trace_id,
+                ic_verdict=verdict,
             )
         elif verdict.get("check_name") == "IC-7" and verdict.get("verdict") == "STALE":
             for shipment_id in _scan_active_shipments(
@@ -201,6 +479,9 @@ def _process_order(
                         "adapter": cdek_adapter,
                         "trace_id": trace_id,
                     },
+                    audit_conn=audit_conn,
+                    sweep_trace_id=sweep_trace_id,
+                    ic_verdict=verdict,
                 )
 
 
@@ -210,12 +491,44 @@ def _run_cycle(
     tbank_adapter: TBankInvoiceAdapter,
     cdek_adapter: CDEKShipmentAdapter,
 ) -> None:
+    global _CYCLE_COUNT
+    _CYCLE_COUNT += 1
     conn = pool.getconn()
+    audit_conn = None
     try:
         conn.autocommit = False
         trace_id = str(uuid4())
         now_ts = datetime.now(timezone.utc)
 
+        try:
+            audit_conn = pool.getconn()
+            audit_conn.autocommit = True
+        except Exception as exc:
+            log_event("phase25_audit_conn_error", {"error": str(exc), "trace_id": trace_id})
+            audit_conn = None
+
+        if audit_conn is not None:
+            _sweep_orphaned_intents(audit_conn)
+
+        # Expire active suppressions with elapsed snooze TTL.
+        try:
+            expiry_conn = audit_conn if audit_conn is not None else conn
+            cur = expiry_conn.cursor()
+            try:
+                cur.execute(
+                    """
+                    UPDATE reconciliation_suppressions
+                    SET suppression_state = 'expired'
+                    WHERE suppression_state = 'active'
+                      AND expires_at IS NOT NULL
+                      AND expires_at < NOW()
+                    """
+                )
+            finally:
+                cur.close()
+        except Exception as exc:
+            log_event("phase25_suppression_expiry_error", {"error": str(exc), "trace_id": trace_id})
+
         ic8 = observability.check_zombie_reservations(conn, trace_id=trace_id, now_ts=now_ts)
         _log_verdict(ic8)
         ic9 = observability.check_orphan_payment_transactions(conn, trace_id=trace_id, now_ts=now_ts)
@@ -230,6 +543,9 @@ def _run_cycle(
                 "batch_limit": _env_int("MAINTENANCE_RC4_BATCH_LIMIT", 100),
                 "now": now_ts,
             },
+            audit_conn=audit_conn,
+            sweep_trace_id=trace_id,
+            ic_verdict=ic8,
         )
 
         if ic9.get("verdict") == "STALE":
@@ -246,15 +562,25 @@ def _run_cycle(
                         "adapter": tbank_adapter,
                         "trace_id": trace_id,
                     },
+                    audit_conn=audit_conn,
+                    sweep_trace_id=trace_id,
+                    ic_verdict=ic9,
                 )
 
         active_order_limit = _env_int("MAINTENANCE_ACTIVE_ORDER_LIMIT", 100)
+        rc4b_budget = {
+            "limit": _env_int("MAINTENANCE_RC4B_CASE_LIMIT", 5),
+            "used": 0,
+        }
         for order_id in _scan_active_orders(conn, limit=active_order_limit):
             _process_order(
                 conn,
                 order_id=order_id,
                 trace_id=trace_id,
                 cdek_adapter=cdek_adapter,
+                audit_conn=audit_conn,
+                sweep_trace_id=trace_id,
+                rc4b_budget=rc4b_budget,
             )
 
         stock_target_limit = _env_int("MAINTENANCE_STOCK_CHECK_LIMIT", 100)
@@ -276,8 +602,28 @@ def _run_cycle(
                         "warehouse_code": warehouse_code,
                         "trace_id": trace_id,
                     },
+                    audit_conn=audit_conn,
+                    sweep_trace_id=trace_id,
+                    ic_verdict=verdict,
                 )
+
+        every_n = _env_int("MAINTENANCE_L3_EVERY_NTH_CYCLE", 10)
+        if every_n > 0 and (_CYCLE_COUNT % every_n) == 0:
+            check_conn = audit_conn if audit_conn is not None else conn
+            _run_l3_checks(check_conn, sweep_trace_id=trace_id, trace_id=trace_id)
+            if check_conn is conn and hasattr(conn, "commit"):
+                conn.commit()
+
+        retention_every_n = _env_int("RETENTION_EVERY_NTH_CYCLE", 50)
+        if retention_every_n > 0 and (_CYCLE_COUNT % retention_every_n) == 0:
+            if audit_conn is not None:
+                try:
+                    run_retention_cleanup(audit_conn, trace_id=trace_id)
+                except Exception as exc:
+                    log_event("retention_cleanup_error", {"error": str(exc), "trace_id": trace_id})
     finally:
+        if audit_conn is not None:
+            pool.putconn(audit_conn)
         pool.putconn(conn)
 
 
```

### `docs/_governance/diff_tier1_hashes.txt`
```diff

```

## D) Pytest
- pytest_status: PASS
- PYTEST_EXIT_CODE: 0

### Last 200 lines of `pytest_output.txt`
```text
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-9.0.2, pluggy-1.6.0 -- C:\Users\Eugene\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: C:\cursor_project\biretos-automation\.cursor\windmill-core-v1
configfile: pytest.ini
plugins: anyio-3.7.1
collecting ... collected 128 items

tests/test_governance_decisions.py::test_record_human_approve_inserts_correctly PASSED [  0%]
tests/test_governance_decisions.py::test_decision_seq_increments_with_mixed_gates PASSED [  1%]
tests/test_governance_decisions.py::test_decision_seq_increments_for_same_gate PASSED [  2%]
tests/test_governance_decisions.py::test_trace_id_none_raises PASSED     [  3%]
tests/test_governance_decisions.py::test_replay_mode_raises PASSED       [  3%]
tests/test_governance_decisions.py::test_corrections_content_in_decision_context PASSED [  4%]
tests/test_governance_decisions.py::test_override_ref_in_decision_context PASSED [  5%]
tests/test_governance_executor.py::test_executor_happy_path PASSED       [  6%]
tests/test_governance_executor.py::test_executor_replay_verified PASSED  [  7%]
tests/test_governance_executor.py::test_executor_replay_divergence_executing PASSED [  7%]
tests/test_governance_executor.py::test_executor_replay_divergence_approved PASSED [  8%]
tests/test_governance_executor.py::test_executor_replay_divergence_cancelled PASSED [  9%]
tests/test_governance_executor.py::test_executor_claim_race_loses PASSED [ 10%]
tests/test_governance_executor.py::test_executor_resume_no_idempotency_row PASSED [ 10%]
tests/test_governance_executor.py::test_executor_resume_sweeper_failed_lock PASSED [ 11%]
tests/test_governance_executor.py::test_executor_genuine_failure_no_retry PASSED [ 12%]
tests/test_governance_executor.py::test_executor_duplicate_succeeded PASSED [ 13%]
tests/test_governance_executor.py::test_executor_duplicate_processing PASSED [ 14%]
tests/test_governance_executor.py::test_executor_leaf_failure_marks_cancelled PASSED [ 14%]
tests/test_governance_executor.py::test_executor_snapshot_validation_failure PASSED [ 15%]
tests/test_governance_executor.py::test_executor_external_key_injected PASSED [ 16%]
tests/test_governance_executor.py::test_executor_cdek_409_treated_as_success PASSED [ 17%]
tests/test_governance_executor.py::test_executor_step3b_retry_limit PASSED [ 17%]
tests/test_governance_trigger.py::test_trigger_happy_path PASSED         [ 18%]
tests/test_governance_trigger.py::test_trigger_snapshot_has_required_fields PASSED [ 19%]
tests/test_governance_trigger.py::test_trigger_external_key_is_uuid PASSED [ 20%]
tests/test_governance_trigger.py::test_trigger_unsupported_action_type PASSED [ 21%]
tests/test_governance_trigger.py::test_trigger_resolution_failure_tbank PASSED [ 21%]
tests/test_governance_trigger.py::test_trigger_resolution_failure_mapping PASSED [ 22%]
tests/test_governance_trigger.py::test_trigger_idempotent_enqueue_key_format PASSED [ 23%]
tests/test_governance_workflow.py::test_create_review_case_inserts_correctly PASSED [ 24%]
tests/test_governance_workflow.py::test_create_review_case_idempotent PASSED [ 25%]
tests/test_governance_workflow.py::test_create_review_case_idempotency_key_format PASSED [ 25%]
tests/test_governance_workflow.py::test_assign_case PASSED               [ 26%]
tests/test_governance_workflow.py::test_resolve_case PASSED              [ 27%]
tests/test_governance_workflow.py::test_case_creator_replay_skips PASSED [ 28%]
tests/test_governance_workflow.py::test_case_creator_creates_case PASSED [ 28%]
tests/test_governance_workflow.py::test_resolve_order_id_excluded PASSED [ 29%]
tests/test_governance_workflow.py::test_approve_case_from_open PASSED    [ 30%]
tests/test_governance_workflow.py::test_approve_case_from_assigned PASSED [ 31%]
tests/test_governance_workflow.py::test_approve_case_already_approved PASSED [ 32%]
tests/test_governance_workflow.py::test_claim_for_execution_success PASSED [ 32%]
tests/test_governance_workflow.py::test_claim_for_execution_not_approved PASSED [ 33%]
tests/test_governance_workflow.py::test_claim_concurrent_race PASSED     [ 34%]
tests/test_governance_workflow.py::test_mark_executed_from_executing PASSED [ 35%]
tests/test_governance_workflow.py::test_mark_executed_wrong_status PASSED [ 35%]
tests/test_governance_workflow.py::test_read_case_for_resume_executing PASSED [ 36%]
tests/test_governance_workflow.py::test_resolve_case_from_executing PASSED [ 37%]
tests/test_idempotency.py::test_t1_generate_key_ship_paid PASSED         [ 38%]
tests/test_idempotency.py::test_t2_generate_key_ship_paid_missing_invoice PASSED [ 39%]
tests/test_idempotency.py::test_t3_read_only_action_has_no_key PASSED    [ 39%]
tests/test_idempotency.py::test_t4_auto_ship_all_paid_has_no_key PASSED  [ 40%]
tests/test_idempotency.py::test_t5_tbank_payment_key_coarse_is_supported PASSED [ 41%]
tests/test_idempotency.py::test_t6_hash_stable_for_same_payload PASSED   [ 42%]
tests/test_idempotency.py::test_t7_hash_excludes_non_business_fields PASSED [ 42%]
tests/test_idempotency.py::test_t8_hash_is_sha256_shape PASSED           [ 43%]
tests/test_idempotency.py::test_t9_real_without_db_conn_raises PASSED    [ 44%]
tests/test_idempotency.py::test_t9b_idempotency_ttl_default_used_when_env_missing_or_invalid PASSED [ 45%]
tests/test_idempotency.py::test_t9c_idempotency_ttl_env_override_used PASSED [ 46%]
tests/test_idempotency.py::test_t10_acquire_new_lock PASSED              [ 46%]
tests/test_idempotency.py::test_t11_duplicate_succeeded_returns_cached_result PASSED [ 47%]
tests/test_idempotency.py::test_t12_duplicate_processing_detected PASSED [ 48%]
tests/test_idempotency.py::test_t13_stale_takeover PASSED                [ 49%]
tests/test_idempotency.py::test_t14_complete_with_correct_token PASSED   [ 50%]
tests/test_idempotency.py::test_t15_complete_with_wrong_token_rejected PASSED [ 50%]
tests/test_idempotency.py::test_t16_complete_after_sweeper_rejected PASSED [ 51%]
tests/test_idempotency.py::test_t17_sweeper_marks_expired_as_failed PASSED [ 52%]
tests/test_idempotency.py::test_t18_sweeper_is_idempotent PASSED         [ 53%]
tests/test_idempotency.py::test_t19_double_ship_paid_single_side_effect PASSED [ 53%]
tests/test_idempotency.py::test_t20_auto_ship_all_paid_fan_out PASSED    [ 54%]
tests/test_idempotency.py::test_t21_dry_run_real_actions_work_without_db PASSED [ 55%]
tests/test_idempotency.py::test_t22_dry_run_does_not_write_idempotency_rows PASSED [ 56%]
tests/validation/test_idempotency_migration_trace_id_index.py::test_action_idempotency_trace_id_index_migration_exists_and_mentions_index PASSED [ 57%]
tests/validation/test_phase25_contract_guards.py::test_observability_service_is_read_only PASSED [ 57%]
tests/validation/test_phase25_contract_guards.py::test_rc3_lock_order_for_update_before_ledger_sum PASSED [ 58%]
tests/validation/test_phase25_contract_guards.py::test_maintenance_sweeper_does_not_import_ru_worker_runtime_module PASSED [ 59%]
tests/validation/test_phase25_observability.py::test_ic1_payment_cache_integrity_pass_and_fail PASSED [ 60%]
tests/validation/test_phase25_observability.py::test_health_classifier_priority PASSED [ 60%]
tests/validation/test_phase25_reconciliation.py::test_rc1_reconcile_payment_cache_is_idempotent PASSED [ 61%]
tests/validation/test_phase25_reconciliation.py::test_rc4_allocated_line_guard_prevents_release PASSED [ 62%]
tests/validation/test_phase25_reconciliation.py::test_rc4_prevents_double_release_via_idempotency_key PASSED [ 63%]
tests/validation/test_phase25_replay_gate.py::test_replay_gate_pre_rebuild_inconsistent PASSED [ 64%]
tests/validation/test_phase25_replay_gate.py::test_replay_gate_deterministic_rebuild PASSED [ 64%]
tests/validation/test_phase25_replay_gate.py::test_replay_gate_rebuild_is_idempotent PASSED [ 65%]
tests/validation/test_phase2_contract_guards.py::test_availability_service_enforces_row_lock_and_atomic_snapshot_mutation PASSED [ 66%]
tests/validation/test_phase2_contract_guards.py::test_payment_service_keeps_insert_and_cache_recompute_in_single_service_path PASSED [ 67%]
tests/validation/test_phase2_contract_guards.py::test_shipment_cache_semantics_latest_non_cancelled PASSED [ 67%]
tests/validation/test_phase2_contract_guards.py::test_unwrap_flow_exists_in_cancel_transition PASSED [ 68%]
tests/validation/test_phase2_contract_guards.py::test_invoice_worker_uses_content_hash_document_contract_not_total_amount_key PASSED [ 69%]
tests/validation/test_phase2_contract_guards.py::test_fsm_contains_phase2_partial_states PASSED [ 70%]
tests/validation/test_phase2_document_contracts.py::test_document_generation_key_is_deterministic_for_equivalent_content PASSED [ 71%]
tests/validation/test_phase2_document_contracts.py::test_document_generation_key_changes_when_business_content_changes PASSED [ 71%]
tests/validation/test_phase2_document_contracts.py::test_reservation_chunk_keys_are_event_scoped_and_replay_safe PASSED [ 72%]
tests/validation/test_phase2_payment_service_runtime.py::test_payment_transaction_update_is_atomic_service_step_without_commit_side_effect PASSED [ 73%]
tests/validation/test_phase2_shipment_cache_runtime.py::test_recompute_order_cdek_cache_uses_latest_non_cancelled PASSED [ 74%]
tests/validation/test_phase2_unwrap_runtime.py::test_cancel_shipment_triggers_unpack_allocated_to_reserved PASSED [ 75%]
tests/validation/test_phase3_alert_emission.py::test_emit_alert_created_then_duplicate PASSED [ 75%]
tests/validation/test_phase3_alert_emission.py::test_emit_batch_alert_uses_unique_key PASSED [ 76%]
tests/validation/test_phase3_alert_emission.py::test_ack_alert_updates_state PASSED [ 77%]
tests/validation/test_phase3_cache_read_model_contract.py::test_cache_read_model_only_contract PASSED [ 78%]
tests/validation/test_phase3_cache_read_model_contract.py::test_detector_catches_synthetic_violation_strings PASSED [ 78%]
tests/validation/test_phase3_l3_structural_checks.py::test_check_stock_ledger_non_negative_pass_and_fail PASSED [ 79%]
tests/validation/test_phase3_l3_structural_checks.py::test_check_reservations_for_terminal_orders_pass_and_fail PASSED [ 80%]
tests/validation/test_phase3_replay_verify.py::test_verify_module_is_read_only_by_static_scan PASSED [ 81%]
tests/validation/test_phase3_replay_verify.py::test_verify_payment_cache_match_and_divergence PASSED [ 82%]
tests/validation/test_phase3_replay_verify.py::test_verify_shipment_cache_match_and_divergence PASSED [ 82%]
tests/validation/test_phase3_replay_verify.py::test_verify_document_key_match_and_divergence PASSED [ 83%]
tests/validation/test_phase3_replay_verify.py::test_verify_stock_snapshot_match_and_divergence PASSED [ 84%]
tests/validation/test_phase3_structural_safety_contract.py::test_structural_safety_contract_static_scan PASSED [ 85%]
tests/validation/test_phase3_structural_safety_contract.py::test_structural_safety_detector_catches_synthetic_forbidden_insert PASSED [ 85%]
tests/validation/test_r1_catalog_pipeline.py::test_r1_01_happy_path_3_rows PASSED [ 86%]
tests/validation/test_r1_catalog_pipeline.py::test_r1_02_parse_stage_single_commit PASSED [ 87%]
tests/validation/test_r1_catalog_pipeline.py::test_r1_03_sync_stage_commit_per_row PASSED [ 88%]
tests/validation/test_r1_catalog_pipeline.py::test_r1_04_photo_failure_non_blocking PASSED [ 89%]
tests/validation/test_r1_catalog_pipeline.py::test_r1_05_idempotency_done_skip PASSED [ 89%]
tests/validation/test_r1_catalog_pipeline.py::test_r1_05b_idempotency_failed_skip PASSED [ 90%]
tests/validation/test_r1_catalog_pipeline.py::test_r1_06_publisher_error_row_failed PASSED [ 91%]
tests/validation/test_r1_catalog_pipeline.py::test_r1_07_parse_error_job_failed PASSED [ 92%]
tests/validation/test_r1_catalog_pipeline.py::test_r1_08_missing_trace_id PASSED [ 92%]
tests/validation/test_r1_catalog_pipeline.py::test_r1_09_empty_rows_rejected PASSED [ 93%]
tests/validation/test_r1_catalog_pipeline.py::test_r1_10_no_reconciliation_imports PASSED [ 94%]
tests/validation/test_shopware_spike_dry_run.py::test_shopware_product_sync_dry_run_creates_operation_and_confirms PASSED [ 95%]
tests/validation/test_shopware_spike_dry_run.py::test_shopware_product_sync_second_run_is_skip_and_no_upsert PASSED [ 96%]
tests/validation/test_shopware_spike_dry_run.py::test_shopware_product_sync_stale_pending_takeover PASSED [ 96%]
tests/validation/test_shopware_spike_dry_run.py::test_shopware_product_sync_marks_failed_on_api_error PASSED [ 97%]
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed PASSED [ 98%]
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset PASSED [ 99%]
tests/validation/test_tier1_stability_guards.py::test_sweeper_uses_safe_interval_parameterization PASSED [100%]

============================== warnings summary ===============================
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset
  C:\cursor_project\biretos-automation\.cursor\windmill-core-v1\webhook_service\main.py:258: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("startup")

tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset
  C:\Users\Eugene\AppData\Local\Programs\Python\Python312\Lib\site-packages\fastapi\applications.py:4547: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    return self.router.on_event(event_type)

tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fail_closed
tests/validation/test_tier1_stability_guards.py::test_webhook_auth_fails_when_secrets_unset
  C:\cursor_project\biretos-automation\.cursor\windmill-core-v1\webhook_service\main.py:263: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("shutdown")

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 128 passed, 8 warnings in 0.82s =======================

PYTEST_EXIT_CODE=0
```

## E) Hash proof (full)
```text
# Tier-1 Hash Proof
total_entries: 19
match_count: 19
mismatch_count: 0

MATCH    | maintenance_sweeper.py | f4d31b85adc195f4386c5e3ab67cd10d85977a5842db356612e2c217dec50153
MATCH    | retention_policy.py | cefd11faad3d0eb459511fc45c4dd36f6be65220d839510779542081e1cb5f04
MATCH    | domain/reconciliation_service.py | eb0ccddd72a25f22e84e06b2e0de5c8092dca0056318b1ba9b315b38538934b1
MATCH    | domain/reconciliation_verify.py | c021d151efb3ecd873fbd58edf17925911bb55735ff43884f9cc7ad41b2e96b5
MATCH    | domain/reconciliation_alerts.py | 966c8a19f5c23ba1a52214c9597f6c4d2e9268223c7dd60d7411a9b50b9c1926
MATCH    | domain/structural_checks.py | 8e76de8bd1fa4919f827c24cd3c8a9c1d69975349824e8002511a0a711656e09
MATCH    | domain/observability_service.py | 3d11d417e447edeb214fd0f34f0c97fc9275bb15b518787d29c8c20215cab6fd
MATCH    | migrations/016_create_reconciliation_audit_log.sql | 390e5fcabfd66b468c680bc90af50efe8c1165a8753a019700979c3672471b83
MATCH    | migrations/017_create_reconciliation_suppressions.sql | de85fe23677c29fab8d113a6607096a64be6666b9a9b579b2444366c46dbddd6
MATCH    | migrations/018_create_reconciliation_alerts.sql | 509ab70dc86a114d3e7f7c7dc75ecffe57157ac3e6c78125d8889251cb162695
MATCH    | migrations/019_add_retention_indexes.sql | 57e285c662abfcb88024551a754a1b3418728e02c4d7d891e0d7a0f2828f34ea
MATCH    | docs/RETENTION_INVARIANT.md | 51c365994769a1be88be95c0b1be5f0f9fe286ad9415583c79dc7fd78b698ebe
MATCH    | tests/validation/test_phase3_alert_emission.py | 7c79790cf37b73288d6ea159aca626c6adfe79dcaf21ad5018d2bacad3f9c62c
MATCH    | tests/validation/test_phase3_cache_read_model_contract.py | 7caefdd44d905bff3742d1e5e6c0acc945d01cf7ff7d9024baffaeb055d1cb4b
MATCH    | tests/validation/test_phase3_l3_structural_checks.py | 9a2043f2d0148f2b0f0525236da05f614369c4a174aec03eb6bb89c695e0aeab
MATCH    | tests/validation/test_phase3_replay_verify.py | a54ae1717d34b813c52c133071d689afb75a8f6c2ce09442728c5da705f90b93
MATCH    | tests/validation/test_phase3_structural_safety_contract.py | 52cdc50831ecb19bbe56a8516d1660d54a05693396a7b0192202a3f7ee037b64
MATCH    | tests/validation/test_phase25_contract_guards.py | a2e63ed77be1f32b5b022ba85bfe6cef59bf5ffa6d6bd1d0a1bb3684db64e338
MATCH    | tests/validation/test_phase25_replay_gate.py | fc3458a75d0c55361fe81a6982b89c111bc8792dbfabb3bc05438efb70365609
```

## F) Untracked referenced by manifest (full)
```text
.cursor/windmill-core-v1/retention_policy.py
.cursor/windmill-core-v1/domain/reconciliation_verify.py
.cursor/windmill-core-v1/domain/reconciliation_alerts.py
.cursor/windmill-core-v1/domain/structural_checks.py
.cursor/windmill-core-v1/migrations/016_create_reconciliation_audit_log.sql
.cursor/windmill-core-v1/migrations/017_create_reconciliation_suppressions.sql
.cursor/windmill-core-v1/migrations/018_create_reconciliation_alerts.sql
.cursor/windmill-core-v1/migrations/019_add_retention_indexes.sql
.cursor/windmill-core-v1/docs/RETENTION_INVARIANT.md
.cursor/windmill-core-v1/tests/validation/test_phase3_alert_emission.py
.cursor/windmill-core-v1/tests/validation/test_phase3_cache_read_model_contract.py
.cursor/windmill-core-v1/tests/validation/test_phase3_l3_structural_checks.py
.cursor/windmill-core-v1/tests/validation/test_phase3_replay_verify.py
.cursor/windmill-core-v1/tests/validation/test_phase3_structural_safety_contract.py
```

## G) SECURITY_GATE.md (full)
```markdown
# SECURITY GATE (Phase P0)

Status: PENDING

- [ ] Credential rotation complete (owner)
- [x] Sensitive files removed from git index (no secret content disclosed)
- [x] Ignore patterns updated in `.gitignore`

Notes:
- No secret values are recorded in this artifact.
- Do not proceed to commit/push until owner confirms rotation.
```

## H) run_state_pre.md (full)
```markdown
# Run State Pre

- repo_root: C:\cursor_project\biretos-automation
- branch: master
- last_commit: 4d81d4c docs: complete Tier-3 worker system with enhanced logging, error handling, and tests.

## git status (full)

`
On branch master
Your branch is ahead of 'origin/master' by 4 commits.
  (use "git push" to publish your local commits)

Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
	deleted:    perplexity/ZAPI_enriched.xlsx
	deleted:    perplexity/ZAPI_enriched_test.xlsx

Changes not staged for commit:
  (use "git add/rm <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   .cursor/windmill-core-v1/.tier1-hashes.sha256
	modified:   .cursor/windmill-core-v1/CREDENTIALS_FOUND.md
	modified:   .cursor/windmill-core-v1/domain/reconciliation_service.py
	modified:   .cursor/windmill-core-v1/maintenance_sweeper.py
	modified:   .cursor/windmill-core-v1/migrations/015_add_review_cases_executing_status.sql
	modified:   .cursor/windmill-core-v1/pytest.ini
	modified:   .cursor/windmill-core-v1/ru_worker/dispatch_action.py
	modified:   .cursor/windmill-core-v1/ru_worker/idempotency.py
	modified:   .cursor/windmill-core-v1/tests/test_idempotency.py
	modified:   .env
	modified:   .gitignore
	modified:   BP-Verification-Checklist.md
	deleted:    EXECUTION_ROADMAP_v1.0.md
	deleted:    EXECUTION_ROADMAP_v2.0.md
	deleted:    MASTER_PLAN_v1.4.3.md
	deleted:    MASTER_PLAN_v1.7.2.md
	modified:   price-checker/.env
	modified:   scripts/lot_scoring/run_full_ranking_v341.py
	modified:   scripts/lot_scoring/tests/test_explain_v4.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	.cursor/rules/lot-structure-analysis.mdc
	.cursor/windmill-core-v1/docs/PHASE2_BOUNDARY.md
	.cursor/windmill-core-v1/docs/RETENTION_INVARIANT.md
	.cursor/windmill-core-v1/domain/reconciliation_alerts.py
	.cursor/windmill-core-v1/domain/reconciliation_verify.py
	.cursor/windmill-core-v1/domain/structural_checks.py
	.cursor/windmill-core-v1/migrations/016_create_reconciliation_audit_log.sql
	.cursor/windmill-core-v1/migrations/017_create_reconciliation_suppressions.sql
	.cursor/windmill-core-v1/migrations/018_create_reconciliation_alerts.sql
	.cursor/windmill-core-v1/migrations/019_add_retention_indexes.sql
	.cursor/windmill-core-v1/migrations/020_create_stg_catalog_jobs.sql
	.cursor/windmill-core-v1/migrations/021_create_stg_catalog_imports.sql
	.cursor/windmill-core-v1/retention_policy.py
	.cursor/windmill-core-v1/tests/validation/test_phase3_alert_emission.py
	.cursor/windmill-core-v1/tests/validation/test_phase3_cache_read_model_contract.py
	.cursor/windmill-core-v1/tests/validation/test_phase3_l3_structural_checks.py
	.cursor/windmill-core-v1/tests/validation/test_phase3_replay_verify.py
	.cursor/windmill-core-v1/tests/validation/test_phase3_structural_safety_contract.py
	.cursor/windmill-core-v1/tests/validation/test_r1_catalog_pipeline.py
	.cursor/windmill-core-v1/workers/
	.env.example
	EXECUTION_ROADMAP_v2_2.md
	MASTER_PLAN_v1_8_0.md
	_archive/
	audits/
	data/
	downloads/
	scripts/lot_scoring/__init__.py
	scripts/lot_scoring/audits/
	scripts/lot_scoring/capital_map.py
	scripts/lot_scoring/category_engine.py
	scripts/lot_scoring/cdm.py
	scripts/lot_scoring/cqr.py
	scripts/lot_scoring/data/
	scripts/lot_scoring/etl/
	scripts/lot_scoring/extract_lot_core.py
	scripts/lot_scoring/filters/
	scripts/lot_scoring/governance_config.py
	scripts/lot_scoring/io/
	scripts/lot_scoring/llm_auditor.py
	scripts/lot_scoring/merge_quarantine.py
	scripts/lot_scoring/pipeline/
	scripts/lot_scoring/run_batch_lot_processing.py
	scripts/lot_scoring/run_commit4_sanity_check.py
	scripts/lot_scoring/run_config.py
	scripts/lot_scoring/run_filters_pipeline.py
	scripts/lot_scoring/run_hybrid_audit.py
	scripts/lot_scoring/run_llm_classify_v2.py
	scripts/lot_scoring/run_llm_quarantine_pipeline.py
	scripts/lot_scoring/run_lot_analysis.py
	scripts/lot_scoring/run_quarantine_console.py
	scripts/lot_scoring/run_series_pipeline.py
	scripts/lot_scoring/run_stage3_automation.py
	scripts/lot_scoring/run_top50_unknown_recon.py
	scripts/lot_scoring/run_web_enriched_llm_pipeline.py
	scripts/lot_scoring/simulation/
	scripts/lot_scoring/tests/__init__.py
	scripts/lot_scoring/tests/test_abs_score.py
	scripts/lot_scoring/tests/test_brand_integration.py
	scripts/lot_scoring/tests/test_brand_intelligence.py
	scripts/lot_scoring/tests/test_brand_regression.py
	scripts/lot_scoring/tests/test_category_engine.py
	scripts/lot_scoring/tests/test_commit4_intelligence_baseline.py
	scripts/lot_scoring/tests/test_determinism_score.py
	scripts/lot_scoring/tests/test_hybrid_audit_llm_only.py
	scripts/lot_scoring/tests/test_llm_classify_v2.py
	scripts/lot_scoring/tests/test_multipliers.py
	scripts/lot_scoring/tests/test_pn_liquidity.py
	scripts/lot_scoring/tests/test_protocol_filters.py
	scripts/lot_scoring/tests/test_score10.py
	scripts/lot_scoring/tests/test_simulation.py
	scripts/lot_scoring/tests/test_stage3_automation.py
	scripts/lot_scoring/tests/test_stage4_guardrails.py
	scripts/lot_scoring/tests/test_unknown_exposure.py
	scripts/lot_scoring/tests/test_v35_value_slice.py
	scripts/lot_scoring/tools/
	scripts/lot_scoring/volume_profile.py

`

## staged files at start (git diff --cached --name-only)

`
perplexity/ZAPI_enriched.xlsx
perplexity/ZAPI_enriched_test.xlsx
`
```

## I) Index snapshot AFTER hygiene
### `git diff --cached --name-status`
```text
D	.cursor/windmill-core-v1/CREDENTIALS_FOUND.md
D	.env
D	price-checker/.env
```

### `git diff --cached --name-only`
```text
.cursor/windmill-core-v1/CREDENTIALS_FOUND.md
.env
price-checker/.env
```

### OUT/REVENUE staged? NO

### Hygiene actions
- unstaged_non_allowlist_count: 2
- unstaged: perplexity/ZAPI_enriched.xlsx
- unstaged: perplexity/ZAPI_enriched_test.xlsx
- out_revenue_staged_before_count: 0

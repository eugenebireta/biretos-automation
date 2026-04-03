from __future__ import annotations

from typing import Any, Dict, Optional

from config import get_config
from idempotency import acquire_action_lock, complete_action, compute_request_hash
from lib_integrations import execute_cdek_shipment, log_event

import governance_workflow


SUPPORTED_LEAF_WORKERS = {"cdek_shipment"}
EXPECTED_SCHEMA_VERSION = 1
_MAX_SWEEPER_ATTEMPTS = 3
_BASE_TTL_SECONDS = 300
_CDEK_IDEMPOTENT_MARKERS = ("already exists", "409")


def _is_cdek_idempotent_success(result: Dict[str, Any]) -> bool:
    """
    Defensive handling for provider-level idempotency:
    CDEK may return HTTP 409 / 'already exists' on retry with the same order_id.
    """
    if not isinstance(result, dict):
        return False
    if result.get("status") == "success":
        return True
    err = str(result.get("error") or "").lower()
    return any(marker in err for marker in _CDEK_IDEMPOTENT_MARKERS)


def execute_governance_case(
    payload: Dict[str, Any],
    db_conn,
    *,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    cfg = get_config()
    mode = (getattr(cfg, "execution_mode", None) or "LIVE").strip().upper()

    case_id = payload.get("case_id")
    if not case_id:
        raise ValueError("case_id is required for governance_execute")

    if mode == "REPLAY":
        return _verify_replay(str(case_id), db_conn)
    return _execute_live(str(case_id), db_conn, trace_id=trace_id)


def _verify_replay(case_id: str, db_conn) -> Dict[str, Any]:
    """
    REPLAY verify-only: zero writes, zero external calls.
    """
    cursor = db_conn.cursor()
    try:
        cursor.execute("SELECT status FROM review_cases WHERE id = %s::uuid", (case_id,))
        row = cursor.fetchone()
        if not row:
            return {"status": "replay_divergence", "reason": "case_not_found"}
        case_status = str(row[0])
    finally:
        cursor.close()

    idempotency_key = f"gov_exec:{case_id}"
    cursor2 = db_conn.cursor()
    try:
        cursor2.execute(
            "SELECT status FROM action_idempotency_log WHERE idempotency_key = %s",
            (idempotency_key,),
        )
        row2 = cursor2.fetchone()
        log_status = str(row2[0]) if row2 else None
    finally:
        cursor2.close()

    if case_status == "executed" and log_status == "succeeded":
        return {"status": "replay_verified"}
    if case_status == "executing" and log_status == "succeeded":
        return {"status": "replay_needs_finalization"}
    if case_status == "executing" and log_status is None:
        return {"status": "replay_divergence", "reason": "incomplete_execution_no_lock"}
    if case_status == "executing":
        return {"status": "replay_divergence", "reason": "incomplete_execution"}
    if case_status == "approved":
        return {"status": "replay_divergence", "reason": "never_executed"}
    if case_status == "cancelled" and log_status == "succeeded":
        return {"status": "replay_divergence", "reason": "cancelled_after_success"}
    if case_status == "cancelled":
        return {"status": "replay_divergence", "reason": "execution_cancelled"}
    return {"status": "replay_divergence", "reason": "unexpected_state", "case_status": case_status, "log_status": log_status}


def _execute_live(case_id: str, db_conn, *, trace_id: Optional[str]) -> Dict[str, Any]:
    sweeper_retries_left = _MAX_SWEEPER_ATTEMPTS - 1

    # Step 1: Claim (approved -> executing) in its own tx boundary.
    claim = governance_workflow.claim_for_execution(db_conn, case_id=case_id)
    db_conn.commit()

    if claim is not None:
        action_snapshot = claim.get("action_snapshot") if isinstance(claim, dict) else None
        effective_trace_id = trace_id or claim.get("trace_id")
        log_event("governance_claim_acquired", {"case_id": case_id})
    else:
        # Step 1b: Resume path (crash-safe).
        case_state = governance_workflow.read_case_for_resume(db_conn, case_id=case_id)
        if case_state is None:
            return {"status": "skipped", "reason": "case_not_found"}
        if case_state.get("status") == "executed":
            return {"status": "success", "already_executed": True, "case_id": case_id}
        if case_state.get("status") != "executing":
            return {"status": "skipped", "reason": f"unexpected_status:{case_state.get('status')}", "case_id": case_id}
        action_snapshot = case_state.get("action_snapshot")
        effective_trace_id = trace_id or case_state.get("trace_id")

    # Step 2: Snapshot validation.
    if not isinstance(action_snapshot, dict):
        governance_workflow.resolve_case(db_conn, case_id=case_id, status="cancelled", resolved_by="governance_executor")
        db_conn.commit()
        return {"status": "error", "reason": "invalid_snapshot_type", "case_id": case_id}

    if int(action_snapshot.get("schema_version", -1)) != EXPECTED_SCHEMA_VERSION:
        governance_workflow.resolve_case(db_conn, case_id=case_id, status="cancelled", resolved_by="governance_executor")
        db_conn.commit()
        return {"status": "error", "reason": "invalid_schema_version", "case_id": case_id}

    leaf_worker_type = action_snapshot.get("leaf_worker_type")
    if leaf_worker_type not in SUPPORTED_LEAF_WORKERS:
        governance_workflow.resolve_case(db_conn, case_id=case_id, status="cancelled", resolved_by="governance_executor")
        db_conn.commit()
        return {"status": "error", "reason": "unsupported_leaf_worker", "case_id": case_id}

    leaf_payload_raw = action_snapshot.get("leaf_payload")
    if not isinstance(leaf_payload_raw, dict) or not leaf_payload_raw:
        governance_workflow.resolve_case(db_conn, case_id=case_id, status="cancelled", resolved_by="governance_executor")
        db_conn.commit()
        return {"status": "error", "reason": "missing_leaf_payload", "case_id": case_id}

    external_idempotency_key = action_snapshot.get("external_idempotency_key")
    if not external_idempotency_key:
        governance_workflow.resolve_case(db_conn, case_id=case_id, status="cancelled", resolved_by="governance_executor")
        db_conn.commit()
        return {"status": "error", "reason": "missing_external_idempotency_key", "case_id": case_id}

    # Step 3: Acquire idempotency lock.
    idempotency_key = f"gov_exec:{case_id}"
    request_hash = compute_request_hash("governance_execute", action_snapshot)

    while True:
        attempt = _MAX_SWEEPER_ATTEMPTS - sweeper_retries_left
        ttl = _BASE_TTL_SECONDS * (2 ** (attempt - 1))
        lock_result = acquire_action_lock(
            db_conn=db_conn,
            idempotency_key=idempotency_key,
            action_type="governance_execute",
            request_hash=request_hash,
            trace_id=str(effective_trace_id) if effective_trace_id else None,
            ttl_seconds=ttl,
        )

        lock_status = lock_result.get("status")
        if lock_status in {"ACQUIRED", "STALE_TAKEOVER"}:
            lease_token = lock_result.get("lease_token")
            break
        if lock_status == "DUPLICATE_SUCCEEDED":
            # Step 6: mark executed and exit.
            governance_workflow.mark_executed(db_conn, case_id=case_id)
            db_conn.commit()
            return {"status": "success", "case_id": case_id, "duplicate": "succeeded"}
        if lock_status == "DUPLICATE_PROCESSING":
            return {"status": "skipped", "reason": "another_worker_processing", "case_id": case_id}
        if lock_status == "DUPLICATE_FAILED":
            last_error = lock_result.get("last_error")
            if last_error == "lock_expired_by_sweeper" and sweeper_retries_left > 0:
                # Step 3b: Sweeper recovery, max 1 retry.
                cursor = db_conn.cursor()
                try:
                    cursor.execute(
                        "DELETE FROM action_idempotency_log WHERE idempotency_key = %s AND status = 'failed'",
                        (idempotency_key,),
                    )
                finally:
                    cursor.close()
                db_conn.commit()
                sweeper_retries_left -= 1
                continue
            governance_workflow.resolve_case(
                db_conn, case_id=case_id, status="cancelled",
                resolved_by="governance_executor",
            )
            db_conn.commit()
            log_event("governance_execute_retries_exhausted", {
                "case_id": case_id,
                "idempotency_key": idempotency_key,
                "last_error": last_error,
            })
            return {"status": "failed", "reason": "previous_execution_failed", "case_id": case_id, "last_error": last_error}

        return {"status": "error", "reason": f"unexpected_lock_status:{lock_status}", "case_id": case_id}

    # Step 4: Call leaf worker directly. Zero live reads here.
    cfg = get_config()
    leaf_payload: Dict[str, Any] = dict(leaf_payload_raw)
    leaf_payload["order_id"] = str(external_idempotency_key)

    result = execute_cdek_shipment(cfg, leaf_payload)
    if result.get("status") != "success" and _is_cdek_idempotent_success(result):
        result = dict(result)
        result["status"] = "success"
        result["_idempotent_recovery"] = True

    if result.get("status") != "success":
        # Step 4e: leaf failure -> failed + cancelled.
        complete_action(
            db_conn=db_conn,
            idempotency_key=idempotency_key,
            lease_token=str(lease_token),
            status="failed",
            last_error=result.get("error"),
        )
        governance_workflow.resolve_case(db_conn, case_id=case_id, status="cancelled", resolved_by="governance_executor")
        db_conn.commit()
        log_event(
            "governance_execute_failed",
            {"case_id": case_id, "idempotency_key": idempotency_key, "error": result.get("error")},
        )
        return {"status": "error", "case_id": case_id, "error": result.get("error")}

    # Step 5: Complete idempotency (succeeded).
    complete_action(
        db_conn=db_conn,
        idempotency_key=idempotency_key,
        lease_token=str(lease_token),
        status="succeeded",
        result_ref=result,
    )

    # Step 6: Mark executed.
    governance_workflow.mark_executed(db_conn, case_id=case_id)
    db_conn.commit()

    log_event(
        "governance_execute_succeeded",
        {"case_id": case_id, "idempotency_key": idempotency_key, "leaf_worker_type": leaf_worker_type},
    )
    return {"status": "success", "case_id": case_id, "result": result}

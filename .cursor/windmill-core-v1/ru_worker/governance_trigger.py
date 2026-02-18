from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from config import get_config
from lib_integrations import (
    execute_tbank_invoice_status,
    log_event,
    map_tbank_invoice_to_cdek_payload,
)


SUPPORTED_RESOLUTION_TYPES = {"ship_paid", "cdek_shipment"}
SNAPSHOT_SCHEMA_VERSION = 1


def _sha256_json(value: Any) -> str:
    # Deterministic hash for observability only.
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _lookup_csg_decision(db_conn, trace_id: str) -> Dict[str, Any]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT decision_seq, gate_name, policy_hash
            FROM control_decisions
            WHERE trace_id = %s::uuid
              AND verdict = 'NEEDS_HUMAN'
            ORDER BY decision_seq DESC
            LIMIT 1
            """,
            (trace_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("No NEEDS_HUMAN control_decision found for trace_id")

        decision_seq = row[0]
        gate_name = row[1]
        policy_hash = row[2]
        return {"decision_seq": int(decision_seq), "gate_name": str(gate_name), "policy_hash": str(policy_hash)}
    finally:
        cursor.close()


def _resolve_leaf_payload(action: Dict[str, Any], config) -> Dict[str, Any]:
    action_type = str(action.get("action_type") or "")
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}

    if action_type not in SUPPORTED_RESOLUTION_TYPES:
        raise ValueError(f"Unsupported action_type for resolution: {action_type}")

    invoice_id = payload.get("invoice_id")
    if not invoice_id:
        raise ValueError("invoice_id is required for governance resolution")

    invoice_status_result = execute_tbank_invoice_status(config, {"invoice_id": invoice_id})
    if invoice_status_result.get("status") != "success":
        raise RuntimeError(invoice_status_result.get("error", "Failed to check invoice status"))

    result_status = invoice_status_result.get("result_status", "unknown")
    if result_status != "paid":
        raise RuntimeError(f"invoice_not_paid:{result_status}")

    invoice_response = invoice_status_result.get("response", {}) if isinstance(invoice_status_result.get("response"), dict) else {}
    cdek_payload, mapping_error = map_tbank_invoice_to_cdek_payload(config, str(invoice_id), invoice_response)
    if mapping_error or not isinstance(cdek_payload, dict):
        raise RuntimeError(f"mapping_error:{mapping_error or 'unknown'}")

    return {
        "leaf_worker_type": "cdek_shipment",
        "leaf_payload": cdek_payload,
        "resolution_source_snapshot": {
            "tbank_invoice_status": str(result_status),
            "tbank_response_hash": f"sha256:{_sha256_json(invoice_response)}",
        },
    }


def handle_pending_approval(
    action: Dict[str, Any],
    pending_result: Dict[str, Any],
    db_conn,
    trace_id: str,
    config=None,
) -> Dict[str, Any]:
    """
    Build an enriched action_snapshot for deterministic governance execution and enqueue governance_case_create.
    """
    if not trace_id or str(trace_id).strip() == "":
        raise ValueError("trace_id is required for handle_pending_approval")

    action_type = str(action.get("action_type") or "")
    if action_type not in SUPPORTED_RESOLUTION_TYPES:
        return {"status": "error", "error": f"unsupported_action_type:{action_type}"}

    cfg = config or get_config()

    decision = _lookup_csg_decision(db_conn, str(trace_id))
    decision_seq = int(decision["decision_seq"])
    gate_name = str(decision["gate_name"])
    policy_hash = str(decision["policy_hash"])

    resolved = _resolve_leaf_payload(action, cfg)
    external_idempotency_key = str(uuid4())

    action_snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "action_type": action_type,
        "original_payload": action.get("payload", {}) if isinstance(action.get("payload"), dict) else {},
        "leaf_worker_type": resolved["leaf_worker_type"],
        "leaf_payload": resolved["leaf_payload"],
        "external_idempotency_key": external_idempotency_key,
        "resolved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "resolution_source_snapshot": resolved["resolution_source_snapshot"],
    }

    case_payload: Dict[str, Any] = {
        "trace_id": str(trace_id),
        "gate_name": gate_name,
        "original_verdict": "NEEDS_HUMAN",
        "original_decision_seq": decision_seq,
        "policy_hash": policy_hash,
        "action_snapshot": action_snapshot,
    }

    job_idempotency_key = f"gov_trigger:{trace_id}:{gate_name}:{int(decision_seq)}"

    # Local import to avoid circular import at module load time.
    from ru_worker import enqueue_job_with_trace  # type: ignore

    try:
        enqueue_job_with_trace(
            db_conn=db_conn,
            job_type="governance_case_create",
            payload=case_payload,
            idempotency_key=job_idempotency_key,
            trace_id=str(trace_id),
        )
    except Exception as e:
        msg = str(e).lower()
        if "duplicate" in msg or "unique" in msg:
            return {"status": "governance_case_enqueued", "duplicate": True, "idempotency_key": job_idempotency_key}
        raise

    log_event(
        "governance_case_enqueued",
        {
            "trace_id": str(trace_id),
            "gate_name": gate_name,
            "decision_seq": int(decision_seq),
            "policy_hash": policy_hash,
            "idempotency_key": job_idempotency_key,
            "action_type": action_type,
        },
    )

    return {"status": "governance_case_enqueued", "idempotency_key": job_idempotency_key}

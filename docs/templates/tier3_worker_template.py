#!/usr/bin/env python3
"""
Canonical Tier-3 worker template.

Compliance targets:
- PROJECT_DNA.md Mandatory Patterns 6-9
- docs/prompt_library/ai_reviewer.md checks C12-C15

Logging contracts:
- Decision log keys:
  event, ts, trace_id, entity_id, operation, state, outcome, reason
- Error log keys:
  event, ts, trace_id, entity_id, operation, error_class, severity, retriable, error

CLI contract:
python tier3_worker_template.py --trace-id <value> [--dry-run] [--payload '<json-object>']
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple


class ErrorClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    POLICY_VIOLATION = "POLICY_VIOLATION"


class Severity(str, Enum):
    WARNING = "WARNING"
    ERROR = "ERROR"


# Backward-compatible aliases for quick copy-paste usage.
TRANSIENT = ErrorClass.TRANSIENT.value
PERMANENT = ErrorClass.PERMANENT.value
POLICY_VIOLATION = ErrorClass.POLICY_VIOLATION.value


def _log(event: str, data: Dict[str, Any]) -> None:
    entry = {"event": event, "ts": time.time(), **data}
    print(json.dumps(entry, ensure_ascii=False), flush=True)


def log_decision(
    *,
    trace_id: str,
    entity_id: str,
    operation: str,
    state: str,
    outcome: str,
    reason: str,
) -> None:
    _log(
        "worker_decision",
        {
            "trace_id": trace_id,
            "entity_id": entity_id,
            "operation": operation,
            "state": state,
            "outcome": outcome,
            "reason": reason,
        },
    )


def log_error(
    *,
    trace_id: str,
    entity_id: str,
    operation: str,
    error_class: ErrorClass,
    severity: Severity,
    retriable: bool,
    error: str,
) -> None:
    _log(
        "worker_error",
        {
            "trace_id": trace_id,
            "entity_id": entity_id,
            "operation": operation,
            "error_class": error_class.value,
            "severity": severity.value,
            "retriable": retriable,
            "error": error,
        },
    )


def _derive_idempotency_key(payload: Dict[str, Any]) -> str:
    explicit = str(payload.get("idempotency_key") or "").strip()
    if explicit:
        return explicit
    trace_id = str(payload.get("trace_id") or "").strip()
    entity_id = str(payload.get("entity_id") or "unknown")
    operation = str(payload.get("operation") or "noop")
    return f"{operation}:{entity_id}:{trace_id}"


def _classify_exception(exc: Exception) -> Tuple[ErrorClass, Severity, bool]:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return ErrorClass.TRANSIENT, Severity.WARNING, True
    if isinstance(exc, ValueError):
        return ErrorClass.POLICY_VIOLATION, Severity.ERROR, False
    return ErrorClass.PERMANENT, Severity.ERROR, False


def _domain_logic(payload: Dict[str, Any], *, dry_run: bool, idempotency_key: str) -> Dict[str, str]:
    """
    Safe extension point: replace internals with worker-specific domain logic.
    Must not call commit here. Commit is owned by worker boundary.
    """
    operation = str(payload.get("operation") or "noop")
    entity_id = str(payload.get("entity_id") or "unknown")
    state = str(payload.get("state") or "new")

    simulate_error = str(payload.get("simulate_error") or "").lower()
    if simulate_error == "transient":
        raise ConnectionError("simulated transient failure")
    if simulate_error == "policy":
        raise ValueError("simulated policy violation")
    if simulate_error == "permanent":
        raise RuntimeError("simulated permanent failure")

    side_effect_ref = f"{operation}:{entity_id}:{idempotency_key}"
    outcome = "skipped" if dry_run else "executed"
    reason = "dry_run" if dry_run else f"side_effect_ref={side_effect_ref}"
    return {"operation": operation, "entity_id": entity_id, "state": state, "outcome": outcome, "reason": reason}


def run_worker(conn: Any, payload: Dict[str, Any], *, dry_run: bool = False) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")

    trace_id = str(payload.get("trace_id") or "").strip()
    if not trace_id:
        raise ValueError("trace_id is required")

    idempotency_key = _derive_idempotency_key(payload)
    entity_id = str(payload.get("entity_id") or "unknown")
    operation = str(payload.get("operation") or "noop")

    try:
        result = _domain_logic(payload, dry_run=dry_run, idempotency_key=idempotency_key)
        log_decision(
            trace_id=trace_id,
            entity_id=result["entity_id"],
            operation=result["operation"],
            state=result["state"],
            outcome=result["outcome"],
            reason=result["reason"],
        )
        if not dry_run and conn is not None:
            # Boundary commit rule: commit only at worker boundary.
            conn.commit()
        return {
            "status": "ok",
            "trace_id": trace_id,
            "entity_id": result["entity_id"],
            "operation": result["operation"],
            "outcome": result["outcome"],
            "idempotency_key": idempotency_key,
        }
    except Exception as exc:
        error_class, severity, retriable = _classify_exception(exc)
        log_error(
            trace_id=trace_id,
            entity_id=entity_id,
            operation=operation,
            error_class=error_class,
            severity=severity,
            retriable=retriable,
            error=str(exc),
        )
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Canonical Tier-3 worker template")
    parser.add_argument("--trace-id", required=True, help="Trace identifier for end-to-end correlation")
    parser.add_argument("--dry-run", action="store_true", help="Skip external side-effects and commit")
    parser.add_argument("--payload", default="{}", help="JSON object payload")
    args = parser.parse_args(argv)

    try:
        input_payload = json.loads(args.payload)
        if not isinstance(input_payload, dict):
            raise ValueError("--payload must be a JSON object")
        trace_id = str(args.trace_id).strip()
        if not trace_id:
            raise ValueError("--trace-id must be non-empty")
        input_payload["trace_id"] = trace_id
        output = run_worker(conn=None, payload=input_payload, dry_run=args.dry_run)
        print(json.dumps({"status": "ok", "result": output}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

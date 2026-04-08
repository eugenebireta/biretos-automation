"""
experience_writer.py — write trace-linked execution experience to shadow_log.

Closes the learning loop: every orchestrator run gets a record with:
  trace_id, task_id, acceptance verdict, audit verdict (if any),
  changed_files, elapsed time, risk class, drift detection.

Records are appended to shadow_log/experience_YYYY-MM.jsonl.

DNA compliance:
- trace_id: required field, never null
- idempotency_key: trace_id (one record per trace)
- no DB side-effects, no imports from domain.reconciliation_*
- structured logging: error_class, severity, retriable
- fail-loud: raises on missing trace_id
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
SHADOW_LOG_DIR = ROOT / "shadow_log"

SCHEMA_VERSION = "execution_experience_v1"


def _log_path() -> Path:
    """Return path for current month's experience log."""
    now = datetime.now(timezone.utc)
    return SHADOW_LOG_DIR / f"experience_{now.strftime('%Y-%m')}.jsonl"


def write_execution_experience(
    trace_id: str,
    task_id: str,
    risk_class: str,
    acceptance_passed: bool,
    acceptance_checks: list[dict],
    drift_detected: bool,
    changed_files: list[str],
    elapsed_seconds: float,
    executor_status: str,
    gate_passed: bool,
    gate_rule: str,
    audit_verdict: Optional[str] = None,
    audit_run_id: Optional[str] = None,
    out_of_scope_files: Optional[list[str]] = None,
    correction_needed: bool = False,
    correction_detail: Optional[str] = None,
) -> dict:
    """Write a single execution experience record.

    Args:
        trace_id: Orchestrator trace ID (required, never null).
        task_id: Task identifier from manifest.
        risk_class: LOW/SEMI/CORE from classifier.
        acceptance_passed: Whether acceptance checker passed.
        acceptance_checks: List of {check_id, passed, detail} dicts.
        drift_detected: Whether executor touched out-of-scope files.
        changed_files: List of files changed by executor.
        elapsed_seconds: Execution time.
        executor_status: Status from ExecutorResult (completed/failed/timeout).
        gate_passed: Whether batch quality gate passed.
        gate_rule: Which gate rule was applied (G1..G6).
        audit_verdict: Optional auditor verdict (PASS/FAIL/None).
        audit_run_id: Optional auditor run ID.
        out_of_scope_files: Files that were outside directive scope.
        correction_needed: Whether a corrective re-run is needed.
        correction_detail: Why correction is needed.

    Returns:
        The record dict that was written.

    Raises:
        ValueError: If trace_id is empty or None.
    """
    if not trace_id:
        raise ValueError("trace_id is required for experience records (cannot be null)")

    now = datetime.now(timezone.utc)

    # Determine overall verdict
    if executor_status != "completed":
        overall_verdict = "EXECUTOR_FAILED"
    elif not gate_passed:
        overall_verdict = "GATE_FAILED"
    elif not acceptance_passed:
        overall_verdict = "ACCEPTANCE_FAILED"
    elif audit_verdict == "FAIL":
        overall_verdict = "AUDIT_FAILED"
    else:
        overall_verdict = "PASS"

    record = {
        "schema_version": SCHEMA_VERSION,
        "ts": now.isoformat(),
        "trace_id": trace_id,
        "task_id": task_id,
        "risk_class": risk_class,
        "overall_verdict": overall_verdict,
        "executor_status": executor_status,
        "elapsed_seconds": round(elapsed_seconds, 1),
        "gate_passed": gate_passed,
        "gate_rule": gate_rule,
        "acceptance_passed": acceptance_passed,
        "acceptance_checks": acceptance_checks,
        "drift_detected": drift_detected,
        "out_of_scope_files": out_of_scope_files or [],
        "changed_files_count": len(changed_files),
        "changed_files": changed_files[:20],  # cap at 20 for readability
        "audit_verdict": audit_verdict,
        "audit_run_id": audit_run_id,
        "correction_needed": correction_needed,
        "correction_detail": correction_detail,
        "idempotency_key": f"exec_exp_{trace_id}",
    }

    # Append to log file
    log_path = _log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Idempotency: check if trace_id already recorded
    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        if f'"trace_id": "{trace_id}"' in existing:
            # Already recorded — skip duplicate
            return record

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def write_failure_experience(
    trace_id: str,
    task_id: str,
    risk_class: str,
    failure_reason: str,
    failure_stage: str,
    elapsed_seconds: float = 0.0,
) -> dict:
    """Write a minimal experience record for early failures (before packet exists).

    Used when executor fails, collect fails, or advisor escalates.
    """
    if not trace_id:
        raise ValueError("trace_id is required for experience records (cannot be null)")

    now = datetime.now(timezone.utc)

    record = {
        "schema_version": SCHEMA_VERSION,
        "ts": now.isoformat(),
        "trace_id": trace_id,
        "task_id": task_id,
        "risk_class": risk_class,
        "overall_verdict": "EARLY_FAILURE",
        "executor_status": "not_reached" if failure_stage != "executor" else "failed",
        "elapsed_seconds": round(elapsed_seconds, 1),
        "gate_passed": False,
        "gate_rule": "N/A",
        "acceptance_passed": False,
        "acceptance_checks": [],
        "drift_detected": False,
        "out_of_scope_files": [],
        "changed_files_count": 0,
        "changed_files": [],
        "audit_verdict": None,
        "audit_run_id": None,
        "correction_needed": False,
        "correction_detail": None,
        "failure_reason": failure_reason,
        "failure_stage": failure_stage,
        "idempotency_key": f"exec_exp_{trace_id}",
    }

    log_path = _log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        if f'"trace_id": "{trace_id}"' in existing:
            return record

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record

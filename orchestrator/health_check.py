"""
health_check.py — Read-only diagnostic module for the Meta Orchestrator.

Checks orchestrator health: manifest validity, config loadability,
auditor keys presence, queue readability.

Returns dict: {healthy: bool, checks: list[dict]}

Each check: {name: str, ok: bool, detail: str}

Usage:
    from orchestrator.health_check import run_health_check
    result = run_health_check(trace_id="...", idempotency_key="...")
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ORCH_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = ORCH_DIR / "manifest.json"
QUEUE_PATH = ORCH_DIR / "task_queue.json"

# Required manifest keys for schema_version v1
REQUIRED_MANIFEST_KEYS = {"schema_version", "fsm_state", "current_task_id", "trace_id"}

# Auditor API keys checked in environment
AUDITOR_ENV_KEYS = ["GEMINI_API_KEY", "ANTHROPIC_API_KEY"]


def _check_manifest_valid() -> dict[str, Any]:
    """Check that manifest.json exists and is valid JSON with required keys."""
    name = "manifest_valid"
    try:
        text = MANIFEST_PATH.read_text(encoding="utf-8")
        data = json.loads(text)
        missing = REQUIRED_MANIFEST_KEYS - set(data.keys())
        if missing:
            return {"name": name, "ok": False, "detail": f"Missing keys: {sorted(missing)}"}
        return {"name": name, "ok": True, "detail": "OK"}
    except FileNotFoundError:
        return {"name": name, "ok": False, "detail": "manifest.json not found"}
    except json.JSONDecodeError as e:
        return {"name": name, "ok": False, "detail": f"Invalid JSON: {e}"}


def _check_config_loadable() -> dict[str, Any]:
    """Check that the schemas module can be imported and has expected schemas."""
    name = "config_loadable"
    try:
        from orchestrator.schemas import SCHEMA_FILES
        if not SCHEMA_FILES:
            return {"name": name, "ok": False, "detail": "SCHEMA_FILES is empty"}
        return {"name": name, "ok": True, "detail": f"{len(SCHEMA_FILES)} schemas available"}
    except Exception as e:
        return {"name": name, "ok": False, "detail": f"Import failed: {e}"}


def _check_auditor_keys_present() -> dict[str, Any]:
    """Check that required auditor API keys are set in environment."""
    name = "auditor_keys_present"
    missing = [k for k in AUDITOR_ENV_KEYS if not os.environ.get(k)]
    if missing:
        return {"name": name, "ok": False, "detail": f"Missing env vars: {missing}"}
    return {"name": name, "ok": True, "detail": "All auditor keys present"}


def _check_queue_readable() -> dict[str, Any]:
    """Check that task_queue.json exists and is valid JSON (or absent = empty queue)."""
    name = "queue_readable"
    if not QUEUE_PATH.exists():
        return {"name": name, "ok": True, "detail": "No queue file (empty queue)"}
    try:
        text = QUEUE_PATH.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, list):
            return {"name": name, "ok": False, "detail": "Queue is not a JSON array"}
        return {"name": name, "ok": True, "detail": f"{len(data)} tasks in queue"}
    except json.JSONDecodeError as e:
        return {"name": name, "ok": False, "detail": f"Invalid JSON: {e}"}


ALL_CHECKS = [
    _check_manifest_valid,
    _check_config_loadable,
    _check_auditor_keys_present,
    _check_queue_readable,
]


def run_health_check(
    *,
    trace_id: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Run all health checks and return aggregate result.

    Args:
        trace_id: Required trace ID for structured logging.
        idempotency_key: Optional idempotency key.

    Returns:
        {"healthy": bool, "checks": list[dict]}
    """
    checks = []
    for check_fn in ALL_CHECKS:
        result = check_fn()
        checks.append(result)

    healthy = all(c["ok"] for c in checks)

    logger.info(
        "health_check complete",
        extra={
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
            "healthy": healthy,
            "check_count": len(checks),
            "failed": [c["name"] for c in checks if not c["ok"]],
        },
    )

    return {"healthy": healthy, "checks": checks}

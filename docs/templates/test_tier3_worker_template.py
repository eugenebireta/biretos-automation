from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
from typing import Any, Dict, List

_TEMPLATE_PATH = Path(__file__).resolve().parent / "tier3_worker_template.py"
_SPEC = importlib.util.spec_from_file_location("tier3_worker_template", _TEMPLATE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Failed to load tier3_worker_template module")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

run_worker = _MODULE.run_worker


class MockConn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def _capture_logs(func: Any, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        func(*args, **kwargs)
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines if line.strip().startswith("{")]


def test_happy_path() -> None:
    conn = MockConn()
    payload = {
        "trace_id": "trace-001",
        "entity_id": "order-100",
        "operation": "ship_paid",
        "state": "ready",
        "idempotency_key": "ship_paid:order-100:trace-001",
    }
    logs = _capture_logs(run_worker, conn, payload, dry_run=False)

    assert conn.commits == 1
    decision = [entry for entry in logs if entry.get("event") == "worker_decision"]
    assert len(decision) == 1
    assert decision[0]["trace_id"] == "trace-001"
    assert decision[0]["entity_id"] == "order-100"
    assert decision[0]["operation"] == "ship_paid"
    assert decision[0]["state"] == "ready"
    assert decision[0]["outcome"] == "executed"
    assert "reason" in decision[0]


def test_error_path() -> None:
    conn = MockConn()
    payload = {
        "trace_id": "trace-002",
        "entity_id": "order-200",
        "operation": "ship_paid",
        "state": "ready",
        "simulate_error": "transient",
    }

    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        try:
            run_worker(conn, payload, dry_run=False)
            raise AssertionError("Expected ConnectionError was not raised")
        except ConnectionError:
            pass
    entries = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip().startswith("{")]
    errors = [entry for entry in entries if entry.get("event") == "worker_error"]
    assert len(errors) == 1
    assert errors[0]["error_class"] == "TRANSIENT"
    assert errors[0]["severity"] == "WARNING"
    assert errors[0]["retriable"] is True
    assert errors[0]["trace_id"] == "trace-002"
    assert conn.commits == 0


def test_dry_run() -> None:
    conn = MockConn()
    payload = {
        "trace_id": "trace-003",
        "entity_id": "order-300",
        "operation": "ship_paid",
        "state": "ready",
    }
    logs = _capture_logs(run_worker, conn, payload, dry_run=True)

    assert conn.commits == 0
    decision = [entry for entry in logs if entry.get("event") == "worker_decision"]
    assert len(decision) == 1
    assert decision[0]["outcome"] == "skipped"

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_TEMPLATE_PATH = Path(__file__).resolve().parent / "tier3_worker_template.py"
_SPEC = importlib.util.spec_from_file_location("tier3_worker_template", _TEMPLATE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Failed to load tier3_worker_template module")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

run_worker = _MODULE.run_worker
log_decision = _MODULE.log_decision
log_error = _MODULE.log_error
main = _MODULE.main
ErrorClass = _MODULE.ErrorClass
Severity = _MODULE.Severity


class MockConn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def _capture_call(
    func: Any, *args: Any, **kwargs: Any
) -> Tuple[Optional[Any], Optional[BaseException], str, str]:
    out_stream = io.StringIO()
    err_stream = io.StringIO()
    result: Optional[Any] = None
    captured_exc: Optional[BaseException] = None
    with contextlib.redirect_stdout(out_stream), contextlib.redirect_stderr(err_stream):
        try:
            result = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001
            captured_exc = exc
    return result, captured_exc, out_stream.getvalue(), err_stream.getvalue()


def _json_lines(text: str) -> List[Dict[str, Any]]:
    lines = [line for line in text.splitlines() if line.strip()]
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
    result, exc, stdout_text, _ = _capture_call(run_worker, conn, payload, dry_run=False)
    assert exc is None
    assert result is not None
    logs = _json_lines(stdout_text)

    assert conn.commits == 1
    assert result["status"] == "ok"
    assert result["idempotency_key"] == "ship_paid:order-100:trace-001"
    decision = [entry for entry in logs if entry.get("event") == "worker_decision"]
    assert len(decision) == 1
    required_keys = {"event", "ts", "trace_id", "entity_id", "operation", "state", "outcome", "reason"}
    assert required_keys.issubset(set(decision[0].keys()))
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
    result, exc, stdout_text, _ = _capture_call(run_worker, conn, payload, dry_run=False)
    assert result is None
    assert isinstance(exc, ConnectionError)
    entries = _json_lines(stdout_text)
    errors = [entry for entry in entries if entry.get("event") == "worker_error"]
    assert len(errors) == 1
    required_keys = {
        "event",
        "ts",
        "trace_id",
        "entity_id",
        "operation",
        "error_class",
        "severity",
        "retriable",
        "error",
    }
    assert required_keys.issubset(set(errors[0].keys()))
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
    result, exc, stdout_text, _ = _capture_call(run_worker, conn, payload, dry_run=True)
    assert exc is None
    assert result is not None
    logs = _json_lines(stdout_text)

    assert conn.commits == 0
    decision = [entry for entry in logs if entry.get("event") == "worker_decision"]
    assert len(decision) == 1
    assert decision[0]["outcome"] == "skipped"


def test_error_taxonomy_enums() -> None:
    assert ErrorClass.TRANSIENT.value == "TRANSIENT"
    assert ErrorClass.PERMANENT.value == "PERMANENT"
    assert ErrorClass.POLICY_VIOLATION.value == "POLICY_VIOLATION"
    assert Severity.WARNING.value == "WARNING"
    assert Severity.ERROR.value == "ERROR"


def test_log_helpers_schema() -> None:
    _, exc1, out1, _ = _capture_call(
        log_decision,
        trace_id="trace-010",
        entity_id="entity-1",
        operation="sync",
        state="ready",
        outcome="executed",
        reason="unit_test",
    )
    assert exc1 is None
    d = _json_lines(out1)[0]
    assert d["event"] == "worker_decision"
    assert d["trace_id"] == "trace-010"
    assert d["outcome"] == "executed"

    _, exc2, out2, _ = _capture_call(
        log_error,
        trace_id="trace-011",
        entity_id="entity-2",
        operation="sync",
        error_class=ErrorClass.PERMANENT,
        severity=Severity.ERROR,
        retriable=False,
        error="unit_test_error",
    )
    assert exc2 is None
    e = _json_lines(out2)[0]
    assert e["event"] == "worker_error"
    assert e["error_class"] == "PERMANENT"
    assert e["severity"] == "ERROR"
    assert e["retriable"] is False


def test_cli_missing_trace_id() -> None:
    result, exc, _, stderr_text = _capture_call(main, [])
    assert result is None
    assert isinstance(exc, SystemExit)
    assert getattr(exc, "code", None) == 2
    assert "--trace-id" in stderr_text


def test_cli_invalid_trace_id() -> None:
    result, exc, _, stderr_text = _capture_call(main, ["--trace-id", "   ", "--payload", "{}"])
    assert exc is None
    assert result == 1
    assert "trace-id" in stderr_text


def test_cli_invalid_payload_type() -> None:
    result, exc, _, stderr_text = _capture_call(main, ["--trace-id", "trace-020", "--payload", "[]"])
    assert exc is None
    assert result == 1
    assert "JSON object" in stderr_text

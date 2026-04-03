from __future__ import annotations

import asyncio
from contextlib import redirect_stdout
import importlib.util
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List
from uuid import UUID

from starlette.requests import Request


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_paths() -> None:
    root = _root()
    webhook_dir = root / "webhook_service"
    for path in (str(root), str(webhook_dir)):
        if path not in sys.path:
            sys.path.insert(0, path)


@dataclass
class _ConfigStub:
    telegram_webhook_secret: str = "telegram-secret"
    tbank_api_token: str = "tbank-secret"
    telegram_bot_token: str = "bot-token"
    tbank_api_base: str = "https://tbank.example"
    cdek_client_id: str = "cdek-client-id"
    cdek_client_secret: str = "cdek-client-secret"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "biretos_automation"
    postgres_user: str = "biretos_user"
    postgres_password: str = "test"
    ru_worker_poll_interval: int = 1
    llm_enabled_default: bool = False

    def __getattr__(self, _: str) -> Any:
        return None


def _import_webhook_main_isolated(config_stub: _ConfigStub) -> ModuleType:
    _ensure_paths()

    import config as config_pkg

    original_get_config = config_pkg.get_config
    config_pkg.get_config = lambda: config_stub
    try:
        module_name = "_synthetic_webhook_runtime"
        sys.modules.pop(module_name, None)
        module_path = _root() / "webhook_service" / "main.py"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to import webhook_service/main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        config_pkg.get_config = original_get_config


def _build_request(path: str, headers: Dict[str, str], body: bytes) -> Request:
    sent = False

    async def receive() -> Dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    raw_headers = [(key.lower().encode("utf-8"), value.encode("utf-8")) for key, value in headers.items()]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8001),
    }
    return Request(scope, receive)


class SyntheticConn:
    def __init__(self) -> None:
        self.rollback_count = 0
        self.commit_count = 0

    def rollback(self) -> None:
        self.rollback_count += 1

    def commit(self) -> None:
        self.commit_count += 1


class SyntheticJobStore:
    def __init__(self) -> None:
        self.jobs_by_idempotency: Dict[str, Dict[str, Any]] = {}
        self.duplicate_hits = 0
        self.last_insert: Dict[str, Any] | None = None
        self.fail_next_insert: str | None = None
        self._uuid_counter = 1

    def next_uuid(self) -> UUID:
        value = UUID(int=self._uuid_counter)
        self._uuid_counter += 1
        return value

    def insert_job_with_idempotency(
        self,
        conn: SyntheticConn,
        job_type: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        trace_id: str,
    ) -> Dict[str, Any]:
        if self.fail_next_insert:
            message = self.fail_next_insert
            self.fail_next_insert = None
            raise RuntimeError(message)

        existing = self.jobs_by_idempotency.get(idempotency_key)
        if existing is not None:
            self.duplicate_hits += 1
            self.last_insert = {
                "created": False,
                "job_type": existing["job_type"],
                "job_id": existing["job_id"],
                "status": existing["status"],
                "trace_id": existing["trace_id"],
                "idempotency_key": idempotency_key,
                "payload": existing["payload"],
            }
            return {
                "created": False,
                "job_id": existing["job_id"],
                "status": existing["status"],
                "trace_id": existing["trace_id"],
            }

        job_id = str(self.next_uuid())
        stored = {
            "job_type": job_type,
            "job_id": job_id,
            "status": "pending",
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
            "payload": json.loads(json.dumps(payload, ensure_ascii=False)),
        }
        self.jobs_by_idempotency[idempotency_key] = stored
        self.last_insert = {
            "created": True,
            **stored,
        }
        conn.commit()
        return {
            "created": True,
            "job_id": job_id,
            "status": "pending",
            "trace_id": trace_id,
        }


def _normalize_dynamic_ids(value: Any, *, placeholder: str) -> Any:
    if value is None:
        return None
    return placeholder


def _normalize_insert(insert: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if insert is None:
        return None
    normalized = {
        "created": insert["created"],
        "job_type": insert["job_type"],
        "job_id": _normalize_dynamic_ids(insert.get("job_id"), placeholder="<job_id>"),
        "status": insert.get("status"),
        "trace_id": _normalize_dynamic_ids(insert.get("trace_id"), placeholder="<trace_id>"),
        "idempotency_key": insert["idempotency_key"],
        "payload": insert["payload"],
    }
    return normalized


def _normalize_log_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key in ("event", "error_type", "message", "invoice_id", "external_id", "idempotency_key"):
        if key in entry:
            normalized[key] = entry[key]
    context = entry.get("context")
    if isinstance(context, dict) and context:
        normalized["context"] = context
    return normalized


def _normalize_logs(stdout_value: str) -> List[Dict[str, Any]]:
    logs: List[Dict[str, Any]] = []
    for line in stdout_value.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except Exception:
            continue
        logs.append(_normalize_log_entry(parsed))
    return logs


def _normalize_response(response) -> Dict[str, Any]:
    body = json.loads(response.body.decode("utf-8"))
    if "trace_id" in body:
        body["trace_id"] = "<trace_id>"
    return {
        "status_code": response.status_code,
        "body": body,
    }


def _compare_subset(expected: Any, actual: Any, path: str = "") -> List[str]:
    mismatches: List[str] = []

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or 'root'}: expected dict, got {type(actual).__name__}"]
        for key, expected_value in expected.items():
            key_path = f"{path}.{key}" if path else key
            if key not in actual:
                mismatches.append(f"{key_path}: missing key")
                continue
            mismatches.extend(_compare_subset(expected_value, actual[key], key_path))
        return mismatches

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path or 'root'}: expected list, got {type(actual).__name__}"]
        if len(expected) != len(actual):
            return [f"{path or 'root'}: expected len {len(expected)}, got {len(actual)}"]
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            item_path = f"{path}[{index}]"
            mismatches.extend(_compare_subset(expected_item, actual_item, item_path))
        return mismatches

    if expected != actual:
        return [f"{path or 'root'}: expected {expected!r}, got {actual!r}"]
    return mismatches


class SyntheticWebhookDriver:
    def __init__(self) -> None:
        self.store = SyntheticJobStore()
        self.conn = SyntheticConn()
        self.module = _import_webhook_main_isolated(_ConfigStub())
        self.module.get_db_connection = lambda: self.conn
        self.module.return_db_connection = lambda conn: None
        self.module._insert_job_with_idempotency = self.store.insert_job_with_idempotency
        self.module.uuid4 = self.store.next_uuid

    def run_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        input_spec = step["input"]
        self.store.last_insert = None
        self.store.fail_next_insert = input_spec.get("simulate_insert_error")
        request = self._build_step_request(input_spec)
        handler = self._resolve_handler(input_spec["endpoint"])

        with redirect_stdout(io.StringIO()) as stdout:
            response = asyncio.run(handler(request))

        result = {
            "response": _normalize_response(response),
            "insert": _normalize_insert(self.store.last_insert),
            "logs": _normalize_logs(stdout.getvalue()),
            "side_effects": {
                "jobs_total": len(self.store.jobs_by_idempotency),
                "duplicate_hits": self.store.duplicate_hits,
                "rollbacks": self.conn.rollback_count,
            },
        }
        self.store.fail_next_insert = None
        return result

    def run_scenario(self, scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [self.run_step(step) for step in scenario["steps"]]

    def _build_step_request(self, input_spec: Dict[str, Any]) -> Request:
        headers = dict(input_spec.get("headers") or {})
        if "json" in input_spec:
            headers.setdefault("Content-Type", "application/json")
            body = json.dumps(input_spec["json"], ensure_ascii=False).encode("utf-8")
        else:
            body = str(input_spec.get("body") or "").encode("utf-8")
        return _build_request(
            self._resolve_path(input_spec["endpoint"]),
            headers,
            body,
        )

    def _resolve_handler(self, endpoint: str):
        if endpoint == "tbank_invoice_paid":
            return self.module.tbank_invoice_paid_webhook
        if endpoint == "cdek_shipment_status":
            return self.module.cdek_shipment_status_webhook
        raise ValueError(f"Unsupported endpoint: {endpoint}")

    def _resolve_path(self, endpoint: str) -> str:
        if endpoint == "tbank_invoice_paid":
            return "/webhook/tbank-invoice-paid"
        if endpoint == "cdek_shipment_status":
            return "/webhook/cdek-shipment-status"
        raise ValueError(f"Unsupported endpoint: {endpoint}")


def load_reference_fixture(path: Path | None = None) -> Dict[str, Any]:
    fixture_path = path or (_root() / "tests" / "fixtures" / "synthetic_webhook_reference.json")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def replay_reference_fixture(path: Path | None = None) -> Dict[str, Any]:
    fixture = load_reference_fixture(path)
    mismatches: List[Dict[str, Any]] = []
    total_steps = 0
    matched_steps = 0

    for scenario in fixture["scenarios"]:
        driver = SyntheticWebhookDriver()
        actual_steps = driver.run_scenario(scenario)
        expected_steps = [step["expected"] for step in scenario["steps"]]

        for index, (expected_step, actual_step) in enumerate(zip(expected_steps, actual_steps), start=1):
            total_steps += 1
            problems = _compare_subset(expected_step, actual_step)
            if problems:
                mismatches.append(
                    {
                        "scenario": scenario["name"],
                        "step": index,
                        "problems": problems,
                        "actual": actual_step,
                    }
                )
            else:
                matched_steps += 1

    match_rate = (matched_steps / total_steps) if total_steps else 0.0
    return {
        "schema_version": fixture["schema_version"],
        "scenario_count": len(fixture["scenarios"]),
        "total_steps": total_steps,
        "matched_steps": matched_steps,
        "match_rate": match_rate,
        "mismatches": mismatches,
    }


def replay_reference_fixture_n_times(path: Path | None = None, *, repeat: int = 1) -> Dict[str, Any]:
    if repeat < 1:
        raise ValueError("repeat must be >= 1")

    fixture = load_reference_fixture(path)
    total_steps = 0
    matched_steps = 0
    mismatches: List[Dict[str, Any]] = []

    for run_index in range(1, repeat + 1):
        result = replay_reference_fixture(path)
        total_steps += result["total_steps"]
        matched_steps += result["matched_steps"]
        for mismatch in result["mismatches"]:
            mismatches.append({"run": run_index, **mismatch})

    match_rate = (matched_steps / total_steps) if total_steps else 0.0
    return {
        "schema_version": fixture["schema_version"],
        "repeat": repeat,
        "scenario_count": len(fixture["scenarios"]),
        "synthetic_requests": total_steps,
        "total_steps": total_steps,
        "matched_steps": matched_steps,
        "match_rate": match_rate,
        "mismatches": mismatches,
    }

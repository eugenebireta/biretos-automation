from __future__ import annotations

from contextlib import redirect_stdout
import io
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from uuid import UUID


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_paths() -> None:
    root = _root()
    for path in (str(root), str(root / "ru_worker")):
        if path not in sys.path:
            sys.path.insert(0, path)


def _ensure_env() -> None:
    defaults = {
        "TELEGRAM_BOT_TOKEN": "bot-token",
        "TELEGRAM_WEBHOOK_SECRET": "telegram-secret",
        "TBANK_API_TOKEN": "tbank-token",
        "TBANK_API_BASE": "https://tbank.example",
        "CDEK_CLIENT_ID": "client-id",
        "CDEK_CLIENT_SECRET": "client-secret",
        "POSTGRES_PASSWORD": "postgres-password",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


_ensure_paths()
_ensure_env()

from ru_worker import assistant_router, telegram_router


def _load_worker_runtime():
    module_name = "_synthetic_worker_runtime"
    module = sys.modules.get(module_name)
    if module is not None:
        return module

    root = _root()
    spec = importlib.util.spec_from_file_location(
        module_name,
        root / "ru_worker" / "ru_worker.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load ru_worker runtime module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return module


WORKER_RUNTIME = _load_worker_runtime()
telegram_router.debug_log = lambda *args, **kwargs: None
WORKER_RUNTIME.debug_log = lambda *args, **kwargs: None


class StubPaymentAdapter:
    def get_invoice_status(self, req):
        from domain.ports import InvoiceStatusResponse

        return InvoiceStatusResponse(
            provider_document_id=req.provider_document_id,
            provider_status="paid",
            raw_response={"synthetic": True, "status": "paid"},
        )


class StubShipmentAdapter:
    def get_tracking_status(self, req):
        from domain.ports import ShipmentTrackingStatusResponse

        return ShipmentTrackingStatusResponse(
            carrier_external_id=req.carrier_external_id,
            carrier_status="delivered",
            raw_response={"synthetic": True, "status": "delivered"},
        )

    def get_waybill(self, req):
        from domain.ports import WaybillResponse

        pdf_bytes = b"%PDF-stub"
        return WaybillResponse(
            carrier_external_id=req.carrier_external_id,
            pdf_bytes=pdf_bytes,
            raw_response={"synthetic": True, "size_bytes": len(pdf_bytes)},
        )


class SyntheticCursor:
    def __init__(self, conn: "SyntheticConn") -> None:
        self._conn = conn
        self._last = None
        self._rowcount = 0

    def execute(self, query: str, params=None) -> None:
        self._conn.queries.append((query, params))
        self._last = None
        self._rowcount = 0
        normalized = " ".join(query.lower().split())

        if "insert into nlu_pending_confirmations" in normalized and "returning id" in normalized:
            confirmation_id = self._conn.next_uuid()
            record = {
                "id": confirmation_id,
                "trace_id": str(params[0]),
                "employee_id": str(params[1]),
                "employee_role": str(params[2]),
                "parsed_intent_type": str(params[3]),
                "parsed_entities": json.loads(params[4]),
                "model_version": str(params[5]),
                "prompt_version": str(params[6]),
                "confidence": float(params[7]),
                "status": "pending",
            }
            self._conn.pending_confirmations[confirmation_id] = record
            self._last = (confirmation_id,)
            self._rowcount = 1
            return

        if (
            "update nlu_pending_confirmations" in normalized
            and "set status = 'confirmed'" in normalized
            and "returning" in normalized
        ):
            confirmation_id = str(params[0])
            record = self._conn.pending_confirmations.get(confirmation_id)
            if record and record["status"] == "pending":
                record["status"] = "confirmed"
                self._last = (
                    record["id"],
                    record["trace_id"],
                    record["employee_id"],
                    record["employee_role"],
                    record["parsed_intent_type"],
                    json.dumps(record["parsed_entities"]),
                    record["model_version"],
                    record["prompt_version"],
                    record["confidence"],
                )
                self._rowcount = 1
            return

        if "update nlu_pending_confirmations" in normalized and "set status = 'expired'" in normalized:
            expired = 0
            for record in self._conn.pending_confirmations.values():
                if record["status"] == "pending":
                    record["status"] = "expired"
                    expired += 1
            self._rowcount = expired
            return

        if "insert into shadow_rag_log" in normalized:
            self._conn.shadow_rows.append({"query": normalized, "params": params})
            self._rowcount = 1
            return

        if "insert into nlu_sla_log" in normalized:
            self._conn.sla_rows.append(params)
            self._rowcount = 1
            return

        if "select count(*)" in normalized and "from employee_actions_log" in normalized:
            employee_id = str(params[0])
            intent_type = str(params[1])
            current = sum(
                1
                for row in self._conn.employee_action_rows
                if row["employee_id"] == employee_id and row["intent_type"] == intent_type
            )
            self._last = (current,)
            return

        if "insert into employee_actions_log" in normalized and "returning id" in normalized:
            idempotency_key = str(params[1])
            if idempotency_key not in self._conn.employee_action_by_idem:
                row_id = self._conn.next_uuid()
                row = {
                    "id": row_id,
                    "trace_id": str(params[0]),
                    "idempotency_key": idempotency_key,
                    "employee_id": str(params[2]),
                    "employee_role": str(params[3]),
                    "intent_type": str(params[4]),
                    "risk_level": str(params[5]),
                }
                self._conn.employee_action_by_idem[idempotency_key] = row
                self._conn.employee_action_rows.append(row)
                self._last = (row_id,)
                self._rowcount = 1
            return

        if "insert into external_read_snapshots" in normalized and "returning id" in normalized:
            trace_id = str(params[0])
            snapshot_key = str(params[1])
            dedupe_key = (trace_id, snapshot_key)
            if dedupe_key not in self._conn.snapshot_by_key:
                row_id = self._conn.next_uuid()
                row = {
                    "id": row_id,
                    "trace_id": trace_id,
                    "snapshot_key": snapshot_key,
                }
                self._conn.snapshot_by_key[dedupe_key] = row
                self._conn.snapshot_rows.append(row)
                self._last = (row_id,)
                self._rowcount = 1
            return

    def fetchone(self):
        return self._last

    def fetchall(self):
        return []

    @property
    def rowcount(self) -> int:
        return self._rowcount

    def close(self) -> None:
        pass


class SyntheticConn:
    def __init__(self) -> None:
        self.queries: List[Any] = []
        self.pending_confirmations: Dict[str, Dict[str, Any]] = {}
        self.shadow_rows: List[Dict[str, Any]] = []
        self.sla_rows: List[Any] = []
        self.employee_action_rows: List[Dict[str, Any]] = []
        self.employee_action_by_idem: Dict[str, Dict[str, Any]] = {}
        self.snapshot_rows: List[Dict[str, Any]] = []
        self.snapshot_by_key: Dict[Any, Dict[str, Any]] = {}
        self.commit_count = 0
        self.rollback_count = 0
        self._uuid_counter = 1

    def cursor(self) -> SyntheticCursor:
        return SyntheticCursor(self)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def next_uuid(self) -> str:
        value = str(UUID(int=self._uuid_counter))
        self._uuid_counter += 1
        return value

    def metrics(self) -> Dict[str, int]:
        return {
            "pending_total": len(self.pending_confirmations),
            "pending_confirmed": sum(
                1 for row in self.pending_confirmations.values() if row["status"] == "confirmed"
            ),
            "shadow_rows": len(self.shadow_rows),
            "sla_rows": len(self.sla_rows),
            "employee_action_rows": len(self.employee_action_rows),
            "snapshot_rows": len(self.snapshot_rows),
        }


def _normalize_callback_data(value: str) -> str:
    if value.startswith("nlu_confirm:"):
        return "nlu_confirm:<confirmation_id>"
    if value.startswith("nlu_cancel:"):
        return "nlu_cancel:<confirmation_id>"
    return value


def _normalize_markup(reply_markup: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if reply_markup is None:
        return None

    normalized = json.loads(json.dumps(reply_markup, ensure_ascii=False))
    for row in normalized.get("inline_keyboard", []):
        for button in row:
            callback_data = button.get("callback_data")
            if callback_data:
                button["callback_data"] = _normalize_callback_data(str(callback_data))
    return normalized


def _normalize_execution(result: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if result is None:
        return None

    normalized: Dict[str, Any] = {"status": result.get("status")}
    for key in (
        "intent_type",
        "provider_document_id",
        "provider_status",
        "carrier_external_id",
        "carrier_status",
        "pdf_size_bytes",
        "error_class",
        "invariant",
        "nlu_confirmed",
    ):
        if key in result:
            normalized[key] = result.get(key)

    entities = result.get("entities")
    if isinstance(entities, dict) and entities:
        normalized["entities"] = dict(entities)

    if result.get("confirmation_id"):
        normalized["confirmation_id"] = "<confirmation_id>"

    return normalized


def _normalize_outbound(text: str | None, reply_markup: Dict[str, Any] | None) -> Dict[str, Any]:
    return {
        "text": text,
        "has_reply_markup": bool(reply_markup),
        "reply_markup": _normalize_markup(reply_markup),
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


class SyntheticTelegramDriver:
    def __init__(self, *, chat_id: int = 999, user_id: int = 999) -> None:
        self.chat_id = chat_id
        self.user_id = user_id
        self.conn = SyntheticConn()
        self.last_confirmation_id: str | None = None
        self._update_counter = 1000
        telegram_router.ALLOWED_USER_IDS = {user_id}

    def run_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        update = self._build_update(step["input"])
        callback_acked = "callback_query" in update and bool(update["callback_query"].get("id"))
        with redirect_stdout(io.StringIO()):
            response_text, action = telegram_router.route_update(update)

        execution_result = None
        outbound_text = response_text
        outbound_markup = None

        if action is not None:
            with redirect_stdout(io.StringIO()):
                execution_result = self._execute_action(action)
            outbound_text, outbound_markup = WORKER_RUNTIME.format_action_result(action, execution_result)
            confirmation_id = execution_result.get("confirmation_id") if execution_result else None
            if confirmation_id:
                self.last_confirmation_id = str(confirmation_id)

        return {
            "callback_acked": callback_acked,
            "route": {
                "action_type": action.get("action_type") if action else None,
                "response_text": response_text,
            },
            "execution": _normalize_execution(execution_result),
            "outbound": _normalize_outbound(outbound_text, outbound_markup),
            "side_effects": self.conn.metrics(),
        }

    def run_scenario(self, scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [self.run_step(step) for step in scenario["steps"]]

    def _build_update(self, input_spec: Dict[str, Any]) -> Dict[str, Any]:
        self._update_counter += 1
        update_id = self._update_counter
        kind = input_spec["type"]

        if kind == "message":
            return {
                "update_id": update_id,
                "message": {
                    "message_id": update_id,
                    "from": {"id": self.user_id, "is_bot": False, "first_name": "Synthetic"},
                    "chat": {"id": self.chat_id, "type": "private"},
                    "text": input_spec["text"],
                    "date": 1_700_000_000 + update_id,
                },
            }

        if kind == "callback":
            callback_data = input_spec["data"]
            if "{last_confirmation_id}" in callback_data:
                if not self.last_confirmation_id:
                    raise RuntimeError("callback step requested last_confirmation_id before parse step")
                callback_data = callback_data.replace("{last_confirmation_id}", self.last_confirmation_id)
            return {
                "update_id": update_id,
                "callback_query": {
                    "id": f"cb-{update_id}",
                    "from": {"id": self.user_id, "is_bot": False, "first_name": "Synthetic"},
                    "message": {
                        "message_id": update_id,
                        "chat": {"id": self.chat_id, "type": "private"},
                        "date": 1_700_000_000 + update_id,
                    },
                    "data": callback_data,
                },
            }

        raise ValueError(f"Unsupported synthetic input type: {kind}")

    def _execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        action_type = action.get("action_type")
        metadata = action.get("metadata", {})
        payload = action.get("payload", {})

        if action_type == "nlu_parse":
            return assistant_router.route_assistant_intent(
                {
                    "trace_id": metadata.get("trace_id"),
                    "employee_id": str(metadata.get("employee_id") or metadata.get("user_id") or self.user_id),
                    "employee_role": str(metadata.get("employee_role") or "operator"),
                    "text": payload.get("text") or "",
                },
                self.conn,
            )

        if action_type == "nlu_confirm":
            return assistant_router.confirm_nlu_intent(
                {
                    "trace_id": metadata.get("trace_id"),
                    "confirmation_id": payload.get("confirmation_id") or "",
                    "employee_id": str(metadata.get("employee_id") or metadata.get("user_id") or self.user_id),
                    "employee_role": str(metadata.get("employee_role") or "operator"),
                },
                self.conn,
                payment_adapter=StubPaymentAdapter(),
                shipment_adapter=StubShipmentAdapter(),
            )

        if action_type == "__nlu_cancel_ack__":
            return {"status": "cancelled"}

        raise NotImplementedError(f"Synthetic driver does not support action_type={action_type}")


def load_reference_fixture(path: Path | None = None) -> Dict[str, Any]:
    fixture_path = path or (_root() / "tests" / "fixtures" / "synthetic_bot_reference.json")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def replay_reference_fixture(path: Path | None = None) -> Dict[str, Any]:
    fixture = load_reference_fixture(path)
    mismatches: List[Dict[str, Any]] = []
    total_steps = 0
    matched_steps = 0

    for scenario in fixture["scenarios"]:
        driver = SyntheticTelegramDriver()
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

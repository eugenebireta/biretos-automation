"""
Tests for Task 5.2–5.4: CDM validation at 3 boundaries + Guardian checks.

Pure unit tests: no DB, no external API, no live dependencies.
All tests are deterministic.

Boundaries:
  B1 — dispatch_action()          (dispatch_action.py)
  B2 — governance_case_creator()  (governance_case_creator.py)
  B3 — governance_executor._execute_live() (governance_executor.py)

Guardian checks (Task 5.4):
  guard_task_intent()      — action_type whitelist
  guard_action_snapshot()  — external_idempotency_key non-empty
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# sys.path helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_paths() -> None:
    root = _project_root()
    ru_worker_dir = root / "ru_worker"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(ru_worker_dir) not in sys.path:
        sys.path.insert(0, str(ru_worker_dir))


_ensure_import_paths()


# ---------------------------------------------------------------------------
# Stub helpers shared across tests
# ---------------------------------------------------------------------------

@dataclass
class _CfgStub:
    execution_mode: str = "LIVE"
    action_mode: str = "DRY_RUN"
    gate_chain_version: str = "1"
    max_input_size_bytes: int = 10_000
    max_price_deviation: float = 0.5
    rounding_tolerance: float = 0.01
    expected_tax_rates: str = ""

    def __getattr__(self, _: str) -> Any:
        return None


def _valid_snapshot_dict(*, ext_key: str = "gov_exec:abc-123") -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "leaf_worker_type": "cdek_shipment",
        "leaf_payload": {"order_id": "INV-001"},
        "external_idempotency_key": ext_key,
    }


def _make_conn(*, case_status: Optional[str] = None):
    """Minimal DB connection stub for governance tests."""

    class _Cursor:
        def __init__(self, conn) -> None:
            self._conn = conn
            self._rows: List[Any] = []

        def execute(self, query: str, params=None) -> None:
            params = params or ()
            q = " ".join(query.strip().lower().split())
            if q.startswith("select status from review_cases where id = %s::uuid"):
                self._rows = [(self._conn.case_status,)] if self._conn.case_status else []
            elif q.startswith("select status from action_idempotency_log"):
                self._rows = []
            # INSERT/UPDATE/DELETE: silently accepted

        def fetchone(self):
            return self._rows.pop(0) if self._rows else None

        def close(self) -> None:
            pass

    class _Conn:
        def __init__(self, cs) -> None:
            self.case_status = cs
            self.commits = 0
            self.resolves: List[str] = []

        def cursor(self) -> _Cursor:
            return _Cursor(self)

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            pass

    return _Conn(case_status)


# ===========================================================================
# Task 5.4 — Guardian unit tests (pure, no DB, no external deps)
# ===========================================================================

def _import_guardian():
    _ensure_import_paths()
    return importlib.import_module("domain.guardian")


class TestGuardTaskIntent:
    def test_allowed_action_type_passes(self):
        g = _import_guardian()
        from domain.cdm_models import TaskIntent

        intent = TaskIntent(
            trace_id="trace-001",
            action_type="cdek_shipment",
            payload={"invoice_id": "INV-001"},
            source="test",
        )
        g.guard_task_intent(intent)  # must not raise

    def test_all_allowed_types_pass(self):
        g = _import_guardian()
        from domain.cdm_models import TaskIntent

        for action_type in g.ALLOWED_ACTION_TYPES:
            intent = TaskIntent(
                trace_id="trace-001",
                action_type=action_type,
                payload={},
                source="test",
            )
            g.guard_task_intent(intent)  # must not raise

    def test_unknown_action_type_raises_veto(self):
        g = _import_guardian()
        from domain.cdm_models import TaskIntent

        intent = TaskIntent(
            trace_id="trace-001",
            action_type="delete_everything",
            payload={},
            source="test",
        )
        with pytest.raises(g.GuardianVeto) as exc_info:
            g.guard_task_intent(intent)

        assert exc_info.value.invariant == "INV-ACTION-WHITELIST"
        assert "delete_everything" in exc_info.value.reason

    def test_veto_is_permanent_non_retriable(self):
        g = _import_guardian()
        from domain.cdm_models import TaskIntent

        intent = TaskIntent(
            trace_id="trace-001",
            action_type="drop_table_users",
            payload={},
            source="test",
        )
        with pytest.raises(g.GuardianVeto) as exc_info:
            g.guard_task_intent(intent)

        veto = exc_info.value
        assert isinstance(veto, Exception)
        assert veto.invariant  # non-empty


class TestGuardActionSnapshot:
    def test_valid_snapshot_passes(self):
        g = _import_guardian()
        from domain.cdm_models import ActionSnapshot

        snapshot = ActionSnapshot.model_validate(_valid_snapshot_dict())
        g.guard_action_snapshot(snapshot)  # must not raise

    def test_empty_external_idempotency_key_raises_veto(self):
        g = _import_guardian()
        from domain.cdm_models import ActionSnapshot

        snapshot = ActionSnapshot.model_validate(
            _valid_snapshot_dict(ext_key="")
        )
        with pytest.raises(g.GuardianVeto) as exc_info:
            g.guard_action_snapshot(snapshot)

        assert exc_info.value.invariant == "INV-IDEM"

    def test_supported_leaf_worker_passes(self):
        g = _import_guardian()
        from domain.cdm_models import ActionSnapshot

        snapshot = ActionSnapshot.model_validate(
            _valid_snapshot_dict(ext_key="gov_exec:xyz-789")
        )
        g.guard_action_snapshot(snapshot)  # must not raise


# ===========================================================================
# Task 5.2 / 5.3 — B1: dispatch_action boundary
# ===========================================================================

def _import_dispatch_action(monkeypatch):
    """Import dispatch_action with all heavy deps stubbed out."""
    _ensure_import_paths()

    cfg_stub = _CfgStub()

    # Stub out every module-level import dispatch_action needs
    csg_stub = SimpleNamespace(
        evaluate_commercial_sanity=lambda action, **_kw: SimpleNamespace(
            verdict="APPROVE", reason="ok", details={}
        )
    )
    lib_stub = SimpleNamespace(
        execute_tbank_payment=lambda *a, **k: {},
        execute_tbank_invoice_status=lambda *a, **k: {},
        execute_tbank_invoices_list=lambda *a, **k: {},
        execute_cdek_shipment=lambda *a, **k: {},
        map_tbank_invoice_to_cdek_payload=lambda *a, **k: ({}, None),
        log_event=lambda *a, **k: None,
    )
    idem_stub = SimpleNamespace(
        acquire_action_lock=lambda **k: {"status": "ACQUIRED", "lease_token": "lt"},
        complete_action=lambda **k: True,
        compute_request_hash=lambda *a: "hash",
        generate_idempotency_key=lambda *a: None,
    )
    ph_stub = SimpleNamespace(
        current_policy_context=lambda _cfg: {"policy_hash": "ph", "policy_inputs": {}},
        get_config_snapshot=lambda *a: None,
        parse_expected_tax_rates=lambda *a: {},
        upsert_config_snapshot=lambda *a: None,
    )

    # Patch before first import
    for name, stub in [
        ("config", SimpleNamespace(get_config=lambda: cfg_stub)),
        ("commercial_sanity_gate", csg_stub),
        ("lib_integrations", lib_stub),
        ("idempotency", idem_stub),
        ("policy_hash", ph_stub),
    ]:
        if name not in sys.modules:
            sys.modules[name] = stub  # type: ignore[assignment]

    # Force fresh import if already cached (monkeypatch handles cleanup)
    da_mod = importlib.import_module("dispatch_action")

    # Patch module-level attributes set at import time
    monkeypatch.setattr(da_mod, "_CONFIG", cfg_stub, raising=False)
    monkeypatch.setattr(da_mod, "ACTION_MODE", "DRY_RUN", raising=False)
    monkeypatch.setattr(da_mod, "EXECUTION_MODE", "LIVE", raising=False)

    return da_mod


class TestDispatchActionB1:
    def test_missing_trace_id_is_rejected(self, monkeypatch):
        """Action without trace_id anywhere → error POLICY_VIOLATION."""
        da = _import_dispatch_action(monkeypatch)

        result = da.dispatch_action(
            {
                "action_type": "cdek_shipment",
                "payload": {"invoice_id": "INV-001"},
                "source": "test",
            }
        )

        assert result["status"] == "error"
        assert result["error_class"] == "POLICY_VIOLATION"

    def test_empty_trace_id_is_rejected(self, monkeypatch):
        """Empty trace_id violates min_length=1 → POLICY_VIOLATION."""
        da = _import_dispatch_action(monkeypatch)

        result = da.dispatch_action(
            {
                "trace_id": "",
                "action_type": "cdek_shipment",
                "payload": {"invoice_id": "INV-001"},
                "source": "test",
            }
        )

        assert result["status"] == "error"
        assert result["error_class"] == "POLICY_VIOLATION"

    def test_trace_id_from_kwarg_is_accepted(self, monkeypatch):
        """trace_id supplied as kwarg must be merged in and accepted."""
        da = _import_dispatch_action(monkeypatch)

        result = da.dispatch_action(
            {
                "action_type": "ship_paid",
                "payload": {"invoice_id": "INV-001"},
                "source": "test",
            },
            trace_id=str(uuid4()),
        )

        # Not a POLICY_VIOLATION — validation passed
        assert result.get("error_class") != "POLICY_VIOLATION"

    def test_trace_id_from_metadata_is_accepted(self, monkeypatch):
        """trace_id in metadata must be merged and accepted."""
        da = _import_dispatch_action(monkeypatch)

        result = da.dispatch_action(
            {
                "action_type": "tbank_invoice_status",
                "payload": {"invoice_id": "INV-001"},
                "source": "test",
                "metadata": {"trace_id": str(uuid4())},
            }
        )

        assert result.get("error_class") != "POLICY_VIOLATION"

    def test_unknown_action_type_triggers_guardian_veto(self, monkeypatch):
        """action_type not in ALLOWED_ACTION_TYPES → guardian_veto."""
        da = _import_dispatch_action(monkeypatch)

        result = da.dispatch_action(
            {
                "trace_id": str(uuid4()),
                "action_type": "delete_all_records",
                "payload": {},
                "source": "test",
            }
        )

        assert result["status"] == "error"
        assert result["error"] == "guardian_veto"
        assert result["error_class"] == "POLICY_VIOLATION"

    def test_missing_action_type_is_rejected(self, monkeypatch):
        """Missing action_type → TaskIntent validation failure."""
        da = _import_dispatch_action(monkeypatch)

        result = da.dispatch_action(
            {
                "trace_id": str(uuid4()),
                "payload": {"invoice_id": "INV-001"},
                "source": "test",
                # action_type intentionally omitted
            }
        )

        assert result["status"] == "error"
        assert result["error_class"] == "POLICY_VIOLATION"


# ===========================================================================
# Task 5.2 / 5.3 — B2: governance_case_creator boundary
# ===========================================================================

def _import_governance_case_creator(monkeypatch):
    _ensure_import_paths()

    cfg_stub = _CfgStub()
    sys.modules.setdefault("config", SimpleNamespace(get_config=lambda: cfg_stub))  # type: ignore

    gw_stub = SimpleNamespace(
        create_review_case=lambda db, **kw: {"case_id": str(uuid4()), "created": True}
    )

    mod = importlib.import_module("governance_case_creator")
    monkeypatch.setattr(mod, "governance_workflow", gw_stub, raising=True)
    monkeypatch.setattr(mod, "get_config", lambda: cfg_stub, raising=True)
    return mod


def _valid_creator_payload(**overrides) -> Dict[str, Any]:
    base = {
        "trace_id": str(uuid4()),
        "gate_name": "commercial_sanity",
        "original_decision_seq": 1,
        "policy_hash": "ph-abc",
        "action_snapshot": _valid_snapshot_dict(),
    }
    base.update(overrides)
    return base


class TestGovernanceCaseCreatorB2:
    def test_valid_payload_creates_case(self, monkeypatch):
        gcc = _import_governance_case_creator(monkeypatch)
        conn = _make_conn()

        result = gcc.execute_governance_case_create(
            _valid_creator_payload(), conn, trace_id=str(uuid4())
        )
        assert result["status"] == "success"
        assert "case_id" in result

    def test_invalid_schema_version_raises_value_error(self, monkeypatch):
        gcc = _import_governance_case_creator(monkeypatch)
        conn = _make_conn()

        bad_snapshot = {**_valid_snapshot_dict(), "schema_version": 99}
        with pytest.raises(ValueError, match="schema violation"):
            gcc.execute_governance_case_create(
                _valid_creator_payload(action_snapshot=bad_snapshot),
                conn,
            )

    def test_wrong_leaf_worker_type_raises_value_error(self, monkeypatch):
        gcc = _import_governance_case_creator(monkeypatch)
        conn = _make_conn()

        bad_snapshot = {**_valid_snapshot_dict(), "leaf_worker_type": "evil_worker"}
        with pytest.raises(ValueError, match="schema violation"):
            gcc.execute_governance_case_create(
                _valid_creator_payload(action_snapshot=bad_snapshot),
                conn,
            )

    def test_missing_leaf_payload_raises_value_error(self, monkeypatch):
        gcc = _import_governance_case_creator(monkeypatch)
        conn = _make_conn()

        bad_snapshot = {
            k: v for k, v in _valid_snapshot_dict().items() if k != "leaf_payload"
        }
        with pytest.raises(ValueError, match="schema violation"):
            gcc.execute_governance_case_create(
                _valid_creator_payload(action_snapshot=bad_snapshot),
                conn,
            )

    def test_missing_external_idempotency_key_raises_value_error(self, monkeypatch):
        gcc = _import_governance_case_creator(monkeypatch)
        conn = _make_conn()

        bad_snapshot = {
            k: v
            for k, v in _valid_snapshot_dict().items()
            if k != "external_idempotency_key"
        }
        with pytest.raises(ValueError, match="schema violation"):
            gcc.execute_governance_case_create(
                _valid_creator_payload(action_snapshot=bad_snapshot),
                conn,
            )

    def test_non_dict_snapshot_raises_value_error(self, monkeypatch):
        gcc = _import_governance_case_creator(monkeypatch)
        conn = _make_conn()

        with pytest.raises(ValueError, match="action_snapshot must be a dict"):
            gcc.execute_governance_case_create(
                _valid_creator_payload(action_snapshot="not-a-dict"),
                conn,
            )


# ===========================================================================
# Task 5.2 / 5.3 / 5.4 — B3: governance_executor boundary
# ===========================================================================

def _import_governance_executor():
    _ensure_import_paths()
    return importlib.import_module("governance_executor")


@dataclass
class _GwStub:
    """governance_workflow stub with call tracking."""

    resolves: List[str] = field(default_factory=list)
    marks: int = 0

    def claim_for_execution(self, db, *, case_id: str):
        return {"action_snapshot": _valid_snapshot_dict(ext_key=f"gov:{case_id}"), "trace_id": str(uuid4())}

    def read_case_for_resume(self, *a, **k):
        return None

    def resolve_case(self, db, *, case_id: str, status: str, resolved_by: str):
        self.resolves.append(status)

    def mark_executed(self, db, *, case_id: str):
        self.marks += 1
        return {"updated": True}


class TestGovernanceExecutorB3:
    def test_invalid_snapshot_schema_version_returns_error(self, monkeypatch):
        """ValidationError from Pydantic → invalid_action_snapshot, case cancelled."""
        ge = _import_governance_executor()
        conn = _make_conn()

        gw = SimpleNamespace(
            claim_for_execution=lambda _db, *, case_id: {
                "action_snapshot": {**_valid_snapshot_dict(), "schema_version": 42},
                "trace_id": str(uuid4()),
            },
            read_case_for_resume=lambda *a, **k: None,
            resolve_case=lambda *a, **k: None,
            mark_executed=lambda *a, **k: None,
        )
        monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
        monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(), raising=True)
        monkeypatch.setattr(ge, "log_event", lambda *a, **k: None, raising=True)

        result = ge.execute_governance_case({"case_id": str(uuid4())}, conn)
        assert result["status"] == "error"
        assert result["reason"] == "invalid_action_snapshot"
        # commit 1: after claim_for_execution; commit 2: after resolve_case (cancelled)
        assert conn.commits == 2

    def test_invalid_snapshot_missing_leaf_payload_returns_error(self, monkeypatch):
        ge = _import_governance_executor()
        conn = _make_conn()

        bad = {k: v for k, v in _valid_snapshot_dict().items() if k != "leaf_payload"}
        gw = SimpleNamespace(
            claim_for_execution=lambda _db, *, case_id: {
                "action_snapshot": bad,
                "trace_id": str(uuid4()),
            },
            read_case_for_resume=lambda *a, **k: None,
            resolve_case=lambda *a, **k: None,
            mark_executed=lambda *a, **k: None,
        )
        monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
        monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(), raising=True)
        monkeypatch.setattr(ge, "log_event", lambda *a, **k: None, raising=True)

        result = ge.execute_governance_case({"case_id": str(uuid4())}, conn)
        assert result["status"] == "error"
        assert result["reason"] == "invalid_action_snapshot"

    def test_empty_external_idempotency_key_triggers_guardian_veto(self, monkeypatch):
        """Empty external_idempotency_key passes Pydantic but fails Guardian."""
        ge = _import_governance_executor()
        conn = _make_conn()

        gw = SimpleNamespace(
            claim_for_execution=lambda _db, *, case_id: {
                "action_snapshot": _valid_snapshot_dict(ext_key=""),
                "trace_id": str(uuid4()),
            },
            read_case_for_resume=lambda *a, **k: None,
            resolve_case=lambda *a, **k: None,
            mark_executed=lambda *a, **k: None,
        )
        monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
        monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(), raising=True)
        monkeypatch.setattr(ge, "log_event", lambda *a, **k: None, raising=True)

        result = ge.execute_governance_case({"case_id": str(uuid4())}, conn)
        assert result["status"] == "error"
        assert result["reason"] == "guardian_veto"
        assert result["invariant"] == "INV-IDEM"
        # commit 1: after claim_for_execution; commit 2: after resolve_case (cancelled)
        assert conn.commits == 2

    def test_valid_snapshot_proceeds_to_execution(self, monkeypatch):
        """Valid snapshot passes B3 + Guardian and reaches leaf worker."""
        ge = _import_governance_executor()
        conn = _make_conn()

        calls: Dict[str, int] = {"leaf": 0, "mark": 0}
        ext = str(uuid4())

        gw = SimpleNamespace(
            claim_for_execution=lambda _db, *, case_id: {
                "action_snapshot": _valid_snapshot_dict(ext_key=ext),
                "trace_id": str(uuid4()),
            },
            read_case_for_resume=lambda *a, **k: None,
            resolve_case=lambda *a, **k: None,
            mark_executed=lambda _db, *, case_id: calls.__setitem__("mark", calls["mark"] + 1) or {"updated": True},
        )
        monkeypatch.setattr(ge, "governance_workflow", gw, raising=True)
        monkeypatch.setattr(ge, "get_config", lambda: _CfgStub(), raising=True)
        monkeypatch.setattr(ge, "acquire_action_lock", lambda **k: {"status": "ACQUIRED", "lease_token": "lt"}, raising=True)
        monkeypatch.setattr(ge, "complete_action", lambda **k: True, raising=True)

        def _leaf(_cfg, payload):
            calls["leaf"] += 1
            assert payload["order_id"] == ext
            return {"status": "success"}

        monkeypatch.setattr(ge, "execute_cdek_shipment", _leaf, raising=True)
        monkeypatch.setattr(ge, "log_event", lambda *a, **k: None, raising=True)

        result = ge.execute_governance_case({"case_id": str(uuid4())}, conn)
        assert result["status"] == "success"
        assert calls["leaf"] == 1
        assert calls["mark"] == 1

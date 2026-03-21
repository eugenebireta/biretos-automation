from __future__ import annotations

import importlib
import sys
from pathlib import Path
from uuid import UUID


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_path() -> None:
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


# ---------------------------------------------------------------------------
# Stub DB — handles all SQL from rebuild_stock_snapshot + verify_stock_snapshot
# ---------------------------------------------------------------------------

class _Rc3Cursor:
    def __init__(self, conn: "_Rc3Conn") -> None:
        self._conn = conn
        self._rows: list = []
        self.rowcount = 0

    def execute(self, query: str, params=None) -> None:  # noqa: C901
        params = params or ()
        n = " ".join(query.strip().lower().split())

        # rebuild_stock_snapshot — SELECT ... FOR UPDATE (locked read)
        if (
            n.startswith(
                "select quantity_on_hand, quantity_reserved, quantity_available from availability_snapshot"
            )
            and "for update" in n
        ):
            product_id = str(params[0])
            warehouse_code = str(params[1])
            key = (product_id, warehouse_code)
            snap = self._conn.snapshots.get(key)
            if snap:
                self._rows = [(snap["quantity_on_hand"], snap["quantity_reserved"], snap["quantity_available"])]
            else:
                self._rows = []
            return

        # verify_stock_snapshot — SELECT without FOR UPDATE (read-only)
        if n.startswith(
            "select quantity_on_hand, quantity_reserved, quantity_available from availability_snapshot"
        ):
            product_id = str(params[0])
            warehouse_code = str(params[1])
            key = (product_id, warehouse_code)
            snap = self._conn.snapshots.get(key)
            if snap:
                self._rows = [(snap["quantity_on_hand"], snap["quantity_reserved"], snap["quantity_available"])]
            else:
                self._rows = []
            return

        # SELECT SUM from stock_ledger_entries
        if "select coalesce(sum(quantity_delta), 0) from stock_ledger_entries" in n:
            product_id = str(params[0])
            warehouse_code = str(params[1])
            total = sum(
                e["quantity_delta"]
                for e in self._conn.ledger_entries
                if e["product_id"] == product_id
                and e["warehouse_code"] == warehouse_code
                and e["change_type"] in {"receipt", "return", "adjustment", "sale"}
            )
            self._rows = [(total,)]
            return

        # SELECT SUM from reservations
        if "select coalesce(sum(quantity), 0) from reservations" in n:
            product_id = str(params[0])
            warehouse_code = str(params[1])
            total = sum(
                r["quantity"]
                for r in self._conn.reservations
                if r["product_id"] == product_id
                and r["warehouse_code"] == warehouse_code
                and r["status"] == "active"
            )
            self._rows = [(total,)]
            return

        # UPDATE availability_snapshot
        if n.startswith("update availability_snapshot set quantity_on_hand"):
            qty_on_hand = params[0]
            qty_reserved = params[1]
            qty_available = params[2]
            product_id = str(params[3])
            warehouse_code = str(params[4])
            key = (product_id, warehouse_code)
            if key in self._conn.snapshots:
                self._conn.snapshots[key]["quantity_on_hand"] = qty_on_hand
                self._conn.snapshots[key]["quantity_reserved"] = qty_reserved
                self._conn.snapshots[key]["quantity_available"] = qty_available
            self.rowcount = 1
            self._rows = []
            return

        raise AssertionError(f"Unexpected SQL in _Rc3Cursor: {n!r}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self) -> None:
        pass


class _Rc3Conn:
    def __init__(
        self,
        *,
        product_id: str,
        warehouse_code: str,
        snap_on_hand: int,
        snap_reserved: int,
        snap_available: int,
        ledger_delta: int,
        active_reservations: int,
    ) -> None:
        self.autocommit = False
        self.product_id = product_id
        self.warehouse_code = warehouse_code

        self.snapshots = {
            (product_id, warehouse_code): {
                "quantity_on_hand": snap_on_hand,
                "quantity_reserved": snap_reserved,
                "quantity_available": snap_available,
            }
        }
        # Single ledger entry summing to ledger_delta
        self.ledger_entries = [
            {
                "product_id": product_id,
                "warehouse_code": warehouse_code,
                "quantity_delta": ledger_delta,
                "change_type": "receipt",
            }
        ]
        # Single active reservation summing to active_reservations
        self.reservations = [
            {
                "product_id": product_id,
                "warehouse_code": warehouse_code,
                "quantity": active_reservations,
                "status": "active",
            }
        ]

    def cursor(self) -> _Rc3Cursor:
        return _Rc3Cursor(self)

    def commit(self) -> None:
        pass


# ---------------------------------------------------------------------------
# rebuild_stock_snapshot tests
# ---------------------------------------------------------------------------

def test_rc3_rebuild_corrects_stale_snapshot() -> None:
    """rebuild_stock_snapshot must overwrite snapshot when ledger disagrees."""
    _ensure_path()
    recon = importlib.import_module("domain.reconciliation_service")

    product_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    warehouse_code = "WH-01"

    # Stale snapshot: 50 on hand but ledger says 100
    conn = _Rc3Conn(
        product_id=product_id,
        warehouse_code=warehouse_code,
        snap_on_hand=50,
        snap_reserved=10,
        snap_available=40,
        ledger_delta=100,
        active_reservations=10,
    )

    result = recon.rebuild_stock_snapshot(
        conn,
        product_id=UUID(product_id),
        warehouse_code=warehouse_code,
        trace_id="tr-rc3-rebuild",
    )

    assert result["action"] == "rebuilt"
    snap = conn.snapshots[(product_id, warehouse_code)]
    assert snap["quantity_on_hand"] == 100
    assert snap["quantity_reserved"] == 10
    assert snap["quantity_available"] == 90


def test_rc3_rebuild_returns_correct_values_when_already_synced() -> None:
    """rebuild_stock_snapshot always rebuilds; values match ledger even when snapshot was correct."""
    _ensure_path()
    recon = importlib.import_module("domain.reconciliation_service")

    product_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    warehouse_code = "WH-02"

    conn = _Rc3Conn(
        product_id=product_id,
        warehouse_code=warehouse_code,
        snap_on_hand=200,
        snap_reserved=20,
        snap_available=180,
        ledger_delta=200,
        active_reservations=20,
    )

    result = recon.rebuild_stock_snapshot(
        conn,
        product_id=UUID(product_id),
        warehouse_code=warehouse_code,
        trace_id="tr-rc3-synced",
    )

    assert result["action"] == "rebuilt"
    assert result["quantity_on_hand"] == 200
    assert result["quantity_reserved"] == 20
    assert result["quantity_available"] == 180


# ---------------------------------------------------------------------------
# verify_stock_snapshot tests
# ---------------------------------------------------------------------------

def test_rc3_verify_match_after_rebuild() -> None:
    """verify_stock_snapshot returns MATCH when snapshot is correct."""
    _ensure_path()
    verify = importlib.import_module("domain.reconciliation_verify")

    product_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    warehouse_code = "WH-03"

    conn = _Rc3Conn(
        product_id=product_id,
        warehouse_code=warehouse_code,
        snap_on_hand=75,
        snap_reserved=5,
        snap_available=70,
        ledger_delta=75,
        active_reservations=5,
    )

    result = verify.verify_stock_snapshot(
        conn,
        product_id=UUID(product_id),
        warehouse_code=warehouse_code,
        trace_id="tr-v-rc3",
    )

    assert result["verdict"] == "MATCH"


def test_rc3_verify_divergence_when_snapshot_stale() -> None:
    """verify_stock_snapshot returns DIVERGENCE when snapshot lags ledger."""
    _ensure_path()
    verify = importlib.import_module("domain.reconciliation_verify")

    product_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    warehouse_code = "WH-04"

    conn = _Rc3Conn(
        product_id=product_id,
        warehouse_code=warehouse_code,
        snap_on_hand=30,          # stale
        snap_reserved=5,
        snap_available=25,
        ledger_delta=60,          # actual ledger total
        active_reservations=5,
    )

    result = verify.verify_stock_snapshot(
        conn,
        product_id=UUID(product_id),
        warehouse_code=warehouse_code,
        trace_id="tr-v-rc3-div",
    )

    assert result["verdict"] == "DIVERGENCE"
    assert result["expected"]["quantity_on_hand"] == 60
    assert result["actual"]["quantity_on_hand"] == 30

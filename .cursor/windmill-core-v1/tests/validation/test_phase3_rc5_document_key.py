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
# Stub infrastructure
# ---------------------------------------------------------------------------

class _Rc5Cursor:
    def __init__(self, conn: "_Rc5Conn") -> None:
        self._conn = conn
        self._rows: list = []
        self.rowcount = 0

    def execute(self, query: str, params=None) -> None:
        params = params or ()
        n = " ".join(query.strip().lower().split())

        # reconcile_document_key — SELECT generation_key, revision FROM documents
        if n.startswith("select generation_key, revision from documents"):
            order_id = str(params[0])
            doc = self._conn.documents.get(order_id)
            if doc and doc.get("status") == "issued":
                self._rows = [(doc["generation_key"], doc["revision"])]
            else:
                self._rows = []
            return

        # reconcile_document_key / verify_document_key — SELECT invoice_request_key, revision FROM order_ledger
        if n.startswith("select invoice_request_key, revision from order_ledger"):
            order_id = str(params[0])
            row = self._conn.order_ledger.get(order_id)
            self._rows = [(row["invoice_request_key"], row["revision"])] if row else []
            return

        # reconcile_document_key — UPDATE order_ledger SET invoice_request_key
        if n.startswith("update order_ledger set invoice_request_key"):
            gen_key = params[0]
            revision = params[1]
            order_id = str(params[3])
            if order_id in self._conn.order_ledger:
                self._conn.order_ledger[order_id]["invoice_request_key"] = gen_key
                self._conn.order_ledger[order_id]["revision"] = revision
            self.rowcount = 1
            self._rows = []
            return

        # verify_document_key — SELECT id, generation_key, revision FROM documents
        if n.startswith("select id, generation_key, revision from documents"):
            order_id = str(params[0])
            doc = self._conn.documents.get(order_id)
            if doc and doc.get("status") == "issued":
                self._rows = [(doc["doc_id"], doc["generation_key"], doc["revision"])]
            else:
                self._rows = []
            return

        raise AssertionError(f"Unexpected SQL in _Rc5Cursor: {n!r}")

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self) -> None:
        pass


class _Rc5Conn:
    def __init__(
        self,
        *,
        ledger_key,
        ledger_revision,
        doc_key,
        doc_revision,
        doc_status: str = "issued",
    ) -> None:
        self.autocommit = False
        self.order_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        self.order_ledger = {
            self.order_id: {
                "invoice_request_key": ledger_key,
                "revision": ledger_revision,
            }
        }
        self.documents = {
            self.order_id: {
                "doc_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
                "generation_key": doc_key,
                "revision": doc_revision,
                "document_type": "invoice",
                "status": doc_status,
            }
        }

    def cursor(self) -> _Rc5Cursor:
        return _Rc5Cursor(self)

    def commit(self) -> None:
        pass


# ---------------------------------------------------------------------------
# reconcile_document_key tests
# ---------------------------------------------------------------------------

def test_rc5_reconcile_updates_key_when_stale() -> None:
    _ensure_path()
    recon = importlib.import_module("domain.reconciliation_service")
    conn = _Rc5Conn(
        ledger_key=None, ledger_revision=None,
        doc_key="GK-NEW-001", doc_revision=3,
    )
    order_id = UUID(conn.order_id)

    result = recon.reconcile_document_key(conn, order_id=order_id, trace_id="tr-rc5-a")

    assert result["action"] == "updated"
    assert result["invoice_request_key"] == "GK-NEW-001"
    assert result["revision"] == 3
    assert conn.order_ledger[conn.order_id]["invoice_request_key"] == "GK-NEW-001"


def test_rc5_reconcile_noop_when_already_synced() -> None:
    _ensure_path()
    recon = importlib.import_module("domain.reconciliation_service")
    conn = _Rc5Conn(
        ledger_key="GK-STABLE", ledger_revision=2,
        doc_key="GK-STABLE", doc_revision=2,
    )
    order_id = UUID(conn.order_id)

    result = recon.reconcile_document_key(conn, order_id=order_id, trace_id="tr-rc5-noop")

    assert result["action"] == "noop"
    assert result["invoice_request_key"] == "GK-STABLE"


def test_rc5_reconcile_noop_when_no_issued_invoice() -> None:
    _ensure_path()
    recon = importlib.import_module("domain.reconciliation_service")
    conn = _Rc5Conn(
        ledger_key=None, ledger_revision=None,
        doc_key="GK-DRAFT", doc_revision=1, doc_status="draft",
    )
    order_id = UUID(conn.order_id)

    result = recon.reconcile_document_key(conn, order_id=order_id, trace_id="tr-rc5-no-inv")

    assert result["action"] == "noop"
    assert result["reason"] == "no_issued_invoice"


# ---------------------------------------------------------------------------
# verify_document_key tests
# ---------------------------------------------------------------------------

def test_rc5_verify_match() -> None:
    _ensure_path()
    verify = importlib.import_module("domain.reconciliation_verify")
    conn = _Rc5Conn(
        ledger_key="GK-MATCH", ledger_revision=5,
        doc_key="GK-MATCH", doc_revision=5,
    )

    result = verify.verify_document_key(conn, order_id=UUID(conn.order_id), trace_id="tr-v-rc5")

    assert result["verdict"] == "MATCH"


def test_rc5_verify_divergence_detected() -> None:
    _ensure_path()
    verify = importlib.import_module("domain.reconciliation_verify")
    conn = _Rc5Conn(
        ledger_key="GK-OLD", ledger_revision=1,
        doc_key="GK-NEW", doc_revision=2,
    )

    result = verify.verify_document_key(conn, order_id=UUID(conn.order_id), trace_id="tr-v-rc5-div")

    assert result["verdict"] == "DIVERGENCE"
    assert result["expected"]["invoice_request_key"] == "GK-NEW"
    assert result["actual"]["invoice_request_key"] == "GK-OLD"

"""
Tests for R1 Mass Catalog Pipeline (workers/catalog_worker.py).

Coverage:
  TC-R1-01  Happy path: 3 rows → parsed, synced, job state = done
  TC-R1-02  Parse stage: ONE commit per batch (not per row)
  TC-R1-03  Sync stage:  ONE commit per row
  TC-R1-04  Photo failure does NOT block row sync
  TC-R1-05  Idempotency: second call with same key returns terminal skip
  TC-R1-06  Publisher error marks row as failed; job still reaches done
  TC-R1-07  Parse error advances job to failed
  TC-R1-08  Pydantic validation rejects payload missing trace_id
  TC-R1-09  Pydantic validation rejects empty rows list
  TC-R1-10  Boundary: catalog_worker imports no domain.reconciliation_* modules
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest

# ── sys.path setup ────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[2]  # windmill-core-v1/
_WORKERS = _ROOT / "workers"

for _p in (_ROOT, _WORKERS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

catalog_worker = importlib.import_module("catalog_worker")

run_catalog_pipeline = catalog_worker.run_catalog_pipeline
CatalogRowIn = catalog_worker.CatalogRowIn
CatalogJobPayload = catalog_worker.CatalogJobPayload


# ── Mock DB infrastructure ────────────────────────────────────────────────────


class _MockCursor:
    """
    Minimal psycopg2-cursor stub.

    Tracks every (query, params) pair.  Returns canned responses
    set on _MockConn.  rowcount is always 1 unless overridden.
    """

    def __init__(self, conn: "_MockConn") -> None:
        self._conn = conn
        self._rows: List[Any] = []
        self.rowcount: int = 1

    def execute(self, query: str, params: Any = None) -> None:
        self._conn._queries.append((query, params))
        self._rows = []
        normalized = " ".join(query.strip().lower().split())

        # INSERT into stg_catalog_jobs
        if "insert into stg_catalog_jobs" in normalized:
            self._rows = [(self._conn._job_id, self._conn._job_existing_state)]

        # INSERT into stg_catalog_imports
        elif "insert into stg_catalog_imports" in normalized:
            if not self._conn._skip_row_insert:
                self._rows = [(self._conn._next_row_id(),)]
            else:
                self._rows = []

        # SELECT pending rows
        elif (
            "select" in normalized
            and "stg_catalog_imports" in normalized
            and "sync_status = 'pending'" in normalized
        ):
            self._rows = list(self._conn._pending_rows)

        # UPDATE / other → no rows returned
        else:
            self._rows = []

    def fetchone(self) -> Optional[Any]:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> List[Any]:
        return list(self._rows)

    def close(self) -> None:
        pass


class _MockConn:
    """
    Minimal psycopg2-connection stub.

    Attributes configurable per test:
      _job_id              UUID str returned by INSERT INTO stg_catalog_jobs
      _job_existing_state  job_state returned for idempotency branch
      _skip_row_insert     when True INSERT INTO stg_catalog_imports returns nothing (duplicate)
      _pending_rows        rows returned by SELECT … sync_status='pending'
      _row_counter         auto-incrementing UUID counter for row ids
    """

    def __init__(self) -> None:
        self._queries: List[tuple] = []
        self._commits: int = 0
        self._rollbacks: int = 0

        self._job_id: str = str(uuid4())
        self._job_existing_state: str = "pending"
        self._skip_row_insert: bool = False
        self._pending_rows: List[tuple] = []
        self._row_ids: List[str] = []
        self._row_idx: int = 0

    def _next_row_id(self) -> str:
        if self._row_idx < len(self._row_ids):
            rid = self._row_ids[self._row_idx]
        else:
            rid = str(uuid4())
            self._row_ids.append(rid)
        self._row_idx += 1
        return rid

    def cursor(self) -> _MockCursor:
        return _MockCursor(self)

    def commit(self) -> None:
        self._commits += 1

    def rollback(self) -> None:
        self._rollbacks += 1

    def queries_matching(self, fragment: str) -> List[tuple]:
        return [q for q in self._queries if fragment.lower() in q[0].lower()]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_payload(n_rows: int = 3, **overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "trace_id": str(uuid4()),
        "idempotency_key": f"test_job_{uuid4()}",
        "source_type": "csv",
        "source_ref": "s3://test/catalog.csv",
        "rows": [
            {
                "mpn": f"SKU-{i:03d}",
                "brand": "Acme",
                "title": f"Product {i}",
                "price_minor": 10000 + i * 100,
                "currency": "RUB",
            }
            for i in range(n_rows)
        ],
    }
    base.update(overrides)
    return base


def _make_db(n_rows: int = 3) -> _MockConn:
    db = _MockConn()
    row_ids = [str(uuid4()) for _ in range(n_rows)]
    db._row_ids = row_ids
    db._pending_rows = [
        (rid, i, f"SKU-{i:03d}", "Acme", f"Product {i}", 10000 + i * 100, "RUB", None)
        for i, rid in enumerate(row_ids)
    ]
    return db


# ── TC-R1-01  Happy path ──────────────────────────────────────────────────────


def test_r1_01_happy_path_3_rows() -> None:
    db = _make_db(3)
    payload = _make_payload(3)

    result = run_catalog_pipeline(db, payload)

    assert result["job_state"] == "done"
    assert result["synced"] == 3
    assert result["failed"] == 0
    assert "job_id" in result

    # job INSERT was attempted
    assert db.queries_matching("insert into stg_catalog_jobs")

    # 3 rows inserted
    row_inserts = db.queries_matching("insert into stg_catalog_imports")
    assert len(row_inserts) == 3


# ── TC-R1-02  Parse stage: ONE commit per batch ───────────────────────────────


def test_r1_02_parse_stage_single_commit() -> None:
    """
    After parse stage all row inserts must be covered by exactly ONE commit.
    We count commits:
      1 → job creation
      1 → job → parsing
      1 → all row inserts + job → syncing  (the "ONE commit per batch")
      N → sync stage commits (one per row)
      1 → job finalisation
    So for 3 rows: total commits = 1+1+1+3+1 = 7
    """
    db = _make_db(3)
    run_catalog_pipeline(db, _make_payload(3))

    # 3 rows sync + 3 fixed stage commits (job create, job→parsing, batch, job→done)
    assert db._commits == 7


# ── TC-R1-03  Sync stage: ONE commit per row ─────────────────────────────────


def test_r1_03_sync_stage_commit_per_row() -> None:
    db = _make_db(5)
    run_catalog_pipeline(db, _make_payload(5))
    # 5 rows → 5 sync commits + 4 fixed = 9
    assert db._commits == 9


# ── TC-R1-04  Photo failure does NOT block sync ───────────────────────────────


def test_r1_04_photo_failure_non_blocking() -> None:
    db = _make_db(2)
    # Give rows photo_urls so uploader is invoked
    db._pending_rows = [
        (db._row_ids[0], 0, "SKU-000", "Acme", "Product 0", 10000, "RUB", "http://img/0.jpg"),
        (db._row_ids[1], 1, "SKU-001", "Acme", "Product 1", 10100, "RUB", "http://img/1.jpg"),
    ]

    exploding_uploader_calls: List[str] = []

    def _bad_uploader(url: str) -> None:
        exploding_uploader_calls.append(url)
        raise RuntimeError("S3 unreachable")

    result = run_catalog_pipeline(db, _make_payload(2), uploader=_bad_uploader)

    # Both rows should still be synced despite photo failure
    assert result["job_state"] == "done"
    assert result["synced"] == 2
    assert result["failed"] == 0

    # Uploader was called for each row
    assert len(exploding_uploader_calls) == 2

    # photo_status = 'failed' updates were issued
    photo_fail_updates = [
        q for q in db._queries
        if "photo_status = 'failed'" in q[0]
    ]
    assert len(photo_fail_updates) == 2


# ── TC-R1-05  Idempotency: duplicate key returns terminal skip ────────────────


def test_r1_05_idempotency_done_skip() -> None:
    db = _make_db(2)
    db._job_existing_state = "done"

    result = run_catalog_pipeline(db, _make_payload(2))

    assert result["job_state"] == "done"
    assert result.get("skipped") is True

    # Only the upsert commit should have happened — no parse or sync work
    assert db._commits == 1
    assert not db.queries_matching("insert into stg_catalog_imports")


def test_r1_05b_idempotency_failed_skip() -> None:
    db = _make_db(1)
    db._job_existing_state = "failed"

    result = run_catalog_pipeline(db, _make_payload(1))

    assert result["job_state"] == "failed"
    assert result.get("skipped") is True
    assert db._commits == 1


# ── TC-R1-06  Publisher error → row failed; job still done ───────────────────


def test_r1_06_publisher_error_row_failed() -> None:
    db = _make_db(3)

    call_count = {"n": 0}

    def _flaky_publisher(row: Dict[str, Any]) -> Optional[str]:
        call_count["n"] += 1
        if row["mpn"] == "SKU-001":
            raise RuntimeError("InSales 503")
        return f"ext:{row['mpn']}"

    result = run_catalog_pipeline(db, _make_payload(3), publisher=_flaky_publisher)

    assert result["job_state"] == "done"
    assert result["synced"] == 2
    assert result["failed"] == 1

    # sync_error update was issued for the failing row
    error_updates = [
        q for q in db._queries
        if "sync_error = %s" in q[0] and q[1] and "InSales 503" in str(q[1])
    ]
    assert len(error_updates) == 1


# ── TC-R1-07  Parse error advances job to failed ─────────────────────────────


def test_r1_07_parse_error_job_failed(monkeypatch) -> None:
    db = _make_db(2)

    original_parse = catalog_worker._run_parse_stage

    def _boom(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("disk full")

    monkeypatch.setattr(catalog_worker, "_run_parse_stage", _boom)

    result = run_catalog_pipeline(db, _make_payload(2))

    assert result["job_state"] == "failed"
    assert "disk full" in result.get("error", "")

    # job was advanced to failed
    job_state_updates = [
        q for q in db._queries
        if "update stg_catalog_jobs" in q[0].lower()
        and q[1] and "failed" in str(q[1])
    ]
    assert job_state_updates


# ── TC-R1-08  Pydantic: missing trace_id ─────────────────────────────────────


def test_r1_08_missing_trace_id() -> None:
    from pydantic import ValidationError

    db = _make_db(1)
    bad_payload = _make_payload(1)
    del bad_payload["trace_id"]

    with pytest.raises(ValidationError):
        run_catalog_pipeline(db, bad_payload)

    # No DB activity
    assert db._commits == 0


# ── TC-R1-09  Pydantic: empty rows list ──────────────────────────────────────


def test_r1_09_empty_rows_rejected() -> None:
    from pydantic import ValidationError

    db = _make_db(0)
    bad_payload = _make_payload(1)
    bad_payload["rows"] = []

    with pytest.raises(ValidationError):
        run_catalog_pipeline(db, bad_payload)

    assert db._commits == 0


# ── TC-R1-10  Boundary: no domain.reconciliation_* imports ───────────────────


def test_r1_10_no_reconciliation_imports() -> None:
    """
    Verify catalog_worker does not import any Tier-1 reconciliation modules.
    This is a static import-graph boundary check.
    """
    forbidden_prefixes = (
        "domain.reconciliation_service",
        "domain.reconciliation_alerts",
        "domain.reconciliation_verify",
        "domain.structural_checks",
        "domain.observability_service",
        "reconciliation_service",
        "reconciliation_alerts",
        "reconciliation_verify",
        "structural_checks",
        "observability_service",
    )

    worker_source = Path(catalog_worker.__file__).read_text(encoding="utf-8")

    for forbidden in forbidden_prefixes:
        assert forbidden not in worker_source, (
            f"catalog_worker imports forbidden Tier-1 module: {forbidden}"
        )

    # Also assert no raw DML on Core business tables
    core_tables = (
        "order_ledger",
        "shipments",
        "payment_transactions",
        "reservations",
        "stock_ledger_entries",
        "availability_snapshot",
    )
    for table in core_tables:
        assert table not in worker_source, (
            f"catalog_worker contains raw DML on Core table: {table}"
        )

"""tests/validation/test_r1_catalog_pipeline.py — R1 Mass Catalog Pipeline tests.

All tests are deterministic: no live DB, no live Shopware API, no unmocked time.
pandas DataFrames are built in-memory; no file I/O.

Coverage:
  test_clean_pn_*            — PN normalisation (§ R1.2)
  test_confidence_*          — confidence scoring policy (catalog_evidence_policy_v1)
  test_review_reason_*       — review flags (§ R1.7)
  test_iter_rows_*           — row iteration + idempotency key generation
  test_row_insert_*          — stg_catalog_imports idempotency (§ R1.5)
  test_job_duplicate_skip    — stg_catalog_jobs ON CONFLICT DO NOTHING
  test_publish_*             — Shopware publish path (§ R1.3)
  test_full_pipeline_*       — end-to-end with stub DB + stub Shopware
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import pytest

# ---------------------------------------------------------------------------
# Path setup — make windmill-core-v1 importable.
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]  # .cursor/windmill-core-v1/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Stub infrastructure
# ---------------------------------------------------------------------------

class _StubCursor:
    """In-memory cursor that simulates stg_catalog_jobs + stg_catalog_imports + shopware_operations."""

    def __init__(self, store: "_StubStore") -> None:
        self._store = store
        self._rows: List[Any] = []

    def execute(self, query: str, params: tuple = ()) -> None:  # type: ignore[assignment]
        q = " ".join(query.strip().lower().split())
        self._rows = []

        # ------------------------------------------------------------------ stg_catalog_jobs
        if q.startswith("insert into stg_catalog_jobs"):
            # SQL hardcodes status='pending', so params has 7 values (no status param).
            job_id, trace_id, idem_key, filename, brand, created_at, updated_at = params
            if idem_key in self._store.jobs_by_idem:
                return
            self._store.jobs_by_idem[idem_key] = {
                "id": str(job_id), "trace_id": trace_id, "idempotency_key": idem_key,
                "source_filename": filename, "brand": brand,
                "row_count": 0, "status": "pending", "error": None,
            }
            self._store.jobs_by_id[str(job_id)] = self._store.jobs_by_idem[idem_key]
            self._rows = [(str(job_id),)]
            return

        if q.startswith("update stg_catalog_jobs set status"):
            status, row_count, error, updated_at, job_id = params
            row = self._store.jobs_by_id.get(str(job_id))
            if row:
                row["status"] = status
                row["row_count"] = row_count
                row["error"] = error
            return

        # ------------------------------------------------------------------ stg_catalog_imports
        if q.startswith("insert into stg_catalog_imports"):
            # SQL hardcodes status='pending', so params has 14 values (no status param).
            (
                row_id, job_id, trace_id, idem_key, brand, pn, name,
                qty, approx_price, confidence, review_reason, photo_url,
                created_at, updated_at,
            ) = params
            if idem_key in self._store.imports_by_idem:
                return
            rec = {
                "id": str(row_id), "job_id": str(job_id), "trace_id": trace_id,
                "idempotency_key": idem_key, "brand": brand, "part_number": pn,
                "name": name, "qty": qty, "approx_price": approx_price,
                "confidence": confidence, "review_reason": review_reason,
                "photo_url": photo_url, "status": "pending",
                "shopware_op_id": None, "error_class": None, "error": None,
            }
            self._store.imports_by_idem[idem_key] = rec
            self._rows = [(str(row_id),)]
            return

        if q.startswith("update stg_catalog_imports"):
            status, shopware_op_id, error_class, error, updated_at, idem_key = params
            rec = self._store.imports_by_idem.get(str(idem_key))
            if rec:
                rec["status"] = status
                rec["shopware_op_id"] = shopware_op_id
                rec["error_class"] = error_class
                rec["error"] = error
            return

        # ------------------------------------------------------------------ shopware_operations
        if q.startswith("insert into shopware_operations"):
            # SQL: VALUES (%s, %s, %s, 'pending', NULL, 0, %s, %s) — 5 params.
            op_id, product_number, content_hash, created_at, updated_at = params
            key = (product_number, content_hash)
            if key in self._store.sw_ops:
                return
            rec = {
                "id": str(op_id), "product_number": product_number,
                "content_hash": content_hash, "status": "pending",
                "error": None, "attempt": 0,
                "created_at": created_at, "updated_at": created_at,
            }
            self._store.sw_ops[key] = rec
            self._store.sw_ops_by_id[str(op_id)] = rec
            self._rows = [(str(op_id),)]
            return

        if q.startswith("select id, status, attempt, updated_at from shopware_operations"):
            product_number, content_hash = params
            rec = self._store.sw_ops.get((product_number, content_hash))
            if rec:
                self._rows = [(rec["id"], rec["status"], rec["attempt"], rec["updated_at"])]
            return

        if "set status = 'pending', attempt = attempt + 1, error = null" in q:
            (op_id,) = params
            rec = self._store.sw_ops_by_id.get(str(op_id))
            if rec:
                rec["status"] = "pending"
                rec["attempt"] = int(rec["attempt"]) + 1
                rec["error"] = None
                rec["updated_at"] = datetime.now(timezone.utc)
                self._rows = [(rec["id"],)]
            return

        if q.startswith("update shopware_operations set status = %s, error = %s where id = %s"):
            status, error, op_id = params
            rec = self._store.sw_ops_by_id.get(str(op_id))
            if rec:
                rec["status"] = status
                rec["error"] = error
            return

        raise AssertionError(f"Unexpected SQL in stub cursor:\n{query}")

    def fetchone(self) -> Any:
        return self._rows.pop(0) if self._rows else None

    def close(self) -> None:
        pass


class _StubStore:
    """Shared in-memory state across cursor instances."""

    def __init__(self) -> None:
        self.jobs_by_idem: Dict[str, Any] = {}
        self.jobs_by_id: Dict[str, Any] = {}
        self.imports_by_idem: Dict[str, Any] = {}
        self.sw_ops: Dict[tuple, Any] = {}
        self.sw_ops_by_id: Dict[str, Any] = {}
        self.commit_count: int = 0


class _StubConn:
    """Stub psycopg2 connection backed by _StubStore."""

    def __init__(self) -> None:
        self.autocommit = False
        self._store = _StubStore()

    def cursor(self) -> _StubCursor:
        return _StubCursor(self._store)

    def commit(self) -> None:
        self._store.commit_count += 1

    def rollback(self) -> None:
        pass

    @property
    def store(self) -> _StubStore:
        return self._store


class _StubShopwareClient:
    """Stub ShopwareApiClient — tracks calls, never hits network."""

    def __init__(self, *, raise_on_pn: Optional[str] = None) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._raise_on_pn = raise_on_pn

    def upsert_product(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append(payload)
        if self._raise_on_pn and payload.get("productNumber") == self._raise_on_pn:
            from ru_worker.shopware_api_client import ShopwareApiError
            raise ShopwareApiError(f"Injected error for {self._raise_on_pn}")
        return {"dry_run": True}


def _make_df(rows: List[Dict[str, Any]]) -> "Any":
    import pandas as pd
    return pd.DataFrame(rows).astype(str).replace("nan", "")


def _make_payload(
    *,
    trace_id: str = "trace-001",
    idem_key: str = "job-idem-001",
    brand: str = "ACME",
    file: str = "test.csv",
    tax_id: str = "TAX-ID",
    currency_id: str = "CURRENCY-ID",
    default_stock: int = 0,
) -> "Any":
    from domain.catalog_models import CatalogJobPayload
    return CatalogJobPayload(
        trace_id=trace_id,
        idempotency_key=idem_key,
        source_file_path=file,
        brand=brand,
        shopware_tax_id=tax_id,
        shopware_currency_id=currency_id,
        shopware_default_stock=default_stock,
    )


import logging
_LOGGER = logging.getLogger("test_r1")


# ===========================================================================
# PN normalisation (R1.2)
# ===========================================================================

def test_clean_pn_uppercase():
    from domain.catalog_models import CatalogImportRow
    row = CatalogImportRow(
        trace_id="t1", idempotency_key="k1", brand="B",
        part_number="abc-123",
    )
    assert row.part_number == "ABC 123"


def test_clean_pn_collapses_separators():
    from domain.catalog_models import CatalogImportRow
    row = CatalogImportRow(
        trace_id="t1", idempotency_key="k1", brand="B",
        part_number="AB//CD__EF",
    )
    assert row.part_number == "AB CD EF"


def test_clean_pn_strips_whitespace():
    from domain.catalog_models import CatalogImportRow
    row = CatalogImportRow(
        trace_id="t1", idempotency_key="k1", brand="B",
        part_number="  XY-001  ",
    )
    assert row.part_number == "XY 001"


def test_clean_pn_empty_raises():
    from domain.catalog_models import CatalogImportRow
    with pytest.raises(Exception):
        CatalogImportRow(trace_id="t1", idempotency_key="k1", brand="B", part_number="   ")


# ===========================================================================
# Confidence scoring (catalog_evidence_policy_v1)
# ===========================================================================

def test_confidence_high_all_fields():
    from domain.catalog_models import CatalogImportRow, ConfidenceLevel
    row = CatalogImportRow(
        trace_id="t", idempotency_key="k", brand="B",
        part_number="PN-001",
        name="Part Name",
        approx_price=100.0,
        qty=5,
        photo_url="https://example.com/photo.jpg",
    )
    assert row.confidence == ConfidenceLevel.HIGH
    assert row.review_reason is None


def test_confidence_high_no_photo_sets_review_reason():
    from domain.catalog_models import CatalogImportRow, ConfidenceLevel, ReviewReason
    row = CatalogImportRow(
        trace_id="t", idempotency_key="k", brand="B",
        part_number="PN-001",
        name="Part Name",
        approx_price=100.0,
        qty=5,
    )
    assert row.confidence == ConfidenceLevel.HIGH
    assert row.review_reason == ReviewReason.NO_PHOTO


def test_confidence_medium_name_only():
    from domain.catalog_models import CatalogImportRow, ConfidenceLevel
    row = CatalogImportRow(
        trace_id="t", idempotency_key="k", brand="B",
        part_number="PN-002",
        name="Partial Name",
    )
    assert row.confidence == ConfidenceLevel.MEDIUM


def test_confidence_medium_price_only():
    from domain.catalog_models import CatalogImportRow, ConfidenceLevel
    row = CatalogImportRow(
        trace_id="t", idempotency_key="k", brand="B",
        part_number="PN-003",
        approx_price=50.0,
    )
    assert row.confidence == ConfidenceLevel.MEDIUM


def test_confidence_low_pn_only():
    from domain.catalog_models import CatalogImportRow, ConfidenceLevel, ReviewReason
    row = CatalogImportRow(
        trace_id="t", idempotency_key="k", brand="B",
        part_number="PN-004",
    )
    assert row.confidence == ConfidenceLevel.LOW
    assert row.review_reason == ReviewReason.TITLE_CONFIDENCE_LOW


# ===========================================================================
# Row iteration (R1.1 — iter_rows)
# ===========================================================================

def test_iter_rows_missing_pn_is_rejected():
    from workers.catalog_worker import _iter_rows
    df = _make_df([{"part_number": "", "name": "X", "qty": "1", "approx_price": "10"}])
    results = list(_iter_rows(df, "ACME", "job-key", "trace-001"))
    assert len(results) == 1
    row, reason = results[0]
    assert row is None
    assert "missing_pn" in reason


def test_iter_rows_valid_row_normalised():
    from workers.catalog_worker import _iter_rows
    from domain.catalog_models import ConfidenceLevel
    df = _make_df([{
        "part_number": "ab-001", "name": "Part AB", "qty": "3", "approx_price": "99.9"
    }])
    results = list(_iter_rows(df, "BRAND", "job-key", "trace-001"))
    assert len(results) == 1
    row, reason = results[0]
    assert reason is None
    assert row is not None
    assert row.part_number == "AB 001"
    assert row.confidence == ConfidenceLevel.HIGH


def test_iter_rows_idempotency_key_is_deterministic():
    from workers.catalog_worker import _iter_rows
    df = _make_df([{"part_number": "PN-X", "name": "N"}])
    r1 = list(_iter_rows(df, "B", "job-key", "trace-1"))
    r2 = list(_iter_rows(df, "B", "job-key", "trace-1"))
    assert r1[0][0].idempotency_key == r2[0][0].idempotency_key


# ===========================================================================
# DB idempotency — stg_catalog_imports (R1.5)
# ===========================================================================

def test_row_insert_idempotent_second_call_is_skip():
    from workers.catalog_worker import _row_insert_idempotent
    from domain.catalog_models import CatalogImportRow
    conn = _StubConn()
    row = CatalogImportRow(
        trace_id="t", idempotency_key="idem-row-001", brand="B",
        part_number="PN-001", name="N", approx_price=1.0, qty=1,
    )
    m1 = _row_insert_idempotent(conn, "job-id-001", row)
    m2 = _row_insert_idempotent(conn, "job-id-001", row)
    assert m1 == "new"
    assert m2 == "skip"
    assert len(conn.store.imports_by_idem) == 1


# ===========================================================================
# DB idempotency — stg_catalog_jobs (R1.5)
# ===========================================================================

def test_job_duplicate_idempotency_key_is_skip():
    from workers.catalog_worker import _job_insert
    conn = _StubConn()
    payload = _make_payload(idem_key="job-idem-dup")
    m1 = _job_insert(conn, "job-id-A", payload, "file.csv")
    m2 = _job_insert(conn, "job-id-B", payload, "file.csv")
    assert m1 == "new"
    assert m2 == "skip"
    assert len(conn.store.jobs_by_idem) == 1


# ===========================================================================
# Shopware publish path (R1.3)
# ===========================================================================

def test_publish_row_high_confidence_calls_shopware(monkeypatch):
    from workers.catalog_worker import _publish_row
    from domain.catalog_models import CatalogImportRow

    conn = _StubConn()
    sw = _StubShopwareClient()

    row = CatalogImportRow(
        trace_id="t", idempotency_key="idem-pub-001", brand="B",
        part_number="PN-PUB", name="Name", approx_price=200.0, qty=10,
    )
    # Pre-insert so update SQL can find it.
    from workers.catalog_worker import _row_insert_idempotent
    _row_insert_idempotent(conn, "job-id", row)

    _publish_row(row, conn, sw, "TAX", "CUR", 0, _LOGGER)

    assert len(sw.calls) == 1
    assert sw.calls[0]["productNumber"] == "PN PUB"

    rec = conn.store.imports_by_idem["idem-pub-001"]
    assert rec["status"] == "done"
    assert rec["shopware_op_id"] is not None


def test_publish_row_idempotent_second_run_is_skip(monkeypatch):
    from workers.catalog_worker import _publish_row
    from domain.catalog_models import CatalogImportRow
    from workers.catalog_worker import _row_insert_idempotent

    conn = _StubConn()
    sw = _StubShopwareClient()

    row = CatalogImportRow(
        trace_id="t", idempotency_key="idem-pub-002", brand="B",
        part_number="PN-DUP-PUB", name="Name", approx_price=50.0, qty=2,
    )
    _row_insert_idempotent(conn, "job-id", row)

    _publish_row(row, conn, sw, "TAX", "CUR", 0, _LOGGER)
    assert len(sw.calls) == 1

    _publish_row(row, conn, sw, "TAX", "CUR", 0, _LOGGER)
    # Second call hits mode=skip — no second Shopware upsert.
    assert len(sw.calls) == 1


def test_publish_row_shopware_error_marks_failed():
    from workers.catalog_worker import _publish_row, _row_insert_idempotent
    from domain.catalog_models import CatalogImportRow
    from ru_worker.shopware_api_client import ShopwareApiError

    conn = _StubConn()
    row = CatalogImportRow(
        trace_id="t", idempotency_key="idem-fail-001", brand="B",
        part_number="PN-FAIL", name="Name", approx_price=50.0, qty=1,
    )
    _row_insert_idempotent(conn, "job-id", row)

    sw = _StubShopwareClient(raise_on_pn="PN FAIL")

    with pytest.raises(ShopwareApiError):
        _publish_row(row, conn, sw, "TAX", "CUR", 0, _LOGGER)

    rec = conn.store.imports_by_idem["idem-fail-001"]
    assert rec["status"] == "failed"
    assert rec["error_class"] == "TRANSIENT"


# ===========================================================================
# Full pipeline (R1.1 — R1.6)
# ===========================================================================

def test_full_pipeline_mixed_confidence():
    from workers.catalog_worker import run_catalog_job

    conn = _StubConn()
    sw = _StubShopwareClient()

    df = _make_df([
        # HIGH: all fields
        {"part_number": "PN-A", "name": "Part A", "qty": "5", "approx_price": "100",
         "photo_url": "https://ex.com/a.jpg"},
        # MEDIUM: name only
        {"part_number": "PN-B", "name": "Part B"},
        # LOW: no name/price/qty
        {"part_number": "PN-C"},
        # Rejected: no PN
        {"part_number": "", "name": "No PN"},
    ])

    payload = _make_payload()
    result = run_catalog_job(payload, conn, sw, _LOGGER, dataframe=df)

    assert result["status"] == "done"
    counts = result["counts"]
    assert counts["total"] == 4
    assert counts["published"] == 1   # Only HIGH (PN-A)
    assert counts["review"] >= 2      # MEDIUM, LOW, and rejected
    assert counts["failed"] == 0


def test_full_pipeline_duplicate_job_is_skip():
    from workers.catalog_worker import run_catalog_job

    conn = _StubConn()
    sw = _StubShopwareClient()
    df = _make_df([{"part_number": "PN-X", "name": "N", "qty": "1", "approx_price": "1"}])
    payload = _make_payload(idem_key="job-dup-key")

    r1 = run_catalog_job(payload, conn, sw, _LOGGER, dataframe=df)
    r2 = run_catalog_job(payload, conn, sw, _LOGGER, dataframe=df)

    assert r1["status"] == "done"
    assert r2["status"] == "skip"
    # Only one job in store.
    assert len(conn.store.jobs_by_idem) == 1


def test_full_pipeline_500_sku_all_high(monkeypatch):
    """Smoke test: 500 HIGH-confidence SKUs all publish successfully."""
    from workers.catalog_worker import run_catalog_job

    rows = [
        {
            "part_number": f"PN-{i:04d}",
            "name": f"Part {i}",
            "qty": "10",
            "approx_price": "99.9",
            "photo_url": f"https://ex.com/{i}.jpg",
        }
        for i in range(500)
    ]
    df = _make_df(rows)
    conn = _StubConn()
    sw = _StubShopwareClient()
    payload = _make_payload(idem_key="job-500-sku")

    result = run_catalog_job(payload, conn, sw, _LOGGER, dataframe=df)

    assert result["status"] == "done"
    assert result["counts"]["total"] == 500
    assert result["counts"]["published"] == 500
    assert result["counts"]["failed"] == 0
    assert len(sw.calls) == 500


def test_full_pipeline_partial_shopware_failure():
    """If some rows fail Shopware, job status is 'failed', others succeed."""
    from workers.catalog_worker import run_catalog_job

    df = _make_df([
        {"part_number": "PN-OK", "name": "OK", "qty": "1", "approx_price": "1",
         "photo_url": "https://ex.com/ok.jpg"},
        {"part_number": "PN-BAD", "name": "Bad", "qty": "1", "approx_price": "1",
         "photo_url": "https://ex.com/bad.jpg"},
    ])
    conn = _StubConn()
    sw = _StubShopwareClient(raise_on_pn="PN BAD")
    payload = _make_payload(idem_key="job-partial-fail")

    result = run_catalog_job(payload, conn, sw, _LOGGER, dataframe=df)

    assert result["status"] == "failed"
    assert result["counts"]["published"] == 1
    assert result["counts"]["failed"] == 1

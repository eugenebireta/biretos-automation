"""workers/catalog_worker.py — R1 Mass Catalog Pipeline.

Tier-3 Revenue worker. Reads Excel/CSV, normalises via Pydantic,
publishes HIGH-confidence rows to Shopware, flags the rest for review.

FSM — stg_catalog_jobs (max 5 states, linear per DNA §5b):
    pending → parsing → syncing → done / failed

FSM — stg_catalog_imports (max 5 states, linear per DNA §5b):
    pending → syncing → done / failed / review_required

DNA §7 compliance checklist:
  [x] trace_id extracted from payload
  [x] idempotency_key for all DB ops (INSERT ON CONFLICT DO NOTHING)
  [x] commit only at worker boundary (callers pass open-transaction conn)
  [x] no logging of secrets or raw payload
  [x] structured error logging: error_class / severity / retriable
  [x] no silent exception swallowing
  [x] runnable in isolation (see __main__ block)
  [x] deterministic tests in test_r1_catalog_pipeline.py
  [x] structured boundary log: trace_id + key inputs + outcome

DNA §5b Revenue prohibitions observed:
  - Writes ONLY to stg_catalog_jobs and stg_catalog_imports (staging tables).
  - No DML on Core business tables.
  - No imports from domain.reconciliation_*.
  - No Guardian bypass (Revenue exception applies — mutations are staging-only).
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from uuid import uuid4

from domain.catalog_models import (
    CatalogImportRow,
    CatalogJobPayload,
    ConfidenceLevel,
    ReviewReason,
)
from ru_worker.shopware_api_client import ShopwareApiClient, ShopwareApiError
from ru_worker.shopware_idempotency import (
    insert_shopware_operation_idempotent,
    mark_shopware_operation_status,
)
from ru_worker.shopware_payload_builder import CDMProduct, build_shopware_product_payload

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
STALE_MINUTES = 10

_REQUIRED_COLUMNS = {"part_number"}
_OPTIONAL_COLUMNS = {"name", "qty", "approx_price", "photo_url"}


# ---------------------------------------------------------------------------
# Internal helpers — file parsing
# ---------------------------------------------------------------------------

def _parse_file(source_file_path: str) -> "Any":
    """Return a pandas DataFrame from an Excel or CSV path.

    Isolated here so tests can bypass file I/O entirely.
    Raises ValueError for unsupported extension.
    """
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pandas is required for catalog import") from exc

    path = Path(source_file_path)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=str)
    if suffix == ".csv":
        return pd.read_csv(path, dtype=str)
    raise ValueError(f"Unsupported file extension: {suffix!r}. Use .xlsx or .csv")


def _iter_rows(
    df: "Any",
    brand: str,
    job_idempotency_key: str,
    trace_id: str,
) -> Iterator[Tuple[Optional[CatalogImportRow], Optional[str]]]:
    """Yield (CatalogImportRow | None, rejection_reason | None) per DataFrame row.

    Row-level idempotency key = SHA-256(job_key + row_index + raw part_number).
    This is deterministic: re-importing the same file produces the same keys.
    """
    for idx, row_raw in enumerate(df.to_dict(orient="records")):
        row = {k.strip().lower(): (str(v).strip() if v is not None else "") for k, v in row_raw.items()}

        raw_pn = row.get("part_number", "").strip()
        if not raw_pn:
            yield None, ReviewReason.MISSING_PN.value
            continue

        # Deterministic idempotency key per row.
        key_src = f"{job_idempotency_key}:{idx}:{raw_pn}"
        row_idem_key = hashlib.sha256(key_src.encode()).hexdigest()

        try:
            import_row = CatalogImportRow(
                trace_id=trace_id,
                idempotency_key=row_idem_key,
                brand=brand,
                part_number=raw_pn,
                name=row.get("name") or None,
                qty=int(row["qty"]) if row.get("qty") and row["qty"].isdigit() else None,
                approx_price=float(row["approx_price"]) if row.get("approx_price") else None,
                photo_url=row.get("photo_url") or None,
            )
        except Exception as exc:
            yield None, f"{ReviewReason.VALIDATION_FAILED.value}: {exc}"
            continue

        yield import_row, None


# ---------------------------------------------------------------------------
# Internal helpers — DB operations
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _job_insert(db_conn, job_id: str, payload: CatalogJobPayload, filename: str) -> str:
    """Insert job row. Returns 'new' or 'skip'."""
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO stg_catalog_jobs
                (id, trace_id, idempotency_key, source_filename, brand, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (job_id, payload.trace_id, payload.idempotency_key, filename,
             payload.brand, _now_utc(), _now_utc()),
        )
        row = cursor.fetchone()
        return "new" if row else "skip"
    finally:
        cursor.close()


def _job_set_status(db_conn, job_id: str, status: str, row_count: int = 0, error: Optional[str] = None) -> None:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE stg_catalog_jobs
            SET status = %s, row_count = %s, error = %s, updated_at = %s
            WHERE id = %s
            """,
            (status, row_count, error, _now_utc(), job_id),
        )
    finally:
        cursor.close()


def _row_insert_idempotent(db_conn, job_id: str, row: CatalogImportRow) -> str:
    """Insert import row. Returns 'new' or 'skip'."""
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO stg_catalog_imports
                (id, job_id, trace_id, idempotency_key, brand, part_number, name,
                 qty, approx_price, confidence, review_reason, photo_url,
                 status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                str(uuid4()), job_id, row.trace_id, row.idempotency_key,
                row.brand, row.part_number, row.name,
                row.qty, row.approx_price,
                row.confidence.value,
                row.review_reason.value if row.review_reason else None,
                row.photo_url,
                _now_utc(), _now_utc(),
            ),
        )
        r = cursor.fetchone()
        return "new" if r else "skip"
    finally:
        cursor.close()


def _row_set_status(
    db_conn,
    idempotency_key: str,
    status: str,
    shopware_op_id: Optional[str] = None,
    error_class: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE stg_catalog_imports
            SET status = %s, shopware_op_id = %s, error_class = %s, error = %s, updated_at = %s
            WHERE idempotency_key = %s
            """,
            (status, shopware_op_id, error_class, error, _now_utc(), idempotency_key),
        )
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Shopware publish step
# ---------------------------------------------------------------------------

def _publish_row(
    row: CatalogImportRow,
    db_conn,
    shopware_client: ShopwareApiClient,
    tax_id: str,
    currency_id: str,
    default_stock: int,
    logger: logging.Logger,
) -> None:
    """Publish one HIGH-confidence row to Shopware (with idempotency guard).

    Updates stg_catalog_imports status: syncing → done / failed.
    Does NOT commit — caller is responsible.
    """
    _row_set_status(db_conn, row.idempotency_key, "syncing")

    cdm = CDMProduct(
        product_number=row.part_number,
        name=row.name or row.part_number,
        description=f"Brand: {row.brand}",
        price_gross=float(row.approx_price or 0.0),
        currency_id=currency_id,
        tax_id=tax_id,
        stock=row.qty if row.qty is not None else default_stock,
        active=True,
    )
    sw_payload = build_shopware_product_payload(cdm)

    op_info = insert_shopware_operation_idempotent(db_conn, row.part_number, sw_payload)
    op_id = op_info["operation_id"]
    mode = op_info["mode"]

    if mode == "skip":
        logger.info(
            "catalog_publish_skip",
            extra={
                "trace_id": row.trace_id,
                "part_number": row.part_number,
                "operation_id": op_id,
                "outcome": "already_synced",
            },
        )
        _row_set_status(db_conn, row.idempotency_key, "done", shopware_op_id=op_id)
        return

    try:
        shopware_client.upsert_product(sw_payload)
    except ShopwareApiError as exc:
        mark_shopware_operation_status(db_conn, op_id, "failed", error=str(exc))
        _row_set_status(
            db_conn, row.idempotency_key, "failed",
            shopware_op_id=op_id,
            error_class="TRANSIENT",
            error=str(exc),
        )
        logger.error(
            "catalog_publish_failed",
            extra={
                "trace_id": row.trace_id,
                "part_number": row.part_number,
                "error_class": "TRANSIENT",
                "severity": "ERROR",
                "retriable": True,
                "error": str(exc),
            },
        )
        raise

    mark_shopware_operation_status(db_conn, op_id, "confirmed")
    _row_set_status(db_conn, row.idempotency_key, "done", shopware_op_id=op_id)
    logger.info(
        "catalog_publish_done",
        extra={
            "trace_id": row.trace_id,
            "part_number": row.part_number,
            "operation_id": op_id,
            "outcome": "published",
        },
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_catalog_job(
    payload: CatalogJobPayload,
    db_conn,
    shopware_client: ShopwareApiClient,
    logger: logging.Logger,
    *,
    dataframe: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute the full R1 catalog pipeline.

    Parameters
    ----------
    payload:
        Validated CatalogJobPayload (trace_id, idempotency_key, brand, …).
    db_conn:
        Open psycopg2 connection with autocommit=False.
        Caller commits after this function returns.
    shopware_client:
        Pre-initialised ShopwareApiClient.
    logger:
        Structured logger.
    dataframe:
        Optional pre-parsed DataFrame (used in tests to avoid file I/O).
        When None the function loads from payload.source_file_path.

    Returns
    -------
    Dict with keys: job_id, status, counts (total/published/review/failed/skip).
    """
    trace_id = payload.trace_id
    job_id = str(uuid4())
    filename = Path(payload.source_file_path).name

    # --- Insert job (idempotent) ---
    insert_mode = _job_insert(db_conn, job_id, payload, filename)
    if insert_mode == "skip":
        logger.info(
            "catalog_job_skip",
            extra={"trace_id": trace_id, "idempotency_key": payload.idempotency_key, "outcome": "duplicate_job"},
        )
        return {"job_id": job_id, "status": "skip", "counts": {}}

    # Boundary log — job start.
    logger.info(
        "catalog_job_start",
        extra={
            "trace_id": trace_id,
            "job_id": job_id,
            "brand": payload.brand,
            "filename": filename,
        },
    )

    # --- Parse ---
    _job_set_status(db_conn, job_id, "parsing")
    try:
        df = dataframe if dataframe is not None else _parse_file(payload.source_file_path)
    except Exception as exc:
        _job_set_status(db_conn, job_id, "failed", error=f"parse_error: {exc}")
        logger.error(
            "catalog_job_parse_failed",
            extra={
                "trace_id": trace_id,
                "job_id": job_id,
                "error_class": "PERMANENT",
                "severity": "ERROR",
                "retriable": False,
                "error": str(exc),
            },
        )
        raise

    counts: Dict[str, int] = {"total": 0, "published": 0, "review": 0, "failed": 0, "skip": 0}

    rows_to_publish: List[CatalogImportRow] = []
    rows_for_review: List[CatalogImportRow] = []

    for import_row, rejection_reason in _iter_rows(
        df, payload.brand, payload.idempotency_key, trace_id
    ):
        counts["total"] += 1
        if import_row is None:
            counts["review"] += 1
            logger.warning(
                "catalog_row_rejected",
                extra={
                    "trace_id": trace_id,
                    "job_id": job_id,
                    "row_index": counts["total"] - 1,
                    "error_class": "POLICY_VIOLATION",
                    "severity": "WARNING",
                    "retriable": False,
                    "reason": rejection_reason,
                },
            )
            continue

        mode = _row_insert_idempotent(db_conn, job_id, import_row)
        if mode == "skip":
            counts["skip"] += 1
            continue

        if import_row.confidence == ConfidenceLevel.HIGH:
            rows_to_publish.append(import_row)
        else:
            rows_for_review.append(import_row)

    # Mark review rows.
    for row in rows_for_review:
        _row_set_status(db_conn, row.idempotency_key, "review_required")
        counts["review"] += 1

    # --- Sync ---
    _job_set_status(db_conn, job_id, "syncing", row_count=counts["total"])

    for row in rows_to_publish:
        try:
            _publish_row(
                row, db_conn, shopware_client,
                payload.shopware_tax_id, payload.shopware_currency_id,
                payload.shopware_default_stock, logger,
            )
            counts["published"] += 1
        except ShopwareApiError:
            counts["failed"] += 1

    # --- Done ---
    final_status = "done" if counts["failed"] == 0 else "failed"
    _job_set_status(db_conn, job_id, final_status, row_count=counts["total"])

    # Boundary log — job outcome.
    logger.info(
        "catalog_job_done",
        extra={
            "trace_id": trace_id,
            "job_id": job_id,
            "status": final_status,
            "counts": counts,
        },
    )

    return {"job_id": job_id, "status": final_status, "counts": counts}


# ---------------------------------------------------------------------------
# Isolation entry point (DNA §7 item 7)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="R1 Catalog Worker — manual run")
    parser.add_argument("--file", required=True, help="Path to Excel/CSV file")
    parser.add_argument("--brand", required=True, help="Brand name")
    parser.add_argument("--trace-id", default="manual-run", help="Trace ID")
    parser.add_argument("--dry-run", action="store_true", help="Shopware dry-run mode")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    _logger = logging.getLogger("catalog_worker")

    _logger.info("manual_run_start", extra={"file": args.file, "brand": args.brand})

    try:
        import os
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from config import get_config  # type: ignore

        cfg = get_config()
        sw = ShopwareApiClient(cfg, _logger)

        import psycopg2  # type: ignore

        conn = psycopg2.connect(
            host=cfg.postgres_host,
            port=cfg.postgres_port or 5432,
            dbname=cfg.postgres_db,
            user=cfg.postgres_user,
            password=cfg.postgres_password,
        )
        conn.autocommit = False

        job_payload = CatalogJobPayload(
            trace_id=args.trace_id,
            idempotency_key=hashlib.sha256(
                f"{args.trace_id}:{args.file}".encode()
            ).hexdigest(),
            source_file_path=args.file,
            brand=args.brand,
            shopware_tax_id=os.environ.get("SHOPWARE_TAX_ID", ""),
            shopware_currency_id=os.environ.get("SHOPWARE_CURRENCY_ID", "b7d2554b0ce847cd82f3ac9bd1c0dfca"),
        )

        result = run_catalog_job(job_payload, conn, sw, _logger)
        conn.commit()
        conn.close()

        _logger.info("manual_run_done", extra={"result": result})
        sys.exit(0)
    except Exception as exc:
        _logger.error("manual_run_error", extra={"error": str(exc)})
        sys.exit(1)

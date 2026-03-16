#!/usr/bin/env python3
"""
R1 Mass Catalog Pipeline — Tier-3 Revenue Adapter (MVP v1)

Architecture constraints (PROJECT_DNA v2.0):
  - NO imports from domain.reconciliation_*
  - NO raw DML on Core business tables
  - Only stg_* tables (stg_catalog_jobs, stg_catalog_imports)
  - Linear FSM:
      job-level:  pending → parsing → syncing → done | failed  (5 states max)
      row-level:  pending → syncing → done | failed
  - trace_id and idempotency_key are mandatory in every payload
  - Commit boundary:
      parse stage  → ONE commit per batch (all row inserts + job advance)
      sync stage   → ONE commit per row
  - Photo upload is optional: failure MUST NOT block sync
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# ── Structured logging ────────────────────────────────────────────────────────

_ALLOWED_JOB_COUNTERS = frozenset(
    {"total_rows", "parsed_rows", "synced_rows", "failed_rows"}
)


def _log(event: str, data: Dict[str, Any]) -> None:
    entry = {"event": event, "ts": time.time(), **data}
    print(json.dumps(entry, ensure_ascii=False), flush=True)


# ── Pydantic boundary models ──────────────────────────────────────────────────


class CatalogRowIn(BaseModel):
    """Single SKU row, validated before touching the DB."""

    mpn: str = Field(..., min_length=1, max_length=255)
    brand: str = Field(..., min_length=1, max_length=255)
    title: str = Field(..., min_length=1, max_length=1024)
    price_minor: Optional[int] = Field(None, ge=0)
    currency: str = Field("RUB", max_length=3)
    photo_url: Optional[str] = Field(None)
    extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("mpn", "brand", "title", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> str:
        return str(v).strip()

    @field_validator("currency", mode="before")
    @classmethod
    def _upper_currency(cls, v: Any) -> str:
        return str(v).strip().upper()


class CatalogJobPayload(BaseModel):
    """Incoming Windmill payload for catalog_worker."""

    trace_id: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)
    source_type: str = Field(..., pattern=r"^(csv|excel|json)$")
    source_ref: str = Field(..., min_length=1)
    rows: List[CatalogRowIn] = Field(..., min_length=1)


# ── FSM helpers ───────────────────────────────────────────────────────────────

_JOB_STATES = frozenset({"pending", "parsing", "syncing", "done", "failed"})
_ROW_STATES = frozenset({"pending", "syncing", "done", "failed"})
_PHOTO_STATES = frozenset({"none", "pending", "uploaded", "failed"})

# States from which resume is safe (idempotent re-entry)
_TERMINAL_JOB_STATES = frozenset({"done", "failed"})


def _advance_job(
    db_conn: Any,
    job_id: str,
    new_state: str,
    *,
    error_detail: Optional[str] = None,
    counters: Optional[Dict[str, int]] = None,
) -> None:
    """
    Advance stg_catalog_jobs FSM.  Caller owns the commit.
    Only whitelisted counter columns are accepted.
    """
    assert new_state in _JOB_STATES, f"Unknown job state: {new_state}"

    set_parts = ["job_state = %s", "updated_at = NOW()"]
    params: List[Any] = [new_state]

    if error_detail is not None:
        set_parts.append("error_detail = %s")
        params.append(error_detail[:2000])

    if counters:
        for col, val in counters.items():
            if col not in _ALLOWED_JOB_COUNTERS:
                raise ValueError(f"Disallowed counter column: {col}")
            set_parts.append(f"{col} = %s")
            params.append(int(val))

    params.append(job_id)
    cur = db_conn.cursor()
    try:
        cur.execute(
            f"UPDATE stg_catalog_jobs SET {', '.join(set_parts)} WHERE id = %s::uuid",
            params,
        )
    finally:
        cur.close()


def _advance_row(
    db_conn: Any,
    row_id: str,
    new_status: str,
    *,
    sync_error: Optional[str] = None,
    external_id: Optional[str] = None,
    mark_published: bool = False,
) -> None:
    """
    Advance stg_catalog_imports sync_status FSM.  Caller owns the commit.
    """
    assert new_status in _ROW_STATES, f"Unknown row status: {new_status}"

    set_parts = ["sync_status = %s", "updated_at = NOW()"]
    params: List[Any] = [new_status]

    if sync_error is not None:
        set_parts.append("sync_error = %s")
        params.append(sync_error[:2000])
    if external_id is not None:
        set_parts.append("external_id = %s")
        params.append(external_id)
    if mark_published:
        set_parts.append("published_at = NOW()")

    params.append(row_id)
    cur = db_conn.cursor()
    try:
        cur.execute(
            f"UPDATE stg_catalog_imports SET {', '.join(set_parts)} WHERE id = %s::uuid",
            params,
        )
    finally:
        cur.close()


# ── Parse stage ───────────────────────────────────────────────────────────────


def _run_parse_stage(
    db_conn: Any,
    job_id: str,
    trace_id: str,
    rows: List[CatalogRowIn],
) -> int:
    """
    Insert all validated rows into stg_catalog_imports.
    Uses ON CONFLICT DO NOTHING for idempotency (safe to re-run).
    Returns number of rows actually inserted.
    Caller owns the commit.
    """
    inserted = 0
    cur = db_conn.cursor()
    try:
        for idx, row in enumerate(rows):
            row_key = f"catalog_row:{job_id}:{idx}:{row.mpn}:{row.brand}"
            cur.execute(
                """
                INSERT INTO stg_catalog_imports (
                    job_id, trace_id, idempotency_key, row_idx,
                    mpn, brand, title, price_minor, currency,
                    raw_payload, photo_url, sync_status
                )
                VALUES (
                    %s::uuid, %s::uuid, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s::jsonb, %s, 'pending'
                )
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING id
                """,
                (
                    job_id,
                    trace_id,
                    row_key,
                    idx,
                    row.mpn,
                    row.brand,
                    row.title,
                    row.price_minor,
                    row.currency,
                    json.dumps(row.extra, ensure_ascii=False),
                    row.photo_url,
                ),
            )
            if cur.fetchone():
                inserted += 1
                _log("catalog_row_parsed", {"job_id": job_id, "idx": idx, "mpn": row.mpn})
            else:
                _log(
                    "catalog_row_parse_skip_duplicate",
                    {"job_id": job_id, "idx": idx, "mpn": row.mpn},
                )
    finally:
        cur.close()
    return inserted


# ── Photo upload (optional, non-blocking) ─────────────────────────────────────


def _try_upload_photo(
    db_conn: Any,
    row_id: str,
    photo_url: Optional[str],
    uploader: Optional[Callable[[str], None]],
) -> None:
    """
    Attempt to upload a photo.  Any exception is swallowed — sync must proceed.
    State transitions: none → pending → uploaded | failed
    No separate commit: photo status is written within the row's sync transaction.
    """
    if not photo_url or uploader is None:
        return

    cur = db_conn.cursor()
    try:
        cur.execute(
            "UPDATE stg_catalog_imports SET photo_status = 'pending', updated_at = NOW()"
            " WHERE id = %s::uuid",
            (row_id,),
        )
        try:
            uploader(photo_url)
            cur.execute(
                "UPDATE stg_catalog_imports SET photo_status = 'uploaded', updated_at = NOW()"
                " WHERE id = %s::uuid",
                (row_id,),
            )
            _log("catalog_photo_uploaded", {"row_id": row_id})
        except Exception as exc:  # noqa: BLE001
            cur.execute(
                "UPDATE stg_catalog_imports SET photo_status = 'failed', updated_at = NOW()"
                " WHERE id = %s::uuid",
                (row_id,),
            )
            _log("catalog_photo_upload_failed", {"row_id": row_id, "error": str(exc)})
    finally:
        cur.close()


# ── Sync stage ────────────────────────────────────────────────────────────────


def _load_pending_rows(db_conn: Any, job_id: str) -> List[Dict[str, Any]]:
    """
    Query stg_catalog_imports for all rows still needing sync.
    Called after parse stage completes so resume is naturally supported.
    """
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, row_idx, mpn, brand, title, price_minor, currency, photo_url
            FROM stg_catalog_imports
            WHERE job_id = %s::uuid
              AND sync_status = 'pending'
            ORDER BY row_idx
            """,
            (job_id,),
        )
        return [
            {
                "id": str(r[0]),
                "row_idx": r[1],
                "mpn": r[2],
                "brand": r[3],
                "title": r[4],
                "price_minor": r[5],
                "currency": r[6],
                "photo_url": r[7],
            }
            for r in cur.fetchall()
        ]
    finally:
        cur.close()


def _run_sync_stage(
    db_conn: Any,
    job_id: str,
    rows: List[Dict[str, Any]],
    *,
    publisher: Optional[Callable[[Dict[str, Any]], Optional[str]]],
    uploader: Optional[Callable[[str], None]],
) -> Dict[str, int]:
    """
    Sync each row to the external catalog platform.

    Commit boundary: ONE commit per row.
    Photo failure MUST NOT prevent the row from being marked done.
    """
    synced = 0
    failed = 0

    for entry in rows:
        row_id = entry["id"]

        # Mark as syncing (within this row's transaction, committed below)
        cur = db_conn.cursor()
        try:
            cur.execute(
                "UPDATE stg_catalog_imports"
                " SET sync_status = 'syncing', updated_at = NOW()"
                " WHERE id = %s::uuid",
                (row_id,),
            )
        finally:
            cur.close()

        # Photo: optional, non-blocking — always runs before publish attempt
        _try_upload_photo(db_conn, row_id, entry.get("photo_url"), uploader)

        # Publish to external catalog
        external_id: Optional[str] = None
        error_msg: Optional[str] = None
        try:
            if publisher is not None:
                result = publisher(
                    {
                        "mpn": entry["mpn"],
                        "brand": entry["brand"],
                        "title": entry["title"],
                        "price_minor": entry["price_minor"],
                        "currency": entry["currency"],
                    }
                )
                external_id = str(result) if result is not None else f"pub:{row_id}"
            else:
                external_id = f"dry_run:{entry['mpn']}"
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            _log(
                "catalog_row_sync_failed",
                {"job_id": job_id, "row_id": row_id, "error": error_msg},
            )

        if error_msg:
            _advance_row(db_conn, row_id, "failed", sync_error=error_msg)
            db_conn.commit()
            failed += 1
        else:
            _advance_row(
                db_conn,
                row_id,
                "done",
                external_id=external_id,
                mark_published=True,
            )
            db_conn.commit()
            synced += 1
            _log(
                "catalog_row_synced",
                {"job_id": job_id, "row_id": row_id, "external_id": external_id},
            )

    return {"synced": synced, "failed": failed}


# ── Main entry point ──────────────────────────────────────────────────────────


def run_catalog_pipeline(
    db_conn: Any,
    payload: Dict[str, Any],
    *,
    publisher: Optional[Callable[[Dict[str, Any]], Optional[str]]] = None,
    uploader: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """
    R1 Mass Catalog Pipeline — main Windmill entry point.

    Args:
        db_conn:   psycopg2-compatible connection.
        payload:   Dict matching CatalogJobPayload schema.
                   MUST contain trace_id and idempotency_key.
        publisher: callable(row_dict) → external_id | None
                   Called once per row during sync stage.
                   None = dry-run mode.
        uploader:  callable(photo_url) → None
                   Called once per row (optional).
                   None = skip photo upload.

    Returns:
        {"job_id": str, "job_state": str, ...counters}

    Commit boundaries:
        - Job creation:       1 commit
        - Parse stage:        1 commit (all row inserts + job → syncing)
        - Sync stage:         1 commit per row
        - Job finalisation:   1 commit
    """
    # ── Validate payload at boundary ─────────────────────────────────────────
    job_payload = CatalogJobPayload.model_validate(payload)
    trace_id = job_payload.trace_id
    idempotency_key = job_payload.idempotency_key

    _log(
        "catalog_pipeline_start",
        {
            "trace_id": trace_id,
            "idempotency_key": idempotency_key,
            "source_type": job_payload.source_type,
            "row_count": len(job_payload.rows),
        },
    )

    # ── Upsert job record (idempotent) ────────────────────────────────────────
    cur = db_conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO stg_catalog_jobs (
                trace_id, idempotency_key, job_state,
                source_type, source_ref, total_rows
            )
            VALUES (%s::uuid, %s, 'pending', %s, %s, %s)
            ON CONFLICT (idempotency_key) DO UPDATE
                SET updated_at = NOW()
            RETURNING id, job_state
            """,
            (
                trace_id,
                idempotency_key,
                job_payload.source_type,
                job_payload.source_ref,
                len(job_payload.rows),
            ),
        )
        job_id_raw, existing_state = cur.fetchone()
        job_id = str(job_id_raw)
    finally:
        cur.close()
    db_conn.commit()

    if existing_state in _TERMINAL_JOB_STATES:
        _log(
            "catalog_pipeline_terminal_skip",
            {"job_id": job_id, "job_state": existing_state, "trace_id": trace_id},
        )
        return {"job_id": job_id, "job_state": existing_state, "skipped": True}

    # ── Parse stage ───────────────────────────────────────────────────────────
    _advance_job(db_conn, job_id, "parsing")
    db_conn.commit()

    try:
        inserted = _run_parse_stage(db_conn, job_id, trace_id, job_payload.rows)
        _advance_job(
            db_conn,
            job_id,
            "syncing",
            counters={"parsed_rows": inserted},
        )
        db_conn.commit()  # ONE commit for the entire parse batch
        _log("catalog_parse_done", {"job_id": job_id, "inserted": inserted})
    except Exception as exc:
        _advance_job(db_conn, job_id, "failed", error_detail=str(exc))
        db_conn.commit()
        _log("catalog_parse_failed", {"job_id": job_id, "error": str(exc)})
        return {"job_id": job_id, "job_state": "failed", "error": str(exc)}

    # ── Sync stage ────────────────────────────────────────────────────────────
    pending_rows = _load_pending_rows(db_conn, job_id)

    try:
        counters = _run_sync_stage(
            db_conn,
            job_id,
            pending_rows,
            publisher=publisher,
            uploader=uploader,
        )
    except Exception as exc:
        _advance_job(db_conn, job_id, "failed", error_detail=str(exc))
        db_conn.commit()
        _log("catalog_sync_fatal", {"job_id": job_id, "error": str(exc)})
        return {"job_id": job_id, "job_state": "failed", "error": str(exc)}

    # ── Finalise job ──────────────────────────────────────────────────────────
    _advance_job(
        db_conn,
        job_id,
        "done",
        counters={
            "synced_rows": counters["synced"],
            "failed_rows": counters["failed"],
        },
    )
    db_conn.commit()

    _log(
        "catalog_pipeline_done",
        {
            "job_id": job_id,
            "trace_id": trace_id,
            "synced": counters["synced"],
            "failed": counters["failed"],
        },
    )
    return {
        "job_id": job_id,
        "job_state": "done",
        "synced": counters["synced"],
        "failed": counters["failed"],
    }

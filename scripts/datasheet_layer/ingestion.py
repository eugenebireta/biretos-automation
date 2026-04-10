"""
SS-1.2 — Ingestion pipeline: find_datasheet() output -> versioned storage.

Takes output from existing find_datasheet() + download_documents.py
and creates versioned DatasheetRecord in the store.

No webhook ingestion path — this module is called directly from scripts.
"""
from __future__ import annotations

import logging
from pathlib import Path
from .schema import DatasheetRecord, compute_content_hash, _now
from .store import get_latest_version, write_version, _structured_log

logger = logging.getLogger(__name__)

_DEFAULT_BASE = Path(__file__).resolve().parent.parent.parent / "downloads" / "datasheets"


def ingest_from_find_datasheet(
    pn: str,
    brand: str,
    find_result: dict,
    pdf_bytes: bytes | None = None,
    pdf_path: str | None = None,
    trace_id: str = "",
    base_dir: Path | None = None,
) -> DatasheetRecord | None:
    """
    Ingest a find_datasheet() result into versioned storage.

    Args:
        pn: Part number
        brand: Brand name
        find_result: dict from find_datasheet() with datasheet_status, pdf_url, etc.
        pdf_bytes: Optional raw PDF content for content hash
        pdf_path: Optional local path to PDF file
        trace_id: Mandatory trace_id (DNA §7)
        base_dir: Storage directory (default: downloads/datasheets/)

    Returns:
        DatasheetRecord if ingested, None if skipped (not_found or dedup)
    """
    if base_dir is None:
        base_dir = _DEFAULT_BASE

    status = find_result.get("datasheet_status", "not_found")
    if status != "found":
        _structured_log(
            trace_id, "ingest_skip",
            pn=pn, reason=f"datasheet_status={status}",
        )
        return None

    # Compute content hash
    if pdf_bytes:
        content_hash = compute_content_hash(pdf_bytes)
    elif pdf_path and Path(pdf_path).exists():
        content_hash = compute_content_hash(Path(pdf_path).read_bytes())
    else:
        content_hash = "no_content"

    # Determine version
    latest = get_latest_version(base_dir, pn)
    new_version = latest + 1

    record = DatasheetRecord(
        pn=pn,
        brand=brand,
        version=new_version,
        trace_id=trace_id,
        source_id=find_result.get("pdf_url", ""),
        source_tier=find_result.get("pdf_source_tier", "unknown"),
        content_hash=content_hash,
        ingested_at=_now(),
        pdf_path=pdf_path,
        pdf_url=find_result.get("pdf_url"),
        pn_confirmed=find_result.get("pn_confirmed_in_pdf", False),
        num_pages=find_result.get("num_pages", 0),
        specs=find_result.get("pdf_specs", {}),
        text_excerpt=find_result.get("pdf_text_excerpt", "")[:600],
        parse_method=find_result.get("parse_method", ""),
        supersedes=latest if latest > 0 else None,
    )

    try:
        write_version(base_dir, record.model_dump_json_safe(), trace_id=trace_id)
    except ValueError as exc:
        # Dedup — same content already ingested
        _structured_log(
            trace_id, "ingest_dedup",
            pn=pn, content_hash=content_hash, detail=str(exc),
        )
        return None
    except Exception as exc:
        _structured_log(
            trace_id, "ingest_error",
            error_class="TRANSIENT", severity="ERROR", retriable=True,
            pn=pn, error=str(exc),
        )
        raise

    _structured_log(
        trace_id, "ingest_success",
        pn=pn, version=new_version,
        spec_count=len(record.specs),
        content_hash=content_hash[:16],
    )
    return record


def ingest_from_evidence(
    evidence: dict,
    trace_id: str = "",
    base_dir: Path | None = None,
) -> DatasheetRecord | None:
    """
    Ingest from an existing evidence bundle's .datasheet block.

    For migration from legacy flat format to versioned storage.
    """
    if base_dir is None:
        base_dir = _DEFAULT_BASE

    ds = evidence.get("datasheet", {})
    if not ds or ds.get("datasheet_status") != "found":
        return None

    pn = evidence.get("entity_id", "")
    brand = evidence.get("brand", "unknown")
    if not pn:
        return None

    return ingest_from_find_datasheet(
        pn=pn,
        brand=brand,
        find_result=ds,
        pdf_path=ds.get("pdf_local_path"),
        trace_id=trace_id,
        base_dir=base_dir,
    )

"""
price_evidence_integrator.py -- bridges price manifests into canonical evidence bundles.

Reads a price manifest JSONL (produced by price_manual_scout.py), applies
price_admissibility.materialize_price_admissibility() to each row, and for
rows with offer_admissibility_status == "admissible_public_price" writes the
price data into the matching canonical evidence bundle.

Side-effects:
  - Overwrites matching evidence_<pn>.json files in evidence_dir (default: downloads/evidence/)
  - Writes an integration audit trace to downloads/audits/price_integration_<ts>/

This module does NOT:
  - fetch HTTP pages (purely deterministic)
  - modify card_status or review_reasons (left to local_catalog_refresh.py)
  - touch Core tables or Tier-1/Tier-2 files

DNA compliance:
  - trace_id: generated per run, stored in audit trace and each evidence bundle's refresh_trace
  - idempotency: running twice with same manifest produces same evidence bundles
    (price section overwrite is safe; refresh_trace records same trace_id)
  - error_class/severity/retriable: present on all error paths
  - no Core DML, no domain.reconciliation_* imports
  - deterministic: no live API, no unmocked time in tests (time injected via parameter)
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent

# Ensure scripts/ is on sys.path so sibling modules resolve correctly when this
# module is imported from outside the scripts/ directory (e.g. from tests/ or root).
_SCRIPTS_DIR = str(ROOT / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from price_admissibility import materialize_price_admissibility  # noqa: E402
DOWNLOADS = ROOT / "downloads"
DEFAULT_EVIDENCE_DIR = DOWNLOADS / "evidence"
DEFAULT_AUDIT_DIR = DOWNLOADS / "audits"

INTEGRATION_SCHEMA_VERSION = "price_evidence_integration_v1"

# Fields mapped from manifest row into the evidence bundle's price section.
# Explicit allowlist -- no extra fields to avoid schema drift.
_PRICE_FIELD_MAP = {
    "price_status": "price_status",
    "price_per_unit": "price_per_unit",
    "currency": "currency",
    "rub_price": "rub_price",
    "fx_rate_used": "fx_rate_used",
    "fx_provider": "fx_provider",
    "price_confidence": "price_confidence",
    "source_tier": "source_tier",
    "stock_status": "stock_status",
    "offer_unit_basis": "offer_unit_basis",
    "offer_qty": "offer_qty",
    "lead_time_detected": "lead_time_detected",
    "page_product_class": "page_product_class",
}

# Fields with explicit boolean coercion
_BOOL_FIELDS = {"lead_time_detected", "suffix_conflict", "category_mismatch", "brand_mismatch"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _evidence_path(evidence_dir: Path, pn: str) -> Optional[Path]:
    """Find evidence_<pn>.json in evidence_dir, case-insensitive fallback."""
    direct = evidence_dir / f"evidence_{pn}.json"
    if direct.exists():
        return direct
    upper_pn = pn.upper()
    for f in evidence_dir.glob("evidence_*.json"):
        stem = f.stem.removeprefix("evidence_")
        if stem.upper() == upper_pn:
            return f
    return None


def build_price_section(row: dict[str, Any]) -> dict[str, Any]:
    """
    Map manifest row fields into the evidence bundle price section schema.

    Uses an explicit allowlist (_PRICE_FIELD_MAP) to avoid schema drift.
    source_url is mapped from page_url (preferred) or source_url.
    source_type is mapped from source_type or source_role.
    Boolean fields are explicitly coerced.
    """
    price: dict[str, Any] = {}

    for src_key, dst_key in _PRICE_FIELD_MAP.items():
        v = row.get(src_key)
        if v is not None:
            price[dst_key] = _coerce_bool(v) if dst_key in _BOOL_FIELDS else v

    # source_url: prefer page_url (the verified URL from the scout run)
    price["source_url"] = str(row.get("page_url") or row.get("source_url") or "")

    # source_type: prefer source_type, fall back to source_role
    price["source_type"] = str(row.get("source_type") or row.get("source_role") or "")

    # Explicit boolean fields with safe defaults
    price["suffix_conflict"] = _coerce_bool(row.get("suffix_conflict", False))
    price["category_mismatch"] = _coerce_bool(row.get("category_mismatch", False))
    price["brand_mismatch"] = _coerce_bool(row.get("brand_mismatch", False))

    # Placeholder price stats for schema consistency with existing bundles
    price["price_median_clean"] = None
    price["price_min_clean"] = None
    price["price_max_clean"] = None
    price["price_sample_size"] = 1

    return price


def integrate_manifest(
    manifest_path: Path,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    audit_dir: Path = DEFAULT_AUDIT_DIR,
    trace_id: Optional[str] = None,
    dry_run: bool = False,
    _now_fn=None,
) -> dict[str, Any]:
    """
    Integrate a price manifest JSONL into canonical evidence bundles.

    For each row classified as offer_admissibility_status == "admissible_public_price":
      1. Find the matching evidence_<pn>.json bundle.
      2. Write the price section into bundle["price"].
      3. Update bundle["field_statuses_v2"]["price_status"] = "ACCEPTED".
      4. Update bundle["policy_decision_v2"]["price_status"] = "ACCEPTED".
      5. Record integration trace in bundle["refresh_trace"]["price_integration"].
      6. Write the updated bundle back to disk (unless dry_run=True).

    card_status is NOT updated here -- left to local_catalog_refresh.py which
    derives card_status from price.price_status on its next run.

    Args:
        manifest_path: Path to price manifest JSONL.
        evidence_dir: Directory containing evidence_<pn>.json files.
        audit_dir: Root dir for integration audit trace output.
        trace_id: Optional; generated as pi_<ts>_<hex> if not provided.
        dry_run: Compute but do not write to disk if True.
        _now_fn: Injectable time function for deterministic tests.

    Returns:
        Summary dict: trace_id, counts (integrated/skipped/error), per-row trace.

    Never raises -- all row-level errors are captured in the trace.
    """
    now_fn = _now_fn or _utc_now
    run_ts = now_fn()
    # Use now_fn for trace_id timestamp so the full call is deterministically testable
    ts_compact = run_ts[:19].replace("-", "").replace("T", "T").replace(":", "") + "Z"
    trace_id = trace_id or f"pi_{ts_compact}_{uuid.uuid4().hex[:6]}"

    # Load manifest rows
    rows: list[dict[str, Any]] = []
    for raw_line in manifest_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if line:
            rows.append(json.loads(line))

    logger.info(
        "price_evidence_integrator: start trace_id=%s manifest=%s rows=%d dry_run=%s",
        trace_id, manifest_path.name, len(rows), dry_run,
    )

    row_traces: list[dict[str, Any]] = []
    integrated_count = 0
    skipped_count = 0
    error_count = 0

    for row in rows:
        pn = str(row.get("part_number") or "").strip()
        if not pn:
            logger.warning(
                "price_evidence_integrator: missing_part_number "
                "error_class=TRANSIENT severity=WARNING retriable=false trace_id=%s",
                trace_id,
            )
            row_traces.append({"pn": "", "action": "skip", "reason": "missing_part_number"})
            skipped_count += 1
            continue

        try:
            admissibility = materialize_price_admissibility(row)
            offer_status = admissibility.get("offer_admissibility_status", "")

            if offer_status != "admissible_public_price":
                logger.info(
                    "price_evidence_integrator: skip pn=%s offer_status=%s trace_id=%s",
                    pn, offer_status, trace_id,
                )
                row_traces.append({
                    "pn": pn,
                    "action": "skip",
                    "reason": f"offer_status={offer_status}",
                    "price_per_unit": row.get("price_per_unit"),
                    "currency": row.get("currency"),
                })
                skipped_count += 1
                continue

            ev_path = _evidence_path(evidence_dir, pn)
            if ev_path is None:
                logger.warning(
                    "price_evidence_integrator: evidence_not_found pn=%s "
                    "error_class=TRANSIENT severity=WARNING retriable=true trace_id=%s",
                    pn, trace_id,
                )
                row_traces.append({
                    "pn": pn,
                    "action": "skip",
                    "reason": "evidence_not_found",
                    "evidence_dir": str(evidence_dir),
                })
                skipped_count += 1
                continue

            bundle = json.loads(ev_path.read_text(encoding="utf-8"))
            price_section = build_price_section(row)
            bundle["price"] = price_section

            # Update policy status fields
            fs = bundle.setdefault("field_statuses_v2", {})
            fs["price_status"] = "ACCEPTED"
            pd_v2 = bundle.setdefault("policy_decision_v2", {})
            pd_v2["price_status"] = "ACCEPTED"

            # Record integration trace inside the bundle
            rt = bundle.setdefault("refresh_trace", {})
            rt["price_integration"] = {
                "trace_id": trace_id,
                "integrated_at": run_ts,
                "source_manifest": manifest_path.name,
                "offer_admissibility_status": offer_status,
                "schema_version": INTEGRATION_SCHEMA_VERSION,
            }

            if not dry_run:
                ev_path.write_text(
                    json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8"
                )

            logger.info(
                "price_evidence_integrator: integrated pn=%s "
                "price_per_unit=%s currency=%s rub_price=%s dry_run=%s trace_id=%s",
                pn, row.get("price_per_unit"), row.get("currency"),
                row.get("rub_price"), dry_run, trace_id,
            )
            row_traces.append({
                "pn": pn,
                "action": "integrated",
                "offer_admissibility_status": offer_status,
                "price_per_unit": row.get("price_per_unit"),
                "currency": row.get("currency"),
                "rub_price": row.get("rub_price"),
                "source_url": row.get("page_url") or row.get("source_url"),
                "evidence_path": str(ev_path) if not dry_run else None,
            })
            integrated_count += 1

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "price_evidence_integrator: row_error pn=%s "
                "error_class=TRANSIENT severity=ERROR retriable=true error=%s trace_id=%s",
                pn, exc, trace_id,
            )
            row_traces.append({"pn": pn, "action": "error", "error": str(exc)})
            error_count += 1

    summary = {
        "schema_version": INTEGRATION_SCHEMA_VERSION,
        "trace_id": trace_id,
        "run_ts": run_ts,
        "manifest": str(manifest_path),
        "evidence_dir": str(evidence_dir),
        "dry_run": dry_run,
        "total_rows": len(rows),
        "integrated_count": integrated_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "rows": row_traces,
    }

    if not dry_run:
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = audit_dir / f"price_integration_{ts_str}"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "integration_trace.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    logger.info(
        "price_evidence_integrator: done trace_id=%s integrated=%d skipped=%d errors=%d",
        trace_id, integrated_count, skipped_count, error_count,
    )
    return summary


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Integrate price manifest into canonical evidence bundles."
    )
    parser.add_argument(
        "--manifest",
        default=str(DOWNLOADS / "scout_cache" / "price_manual_manifest.jsonl"),
        help="Path to price manifest JSONL",
    )
    parser.add_argument(
        "--evidence-dir",
        default=str(DEFAULT_EVIDENCE_DIR),
        help="Directory containing evidence_<pn>.json files",
    )
    parser.add_argument(
        "--audit-dir",
        default=str(DEFAULT_AUDIT_DIR),
        help="Root directory for audit traces",
    )
    parser.add_argument("--trace-id", default=None, help="Optional trace ID")
    parser.add_argument("--dry-run", action="store_true", help="Compute but do not write to disk")
    args = parser.parse_args()

    summary = integrate_manifest(
        manifest_path=Path(args.manifest),
        evidence_dir=Path(args.evidence_dir),
        audit_dir=Path(args.audit_dir),
        trace_id=args.trace_id,
        dry_run=args.dry_run,
    )
    print(f"[price_evidence_integrator] trace_id={summary['trace_id']}")
    print(f"  total={summary['total_rows']} integrated={summary['integrated_count']} "
          f"skipped={summary['skipped_count']} errors={summary['error_count']}")
    for row in summary["rows"]:
        flag = "OK" if row["action"] == "integrated" else "SKIP" if row["action"] == "skip" else "ERR"
        detail = row.get("reason") or (
            f"{row.get('price_per_unit')} {row.get('currency')} -> {row.get('rub_price')} RUB"
            if row["action"] == "integrated" else ""
        )
        print(f"  [{flag}] {row['pn']:20} {detail}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    main()

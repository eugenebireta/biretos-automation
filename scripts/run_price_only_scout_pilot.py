"""Bounded price-only scout pilot using prior admissible surfaces as seed candidates.

This runner intentionally avoids widening runtime scope:
- one brand only;
- bounded SKU slice (default 20);
- no photo or scene handling;
- seeded from prior admissible run evidence instead of requiring SerpAPI.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from deterministic_false_positive_controls import tighten_public_price_result
from photo_pipeline import BRAND, INPUT_FILE, step2b_extract_from_pages
from price_evidence_cache import build_cache_payload_from_run_dirs
from price_manual_scout import run as run_manual_price_scout
from price_source_surface_stability import build_source_surface_cache_payload_from_run_dirs


ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
AUDITS_DIR = DOWNLOADS / "audits"
QUEUE_SCHEMA_VERSION = "followup_queue_v2"
SCOUT_PRICE_ACTION_CODE = "scout_price"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_catalog_rows(input_file: Path) -> list[dict[str, str]]:
    df = pd.read_csv(input_file, sep="\t", encoding="utf-16", dtype=str).fillna("")
    rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        brand = str(row.get("Параметр: Бренд", "")).strip() or BRAND
        if brand.lower() != BRAND.lower():
            continue
        rows.append(
            {
                "brand": brand,
                "pn": str(row.get("Параметр: Партномер", "")).strip(),
                "name": str(row.get("Название товара или услуги", "")).strip(),
                "expected_category": str(row.get("Параметр: Тип товара", "")).strip(),
            }
        )
    return [row for row in rows if row["pn"]]


def discover_prior_run_dirs(audits_dir: Path) -> list[Path]:
    discovered = [
        path
        for path in sorted(audits_dir.glob("phase_a_v2_sanity_*"))
        if path.is_dir() and (path / "evidence").exists()
    ]
    if (DOWNLOADS / "evidence").exists():
        discovered.append(DOWNLOADS)
    return discovered


def _tier_rank(value: Any) -> int:
    normalized = str(value or "").strip().lower()
    if normalized == "official":
        return 3
    if normalized == "authorized":
        return 2
    if normalized == "industrial":
        return 1
    return 0


def make_candidate_from_cache_entry(
    pn: str,
    brand: str,
    entry: dict[str, Any],
    *,
    source_label: str,
) -> dict[str, Any] | None:
    source_url = str(entry.get("source_url") or "").strip()
    if not source_url:
        return None
    source_tier = str(entry.get("source_tier") or "").strip()
    return {
        "url": source_url,
        "snippet": f"{brand} {pn} seeded via {source_label}",
        "title": f"{brand} {pn}",
        "source_type": str(entry.get("source_type") or "other").strip() or "other",
        "source_tier": source_tier,
        "source_weight": 0.9 if source_label == "price_cache" else 0.7,
        "engine": source_label,
    }


def build_candidate_index_from_caches(
    *,
    price_cache_payload: dict[str, Any] | None,
    surface_cache_payload: dict[str, Any] | None,
    brand: str = BRAND,
) -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, dict[str, dict[str, Any]]] = {}
    payloads = (
        ("price_cache", price_cache_payload or {}),
        ("surface_cache", surface_cache_payload or {}),
    )
    for source_label, payload in payloads:
        for pn, entries in (payload.get("entries_by_pn") or {}).items():
            bucket = merged.setdefault(str(pn), {})
            for entry in entries:
                candidate = make_candidate_from_cache_entry(str(pn), brand, dict(entry), source_label=source_label)
                if candidate is None:
                    continue
                source_url = candidate["url"]
                current = bucket.get(source_url)
                if current is None or _tier_rank(candidate.get("source_tier")) > _tier_rank(current.get("source_tier")):
                    bucket[source_url] = candidate

    result: dict[str, list[dict[str, Any]]] = {}
    for pn, by_url in merged.items():
        result[pn] = sorted(
            by_url.values(),
            key=lambda item: (-_tier_rank(item.get("source_tier")), item.get("url", "")),
        )
    return result


def select_seeded_rows(
    rows: list[dict[str, str]],
    candidate_index: dict[str, list[dict[str, Any]]],
    *,
    limit: int,
) -> list[dict[str, str]]:
    seeded = [row for row in rows if candidate_index.get(row["pn"])]
    return seeded[:limit]


def load_queue_request(queue_path: Path | str) -> dict[str, Any]:
    rows = [
        json.loads(line)
        for line in Path(queue_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    requested_pns: list[str] = []
    skipped_action_counts: Counter[str] = Counter()
    snapshot_id = ""
    for row in rows:
        schema_version = str(row.get("queue_schema_version", "") or "").strip()
        if schema_version != QUEUE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported queue schema version: {schema_version or '<missing>'}"
            )
        action_code = str(row.get("action_code", "") or "").strip()
        if not action_code:
            raise ValueError("Queue row missing action_code")
        snapshot_id = snapshot_id or str(row.get("snapshot_id", "") or "").strip()
        pn = str(row.get("pn") or row.get("part_number") or "").strip()
        if not pn:
            raise ValueError("Queue row missing pn/part_number")
        if action_code == SCOUT_PRICE_ACTION_CODE:
            requested_pns.append(pn)
        else:
            skipped_action_counts[action_code] += 1
    return {
        "queue_path": str(queue_path),
        "queue_schema_version": QUEUE_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "requested_pns": requested_pns,
        "requested_count": len(requested_pns),
        "total_rows": len(rows),
        "skipped_action_counts": dict(skipped_action_counts),
    }


def select_queue_seeded_rows(
    *,
    queue_request: dict[str, Any],
    catalog_rows: list[dict[str, str]],
    candidate_index: dict[str, list[dict[str, Any]]],
    limit: int,
) -> list[dict[str, str]]:
    row_index = {row["pn"]: row for row in catalog_rows}
    seeded: list[dict[str, str]] = []
    for pn in queue_request.get("requested_pns", []):
        row = row_index.get(pn)
        if row is None or not candidate_index.get(pn):
            continue
        seeded.append(row)
        if len(seeded) >= limit:
            break
    return seeded


def materialize_price_result(
    row: dict[str, str],
    *,
    candidate_index: dict[str, list[dict[str, Any]]],
    price_cache_payload: dict[str, Any] | None,
    surface_cache_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    pn = row["pn"]
    candidates = list(candidate_index.get(pn, []))
    price = tighten_public_price_result(
        step2b_extract_from_pages(
            candidates,
            pn,
            row.get("brand") or BRAND,
            row.get("expected_category", ""),
            price_cache_payload=price_cache_payload,
            source_surface_cache_payload=surface_cache_payload,
        )
    )
    return {
        "pn": pn,
        "name": row.get("name", ""),
        "expected_category": row.get("expected_category", ""),
        "candidate_count": len(candidates),
        "candidate_urls": [candidate.get("url", "") for candidate in candidates],
        "seed_engines": sorted({str(candidate.get("engine", "")).strip() for candidate in candidates if candidate.get("engine")}),
        "price_status": price.get("price_status", "no_price_found"),
        "price_confidence": int(price.get("price_confidence") or 0),
        "source_url": price.get("source_url"),
        "source_tier": price.get("source_tier"),
        "source_type": price.get("source_type"),
        "price_source_seen": bool(price.get("price_source_seen")),
        "price_source_exact_product_lineage_confirmed": bool(price.get("price_source_exact_product_lineage_confirmed")),
        "price_source_lineage_reason_code": price.get("price_source_lineage_reason_code", ""),
        "price_source_surface_stable": bool(price.get("price_source_surface_stable")),
        "price_source_surface_conflict_detected": bool(price.get("price_source_surface_conflict_detected")),
        "price_source_surface_conflict_reason_code": price.get("price_source_surface_conflict_reason_code", ""),
        "cache_fallback_used": bool(price.get("cache_fallback_used")),
        "cache_source_run_id": price.get("cache_source_run_id", ""),
        "transient_failure_codes": list(price.get("transient_failure_codes", [])),
    }


def summarize_results(
    results: list[dict[str, Any]],
    *,
    requested_limit: int,
    selected_rows_count: int,
    prior_run_count: int,
) -> dict[str, Any]:
    status_counts = Counter(str(row.get("price_status") or "no_price_found") for row in results)
    exact_lineage_confirmed_count = sum(1 for row in results if row.get("price_source_exact_product_lineage_confirmed"))
    surface_conflict_count = sum(1 for row in results if row.get("price_source_surface_conflict_detected"))
    cache_fallback_used_count = sum(1 for row in results if row.get("cache_fallback_used"))
    transient_failure_row_count = sum(1 for row in results if row.get("transient_failure_codes"))
    fx_status_counts = Counter(str(row.get("fx_normalization_status") or "unknown") for row in results)
    fx_gap_count = sum(1 for row in results if row.get("fx_normalization_status") == "fx_gap")
    rows_with_price_signal = sum(
        1 for row in results if row.get("price_status") in {"public_price", "rfq_only", "hidden_price"}
    )

    return {
        "schema_version": "price_only_scout_pilot_summary_v1",
        "requested_limit": requested_limit,
        "selected_rows_count": selected_rows_count,
        "processed_rows_count": len(results),
        "prior_run_count": prior_run_count,
        "price_status_counts": dict(status_counts),
        "rows_with_price_signal": rows_with_price_signal,
        "exact_product_lineage_confirmed_count": exact_lineage_confirmed_count,
        "surface_conflict_count": surface_conflict_count,
        "cache_fallback_used_count": cache_fallback_used_count,
        "transient_failure_row_count": transient_failure_row_count,
        "fx_status_counts": dict(fx_status_counts),
        "fx_gap_count": fx_gap_count,
        "success_gates": {
            "requested_limit_satisfied": {
                "passed": selected_rows_count == requested_limit,
                "expected": requested_limit,
                "observed": selected_rows_count,
            },
            "every_selected_row_processed": {
                "passed": len(results) == selected_rows_count,
                "expected": selected_rows_count,
                "observed": len(results),
            },
            "zero_surface_conflicts": {
                "passed": surface_conflict_count == 0,
                "expected": 0,
                "observed": surface_conflict_count,
            },
        },
    }


def run(
    limit: int = 20,
    manual_seed_path: Path | None = None,
    queue_path: Path | None = None,
) -> dict[str, Any]:
    if manual_seed_path is not None and queue_path is not None:
        raise ValueError("manual_seed_path and queue_path are mutually exclusive")
    batch_root = AUDITS_DIR / f"price_only_scout_pilot_{utc_stamp()}"
    batch_root.mkdir(parents=True, exist_ok=True)
    prior_run_dirs = discover_prior_run_dirs(AUDITS_DIR)
    queue_request: dict[str, Any] | None = None

    if manual_seed_path is not None:
        manifest_path = batch_root / "manual_price_manifest.jsonl"
        manual_results = run_manual_price_scout(manual_seed_path, manifest_path, limit=limit)
        selected_rows = [
            {
                "brand": row.get("brand", BRAND),
                "pn": row["part_number"],
                "name": row.get("product_name", ""),
                "expected_category": row.get("expected_category", ""),
                "seed_candidate_count": 1,
            }
            for row in manual_results
        ]
        results = [
            {
                "pn": row["part_number"],
                "name": row.get("product_name", ""),
                "expected_category": row.get("expected_category", ""),
                "candidate_count": 1,
                "candidate_urls": [row.get("page_url", "")],
                "seed_engines": [row.get("source_provider", "codex_manual")],
                "price_status": row.get("price_status", "no_price_found"),
                "price_confidence": int(row.get("price_confidence") or 0),
                "source_url": row.get("page_url"),
                "source_tier": row.get("source_tier"),
                "source_type": row.get("source_type"),
                "price_source_seen": bool(row.get("price_source_seen")),
                "price_source_exact_product_lineage_confirmed": bool(row.get("price_source_exact_product_lineage_confirmed")),
                "price_source_lineage_reason_code": row.get("price_source_lineage_reason_code", ""),
                "price_source_surface_stable": bool(row.get("price_source_surface_stable")),
                "price_source_surface_conflict_detected": bool(row.get("price_source_surface_conflict_detected")),
                "price_source_surface_conflict_reason_code": row.get("price_source_surface_conflict_reason_code", ""),
                "cache_fallback_used": False,
                "cache_source_run_id": "",
                "transient_failure_codes": list(row.get("transient_failure_codes", [])),
                "manual_seed_used": True,
                "price_per_unit": row.get("price_per_unit"),
                "currency": row.get("currency"),
                "rub_price": row.get("rub_price"),
                "offer_qty": row.get("offer_qty"),
                "offer_unit_basis": row.get("offer_unit_basis"),
                "source_price_value": row.get("source_price_value"),
                "source_price_currency": row.get("source_price_currency"),
                "source_offer_qty": row.get("source_offer_qty"),
                "source_offer_unit_basis": row.get("source_offer_unit_basis"),
                "price_basis_note": row.get("price_basis_note", ""),
                "review_required": bool(row.get("review_required")),
                "fx_normalization_status": row.get("fx_normalization_status", "unknown"),
                "fx_gap_reason_code": row.get("fx_gap_reason_code", ""),
                "fx_provider": row.get("fx_provider"),
                "fx_rate_used": row.get("fx_rate_used"),
            }
            for row in manual_results
        ]
        results_path = batch_root / "price_only_results.jsonl"
        with open(results_path, "w", encoding="utf-8") as fh:
            for row in results:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        selected_path = batch_root / "selected_rows.jsonl"
        with open(selected_path, "w", encoding="utf-8") as fh:
            for row in selected_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    else:
        price_cache_payload = build_cache_payload_from_run_dirs(prior_run_dirs)
        surface_cache_payload = build_source_surface_cache_payload_from_run_dirs(prior_run_dirs)
        candidate_index = build_candidate_index_from_caches(
            price_cache_payload=price_cache_payload,
            surface_cache_payload=surface_cache_payload,
        )
        catalog_rows = load_catalog_rows(INPUT_FILE)
        if queue_path is not None:
            queue_request = load_queue_request(queue_path)
            selected_rows = select_queue_seeded_rows(
                queue_request=queue_request,
                catalog_rows=catalog_rows,
                candidate_index=candidate_index,
                limit=limit,
            )
        else:
            selected_rows = select_seeded_rows(catalog_rows, candidate_index, limit=limit)
        results = [
            materialize_price_result(
                row,
                candidate_index=candidate_index,
                price_cache_payload=price_cache_payload,
                surface_cache_payload=surface_cache_payload,
            )
            for row in selected_rows
        ]
        results_path = batch_root / "price_only_results.jsonl"
        with open(results_path, "w", encoding="utf-8") as fh:
            for row in results:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        selected_path = batch_root / "selected_rows.jsonl"
        with open(selected_path, "w", encoding="utf-8") as fh:
            for row in selected_rows:
                enriched = {
                    **row,
                    "seed_candidate_count": len(candidate_index.get(row["pn"], [])),
                }
                fh.write(json.dumps(enriched, ensure_ascii=False) + "\n")

    summary = summarize_results(
        results,
        requested_limit=limit,
        selected_rows_count=len(selected_rows),
        prior_run_count=len(prior_run_dirs),
    )
    summary.update(
        {
            "batch_root": str(batch_root),
            "results_path": str(results_path),
            "selected_rows_path": str(selected_path),
        }
    )
    if queue_request is not None:
        summary.update(
            {
                "queue_path": queue_request["queue_path"],
                "queue_schema_version": queue_request["queue_schema_version"],
                "queue_snapshot_id": queue_request["snapshot_id"],
                "queue_total_rows": queue_request["total_rows"],
                "queue_requested_count": queue_request["requested_count"],
                "queue_skipped_action_counts": queue_request["skipped_action_counts"],
            }
        )
    summary_path = batch_root / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded price-only scout pilot from prior admissible surfaces.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--manual-seed", default="", help="Optional JSONL of Codex-seeded manual price observations.")
    parser.add_argument("--queue", default="", help="Optional follow-up queue JSONL; only action_code=scout_price is processed.")
    args = parser.parse_args()
    if args.manual_seed and args.queue:
        parser.error("--manual-seed and --queue are mutually exclusive")

    summary = run(
        limit=args.limit,
        manual_seed_path=Path(args.manual_seed) if args.manual_seed else None,
        queue_path=Path(args.queue) if args.queue else None,
    )
    print(
        f"requested_limit={summary['requested_limit']} "
        f"selected={summary['selected_rows_count']} processed={summary['processed_rows_count']}"
    )
    print(f"price_status_counts={json.dumps(summary['price_status_counts'], ensure_ascii=False)}")
    print(f"surface_conflict_count={summary['surface_conflict_count']}")
    print(f"summary_path={Path(summary['batch_root']) / 'summary.json'}")


if __name__ == "__main__":
    main()

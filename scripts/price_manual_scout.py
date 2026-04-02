"""Manual price scout for Codex-seeded exact product pages.

This runner lets Codex or an operator provide structured price observations when
the LLM extraction step is unavailable. It still fetches the source page and
reuses deterministic lineage and surface-stability checks so the result remains
traceable and bounded.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from deterministic_false_positive_controls import tighten_public_price_result
from fx import convert_to_rub, fx_meta
from no_price_coverage import materialize_no_price_coverage
from photo_pipeline import BROWSER_HEADERS, BRAND
from price_lineage import materialize_pre_llm_price_lineage
from price_source_surface_stability import build_source_surface_cache_payload_from_run_dirs, materialize_source_surface_stability
from source_trust import get_source_role, is_denied
from trust import get_source_trust


ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
AUDITS_DIR = DOWNLOADS / "audits"
SCOUT_CACHE_DIR = DOWNLOADS / "scout_cache"
DEFAULT_SEED_FILE = SCOUT_CACHE_DIR / "price_manual_seed.jsonl"
DEFAULT_MANIFEST_FILE = SCOUT_CACHE_DIR / "price_manual_manifest.jsonl"

VALID_PRICE_STATUSES = {"public_price", "rfq_only", "hidden_price", "no_price_found"}


def _fx_status_for(amount: float | None, currency: str | None, rub_price: float | None) -> tuple[str, str]:
    if amount is None or not currency:
        return "not_attempted", ""
    if rub_price is None:
        return "fx_gap", "fx_rate_unavailable_for_currency"
    return "normalized", ""


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ".").strip())
    except Exception:
        return None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "y"}


def _derive_source_type(page_url: str, source_role: str) -> str:
    domain = (urlparse(page_url).netloc or "").lower().removeprefix("www.")
    if source_role == "manufacturer_proof":
        return "official"
    if source_role == "authorized_distributor":
        return "authorized_distributor"
    if source_role == "industrial_distributor":
        return "industrial_distributor"
    if domain.endswith(".ru"):
        return "ru_b2b"
    return "other"


def _normalize_source_role(page_url: str, source_role: str, trust: dict[str, Any]) -> str:
    normalized = str(source_role or "").strip() or "organic_discovery"
    if normalized != "organic_discovery":
        return normalized

    tier = str((trust or {}).get("tier") or "").strip().lower()
    if tier == "official":
        return "manufacturer_proof"
    if tier == "authorized":
        return "authorized_distributor"
    if tier == "industrial":
        return "industrial_distributor"
    if tier == "ru_b2b":
        return "industrial_distributor"

    domain = (urlparse(page_url).netloc or "").lower().removeprefix("www.")
    if domain.endswith(".ru"):
        return "industrial_distributor"
    return normalized


def discover_prior_run_dirs(audits_dir: Path) -> list[Path]:
    discovered = [
        path
        for path in sorted(audits_dir.glob("phase_a_v2_sanity_*"))
        if path.is_dir() and (path / "evidence").exists()
    ]
    if (DOWNLOADS / "evidence").exists():
        discovered.append(DOWNLOADS)
    return discovered


def load_seed_records(seed_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not seed_path.exists():
        return records
    for raw_line in seed_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            continue
        pn = str(payload.get("part_number", "")).strip()
        page_url = str(payload.get("page_url", "")).strip()
        price_status = str(payload.get("price_status", "")).strip()
        if not pn or not page_url or price_status not in VALID_PRICE_STATUSES:
            continue
        records.append(
            {
                "part_number": pn,
                "brand": str(payload.get("brand", BRAND)).strip() or BRAND,
                "product_name": str(payload.get("product_name", "")).strip(),
                "expected_category": str(payload.get("expected_category", "")).strip(),
                "page_url": page_url,
                "source_provider": str(payload.get("source_provider", "codex_manual")).strip() or "codex_manual",
                "price_status": price_status,
                "price_per_unit": _coerce_float(payload.get("price_per_unit")),
                "currency": str(payload.get("currency", "")).strip(),
                "offer_qty": int(payload.get("offer_qty", 1) or 1),
                "offer_unit_basis": str(payload.get("offer_unit_basis", "piece")).strip() or "piece",
                "stock_status": str(payload.get("stock_status", "unknown")).strip() or "unknown",
                "lead_time_detected": _coerce_bool(payload.get("lead_time_detected")),
                "quote_cta_url": str(payload.get("quote_cta_url", "")).strip(),
                "page_product_class": str(payload.get("page_product_class", "")).strip(),
                "category_mismatch": _coerce_bool(payload.get("category_mismatch")),
                "brand_mismatch": _coerce_bool(payload.get("brand_mismatch")),
                "price_confidence": int(payload.get("price_confidence", 95 if price_status == "public_price" else 80) or 0),
                "source_price_value": _coerce_float(payload.get("source_price_value")),
                "source_price_currency": str(payload.get("source_price_currency", payload.get("currency", ""))).strip(),
                "source_offer_qty": int(payload.get("source_offer_qty", payload.get("offer_qty", 1)) or 1),
                "source_offer_unit_basis": str(payload.get("source_offer_unit_basis", payload.get("offer_unit_basis", "piece"))).strip() or "piece",
                "price_basis_note": str(payload.get("price_basis_note", "")).strip(),
                "notes": str(payload.get("notes", "")).strip(),
            }
        )
    return records


def materialize_seed_record(
    record: dict[str, Any],
    *,
    surface_cache_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    page_url = record["page_url"]
    response = requests.get(page_url, headers=BROWSER_HEADERS, timeout=20)
    html = response.text if response.status_code == 200 else ""
    content_type = response.headers.get("Content-Type", "")

    trust = get_source_trust(page_url)
    source_role = get_source_role(page_url)
    if source_role == "organic_discovery" and trust.get("domain"):
        source_role = get_source_role(str(trust["domain"]))
    source_role = _normalize_source_role(page_url, source_role, trust)

    source_type = _derive_source_type(page_url, source_role)
    price_result: dict[str, Any] = {
        "price_usd": record.get("price_per_unit"),
        "currency": record.get("currency") or None,
        "source_url": page_url,
        "source_type": source_type,
        "source_tier": trust.get("tier", "unknown"),
        "source_engine": "manual_seed",
        "price_status": record["price_status"],
        "price_confidence": int(record.get("price_confidence") or 0),
        "stock_status": record.get("stock_status", "unknown"),
        "offer_unit_basis": record.get("offer_unit_basis", "piece"),
        "offer_qty": int(record.get("offer_qty", 1) or 1),
        "lead_time_detected": bool(record.get("lead_time_detected")),
        "quote_cta_url": record.get("quote_cta_url") or None,
        "suffix_conflict": False,
        "category_mismatch": bool(record.get("category_mismatch")),
        "page_product_class": record.get("page_product_class", ""),
        "brand_mismatch": bool(record.get("brand_mismatch")),
        "pn_exact_confirmed": False,
        "manual_seed_used": True,
        "manual_source_price_value": record.get("source_price_value"),
        "manual_source_price_currency": record.get("source_price_currency"),
        "manual_source_offer_qty": int(record.get("source_offer_qty", 1) or 1),
        "manual_source_offer_unit_basis": record.get("source_offer_unit_basis", "piece"),
        "manual_price_basis_note": record.get("price_basis_note", ""),
    }

    if price_result["price_usd"] is not None and price_result["currency"]:
        price_result["rub_price"] = convert_to_rub(price_result["price_usd"], price_result["currency"])
        fx = fx_meta(price_result["currency"])
        price_result["fx_rate_used"] = fx.get("fx_rate_stub")
        price_result["fx_provider"] = fx.get("fx_provider")
    fx_normalization_status, fx_gap_reason_code = _fx_status_for(
        price_result.get("price_usd"),
        price_result.get("currency"),
        price_result.get("rub_price"),
    )

    price_result = materialize_pre_llm_price_lineage(
        pn=record["part_number"],
        price_result=price_result,
        html=html,
        source_url=page_url,
        source_type=source_type,
        source_tier=trust.get("tier", "unknown"),
        source_engine="manual_seed",
        content_type=content_type,
        status_code=response.status_code,
    )
    price_result = materialize_no_price_coverage(price_result)
    price_result = tighten_public_price_result(price_result)
    price_result = materialize_source_surface_stability(
        price_result,
        pn=record["part_number"],
        surface_cache_payload=surface_cache_payload,
        observed_candidate={
            "url": page_url,
            "source_type": source_type,
            "engine": "manual_seed",
            "source_tier": trust.get("tier", "unknown"),
        },
    )

    review_required = any(
        (
            is_denied(page_url),
            response.status_code != 200,
            not price_result.get("price_source_exact_product_lineage_confirmed", False),
            bool(price_result.get("price_source_surface_conflict_detected", False)),
            str(price_result.get("price_status", "")) in {"ambiguous_offer", "category_mismatch_only"},
        )
    )

    return {
        "part_number": record["part_number"],
        "brand": record.get("brand", BRAND),
        "product_name": record.get("product_name", ""),
        "expected_category": record.get("expected_category", ""),
        "source_provider": record.get("source_provider", "codex_manual"),
        "page_url": page_url,
        "source_domain": (urlparse(page_url).netloc or "").lower().removeprefix("www."),
        "source_role": source_role,
        "source_type": source_type,
        "source_tier": trust.get("tier", "unknown"),
        "source_weight": trust.get("weight", 0.4),
        "http_status": response.status_code,
        "price_status": price_result.get("price_status", "no_price_found"),
        "price_per_unit": price_result.get("price_usd"),
        "currency": price_result.get("currency"),
        "rub_price": price_result.get("rub_price"),
        "fx_normalization_status": fx_normalization_status,
        "fx_gap_reason_code": fx_gap_reason_code,
        "fx_provider": price_result.get("fx_provider"),
        "fx_rate_used": price_result.get("fx_rate_used"),
        "offer_qty": price_result.get("offer_qty"),
        "offer_unit_basis": price_result.get("offer_unit_basis"),
        "stock_status": price_result.get("stock_status"),
        "lead_time_detected": bool(price_result.get("lead_time_detected")),
        "quote_cta_url": price_result.get("quote_cta_url"),
        "page_product_class": price_result.get("page_product_class", ""),
        "price_confidence": int(price_result.get("price_confidence") or 0),
        "price_source_seen": bool(price_result.get("price_source_seen")),
        "price_source_exact_product_lineage_confirmed": bool(price_result.get("price_source_exact_product_lineage_confirmed")),
        "price_source_lineage_reason_code": price_result.get("price_source_lineage_reason_code", ""),
        "price_source_surface_stable": bool(price_result.get("price_source_surface_stable")),
        "price_source_surface_conflict_detected": bool(price_result.get("price_source_surface_conflict_detected")),
        "price_source_surface_conflict_reason_code": price_result.get("price_source_surface_conflict_reason_code", ""),
        "source_price_value": record.get("source_price_value"),
        "source_price_currency": record.get("source_price_currency"),
        "source_offer_qty": record.get("source_offer_qty"),
        "source_offer_unit_basis": record.get("source_offer_unit_basis"),
        "price_basis_note": record.get("price_basis_note", ""),
        "notes": record.get("notes", ""),
        "transient_failure_codes": [],
        "cache_fallback_used": False,
        "review_required": review_required,
    }


def run(
    seed_path: Path,
    manifest_path: Path,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    records = load_seed_records(seed_path)
    if limit is not None:
        records = records[:limit]

    prior_run_dirs = discover_prior_run_dirs(AUDITS_DIR)
    surface_cache_payload = build_source_surface_cache_payload_from_run_dirs(prior_run_dirs)

    results = [
        materialize_seed_record(record, surface_cache_payload=surface_cache_payload)
        for record in records
    ]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize Codex-seeded manual price observations.")
    parser.add_argument("--seed", default=str(DEFAULT_SEED_FILE))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_FILE))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    results = run(Path(args.seed), Path(args.manifest), limit=args.limit)
    print(f"seed_records={len(results)} manifest={args.manifest}")
    for row in results:
        print(
            f"{row['part_number']}: status={row['price_status']} "
            f"price={row['price_per_unit']} {row['currency']} "
            f"tier={row['source_tier']} lineage={row['price_source_exact_product_lineage_confirmed']} "
            f"review={row['review_required']}"
        )


if __name__ == "__main__":
    main()

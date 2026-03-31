"""Controlled Phase A v2 sanity batch runner.

Runs a 25-SKU sanity batch against the existing photo_pipeline without opening
unrestricted full run or any live publish side-effects.

Outputs are isolated under downloads/audits/<batch_id>/.
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
INPUT_FILE = DOWNLOADS / "honeywell_insales_import.csv"
PRIOR_AUDIT_REPORT = DOWNLOADS / "export" / "audit_report.json"
PRIOR_EVIDENCE_DIR = DOWNLOADS / "evidence"

SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import photo_pipeline  # noqa: E402
from catalog_shadow_runtime import activate_shadow_runtime, get_shadow_runtime_summary, load_shadow_profile, reset_shadow_runtime  # noqa: E402
from price_evidence_cache import build_cache_payload_from_run_dirs  # noqa: E402
from price_source_surface_stability import build_source_surface_cache_payload_from_run_dirs  # noqa: E402
from source_trust import get_source_role  # noqa: E402


BATCH_SIZE = 25
PN_COL = "Параметр: Партномер"
NAME_COL = "Название товара или услуги"
PRICE_COL = "Цена продажи"
CATEGORY_COL = "Параметр: Тип товара"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip()).strip("_")


def _load_prior_audit_index() -> dict[str, dict]:
    if not PRIOR_AUDIT_REPORT.exists():
        return {}
    payload = json.loads(PRIOR_AUDIT_REPORT.read_text(encoding="utf-8"))
    return {row["pn"]: row for row in payload.get("per_sku", [])}


def _pn_tags(pn: str) -> set[str]:
    tags: set[str] = set()
    if re.fullmatch(r"\d+", pn):
        tags.add("numeric")
    if re.fullmatch(r"\d+\.\d+", pn):
        tags.add("dotted_numeric")
    if any(ch.isalpha() for ch in pn):
        tags.add("alphanumeric")
    if "-" in pn or "/" in pn:
        tags.add("suffix_case")
    if pn.startswith("0"):
        tags.add("leading_zero")
    return tags


def _family_tags(name: str) -> set[str]:
    lowered = name.lower()
    tags: set[str] = set()
    if "sperian" in lowered:
        tags.add("family_sperian")
    if "titan" in lowered:
        tags.add("family_titan")
    if "leightning" in lowered:
        tags.add("family_leightning")
    if "weidmuller" in lowered:
        tags.add("family_weidmuller")
    if "gasalert" in lowered:
        tags.add("family_gasalert")
    return tags


def _expected_pdf_friendly(name: str, category: str) -> bool:
    hay = f"{name} {category}".lower()
    return any(
        token in hay
        for token in (
            "датчик",
            "sensor",
            "reader",
            "module",
            "модуль",
            "считыватель",
            "aspirator",
            "вентиль",
            "thermost",
        )
    )


def build_manifest(df: pd.DataFrame, batch_size: int = BATCH_SIZE) -> tuple[dict[str, Any], pd.DataFrame]:
    """Select the deterministic sanity subset and materialize manifest metadata."""
    prior_index = _load_prior_audit_index()
    subset = df.head(batch_size).copy()
    batch_rows: list[dict[str, Any]] = []
    coverage = Counter()

    for row_number, (_, row) in enumerate(subset.iterrows(), start=1):
        pn = str(row[PN_COL]).strip()
        name = str(row[NAME_COL]).strip()
        price = str(row[PRICE_COL]).strip()
        category = str(row[CATEGORY_COL]).strip()
        tags = _pn_tags(pn) | _family_tags(name)

        prior = prior_index.get(pn, {})
        if prior.get("photo_verdict") == "REJECT":
            tags.add("weak_photo_case")
        if prior.get("price_status") == "rfq_only":
            tags.add("rfq_only_case")
        if prior.get("price_status") in {"no_price_found", ""}:
            tags.add("no_price_case")
        if prior.get("price_status") == "category_mismatch_only":
            tags.add("category_mismatch_case")
        if _expected_pdf_friendly(name, category):
            tags.add("expected_pdf_friendly")

        for tag in tags:
            coverage[tag] += 1

        batch_rows.append(
            {
                "row_number": row_number,
                "pn_primary": pn,
                "name": name,
                "expected_category": category,
                "our_price_raw": price,
                "case_tags": sorted(tags),
                "selection_reason": (
                    f"Deterministic head-{batch_size} subset from the 370-SKU input. "
                    f"Chosen because it matches the prior limited {batch_size}-SKU run "
                    "and covers numeric, dotted, alphanumeric, suffix, price, "
                    "and weak-photo patterns without opening broader run scope."
                ),
            }
        )

    coverage_gaps: list[str] = []
    if coverage["expected_pdf_friendly"] == 0:
        coverage_gaps.append("No expected PDF-friendly SKU in the selected subset.")
    if sum(1 for row in batch_rows if row["case_tags"] and "suffix_case" in row["case_tags"]) == 0:
        coverage_gaps.append("No suffix-case PN in the selected subset.")
    if not any(tag.startswith("family_") for row in batch_rows for tag in row["case_tags"]):
        coverage_gaps.append("No family/subbrand pattern surfaced in names.")
    coverage_gaps.append("Cross-pollination-positive cases are not guaranteed by this supplier slice.")
    coverage_gaps.append("Brand diversity is limited: supplier input is Honeywell-only.")

    manifest = {
        "batch_id": "",
        "created_at": _utc_now(),
        "source_input": str(INPUT_FILE),
        "selection_mode": f"deterministic_head_{len(batch_rows)}_prior_limited_run_alignment",
        "batch_size": len(batch_rows),
        "sku_rows": batch_rows,
        "coverage_by_case_type": dict(sorted(coverage.items())),
        "coverage_gaps": coverage_gaps,
    }
    return manifest, subset


def _copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copy2(src, dst)


def prepare_batch_root(batch_id: str) -> dict[str, Path]:
    batch_root = DOWNLOADS / "audits" / batch_id
    evidence_dir = batch_root / "evidence"
    export_dir = batch_root / "export"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "batch_root": batch_root,
        "input_file": batch_root / "input_sanity_batch.tsv",
        "manifest_file": batch_root / "batch_manifest.json",
        "report_file": batch_root / "sanity_audit_report.json",
        "sidecar_file": batch_root / "candidate_sidecar.jsonl",
        "stdout_first": batch_root / "run_first_stdout.log",
        "stdout_resume": batch_root / "run_resume_stdout.log",
        "checkpoint_file": batch_root / "checkpoint.json",
        "evidence_dir": evidence_dir,
        "export_dir": export_dir,
        "verdict_file": batch_root / "photo_verdict.json",
        "data_file": batch_root / "product_data.json",
        "gpt_cache_file": batch_root / "_gpt_cache.json",
        "artifact_cache_file": batch_root / "artifact_verdict_cache.json",
        "price_cache_file": batch_root / "price_evidence_cache.json",
        "source_surface_cache_file": batch_root / "price_source_surface_cache.json",
    }

    _copy_if_exists(DOWNLOADS / "_gpt_cache.json", paths["gpt_cache_file"])
    _copy_if_exists(DOWNLOADS / "artifact_verdict_cache.json", paths["artifact_cache_file"])
    if not paths["verdict_file"].exists():
        paths["verdict_file"].write_text("{}", encoding="utf-8")
    if not paths["data_file"].exists():
        paths["data_file"].write_text("{}", encoding="utf-8")
    if not paths["gpt_cache_file"].exists():
        paths["gpt_cache_file"].write_text("{}", encoding="utf-8")
    if not paths["artifact_cache_file"].exists():
        paths["artifact_cache_file"].write_text("{}", encoding="utf-8")
    return paths


def apply_pipeline_overrides(paths: dict[str, Path]) -> None:
    photo_pipeline.INPUT_FILE = paths["input_file"]
    photo_pipeline.VERDICT_FILE = paths["verdict_file"]
    photo_pipeline.DATA_FILE = paths["data_file"]
    photo_pipeline.GPT_CACHE = paths["gpt_cache_file"]
    photo_pipeline.ARTIFACT_CACHE_FILE = paths["artifact_cache_file"]
    photo_pipeline.PRICE_EVIDENCE_CACHE_FILE = paths["price_cache_file"]
    photo_pipeline.PRICE_SOURCE_SURFACE_CACHE_FILE = paths["source_surface_cache_file"]
    photo_pipeline.CHECKPOINT_FILE = paths["checkpoint_file"]
    photo_pipeline.EVIDENCE_DIR = paths["evidence_dir"]
    photo_pipeline.EXPORT_DIR = paths["export_dir"]
    photo_pipeline.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    photo_pipeline.EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def materialize_price_cache(paths: dict[str, Path], *, batch_id: str) -> dict[str, Any]:
    audits_dir = DOWNLOADS / "audits"
    prior_run_dirs = [
        path for path in sorted(audits_dir.glob("phase_a_v2_sanity_*"))
        if path.is_dir() and path.name != batch_id
    ]
    payload = build_cache_payload_from_run_dirs(prior_run_dirs)
    paths["price_cache_file"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def materialize_source_surface_cache(paths: dict[str, Path], *, batch_id: str) -> dict[str, Any]:
    audits_dir = DOWNLOADS / "audits"
    prior_run_dirs = [
        path for path in sorted(audits_dir.glob("phase_a_v2_sanity_*"))
        if path.is_dir() and path.name != batch_id
    ]
    payload = build_source_surface_cache_payload_from_run_dirs(prior_run_dirs)
    paths["source_surface_cache_file"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def run_pipeline_capture(
    paths: dict[str, Path],
    batch_size: int,
    log_path: Path,
    *,
    run_manifest_id: str,
) -> tuple[list[dict], str, dict[str, Any]]:
    reset_shadow_runtime()
    activate_shadow_runtime(run_manifest_id=run_manifest_id, planned_skus=batch_size)
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        results = photo_pipeline.run(
            limit=batch_size,
            show_results=False,
            datasheets=True,
            export=True,
            base_photo_url="",
        )
    stdout = buffer.getvalue()
    log_path.write_text(stdout, encoding="utf-8")
    run_meta = getattr(photo_pipeline, "LAST_RUN_META", {}) or {}
    return results, stdout, run_meta.get("shadow_runtime_summary", get_shadow_runtime_summary())


def load_bundles(paths: dict[str, Path], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    by_pn: dict[str, dict[str, Any]] = {}
    for file_path in sorted(paths["evidence_dir"].glob("evidence_*.json")):
        by_pn[json.loads(file_path.read_text(encoding="utf-8"))["pn"]] = json.loads(
            file_path.read_text(encoding="utf-8")
        )
    for row in manifest["sku_rows"]:
        bundle = by_pn.get(row["pn_primary"])
        if bundle is not None:
            bundles.append(bundle)
    return bundles


def _extract_url(raw: str) -> str:
    if not raw:
        return ""
    match = re.search(r"https?://\S+", raw)
    return match.group(0) if match else ""


def _source_domain_from_url(url: str) -> str:
    if not url:
        return ""
    return (urlparse(url).netloc or "").lower().removeprefix("www.")


def _parse_legacy_export_summary(stdout_text: str) -> dict[str, int]:
    match = re.search(
        r"EXPORT:\s+AUTO_PUBLISH=(\d+)\s+REVIEW_REQUIRED=(\d+)\s+DRAFT_ONLY=(\d+)",
        stdout_text,
    )
    if not match:
        return {}
    return {
        "AUTO_PUBLISH": int(match.group(1)),
        "REVIEW_REQUIRED": int(match.group(2)),
        "DRAFT_ONLY": int(match.group(3)),
    }


def build_status_distributions(
    bundles: list[dict[str, Any]],
    *,
    first_stdout: str,
    resume_stdout: str,
) -> dict[str, Any]:
    legacy_bundle = Counter(bundle["card_status"] for bundle in bundles)
    v2_bundle = Counter(bundle["policy_decision_v2"]["card_status"] for bundle in bundles)
    legacy_first_stdout = _parse_legacy_export_summary(first_stdout)
    legacy_resume_stdout = _parse_legacy_export_summary(resume_stdout)
    return {
        "authoritative_v2_source": "policy_decision_v2.card_status",
        "legacy_source": "bundle.card_status and legacy export stdout",
        "legacy_bundle_distribution": dict(sorted(legacy_bundle.items())),
        "legacy_first_stdout_distribution": legacy_first_stdout,
        "legacy_resume_stdout_distribution": legacy_resume_stdout,
        "v2_authoritative_distribution": dict(sorted(v2_bundle.items())),
        "consistency_checks": {
            "legacy_bundle_matches_first_stdout": dict(sorted(legacy_bundle.items())) == legacy_first_stdout,
            "legacy_bundle_matches_resume_stdout": dict(sorted(legacy_bundle.items())) == legacy_resume_stdout,
            "legacy_matches_v2": dict(sorted(legacy_bundle.items())) == dict(sorted(v2_bundle.items())),
        },
    }


def _sidecar_row(
    *,
    bundle: dict[str, Any],
    candidate_id: str,
    field_type: str,
    source_role: str,
    source_url: str,
    publishable: bool,
    rejection_reason: str | None,
    run_manifest_id: str,
    bundle_ref: str,
    decision_ref: str,
) -> dict[str, Any]:
    return {
        "schema_version": "candidate_sidecar_schema_v1",
        "run_manifest_id": run_manifest_id,
        "bundle_ref": bundle_ref,
        "decision_ref": decision_ref,
        "pn_primary": bundle["pn"],
        "pn": bundle["pn"],
        "candidate_id": candidate_id,
        "field_type": field_type,
        "source_role": source_role,
        "publishable_candidate": publishable,
        "rejection_reason": rejection_reason,
        "source_url": source_url,
        "source_domain": _source_domain_from_url(source_url),
        "dedupe_key": f"sanity:{bundle['pn']}:{field_type}",
        "field_status": bundle["field_statuses_v2"].get(f"{field_type}_status", ""),
        "card_status": bundle["policy_decision_v2"]["card_status"],
    }


def build_sidecar_rows(bundles: list[dict[str, Any]], batch_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bundle in bundles:
        pn = bundle["pn"]
        decision = bundle["policy_decision_v2"]
        bundle_ref = f"evidence_{_slugify(pn)}.json"
        decision_ref = decision["decision_id"]

        title_status = bundle["field_statuses_v2"]["title_status"]
        rows.append(
            _sidecar_row(
                bundle=bundle,
                candidate_id=f"cand_title_{pn}",
                field_type="title",
                source_role="raw_input",
                source_url=f"input://sanity_batch/{pn}",
                publishable=title_status == "ACCEPTED",
                rejection_reason=None if title_status == "ACCEPTED" else title_status,
                run_manifest_id=batch_id,
                bundle_ref=bundle_ref,
                decision_ref=decision_ref,
            )
        )

        photo_source = bundle.get("photo", {}).get("source", "")
        photo_url = _extract_url(photo_source)
        photo_role = get_source_role(photo_url) if photo_url else "organic_discovery"
        image_status = bundle["field_statuses_v2"]["image_status"]
        rows.append(
            _sidecar_row(
                bundle=bundle,
                candidate_id=f"cand_image_{pn}",
                field_type="image",
                source_role=photo_role,
                source_url=photo_url or photo_source,
                publishable=image_status == "ACCEPTED",
                rejection_reason=None if image_status == "ACCEPTED" else image_status,
                run_manifest_id=batch_id,
                bundle_ref=bundle_ref,
                decision_ref=decision_ref,
            )
        )

        price_url = bundle.get("price", {}).get("source_url") or ""
        if not price_url:
            price_url = bundle.get("price", {}).get("price_source_url") or ""
        price_role = get_source_role(price_url) if price_url else "organic_discovery"
        price_status = bundle["field_statuses_v2"]["price_status"]
        price_row = _sidecar_row(
            bundle=bundle,
            candidate_id=f"cand_price_{pn}",
            field_type="price",
            source_role=price_role,
            source_url=price_url,
            publishable=price_status == "ACCEPTED",
            rejection_reason=None if price_status == "ACCEPTED" else price_status,
            run_manifest_id=batch_id,
            bundle_ref=bundle_ref,
            decision_ref=decision_ref,
        )
        price_row.update(
            {
                "raw_price_status": bundle.get("price", {}).get("price_status", ""),
                "source_tier": bundle.get("price", {}).get("price_source_tier") or bundle.get("price", {}).get("source_tier"),
                "source_type": bundle.get("price", {}).get("price_source_type") or bundle.get("price", {}).get("source_type"),
                "price_source_seen": bool(bundle.get("price", {}).get("price_source_seen")),
                "price_source_lineage_confirmed": bool(bundle.get("price", {}).get("price_source_lineage_confirmed")),
                "price_source_exact_product_lineage_confirmed": bool(bundle.get("price", {}).get("price_source_exact_product_lineage_confirmed")),
                "price_source_lineage_reason_code": bundle.get("price", {}).get("price_source_lineage_reason_code", ""),
                "price_source_admissible_replacement_confirmed": bool(bundle.get("price", {}).get("price_source_admissible_replacement_confirmed")),
                "price_source_terminal_weak_lineage": bool(bundle.get("price", {}).get("price_source_terminal_weak_lineage")),
                "price_source_replacement_reason_code": bundle.get("price", {}).get("price_source_replacement_reason_code", ""),
                "price_source_surface_stable": bool(bundle.get("price", {}).get("price_source_surface_stable")),
                "price_source_surface_seen_current_run": bool(bundle.get("price", {}).get("price_source_surface_seen_current_run")),
                "price_source_surface_preserved_from_prior_run": bool(bundle.get("price", {}).get("price_source_surface_preserved_from_prior_run")),
                "price_source_surface_drop_detected": bool(bundle.get("price", {}).get("price_source_surface_drop_detected")),
                "price_source_surface_conflict_detected": bool(bundle.get("price", {}).get("price_source_surface_conflict_detected")),
                "price_source_surface_preservation_reason_code": bundle.get("price", {}).get("price_source_surface_preservation_reason_code", ""),
                "price_source_surface_drop_reason_code": bundle.get("price", {}).get("price_source_surface_drop_reason_code", ""),
                "price_source_surface_conflict_reason_code": bundle.get("price", {}).get("price_source_surface_conflict_reason_code", ""),
                "price_source_surface_preserved_source_run_id": bundle.get("price", {}).get("price_source_surface_preserved_source_run_id", ""),
                "price_source_surface_preserved_bundle_ref": bundle.get("price", {}).get("price_source_surface_preserved_bundle_ref", ""),
                "price_exact_product_page": bool(bundle.get("price", {}).get("price_exact_product_page")),
                "price_quote_required": bool(bundle.get("price", {}).get("price_quote_required")),
                "price_no_price_reason_code": bundle.get("price", {}).get("price_no_price_reason_code", ""),
                "price_reviewable_no_price_candidate": bool(bundle.get("price", {}).get("price_reviewable_no_price_candidate")),
            }
        )
        rows.append(price_row)

        pdf_url = bundle.get("datasheet", {}).get("pdf_url") or ""
        pdf_role = get_source_role(pdf_url) if pdf_url else "official_pdf_proof"
        pdf_status = bundle["field_statuses_v2"]["pdf_status"]
        rows.append(
            _sidecar_row(
                bundle=bundle,
                candidate_id=f"cand_pdf_{pn}",
                field_type="pdf",
                source_role=pdf_role,
                source_url=pdf_url,
                publishable=pdf_status == "ACCEPTED",
                rejection_reason=None if pdf_status == "ACCEPTED" else pdf_status,
                run_manifest_id=batch_id,
                bundle_ref=bundle_ref,
                decision_ref=decision_ref,
            )
        )
    return rows


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def build_metrics(
    bundles: list[dict[str, Any]],
    *,
    checkpoint_skip_count: int,
    batch_size: int,
) -> dict[str, Any]:
    total = len(bundles)
    card_counter = Counter(bundle["policy_decision_v2"]["card_status"] for bundle in bundles)
    review_bucket_counter = Counter()
    reason_counter = Counter()
    field_status_counter: dict[str, Counter] = {
        field: Counter(bundle["field_statuses_v2"][f"{field}_status"] for bundle in bundles)
        for field in ("title", "image", "price", "pdf")
    }

    false_keep_numeric_pn = []
    false_public_price = []
    ambiguous_cases = []
    critical_policy_surprises = []
    family_photo_count = 0
    identity_conflict_count = 0
    category_mismatch_count = 0
    cross_pollination_count = 0
    no_price_found_count = 0
    keep_count = 0
    usable_price_count = 0
    image_exact_proxy_numerator = 0
    image_exact_proxy_denominator = 0
    price_exact_proxy_numerator = 0
    price_exact_proxy_denominator = 0
    non_accepted_field_statuses = 0
    cache_fallback_reuse_pns: list[str] = []
    explicit_no_price_coverage_pns: list[str] = []
    exact_product_lineage_confirmed_pns: list[str] = []
    admissible_source_replacement_confirmed_pns: list[str] = []
    terminal_weak_lineage_pns: list[str] = []
    reviewable_no_price_candidate_pns: list[str] = []
    remaining_no_price_family_pns: list[str] = []
    source_surface_preserved_pns: list[str] = []
    source_surface_drop_detected_pns: list[str] = []
    source_surface_conflict_pns: list[str] = []
    remaining_ambiguous_tail_pns: list[str] = []

    for bundle in bundles:
        pn = bundle["pn"]
        decision = bundle["policy_decision_v2"]
        tags = _pn_tags(pn)
        photo = bundle.get("photo", {})
        price = bundle.get("price", {})
        reasons_v2 = decision.get("review_reasons", [])

        if photo.get("verdict") == "KEEP":
            keep_count += 1
            image_exact_proxy_denominator += 1
            if bundle["field_statuses_v2"]["image_status"] == "ACCEPTED":
                image_exact_proxy_numerator += 1

        if price.get("price_status") in {"no_price_found", "hidden_price", ""}:
            no_price_found_count += 1
            if price.get("price_source_seen") or price.get("price_source_lineage_confirmed"):
                explicit_no_price_coverage_pns.append(pn)
            if price.get("price_source_exact_product_lineage_confirmed"):
                exact_product_lineage_confirmed_pns.append(pn)
            if price.get("price_source_admissible_replacement_confirmed"):
                admissible_source_replacement_confirmed_pns.append(pn)
            if price.get("price_source_terminal_weak_lineage"):
                terminal_weak_lineage_pns.append(pn)
            if price.get("price_reviewable_no_price_candidate"):
                reviewable_no_price_candidate_pns.append(pn)
            if price.get("price_source_surface_preserved_from_prior_run"):
                source_surface_preserved_pns.append(pn)
            if price.get("price_source_surface_drop_detected"):
                source_surface_drop_detected_pns.append(pn)
            if price.get("price_source_surface_conflict_detected"):
                source_surface_conflict_pns.append(pn)
        if price.get("category_mismatch"):
            category_mismatch_count += 1

        if price.get("price_status") in {"public_price", "rfq_only"}:
            price_exact_proxy_denominator += 1
            if bundle["field_statuses_v2"]["price_status"] == "ACCEPTED":
                price_exact_proxy_numerator += 1
                usable_price_count += 1
            elif price.get("price_status") == "public_price":
                false_public_price.append(pn)
        if price.get("cache_fallback_used"):
            cache_fallback_reuse_pns.append(pn)
        if (
            decision["card_status"] == "DRAFT_ONLY"
            and any(
                reason.get("reason_code") in {"NO_PRICE_EVIDENCE", "TERMINAL_WEAK_NO_PRICE_LINEAGE"}
                for reason in reasons_v2
            )
        ):
            remaining_no_price_family_pns.append(pn)
            if not price.get("price_source_terminal_weak_lineage") and not price.get("price_reviewable_no_price_candidate"):
                remaining_ambiguous_tail_pns.append(pn)

        for field_name, status in bundle["field_statuses_v2"].items():
            if status != "ACCEPTED":
                non_accepted_field_statuses += 1

        for reason in reasons_v2:
            reason_counter[reason["reason_code"]] += 1
            review_bucket_counter[reason["bucket"]] += 1
            if reason["bucket"] == "FAMILY_PHOTO_REVIEW":
                family_photo_count += 1
            if reason["bucket"] == "IDENTITY_CONFLICT":
                identity_conflict_count += 1
            if reason["bucket"] == "CROSS_POLLINATION_REVIEW":
                cross_pollination_count += 1

        if (
            tags & {"numeric", "dotted_numeric", "leading_zero"}
            and photo.get("verdict") == "KEEP"
            and decision["card_status"] != "AUTO_PUBLISH"
        ):
            false_keep_numeric_pn.append(pn)

        ambiguous_cases.append(
            {
                "pn_primary": pn,
                "card_status": decision["card_status"],
                "review_reason_count": len(reasons_v2),
                "review_buckets": decision.get("review_buckets", []),
            }
        )

        if decision["card_status"] == "AUTO_PUBLISH" and reasons_v2:
            critical_policy_surprises.append(
                {
                    "pn_primary": pn,
                    "issue": "AUTO_PUBLISH emitted replayable review reasons",
                    "review_reasons": reasons_v2,
                }
            )
        if (
            decision["card_status"] == "AUTO_PUBLISH"
            and bundle["field_statuses_v2"]["price_status"] != "ACCEPTED"
        ):
            critical_policy_surprises.append(
                {
                    "pn_primary": pn,
                    "issue": "AUTO_PUBLISH with non-accepted price field status",
                    "price_status": bundle["field_statuses_v2"]["price_status"],
                }
            )

    ambiguous_cases = sorted(
        ambiguous_cases,
        key=lambda item: (-item["review_reason_count"], item["pn_primary"]),
    )[:10]

    return {
        "batch_size": total,
        "false_keep_numeric_pn": {
            "count": len(false_keep_numeric_pn),
            "pn_list": false_keep_numeric_pn,
            "definition": "Numeric/dotted/leading-zero PN cases with photo verdict KEEP but non-AUTO_PUBLISH card outcome.",
        },
        "false_public_price_count": {
            "count": len(false_public_price),
            "pn_list": false_public_price,
            "definition": "Bundles with raw public_price but non-ACCEPTED v2 price field status.",
        },
        "safe_cache_fallback_reuse_count": {
            "count": len(cache_fallback_reuse_pns),
            "pn_list": cache_fallback_reuse_pns,
            "definition": "SKUs where transient deterministic price extraction failure reused prior admissible exact-product price evidence from bounded-run cache.",
        },
        "explicit_no_price_coverage_count": {
            "count": len(explicit_no_price_coverage_pns),
            "pn_list": explicit_no_price_coverage_pns,
            "definition": "No-price/hidden-price bundles where deterministic upstream source or page lineage was still materialized explicitly.",
        },
        "exact_product_lineage_confirmed_count": {
            "count": len(exact_product_lineage_confirmed_pns),
            "pn_list": exact_product_lineage_confirmed_pns,
            "definition": "No-price/source-seen bundles where pre-LLM exact-product lineage was confirmed deterministically from structured page evidence.",
        },
        "admissible_source_replacement_confirmed_count": {
            "count": len(admissible_source_replacement_confirmed_pns),
            "pn_list": admissible_source_replacement_confirmed_pns,
            "definition": "Weak exact-lineage no-price bundles where a higher-tier admissible exact-product replacement source was confirmed deterministically.",
        },
        "terminal_weak_lineage_count": {
            "count": len(terminal_weak_lineage_pns),
            "pn_list": terminal_weak_lineage_pns,
            "definition": "Weak exact-lineage no-price bundles with no admissible replacement confirmed in the bounded candidate surface.",
        },
        "source_surface_preserved_count": {
            "count": len(source_surface_preserved_pns),
            "pn_list": source_surface_preserved_pns,
            "definition": "Bundles where compatible no-price source surface was preserved explicitly from a prior bounded run because the current run dropped it.",
        },
        "source_surface_drop_detected_count": {
            "count": len(source_surface_drop_detected_pns),
            "pn_list": source_surface_drop_detected_pns,
            "definition": "Bundles where current-run no-price source surface dropped relative to compatible prior bounded evidence.",
        },
        "source_surface_conflict_count": {
            "count": len(source_surface_conflict_pns),
            "pn_list": source_surface_conflict_pns,
            "definition": "Bundles where current-run no-price source surface conflicts with compatible prior bounded evidence and was not preserved silently.",
        },
        "reviewable_no_price_candidate_count": {
            "count": len(reviewable_no_price_candidate_pns),
            "pn_list": reviewable_no_price_candidate_pns,
            "definition": "No-price exact-product pages with clean admissible lineage that may be considered for future deterministic review-routing.",
        },
        "remaining_no_price_family_count": {
            "count": len(remaining_no_price_family_pns),
            "pn_list": remaining_no_price_family_pns,
            "definition": "DRAFT_ONLY bundles still blocked by terminal or generic no-price evidence failure on the authoritative v2 path.",
        },
        "remaining_ambiguous_tail_count": {
            "count": len(remaining_ambiguous_tail_pns),
            "pn_list": remaining_ambiguous_tail_pns,
            "definition": "DRAFT_ONLY no-price bundles that are neither terminal weak lineage nor reviewable no-price candidates after the current deterministic classification pass.",
        },
        "photo_keep_rate": round(keep_count / total, 4) if total else 0.0,
        "usable_price_rate": round(usable_price_count / total, 4) if total else 0.0,
        "review_required_rate": round(card_counter["REVIEW_REQUIRED"] / total, 4) if total else 0.0,
        "no_price_found_rate": round(no_price_found_count / total, 4) if total else 0.0,
        "category_mismatch_count": category_mismatch_count,
        "cross_pollination_count": cross_pollination_count,
        "checkpoint_resume_ok": checkpoint_skip_count == batch_size,
        "exact_photo_precision": round(
            image_exact_proxy_numerator / image_exact_proxy_denominator, 4
        ) if image_exact_proxy_denominator else None,
        "exact_price_precision": round(
            price_exact_proxy_numerator / price_exact_proxy_denominator, 4
        ) if price_exact_proxy_denominator else None,
        "identity_conflict_rate": round(identity_conflict_count / total, 4) if total else 0.0,
        "family_photo_used_rate": round(family_photo_count / total, 4) if total else 0.0,
        "field_status_failure_rate": round(
            non_accepted_field_statuses / (total * 4), 4
        ) if total else 0.0,
        "card_status_distribution": dict(sorted(card_counter.items())),
        "field_status_distribution": {
            field: dict(sorted(counter.items()))
            for field, counter in field_status_counter.items()
        },
        "review_bucket_distribution": dict(sorted(review_bucket_counter.items())),
        "top_failure_modes": reason_counter.most_common(10),
        "top_ambiguous_cases": ambiguous_cases,
        "critical_policy_surprises": critical_policy_surprises,
    }


def build_example_outcomes(bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for bundle in bundles[:10]:
        decision = bundle["policy_decision_v2"]
        explanation_parts = [
            f"card rule {decision['policy_rule_id']}",
            f"identity={decision['identity_level']}",
            f"image={decision['image_status']}",
            f"price={decision['price_status']}",
            f"pdf={decision['pdf_status']}",
        ]
        if decision.get("review_reasons"):
            explanation_parts.append(
                "reasons=" + ",".join(reason["reason_code"] for reason in decision["review_reasons"])
            )
        examples.append(
            {
                "pn_primary": bundle["pn"],
                "card_status": decision["card_status"],
                "title_status": decision["title_status"],
                "image_status": decision["image_status"],
                "price_status": decision["price_status"],
                "pdf_status": decision["pdf_status"],
                "review_reasons": decision["review_reasons"],
                "short_explanation": "; ".join(explanation_parts),
            }
        )
    return examples


def build_dual_status_examples(bundles: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for bundle in bundles[:limit]:
        decision = bundle["policy_decision_v2"]
        examples.append(
            {
                "pn_primary": bundle["pn"],
                "legacy_card_status": bundle["card_status"],
                "v2_card_status": decision["card_status"],
                "title_status": decision["title_status"],
                "image_status": decision["image_status"],
                "price_status": decision["price_status"],
                "pdf_status": decision["pdf_status"],
                "v2_status_source_path": f"evidence_{_slugify(bundle['pn'])}.json::policy_decision_v2.card_status",
                "review_reasons": decision["review_reasons"],
            }
        )
    return examples


def build_report(
    *,
    manifest: dict[str, Any],
    paths: dict[str, Path],
    bundles: list[dict[str, Any]],
    sidecar_rows: list[dict[str, Any]],
    first_stdout: str,
    resume_stdout: str,
    first_shadow_summary: dict[str, Any],
    resume_shadow_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    checkpoint_skip_count = resume_stdout.count("CHECKPOINT (skip)")
    metrics = build_metrics(
        bundles,
        checkpoint_skip_count=checkpoint_skip_count,
        batch_size=manifest["batch_size"],
    )
    status_distributions = build_status_distributions(
        bundles,
        first_stdout=first_stdout,
        resume_stdout=resume_stdout,
    )

    produced_artifacts = [
        str(paths["manifest_file"]),
        str(paths["report_file"]),
        str(paths["sidecar_file"]),
        str(paths["stdout_first"]),
        str(paths["stdout_resume"]),
        str(paths["checkpoint_file"]),
        *[str(path) for path in sorted(paths["evidence_dir"].glob("evidence_*.json"))],
        *[str(path) for path in sorted(paths["export_dir"].glob("*"))],
    ]
    if "price_cache_file" in paths:
        produced_artifacts.insert(6, str(paths["price_cache_file"]))
    if "source_surface_cache_file" in paths:
        produced_artifacts.insert(7, str(paths["source_surface_cache_file"]))

    report = {
        "batch_id": manifest["batch_id"],
        "created_at": _utc_now(),
        "manifest_summary": {
            "batch_size": manifest["batch_size"],
            "selection_mode": manifest["selection_mode"],
            "coverage_by_case_type": manifest["coverage_by_case_type"],
            "coverage_gaps": manifest["coverage_gaps"],
        },
        "produced_artifacts": produced_artifacts,
        "metrics": metrics,
        "status_distributions": status_distributions,
        "example_sku_outcomes": build_example_outcomes(bundles),
        "dual_status_examples": build_dual_status_examples(bundles),
        "resume_evidence": {
            "checkpoint_entries": len(json.loads(paths["checkpoint_file"].read_text(encoding="utf-8"))),
            "resume_skip_count": checkpoint_skip_count,
            "checkpoint_resume_ok": metrics["checkpoint_resume_ok"],
            "resume_skipped_due_to_early_stop": bool(first_shadow_summary.get("early_stop")),
        },
        "shadow_run_summary": {
            "first_run": first_shadow_summary,
            "resume_run": resume_shadow_summary,
        },
        "run_logs": {
            "first_run_log": str(paths["stdout_first"]),
            "resume_run_log": str(paths["stdout_resume"]),
            "first_run_tail": first_stdout.splitlines()[-20:],
            "resume_run_tail": resume_stdout.splitlines()[-20:],
        },
        "explicit_false_positives": {
            "false_keep_numeric_pn": metrics["false_keep_numeric_pn"]["pn_list"],
            "false_public_price": metrics["false_public_price_count"]["pn_list"],
        },
        "critical_policy_surprises": metrics["critical_policy_surprises"],
        "broader_controlled_run_assessment": {
            "ready": "NO",
            "blocking_issues": [],
            "non_blocking_issues": [],
        },
    }

    if metrics["false_public_price_count"]["count"] > 0:
        report["broader_controlled_run_assessment"]["blocking_issues"].append(
            "False public-price signals remain in the sanity slice."
        )
    if metrics["false_keep_numeric_pn"]["count"] > 0:
        report["broader_controlled_run_assessment"]["blocking_issues"].append(
            "Numeric/dotted PN KEEP outcomes still require tighter false-positive controls."
        )
    if metrics["card_status_distribution"].get("DRAFT_ONLY", 0) > metrics["batch_size"] * 0.3:
        report["broader_controlled_run_assessment"]["blocking_issues"].append(
            "DRAFT_ONLY share is still high for a broader controlled run."
        )
    if metrics["review_bucket_distribution"].get("PDF_CONFLICT", 0) > 0:
        report["broader_controlled_run_assessment"]["non_blocking_issues"].append(
            "PDF coverage remains incomplete and needs better datasheet hit-rate before scaling."
        )
    if metrics["review_bucket_distribution"].get("MISSING_MINIMUM_EVIDENCE", 0) > 0:
        report["broader_controlled_run_assessment"]["non_blocking_issues"].append(
            "Missing-evidence review load is still material."
        )
    if not report["broader_controlled_run_assessment"]["blocking_issues"]:
        report["broader_controlled_run_assessment"]["ready"] = "YES WITH FIXES"

    return report


def main() -> None:
    shadow_profile = load_shadow_profile()
    bounded_batch_size = min(BATCH_SIZE, int(shadow_profile["limits"]["MAX_SHADOW_SKUS"]))
    batch_id = f"phase_a_v2_sanity_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    df = pd.read_csv(INPUT_FILE, sep="\t", encoding="utf-16", dtype=str).fillna("")
    manifest, subset = build_manifest(df, batch_size=bounded_batch_size)
    manifest["batch_id"] = batch_id
    manifest["execution_profile"] = shadow_profile["profile_name"]
    manifest["execution_limits"] = shadow_profile["limits"]

    paths = prepare_batch_root(batch_id)
    subset.to_csv(paths["input_file"], sep="\t", index=False, encoding="utf-16")
    paths["manifest_file"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    materialize_price_cache(paths, batch_id=batch_id)
    materialize_source_surface_cache(paths, batch_id=batch_id)

    apply_pipeline_overrides(paths)
    _, first_stdout, first_shadow_summary = run_pipeline_capture(
        paths,
        batch_size=manifest["batch_size"],
        log_path=paths["stdout_first"],
        run_manifest_id=batch_id,
    )
    bundles = load_bundles(paths, manifest)
    sidecar_rows = build_sidecar_rows(bundles, batch_id=batch_id)
    with paths["sidecar_file"].open("w", encoding="utf-8") as fh:
        for row in sidecar_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    resume_stdout = ""
    resume_shadow_summary: dict[str, Any] | None = None
    if first_shadow_summary.get("early_stop"):
        paths["stdout_resume"].write_text(
            f"RESUME_SKIPPED due_to_early_stop={first_shadow_summary.get('reason_for_early_stop', '')}\n",
            encoding="utf-8",
        )
    else:
        _, resume_stdout, resume_shadow_summary = run_pipeline_capture(
            paths,
            batch_size=manifest["batch_size"],
            log_path=paths["stdout_resume"],
            run_manifest_id=f"{batch_id}:resume",
        )
    report = build_report(
        manifest=manifest,
        paths=paths,
        bundles=bundles,
        sidecar_rows=sidecar_rows,
        first_stdout=first_stdout,
        resume_stdout=resume_stdout,
        first_shadow_summary=first_shadow_summary,
        resume_shadow_summary=resume_shadow_summary,
    )
    paths["report_file"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"batch_id={batch_id}")
    print(f"manifest={paths['manifest_file']}")
    print(f"report={paths['report_file']}")
    print(f"sidecar={paths['sidecar_file']}")
    print(f"evidence_dir={paths['evidence_dir']}")
    print(f"export_dir={paths['export_dir']}")
    print(f"checkpoint_resume_ok={report['resume_evidence']['checkpoint_resume_ok']}")
    print(f"total_wall_clock_sec={report['shadow_run_summary']['first_run']['total_wall_clock_sec']}")
    print(f"verifier_calls_used={report['shadow_run_summary']['first_run']['verifier_calls_used']}")
    print(f"responses_calls={report['shadow_run_summary']['first_run']['responses_calls']}")
    print(
        "chat_completions_calls_verifier="
        f"{report['shadow_run_summary']['first_run']['chat_completions_calls_verifier']}"
    )
    print(f"timeout_count={report['shadow_run_summary']['first_run']['timeout_count']}")
    print(f"safe_cache_fallback_reuse_count={report['metrics']['safe_cache_fallback_reuse_count']['count']}")
    print(
        "per_source_failure_summary="
        f"{report['shadow_run_summary']['first_run']['per_source_failure_summary']}"
    )
    print(f"early_stop={report['shadow_run_summary']['first_run']['early_stop']}")
    print(f"reason_for_early_stop={report['shadow_run_summary']['first_run']['reason_for_early_stop']}")
    print(f"card_status_distribution={report['metrics']['card_status_distribution']}")
    print(f"blocking_issues={report['broader_controlled_run_assessment']['blocking_issues']}")


if __name__ == "__main__":
    main()

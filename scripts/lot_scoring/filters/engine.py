from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.etl import run_etl_pipeline
from scripts.lot_scoring.filters.artifact import build_lot_artifact_payload, write_lot_artifact, write_summary
from scripts.lot_scoring.filters.f0_data_quality import evaluate_f0
from scripts.lot_scoring.filters.f1_capital_composition import evaluate_f1
from scripts.lot_scoring.filters.f2_capital_safety import evaluate_f2
from scripts.lot_scoring.filters.f3_structural_ranking import evaluate_f3
from scripts.lot_scoring.filters.protocol_config import ProtocolConfig
from scripts.lot_scoring.filters.protocol_metrics import (
    aggregate_by_sku,
    brand_count_core,
    build_review_lines,
    core_coverage_ratio,
    core_sku_count,
    lot_sort_key,
    prepare_protocol_lines,
    shares,
    sm_ratio,
    ticket_pct,
    top_slices,
    total_value,
    unknown_value_share,
)
from scripts.lot_scoring.pipeline.helpers import to_float, to_str
from scripts.lot_scoring.pipeline.score import compute_hhi, compute_unknown_exposure
from scripts.lot_scoring.run_full_ranking_v341 import (
    REPORT_FILENAMES,
    _column_map,
    _load_rows_by_lot,
    _load_rows_by_lot_with_report_merge,
    _resolve_enriched_source_path,
)


def _total_effective_lot_usd(all_skus: list[dict[str, Any]]) -> float:
    total = 0.0
    for sku in all_skus:
        q_has_qty = sku.get("q_has_qty")
        has_qty = q_has_qty is not False
        has_line = sku.get("effective_line_usd") is not None
        if not has_qty or not has_line:
            continue
        total += max(0.0, to_float(sku.get("effective_line_usd"), 0.0))
    return total


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_sha_refs(config: ProtocolConfig) -> dict[str, str]:
    refs: dict[str, str] = {}
    root = _repo_root()
    for relative in config.metadata_sha_ref_files:
        path = root / relative
        if not path.exists():
            continue
        refs[relative] = _sha256(path)
    return refs


def _dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)


def _load_rows_for_engine(input_path: Path, usd_rate: float) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    report_paths = [input_path.parent / name for name in REPORT_FILENAMES]
    enriched_path = _resolve_enriched_source_path(input_path.parent)
    merge_stats: dict[str, Any] = {}
    use_report_merge = False

    if (enriched_path is not None and enriched_path.exists()) or any(path.exists() for path in report_paths):
        workbook = pd.ExcelFile(input_path)
        if len(workbook.sheet_names) > 1:
            sample_df = pd.read_excel(input_path, sheet_name=workbook.sheet_names[0], nrows=2)
            use_report_merge = "lot_id" not in _column_map(sample_df)

    if use_report_merge:
        lots, merge_stats = _load_rows_by_lot_with_report_merge(
            input_path,
            report_paths,
            usd_rate=usd_rate,
            enriched_path=enriched_path,
        )
    else:
        lots = _load_rows_by_lot(input_path)
    return lots, merge_stats


def run_filters(
    *,
    input_path: str | Path,
    usd_rate: float,
    entry_price_rub: float | None,
    output_dir: str | Path,
    filter4_top_n: int = 5,
    config: ProtocolConfig | None = None,
) -> dict[str, Any]:
    cfg = config or ProtocolConfig()
    if usd_rate <= 0:
        raise ValueError("usd_rate must be > 0")
    if filter4_top_n <= 0:
        raise ValueError("filter4_top_n must be > 0")

    input_file = Path(input_path).resolve()
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    lots, merge_stats = _load_rows_for_engine(input_file, usd_rate)
    match_confidence_weighted: float | None = None
    if "match_coverage" in merge_stats:
        match_confidence_weighted = to_float(merge_stats.get("match_coverage"), 0.0)

    per_lot: list[dict[str, Any]] = []
    for lot_id in sorted(lots.keys(), key=lot_sort_key):
        raw_rows = lots[lot_id]
        assembled = run_etl_pipeline(raw_rows)

        lines = prepare_protocol_lines(assembled.all_skus, usd_rate, cfg)
        aggregated = aggregate_by_sku(lines, value_key="line_value_rub")
        total_value_rub = total_value(lines, value_key="line_value_rub")

        f0 = evaluate_f0(lines=lines, aggregated=aggregated, total_value_rub=total_value_rub, config=cfg)
        f1 = evaluate_f1(
            lines=lines,
            total_value_rub=total_value_rub,
            match_confidence_weighted=match_confidence_weighted,
            config=cfg,
        )
        f2 = evaluate_f2(
            aggregated=aggregated,
            total_value_rub=total_value_rub,
            entry_price_rub=entry_price_rub,
            config=cfg,
        )

        # Canonical cascade statuses
        f0_status = to_str(f0.get("status"), "STOP")
        f1_status = to_str(f1.get("status"), "STOP") if f0_status != "STOP" else "N/A"
        f2_status = to_str(f2.get("status"), "REVIEW") if f1_status == "PASS" else "N/A"

        effective_shares = shares(lines, cfg, total_value_rub, value_key="line_value_rub")
        if bool(f1.get("used_stress_applied")):
            effective_shares = shares(lines, cfg, to_float(f1.get("adjusted_value_rub"), 0.0), value_key="adjusted_value_rub")
        share_a = to_float(f1.get("share_a"), to_float(effective_shares.get("share_a"), 0.0))
        share_b = to_float(f1.get("share_b"), to_float(effective_shares.get("share_b"), 0.0))
        share_e = to_float(f1.get("share_e"), to_float(effective_shares.get("share_e"), 0.0))

        core70_slice = list(f2.get("core70_slice") or [])
        core70_value_rub = to_float(f2.get("core70_value_rub"), 0.0)
        ticket = ticket_pct(aggregated, cfg.f3_ticket_threshold_rub)
        core_count = core_sku_count(core70_slice)
        brand_count = brand_count_core(core70_slice, cfg)

        f3 = evaluate_f3(
            f1_status=f1_status,
            f2_status=f2_status,
            share_a=share_a,
            share_b=share_b,
            share_e=share_e,
            total_value_rub=total_value_rub,
            entry_price_rub=entry_price_rub,
            largest_sku_share=to_float(f2.get("largest_sku_share"), to_float(f1.get("largest_sku_share"), 0.0)),
            match_confidence_weighted=match_confidence_weighted,
            core70_value_rub=core70_value_rub,
            share_used=to_float(f1.get("share_used"), 0.0),
            used_signal_available=bool(f1.get("share_used") is not None),
            ticket_pct=ticket,
            core_sku_count=core_count,
            brand_count_core=brand_count,
        )
        score_100 = int(to_float(f3.get("score_100"), 0.0))
        class_name = to_str(f3.get("class"), "Weak")
        f3_status = "SCORED" if (f1_status == "PASS" and f2_status == "PASS") else "SKIPPED"

        total_effective_usd = _total_effective_lot_usd(assembled.all_skus)
        hhi = compute_hhi(assembled.all_skus, total_effective_usd)
        unknown_exposure, unknown_exposure_usd = compute_unknown_exposure(assembled.all_skus, total_effective_usd)
        lot_record = LotRecord(lot_id=to_str(lot_id))
        lot_record.hhi_index = hhi
        lot_record.unknown_exposure = unknown_exposure
        lot_record.unknown_exposure_usd = unknown_exposure_usd

        top_slice_payload = top_slices(aggregated, total_value_rub, cfg)
        top3 = list(aggregated[:3])
        duplicate_skus = set(f0.get("duplicate_sku_keys") or [])
        review_lines = build_review_lines(lines, duplicate_sku_keys=duplicate_skus)
        unknown_share = unknown_value_share(lines, total_value_rub, value_key="line_value_rub")

        metrics = {
            "total_value_rub": round(total_value_rub, 8),
            "adjusted_value_rub": round(to_float(f1.get("adjusted_value_rub"), total_value_rub), 8),
            "share_a": round(share_a, 8),
            "share_b": round(share_b, 8),
            "share_e": round(share_e, 8),
            "share_used": round(to_float(f1.get("share_used"), 0.0), 8),
            "largest_sku_share": round(to_float(f2.get("largest_sku_share"), to_float(f1.get("largest_sku_share"), 0.0)), 8),
            "core70_value_rub": round(core70_value_rub, 8),
            "entry_price_rub": entry_price_rub,
            "sm": round(sm_ratio(total_value_rub, entry_price_rub), 8),
            "core_coverage": round(core_coverage_ratio(core70_value_rub, entry_price_rub), 8),
            "ticket_pct": round(ticket, 8),
            "core_sku_count": core_count,
            "brand_count_core": brand_count,
            "unknown_value_share": round(unknown_share, 8),
            "unknown_exposure": round(lot_record.unknown_exposure, 8),
            "unknown_exposure_usd": round(lot_record.unknown_exposure_usd, 8),
            "hhi": round(lot_record.hhi_index, 8),
            "mass_anchor_status": to_str(f2.get("mass_anchor_status"), "PASS"),
            "mass_anchor_hits": f2.get("mass_anchor_hits") or [],
            "buy_allowed": bool(f2.get("buy_allowed")),
            "match_confidence_weighted": match_confidence_weighted,
            "f0_reasons": {
                "stop": f0.get("stop_reasons") or [],
                "review": f0.get("review_reasons") or [],
            },
            "f1_fail_reasons": f1.get("fail_reasons") or [],
            "f2_reasons": {
                "stop": f2.get("stop_reasons") or [],
                "review": f2.get("review_reasons") or [],
            },
            "f3_blocks": {
                "block_i": f3.get("block_i"),
                "block_ii": f3.get("block_ii"),
                "block_iii": f3.get("block_iii"),
                "block_iv": f3.get("block_iv"),
                "details": f3.get("details"),
            },
        }
        statuses = {
            "f0": f0_status,
            "f1": f1_status,
            "f2": f2_status,
            "f3": f3_status,
        }
        per_lot.append(
            {
                "lot_id": to_str(lot_id),
                "statuses": statuses,
                "metrics": metrics,
                "top3": top3,
                "top20": top_slice_payload.get("top20_value_slice", []),
                "top40": top_slice_payload.get("top40_value_slice", []),
                "top80": top_slice_payload.get("top80_value_slice", []),
                "review_lines": review_lines,
                "score_100": score_100,
                "class": class_name,
            }
        )

    candidates = [
        item
        for item in per_lot
        if item["statuses"]["f0"] != "STOP" and item["statuses"]["f1"] == "PASS" and item["statuses"]["f2"] == "PASS"
    ]
    candidates_sorted = sorted(candidates, key=lambda item: (-to_float(item.get("score_100"), 0.0), lot_sort_key(item["lot_id"])))
    candidate_ids = {item["lot_id"] for item in candidates_sorted[:filter4_top_n]}

    summary_rows: list[dict[str, Any]] = []
    for item in sorted(per_lot, key=lambda row: lot_sort_key(row["lot_id"])):
        lot_id = item["lot_id"]
        is_candidate = lot_id in candidate_ids
        metrics = item["metrics"]
        artifact_payload = build_lot_artifact_payload(
            lot_id=lot_id,
            statuses=item["statuses"],
            metrics=metrics,
            top3=item["top3"],
            top20=item["top20"],
            top40=item["top40"],
            top80=item["top80"],
            review_lines=item["review_lines"],
            filter4_candidate=is_candidate,
            config=cfg,
        )
        write_lot_artifact(out_dir, lot_id, artifact_payload)

        summary_rows.append(
            {
                "lot_id": lot_id,
                "f0_status": item["statuses"]["f0"],
                "f1_status": item["statuses"]["f1"],
                "f2_status": item["statuses"]["f2"],
                "score_100": item["score_100"],
                "class": item["class"],
                "total_value_rub": metrics["total_value_rub"],
                "adjusted_value_rub": metrics["adjusted_value_rub"],
                "share_a": metrics["share_a"],
                "share_b": metrics["share_b"],
                "share_e": metrics["share_e"],
                "share_used": metrics["share_used"],
                "largest_sku_share": metrics["largest_sku_share"],
                "core70_value_rub": metrics["core70_value_rub"],
                "entry_price_rub": metrics["entry_price_rub"],
                "sm": metrics["sm"],
                "core_coverage": metrics["core_coverage"],
                "ticket_pct": metrics["ticket_pct"],
                "core_sku_count": metrics["core_sku_count"],
                "brand_count_core": metrics["brand_count_core"],
                "unknown_value_share": metrics["unknown_value_share"],
                "unknown_exposure": metrics["unknown_exposure"],
                "hhi": metrics["hhi"],
                "mass_anchor_status": metrics["mass_anchor_status"],
                "filter4_candidate": is_candidate,
            }
        )

    summary_path = write_summary(out_dir, summary_rows, cfg)
    metadata_dir = out_dir / "_metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    manifest_payload = {
        "schema_version": cfg.schema_version,
        "usd_rate": usd_rate,
        "entry_price_rub": entry_price_rub,
        "input_path": str(input_file),
        "lots_count": len(per_lot),
        "filter4_top_n": filter4_top_n,
        "sha256_refs": _build_sha_refs(cfg),
    }
    _dump_json(metadata_dir / "engine_manifest.json", manifest_payload)
    _dump_json(metadata_dir / "merge_stats.json", merge_stats)

    return {
        "summary_path": str(summary_path),
        "output_dir": str(out_dir),
        "lots_count": len(per_lot),
        "candidate_count": len(candidate_ids),
    }

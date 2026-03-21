from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from scripts.lot_scoring.filters.protocol_config import ProtocolConfig
from scripts.lot_scoring.pipeline.helpers import to_float, to_str


def _stable_float(value: object) -> float:
    return round(float(to_float(value, 0.0)), 8)


def _serialize_sku_row(sku: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku": to_str(sku.get("sku")),
        "raw_text": to_str(sku.get("raw_text")),
        "qty": _stable_float(sku.get("qty_total")),
        "line_value_rub": _stable_float(sku.get("sku_value_rub")),
        "category": to_str(sku.get("category"), "unknown"),
        "brand": to_str(sku.get("brand"), "unknown"),
    }


def write_lot_artifact(output_dir: Path, lot_id: str, artifact: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"lot_{to_str(lot_id)}_artifact.json"
    payload = dict(artifact)
    payload["generated_at"] = datetime.now(tz=timezone.utc).isoformat()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
    return path


def write_summary(output_dir: Path, rows: list[dict[str, Any]], config: ProtocolConfig) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "summary_filters_report.xlsx"

    workbook = Workbook()
    ws = workbook.active
    ws.title = "summary"

    headers = list(config.summary_columns)
    ws.append(headers)
    for row in rows:
        ws.append([row.get(column) for column in headers])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    workbook.save(path)
    return path


def build_filter4_checklist(config: ProtocolConfig) -> dict[str, Any]:
    return {
        "fatal_items": [
            {
                "rule": "vendor_lock_or_firmware_lock",
                "if_confirmed": "STOP",
                "if_unknown": "REVIEW",
            },
            {
                "rule": "legal_non_resalable",
                "if_confirmed": "STOP",
                "if_unknown": "REVIEW",
            },
            {
                "rule": "critical_revision_incompatibility_or_project_lock",
                "if_confirmed": "STOP",
                "if_unknown": "REVIEW",
            },
        ],
        "adaptive_depth": {
            "base_x": 20,
            "raise_to_40_if": [
                "top20_sku_count<=5",
                "largest_sku_share>=0.30",
                "share_e>=0.15",
            ],
            "raise_to_80_if": ["shelf_risk_signals"],
        },
        "market_rule_top3": list(config.filter4_market_rule),
        "physical_degradation_rule": list(config.filter4_physical_rule),
    }


def build_lot_artifact_payload(
    *,
    lot_id: str,
    statuses: dict[str, str],
    metrics: dict[str, Any],
    top3: list[dict[str, Any]],
    top20: list[dict[str, Any]],
    top40: list[dict[str, Any]],
    top80: list[dict[str, Any]],
    review_lines: list[dict[str, Any]],
    filter4_candidate: bool,
    config: ProtocolConfig,
) -> dict[str, Any]:
    return {
        "lot_id": to_str(lot_id),
        "statuses": statuses,
        "metrics": metrics,
        "top3_by_value": [_serialize_sku_row(row) for row in top3],
        "top20_value_slice": [_serialize_sku_row(row) for row in top20],
        "top40_value_slice": [_serialize_sku_row(row) for row in top40],
        "top80_value_slice": [_serialize_sku_row(row) for row in top80],
        "review_lines": review_lines,
        "filter4_candidate": bool(filter4_candidate),
        "filter4_checklist": build_filter4_checklist(config),
    }

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


TARGET_LOT_ID = "10"
TARGET_SKUS = ("CC-PCF901", "CPO-PC400", "XS830")

QTY_PATTERNS = (
    r"(?:кол-?во|количество|\bqty\b|\bquantity\b|\bpcs?\b|\bшт\b)\s*[:=]?\s*(\d+(?:[.,]\d+)?)",
    r"(?:кол-?во|количество|\bqty\b|\bquantity\b|\bpcs?\b|\bшт\b)\D{0,12}(\d+(?:[.,]\d+)?)",
)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def _normalize_sku(value: Any) -> str:
    text = str(value or "").upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def _normalize_lot_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"\d+", text)
    if not match:
        return text
    return str(int(match.group(0)))


def _extract_qty_from_text(raw_text: str) -> float | None:
    if not raw_text:
        return None
    for pattern in QTY_PATTERNS:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            parsed = _to_float(match.group(1).replace(",", "."))
            if parsed is not None and 0 <= parsed <= 1_000_000:
                return parsed
    # Fallback for malformed encodings: take last numeric token.
    tokens = re.findall(r"\d+(?:[.,]\d+)?", raw_text)
    if not tokens:
        return None
    parsed = _to_float(tokens[-1].replace(",", "."))
    if parsed is None or parsed < 0 or parsed > 1_000_000:
        return None
    return parsed


def _column_map(df: pd.DataFrame) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for column in df.columns:
        key = str(column).strip().lower()
        if key not in mapped:
            mapped[key] = str(column)
    return mapped


def _find_column_by_tokens(cmap: dict[str, str], tokens: tuple[str, ...]) -> str | None:
    for token in tokens:
        token_lower = token.lower()
        for key, value in cmap.items():
            if token_lower in key:
                return value
    return None


def _choose_best_numeric_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    best_col: str | None = None
    best_score = -1.0
    for col in candidates:
        series = pd.to_numeric(df[col], errors="coerce")
        if len(series) == 0:
            continue
        numeric_ratio = float(series.notna().mean())
        positive_ratio = float((series > 0).mean())
        score = numeric_ratio * 1000.0 + positive_ratio
        if score > best_score and numeric_ratio > 0:
            best_score = score
            best_col = col
    return best_col


def _find_columns_with_tokens(df: pd.DataFrame, tokens: tuple[str, ...]) -> list[str]:
    normalized = {str(column): re.sub(r"[^a-zа-я0-9]+", "", str(column).lower()) for column in df.columns}
    matches: list[str] = []
    for token in tokens:
        token_norm = re.sub(r"[^a-zа-я0-9]+", "", token.lower())
        if not token_norm:
            continue
        for col in df.columns:
            col_name = str(col)
            if col_name in matches:
                continue
            if token_norm in normalized[col_name]:
                matches.append(col_name)
    return matches


def _first_non_empty_cell(row_values: list[Any]) -> str:
    for value in row_values:
        text = str(value).strip() if value is not None else ""
        if text and text.lower() != "nan":
            return text
    return ""


def _full_row_text(row_values: list[Any]) -> str:
    chunks: list[str] = []
    numeric_only = re.compile(r"^\d+(?:[.,]\d+)?$")
    for value in row_values:
        text = str(value).strip() if value is not None else ""
        if not text or text.lower() == "nan":
            continue
        if numeric_only.fullmatch(text):
            continue
        chunks.append(text)
    return " | ".join(chunks)


def _extract_line_value_from_row_values(row_values: list[Any], qty: float | None) -> float | None:
    nums: list[float] = []
    for value in row_values:
        parsed = _to_float(value)
        if parsed is None or parsed <= 0:
            continue
        nums.append(parsed)
    if not nums:
        return None
    # Heuristic: line value is a larger number than qty.
    candidates = [x for x in nums if x >= 1000]
    if not candidates and qty is not None:
        candidates = [x for x in nums if x > qty]
    if not candidates:
        return None
    return max(candidates)


@dataclass
class RowExtract:
    sku: str
    raw_text: str
    raw_qty: float | None
    unit_price_rub: float | None
    line_value_rub: float | None


def _extract_rows_from_sheet_without_headers(input_path: Path, sheet_name: str) -> list[RowExtract]:
    df = pd.read_excel(input_path, sheet_name=sheet_name, header=None).dropna(how="all")
    rows: list[RowExtract] = []
    sku_norm_map = {_normalize_sku(s): s for s in TARGET_SKUS}
    for _, row in df.iterrows():
        values = list(row.values)
        raw_text = _first_non_empty_cell(values)
        if not raw_text:
            continue
        normalized_text = _normalize_sku(_full_row_text(values) or raw_text)
        sku_hit: str | None = None
        for sku_norm, sku_label in sku_norm_map.items():
            if sku_norm in normalized_text:
                sku_hit = sku_label
                break
        if sku_hit is None:
            continue

        qty = _extract_qty_from_text(raw_text)
        line_value = _extract_line_value_from_row_values(values, qty)
        unit_price = (line_value / qty) if (line_value is not None and qty is not None and qty > 0) else None
        rows.append(RowExtract(sku=sku_hit, raw_text=raw_text, raw_qty=qty, unit_price_rub=unit_price, line_value_rub=line_value))
    return rows


def _extract_rows_from_modern_sheets(input_path: Path, target_lot_id: str) -> list[RowExtract]:
    xls = pd.ExcelFile(input_path)
    sku_norm_map = {_normalize_sku(s): s for s in TARGET_SKUS}
    extracted: list[RowExtract] = []
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(input_path, sheet_name=sheet_name).dropna(how="all")
        if df.empty:
            continue
        cmap = _column_map(df)
        lot_col = _find_column_by_tokens(cmap, ("lot_id", "lot id", "sheetname", "sheet_name"))
        if lot_col is None:
            continue

        qty_cols = _find_columns_with_tokens(df, ("raw_qty", "qty", "quantity", "кол-во", "количество"))
        line_cols = _find_columns_with_tokens(
            df,
            ("calculatedlotcost", "line_value_rub", "line value", "стоимость", "total_rub", "итого"),
        )
        unit_cols = _find_columns_with_tokens(
            df,
            ("unit_price_rub", "unit price", "price_rub", "цена", "price"),
        )
        qty_col = _choose_best_numeric_column(df, qty_cols) if qty_cols else None
        line_col = _choose_best_numeric_column(df, line_cols) if line_cols else None
        unit_col = _choose_best_numeric_column(df, unit_cols) if unit_cols else None
        sku_col = _find_column_by_tokens(
            cmap,
            ("sku_code_normalized", "partnumber", "part_number", "model", "sku", "артикул"),
        )
        raw_text_col = _find_column_by_tokens(cmap, ("raw_text", "description", "наимен", "column1", "desc"))

        for _, row in df.iterrows():
            lot_value = _normalize_lot_id(row.get(lot_col))
            if lot_value != target_lot_id:
                continue
            raw_text = str(row.get(raw_text_col)).strip() if raw_text_col else ""
            if not raw_text or raw_text.lower() == "nan":
                raw_text = _full_row_text(list(row.values))
            if not raw_text:
                continue

            normalized_text = _normalize_sku(raw_text)
            sku_hit: str | None = None
            sku_cell_norm = _normalize_sku(row.get(sku_col)) if sku_col else ""
            for sku_norm, sku_label in sku_norm_map.items():
                if sku_norm and (sku_norm in normalized_text or sku_norm == sku_cell_norm):
                    sku_hit = sku_label
                    break
            if sku_hit is None:
                continue

            qty = _to_float(row.get(qty_col)) if qty_col else None
            if qty is None or qty <= 0:
                qty = _extract_qty_from_text(raw_text)
            line_value = _to_float(row.get(line_col)) if line_col else None
            if line_value is None or line_value <= 0:
                line_value = None
            unit_price = _to_float(row.get(unit_col)) if unit_col else None
            if (unit_price is None or unit_price <= 0) and line_value is not None and qty is not None and qty > 0:
                unit_price = line_value / qty
            if unit_price is not None and unit_price <= 0:
                unit_price = None

            extracted.append(
                RowExtract(
                    sku=sku_hit,
                    raw_text=raw_text,
                    raw_qty=qty,
                    unit_price_rub=unit_price,
                    line_value_rub=line_value,
                )
            )
    return extracted


def _load_lot10_rows(input_path: Path) -> list[RowExtract]:
    xls = pd.ExcelFile(input_path)
    for sheet_name in xls.sheet_names:
        if _normalize_lot_id(sheet_name) == TARGET_LOT_ID:
            rows = _extract_rows_from_sheet_without_headers(input_path, sheet_name)
            if rows:
                return rows
    # Fallback for a single-sheet modern schema with lot_id column.
    return _extract_rows_from_modern_sheets(input_path, TARGET_LOT_ID)


def _parse_qty_from_artifact_text(raw_text: Any) -> float | None:
    if raw_text is None:
        return None
    return _extract_qty_from_text(str(raw_text))


def _dedupe_sorted(values: list[float], ndigits: int = 6) -> list[float]:
    seen: set[float] = set()
    out: list[float] = []
    for value in sorted(values):
        key = round(value, ndigits)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _class_from_score(score_100: int) -> str:
    if score_100 >= 90:
        return "Elite"
    if score_100 >= 80:
        return "Strong"
    if score_100 >= 70:
        return "Good"
    if score_100 >= 60:
        return "Acceptable"
    return "Weak"


def _block_i(share_a: float, share_b: float, share_e: float) -> tuple[int, dict[str, int]]:
    if share_a >= 0.60:
        a_points = 20
    elif share_a >= 0.50:
        a_points = 16
    elif share_a >= 0.40:
        a_points = 12
    elif share_a >= 0.30:
        a_points = 8
    else:
        a_points = 4

    ab = share_a + share_b
    if ab >= 0.80:
        ab_points = 15
    elif ab >= 0.70:
        ab_points = 12
    elif ab >= 0.60:
        ab_points = 9
    elif ab >= 0.50:
        ab_points = 6
    else:
        ab_points = 0

    if share_e > 0.20:
        e_penalty = -5
    elif share_e >= 0.10:
        e_penalty = -3
    else:
        e_penalty = 0

    total = max(0, min(40, a_points + ab_points + e_penalty))
    return total, {"a_points": a_points, "ab_points": ab_points, "e_penalty": e_penalty}


def _block_ii(total_value_rub: float, entry_price_rub: float, largest_share: float, confidence: float | None) -> tuple[int, dict[str, int]]:
    sm = (total_value_rub / entry_price_rub) if entry_price_rub > 0 else 0.0
    if sm >= 4.0:
        sm_points = 15
    elif sm >= 3.0:
        sm_points = 10
    elif sm >= 2.0:
        sm_points = 5
    else:
        sm_points = 0

    if largest_share < 0.30:
        concentration_points = 10
    elif largest_share < 0.40:
        concentration_points = 6
    elif largest_share <= 0.50:
        concentration_points = 3
    else:
        concentration_points = 0

    if confidence is None:
        confidence_points = 2
    elif confidence >= 0.85:
        confidence_points = 3
    elif confidence >= 0.70:
        confidence_points = 2
    else:
        confidence_points = 0

    total = max(0, min(28, sm_points + concentration_points + confidence_points))
    return total, {
        "sm_points": sm_points,
        "concentration_points": concentration_points,
        "confidence_points": confidence_points,
    }


def _block_iii(
    core70_value_rub: float,
    entry_price_rub: float,
    share_used: float | None,
    used_signal_available: bool,
    ticket_pct: float,
) -> tuple[int, dict[str, int]]:
    coverage = (core70_value_rub / entry_price_rub) if entry_price_rub > 0 else 0.0
    if coverage >= 1.5:
        core_coverage_points = 15
    elif coverage >= 1.0:
        core_coverage_points = 10
    elif coverage >= 0.70:
        core_coverage_points = 5
    else:
        core_coverage_points = 0

    if not used_signal_available or share_used is None:
        used_points = 6
    elif share_used <= 0.30:
        used_points = 10
    elif share_used <= 0.50:
        used_points = 6
    else:
        used_points = 3

    if ticket_pct >= 0.40:
        ticket_points = 3
    elif ticket_pct >= 0.20:
        ticket_points = 2
    else:
        ticket_points = 1

    total = max(0, min(28, core_coverage_points + used_points + ticket_points))
    return total, {
        "core_coverage_points": core_coverage_points,
        "used_points": used_points,
        "ticket_points": ticket_points,
    }


def _block_iv(core_sku_count: int, brand_count_core: int) -> tuple[int, dict[str, int]]:
    if core_sku_count <= 25:
        sku_points = 2
    elif core_sku_count <= 60:
        sku_points = 1
    else:
        sku_points = 0

    if 1 <= brand_count_core <= 2:
        brand_points = 2
    elif 3 <= brand_count_core <= 4:
        brand_points = 1
    else:
        brand_points = 0

    total = max(0, min(4, sku_points + brand_points))
    return total, {"core_sku_points": sku_points, "brand_points": brand_points}


def _fmt_num(value: Any, precision: int = 4) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "N/A"
    if parsed.is_integer():
        return str(int(parsed))
    return f"{parsed:.{precision}f}"


def _fmt_money(value: Any) -> str:
    parsed = _to_float(value)
    if parsed is None:
        return "N/A"
    return f"{parsed:,.2f}".replace(",", " ")


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "N/A"
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(out)


def build_due_diligence(entry_price_rub: float, input_path: Path, artifact_path: Path, md_output: Path, json_output: Path) -> None:
    if entry_price_rub <= 0:
        raise ValueError("--entry-price-rub must be > 0")
    if not input_path.exists():
        raise FileNotFoundError(f"Input Excel not found: {input_path}")
    if not artifact_path.exists():
        raise FileNotFoundError(f"Artifact not found: {artifact_path}")

    with artifact_path.open("r", encoding="utf-8") as handle:
        artifact = json.load(handle)

    rows = _load_lot10_rows(input_path)
    if not rows:
        raise RuntimeError("Could not extract lot 10 rows from source Excel")

    sku_rows: dict[str, list[RowExtract]] = {sku: [] for sku in TARGET_SKUS}
    for row in rows:
        if row.sku in sku_rows:
            sku_rows[row.sku].append(row)

    top3 = artifact.get("top3_by_value", []) if isinstance(artifact, dict) else []
    top80 = artifact.get("top80_value_slice", []) if isinstance(artifact, dict) else []
    artifact_sku_map: dict[str, dict[str, Any]] = {}
    for item in list(top3) + list(top80):
        if not isinstance(item, dict):
            continue
        sku_norm = _normalize_sku(item.get("sku"))
        if not sku_norm:
            continue
        if sku_norm not in artifact_sku_map:
            artifact_sku_map[sku_norm] = item

    audit_rows_md: list[list[Any]] = []
    sku_audit_payload: list[dict[str, Any]] = []
    any_qty_suspicious = False
    for sku in TARGET_SKUS:
        norm = _normalize_sku(sku)
        extracted = sku_rows.get(sku, [])
        line_count = len(extracted)
        qty_values = [row.raw_qty for row in extracted if row.raw_qty is not None]
        sum_raw_qty = sum(qty_values) if qty_values else None
        unit_prices = _dedupe_sorted([row.unit_price_rub for row in extracted if row.unit_price_rub is not None and row.unit_price_rub > 0])  # type: ignore[arg-type]
        line_values = [row.line_value_rub for row in extracted if row.line_value_rub is not None and row.line_value_rub > 0]
        sum_line_value = sum(line_values) if line_values else None

        artifact_row = artifact_sku_map.get(norm, {})
        artifact_qty = _to_float(artifact_row.get("qty")) if artifact_row else None
        artifact_line_value = _to_float(artifact_row.get("line_value_rub")) if artifact_row else None
        artifact_text_qty = _parse_qty_from_artifact_text(artifact_row.get("raw_text")) if artifact_row else None

        mismatch = (
            artifact_qty is not None
            and artifact_text_qty is not None
            and abs(artifact_qty - artifact_text_qty) > 1e-9
        )
        qty_mismatch_explained = (
            mismatch
            and line_count > 1
            and sum_raw_qty is not None
            and artifact_qty is not None
            and abs(artifact_qty - sum_raw_qty) <= 1e-6
        )

        unit_price_ratio = None
        if len(unit_prices) >= 2 and unit_prices[0] > 0:
            unit_price_ratio = unit_prices[-1] / unit_prices[0]

        qty_suspicious = False
        suspicious_reasons: list[str] = []
        if line_count == 0:
            qty_suspicious = True
            suspicious_reasons.append("sku_not_found_in_excel_lot10")
        if unit_price_ratio is not None and unit_price_ratio > 3.0:
            qty_suspicious = True
            suspicious_reasons.append("unit_price_ratio_gt_3x")
        if artifact_qty is not None and sum_raw_qty is not None and abs(artifact_qty - sum_raw_qty) > 1e-6 and not qty_mismatch_explained:
            qty_suspicious = True
            suspicious_reasons.append("artifact_qty_ne_sum_raw_qty")
        if sum_raw_qty is None:
            qty_suspicious = True
            suspicious_reasons.append("sum_raw_qty_unavailable")
        if qty_suspicious:
            any_qty_suspicious = True

        audit_rows_md.append(
            [
                sku,
                line_count,
                _fmt_num(sum_raw_qty, 3),
                _fmt_num(artifact_qty, 3),
                _fmt_num(artifact_text_qty, 3),
                _fmt_money(sum_line_value),
                _fmt_money(artifact_line_value),
                ", ".join(_fmt_num(v, 6) for v in unit_prices) if unit_prices else "N/A",
                _fmt_num(unit_price_ratio, 3),
                str(bool(qty_mismatch_explained)).lower(),
                str(bool(qty_suspicious)).lower(),
            ]
        )
        sku_audit_payload.append(
            {
                "sku": sku,
                "line_count": line_count,
                "sum_raw_qty": sum_raw_qty,
                "unique_unit_price_rub": unit_prices,
                "sum_line_value_rub": sum_line_value,
                "artifact_qty": artifact_qty,
                "artifact_raw_text_qty": artifact_text_qty,
                "artifact_line_value_rub": artifact_line_value,
                "qty_mismatch_explained": bool(qty_mismatch_explained),
                "qty_suspicious": bool(qty_suspicious),
                "qty_suspicious_reasons": suspicious_reasons,
            }
        )

    metrics = artifact.get("metrics", {}) if isinstance(artifact, dict) else {}
    statuses = artifact.get("statuses", {}) if isinstance(artifact, dict) else {}

    total_value_rub = _to_float(metrics.get("total_value_rub")) or 0.0
    core70_value_rub = _to_float(metrics.get("core70_value_rub")) or 0.0
    largest_sku_share = _to_float(metrics.get("largest_sku_share")) or 0.0
    ticket_pct = _to_float(metrics.get("ticket_pct")) or 0.0
    share_a = _to_float(metrics.get("share_a")) or 0.0
    share_b = _to_float(metrics.get("share_b")) or 0.0
    share_e = _to_float(metrics.get("share_e")) or 0.0
    share_used = _to_float(metrics.get("share_used"))
    match_confidence = _to_float(metrics.get("match_confidence_weighted"))
    core_sku_count = int(_to_float(metrics.get("core_sku_count")) or 0)
    brand_count_core = int(_to_float(metrics.get("brand_count_core")) or 0)

    f2_check_a_status = "PASS" if core70_value_rub + 1e-9 >= entry_price_rub else "STOP"
    sm = (total_value_rub / entry_price_rub) if entry_price_rub > 0 else 0.0
    core_coverage = (core70_value_rub / entry_price_rub) if entry_price_rub > 0 else 0.0

    block_i, block_i_details = _block_i(share_a, share_b, share_e)
    block_ii, block_ii_details = _block_ii(total_value_rub, entry_price_rub, largest_sku_share, match_confidence)
    block_iii, block_iii_details = _block_iii(
        core70_value_rub=core70_value_rub,
        entry_price_rub=entry_price_rub,
        share_used=share_used,
        used_signal_available=share_used is not None,
        ticket_pct=ticket_pct,
    )
    block_iv, block_iv_details = _block_iv(core_sku_count, brand_count_core)

    f1_status = str(statuses.get("f1", "N/A"))
    if f1_status == "PASS" and f2_check_a_status == "PASS":
        score_recalc = int(max(0, min(100, block_i + block_ii + block_iii + block_iv)))
        class_recalc = _class_from_score(score_recalc)
    else:
        score_recalc = 0
        class_recalc = "Weak"

    if f2_check_a_status == "STOP":
        final_verdict = "REJECT"
    elif any_qty_suspicious:
        final_verdict = "CONDITIONAL"
    else:
        final_verdict = "PASS"

    reasons: list[str] = []
    if f2_check_a_status == "STOP":
        reasons.append("CORE70_LT_ENTRYPRICE")
    else:
        reasons.append("CORE70_GTE_ENTRYPRICE")
    if any_qty_suspicious:
        reasons.append("SKU_QTY_OR_PRICE_NEEDS_MANUAL_CHECK")
    reasons.append(f"LARGEST_SKU_SHARE={largest_sku_share:.6f}")
    reasons.append(f"MASS_ANCHOR_STATUS={metrics.get('mass_anchor_status', 'N/A')}")
    reasons.append(f"TICKET_PCT={ticket_pct:.6f}")

    recalc_json = {
        "lot_id": TARGET_LOT_ID,
        "entry_price_rub": entry_price_rub,
        "f2_status_recalc": f2_check_a_status,
        "score_100_recalc": score_recalc,
        "class_recalc": class_recalc,
        "sm_recalc": sm,
        "core_coverage_recalc": core_coverage,
        "blocks_recalc": {
            "block_i": block_i,
            "block_ii": block_ii,
            "block_iii": block_iii,
            "block_iv": block_iv,
            "details": {
                "block_i": block_i_details,
                "block_ii": block_ii_details,
                "block_iii": block_iii_details,
                "block_iv": block_iv_details,
            },
        },
        "reasons": reasons,
        "sku_audit": sku_audit_payload,
    }

    md_lines: list[str] = []
    md_lines.append("# LOT10_DUE_DILIGENCE")
    md_lines.append("")
    md_lines.append(f"- lot_id: `{TARGET_LOT_ID}`")
    md_lines.append(f"- entry_price_rub (input): `{_fmt_money(entry_price_rub)}`")
    md_lines.append(f"- final_verdict: `{final_verdict}`")
    md_lines.append("")
    md_lines.append("## SKU Audit (Excel lot 10 vs artifact)")
    md_lines.append("")
    md_lines.append(
        _table(
            [
                "sku",
                "line_count",
                "sum_raw_qty",
                "artifact_qty",
                "artifact_text_qty",
                "sum_line_value_rub_excel",
                "artifact_line_value_rub",
                "unit_prices_rub",
                "unit_price_ratio",
                "qty_mismatch_explained",
                "qty_suspicious",
            ],
            audit_rows_md,
        )
    )
    md_lines.append("")
    md_lines.append("## F2/F3 Recalc (entry-price-sensitive)")
    md_lines.append("")
    md_lines.append(
        _table(
            ["metric", "value"],
            [
                ["f1_status (artifact)", f1_status],
                ["f2_check_A_recalc (core70 vs entry)", f2_check_a_status],
                ["total_value_rub", _fmt_money(total_value_rub)],
                ["core70_value_rub", _fmt_money(core70_value_rub)],
                ["sm_recalc", _fmt_num(sm, 6)],
                ["core_coverage_recalc", _fmt_num(core_coverage, 6)],
                ["largest_sku_share", _fmt_num(largest_sku_share, 6)],
                ["ticket_pct", _fmt_num(ticket_pct, 6)],
                ["block_i", str(block_i)],
                ["block_ii", str(block_ii)],
                ["block_iii", str(block_iii)],
                ["block_iv", str(block_iv)],
                ["score_100_recalc", str(score_recalc)],
                ["class_recalc", class_recalc],
            ],
        )
    )
    md_lines.append("")
    md_lines.append("## Notes")
    md_lines.append("")
    for reason in reasons:
        md_lines.append(f"- {reason}")
    md_lines.append("")

    md_output.write_text("\n".join(md_lines), encoding="utf-8")
    json_output.write_text(json.dumps(recalc_json, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_paths(repo_root: Path) -> tuple[Path, Path, Path, Path]:
    input_path = repo_root / "honeywell.xlsx"
    downloads_dir = repo_root / "downloads" / "lots"
    artifact_path = downloads_dir / "lot_10_artifact.json"
    md_output = downloads_dir / "LOT10_DUE_DILIGENCE.md"
    json_output = downloads_dir / "LOT10_ENTRYPRICE_RECALC.json"
    return input_path, artifact_path, md_output, json_output


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    default_input, default_artifact, default_md, default_json = _default_paths(repo_root)
    parser = argparse.ArgumentParser(description="LOT 10 due diligence: SKU audit and entry-price-sensitive recalc.")
    parser.add_argument("--entry-price-rub", required=True, type=float, help="Entry price in RUB for recalc")
    parser.add_argument("--input", default=str(default_input), help="Path to honeywell.xlsx source")
    parser.add_argument("--artifact", default=str(default_artifact), help="Path to lot_10_artifact.json")
    parser.add_argument("--md-output", default=str(default_md), help="Path to LOT10_DUE_DILIGENCE.md")
    parser.add_argument("--json-output", default=str(default_json), help="Path to LOT10_ENTRYPRICE_RECALC.json")
    args = parser.parse_args()

    build_due_diligence(
        entry_price_rub=float(args.entry_price_rub),
        input_path=Path(args.input),
        artifact_path=Path(args.artifact),
        md_output=Path(args.md_output),
        json_output=Path(args.json_output),
    )
    print(f"Due diligence report written to: {args.md_output}")
    print(f"Entry-price recalc JSON written to: {args.json_output}")


if __name__ == "__main__":
    main()

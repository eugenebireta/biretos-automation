from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.lot_scoring.category_engine import (
    BRAND_KEYWORDS,
    CATEGORY_KEYWORDS,
    infer_brand_from_text,
    normalize_brand,
    resolve_category,
)
from scripts.lot_scoring.cdm import LotRecord
from scripts.lot_scoring.etl import ETLInvariantError, EtlConfig, run_etl_pipeline
from scripts.lot_scoring.governance_config import GovernanceConfig
from scripts.lot_scoring.pipeline.explain import build_explanation_card
from scripts.lot_scoring.pipeline.explain_v4 import (
    compute_investor_summary,
    compute_loss_attribution,
    compute_top_loss_reasons,
    compute_v4_scalars,
    compute_zone,
)
from scripts.lot_scoring.pipeline.governance_flags import compute_governance_flags, is_hvl
from scripts.lot_scoring.pipeline.helpers import clamp, load_json_dict, to_float, to_str
from scripts.lot_scoring.pipeline.pn_liquidity import (
    PnLiquidityConfig,
    compute_lot_avg_pn_liquidity,
    compute_pn_liquidity,
)
from scripts.lot_scoring.pipeline.score import apply_base_score, apply_final_score, rank_lots
from scripts.lot_scoring.run_config import RunConfig
from scripts.lot_scoring.simulation.scoring_kernel import V4Config


MODERN_REQUIRED_COLUMNS = {
    "lot_id",
    "sku_code_normalized",
    "base_unit_usd",
    "raw_qty",
    "condition_raw",
    "is_fake",
    "category",
    "brand",
}

LEGACY_FAKE_KEYWORDS = (
    "fake",
    "counterfeit",
    "it hardware",
    "mouse",
    "keyboard",
    "monitor",
    "server",
    "rack",
    "toner",
    "cartridge",
    "consumer",
)

# Keep imported taxonomy constants available from this module.
_CATEGORY_ENGINE_EXPORTS = (CATEGORY_KEYWORDS, BRAND_KEYWORDS)


REPORT_MODEL_COLUMNS = (
    "модель / артикул",
    "модель/артикул",
    "модель",
    "артикул",
    "model",
    "part number",
    "part_number",
    "pn",
)
REPORT_QTY_COLUMNS = ("кол-во", "кол во", "количество", "qty", "quantity")
REPORT_TOTAL_RUB_COLUMNS = (
    "итого рыночная стоимость, руб.",
    "итого рыночная стоимость руб.",
    "рыночная стоимость, руб.",
    "рыночная стоимость руб.",
    "total rub",
    "total_rub",
)
REPORT_FILENAMES = ("Report.xlsx", "Report2.xlsx", "report3.xlsx")
ENRICHED_SOURCE_CANDIDATES = (
    "Honeywell_enriched.xlsx",
    "honeywell_enriched.xlsx",
    "Ханивелл_enriched.xlsx",
)
ENRICHED_PN_COLUMN_TOKENS = ("артикул", "model", "pn", "sku")
ENRICHED_QTY_COLUMN_TOKENS = ("qty", "кол", "quantity")
ENRICHED_UNIT_PRICE_COLUMN_TOKENS = ("price", "unitprice", "pricefound")
ENRICHED_LINE_VALUE_COLUMN_TOKENS = ("calculatedlotcost", "linevalue", "стоим")


def _column_map(df: pd.DataFrame) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for column in df.columns:
        key = str(column).strip().lower()
        if key not in mapped:
            mapped[key] = str(column)
    return mapped


def _normalize_token(value: object) -> str:
    return "".join(ch for ch in to_str(value).lower() if ch.isalnum())


def _match_columns_by_tokens(df: pd.DataFrame, tokens: tuple[str, ...]) -> list[str]:
    normalized = {str(column): _normalize_token(column) for column in df.columns}
    matched: list[str] = []
    for token in tokens:
        token_norm = _normalize_token(token)
        if not token_norm:
            continue
        for column in df.columns:
            column_text = str(column)
            if column_text in matched:
                continue
            if token_norm in normalized[column_text]:
                matched.append(column_text)
    return matched


def _choose_best_numeric_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    best_column: str | None = None
    best_score = -1.0
    for column in candidates:
        numeric = pd.to_numeric(df[column], errors="coerce")
        numeric_ratio = float(numeric.notna().mean()) if len(numeric) > 0 else 0.0
        positive_ratio = float((numeric > 0).mean()) if len(numeric) > 0 else 0.0
        score = (numeric_ratio * 1000.0) + positive_ratio
        if score > best_score and numeric_ratio > 0.0:
            best_score = score
            best_column = column
    return best_column


def _detect_enriched_columns(df: pd.DataFrame) -> dict[str, str | None]:
    pn_candidates = _match_columns_by_tokens(df, ENRICHED_PN_COLUMN_TOKENS)
    qty_candidates = _match_columns_by_tokens(df, ENRICHED_QTY_COLUMN_TOKENS)
    unit_price_candidates = _match_columns_by_tokens(df, ENRICHED_UNIT_PRICE_COLUMN_TOKENS)
    line_value_candidates = _match_columns_by_tokens(df, ENRICHED_LINE_VALUE_COLUMN_TOKENS)
    raw_text_candidates = _match_columns_by_tokens(df, ("rawtext", "description", "наимен", "column1"))

    pn_col = pn_candidates[0] if pn_candidates else None
    qty_col = _choose_best_numeric_column(df, qty_candidates) if qty_candidates else None
    if qty_col is None and qty_candidates:
        qty_col = qty_candidates[0]
    unit_price_col = _choose_best_numeric_column(df, unit_price_candidates) if unit_price_candidates else None
    line_value_col = _choose_best_numeric_column(df, line_value_candidates) if line_value_candidates else None
    raw_text_col = raw_text_candidates[0] if raw_text_candidates else None

    return {
        "pn_col": pn_col,
        "qty_col": qty_col,
        "unit_price_col": unit_price_col,
        "line_value_col": line_value_col,
        "raw_text_col": raw_text_col,
    }


def _resolve_enriched_source_path(base_dir: Path) -> Path | None:
    for candidate in ENRICHED_SOURCE_CANDIDATES:
        path = base_dir / candidate
        if path.exists():
            return path
    fallback = sorted(
        [
            path
            for path in base_dir.glob("*_enriched.xlsx")
            if path.is_file() and not path.name.startswith("~$")
        ],
        key=lambda path: path.name.lower(),
    )
    if fallback:
        return fallback[0]
    return None


def _extract_lot_id(raw: object) -> str:
    text = to_str(raw).strip()
    if not text:
        return ""
    match = re.search(r"\d+", text)
    if match:
        return match.group(0)
    return text


def _bool_from_any(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = to_str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n", ""}:
        return False
    return bool(value)


def _normalize_sku_code(value: object, row_index: int) -> str:
    text = to_str(value).upper()
    cleaned = re.sub(r"[^A-Z0-9]+", "", text)
    if cleaned:
        return cleaned
    return f"ROW{row_index}"


def _infer_fake(text: str, brand: str) -> bool:
    trusted_brands = {"honeywell", "esser", "notifier", "siemens", "draeger"}
    if to_str(brand).lower() in trusted_brands:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in LEGACY_FAKE_KEYWORDS)


def _is_generic_column_name(name: str) -> bool:
    return bool(re.fullmatch(r"column\d+", to_str(name).strip().lower()))


def _strip_text(value: object) -> str:
    return to_str(value).strip()


def _normalize_pn_key(value: object) -> str:
    text = _strip_text(value).upper()
    text = text.replace(" ", "")
    text = text.replace("\u00a0", "")
    text = re.sub(r"[^A-Z0-9]", "", text)
    return text


def build_base_key(pn: object) -> str:
    text_raw = _strip_text(pn).upper().replace(" ", "").replace("\u00a0", "")
    text_raw = re.sub(r"-[A-Z]{1,4}$", "", text_raw)
    cleaned = re.sub(r"[^A-Z0-9]", "", text_raw)
    if re.search(r"\d[A-Z]{1,4}$", cleaned):
        cleaned = re.sub(r"[A-Z]{1,4}$", "", cleaned)
    return cleaned


def _find_matching_column(cmap: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        candidate_norm = candidate.lower()
        for key, real in cmap.items():
            if candidate_norm in key:
                return real
    return None


def _upsert_report_entry(
    report_dict: dict[str, dict[str, float]],
    *,
    pn_key: str,
    qty_report: float,
    total_rub: float,
    usd_rate: float,
    source_file: str,
    pn_report_raw: object,
    source_kind: str = "report",
) -> None:
    if not pn_key or qty_report <= 0.0 or total_rub <= 0.0:
        return
    unit_price_usd = (total_rub / qty_report) / usd_rate
    if unit_price_usd <= 0.0:
        return
    existing = report_dict.get(pn_key)
    if existing is None or total_rub > to_float(existing.get("total_rub"), 0.0):
        report_dict[pn_key] = {
            "qty_report": qty_report,
            "total_rub": total_rub,
            "unit_price_usd": unit_price_usd,
            "source_file": source_file,
            "pn_report_raw": _strip_text(pn_report_raw) or pn_key,
            "source_kind": source_kind,
        }


def _build_report_dict(report_paths: list[Path], usd_rate: float) -> dict[str, dict[str, float]]:
    report_dict: dict[str, dict[str, float]] = {}
    for report_path in report_paths:
        if not report_path.exists():
            continue
        report_df = pd.read_excel(report_path, sheet_name="Table 1")
        cmap = _column_map(report_df)
        model_col = _find_matching_column(cmap, REPORT_MODEL_COLUMNS)
        qty_col = _find_matching_column(cmap, REPORT_QTY_COLUMNS)
        total_rub_col = _find_matching_column(cmap, REPORT_TOTAL_RUB_COLUMNS)

        if model_col is not None and qty_col is not None and total_rub_col is not None:
            for _, row in report_df.iterrows():
                model_raw = row.get(model_col)
                qty_report = max(0.0, to_float(row.get(qty_col), 0.0))
                total_rub = max(0.0, to_float(row.get(total_rub_col), 0.0))
                pn_key = _normalize_pn_key(model_raw)
                _upsert_report_entry(
                    report_dict,
                    pn_key=pn_key,
                    qty_report=qty_report,
                    total_rub=total_rub,
                    usd_rate=usd_rate,
                    source_file=report_path.name,
                    pn_report_raw=model_raw,
                    source_kind="report",
                )
        else:
            # Fallback for badly encoded legacy reports where headers are unreadable.
            raw_df = pd.read_excel(report_path, sheet_name="Table 1", header=None).dropna(how="all")
            for _, row in raw_df.iterrows():
                cells = list(row.values)

                pn_idx = -1
                pn_key = ""
                for idx, cell in enumerate(cells):
                    candidate = _normalize_pn_key(cell)
                    if not candidate:
                        continue
                    has_alpha = any(ch.isalpha() for ch in candidate)
                    has_digit = any(ch.isdigit() for ch in candidate)
                    if has_alpha and has_digit and len(candidate) >= 4:
                        pn_idx = idx
                        pn_key = candidate
                        break
                if not pn_key:
                    continue

                qty_report = 0.0
                for idx in range(max(0, pn_idx - 1), min(len(cells), pn_idx + 4)):
                    numeric = to_float(cells[idx], 0.0)
                    if numeric > 0 and abs(numeric - round(numeric)) < 1e-9:
                        if numeric <= 1_000_000:
                            qty_report = numeric
                            break
                if qty_report <= 0.0:
                    continue

                numeric_values = [to_float(cell, 0.0) for cell in cells]
                positive = [value for value in numeric_values if value > 0.0]
                if not positive:
                    continue
                total_rub = max(positive)
                _upsert_report_entry(
                    report_dict,
                    pn_key=pn_key,
                    qty_report=qty_report,
                    total_rub=total_rub,
                    usd_rate=usd_rate,
                    source_file=report_path.name,
                    pn_report_raw=pn_key,
                    source_kind="report",
                )

    if not report_dict:
        raise ValueError(
            "Report dictionary is empty after parsing valuation reports (Report.xlsx/Report2.xlsx/report3.xlsx) Table 1 sheets."
        )
    return report_dict


def _build_enriched_valuation_dict(
    enriched_path: Path,
    usd_rate: float,
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    valuation_dict: dict[str, dict[str, float]] = {}
    xls = pd.ExcelFile(enriched_path)
    rows_with_pn = 0
    rows_priced = 0
    rows_skipped_no_price = 0

    print(f"Using enriched valuation source: {enriched_path.name}")
    for sheet_name in xls.sheet_names:
        sheet_df = pd.read_excel(enriched_path, sheet_name=sheet_name).dropna(how="all")
        if sheet_df.empty:
            continue
        mapping = _detect_enriched_columns(sheet_df)
        print(
            f"ENRICHED COLUMN MAP [{sheet_name}]: "
            f"pn={mapping['pn_col']}, qty={mapping['qty_col']}, "
            f"unit_price={mapping['unit_price_col']}, line_value={mapping['line_value_col']}"
        )

        pn_col = mapping["pn_col"]
        qty_col = mapping["qty_col"]
        unit_price_col = mapping["unit_price_col"]
        line_value_col = mapping["line_value_col"]
        raw_text_col = mapping["raw_text_col"]
        if pn_col is None:
            continue

        for _, row in sheet_df.iterrows():
            pn_key = _normalize_pn_key(row.get(pn_col))
            if not pn_key and raw_text_col:
                pn_key = _extract_pn_semiai(to_str(row.get(raw_text_col)))
            if not pn_key:
                continue
            rows_with_pn += 1

            qty_report = max(0.0, to_float(row.get(qty_col), 0.0)) if qty_col else 0.0
            if qty_report <= 0.0 and raw_text_col:
                qty_report = _extract_qty_semiai(to_str(row.get(raw_text_col)))

            unit_price_rub = 0.0
            if unit_price_col is not None:
                unit_price_rub = max(0.0, to_float(row.get(unit_price_col), 0.0))
            if unit_price_rub <= 0.0 and qty_report > 0.0 and line_value_col is not None:
                line_value_rub = max(0.0, to_float(row.get(line_value_col), 0.0))
                if line_value_rub > 0.0:
                    unit_price_rub = line_value_rub / qty_report

            if qty_report <= 0.0 or unit_price_rub <= 0.0:
                rows_skipped_no_price += 1
                continue

            total_rub = unit_price_rub * qty_report
            _upsert_report_entry(
                valuation_dict,
                pn_key=pn_key,
                qty_report=qty_report,
                total_rub=total_rub,
                usd_rate=usd_rate,
                source_file=enriched_path.name,
                pn_report_raw=row.get(pn_col),
                source_kind="enriched",
            )
            rows_priced += 1

    stats = {
        "enriched_rows_with_pn": float(rows_with_pn),
        "enriched_rows_priced": float(rows_priced),
        "enriched_rows_skipped_no_price": float(rows_skipped_no_price),
        "enriched_dict_size": float(len(valuation_dict)),
    }
    return valuation_dict, stats


def _build_valuation_dict(
    *,
    enriched_path: Path | None,
    report_paths: list[Path],
    usd_rate: float,
) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    report_dict: dict[str, dict[str, float]] = {}
    report_stats: dict[str, float] = {"report_dict_size": 0.0, "report_files_used": 0.0}
    existing_report_paths = [path for path in report_paths if path.exists()]
    if existing_report_paths:
        report_dict = _build_report_dict(existing_report_paths, usd_rate)
        report_stats["report_dict_size"] = float(len(report_dict))
        report_stats["report_files_used"] = float(len(existing_report_paths))

    enriched_dict: dict[str, dict[str, float]] = {}
    enriched_stats: dict[str, float] = {
        "enriched_rows_with_pn": 0.0,
        "enriched_rows_priced": 0.0,
        "enriched_rows_skipped_no_price": 0.0,
        "enriched_dict_size": 0.0,
        "enriched_file_used": 0.0,
    }
    if enriched_path is not None and enriched_path.exists():
        enriched_dict, enriched_build_stats = _build_enriched_valuation_dict(enriched_path, usd_rate)
        enriched_stats.update(enriched_build_stats)
        enriched_stats["enriched_file_used"] = 1.0

    valuation_dict = dict(report_dict)
    valuation_dict.update(enriched_dict)  # Primary source priority: enriched > reports
    if not valuation_dict:
        raise ValueError(
            "Valuation dictionary is empty after parsing enriched/report valuation sources."
        )
    stats = {
        **report_stats,
        **enriched_stats,
        "valuation_dict_size": float(len(valuation_dict)),
    }
    return valuation_dict, stats


def _resolve_report_match(
    honeywell_pn_key: str,
    report_dict: dict[str, dict[str, float]],
    report_base_index: dict[str, str],
) -> tuple[str | None, str]:
    if honeywell_pn_key in report_dict:
        return honeywell_pn_key, "exact"

    honeywell_base = build_base_key(honeywell_pn_key)
    if honeywell_base and honeywell_base in report_base_index:
        report_key = report_base_index[honeywell_base]
        return report_key, "base"

    return None, "none"


def _first_non_empty_cell(row_values: list[Any]) -> str:
    for value in row_values:
        text = _strip_text(value)
        if text:
            return text
    return ""


def _build_full_row_text(row_values: list[Any]) -> str:
    chunks: list[str] = []
    numeric_pattern = re.compile(r"^\d+(?:[.,]\d+)?$")
    for value in row_values:
        text = _strip_text(value)
        if not text:
            continue
        if numeric_pattern.fullmatch(text):
            continue
        chunks.append(text)
    return " | ".join(chunks)


def _extract_pn_semiai(raw_text: str) -> str:
    text = _strip_text(raw_text)
    if not text:
        return ""
    upper = text.upper()
    markers = ("АРТИКУЛ", "МОДЕЛЬ", "MODEL", "PART", "PN", "P/N", "SKU")
    weighted_candidates: list[tuple[int, str]] = []

    for match in re.finditer(r"[A-Z0-9][A-Z0-9\-\/]{2,}", upper):
        token = match.group(0).strip("-/")
        if len(token) < 4:
            continue
        has_alpha = any(ch.isalpha() for ch in token)
        has_digit = any(ch.isdigit() for ch in token)
        if not (has_alpha and has_digit):
            continue
        score = 0
        if "-" in token or "/" in token:
            score += 2
        if len(token) >= 6:
            score += 1
        left_context = upper[max(0, match.start() - 25) : match.start()]
        if any(marker in left_context for marker in markers):
            score += 4
        if token.endswith("M") and token[:-1].isdigit():
            score -= 2
        weighted_candidates.append((score, token))

    if not weighted_candidates:
        return ""
    weighted_candidates.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    return _normalize_pn_key(weighted_candidates[0][1])


def _extract_qty_semiai(raw_text: str) -> float:
    text = _strip_text(raw_text)
    if not text:
        return 0.0
    keyed_patterns = (
        r"(?:КОЛ-?ВО|КОЛИЧЕСТВО|QTY|QUANTITY|PCS?|PC|ШТ)\D*(\d{1,7}(?:[.,]\d+)?)",
        r"(?:КОЛ-?ВО|КОЛИЧЕСТВО|QTY|QUANTITY)\s*[:=]?\s*(\d{1,7}(?:[.,]\d+)?)",
    )
    for pattern in keyed_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = to_float(match.group(1).replace(",", "."), 0.0)
            if 0.0 < value <= 1_000_000.0:
                return value
    tail = text[-40:]
    tail_numbers = re.findall(r"\d{1,7}", tail)
    if tail_numbers:
        value = to_float(tail_numbers[-1], 0.0)
        if 0.0 < value <= 1_000_000.0:
            return value
    return 0.0


def _infer_packaging_fake(raw_text: str, brand: str) -> bool:
    text = _strip_text(raw_text).lower()
    packaging_markers = (
        "seal",
        "box",
        "package",
        "packaging",
        "упаков",
        "короб",
        "пломб",
        "лента",
        "sticker",
    )
    if any(marker in text for marker in packaging_markers):
        trusted_brands = {"honeywell", "esser", "notifier", "siemens", "draeger"}
        if to_str(brand).lower() in trusted_brands:
            return False
        return True
    return _infer_fake(text, brand)


def _extract_qty_from_text(raw_text: str) -> float:
    text = to_str(raw_text)
    if not text:
        return 0.0

    keyed_patterns = (
        r"(?:qty|quantity|pcs?|pc|шт|кол-?во|количество)\D*(\d+(?:[.,]\d+)?)",
        r"(?:qty|quantity|pcs?|pc|шт|кол-?во|количество)\s*[:=]?\s*(\d+(?:[.,]\d+)?)",
    )
    for pattern in keyed_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = to_float(match.group(1).replace(",", "."), 0.0)
            if 0.0 <= value <= 1_000_000.0:
                return value

    # Fallback for vendor strings where qty is the last number.
    numeric_tokens = re.findall(r"\d+(?:[.,]\d+)?", text)
    if not numeric_tokens:
        return 0.0
    fallback = to_float(numeric_tokens[-1].replace(",", "."), 0.0)
    if 0.0 <= fallback <= 100_000.0:
        return fallback
    return 0.0


def _find_column_by_tokens(cmap: dict[str, str], tokens: tuple[str, ...]) -> str | None:
    for token in tokens:
        token_lower = token.lower()
        for key, value in cmap.items():
            if token_lower in key:
                return value
    return None


def _legacy_numeric_columns(df: pd.DataFrame) -> list[str]:
    numeric_cols: list[str] = []
    for column in df.columns:
        series = pd.to_numeric(df[column], errors="coerce")
        if int(series.notna().sum()) == 0:
            continue
        numeric_cols.append(str(column))
    return numeric_cols


def _choose_legacy_qty_column(df: pd.DataFrame, cmap: dict[str, str]) -> str | None:
    explicit = _find_column_by_tokens(cmap, ("qtylot", "qty", "quantity"))
    if explicit is not None:
        return explicit

    best_column: str | None = None
    best_score = -1.0
    for column in _legacy_numeric_columns(df):
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if series.empty:
            continue
        positives = series[series > 0]
        if positives.empty:
            continue
        integer_ratio = float((positives.round() == positives).mean())
        median_positive = float(positives.median())
        if median_positive <= 0 or median_positive > 10_000:
            continue
        score = integer_ratio
        if score > best_score:
            best_score = score
            best_column = column
    return best_column


def _choose_legacy_line_value_column(df: pd.DataFrame, cmap: dict[str, str], skip: set[str]) -> str | None:
    explicit = _find_column_by_tokens(cmap, ("calculatedlotcost", "linevalue", "lotcost", "total", "amount"))
    if explicit is not None:
        return explicit

    best_column: str | None = None
    best_mean = -1.0
    for column in _legacy_numeric_columns(df):
        if column in skip:
            continue
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if series.empty:
            continue
        positives = series[series > 0]
        if positives.empty:
            continue
        mean_value = float(positives.mean())
        if mean_value > best_mean:
            best_mean = mean_value
            best_column = column
    return best_column


def _choose_legacy_price_column(df: pd.DataFrame, cmap: dict[str, str], skip: set[str]) -> str | None:
    explicit = _find_column_by_tokens(cmap, ("pricefound", "unitprice", "price", "usd"))
    if explicit is not None:
        return explicit

    best_column: str | None = None
    best_score = -1.0
    for column in _legacy_numeric_columns(df):
        if column in skip:
            continue
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        if series.empty:
            continue
        positives = series[series > 0]
        if positives.empty:
            continue
        decimal_ratio = float((positives.round() != positives).mean())
        median_positive = float(positives.median())
        score = decimal_ratio
        if median_positive > 0 and median_positive < 1_000_000 and score >= best_score:
            best_score = score
            best_column = column
    return best_column


def _row_raw_text(
    raw_row: dict,
    *,
    preferred_raw_text_col: str | None,
    fallback_string_cols: list[str],
) -> str:
    if preferred_raw_text_col:
        direct = to_str(raw_row.get(preferred_raw_text_col), "")
        if direct:
            return direct
    chunks: list[str] = []
    for column in fallback_string_cols:
        value = raw_row.get(column)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                chunks.append(stripped)
    return " | ".join(chunks)


def _as_rows_by_lot(df: pd.DataFrame, *, forced_lot_id: str | None = None) -> dict[str, list[dict]]:
    cmap = _column_map(df)
    modern = MODERN_REQUIRED_COLUMNS.issubset(set(cmap))
    lots: dict[str, list[dict]] = {}
    counters: dict[str, int] = {}
    qty_col = _choose_legacy_qty_column(df, cmap)
    line_value_col = _choose_legacy_line_value_column(df, cmap, {qty_col} if qty_col else set())
    price_col = _choose_legacy_price_column(
        df,
        cmap,
        {col for col in (qty_col, line_value_col) if col is not None},
    )
    sku_col = _find_column_by_tokens(cmap, ("sku_code_normalized", "partnumber", "part_number", "part no", "sku", "model"))
    brand_col = _find_column_by_tokens(cmap, ("brand",))
    category_col = _find_column_by_tokens(cmap, ("category", "group", "type"))
    fake_col = _find_column_by_tokens(cmap, ("is_fake", "fake"))
    raw_text_col = _find_column_by_tokens(cmap, ("rawtext", "description", "desc", "column1"))
    sheet_col = cmap.get("sheetname", "")
    fallback_string_cols = [str(col) for col in df.columns if df[col].dtype == object]

    for _, row in df.iterrows():
        raw_row = row.to_dict()
        if modern:
            lot_id = forced_lot_id or _extract_lot_id(raw_row.get(cmap["lot_id"]))
            if not lot_id:
                continue
            counters[lot_id] = counters.get(lot_id, 0) + 1
            row_index = counters[lot_id]
            raw_text = _row_raw_text(raw_row, preferred_raw_text_col=raw_text_col, fallback_string_cols=fallback_string_cols)
            sku_code = _normalize_sku_code(raw_row.get(cmap["sku_code_normalized"]), row_index)
            explicit_brand = to_str(raw_row.get(cmap["brand"]), "")
            explicit_category = to_str(raw_row.get(cmap["category"]), "")
            sku = {
                "lot_id": lot_id,
                "row_index": row_index,
                "sku_code_normalized": sku_code,
                "base_unit_usd": max(0.0, to_float(raw_row.get(cmap["base_unit_usd"]), 0.0)),
                "raw_qty": max(0.0, to_float(raw_row.get(cmap["raw_qty"]), 0.0)),
                "condition_raw": to_float(raw_row.get(cmap["condition_raw"]), 1.0),
                "is_fake": _bool_from_any(raw_row.get(cmap["is_fake"])),
                "category": resolve_category(
                    explicit_category=explicit_category,
                    explicit_brand=explicit_brand,
                    sku_code=sku_code,
                    full_row_text=raw_text,
                ),
                "brand": explicit_brand or "unknown",
                "raw_text": raw_text,
                "full_row_text": raw_text,
            }
        else:
            lot_id = forced_lot_id
            if not lot_id:
                lot_id = _extract_lot_id(raw_row.get(sheet_col)) if sheet_col else ""
            if not lot_id:
                continue
            counters[lot_id] = counters.get(lot_id, 0) + 1
            row_index = counters[lot_id]

            raw_text = _row_raw_text(raw_row, preferred_raw_text_col=raw_text_col, fallback_string_cols=fallback_string_cols)
            qty = max(0.0, to_float(raw_row.get(qty_col), 0.0)) if qty_col else 0.0
            if qty <= 0.0:
                qty = _extract_qty_from_text(raw_text)

            line_value = max(0.0, to_float(raw_row.get(line_value_col), 0.0)) if line_value_col else 0.0
            price_found = max(0.0, to_float(raw_row.get(price_col), 0.0)) if price_col else 0.0
            base_unit_usd = price_found if price_found > 0 else (line_value / qty if qty > 0 else 0.0)

            sku_code_source = (
                (raw_row.get(sku_col) if sku_col else None)
                or f"{lot_id}_{row_index}"
            )
            sku_code = _normalize_sku_code(sku_code_source, row_index)
            explicit_brand = to_str(raw_row.get(brand_col), "") if brand_col else ""
            brand = normalize_brand(explicit_brand) or infer_brand_from_text(raw_text) or "unknown"
            explicit_category = to_str(raw_row.get(category_col), "") if category_col else ""
            category = resolve_category(
                explicit_category=explicit_category,
                explicit_brand=explicit_brand,
                sku_code=sku_code,
                full_row_text=raw_text,
            )
            explicit_fake = _bool_from_any(raw_row.get(fake_col)) if fake_col else False
            inferred_fake = _infer_fake(raw_text, brand)

            sku = {
                "lot_id": lot_id,
                "row_index": row_index,
                "sku_code_normalized": sku_code,
                "base_unit_usd": base_unit_usd,
                "raw_qty": qty,
                "condition_raw": 1.0,
                "is_fake": explicit_fake or inferred_fake,
                "category": category,
                "brand": brand,
                "raw_text": raw_text,
                "full_row_text": raw_text,
            }

        lots.setdefault(lot_id, []).append(sku)

    return lots


def _clean_sheet_frame(input_path: Path, sheet_name: str) -> pd.DataFrame:
    default_df = pd.read_excel(input_path, sheet_name=sheet_name)
    if all(_is_generic_column_name(str(col)) for col in default_df.columns):
        no_header_df = pd.read_excel(input_path, sheet_name=sheet_name, header=None)
        no_header_df.columns = [f"Column{i + 1}" for i in range(no_header_df.shape[1])]
        cleaned = no_header_df
    else:
        cleaned = default_df
    return cleaned.dropna(how="all")


def _load_rows_by_lot(input_path: Path) -> dict[str, list[dict]]:
    excel = pd.ExcelFile(input_path)
    sheet_names = [to_str(name) for name in excel.sheet_names]
    first_sheet_df = pd.read_excel(input_path, sheet_name=sheet_names[0])
    first_cmap = _column_map(first_sheet_df)

    if "lot_id" not in first_cmap and len(sheet_names) > 1:
        lots: dict[str, list[dict]] = {}
        for sheet_name in sheet_names:
            sheet_df = _clean_sheet_frame(input_path, sheet_name)
            if sheet_df.empty:
                continue
            rows = _as_rows_by_lot(sheet_df, forced_lot_id=sheet_name).get(sheet_name, [])
            if rows:
                lots[sheet_name] = rows
        return lots

    if len(sheet_names) == 1:
        single_df = _clean_sheet_frame(input_path, sheet_names[0])
        rows = _as_rows_by_lot(single_df)
        if rows:
            return rows
        fallback_rows = _as_rows_by_lot(single_df, forced_lot_id=sheet_names[0])
        return fallback_rows

    # Multi-sheet but modern schema: concatenate all sheets and parse normally.
    frames = []
    for sheet_name in sheet_names:
        frame = pd.read_excel(input_path, sheet_name=sheet_name)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return {}
    merged = pd.concat(frames, ignore_index=True)
    return _as_rows_by_lot(merged)


def _load_rows_by_lot_with_report_merge(
    input_path: Path,
    report_paths: list[Path],
    usd_rate: float,
    enriched_path: Path | None = None,
) -> tuple[dict[str, list[dict]], dict[str, object]]:
    report_dict, valuation_stats = _build_valuation_dict(
        enriched_path=enriched_path,
        report_paths=report_paths,
        usd_rate=usd_rate,
    )
    report_base_candidates: dict[str, list[str]] = {}
    for report_key in report_dict:
        base_key = build_base_key(report_key)
        if not base_key:
            continue
        report_base_candidates.setdefault(base_key, []).append(report_key)
    report_base_index: dict[str, str] = {}
    for base_key, candidates in report_base_candidates.items():
        if not candidates:
            continue
        selected = sorted(
            candidates,
            key=lambda key: (
                to_float(report_dict[key].get("total_rub"), 0.0),
                key,
            ),
            reverse=True,
        )[0]
        report_base_index[base_key] = selected

    excel = pd.ExcelFile(input_path)
    lots: dict[str, list[dict]] = {}
    total_rows_with_pn = 0
    exact_matches = 0
    base_matches = 0
    unmatched_rows = 0
    matched_from_enriched = 0
    matched_from_report = 0
    unmatched_pn: set[str] = set()

    for sheet_name in excel.sheet_names:
        sheet_df = pd.read_excel(input_path, sheet_name=sheet_name, header=None).dropna(how="all")
        if sheet_df.empty:
            continue
        lot_id = to_str(sheet_name)
        lot_rows: list[dict] = []
        row_index = 0
        for _, row in sheet_df.iterrows():
            row_values = list(row.values)
            raw_text = _first_non_empty_cell(row_values)
            if not raw_text:
                continue
            pn_key = _extract_pn_semiai(raw_text)
            if not pn_key:
                continue
            total_rows_with_pn += 1
            matched_report_key, matched_mode = _resolve_report_match(pn_key, report_dict, report_base_index)
            if matched_report_key is None:
                unmatched_rows += 1
                unmatched_pn.add(pn_key)
                continue
            report_entry = report_dict[matched_report_key]
            if matched_mode == "exact":
                exact_matches += 1
            elif matched_mode == "base":
                base_matches += 1
            source_kind = to_str(report_entry.get("source_kind"), "report").lower()
            if source_kind == "enriched":
                matched_from_enriched += 1
            else:
                matched_from_report += 1

            qty_extracted = _extract_qty_semiai(raw_text)
            qty_report = max(0.0, to_float(report_entry.get("qty_report"), 0.0))
            raw_qty = qty_extracted if qty_extracted > 0.0 else qty_report
            if raw_qty <= 0.0:
                unmatched_rows += 1
                unmatched_pn.add(pn_key)
                continue

            unit_price_usd = max(0.0, to_float(report_entry.get("unit_price_usd"), 0.0))
            row_index += 1
            full_row_text = _build_full_row_text(row_values) or raw_text
            brand = infer_brand_from_text(full_row_text) or "unknown"
            lot_rows.append(
                {
                    "lot_id": lot_id,
                    "row_index": row_index,
                    "sku_code_normalized": pn_key,
                    "base_unit_usd": unit_price_usd,
                    "raw_qty": raw_qty,
                    "condition_raw": 1.0,
                    "is_fake": _infer_packaging_fake(raw_text, brand),
                    "category": resolve_category(
                        explicit_category="",
                        explicit_brand="",
                        sku_code=pn_key,
                        full_row_text=full_row_text,
                    ),
                    "brand": brand,
                    "raw_text": raw_text,
                    "full_row_text": full_row_text,
                }
            )
        if lot_rows:
            lots[lot_id] = lot_rows

    total_matched = exact_matches + base_matches
    coverage = (total_matched / total_rows_with_pn) if total_rows_with_pn > 0 else 0.0
    stats = {
        "total_rows": float(total_rows_with_pn),
        "exact_matches": float(exact_matches),
        "base_matches": float(base_matches),
        "matched_from_enriched": float(matched_from_enriched),
        "matched_from_report": float(matched_from_report),
        "total_matched": float(total_matched),
        "unmatched_rows": float(unmatched_rows),
        "unmatched_unique_pn": float(len(unmatched_pn)),
        "match_coverage": coverage,
        "report_dict_size": valuation_stats.get("report_dict_size", 0.0),
        "report_files_used": valuation_stats.get("report_files_used", 0.0),
        "enriched_file_used": valuation_stats.get("enriched_file_used", 0.0),
        "enriched_dict_size": valuation_stats.get("enriched_dict_size", 0.0),
        "valuation_dict_size": valuation_stats.get("valuation_dict_size", 0.0),
        "enriched_rows_with_pn": valuation_stats.get("enriched_rows_with_pn", 0.0),
        "enriched_rows_priced": valuation_stats.get("enriched_rows_priced", 0.0),
        "enriched_rows_skipped_no_price": valuation_stats.get("enriched_rows_skipped_no_price", 0.0),
    }
    return lots, stats


def _lot_sort_key(lot_id: str) -> tuple[int, str]:
    text = to_str(lot_id)
    return (int(text), text) if text.isdigit() else (10**9, text)


def _extract_first_number(text: str) -> int | None:
    match = re.search(r"\d+", to_str(text))
    if match:
        return int(match.group(0))
    return None


def _compute_avg_brand_score(core_skus: list[dict], brand_score: dict) -> float:
    if not core_skus:
        return 0.0
    default_score = to_float(brand_score.get("_default", 0.50), 0.50)
    values: list[float] = []
    for sku in core_skus:
        brand = to_str(sku.get("brand"), "unknown")
        values.append(to_float(brand_score.get(brand, default_score), default_score))
    return sum(values) / float(len(values))


def _compute_confidence(
    lot: LotRecord,
    *,
    core_skus: list[dict],
    core_ratio: float,
    brand_score: dict,
) -> float:
    confidence = 0.0
    if all(to_str(sku.get("category")).lower() != "toxic_fake" for sku in core_skus):
        confidence += 0.2
    if lot.hhi_index < 0.30:
        confidence += 0.2
    if 0.65 <= core_ratio <= 0.85:
        confidence += 0.2
    if _compute_avg_brand_score(core_skus, brand_score) > 0.6:
        confidence += 0.2
    if lot.s2 > 0.4:
        confidence += 0.2
    return clamp(confidence, 0.0, 1.0)


def _compute_abs_score_100(
    *,
    q_category: float,
    q_ticket: float,
    q_density: float,
    unknown_exposure: float,
    m_concentration: float,
) -> float:
    q_category_clamped = clamp(to_float(q_category, 0.0), 0.0, 1.0)
    q_ticket_clamped = clamp(to_float(q_ticket, 0.0), 0.0, 1.0)
    q_density_clamped = clamp(to_float(q_density, 0.0), 0.0, 1.0)
    unknown_component = 1.0 - clamp(to_float(unknown_exposure, 0.0), 0.0, 1.0)
    concentration_penalty = clamp(1.0 - clamp(to_float(m_concentration, 0.0), 0.0, 1.0), 0.0, 1.0)
    concentration_component = 1.0 - concentration_penalty

    abs_01 = (
        0.25 * q_category_clamped
        + 0.25 * q_ticket_clamped
        + 0.20 * q_density_clamped
        + 0.15 * unknown_component
        + 0.15 * concentration_component
    )
    return round(clamp(abs_01, 0.0, 1.0) * 100.0, 6)


def _compute_abs_score_100_from_row(row: dict[str, Any]) -> float:
    return _compute_abs_score_100(
        q_category=to_float(row.get("S1"), 0.0),
        q_ticket=to_float(row.get("S2"), 0.0),
        q_density=to_float(row.get("S4"), 0.0),
        unknown_exposure=to_float(row.get("unknown_exposure"), 0.0),
        m_concentration=to_float(row.get("M_concentration"), 0.0),
    )


def _build_abs_score_validation_payload(full_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_lot_original: dict[str, float] = {}
    by_lot_reordered: dict[str, float] = {}
    by_lot_single: dict[str, float] = {}
    for row in full_rows:
        lot_id = to_str(row.get("lot_id"))
        if not lot_id:
            continue
        by_lot_original[lot_id] = _compute_abs_score_100_from_row(row)
    for row in reversed(full_rows):
        lot_id = to_str(row.get("lot_id"))
        if not lot_id:
            continue
        by_lot_reordered[lot_id] = _compute_abs_score_100_from_row(row)
    for row in full_rows:
        lot_id = to_str(row.get("lot_id"))
        if not lot_id:
            continue
        by_lot_single[lot_id] = _compute_abs_score_100_from_row(dict(row))

    all_lot_ids = sorted(set(by_lot_original.keys()) | set(by_lot_reordered.keys()) | set(by_lot_single.keys()), key=_lot_sort_key)
    order_changed_lots: list[str] = []
    single_changed_lots: list[str] = []
    max_order_abs_diff = 0.0
    max_single_abs_diff = 0.0
    for lot_id in all_lot_ids:
        score_original = to_float(by_lot_original.get(lot_id), 0.0)
        score_reordered = to_float(by_lot_reordered.get(lot_id), 0.0)
        score_single = to_float(by_lot_single.get(lot_id), 0.0)
        order_diff = abs(score_original - score_reordered)
        single_diff = abs(score_original - score_single)
        max_order_abs_diff = max(max_order_abs_diff, order_diff)
        max_single_abs_diff = max(max_single_abs_diff, single_diff)
        if order_diff > 1e-12:
            order_changed_lots.append(lot_id)
        if single_diff > 1e-12:
            single_changed_lots.append(lot_id)

    return {
        "formula": {
            "q_category_weight": 0.25,
            "q_ticket_weight": 0.25,
            "q_density_weight": 0.20,
            "unknown_component_weight": 0.15,
            "concentration_component_weight": 0.15,
            "capital_core_threshold": "independent_per_lot",
        },
        "lot_count": len(all_lot_ids),
        "checks": {
            "order_invariance": len(order_changed_lots) == 0,
            "single_lot_invariance": len(single_changed_lots) == 0,
        },
        "max_abs_diff": {
            "order_invariance": round(max_order_abs_diff, 12),
            "single_lot_invariance": round(max_single_abs_diff, 12),
        },
        "changed_lots": {
            "order_invariance": order_changed_lots,
            "single_lot_invariance": single_changed_lots,
        },
        "sample": [
            {
                "lot_id": lot_id,
                "abs_score_100": round(to_float(by_lot_original.get(lot_id), 0.0), 6),
            }
            for lot_id in all_lot_ids[:10]
        ],
    }


def _write_abs_score_validation_report(full_rows: list[dict[str, Any]], audits_dir: Path) -> Path:
    payload = _build_abs_score_validation_payload(full_rows)
    audits_dir.mkdir(parents=True, exist_ok=True)
    report_path = audits_dir / "abs_score_validation.json"
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return report_path


def _write_pn_liquidity_audits(
    pn_rows: list[dict[str, Any]],
    audits_dir: Path,
) -> tuple[Path, Path]:
    audits_dir.mkdir(parents=True, exist_ok=True)
    json_path = audits_dir / "pn_liquidity.json"
    csv_path = audits_dir / "pn_liquidity.csv"
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(pn_rows, handle, ensure_ascii=False, indent=2)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "pn_id",
                "vol_raw_usd",
                "vol_norm",
                "lot_count",
                "breadth_norm",
                "line_count",
                "avg_line_usd",
                "ticket_norm",
                "cat_liq_norm",
                "pn_liquidity",
                "flags",
            ],
        )
        writer.writeheader()
        for row in pn_rows:
            flags = row.get("flags")
            writer.writerow(
                {
                    "pn_id": to_str(row.get("pn_id")),
                    "vol_raw_usd": f"{to_float(row.get('vol_raw_usd'), 0.0):.6f}",
                    "vol_norm": f"{to_float(row.get('vol_norm'), 0.0):.6f}",
                    "lot_count": int(to_float(row.get("lot_count"), 0.0)),
                    "breadth_norm": f"{to_float(row.get('breadth_norm'), 0.0):.6f}",
                    "line_count": int(to_float(row.get("line_count"), 0.0)),
                    "avg_line_usd": f"{to_float(row.get('avg_line_usd'), 0.0):.6f}",
                    "ticket_norm": f"{to_float(row.get('ticket_norm'), 0.0):.6f}",
                    "cat_liq_norm": f"{to_float(row.get('cat_liq_norm'), 0.0):.6f}",
                    "pn_liquidity": f"{to_float(row.get('pn_liquidity'), 0.0):.6f}",
                    "flags": ",".join(flags) if isinstance(flags, list) else "",
                }
            )
    return json_path, csv_path


def _write_content_hash(
    df: pd.DataFrame,
    audits_dir: Path,
    basename: str,
    sort_by: list[str],
    float_precision: int = 6,
) -> tuple[Path, Path]:
    canon = df.copy()
    for col in canon.select_dtypes(include="number").columns:
        canon[col] = canon[col].round(float_precision)
    canon = canon.sort_values(by=sort_by, ascending=True, kind="mergesort").reset_index(drop=True)
    csv_bytes = canon.to_csv(index=False, lineterminator="\n").encode("utf-8")
    sha_hex = _sha256_from_bytes(csv_bytes)
    audits_dir.mkdir(parents=True, exist_ok=True)
    csv_path = audits_dir / f"{basename}.content.csv"
    sha_path = audits_dir / f"{basename}.content.sha256"
    csv_path.write_bytes(csv_bytes)
    sha_path.write_text(sha_hex + "\n", encoding="utf-8")
    return csv_path, sha_path


def _red_flags(lot: LotRecord, metadata: dict[str, float | int]) -> list[str]:
    flags: list[str] = []
    if lot.hhi_index > 0.30:
        flags.append("concentration>30%")
    if int(metadata.get("toxic_fake_count", 0)) > 0:
        flags.append(f"toxic_fake:{int(metadata.get('toxic_fake_count', 0))}")
    if lot.m_tail <= 0.75:
        flags.append("heavy_tail_penalty")
    return flags


def _short_reason(lot: LotRecord, metadata: dict[str, float | int]) -> str:
    reasons: list[str] = []
    if lot.s2 >= 0.6:
        reasons.append("strong_ticket_size")
    if lot.s4 >= 0.6:
        reasons.append("high_value_density")
    if lot.m_tail < 0.90:
        reasons.append("tail_penalty")
    if lot.m_concentration < 0.90:
        reasons.append("concentration_penalty")
    if int(metadata.get("toxic_fake_count", 0)) > 0:
        reasons.append(f"toxic_fake_tail:{int(metadata.get('toxic_fake_count', 0))}")
    if lot.hhi_index > 0.30:
        reasons.append("red_flag_hhi")
    if not reasons:
        reasons.append("balanced_profile")
    return "; ".join(reasons[:2])


def _load_reference_maps() -> tuple[dict, dict, dict, dict]:
    category_obsolescence = load_json_dict("data/category_obsolescence.json")
    brand_score = load_json_dict("data/brand_score.json")
    category_liquidity = load_json_dict("data/category_liquidity.json")
    category_volume_proxy = load_json_dict("data/category_volume_proxy.json")
    return (
        category_obsolescence,
        brand_score,
        category_liquidity,
        category_volume_proxy,
    )


def _sha256_from_bytes(raw: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(raw)
    return digest.hexdigest()


def _compute_refs_manifest(*, usd_rate: float, gov_config: GovernanceConfig) -> dict[str, Any]:
    lot_scoring_root = Path(__file__).resolve().parent
    refs_paths = {
        "category_obsolescence": Path("data/category_obsolescence.json"),
        "brand_score": Path("data/brand_score.json"),
        "category_liquidity": Path("data/category_liquidity.json"),
        "category_volume_proxy": Path("data/category_volume_proxy.json"),
    }
    refs_payload: dict[str, Any] = {}
    for ref_name, relative_path in refs_paths.items():
        target = lot_scoring_root / relative_path
        raw = target.read_bytes()
        parsed = json.loads(raw.decode("utf-8"))
        entry_count = len(parsed) if isinstance(parsed, dict) else 0
        refs_payload[ref_name] = {
            "path": str(relative_path).replace("\\", "/"),
            "sha256": _sha256_from_bytes(raw),
            "entry_count": entry_count,
        }

    taxonomy_relative = Path("data/taxonomy_version.json")
    taxonomy_path = lot_scoring_root / taxonomy_relative
    taxonomy_raw = taxonomy_path.read_bytes()
    taxonomy_payload = json.loads(taxonomy_raw.decode("utf-8"))
    taxonomy_version = to_str(taxonomy_payload.get("version"), "unknown")
    refs_payload["taxonomy_version"] = {
        "path": str(taxonomy_relative).replace("\\", "/"),
        "sha256": _sha256_from_bytes(taxonomy_raw),
    }

    return {
        "schema_version": "v4.1",
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "etl_usd_rate": float(usd_rate),
        "governance_config_version": gov_config.GOVERNANCE_VERSION,
        "hvl_threshold_usd": gov_config.HVL_THRESHOLD_USD,
        "taxonomy_version": taxonomy_version,
        "refs": refs_payload,
    }


_REFS_GUARD_KEYS = (
    "category_obsolescence",
    "brand_score",
    "category_liquidity",
    "category_volume_proxy",
    "taxonomy_version",
)


def _check_refs_drift(
    current_manifest: dict[str, Any],
    previous_manifest_path: Path,
    *,
    strict: bool,
) -> None:
    if not previous_manifest_path.exists():
        raise FileNotFoundError(f"STRICT_REFS_GUARD: previous manifest not found: {previous_manifest_path}")

    drifted: list[str] = []
    malformed_reason = "previous manifest is malformed or not a JSON object"
    try:
        parsed_previous = json.loads(previous_manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        previous_data: dict[str, Any] = {}
        drifted.append(malformed_reason)
    else:
        if isinstance(parsed_previous, dict):
            previous_data = parsed_previous
        else:
            previous_data = {}
            drifted.append(malformed_reason)

    prev_refs_raw = previous_data.get("refs", {})
    curr_refs_raw = current_manifest.get("refs", {})
    prev_refs = prev_refs_raw if isinstance(prev_refs_raw, dict) else {}
    curr_refs = curr_refs_raw if isinstance(curr_refs_raw, dict) else {}

    for key in _REFS_GUARD_KEYS:
        prev_entry = prev_refs.get(key, {})
        curr_entry = curr_refs.get(key, {})
        prev_sha = prev_entry.get("sha256") if isinstance(prev_entry, dict) else None
        curr_sha = curr_entry.get("sha256") if isinstance(curr_entry, dict) else None
        if prev_sha is None:
            drifted.append(f"{key}: missing in previous manifest")
        elif curr_sha is None:
            drifted.append(f"{key}: missing in current manifest")
        elif prev_sha != curr_sha:
            drifted.append(f"{key}: SHA256 mismatch ({str(prev_sha)[:8]}.. -> {str(curr_sha)[:8]}..)")

    if "etl_usd_rate" not in previous_data:
        drifted.append("etl_usd_rate: missing in previous manifest")
    else:
        prev_rate = to_float(previous_data.get("etl_usd_rate"), -1.0)
        curr_rate = to_float(current_manifest.get("etl_usd_rate"), -1.0)
        if prev_rate > 0 and curr_rate > 0 and abs(prev_rate - curr_rate) > 1e-5:
            drifted.append(f"etl_usd_rate: changed ({prev_rate} -> {curr_rate})")

    if not drifted:
        return

    msg = f"STRICT_REFS_GUARD: drift detected ({len(drifted)} item(s)):\n" + "\n".join(
        f"  - {item}" for item in drifted
    )
    if strict:
        raise RuntimeError(msg)
    print(f"\n[WARNING] {msg}\n", file=sys.stderr)


def _flatten_manifest_rows(payload: Any, prefix: str = "") -> list[dict[str, str]]:
    if isinstance(payload, dict):
        rows: list[dict[str, str]] = []
        for key, value in payload.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_flatten_manifest_rows(value, next_prefix))
        return rows
    return [{"key": prefix, "value": str(payload)}]


def _print_console_summary(rows: list[dict]) -> None:
    if not rows:
        print("No lots to display.")
        return

    print("\nTOP-5 LOTS")
    print("rank | lot_id | score_10 | confidence | core_ratio | total_effective_usd | red_flags")
    for row in rows[:5]:
        print(
            f"{row['rank']:>4} | {row['lot_id']:<6} | {row['score_10']:>7.2f} | "
            f"{row['confidence_score']:.2f} | {row['core_ratio']:.3f} | "
            f"{row['total_effective_usd']:>19.2f} | {row['red_flags']}"
        )
        print(
            f"  why: s2={row['S2']:.3f}, s4={row['S4']:.3f}, "
            f"m_hustle={row['M_hustle']:.3f}, m_concentration={row['M_concentration']:.3f}, m_tail={row['M_tail']:.3f}"
        )

    print("\nBOTTOM-5 LOTS")
    print("rank | lot_id | score_10 | confidence | core_ratio | total_effective_usd | red_flags")
    for row in rows[-5:]:
        print(
            f"{row['rank']:>4} | {row['lot_id']:<6} | {row['score_10']:>7.2f} | "
            f"{row['confidence_score']:.2f} | {row['core_ratio']:.3f} | "
            f"{row['total_effective_usd']:>19.2f} | {row['red_flags']}"
        )


def _collect_unknown_intelligence(processed: list[dict], audits_dir: Path, *, top_n: int = 20) -> Path:
    aggregated: dict[str, dict[str, object]] = {}
    for item in processed:
        lot = item.get("lot")
        lot_id = to_str(lot.lot_id) if isinstance(lot, LotRecord) else ""
        all_skus = item.get("all_skus")
        if not isinstance(all_skus, list):
            continue
        for sku in all_skus:
            if not isinstance(sku, dict):
                continue
            category = to_str(sku.get("category"), "unknown").lower()
            if category != "unknown":
                continue
            pn = _normalize_pn_key(
                sku.get("sku_code_normalized")
                or sku.get("sku_code")
                or sku.get("sku")
                or sku.get("part_number")
                or sku.get("model")
            )
            if not pn:
                continue
            if pn not in aggregated:
                aggregated[pn] = {
                    "pn": pn,
                    "total_effective_usd": 0.0,
                    "line_count": 0,
                    "lot_ids": set(),
                }
            entry = aggregated[pn]
            entry["total_effective_usd"] = to_float(entry.get("total_effective_usd"), 0.0) + max(
                0.0, to_float(sku.get("effective_line_usd"), 0.0)
            )
            entry["line_count"] = int(entry.get("line_count", 0)) + 1
            lot_ids = entry.get("lot_ids")
            if isinstance(lot_ids, set) and lot_id:
                lot_ids.add(lot_id)

    summary: list[dict[str, object]] = []
    for pn in sorted(aggregated.keys()):
        item = aggregated[pn]
        lot_ids = item.get("lot_ids")
        lot_count = len(lot_ids) if isinstance(lot_ids, set) else 0
        summary.append(
            {
                "pn": pn,
                "total_effective_usd": to_float(item.get("total_effective_usd"), 0.0),
                "line_count": int(item.get("line_count", 0)),
                "lot_count": lot_count,
            }
        )

    top_n = max(0, int(top_n))
    top_by_usd = sorted(
        summary,
        key=lambda row: (-to_float(row.get("total_effective_usd"), 0.0), to_str(row.get("pn"))),
    )[:top_n]
    top_by_freq = sorted(
        summary,
        key=lambda row: (
            -int(row.get("lot_count", 0)),
            -to_float(row.get("total_effective_usd"), 0.0),
            to_str(row.get("pn")),
        ),
    )[:top_n]

    rows: list[dict[str, str]] = []
    for idx, row in enumerate(top_by_usd, start=1):
        rows.append(
            {
                "ranking": "top_usd",
                "rank": str(idx),
                "pn": to_str(row.get("pn")),
                "total_effective_usd": f"{to_float(row.get('total_effective_usd'), 0.0):.6f}",
                "lot_count": str(int(row.get("lot_count", 0))),
                "line_count": str(int(row.get("line_count", 0))),
            }
        )
    for idx, row in enumerate(top_by_freq, start=1):
        rows.append(
            {
                "ranking": "top_freq",
                "rank": str(idx),
                "pn": to_str(row.get("pn")),
                "total_effective_usd": f"{to_float(row.get('total_effective_usd'), 0.0):.6f}",
                "lot_count": str(int(row.get("lot_count", 0))),
                "line_count": str(int(row.get("line_count", 0))),
            }
        )

    audits_dir.mkdir(parents=True, exist_ok=True)
    out_path = audits_dir / "unknown_intelligence.csv"
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ranking", "rank", "pn", "total_effective_usd", "lot_count", "line_count"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def _handle_baseline_and_delta(
    full_rows: list[dict],
    audits_dir: Path,
    *,
    save_baseline: bool = False,
) -> tuple[Path, Path | None]:
    baseline_path = audits_dir / "baseline_v35.json"
    delta_path = audits_dir / "delta_from_baseline.csv"
    audits_dir.mkdir(parents=True, exist_ok=True)

    current_rows = sorted(
        [
            {
                "lot_id": to_str(row.get("lot_id")),
                "rank": int(to_float(row.get("rank"), 0.0)),
                "score_10": round(to_float(row.get("score_10"), 0.0), 6),
                "final_score": round(to_float(row.get("final_score"), 0.0), 6),
                "unknown_exposure": round(to_float(row.get("unknown_exposure"), 0.0), 6),
                "abs_score_100": round(to_float(row.get("abs_score_100"), 0.0), 6),
            }
            for row in full_rows
        ],
        key=lambda row: (int(row["rank"]), to_str(row["lot_id"])),
    )

    baseline_exists_before = baseline_path.exists()
    if save_baseline or not baseline_exists_before:
        payload = {"schema_version": "v1", "lots": current_rows}
        with baseline_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        if not baseline_exists_before:
            return baseline_path, None
        if save_baseline:
            return baseline_path, None

    with baseline_path.open("r", encoding="utf-8") as handle:
        baseline_payload = json.load(handle)
    baseline_rows_raw = baseline_payload.get("lots", []) if isinstance(baseline_payload, dict) else []
    baseline_rows: list[dict[str, object]] = baseline_rows_raw if isinstance(baseline_rows_raw, list) else []
    baseline_by_lot = {
        to_str(row.get("lot_id")): row
        for row in baseline_rows
        if isinstance(row, dict) and to_str(row.get("lot_id"))
    }

    delta_rows: list[dict[str, object]] = []
    for current in current_rows:
        lot_id = to_str(current.get("lot_id"))
        baseline_row = baseline_by_lot.get(lot_id)
        if baseline_row is None:
            delta_rows.append(
                {
                    "lot_id": lot_id,
                    "rank": int(current.get("rank", 0)),
                    "baseline_rank": "",
                    "delta_rank": "",
                    "score_10": to_float(current.get("score_10"), 0.0),
                    "baseline_score_10": "",
                    "delta_score_10": "",
                    "unknown_exposure": to_float(current.get("unknown_exposure"), 0.0),
                    "baseline_unknown_exposure": "",
                    "delta_unknown_exposure": "",
                    "abs_score_100": to_float(current.get("abs_score_100"), 0.0),
                    "baseline_abs_score_100": "",
                    "delta_abs_score_100": "",
                }
            )
            continue
        rank_now = int(current.get("rank", 0))
        rank_then = int(to_float(baseline_row.get("rank"), 0.0))
        score_now = to_float(current.get("score_10"), 0.0)
        score_then = to_float(baseline_row.get("score_10"), 0.0)
        unknown_now = to_float(current.get("unknown_exposure"), 0.0)
        unknown_then = to_float(baseline_row.get("unknown_exposure"), 0.0)
        abs_now = to_float(current.get("abs_score_100"), 0.0)
        has_abs_then = "abs_score_100" in baseline_row and to_str(baseline_row.get("abs_score_100")) != ""
        abs_then = to_float(baseline_row.get("abs_score_100"), 0.0) if has_abs_then else None
        delta_rows.append(
            {
                "lot_id": lot_id,
                "rank": rank_now,
                "baseline_rank": rank_then,
                "delta_rank": rank_now - rank_then,
                "score_10": score_now,
                "baseline_score_10": score_then,
                "delta_score_10": round(score_now - score_then, 6),
                "unknown_exposure": unknown_now,
                "baseline_unknown_exposure": unknown_then,
                "delta_unknown_exposure": round(unknown_now - unknown_then, 6),
                "abs_score_100": abs_now,
                "baseline_abs_score_100": "" if abs_then is None else abs_then,
                "delta_abs_score_100": "" if abs_then is None else round(abs_now - abs_then, 6),
            }
        )

    with delta_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "lot_id",
                "rank",
                "baseline_rank",
                "delta_rank",
                "score_10",
                "baseline_score_10",
                "delta_score_10",
                "unknown_exposure",
                "baseline_unknown_exposure",
                "delta_unknown_exposure",
                "abs_score_100",
                "baseline_abs_score_100",
                "delta_abs_score_100",
            ],
        )
        writer.writeheader()
        writer.writerows(delta_rows)
    return baseline_path, delta_path


def run_full_ranking(
    input_path: Path,
    output_dir: Path,
    save_baseline: bool = False,
    usd_rate: float = 78.0,
    strict_refs_path: Path | None = None,
    strict_refs_fail: bool = False,
) -> tuple[Path, Path]:
    if usd_rate <= 0:
        raise ValueError("usd_rate must be > 0.")
    (
        category_obsolescence,
        brand_score,
        category_liquidity,
        category_volume_proxy,
    ) = _load_reference_maps()
    run_config = RunConfig()
    v4_config = V4Config()
    gov_config = GovernanceConfig()
    refs_manifest = _compute_refs_manifest(usd_rate=usd_rate, gov_config=gov_config)
    if strict_refs_path is not None:
        _check_refs_drift(refs_manifest, strict_refs_path, strict=strict_refs_fail)
    etl_config = EtlConfig()
    report_paths = [input_path.parent / name for name in REPORT_FILENAMES]
    enriched_path = _resolve_enriched_source_path(input_path.parent)
    merge_stats: dict[str, float] = {}

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
    print(f"Detected lots: {len(lots)}")
    if len(lots) < 5:
        raise ValueError(f"Too few lots detected: {len(lots)}. Expected at least 5.")

    processed: list[dict] = []
    for lot_id in sorted(lots.keys(), key=_lot_sort_key):
        raw_skus = lots[lot_id]
        try:
            assembled = run_etl_pipeline(raw_skus, etl_config)
        except ETLInvariantError as exc:
            raise ETLInvariantError(f"Lot {lot_id} failed ETL invariants: {exc}") from exc

        lot = LotRecord(lot_id=str(lot_id))
        apply_base_score(
            lot,
            core_skus=assembled.core_skus,
            all_skus=assembled.all_skus,
            category_obsolescence=category_obsolescence,
            brand_score=brand_score,
            category_liquidity=category_liquidity,
            category_volume_proxy=category_volume_proxy,
            config=run_config,
        )
        apply_final_score(
            lot,
            core_skus=assembled.core_skus,
            all_skus=assembled.all_skus,
            config=run_config,
        )
        lot.flags.extend(assembled.soft_flags)
        card = build_explanation_card(lot)
        confidence = _compute_confidence(
            lot,
            core_skus=assembled.core_skus,
            core_ratio=to_float(assembled.metadata.get("core_ratio"), 0.0),
            brand_score=brand_score,
        )

        processed.append(
            {
                "lot": lot,
                "metadata": assembled.metadata,
                "confidence": confidence,
                "card": card,
                "core_skus": assembled.core_skus,
                "all_skus": assembled.all_skus,
            }
        )

    rank_lots([item["lot"] for item in processed])
    pn_config = PnLiquidityConfig()
    pn_rows, pn_scores = compute_pn_liquidity(processed, category_liquidity, pn_config)
    lot_pn_metrics = compute_lot_avg_pn_liquidity(processed, pn_scores)

    full_rows: list[dict] = []
    for item in processed:
        lot: LotRecord = item["lot"]
        metadata: dict[str, float | int] = item["metadata"]
        core_skus: list[dict] = item["core_skus"]
        total_effective_usd = to_float(metadata.get("total_effective_usd"), 0.0)
        v4_scalars = compute_v4_scalars(
            lot=lot,
            metadata=metadata,
            core_skus=core_skus,
            category_obsolescence=category_obsolescence,
            run_config=run_config,
            v4_config=v4_config,
        )
        zone_v4 = compute_zone(to_float(v4_scalars.get("fas"), 0.0), gov_config)
        loss_attribution = compute_loss_attribution(v4_scalars)
        top_loss_reasons = compute_top_loss_reasons(loss_attribution)
        investor_summary = compute_investor_summary(v4_scalars, top_loss_reasons, zone_v4)
        governance_flags = compute_governance_flags(
            lot=lot,
            metadata=metadata,
            v4_scalars=v4_scalars,
            gov_config=gov_config,
        )
        red_flags = _red_flags(lot, metadata)
        lot_metrics = lot_pn_metrics.get(to_str(lot.lot_id), {"lot_avg_pn_liquidity": 0.0, "flags": []})
        full_rows.append(
            {
                "lot_id": lot.lot_id,
                "rank": lot.rank,
                "score_10": lot.score_10,
                "confidence_score": item["confidence"],
                "final_score": lot.final_score,
                "base_score": lot.base_score,
                "S1": lot.s1,
                "S2": lot.s2,
                "S3": lot.s3,
                "S4": lot.s4,
                "M_hustle": lot.m_hustle,
                "M_concentration": lot.m_concentration,
                "M_tail": lot.m_tail,
                "core_ratio": to_float(metadata.get("core_ratio"), 0.0),
                "total_effective_usd": total_effective_usd,
                "hhi": lot.hhi_index,
                "unknown_exposure": lot.unknown_exposure,
                "unknown_exposure_usd": lot.unknown_exposure_usd,
                "abs_score_100": _compute_abs_score_100(
                    q_category=lot.s1,
                    q_ticket=lot.s2,
                    q_density=lot.s4,
                    unknown_exposure=lot.unknown_exposure,
                    m_concentration=lot.m_concentration,
                ),
                "core_count": int(metadata.get("core_count", 0)),
                "tail_count": int(metadata.get("tail_count", 0)),
                "short_reason": _short_reason(lot, metadata),
                "red_flags": ",".join(red_flags),
                "top_minus": ",".join(item["card"].top_minus),
                "flags": ",".join(lot.flags),
                "AQ_v4": to_float(v4_scalars.get("aq"), 0.0),
                "FAS_v4": to_float(v4_scalars.get("fas"), 0.0),
                "M_Lifecycle": to_float(v4_scalars.get("m_lifecycle"), 1.0),
                "M_Unknown": to_float(v4_scalars.get("m_unknown"), 1.0),
                "KS_liquidity": to_float(v4_scalars.get("ks_liquidity"), 1.0),
                "KS_obsolescence": to_float(v4_scalars.get("ks_obsolescence"), 1.0),
                "Combined_Risk_v4": to_float(v4_scalars.get("combined_risk"), 0.0),
                "obs_weighted": to_float(v4_scalars.get("obs_weighted"), 0.0),
                "Top_Loss_Reasons": top_loss_reasons,
                "Investor_Summary": investor_summary,
                "Zone_v4": zone_v4,
                "loss_attribution_json": to_str(loss_attribution.get("loss_attribution_json")),
                "is_hvl": is_hvl(total_effective_usd, gov_config),
                "governance_flags": ",".join(governance_flags),
                "lot_avg_pn_liquidity": round(to_float(lot_metrics.get("lot_avg_pn_liquidity"), 0.0), 6),
            }
        )

    full_rows = sorted(full_rows, key=lambda row: int(row["rank"]))

    output_dir.mkdir(parents=True, exist_ok=True)
    audits_dir = output_dir / "audits"
    pn_liquidity_json_path, pn_liquidity_csv_path = _write_pn_liquidity_audits(pn_rows, audits_dir)
    unknown_intelligence_path = _collect_unknown_intelligence(processed, audits_dir, top_n=20)
    abs_score_validation_path = _write_abs_score_validation_report(full_rows, audits_dir)
    baseline_path, delta_path = _handle_baseline_and_delta(full_rows, audits_dir, save_baseline=save_baseline)
    refs_manifest_path = audits_dir / "refs_manifest.json"
    refs_manifest_path.write_text(json.dumps(refs_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    full_path = output_dir / "results_full_v341.xlsx"
    ranked_path = output_dir / "results_ranked_v341.xlsx"

    full_df = pd.DataFrame(full_rows)
    ranked_df = full_df[
        [
            "rank",
            "lot_id",
            "score_10",
            "abs_score_100",
            "confidence_score",
            "final_score",
            "core_ratio",
            "total_effective_usd",
            "hhi",
            "short_reason",
            "red_flags",
            "FAS_v4",
            "AQ_v4",
            "Top_Loss_Reasons",
            "Zone_v4",
            "is_hvl",
        ]
    ]
    with pd.ExcelWriter(full_path, engine="openpyxl") as writer:
        full_df.to_excel(writer, sheet_name="results", index=False)
        metadata_df = pd.DataFrame(_flatten_manifest_rows(refs_manifest))
        metadata_df.to_excel(writer, sheet_name="_metadata", index=False)
    ranked_df.to_excel(ranked_path, index=False)
    ranked_content_csv, ranked_content_sha = _write_content_hash(
        ranked_df, audits_dir, "results_ranked_v341", sort_by=["lot_id"],
    )
    full_content_csv, full_content_sha = _write_content_hash(
        full_df, audits_dir, "results_full_v341", sort_by=["rank", "lot_id"],
    )

    _print_console_summary(full_rows)
    if merge_stats:
        print("VAL SOURCE STATS:")
        print(
            f"exact={int(merge_stats.get('exact_matches', 0))}, "
            f"base={int(merge_stats.get('base_matches', 0))}, "
            f"matched_from_enriched={int(merge_stats.get('matched_from_enriched', 0))}, "
            f"matched_from_report={int(merge_stats.get('matched_from_report', 0))}, "
            f"total_rows={int(merge_stats.get('total_rows', 0))}, "
            f"total_matched={int(merge_stats.get('total_matched', 0))}, "
            f"unmatched={int(merge_stats.get('unmatched_rows', 0))}, "
            f"coverage={merge_stats.get('match_coverage', 0.0) * 100.0:.2f}%, "
            f"unmatched_unique_pn={int(merge_stats.get('unmatched_unique_pn', 0))}, "
            f"report_files_used={int(merge_stats.get('report_files_used', 0))}, "
            f"enriched_file_used={int(merge_stats.get('enriched_file_used', 0))}, "
            f"valuation_dict_size={int(merge_stats.get('valuation_dict_size', 0))}, "
            f"enriched_dict_size={int(merge_stats.get('enriched_dict_size', 0))}, "
            f"enriched_rows_with_pn={int(merge_stats.get('enriched_rows_with_pn', 0))}, "
            f"enriched_rows_priced={int(merge_stats.get('enriched_rows_priced', 0))}, "
            f"enriched_rows_skipped_no_price={int(merge_stats.get('enriched_rows_skipped_no_price', 0))}"
        )
    print("\nLot scores (lot_id | total_effective_usd | score_10 | confidence)")
    for row in full_rows:
        print(
            f"{row['lot_id']} | {row['total_effective_usd']:.2f} | "
            f"{row['score_10']:.2f} | {row['confidence_score']:.2f}"
        )
    print("\nTOP-5 (lot_id | score_10 | confidence | total_effective_usd)")
    for row in full_rows[:5]:
        print(
            f"{row['lot_id']} | {row['score_10']:.2f} | "
            f"{row['confidence_score']:.2f} | {row['total_effective_usd']:.2f}"
        )

    for target_lot in (14, 16):
        candidates = [row for row in full_rows if _extract_first_number(str(row.get("lot_id"))) == target_lot]
        if candidates:
            best = candidates[0]
            print(
                f"Lot {target_lot}: position={int(best['rank'])}, "
                f"score_10={best['score_10']:.2f}, confidence={best['confidence_score']:.2f}"
            )
        else:
            print(f"Lot {target_lot}: not found in ranking.")
    print(f"\nSaved full results to: {full_path}")
    print(f"Saved ranked results to: {ranked_path}")
    print(f"Saved PN liquidity JSON to: {pn_liquidity_json_path}")
    print(f"Saved PN liquidity CSV to: {pn_liquidity_csv_path}")
    print(f"Saved unknown intelligence to: {unknown_intelligence_path}")
    print(f"Saved abs score validation to: {abs_score_validation_path}")
    print(f"Saved refs manifest to: {refs_manifest_path}")
    print(f"Saved ranked content hash to: {ranked_content_sha}")
    print(f"Saved full content hash to: {full_content_sha}")
    print(f"Saved baseline snapshot to: {baseline_path}")
    if delta_path is not None:
        print(f"Saved baseline delta to: {delta_path}")
    return full_path, ranked_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LOT SCORING v3.4.1 full ranking.")
    parser.add_argument("--input", required=True, help="Path to input Excel file.")
    parser.add_argument(
        "--output-dir",
        default="downloads",
        help="Directory for output Excel files (default: downloads).",
    )
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="Overwrite audits/baseline_v35.json with current ranking snapshot.",
    )
    parser.add_argument(
        "--usd-rate",
        type=float,
        default=78.0,
        help="RUB/USD rate used when report merge converts RUB values to USD.",
    )
    parser.add_argument(
        "--strict-refs",
        type=str,
        default=None,
        metavar="MANIFEST_PATH",
        help="Path to previous refs manifest for strict drift checks.",
    )
    parser.add_argument(
        "--strict-refs-fail",
        action="store_true",
        help="Fail run when strict refs drift is detected.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    output_dir = Path(args.output_dir)
    strict_refs_path = Path(args.strict_refs) if args.strict_refs else None
    run_full_ranking(
        input_path,
        output_dir,
        save_baseline=args.save_baseline,
        usd_rate=args.usd_rate,
        strict_refs_path=strict_refs_path,
        strict_refs_fail=args.strict_refs_fail,
    )


if __name__ == "__main__":
    main()


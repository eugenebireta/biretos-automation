from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.lot_scoring.category_engine import BRAND_CATEGORY_MAP, CATEGORY_KEYWORDS, VALID_CATEGORIES
from scripts.lot_scoring.pipeline.helpers import normalize_category_key, to_float, to_str

try:
    from dotenv import load_dotenv as _load_dotenv
except Exception:  # noqa: BLE001
    _load_dotenv = None


SYSTEM_PROMPT = (
    "You are an industrial catalog auditor. "
    "Classify each row into one of these categories only: "
    "gas_safety, fire_safety, hvac_components, industrial_sensors, valves_actuators, "
    "it_hardware, packaging_materials, construction_supplies, toxic_fake, unknown. "
    "Return strict JSON only."
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _load_env_from_dotenv() -> None:
    if _load_dotenv is None:
        return
    try:
        # Single source of truth for API keys (price-checker/.env), then cwd .env
        _repo_root = Path(__file__).resolve().parent.parent.parent
        _price_checker_env = _repo_root / "price-checker" / ".env"
        if _price_checker_env.exists():
            _load_dotenv(_price_checker_env)
        _load_dotenv()
    except Exception:  # noqa: BLE001
        # Keep deterministic fallback to process env when dotenv load fails.
        return


def _parse_llm_json(content: str) -> list[dict[str, Any]]:
    text = to_str(content)
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end < start:
            return []
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    if isinstance(payload, dict) and "results" in payload and isinstance(payload["results"], list):
        payload = payload["results"]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _normalize_llm_item(item: dict[str, Any]) -> dict[str, Any]:
    category = normalize_category_key(item.get("llm_category"))
    if category not in VALID_CATEGORIES:
        category = "unknown"
    brand = to_str(item.get("llm_brand"), "unknown").lower() or "unknown"
    confidence = _clamp01(to_float(item.get("confidence"), 0.0))
    reason = to_str(item.get("reason"), "")
    slice_rank = int(to_float(item.get("slice_rank"), 0.0))
    sku_code = to_str(item.get("sku_code"), "")
    return {
        "slice_rank": slice_rank,
        "sku_code": sku_code,
        "llm_category": category,
        "llm_brand": brand,
        "confidence": confidence,
        "reason": reason,
    }


def _read_value_slice_rows(value_slice_csv_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with value_slice_csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "lot_id": to_str(row.get("lot_id")),
                    "slice_rank": int(to_float(row.get("slice_rank"), 0.0)),
                    "sku_code": to_str(row.get("sku_code")),
                    "qty": to_float(row.get("qty"), 0.0),
                    "effective_usd": to_float(row.get("effective_usd"), 0.0),
                    "category_engine": to_str(row.get("category_engine"), "unknown"),
                    "brand_engine": to_str(row.get("brand_engine"), "unknown"),
                    "raw_text": to_str(row.get("raw_text")),
                    "full_row_text": to_str(row.get("full_row_text")),
                }
            )
    return rows


def _group_rows_by_lot(rows: list[dict[str, Any]], selected_lots: list[str]) -> dict[str, list[dict[str, Any]]]:
    selected = set(selected_lots)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        lot_id = to_str(row.get("lot_id"))
        if lot_id not in selected:
            continue
        grouped.setdefault(lot_id, []).append(row)
    for lot_id in grouped:
        grouped[lot_id] = sorted(grouped[lot_id], key=lambda r: int(r["slice_rank"]))
    return grouped


def _chunk_rows(rows: list[dict[str, Any]], chunk_size: int) -> list[list[dict[str, Any]]]:
    if chunk_size <= 0:
        return [rows]
    return [rows[index : index + chunk_size] for index in range(0, len(rows), chunk_size)]


def _call_openai_batch(
    *,
    api_key: str,
    model: str,
    base_url: str,
    lot_id: str,
    batch_rows: list[dict[str, Any]],
    batch_label: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload_rows = [
        {
            "slice_rank": row["slice_rank"],
            "sku_code": row["sku_code"],
            "qty": row["qty"],
            "effective_usd": row["effective_usd"],
            "category_engine": row["category_engine"],
            "brand_engine": row["brand_engine"],
            "raw_text": row["raw_text"],
            "full_row_text": row["full_row_text"],
        }
        for row in batch_rows
    ]

    user_prompt = {
        "task": "Reclassify each row with same taxonomy only.",
        "rules": {
            "valid_categories": sorted(VALID_CATEGORIES),
            "output_format": "JSON array only",
            "required_fields": ["slice_rank", "sku_code", "llm_category", "llm_brand", "confidence", "reason"],
            "confidence_range": "0..1",
            "keep_reason_short": True,
        },
        "rows": payload_rows,
    }

    request_body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
    }

    endpoint = base_url.rstrip("/") + "/chat/completions"
    request = Request(
        endpoint,
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    debug: dict[str, Any] = {
        "lot_id": lot_id,
        "batch_label": batch_label,
        "rows_count": len(batch_rows),
        "model": model,
        "endpoint": endpoint,
        # NEVER LOG HEADERS: Authorization contains OPENAI_API_KEY.
        "request_body": request_body,
        "response_body": None,
        "error": None,
    }

    dry_network = to_str(os.getenv("LLM_AUDIT_DRY_NETWORK")).strip().lower() in {"1", "true", "yes"}
    if dry_network:
        print(
            f"[DEBUG] DRY_NETWORK enabled. Skip HTTP call for lot={lot_id}, "
            f"batch={batch_label or 'single'}, rows={len(batch_rows)}",
            flush=True,
        )
        debug["response_body"] = {"status": "network_test_ok"}
        return [], debug

    print(
        f"[DEBUG] Before HTTP call: lot={lot_id}, batch={batch_label or 'single'}, rows={len(batch_rows)}",
        flush=True,
    )
    try:
        with urlopen(request, timeout=60) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        debug["error"] = f"HTTPError {exc.code}: {exc.reason}"
        return [], debug
    except URLError as exc:
        debug["error"] = f"URLError: {exc.reason}"
        return [], debug
    except Exception as exc:  # noqa: BLE001
        debug["error"] = f"Exception: {exc}"
        return [], debug

    print(
        f"[DEBUG] After HTTP response: lot={lot_id}, batch={batch_label or 'single'}, bytes={len(raw_body)}",
        flush=True,
    )
    debug["response_body"] = raw_body
    try:
        parsed = json.loads(raw_body)
        content = to_str(parsed["choices"][0]["message"]["content"])
    except Exception as exc:  # noqa: BLE001
        debug["error"] = f"Invalid API response: {exc}"
        return [], debug

    raw_items = _parse_llm_json(content)
    normalized = [_normalize_llm_item(item) for item in raw_items]
    return normalized, debug


def run_llm_audit(
    *,
    value_slice_csv_path: Path,
    selected_lots: list[str],
    output_json_path: Path,
    raw_output_dir: Path,
) -> dict[str, Any]:
    raw_output_dir.mkdir(parents=True, exist_ok=True)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)

    print("[DEBUG] Entered run_llm_audit", flush=True)
    _load_env_from_dotenv()
    api_key = to_str(os.getenv("OPENAI_API_KEY"))
    model = to_str(os.getenv("OPENAI_MODEL"), "gpt-4o-mini")
    base_url = to_str(os.getenv("OPENAI_BASE_URL"), "https://api.openai.com/v1")

    if not api_key:
        skipped = {
            "status": "skipped",
            "reason": "OPENAI_API_KEY is not configured.",
            "selected_lots": selected_lots,
            "results": [],
            "raw_response_files": [],
        }
        output_json_path.write_text(json.dumps(skipped, ensure_ascii=False, indent=2), encoding="utf-8")
        return skipped

    rows = _read_value_slice_rows(value_slice_csv_path)
    grouped = _group_rows_by_lot(rows, selected_lots)

    all_results: list[dict[str, Any]] = []
    raw_files: list[str] = []

    for lot_id in selected_lots:
        lot_rows = grouped.get(lot_id, [])
        if not lot_rows:
            continue
        chunk_size = 25 if len(lot_rows) > 50 else max(1, len(lot_rows))
        chunks = _chunk_rows(lot_rows, chunk_size)
        print(
            f"[DEBUG] lot={lot_id}: rows={len(lot_rows)}, chunks={len(chunks)}, chunk_size={chunk_size}",
            flush=True,
        )

        llm_items: list[dict[str, Any]] = []
        lot_debugs: list[dict[str, Any]] = []
        for chunk_index, chunk_rows in enumerate(chunks, start=1):
            label = f"{chunk_index}/{len(chunks)}"
            chunk_items, chunk_debug = _call_openai_batch(
                api_key=api_key,
                model=model,
                base_url=base_url,
                lot_id=lot_id,
                batch_rows=chunk_rows,
                batch_label=label,
            )
            llm_items.extend(chunk_items)
            lot_debugs.append(chunk_debug)
        raw_path = raw_output_dir / f"lot_{lot_id}.json"
        raw_path.write_text(json.dumps({"batches": lot_debugs}, ensure_ascii=False, indent=2), encoding="utf-8")
        raw_files.append(str(raw_path))

        by_rank: dict[int, list[dict[str, Any]]] = {}
        by_sku: dict[str, list[dict[str, Any]]] = {}
        for item in llm_items:
            by_rank.setdefault(int(item.get("slice_rank", 0)), []).append(item)
            sku = to_str(item.get("sku_code"))
            by_sku.setdefault(sku, []).append(item)

        for row in lot_rows:
            slice_rank = int(row["slice_rank"])
            sku_code = to_str(row["sku_code"])
            chosen: dict[str, Any] | None = None

            rank_candidates = by_rank.get(slice_rank, [])
            if rank_candidates:
                chosen = rank_candidates.pop(0)
            else:
                sku_candidates = by_sku.get(sku_code, [])
                if sku_candidates:
                    chosen = sku_candidates.pop(0)

            if chosen is None:
                chosen = {
                    "llm_category": "unknown",
                    "llm_brand": "unknown",
                    "confidence": 0.0,
                    "reason": "No valid LLM output for row.",
                }

            all_results.append(
                {
                    "lot_id": lot_id,
                    "slice_rank": slice_rank,
                    "sku_code": sku_code,
                    "qty": row["qty"],
                    "effective_usd": row["effective_usd"],
                    "category_engine": row["category_engine"],
                    "brand_engine": row["brand_engine"],
                    "raw_text": row["raw_text"],
                    "full_row_text": row["full_row_text"],
                    "llm_category": to_str(chosen.get("llm_category"), "unknown"),
                    "llm_brand": to_str(chosen.get("llm_brand"), "unknown"),
                    "confidence": _clamp01(to_float(chosen.get("confidence"), 0.0)),
                    "reason": to_str(chosen.get("reason")),
                }
            )

    result_payload = {
        "status": "completed",
        "reason": "",
        "model": model,
        "selected_lots": selected_lots,
        "results": all_results,
        "raw_response_files": raw_files,
        "reference": {
            "valid_categories": sorted(VALID_CATEGORIES),
            "existing_brand_category_map": BRAND_CATEGORY_MAP,
            "keyword_categories": {key: list(value) for key, value in CATEGORY_KEYWORDS.items()},
        },
    }
    output_json_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return result_payload


"""training_logger.py — Central JSONL logging utilities for 6-point training data collection.

All pipeline modules write here in try/except — NEVER kills the pipeline.

Collection points:
1. photo_verdict_examples.jsonl      — KEEP/REJECT with context
2. page_ranking_examples.jsonl       — candidate URLs + ranked result
3. price_extraction_examples.jsonl   — HTML snippet + prompt + response
4. unit_judge_examples.jsonl         — price context + unit basis verdict
5. category_resolution_examples.jsonl— xlsx_hint + page + resolution
6. spec_extraction_examples.jsonl    — HTML snippet + extracted specs

Usage:
    from training_logger import log_page_ranking, log_unit_judge, log_category_resolution, log_spec_extraction
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent
_TRAINING_DIR = _ROOT / "training_data"


def _write_jsonl(path: Path, record: dict) -> None:
    """Append a single JSON record to a JSONL file. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.debug(f"training_logger write failed ({path.name}): {exc}")


def _ts() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ── Point 1: Photo verdict ─────────────────────────────────────────────────

def log_photo_verdict(
    pn: str,
    brand: str,
    photo_path: str,
    verdict: str,   # "KEEP" | "REJECT" | "NO_PHOTO"
    reason: str,
    source_url: str = "",
    thumbnail_path: str = "",
    vision_model: str = "",
) -> None:
    """Log photo verdict for training dataset."""
    try:
        record = {
            "dataset": "photo_verdict",
            "ts": _ts(),
            "pn": pn,
            "brand": brand,
            "photo_path": photo_path,
            "verdict": verdict,
            "reason": reason,
            "source_url": source_url,
            "thumbnail_path": thumbnail_path,
            "vision_model": vision_model,
        }
        _write_jsonl(_TRAINING_DIR / "photo_verdict_examples.jsonl", record)
    except Exception as exc:
        log.debug(f"log_photo_verdict failed: {exc}")


# ── Point 2: Page ranking ──────────────────────────────────────────────────

def log_page_ranking(
    pn: str,
    brand: str,
    candidate_urls: list[str],
    ranked_result: list[dict],
    method: str,  # "gemini" | "deterministic"
) -> None:
    """Log page ranking decisions for training dataset."""
    try:
        record = {
            "dataset": "page_ranking",
            "ts": _ts(),
            "pn": pn,
            "brand": brand,
            "candidate_count": len(candidate_urls),
            "candidate_urls": candidate_urls[:10],
            "ranked_result": [
                {"url": r.get("url", ""), "score": r.get("score", 0), "rejected": r.get("rejected", False)}
                for r in ranked_result[:10]
            ],
            "method": method,
        }
        _write_jsonl(_TRAINING_DIR / "page_ranking_examples.jsonl", record)
    except Exception as exc:
        log.debug(f"log_page_ranking failed: {exc}")


# ── Point 3: Price extraction ──────────────────────────────────────────────
# Already logged to shadow_log/price_extraction_*.jsonl by photo_pipeline.py
# This function adds an additional extract with HTML context snippet.

def log_price_extraction(
    pn: str,
    brand: str,
    html_snippet: str,
    prompt: str,
    response_raw: str,
    source_url: str = "",
    extracted_price: Optional[float] = None,
    currency: str = "",
) -> None:
    """Log price extraction with HTML context for fine-tuning."""
    try:
        record = {
            "dataset": "price_extraction",
            "ts": _ts(),
            "pn": pn,
            "brand": brand,
            "html_snippet": html_snippet[:2000] if html_snippet else "",
            "prompt": prompt[:1000] if prompt else "",
            "response_raw": response_raw[:2000] if response_raw else "",
            "source_url": source_url,
            "extracted_price": extracted_price,
            "currency": currency,
        }
        _write_jsonl(_TRAINING_DIR / "price_extraction_examples.jsonl", record)
    except Exception as exc:
        log.debug(f"log_price_extraction failed: {exc}")


# ── Point 4: Unit basis judge ──────────────────────────────────────────────

def log_unit_judge(
    pn: str,
    brand: str,
    price: float,
    currency: str,
    context_text: str,
    unit_basis: str,
    confidence: str,
    triggered: bool,
    trigger_reason: str,
    llm_raw: Optional[str] = None,
) -> None:
    """Log unit basis judge decisions for training dataset."""
    try:
        record = {
            "dataset": "unit_judge",
            "ts": _ts(),
            "pn": pn,
            "brand": brand,
            "price": price,
            "currency": currency,
            "context_text": context_text[:500] if context_text else "",
            "unit_basis": unit_basis,
            "confidence": confidence,
            "triggered": triggered,
            "trigger_reason": trigger_reason,
            "llm_raw": llm_raw[:500] if llm_raw else None,
        }
        _write_jsonl(_TRAINING_DIR / "unit_judge_examples.jsonl", record)
    except Exception as exc:
        log.debug(f"log_unit_judge failed: {exc}")


# ── Point 5: Category resolution ──────────────────────────────────────────

def log_category_resolution(
    pn: str,
    brand: str,
    xlsx_hint: Optional[str],
    page_category: Optional[str],
    source_tier: int,
    exact_pn_confirmed: bool,
    resolved_category: Optional[str],
    resolution_method: str,
    confidence: str,
) -> None:
    """Log category resolution decisions for training dataset."""
    try:
        record = {
            "dataset": "category_resolution",
            "ts": _ts(),
            "pn": pn,
            "brand": brand,
            "xlsx_hint": xlsx_hint,
            "page_category": page_category,
            "source_tier": source_tier,
            "exact_pn_confirmed": exact_pn_confirmed,
            "resolved_category": resolved_category,
            "resolution_method": resolution_method,
            "confidence": confidence,
        }
        _write_jsonl(_TRAINING_DIR / "category_resolution_examples.jsonl", record)
    except Exception as exc:
        log.debug(f"log_category_resolution failed: {exc}")


# ── Point 6: Spec extraction ───────────────────────────────────────────────

def log_spec_extraction(
    pn: str,
    brand: str,
    html_snippet: str,
    extracted_specs: dict,
    method: str,
    source_url: str = "",
) -> None:
    """Log spec extraction results for training dataset."""
    try:
        record = {
            "dataset": "spec_extraction",
            "ts": _ts(),
            "pn": pn,
            "brand": brand,
            "html_snippet": html_snippet[:1000] if html_snippet else "",
            "extracted_specs": extracted_specs,
            "spec_count": len(extracted_specs) if isinstance(extracted_specs, dict) else 0,
            "method": method,
            "source_url": source_url,
        }
        _write_jsonl(_TRAINING_DIR / "spec_extraction_examples.jsonl", record)
    except Exception as exc:
        log.debug(f"log_spec_extraction failed: {exc}")


if __name__ == "__main__":
    # Smoke test — write one example of each type
    print("Testing training_logger...")
    log_photo_verdict("TEST001", "Honeywell", "/photos/test.jpg", "KEEP", "product photo", "https://example.com")
    log_page_ranking("TEST001", "Honeywell", ["https://a.com", "https://b.com"], [{"url": "https://a.com", "score": 90.0, "rejected": False}], "deterministic")
    log_price_extraction("TEST001", "Honeywell", "<div>price 1500</div>", "What is the price?", '{"price": 1500}', "https://example.com", 1500.0, "RUB")
    log_unit_judge("TEST001", "Honeywell", 1500.0, "RUB", "price per unit", "per_unit", "high", False, "")
    log_category_resolution("TEST001", "Honeywell", "Термостаты", "thermostat", 1, True, "Термостаты", "page_confirmed", "high")
    log_spec_extraction("TEST001", "Honeywell", "<table><tr><td>Model</td><td>TEST001</td></tr></table>", {"Model": "TEST001"}, "table", "https://example.com")
    print("Done. Check training_data/ for example JSONL files.")

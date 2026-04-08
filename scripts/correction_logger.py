"""correction_logger.py — Owner correction logger for enrichment decisions.

Records human corrections to the experience log with salience=9 (highest priority).
These records are used for:
- Training local AI (correction pairs = highest-value training data)
- RAG retrieval (what was wrong and why)
- Audit trail (when was what corrected)

Usage:
  log_correction(pn, brand, field_corrected, original_value, corrected_value, reason)

Also provides:
  log_price_sanity_warning(pn, brand, price_usd, flags, source_url)
  retrospective_peha_corrections(evidence_dir) — batch log 33 PEHA category fixes
  retrospective_sanity_warnings(shadow_dir)   — batch log price sanity warnings
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

_ROOT = Path(_scripts_dir).parent
_SHADOW_LOG_DIR = _ROOT / "shadow_log"
CORRECTION_SCHEMA = "correction_v1"


def _read_jsonl(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_correction(
    pn: str,
    brand: str,
    field_corrected: str,
    original_value: str,
    corrected_value: str,
    reason: str,
    corrected_by: str = "owner",
    shadow_log_dir: Optional[Path] = None,
) -> None:
    """Log a human correction to the experience log.

    Args:
        pn:              Part number that was corrected.
        brand:           Brand name.
        field_corrected: Which field was wrong (e.g. 'expected_category').
        original_value:  The wrong value that was in the system.
        corrected_value: The correct value after correction.
        reason:          Why the original was wrong.
        corrected_by:    Who made the correction (default: 'owner').
        shadow_log_dir:  Override shadow log directory (for testing).
    """
    log_dir = shadow_log_dir or _SHADOW_LOG_DIR
    month = datetime.utcnow().strftime("%Y-%m")
    path = log_dir / f"experience_{month}.jsonl"

    summary = (
        f"CORRECTION {pn}: {field_corrected} "
        f"'{str(original_value)[:30]}' -> '{str(corrected_value)[:30]}'"
    )[:200]

    record = {
        "schema_version": CORRECTION_SCHEMA,
        "ts": datetime.utcnow().isoformat() + "Z",
        "pn": pn,
        "brand": brand,
        "task_type": "correction",
        "task_family": "correction",
        "decision": "corrected",
        "reason_code": "human_correction",
        "outcome": "corrected",
        "salience_score": 9,
        "summary": summary,
        "field_corrected": field_corrected,
        "original_value": str(original_value),
        "corrected_value": str(corrected_value),
        "reason": reason,
        "corrected_by": corrected_by,
        "correction_if_any": f"{field_corrected}: {original_value} -> {corrected_value}",
    }

    try:
        _append_jsonl(path, record)
    except Exception as exc:
        log.warning(f"log_correction write failed for {pn}: {exc}")


def log_price_sanity_warning(
    pn: str,
    brand: str,
    price_usd: float,
    flags: list[str],
    source_url: str = "",
    shadow_log_dir: Optional[Path] = None,
) -> None:
    """Log a price sanity warning as an experience event (salience=7)."""
    log_dir = shadow_log_dir or _SHADOW_LOG_DIR
    month = datetime.utcnow().strftime("%Y-%m")
    path = log_dir / f"experience_{month}.jsonl"

    summary = f"SANITY_WARNING {pn}: price={price_usd} flags={','.join(flags)}"[:200]

    record = {
        "schema_version": CORRECTION_SCHEMA,
        "ts": datetime.utcnow().isoformat() + "Z",
        "pn": pn,
        "brand": brand,
        "task_type": "price_sanity_warning",
        "task_family": "price_sanity",
        "decision": "warning",
        "reason_code": "|".join(flags),
        "outcome": "warning",
        "salience_score": 7,
        "summary": summary,
        "price_usd": price_usd,
        "flags": flags,
        "source_url": source_url,
    }

    try:
        _append_jsonl(path, record)
    except Exception as exc:
        log.warning(f"log_price_sanity_warning write failed for {pn}: {exc}")


def retrospective_peha_corrections(
    evidence_dir: Optional[Path] = None,
    shadow_log_dir: Optional[Path] = None,
) -> int:
    """Retrospectively log 33 PEHA category corrections as experience records.

    Reads category_fix_*.jsonl from shadow_log to get original→corrected mappings.
    Returns count of records written.
    """
    log_dir = shadow_log_dir or _SHADOW_LOG_DIR
    ev_dir = evidence_dir or (_ROOT / "downloads" / "evidence")
    count = 0

    # Read from category fix log
    fix_records = []
    for f in sorted(log_dir.glob("category_fix_*.jsonl")):
        fix_records.extend(_read_jsonl(f))

    for r in fix_records:
        pn = r.get("pn", "")
        if not pn:
            continue
        original = (r.get("original_category", "") or r.get("old_expected_category", "")
                    or r.get("old_category", ""))
        corrected = (r.get("corrected_category", "") or r.get("new_expected_category", "")
                     or r.get("new_category", ""))
        if not original or not corrected or original == corrected:
            continue
        brand = r.get("brand", "Honeywell")

        log_correction(
            pn=pn,
            brand=brand,
            field_corrected="expected_category",
            original_value=original,
            corrected_value=corrected,
            reason="xlsx source data had wrong Параметр: Тип товара for PEHA items — "
                   "numeric PNs labeled as Вентиль/Датчик but are PEHA electrical accessories",
            corrected_by="batch_fix_2026-04-08",
            shadow_log_dir=log_dir,
        )
        count += 1

    return count


def retrospective_sanity_warnings(
    shadow_log_dir: Optional[Path] = None,
) -> int:
    """Retrospectively log price sanity warnings as experience events.

    Reads price_sanity_audit_*.jsonl from shadow_log.
    Returns count of records written.
    """
    log_dir = shadow_log_dir or _SHADOW_LOG_DIR
    count = 0

    sanity_records = []
    for f in sorted(log_dir.glob("price_sanity_audit_*.jsonl")):
        sanity_records.extend(_read_jsonl(f))

    for r in sanity_records:
        pn = r.get("pn", "")
        status = (r.get("sanity_status", "") or r.get("status", "")
                  or r.get("sanity_result", ""))
        if not pn or status not in ("WARNING", "REJECT"):
            continue
        flags = r.get("flags", []) or r.get("sanity_flags", [])
        brand = r.get("brand", "Honeywell")
        price_usd = (r.get("price_usd") or r.get("price", 0)
                     or r.get("price_native", 0) or 0.0)

        log_price_sanity_warning(
            pn=pn,
            brand=brand,
            price_usd=float(price_usd),
            flags=flags if isinstance(flags, list) else [str(flags)],
            source_url=r.get("source_url", ""),
            shadow_log_dir=log_dir,
        )
        count += 1

    return count


if __name__ == "__main__":
    print("Running retrospective correction logging...")

    peha_count = retrospective_peha_corrections()
    print(f"  PEHA category corrections logged: {peha_count}")

    sanity_count = retrospective_sanity_warnings()
    print(f"  Price sanity warnings logged: {sanity_count}")

    print(f"\nTotal correction records: {peha_count + sanity_count}")
    print("Written to shadow_log/experience_YYYY-MM.jsonl (salience: corrections=9, warnings=7)")

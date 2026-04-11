"""golden_eval.py — Golden evaluation dataset loader and validator.

Provides a canonical format for human-verified eval records that can be used
to compare local AI vs cloud AI outputs across enrichment tasks.

Supported task types: price_extraction, spec_extraction, image_validation.

Dataset location: golden_eval/{task_type}.jsonl
Each record is one human-verified example with input + expected output.

Usage:
  from golden_eval import load_golden_dataset, validate_record

  records = load_golden_dataset("price_extraction")
  for r in records:
      errors = validate_record(r)
      if errors:
          print(f"Invalid: {errors}")
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_DEFAULT_GOLDEN_DIR = _ROOT / "golden_eval"

GOLDEN_EVAL_SCHEMA_VERSION = "golden_eval_v1"

# Required fields per task type
_REQUIRED_BASE = {"task_type", "pn", "expected_output", "verification_status"}
_REQUIRED_BY_TASK: dict[str, set[str]] = {
    "price_extraction": {"input_text"},
    "spec_extraction": {"input_text"},
    "image_validation": set(),
}
VALID_TASK_TYPES = set(_REQUIRED_BY_TASK.keys())
VALID_VERIFICATION_STATUSES = {"verified", "pending", "disputed"}


def validate_record(record: dict) -> list[str]:
    """Validate a golden eval record. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    # Base required fields
    for field in _REQUIRED_BASE:
        if field not in record or record[field] is None:
            errors.append(f"missing required field: {field}")

    task_type = record.get("task_type", "")
    if task_type not in VALID_TASK_TYPES:
        errors.append(f"invalid task_type: {task_type!r} (valid: {VALID_TASK_TYPES})")
    else:
        for field in _REQUIRED_BY_TASK.get(task_type, set()):
            if field not in record or not record[field]:
                errors.append(f"missing required field for {task_type}: {field}")

    vs = record.get("verification_status", "")
    if vs and vs not in VALID_VERIFICATION_STATUSES:
        errors.append(
            f"invalid verification_status: {vs!r} "
            f"(valid: {VALID_VERIFICATION_STATUSES})"
        )

    expected = record.get("expected_output")
    if expected is not None and not isinstance(expected, (dict, str)):
        errors.append(f"expected_output must be dict or str, got {type(expected).__name__}")

    return errors


def load_golden_dataset(
    task_type: str,
    golden_dir: Path = _DEFAULT_GOLDEN_DIR,
    *,
    verified_only: bool = False,
) -> list[dict]:
    """Load golden eval records for a task type.

    Args:
        task_type: One of VALID_TASK_TYPES
        golden_dir: Directory containing golden eval JSONL files
        verified_only: If True, skip records with verification_status != "verified"

    Returns:
        List of validated records. Invalid records are skipped with a warning.
    """
    path = golden_dir / f"{task_type}.jsonl"
    if not path.exists():
        return []

    records = []
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            errors = validate_record(record)
            if errors:
                continue

            if verified_only and record.get("verification_status") != "verified":
                continue

            records.append(record)
    return records


def create_golden_record(
    task_type: str,
    pn: str,
    expected_output: dict | str,
    *,
    input_text: str = "",
    brand: str = "Honeywell",
    source_url: str = "",
    evidence_ref: str = "",
    notes: str = "",
    verification_status: str = "pending",
) -> dict:
    """Create a new golden eval record with proper schema."""
    return {
        "schema_version": GOLDEN_EVAL_SCHEMA_VERSION,
        "task_type": task_type,
        "pn": pn,
        "brand": brand,
        "input_text": input_text,
        "expected_output": expected_output,
        "source_url": source_url,
        "evidence_ref": evidence_ref,
        "notes": notes,
        "verification_status": verification_status,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }


def save_golden_record(
    record: dict,
    golden_dir: Path = _DEFAULT_GOLDEN_DIR,
) -> Path:
    """Append a golden eval record to the appropriate JSONL file."""
    errors = validate_record(record)
    if errors:
        raise ValueError(f"Invalid golden record: {errors}")

    golden_dir.mkdir(parents=True, exist_ok=True)
    task_type = record["task_type"]
    path = golden_dir / f"{task_type}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def golden_summary(golden_dir: Path = _DEFAULT_GOLDEN_DIR) -> dict[str, dict]:
    """Return summary stats for all golden eval datasets."""
    summary: dict[str, dict] = {}
    if not golden_dir.exists():
        return summary

    for task_type in VALID_TASK_TYPES:
        records = load_golden_dataset(task_type, golden_dir)
        verified = [r for r in records if r.get("verification_status") == "verified"]
        summary[task_type] = {
            "total": len(records),
            "verified": len(verified),
            "pending": len(records) - len(verified),
        }
    return summary

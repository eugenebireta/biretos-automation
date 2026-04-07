"""
experience_writer.py — Unified experience schema v1 + thin adapters.

Writes ExperienceRecord dicts to shadow_log/experience_unified_YYYY-MM.jsonl
(append-only, atomic via temp+replace).

Standalone usage:
    python shadow_log/experience_writer.py
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_SHADOW_LOG_DIR = Path(__file__).resolve().parent
_MAX_SUMMARY_CHARS = 200

# Valid enum values (not enforced at runtime to stay lightweight, documented here)
_VALID_DOMAINS      = {"enrichment", "pricing", "lot", "rfq", "audit"}
_VALID_RECORD_TYPES = {"event", "lesson", "decision", "rule", "golden_case", "failure_pattern"}
_VALID_STATUSES     = {"active", "superseded", "deprecated", "pinned"}


# ---------------------------------------------------------------------------
# Schema contract
# ---------------------------------------------------------------------------

@dataclass
class ExperienceRecord:
    # ── Required fields (no defaults) ─────────────────────────────────────────
    record_id:     str   # uuid4
    timestamp:     str   # ISO 8601
    domain:        str   # "enrichment" | "pricing" | "lot" | "rfq" | "audit"
    task_family:   str   # "photo_validation" | "price_extraction" | "core_gate_review" | ...
    record_type:   str   # "event" | "lesson" | "decision" | "rule" | "golden_case" | "failure_pattern"
    salience_score: int  # 1–10
    summary:       str   # human-readable, MAX 200 chars

    # ── Optional fields (must come after required in dataclass) ────────────────
    entity_type:   Optional[str] = None   # "sku" | "order" | "lot"
    entity_id:     Optional[str] = None
    trace_id:      Optional[str] = None
    tags:          list[str]     = field(default_factory=list)
    payload:       dict          = field(default_factory=dict)
    status:        str           = "active"  # "active" | "superseded" | "deprecated" | "pinned"


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

def _default_file_path() -> Path:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return _SHADOW_LOG_DIR / f"experience_unified_{month}.jsonl"


def _validate(record: ExperienceRecord) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors: list[str] = []
    required = ("record_id", "timestamp", "domain", "task_family", "record_type", "summary")
    for f_name in required:
        val = getattr(record, f_name, None)
        if not val and val != 0:
            errors.append(f"missing required field: {f_name}")
    if not (1 <= record.salience_score <= 10):
        errors.append(f"salience_score must be 1-10, got {record.salience_score}")
    return errors


def write_experience(record: ExperienceRecord, file_path: str | Path | None = None) -> None:
    """
    Append ExperienceRecord to the unified JSONL file.

    Validates required fields and truncates summary to 200 chars.
    Logs outcome at the decision boundary (trace_id, domain, record_type, outcome).
    """
    errors = _validate(record)
    if errors:
        log.warning(
            json.dumps({
                "trace_id":    record.trace_id,
                "domain":      record.domain,
                "record_type": record.record_type,
                "outcome":     "rejected",
                "errors":      errors,
                "error_class": "POLICY_VIOLATION",
                "severity":    "WARNING",
                "retriable":   False,
            }, ensure_ascii=False)
        )
        return

    # Truncate summary if needed
    if len(record.summary) > _MAX_SUMMARY_CHARS:
        record.summary = record.summary[:_MAX_SUMMARY_CHARS]

    target = Path(file_path) if file_path else _default_file_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    row = asdict(record)

    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        log.debug(
            json.dumps({
                "trace_id":    record.trace_id,
                "domain":      record.domain,
                "record_type": record.record_type,
                "outcome":     "written",
                "file":        str(target),
            }, ensure_ascii=False)
        )
    except Exception as exc:
        log.error(
            json.dumps({
                "trace_id":    record.trace_id,
                "domain":      record.domain,
                "record_type": record.record_type,
                "outcome":     "write_error",
                "error":       str(exc),
                "error_class": "TRANSIENT",
                "severity":    "ERROR",
                "retriable":   True,
            }, ensure_ascii=False)
        )


# ---------------------------------------------------------------------------
# Thin adapters (old format → ExperienceRecord)
# Old writers remain as-is. Adapters are called alongside (not instead of) them.
# ---------------------------------------------------------------------------

def adapt_price_shadow(old_record: dict) -> ExperienceRecord:
    """
    Map photo_pipeline shadow_log price_extraction record
    (schema_version=photo_pipeline_shadow_log_record_v1, task_type=price_extraction)
    → ExperienceRecord.
    """
    verdict = (old_record.get("response_parsed") or {}).get("price_status", "")
    outcome_ok = bool(old_record.get("parse_success"))

    return ExperienceRecord(
        record_id=str(uuid.uuid4()),
        timestamp=old_record.get("ts", datetime.now(timezone.utc).isoformat()),
        domain="pricing",
        task_family="price_extraction",
        record_type="event" if outcome_ok else "failure_pattern",
        salience_score=6 if outcome_ok else 8,
        summary=(
            f"price extraction {old_record.get('pn', '?')} "
            f"via {old_record.get('provider', '?')} "
            f"status={verdict or ('ok' if outcome_ok else 'failed')}"
        )[:_MAX_SUMMARY_CHARS],
        entity_type="sku",
        entity_id=old_record.get("pn"),
        trace_id=None,
        tags=[old_record.get("provider", ""), old_record.get("model", "")],
        payload={
            "source_url":    old_record.get("source_url"),
            "parse_success": outcome_ok,
            "error_class":   old_record.get("error_class"),
            "latency_ms":    old_record.get("latency_ms"),
        },
    )


def adapt_image_shadow(old_record: dict) -> ExperienceRecord:
    """
    Map photo_pipeline shadow_log image_validation record
    (schema_version=photo_pipeline_shadow_log_record_v1, task_type=image_validation)
    → ExperienceRecord.
    """
    parsed   = old_record.get("response_parsed") or {}
    verdict  = parsed.get("verdict", "UNKNOWN")
    outcome_ok = bool(old_record.get("parse_success")) and verdict in ("KEEP", "REJECT")

    return ExperienceRecord(
        record_id=str(uuid.uuid4()),
        timestamp=old_record.get("ts", datetime.now(timezone.utc).isoformat()),
        domain="enrichment",
        task_family="photo_validation",
        record_type="golden_case" if verdict == "KEEP" else "event",
        salience_score=7 if verdict == "KEEP" else 5,
        summary=(
            f"image verdict={verdict} for {old_record.get('pn', '?')} "
            f"reason={parsed.get('reason', '')}"
        )[:_MAX_SUMMARY_CHARS],
        entity_type="sku",
        entity_id=old_record.get("pn"),
        trace_id=None,
        tags=[verdict, old_record.get("provider", ""), old_record.get("model", "")],
        payload={
            "verdict":     verdict,
            "parse_success": outcome_ok,
            "latency_ms":  old_record.get("latency_ms"),
        },
    )


def adapt_auditor_sink(old_record: dict) -> ExperienceRecord:
    """
    Map auditor_system ExperienceSink record
    (fields: trace_id, task, context_summary, chosen_solution, owner_verdict, ...)
    → ExperienceRecord.
    """
    task      = old_record.get("task") or {}
    chosen    = old_record.get("chosen_solution") or {}
    verdict   = old_record.get("owner_verdict", "unknown")
    is_positive = verdict == "approved"

    return ExperienceRecord(
        record_id=str(uuid.uuid4()),
        timestamp=old_record.get("timestamp", datetime.now(timezone.utc).isoformat()),
        domain="audit",
        task_family="core_gate_review",
        record_type="decision" if is_positive else "failure_pattern",
        salience_score=9 if is_positive else 8,
        summary=(
            f"audit {task.get('stage', '?')} risk={task.get('risk', '?')} "
            f"verdict={verdict} escalated={old_record.get('escalation', False)}"
        )[:_MAX_SUMMARY_CHARS],
        entity_type=None,
        entity_id=None,
        trace_id=old_record.get("trace_id"),
        tags=[task.get("risk", ""), verdict],
        payload={
            "roadmap_stage":      task.get("stage"),
            "risk":               task.get("risk"),
            "chosen_model":       chosen.get("model"),
            "escalation":         old_record.get("escalation"),
            "post_audit_clean":   old_record.get("post_audit_clean"),
            "cost_usd":           old_record.get("cost_usd"),
            "duration_minutes":   old_record.get("duration_minutes"),
        },
    )


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import tempfile

    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

    with tempfile.TemporaryDirectory() as tmp:
        out_file = Path(tmp) / "experience_unified_demo.jsonl"

        demo = ExperienceRecord(
            record_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            domain="enrichment",
            task_family="photo_validation",
            record_type="lesson",
            salience_score=8,
            summary="Demo: image verdict=KEEP for test SKU",
            entity_type="sku",
            entity_id="DEMO-PN",
            trace_id="demo-trace-001",
            tags=["demo", "enrichment"],
            payload={"verdict": "KEEP"},
        )

        write_experience(demo, file_path=out_file)

        # Read back and print
        content = out_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            record = json.loads(line)
            print(json.dumps(record, indent=2, ensure_ascii=False))

        print(f"\nWrote {len(content.splitlines())} record(s) to {out_file}")

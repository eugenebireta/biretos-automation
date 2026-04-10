"""corpus_status.py — Training corpus readiness report.

Scans shadow_log/ and golden_eval/ to report how much data is available
for each enrichment task type, quality metrics, and fine-tune readiness.

Usage:
  python scripts/corpus_status.py [--shadow-dir shadow_log] [--json]

Output: human-readable console report (or JSON with --json flag).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

_ROOT = Path(_scripts_dir).parent
_DEFAULT_SHADOW_DIR = _ROOT / "shadow_log"
_DEFAULT_GOLDEN_DIR = _ROOT / "golden_eval"

# Minimum records needed for fine-tune readiness per task type
MIN_FOR_FINETUNE = {
    "price_extraction": 500,
    "spec_extraction": 200,
    "image_validation": 100,
    "correction": 50,
    "experience_dpo": 20,
}


def _read_jsonl_records(path: Path) -> list[dict]:
    """Read all records from a JSONL file."""
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


def _read_all_in_dir(directory: Path, pattern: str) -> list[dict]:
    """Read all JSONL files matching pattern."""
    records = []
    if not directory.exists():
        return records
    for f in sorted(directory.glob(pattern)):
        records.extend(_read_jsonl_records(f))
    return records


def _count_field(records: list[dict], field: str) -> int:
    """Count records where field is non-null and non-empty."""
    return sum(1 for r in records if r.get(field))


def _latest_ts(records: list[dict]) -> str:
    """Get the latest timestamp from records."""
    timestamps = [r.get("ts", "") for r in records if r.get("ts")]
    return max(timestamps) if timestamps else ""


def corpus_status(
    shadow_dir: Path = _DEFAULT_SHADOW_DIR,
    golden_dir: Path = _DEFAULT_GOLDEN_DIR,
) -> dict:
    """Build corpus status report.

    Returns dict with per-task-type stats and overall readiness.
    """
    report: dict = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "shadow_dir": str(shadow_dir),
        "tasks": {},
        "totals": {},
    }

    # ── Price extraction ─────────────────────────────────────────────────
    price_records = _read_all_in_dir(shadow_dir, "price_extraction_*.jsonl")
    price_with_response = [r for r in price_records if r.get("response_raw")]
    report["tasks"]["price_extraction"] = {
        "total": len(price_records),
        "with_response": len(price_with_response),
        "with_prompt_version": _count_field(price_records, "prompt_version"),
        "with_trace_id": _count_field(price_records, "trace_id"),
        "latest_ts": _latest_ts(price_records),
        "min_for_finetune": MIN_FOR_FINETUNE["price_extraction"],
    }

    # ── Spec extraction ──────────────────────────────────────────────────
    spec_records = _read_all_in_dir(shadow_dir, "spec_extraction_*.jsonl")
    report["tasks"]["spec_extraction"] = {
        "total": len(spec_records),
        "with_response": len([r for r in spec_records if r.get("response_raw")]),
        "with_prompt_version": _count_field(spec_records, "prompt_version"),
        "with_trace_id": _count_field(spec_records, "trace_id"),
        "latest_ts": _latest_ts(spec_records),
        "min_for_finetune": MIN_FOR_FINETUNE["spec_extraction"],
    }

    # ── Image validation ─────────────────────────────────────────────────
    img_records = _read_all_in_dir(shadow_dir, "image_validation_*.jsonl")
    report["tasks"]["image_validation"] = {
        "total": len(img_records),
        "with_response": len([r for r in img_records if r.get("response_raw")]),
        "with_prompt_version": _count_field(img_records, "prompt_version"),
        "with_trace_id": _count_field(img_records, "trace_id"),
        "latest_ts": _latest_ts(img_records),
        "min_for_finetune": MIN_FOR_FINETUNE["image_validation"],
    }

    # ── Corrections ──────────────────────────────────────────────────────
    experience_records = _read_all_in_dir(shadow_dir, "experience_*.jsonl")
    corrections = [r for r in experience_records if r.get("task_type") == "correction"]
    sanity_warnings = [r for r in experience_records if r.get("task_type") == "price_sanity_warning"]
    report["tasks"]["correction"] = {
        "total": len(corrections),
        "with_trace_id": _count_field(corrections, "trace_id"),
        "with_source": _count_field(corrections, "source"),
        "with_ai_model": _count_field(corrections, "ai_model"),
        "sanity_warnings": len(sanity_warnings),
        "latest_ts": _latest_ts(corrections),
        "min_for_finetune": MIN_FOR_FINETUNE["correction"],
    }

    # ── Experience / DPO pairs ───────────────────────────────────────────
    exp_log_dir = _ROOT / "auditor_system"
    exp_log_records: list[dict] = []
    for sub in ["experience_log", "anti_patterns"]:
        sub_dir = exp_log_dir / sub
        if sub_dir.exists():
            for f in sub_dir.glob("*.jsonl"):
                exp_log_records.extend(_read_jsonl_records(f))
    dpo_pairs = [r for r in exp_log_records if r.get("rejected_solution") and r.get("chosen_solution")]
    report["tasks"]["experience_dpo"] = {
        "total": len(exp_log_records),
        "dpo_pairs": len(dpo_pairs),
        "with_proposal_text": sum(
            1 for r in exp_log_records
            if r.get("chosen_solution", {}).get("proposal_text")
        ),
        "latest_ts": _latest_ts(exp_log_records),
        "min_for_finetune": MIN_FOR_FINETUNE["experience_dpo"],
    }

    # ── Golden eval ──────────────────────────────────────────────────────
    try:
        from golden_eval import golden_summary
        report["golden_eval"] = golden_summary(golden_dir)
    except Exception:
        report["golden_eval"] = {}

    # ── Totals ───────────────────────────────────────────────────────────
    total_records = sum(t.get("total", 0) for t in report["tasks"].values())
    ready_tasks = 0
    for task_name, task_data in report["tasks"].items():
        total = task_data.get("total", 0)
        needed = task_data.get("min_for_finetune", 50)
        task_data["finetune_ready"] = total >= needed
        task_data["records_needed"] = max(0, needed - total)
        if task_data["finetune_ready"]:
            ready_tasks += 1

    report["totals"] = {
        "total_records": total_records,
        "tasks_ready": ready_tasks,
        "tasks_total": len(report["tasks"]),
        "overall_ready": ready_tasks == len(report["tasks"]),
    }

    return report


def format_report(report: dict) -> str:
    """Format corpus status report for console output."""
    lines = [
        "",
        "=" * 65,
        "  CORPUS STATUS — Training Data Readiness Report",
        "=" * 65,
        "",
    ]

    for task_name, task_data in report.get("tasks", {}).items():
        total = task_data.get("total", 0)
        needed = task_data.get("min_for_finetune", 50)
        ready = task_data.get("finetune_ready", False)
        status = "READY" if ready else f"need {task_data.get('records_needed', 0)} more"
        bar = min(total, needed)
        pct = (bar / needed * 100) if needed else 100

        lines.append(f"  {task_name:25s}  {total:5d} / {needed:5d}  [{status}]  {pct:5.1f}%")

        # Detail fields
        details = []
        if "with_response" in task_data:
            details.append(f"with_response={task_data['with_response']}")
        if "with_prompt_version" in task_data:
            pv = task_data["with_prompt_version"]
            if pv > 0:
                details.append(f"prompt_version={pv}")
        if "dpo_pairs" in task_data:
            details.append(f"dpo_pairs={task_data['dpo_pairs']}")
        if "with_source" in task_data:
            details.append(f"with_source={task_data['with_source']}")
        latest = task_data.get("latest_ts", "")
        if latest:
            details.append(f"latest={latest[:10]}")
        if details:
            lines.append(f"  {'':25s}  {', '.join(details)}")
        lines.append("")

    # Golden eval
    golden = report.get("golden_eval", {})
    if golden:
        lines.append("  GOLDEN EVAL:")
        for task_name, gdata in golden.items():
            lines.append(
                f"    {task_name:23s}  {gdata.get('verified', 0):3d} verified"
                f"  / {gdata.get('total', 0):3d} total"
            )
        lines.append("")

    # Overall
    totals = report.get("totals", {})
    lines.append("-" * 65)
    lines.append(
        f"  TOTAL: {totals.get('total_records', 0)} records"
        f"  |  {totals.get('tasks_ready', 0)}/{totals.get('tasks_total', 0)} tasks ready"
        f"  |  {'READY' if totals.get('overall_ready') else 'NOT READY'}"
    )
    lines.append("=" * 65)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Training corpus readiness report")
    parser.add_argument("--shadow-dir", default=str(_DEFAULT_SHADOW_DIR))
    parser.add_argument("--golden-dir", default=str(_DEFAULT_GOLDEN_DIR))
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args(argv)

    report = corpus_status(
        shadow_dir=Path(args.shadow_dir),
        golden_dir=Path(args.golden_dir),
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())

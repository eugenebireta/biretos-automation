"""
experience_reader.py — P5: Read past execution experience to improve future directives.

Scans shadow_log/experience_YYYY-MM.jsonl for patterns:
  - Common failure reasons (drift, tier-1 touch, test failures)
  - Task-specific history (same task_id retried before?)
  - Correction patterns (what worked after retry?)

Produces a "lessons learned" block for injection into directives.

Usage:
    from experience_reader import get_lessons_for_task
    lessons = get_lessons_for_task("my-task-id", risk_class="SEMI")
    # → "## Lessons from Past Runs\n- Previous attempt drifted..."
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SHADOW_LOG_DIR = ROOT / "shadow_log"
SCHEMA_VERSION = "execution_experience_v1"


def _load_experience_records(months: int = 3) -> list[dict]:
    """Load execution experience records from recent months.

    Only loads records with schema_version=execution_experience_v1.
    Older experience_log_v1 records are skipped (no trace_id, no structure).

    Args:
        months: How many months of logs to scan (default 3).

    Returns:
        List of experience record dicts, newest first.
    """
    from datetime import datetime, timezone, timedelta

    records = []
    now = datetime.now(timezone.utc)

    for m in range(months):
        dt = now - timedelta(days=30 * m)
        path = SHADOW_LOG_DIR / f"experience_{dt.strftime('%Y-%m')}.jsonl"
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    if record.get("schema_version") == SCHEMA_VERSION:
                        records.append(record)
                except json.JSONDecodeError:
                    continue
        except OSError as exc:
            logger.warning("Failed to read %s: %s", path, exc)

    # Sort newest first
    records.sort(key=lambda r: r.get("ts", ""), reverse=True)
    return records


def get_task_history(task_id: str, records: list[dict] | None = None) -> list[dict]:
    """Get all experience records for a specific task_id."""
    if records is None:
        records = _load_experience_records()
    return [r for r in records if r.get("task_id") == task_id]


def get_failure_patterns(records: list[dict] | None = None, limit: int = 20) -> dict:
    """Analyze failure patterns across all recent experience records.

    Returns:
        Dict with:
          - common_failures: Counter of (check_id → count)
          - drift_rate: fraction of runs with drift
          - common_oos_files: most frequent out-of-scope file paths
          - avg_elapsed: average execution time
    """
    if records is None:
        records = _load_experience_records()

    if not records:
        return {"common_failures": {}, "drift_rate": 0.0,
                "common_oos_files": [], "avg_elapsed": 0.0}

    failure_checks: Counter = Counter()
    drift_count = 0
    oos_files: Counter = Counter()
    total_elapsed = 0.0

    for r in records[:limit]:
        total_elapsed += r.get("elapsed_seconds", 0)
        if r.get("drift_detected"):
            drift_count += 1
        for oos in r.get("out_of_scope_files", []):
            oos_files[oos] += 1
        for check in r.get("acceptance_checks", []):
            if not check.get("passed", True):
                failure_checks[check.get("check_id", "?")] += 1

    n = min(len(records), limit)
    return {
        "common_failures": dict(failure_checks.most_common(5)),
        "drift_rate": drift_count / n if n else 0.0,
        "common_oos_files": [f for f, _ in oos_files.most_common(5)],
        "avg_elapsed": total_elapsed / n if n else 0.0,
    }


def get_lessons_for_task(
    task_id: str,
    risk_class: str = "LOW",
    max_lessons: int = 5,
) -> str:
    """Generate a "lessons learned" block for injection into a directive.

    Combines task-specific history with global failure patterns.
    Returns empty string if no relevant experience exists.

    Args:
        task_id: Current task being planned.
        risk_class: Risk classification (LOW/SEMI/CORE).
        max_lessons: Maximum number of lesson items.

    Returns:
        Formatted markdown section, or "" if no lessons.
    """
    records = _load_experience_records()
    if not records:
        return ""

    lessons = []

    # 1. Task-specific history
    task_records = get_task_history(task_id, records)
    if task_records:
        failed = [r for r in task_records if r.get("overall_verdict") != "PASS"]
        passed = [r for r in task_records if r.get("overall_verdict") == "PASS"]

        if failed:
            # Extract what went wrong before
            for r in failed[:3]:
                verdict = r.get("overall_verdict", "?")
                detail = r.get("correction_detail") or ""
                failed_checks = [
                    c.get("check_id", "?")
                    for c in r.get("acceptance_checks", [])
                    if not c.get("passed", True)
                ]
                if failed_checks:
                    lessons.append(
                        f"Previous attempt on this task failed: {verdict}. "
                        f"Failed checks: {', '.join(failed_checks)}. {detail}"
                    )
                elif detail:
                    lessons.append(f"Previous attempt: {verdict}. {detail}")

        if passed:
            # What file patterns worked
            last_pass = passed[0]
            changed = last_pass.get("changed_files", [])
            if changed:
                lessons.append(
                    f"Last successful run changed {len(changed)} files: "
                    f"{', '.join(changed[:5])}"
                )

    # 2. Global patterns (from all recent runs)
    patterns = get_failure_patterns(records)

    if patterns["drift_rate"] > 0.2:
        lessons.append(
            f"WARNING: {patterns['drift_rate']:.0%} of recent runs had scope drift. "
            "Stay strictly within the Scope section."
        )

    if patterns["common_oos_files"]:
        top_oos = patterns["common_oos_files"][:3]
        lessons.append(
            f"Files commonly touched out-of-scope: {', '.join(top_oos)}. "
            "Do NOT modify these."
        )

    common_fails = patterns.get("common_failures", {})
    if common_fails:
        top_fail = list(common_fails.keys())[:2]
        lessons.append(
            f"Common acceptance failures: {', '.join(top_fail)}. "
            "Pay special attention to these checks."
        )

    if not lessons:
        return ""

    # Trim to max_lessons
    lessons = lessons[:max_lessons]

    lines = ["## Lessons from Past Runs", ""]
    for lesson in lessons:
        lines.append(f"- {lesson}")
    lines.append("")

    return "\n".join(lines)

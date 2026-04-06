"""
collect_packet.py — deterministic execution packet collector.

Collects git diff + pytest results and writes a valid
EXECUTION_PACKET_SCHEMA_v1 JSON to orchestrator/last_execution_packet.json.

Usage:
    python orchestrator/collect_packet.py --trace-id orch_... [--base-commit abc123]
    python orchestrator/collect_packet.py --trace-id orch_... --run-pytest

This is the post-processor for Meta Orchestrator M0.
Claude Code output is optional (--executor-notes); this script is source of truth.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR_DIR = ROOT / "orchestrator"
OUTPUT_PATH = ORCHESTRATOR_DIR / "last_execution_packet.json"
DIFF_TRUNCATION_CHARS = 15_000

# Tier classification based on file path prefixes
TIER_MAP: list[tuple[str, str]] = [
    (".cursor/windmill-core-v1/domain/reconciliation_", "Tier-1"),
    (".cursor/windmill-core-v1/maintenance_sweeper", "Tier-1"),
    (".cursor/windmill-core-v1/retention_policy", "Tier-1"),
    (".cursor/windmill-core-v1/domain/structural_checks", "Tier-1"),
    (".cursor/windmill-core-v1/domain/observability_service", "Tier-1"),
    (".cursor/windmill-core-v1/migrations/016_", "Tier-1"),
    (".cursor/windmill-core-v1/migrations/017_", "Tier-1"),
    (".cursor/windmill-core-v1/migrations/018_", "Tier-1"),
    (".cursor/windmill-core-v1/migrations/019_", "Tier-1"),
    (".cursor/windmill-core-v1/tests/validation/", "Tier-1"),
    (".cursor/windmill-core-v1/domain/", "Tier-2"),
    (".cursor/windmill-core-v1/migrations/", "Tier-2"),
    ("scripts/", "Tier-3"),
    ("orchestrator/", "Tier-3"),
    ("tests/", "Tier-3"),
    ("config/", "Tier-3"),
    ("docs/", "Tier-3"),
]


def classify_tiers(changed_files: list[str]) -> list[str]:
    tiers: set[str] = set()
    for f in changed_files:
        for prefix, tier in TIER_MAP:
            if f.startswith(prefix):
                tiers.add(tier)
                break
        else:
            tiers.add("Tier-3")  # default
    return sorted(tiers)


def run_git_diff_stat(base_commit: str | None) -> list[str]:
    """Return list of changed file paths relative to base_commit (or HEAD~1)."""
    ref = base_commit or _resolve_base_commit()
    result = subprocess.run(
        ["git", "diff", "--name-only", ref, "HEAD"],
        capture_output=True, text=True, cwd=ROOT
    )
    if result.returncode != 0:
        # Fallback: uncommitted changes vs index
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=ROOT
        )
    lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    return lines


def run_git_diff(base_commit: str | None) -> tuple[str, int, bool]:
    """Return (diff_summary, char_count, truncated)."""
    ref = base_commit or _resolve_base_commit()
    result = subprocess.run(
        ["git", "diff", "--stat", ref, "HEAD"],
        capture_output=True, text=True, cwd=ROOT
    )
    stat = result.stdout.strip()

    result2 = subprocess.run(
        ["git", "diff", ref, "HEAD", "--", "*.py", "*.json", "*.yaml", "*.md"],
        capture_output=True, text=True, cwd=ROOT
    )
    full_diff = result2.stdout

    combined = f"{stat}\n\n{full_diff}".strip()
    truncated = len(combined) > DIFF_TRUNCATION_CHARS
    if truncated:
        combined = combined[:DIFF_TRUNCATION_CHARS] + "\n[DIFF TRUNCATED]"
    return combined, len(combined), truncated


def _resolve_base_commit() -> str:
    """Find merge-base with master/main, fallback to HEAD~1."""
    for branch in ("origin/master", "origin/main", "master", "main"):
        result = subprocess.run(
            ["git", "merge-base", "HEAD", branch],
            capture_output=True, text=True, cwd=ROOT
        )
        if result.returncode == 0:
            return result.stdout.strip()
    return "HEAD~1"


def run_pytest(timeout: int = 120) -> dict | None:
    """Run pytest and return {passed, failed, skipped, error} or None on timeout/crash."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--tb=no", "-q", "--no-header"],
            capture_output=True, text=True, cwd=ROOT, timeout=timeout
        )
        return _parse_pytest_output(result.stdout + result.stderr)
    except subprocess.TimeoutExpired:
        return {"passed": 0, "failed": 0, "skipped": 0, "error": -1, "_note": "timeout"}
    except Exception:
        return None


def _parse_pytest_output(output: str) -> dict:
    """Parse pytest summary line like '509 passed in 4.20s' or '5 failed, 3 passed'."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    patterns = {
        "passed":  r"(\d+) passed",
        "failed":  r"(\d+) failed",
        "skipped": r"(\d+) skipped",
        "error":   r"(\d+) error",
    }
    for key, pat in patterns.items():
        m = re.search(pat, output)
        if m:
            counts[key] = int(m.group(1))
    return counts


def collect(
    trace_id: str,
    base_commit: str | None = None,
    run_pytest_flag: bool = False,
    executor_notes: str | None = None,
) -> dict:
    """Collect execution packet. Returns valid packet dict."""
    changed_files = run_git_diff_stat(base_commit)
    diff_summary, diff_char_count, diff_truncated = run_git_diff(base_commit)
    affected_tiers = classify_tiers(changed_files)

    test_results = None
    if run_pytest_flag:
        test_results = run_pytest()

    status = "completed"
    if not changed_files and not run_pytest_flag:
        status = "partial"

    packet = {
        "schema_version": "v1",
        "trace_id": trace_id,
        "status": status,
        "changed_files": changed_files,
        "diff_summary": diff_summary if diff_summary else None,
        "diff_char_count": diff_char_count,
        "diff_truncated": diff_truncated,
        "test_results": test_results,
        "affected_tiers": affected_tiers,
        "executor_notes": executor_notes,
        "questions": [],
        "blockers": [],
        "artifacts_produced": [],
        "collected_by": "collect_packet.py",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "base_commit": base_commit,
    }
    return packet


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect execution packet for Meta Orchestrator")
    parser.add_argument("--trace-id", required=True, help="Trace ID from current directive")
    parser.add_argument("--base-commit", default=None, help="Base commit for diff (default: merge-base)")
    parser.add_argument("--run-pytest", action="store_true", help="Run pytest and include results")
    parser.add_argument("--executor-notes", default=None, help="Optional notes from Claude Code output")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Output path for packet JSON")
    args = parser.parse_args()

    packet = collect(
        trace_id=args.trace_id,
        base_commit=args.base_commit,
        run_pytest_flag=args.run_pytest,
        executor_notes=args.executor_notes,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[collect_packet] status={packet['status']} "
          f"changed={len(packet['changed_files'])} files "
          f"tiers={packet['affected_tiers']} "
          f"diff_chars={packet['diff_char_count']} "
          f"truncated={packet['diff_truncated']}")
    if packet["test_results"]:
        tr = packet["test_results"]
        print(f"[collect_packet] tests: passed={tr.get('passed',0)} "
              f"failed={tr.get('failed',0)} skipped={tr.get('skipped',0)}")
    print(f"[collect_packet] written to {out_path}")


if __name__ == "__main__":
    main()

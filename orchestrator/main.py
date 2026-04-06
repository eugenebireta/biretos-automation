"""
main.py — Meta Orchestrator, one-cycle run-once skeleton.

M0 Spike: proves the directive → execution → packet roundtrip.

Usage:
    python orchestrator/main.py init          # create default manifest
    python orchestrator/main.py               # run one cycle
    python orchestrator/main.py show-directive  # print last directive

Physical interface (M0 finding):
    cat orchestrator/orchestrator_directive.md | claude -p
    (stdin piped to claude --print mode; no arg length limit)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"
MANIFEST_PATH = ORCH_DIR / "manifest.json"
DIRECTIVE_PATH = ORCH_DIR / "orchestrator_directive.md"
PACKET_PATH = ORCH_DIR / "last_execution_packet.json"
RUNS_PATH = ORCH_DIR / "runs.jsonl"

DEFAULT_MANIFEST = {
    "schema_version": "v1",
    "fsm_state": "ready",
    "current_sprint_goal": "",
    "current_task_id": "",
    "trace_id": "",
    "attempt_count": 0,
    "last_verdict": None,
    "last_directive_hash": None,
    "pending_packet_id": None,
    "deadline_at": None,
    "default_option_id": None,
    "updated_at": "",
}

# ---------------------------------------------------------------------------
# FSM transition table (M0: defined, enforced in M3)
# (current_state, event) -> next_state
# ---------------------------------------------------------------------------
FSM_TRANSITIONS: dict[tuple[str, str], str] = {
    ("ready",                 "cycle_start"):       "ready",
    ("ready",                 "directive_written"):  "awaiting_execution",
    ("ready",                 "task_completed"):     "completed",
    ("ready",                 "error_detected"):     "error",
    ("awaiting_execution",    "packet_received"):    "ready",
    ("awaiting_execution",    "error_detected"):     "error",
    ("awaiting_execution",    "cycle_start"):        "awaiting_execution",
    ("awaiting_owner_reply",  "owner_replied"):      "ready",
    ("awaiting_owner_reply",  "cycle_start"):        "awaiting_owner_reply",
    ("error",                 "owner_replied"):      "ready",
    ("error",                 "cycle_start"):        "error",
    ("completed",             "cycle_start"):        "completed",
}


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {**DEFAULT_MANIFEST, "updated_at": _now()}


def save_manifest(m: dict) -> None:
    m["updated_at"] = _now()
    MANIFEST_PATH.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")


def append_run(entry: dict) -> None:
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUNS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sprint_goal_warning(manifest: dict) -> None:
    """Warn if current_sprint_goal is empty or stale."""
    try:
        import yaml
        cfg_path = ORCH_DIR / "config.yaml"
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
        warn_days = cfg.get("sprint_goal_staleness_warn_days", 7)
    except Exception:
        warn_days = 7

    goal = manifest.get("current_sprint_goal", "")
    if not goal:
        print("[orchestrator] WARNING: current_sprint_goal is empty. "
              "Set it in manifest.json before running a cycle.", file=sys.stderr)
        return

    updated_at = manifest.get("updated_at", "")
    if updated_at:
        try:
            from datetime import timedelta
            updated = datetime.fromisoformat(updated_at)
            if datetime.now(timezone.utc) - updated > timedelta(days=warn_days):
                print(f"[orchestrator] WARNING: sprint_goal not updated in >{warn_days} days.",
                      file=sys.stderr)
        except Exception:
            pass


def cmd_init(args: argparse.Namespace) -> None:
    if MANIFEST_PATH.exists() and not args.force:
        print("[orchestrator] manifest.json already exists. Use --force to overwrite.")
        return
    m = {**DEFAULT_MANIFEST, "updated_at": _now()}
    ORCH_DIR.mkdir(parents=True, exist_ok=True)
    save_manifest(m)
    print(f"[orchestrator] Initialized manifest at {MANIFEST_PATH}")
    print("[orchestrator] Next: set current_sprint_goal in manifest.json, then run main.py")


def cmd_cycle(args: argparse.Namespace) -> None:
    manifest = load_manifest()
    state = manifest.get("fsm_state", "ready")

    _sprint_goal_warning(manifest)
    print(f"[orchestrator] state={state} task={manifest.get('current_task_id','(none)')}")

    if state == "completed":
        print("[orchestrator] Task completed. Set new task_id and sprint_goal to start next.")
        return

    if state == "error":
        print("[orchestrator] In error state. Resolve and set fsm_state=ready in manifest.json.")
        return

    if state == "awaiting_owner_reply":
        print("[orchestrator] Awaiting owner reply. Check escalation packet and respond.")
        return

    if state == "awaiting_execution":
        if PACKET_PATH.exists():
            packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
            print(f"[orchestrator] Packet found: status={packet.get('status')} "
                  f"files={len(packet.get('changed_files', []))}")
            manifest["fsm_state"] = "ready"
            manifest["last_verdict"] = None
            save_manifest(manifest)
            append_run({"ts": _now(), "event": "packet_received",
                        "state_before": "awaiting_execution", "state_after": "ready",
                        "trace_id": manifest.get("trace_id")})
            print("[orchestrator] Packet consumed. Ready for next cycle.")
        else:
            print(f"[orchestrator] Awaiting execution. Directive at: {DIRECTIVE_PATH}")
            print("[orchestrator] Run: cat orchestrator/orchestrator_directive.md | claude -p")
            print("[orchestrator] Then: python orchestrator/collect_packet.py "
                  f"--trace-id {manifest.get('trace_id', '<trace_id>')}")
        return

    # state == "ready": write directive stub (real intent from Claude Advisor in M2)
    trace_id = f"orch_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
    manifest["trace_id"] = trace_id
    manifest["attempt_count"] = manifest.get("attempt_count", 0) + 1

    directive = _build_stub_directive(manifest, trace_id)
    DIRECTIVE_PATH.write_text(directive, encoding="utf-8")

    directive_hash = hashlib.sha256(directive.encode()).hexdigest()[:12]
    manifest["last_directive_hash"] = directive_hash
    manifest["fsm_state"] = "awaiting_execution"
    save_manifest(manifest)

    append_run({"ts": _now(), "event": "directive_written",
                "state_before": "ready", "state_after": "awaiting_execution",
                "trace_id": trace_id, "directive_hash": directive_hash})

    print(f"[orchestrator] Directive written → {DIRECTIVE_PATH}")
    print(f"[orchestrator] trace_id={trace_id}")
    print()
    print("=" * 60)
    print("NEXT — feed directive to Claude Code:")
    print()
    print("    cat orchestrator/orchestrator_directive.md | claude -p")
    print()
    print("Then collect result:")
    print(f"    python orchestrator/collect_packet.py --trace-id {trace_id} [--run-pytest]")
    print()
    print("Then run next cycle:")
    print("    python orchestrator/main.py")
    print("=" * 60)


def _build_stub_directive(manifest: dict, trace_id: str) -> str:
    task_id = manifest.get("current_task_id") or "UNSET_TASK_ID"
    sprint_goal = manifest.get("current_sprint_goal") or "(no sprint goal set)"
    attempt = manifest.get("attempt_count", 1)

    return f"""# Orchestrator Directive
trace_id: {trace_id}
task_id: {task_id}
attempt: {attempt}
generated_at: {_now()}

## Sprint Goal
{sprint_goal}

## Intent
(M0 stub — advisor integration in M2)

## Scope
- (set in M2 via Claude Advisor)

## Constraints
- Do not touch any Tier-1 files
- Do not modify Core business tables
- Tier-3 only

## Acceptance Criteria
- (set per task)

## Context
This directive was generated by the Meta Orchestrator M0 spike.
Real task-specific intent will be populated by Claude Advisor in M2.

---
Read this directive, execute the task, commit your changes.
Then the owner will run collect_packet.py to capture the result.
"""


def cmd_show_directive(args: argparse.Namespace) -> None:
    if DIRECTIVE_PATH.exists():
        print(DIRECTIVE_PATH.read_text(encoding="utf-8"))
    else:
        print("[orchestrator] No directive found. Run main.py to generate one.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Meta Orchestrator — run-once cycle")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="Initialize manifest.json")
    p_init.add_argument("--force", action="store_true")

    sub.add_parser("show-directive", help="Print last directive")

    args = parser.parse_args()

    if args.cmd == "init":
        cmd_init(args)
    elif args.cmd == "show-directive":
        cmd_show_directive(args)
    else:
        cmd_cycle(args)


if __name__ == "__main__":
    main()

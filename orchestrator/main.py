"""
main.py — Meta Orchestrator, one-cycle run-once.

M1: integrates classifier (risk) + intake (context bundle).
M2: Claude Advisor call (next step).

Usage:
    python orchestrator/main.py init            # create default manifest
    python orchestrator/main.py                 # run one cycle
    python orchestrator/main.py show-directive  # print last directive
    python orchestrator/main.py classify        # classify risk of last packet

Physical interface (M0 finding):
    cat orchestrator/orchestrator_directive.md | claude -p
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
    "last_audit_result": None,
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

    # state == "ready": run intake + classify + write directive
    trace_id = f"orch_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
    manifest["trace_id"] = trace_id
    manifest["attempt_count"] = manifest.get("attempt_count", 0) + 1

    # M1: load context bundle
    bundle = _run_intake()
    if bundle.warnings:
        for w in bundle.warnings:
            print(f"[orchestrator] INTAKE WARNING: {w}", file=sys.stderr)
    if bundle.validation_errors:
        for e in bundle.validation_errors:
            print(f"[orchestrator] VALIDATION: {e}", file=sys.stderr)

    # M1: classify risk of last execution packet
    classification = _run_classify(bundle)
    print(f"[orchestrator] risk={classification.risk_class} "
          f"route={classification.governance_route}")
    if classification.tier_violations:
        for v in classification.tier_violations:
            print(f"[orchestrator] TIER VIOLATION: {v}", file=sys.stderr)
    if classification.blocking_rules:
        for r in classification.blocking_rules:
            print(f"[orchestrator] BLOCKING RULE: {r}", file=sys.stderr)

    # M2: call Claude Advisor for task guidance
    advisor_result = _run_advisor(bundle, trace_id)
    if advisor_result.warnings:
        for w in advisor_result.warnings:
            print(f"[orchestrator] ADVISOR WARNING: {w}", file=sys.stderr)

    if advisor_result.escalated:
        manifest["fsm_state"] = "awaiting_owner_reply"
        manifest["last_verdict"] = "ESCALATE"
        save_manifest(manifest)
        append_run({"ts": _now(), "event": "advisor_escalation",
                    "reason": advisor_result.escalation_reason,
                    "trace_id": trace_id})
        print()
        print("=" * 60)
        print("ADVISOR ESCALATION — could not obtain valid verdict.")
        print(f"Reason: {advisor_result.escalation_reason}")
        print("Check orchestrator/last_escalation.json and resolve.")
        print("After resolving: set fsm_state=ready in manifest.json")
        print("=" * 60)
        return

    verdict = advisor_result.verdict
    print(f"[orchestrator] advisor risk={verdict.risk_assessment} "
          f"route={verdict.governance_route} attempts={advisor_result.attempt_count}")

    # M3: synthesizer — deterministic safety gate
    cfg = _load_config()
    synth = _run_synthesizer(
        classification, verdict,
        attempt_count=manifest.get("attempt_count", 1),
        last_packet_status=bundle.last_status,
        max_attempts=int(cfg.get("max_attempts", 3)),
    )
    for w in synth.warnings:
        print(f"[orchestrator] SYNTH WARNING: {w}", file=sys.stderr)
    print(f"[orchestrator] synth action={synth.action} final_risk={synth.final_risk} "
          f"scope={len(synth.approved_scope)} rules={synth.rule_trace}")

    if synth.action == "CORE_GATE":
        # Automated dual-audit via CORE_GATE bridge (infra/acceleration-bootstrap Task 5)
        manifest["fsm_state"] = "audit_in_progress"
        save_manifest(manifest)
        append_run({"ts": _now(), "event": "core_risk_gate_started",
                    "rule_trace": synth.rule_trace, "rationale": synth.rationale,
                    "trace_id": trace_id})
        print()
        print("=" * 60)
        print("CORE RISK — launching automated auditor_system review...")
        print(f"Rationale: {synth.rationale}")
        print("=" * 60)

        try:
            import core_gate_bridge as _cgb
            task_pack = _cgb.decision_to_task_pack(synth, manifest)
            audit_result = _cgb.run_audit_sync(task_pack)

            new_state  = _cgb._determine_fsm_state(audit_result)
            new_verdict = _cgb._determine_last_verdict(new_state)

            # Persist compact audit summary
            audit_summary = {
                "run_id":         audit_result.run_id,
                "ts":             _now(),
                "fsm_state":      new_state,
                "verdict":        new_verdict,
                "gate_passed":    audit_result.quality_gate.passed if audit_result.quality_gate else None,
                "approval_route": audit_result.approval_route.value if audit_result.approval_route else None,
                "escalated":      audit_result.escalated,
                "trace_id":       trace_id,
            }
            LAST_AUDIT_RESULT_PATH = ORCH_DIR / "last_audit_result.json"
            LAST_AUDIT_RESULT_PATH.write_text(
                json.dumps(audit_summary, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            manifest["fsm_state"]        = new_state
            manifest["last_verdict"]     = new_verdict
            manifest["last_audit_result"] = audit_summary
            save_manifest(manifest)
            append_run({"ts": _now(), "event": "core_risk_gate_complete",
                        "new_state": new_state, "verdict": new_verdict,
                        "trace_id": trace_id})

            print(f"[orchestrator] Audit complete: state={new_state} verdict={new_verdict}")
            if new_state == "audit_passed":
                print("[orchestrator] Audit PASSED — ready to proceed to builder.")
            elif new_state == "blocked":
                print("[orchestrator] Audit FAILED — task blocked. See last_audit_result.json")
            else:
                print("[orchestrator] Audit INCONCLUSIVE — owner review required.")

        except Exception as _audit_exc:
            # ConfigError (missing .env.auditors) or any other failure
            _err_class = type(_audit_exc).__name__
            print(f"[orchestrator] AUDIT BLOCKED: {_err_class}: {_audit_exc}")
            manifest["fsm_state"]    = "blocked"
            manifest["last_verdict"] = "AUDIT_FAILED"
            save_manifest(manifest)
            append_run({"ts": _now(), "event": "core_risk_gate_error",
                        "error": str(_audit_exc), "error_class": _err_class,
                        "trace_id": trace_id})

        return

    if synth.action in ("ESCALATE", "BLOCKED", "NO_OP"):
        verdict_map = {"ESCALATE": "ESCALATE", "BLOCKED": "BLOCKED", "NO_OP": "ESCALATE"}
        manifest["fsm_state"] = "awaiting_owner_reply"
        manifest["last_verdict"] = verdict_map[synth.action]
        save_manifest(manifest)
        append_run({"ts": _now(), "event": f"synth_{synth.action.lower()}",
                    "rule_trace": synth.rule_trace, "rationale": synth.rationale,
                    "trace_id": trace_id})
        print()
        print("=" * 60)
        print(f"SYNTHESIZER: {synth.action}")
        print(f"Rationale: {synth.rationale}")
        if synth.stripped_files:
            print(f"Stripped Tier-1/2 files: {synth.stripped_files}")
        print("After resolving: set fsm_state=ready in manifest.json")
        print("=" * 60)
        return

    # PROCEED — build directive with synthesizer-approved scope
    directive = _build_directive(manifest, trace_id, bundle, classification, verdict, synth)
    DIRECTIVE_PATH.write_text(directive, encoding="utf-8")

    directive_hash = hashlib.sha256(directive.encode()).hexdigest()[:12]
    manifest["last_directive_hash"] = directive_hash
    manifest["fsm_state"] = "awaiting_execution"
    save_manifest(manifest)

    append_run({"ts": _now(), "event": "directive_written",
                "state_before": "ready", "state_after": "awaiting_execution",
                "trace_id": trace_id, "directive_hash": directive_hash})

    print(f"[orchestrator] Directive written -> {DIRECTIVE_PATH}")
    print(f"[orchestrator] trace_id={trace_id}")

    # M4: auto-execute if enabled in config
    if cfg.get("auto_execute", False):
        _run_executor_bridge(manifest, trace_id, cfg)
    else:
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


def _run_intake():
    """Load context bundle from persisted artifacts (M1)."""
    import intake as _intake
    return _intake.load()


def _run_classify(bundle):
    """Classify risk from context bundle (M1)."""
    import classifier as _classifier
    return _classifier.classify(
        changed_files=bundle.last_changed_files,
        affected_tiers=bundle.last_affected_tiers or None,
        task_id=bundle.task_id,
        intent=bundle.sprint_goal,
    )


def _run_advisor(bundle, trace_id: str):
    """Call Claude Advisor for task guidance (M2)."""
    import advisor as _advisor
    return _advisor.call(bundle)


def _run_synthesizer(classification, verdict, attempt_count: int,
                     last_packet_status, max_attempts: int):
    """Apply deterministic rule engine (M3)."""
    import synthesizer as _synthesizer
    return _synthesizer.decide(
        classification=classification,
        verdict=verdict,
        attempt_count=attempt_count,
        last_packet_status=last_packet_status,
        max_attempts=max_attempts,
    )


def _run_executor_bridge(manifest: dict, trace_id: str, cfg: dict) -> None:
    """M4: run Claude Code autonomously and auto-collect packet."""
    import json
    import executor_bridge as _eb

    timeout = int(cfg.get("executor_timeout_seconds", 600))
    run_pytest = bool(cfg.get("auto_pytest", False))
    base_commit = cfg.get("base_commit") or None

    print()
    print("[orchestrator] auto_execute=true — running claude -p...")

    exec_result, packet = _eb.run_with_collect(
        directive_path=DIRECTIVE_PATH,
        trace_id=trace_id,
        base_commit=base_commit,
        run_pytest=run_pytest,
        timeout=timeout,
    )

    print(f"[orchestrator] executor status={exec_result.status} "
          f"exit_code={exec_result.exit_code} "
          f"elapsed={exec_result.elapsed_seconds:.1f}s")

    if exec_result.status == "completed" and packet is not None:
        # Write packet and advance FSM to ready
        PACKET_PATH.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest["fsm_state"] = "ready"
        manifest["last_verdict"] = None
        save_manifest(manifest)
        append_run({"ts": _now(), "event": "auto_execute_completed",
                    "state_before": "awaiting_execution", "state_after": "ready",
                    "trace_id": trace_id,
                    "changed_files": len(packet.get("changed_files", [])),
                    "elapsed_seconds": exec_result.elapsed_seconds})
        print(f"[orchestrator] Packet collected: "
              f"files={len(packet.get('changed_files', []))} "
              f"tiers={packet.get('affected_tiers', [])}")
        print("[orchestrator] FSM -> ready. Run main.py for next cycle.")
    else:
        # Execution failed — keep FSM at awaiting_execution, report error
        append_run({"ts": _now(), "event": "auto_execute_failed",
                    "state": "awaiting_execution",
                    "trace_id": trace_id,
                    "status": exec_result.status,
                    "exit_code": exec_result.exit_code,
                    "error_class": exec_result.error_class})
        print()
        print("=" * 60)
        print(f"EXECUTOR FAILED: status={exec_result.status} "
              f"exit_code={exec_result.exit_code}")
        if exec_result.stderr:
            print(f"stderr: {exec_result.stderr[:300]}")
        print("Directive preserved. Manual fallback:")
        print("    cat orchestrator/orchestrator_directive.md | claude -p")
        print(f"    python orchestrator/collect_packet.py --trace-id {trace_id}")
        print("=" * 60)


def _load_config() -> dict:
    """Load orchestrator config.yaml."""
    try:
        import yaml
        cfg_path = ORCH_DIR / "config.yaml"
        if cfg_path.exists():
            return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def _build_directive(manifest: dict, trace_id: str,
                     bundle, classification, verdict, synth=None) -> str:
    """Build directive with synthesizer-approved scope (M3)."""
    task_id = manifest.get("current_task_id") or "UNSET_TASK_ID"
    sprint_goal = manifest.get("current_sprint_goal") or "(no sprint goal set)"
    attempt = manifest.get("attempt_count", 1)

    # Use synthesizer approved_scope when available (Tier-3 guaranteed)
    if synth is not None and synth.approved_scope:
        scope_source = synth.approved_scope
        scope_note = f"synthesizer_action={synth.action} rule_trace={synth.rule_trace}"
    else:
        scope_source = verdict.scope or []
        scope_note = "scope from advisor (synthesizer not applied)"

    scope_lines = "\n".join(f"- {f}" for f in scope_source) or "- (no scope specified)"
    constraints_lines = "\n".join(f"- {c}" for c in bundle.dna_constraints)

    return f"""# Orchestrator Directive
trace_id: {trace_id}
task_id: {task_id}
attempt: {attempt}
generated_at: {_now()}
risk_class: {classification.risk_class}  governance_route: {classification.governance_route}
advisor_risk: {verdict.risk_assessment}  advisor_route: {verdict.governance_route}
scope_source: {scope_note}

## Sprint Goal
{sprint_goal}

## Next Step (from Claude Advisor)
{verdict.next_step}

## Advisor Rationale
{verdict.rationale}

## Scope (Tier-3 verified)
{scope_lines}

## Constraints
{constraints_lines}

## Acceptance Criteria
- All tests pass (zero regression)
- Only files in Scope section touched
- Tier-1 files untouched
- Pinned API signatures unchanged

---
Read this directive, execute the task, commit your changes.
Then run: python orchestrator/collect_packet.py --trace-id {trace_id} [--run-pytest]
"""


def _build_stub_directive(manifest: dict, trace_id: str,
                          bundle=None, classification=None) -> str:
    task_id = manifest.get("current_task_id") or "UNSET_TASK_ID"
    sprint_goal = manifest.get("current_sprint_goal") or "(no sprint goal set)"
    attempt = manifest.get("attempt_count", 1)

    risk_line = ""
    context_section = ""
    if classification is not None:
        risk_line = (f"risk_class: {classification.risk_class}  "
                     f"governance_route: {classification.governance_route}\n")
    if bundle is not None:
        ctx = bundle.to_advisor_prompt_context()
        if ctx:
            context_section = f"\n## Execution Context\n{ctx}\n"

    return f"""# Orchestrator Directive
trace_id: {trace_id}
task_id: {task_id}
attempt: {attempt}
generated_at: {_now()}
{risk_line}
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
{context_section}
## Context
This directive was generated by the Meta Orchestrator M1 with risk classification.
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


def cmd_classify(args: argparse.Namespace) -> None:
    """Classify risk of last execution packet (standalone diagnostic)."""
    if not PACKET_PATH.exists():
        print("[orchestrator] No execution packet found. Run collect_packet.py first.")
        return
    bundle = _run_intake()
    result = _run_classify(bundle)
    print(f"risk_class:        {result.risk_class}")
    print(f"governance_route:  {result.governance_route}")
    print(f"rationale:         {result.rationale}")
    if result.tier_violations:
        print("tier_violations:")
        for v in result.tier_violations:
            print(f"  - {v}")
    if result.blocking_rules:
        print("blocking_rules:")
        for r in result.blocking_rules:
            print(f"  - {r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Meta Orchestrator — run-once cycle")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="Initialize manifest.json")
    p_init.add_argument("--force", action="store_true")

    sub.add_parser("show-directive", help="Print last directive")
    sub.add_parser("classify", help="Classify risk of last execution packet")

    args = parser.parse_args()

    if args.cmd == "init":
        cmd_init(args)
    elif args.cmd == "show-directive":
        cmd_show_directive(args)
    elif args.cmd == "classify":
        cmd_classify(args)
    else:
        cmd_cycle(args)


if __name__ == "__main__":
    main()

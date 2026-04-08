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
import os
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
LOCK_PATH = ORCH_DIR / "orchestrator.lock"
RUNS_DIR = ORCH_DIR / "runs"


# ---------------------------------------------------------------------------
# P0-1: File lock — prevent concurrent manifest overwrites
# ---------------------------------------------------------------------------
def _acquire_lock():
    """Non-blocking file lock. Returns file handle or None."""
    try:
        fh = open(LOCK_PATH, "w")
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.write(str(os.getpid()))
        fh.flush()
        return fh
    except (IOError, OSError):
        try:
            fh.close()
        except Exception:
            pass
        return None


def _release_lock(fh):
    """Release file lock."""
    if fh is None:
        return
    try:
        if sys.platform == "win32":
            import msvcrt
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except (IOError, OSError):
                pass
        fh.close()
    except Exception:
        pass

def _ensure_run_dir(trace_id: str) -> Path:
    """Create and return per-run directory for artifacts isolation."""
    run_dir = RUNS_DIR / trace_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _save_manifest_atomic(updates: dict) -> None:
    """Briefly lock → load manifest → apply updates → save → unlock.

    Used for state transitions when the main file lock is NOT held
    (e.g., error recovery during unlocked cycle work).
    """
    lock_fh = _acquire_lock()
    try:
        manifest = load_manifest()
        manifest.update(updates)
        save_manifest(manifest)
    finally:
        _release_lock(lock_fh)


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
    ("processing",            "directive_written"):  "awaiting_execution",
    ("processing",            "error_detected"):     "error",
    ("processing",            "escalated"):          "awaiting_owner_reply",
    ("processing",            "cycle_start"):        "processing",
    ("awaiting_execution",    "packet_received"):    "ready",
    ("awaiting_execution",    "error_detected"):     "error",
    ("awaiting_execution",    "cycle_start"):        "awaiting_execution",
    ("awaiting_owner_reply",  "owner_replied"):      "ready",
    ("awaiting_owner_reply",  "cycle_start"):        "awaiting_owner_reply",
    ("error",                 "owner_replied"):      "ready",
    ("error",                 "cycle_start"):        "error",
    ("completed",             "cycle_start"):        "completed",
    # P0.5: audit states
    ("audit_in_progress",     "audit_passed"):       "ready",
    ("audit_in_progress",     "audit_failed"):       "awaiting_owner_reply",
    ("audit_in_progress",     "audit_blocked"):      "blocked",
    ("audit_in_progress",     "cycle_start"):        "audit_in_progress",
    ("blocked",               "owner_replied"):      "ready",
    ("blocked",               "cycle_start"):        "blocked",
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
    """Run one orchestrator cycle with narrow file-lock scope.

    Phase 1: Brief lock — check state, handle parked states, or
             claim the cycle (ready → processing).
    Phase 2: Execute cycle WITHOUT holding file lock.
             The "processing" FSM state prevents concurrent starts.
    """
    # ---------------------------------------------------------------
    # Phase 1: Brief lock — state check + claim
    # ---------------------------------------------------------------
    lock_fh = _acquire_lock()
    if lock_fh is None:
        append_run({"ts": _now(), "event": "lock_busy",
                     "status": "lock_busy",
                     "reason": "Another orchestrator instance holds the lock"})
        print("[orchestrator] lock_busy — another instance is running. Exiting.",
              file=sys.stderr)
        return

    manifest = None
    ready_to_proceed = False
    try:
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

        if state == "blocked":
            print("[orchestrator] Blocked by auditor. Owner review required.")
            return

        if state == "audit_in_progress":
            print("[orchestrator] Audit in progress. Waiting for completion.")
            return

        if state == "processing":
            append_run({"ts": _now(), "event": "cycle_busy",
                        "status": "cycle_busy",
                        "reason": "Previous cycle still in progress"})
            print("[orchestrator] cycle_busy — previous cycle still running. Exiting.",
                  file=sys.stderr)
            return

        if state == "audit_passed":
            # P0.5: pre-execution SEMI audit passed — forward to ready for directive build
            manifest["fsm_state"] = "ready"
            state = "ready"
            save_manifest(manifest)
            append_run({"ts": _now(), "event": "audit_passed_forwarded",
                        "status": "audit_passed_forwarded",
                        "state_before": "audit_passed", "state_after": "ready",
                        "trace_id": manifest.get("trace_id")})
            print("[orchestrator] audit_passed → ready (directive build next)")
            # fall through to ready processing below

        if state == "awaiting_execution":
            if PACKET_PATH.exists():
                packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
                print(f"[orchestrator] Packet found: status={packet.get('status')} "
                      f"files={len(packet.get('changed_files', []))}")
                manifest["fsm_state"] = "ready"
                manifest["last_verdict"] = None
                save_manifest(manifest)
                append_run({"ts": _now(), "event": "packet_received",
                            "status": "packet_received",
                            "state_before": "awaiting_execution", "state_after": "ready",
                            "trace_id": manifest.get("trace_id")})
                print("[orchestrator] Packet consumed. Ready for next cycle.")
            else:
                print(f"[orchestrator] Awaiting execution. Directive at: {DIRECTIVE_PATH}")
                print("[orchestrator] Run: cat orchestrator/orchestrator_directive.md | claude -p")
                print("[orchestrator] Then: python orchestrator/collect_packet.py "
                      f"--trace-id {manifest.get('trace_id', '<trace_id>')}")
            return

        # state == "ready": claim the cycle → processing
        manifest["fsm_state"] = "processing"
        save_manifest(manifest)
        ready_to_proceed = True
    finally:
        _release_lock(lock_fh)

    if not ready_to_proceed:
        return

    # ---------------------------------------------------------------
    # Phase 2: Execute cycle WITHOUT holding file lock.
    # "processing" state is the logical lock — prevents concurrent starts.
    # ---------------------------------------------------------------
    try:
        _cmd_cycle_inner(args, manifest)
    except Exception as exc:
        _save_manifest_atomic({
            "fsm_state": "error",
            "last_verdict": "CYCLE_ERROR",
        })
        append_run({"ts": _now(), "event": "cycle_error",
                    "status": "cycle_error",
                    "error": str(exc)[:200]})
        print(f"[orchestrator] CYCLE ERROR: {exc}", file=sys.stderr)


def _cmd_cycle_inner(args: argparse.Namespace, manifest: dict) -> None:
    """Main cycle work. Called WITHOUT file lock held.

    manifest["fsm_state"] is "processing" on entry.
    """
    # state == "ready" equivalent — manifest already loaded and claimed
    trace_id = f"orch_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
    manifest["trace_id"] = trace_id
    manifest["attempt_count"] = manifest.get("attempt_count", 0) + 1

    # P1: create per-run directory for artifact isolation
    run_dir = _ensure_run_dir(trace_id)
    manifest["_run_dir"] = str(run_dir)

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
    # Model selection: LOW → Sonnet API, SEMI/CORE → Opus API
    advisor_result = _run_advisor(bundle, trace_id,
                                  classifier_risk=classification.risk_class)
    if advisor_result.warnings:
        for w in advisor_result.warnings:
            print(f"[orchestrator] ADVISOR WARNING: {w}", file=sys.stderr)

    if advisor_result.escalated:
        manifest["fsm_state"] = "awaiting_owner_reply"
        manifest["last_verdict"] = "ESCALATE"
        save_manifest(manifest)
        append_run({"ts": _now(), "event": "advisor_escalation",
                    "status": "escalated",
                    "reason": advisor_result.escalation_reason,
                    "trace_id": trace_id})
        # Record experience for escalation
        try:
            import experience_writer as _ew
            _ew.write_failure_experience(
                trace_id=trace_id,
                task_id=manifest.get("current_task_id", "unknown"),
                risk_class=classification.risk_class if classification else "LOW",
                failure_reason=f"advisor escalation: {advisor_result.escalation_reason}",
                failure_stage="advisor",
            )
        except Exception:
            pass  # experience writing should not block orchestrator
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
                    "status": "audit_in_progress",
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
                        "status": new_verdict.lower() if new_verdict else "unknown",
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
                        "status": "audit_error",
                        "error": str(_audit_exc), "error_class": _err_class,
                        "trace_id": trace_id})

        return

    # P0.5: SEMI_AUDIT — pre-execution auditor review for SEMI risk tasks
    _semi_audit_critique = None
    if synth.action == "SEMI_AUDIT":
        manifest["fsm_state"] = "audit_in_progress"
        save_manifest(manifest)
        append_run({"ts": _now(), "event": "semi_risk_audit_started",
                    "status": "audit_in_progress",
                    "rule_trace": synth.rule_trace, "rationale": synth.rationale,
                    "trace_id": trace_id})
        print()
        print("=" * 60)
        print("SEMI RISK — launching pre-execution auditor review...")
        print(f"Rationale: {synth.rationale}")
        print("=" * 60)

        try:
            import core_gate_bridge as _cgb
            task_pack = _cgb.decision_to_task_pack(synth, manifest)
            proposal_text = (
                f"## SEMI Risk Pre-Execution Review\n\n"
                f"Task: {manifest.get('current_task_id', 'unknown')}\n"
                f"Sprint Goal: {manifest.get('current_sprint_goal', '')}\n"
                f"Scope ({len(synth.approved_scope)} files): {synth.approved_scope[:20]}\n"
                f"Rationale: {synth.rationale}\n"
                f"Rule trace: {synth.rule_trace}\n"
            )
            audit_result = _cgb.run_audit_sync(task_pack, proposal_text=proposal_text)
            new_state = _cgb._determine_fsm_state(audit_result)
            new_verdict = _cgb._determine_last_verdict(new_state)
            _semi_audit_critique = _cgb.extract_critique_text(audit_result)

            audit_summary = {
                "run_id": audit_result.run_id,
                "ts": _now(),
                "fsm_state": new_state,
                "verdict": new_verdict,
                "gate_passed": audit_result.quality_gate.passed if audit_result.quality_gate else None,
                "approval_route": audit_result.approval_route.value if audit_result.approval_route else None,
                "escalated": audit_result.escalated,
                "trace_id": trace_id,
                "audit_type": "semi_pre_execution",
            }
            LAST_AUDIT_RESULT_PATH = ORCH_DIR / "last_audit_result.json"
            LAST_AUDIT_RESULT_PATH.write_text(
                json.dumps(audit_summary, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            manifest["last_audit_result"] = audit_summary

            if new_state == "audit_passed":
                # Audit passed → continue to directive building (fall through below)
                manifest["_semi_audit_critique"] = _semi_audit_critique
                save_manifest(manifest)
                append_run({"ts": _now(), "event": "semi_risk_audit_passed",
                            "status": "audit_passed", "trace_id": trace_id})
                print(f"[orchestrator] SEMI audit PASSED — building directive.")
            else:
                manifest["fsm_state"] = new_state
                manifest["last_verdict"] = new_verdict
                save_manifest(manifest)
                append_run({"ts": _now(), "event": "semi_risk_audit_complete",
                            "status": new_verdict.lower(), "new_state": new_state,
                            "verdict": new_verdict, "trace_id": trace_id})
                print(f"[orchestrator] SEMI audit: state={new_state} verdict={new_verdict}")
                if new_state == "blocked":
                    print("[orchestrator] Audit FAILED — task blocked. See last_audit_result.json")
                else:
                    print("[orchestrator] Audit INCONCLUSIVE — owner review required.")
                return

        except Exception as _audit_exc:
            _err_class = type(_audit_exc).__name__
            print(f"[orchestrator] SEMI AUDIT BLOCKED: {_err_class}: {_audit_exc}")
            manifest["fsm_state"] = "blocked"
            manifest["last_verdict"] = "AUDIT_FAILED"
            save_manifest(manifest)
            append_run({"ts": _now(), "event": "semi_risk_audit_error",
                        "status": "audit_error",
                        "error": str(_audit_exc), "error_class": _err_class,
                        "trace_id": trace_id})
            return
        # If we reach here: SEMI audit passed, fall through to directive building

    if synth.action in ("ESCALATE", "BLOCKED", "NO_OP"):
        verdict_map = {"ESCALATE": "ESCALATE", "BLOCKED": "BLOCKED", "NO_OP": "ESCALATE"}
        manifest["fsm_state"] = "awaiting_owner_reply"
        manifest["last_verdict"] = verdict_map[synth.action]
        save_manifest(manifest)
        append_run({"ts": _now(), "event": f"synth_{synth.action.lower()}",
                    "status": f"synth_{synth.action.lower()}",
                    "rule_trace": synth.rule_trace, "rationale": synth.rationale,
                    "trace_id": trace_id})
        # Record experience for synthesizer block
        try:
            import experience_writer as _ew
            _ew.write_failure_experience(
                trace_id=trace_id,
                task_id=manifest.get("current_task_id", "unknown"),
                risk_class=synth.final_risk or classification.risk_class,
                failure_reason=f"synthesizer {synth.action}: {synth.rationale}",
                failure_stage="synthesizer",
            )
        except Exception:
            pass
        print()
        print("=" * 60)
        print(f"SYNTHESIZER: {synth.action}")
        print(f"Rationale: {synth.rationale}")
        if synth.stripped_files:
            print(f"Stripped Tier-1/2 files: {synth.stripped_files}")
        print("After resolving: set fsm_state=ready in manifest.json")
        print("=" * 60)
        return

    # PROCEED (or SEMI_AUDIT after audit pass) — build directive with synthesizer-approved scope
    directive = _build_directive(
        manifest, trace_id, bundle, classification, verdict, synth,
        retry_context=manifest.get("_retry_reason"),
        audit_critique=_semi_audit_critique,
    )

    # P1: write to per-run dir + legacy path (backward compat)
    (run_dir / "directive.md").write_text(directive, encoding="utf-8")
    DIRECTIVE_PATH.write_text(directive, encoding="utf-8")

    directive_hash = hashlib.sha256(directive.encode()).hexdigest()[:12]
    manifest["last_directive_hash"] = directive_hash
    manifest["fsm_state"] = "awaiting_execution"
    manifest["_last_risk_class"] = synth.final_risk or classification.risk_class
    save_manifest(manifest)

    append_run({"ts": _now(), "event": "directive_written",
                "status": "directive_written",
                "state_before": "processing", "state_after": "awaiting_execution",
                "trace_id": trace_id, "directive_hash": directive_hash,
                "run_dir": str(run_dir)})

    print(f"[orchestrator] Directive written -> {run_dir / 'directive.md'}")
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


def _run_advisor(bundle, trace_id: str, classifier_risk: str = "LOW"):
    """Call Claude Advisor for task guidance (M2).

    classifier_risk is used for model selection:
      LOW  → Sonnet API (fast, cheap)
      SEMI/CORE → Opus API (deeper reasoning)
    """
    import advisor as _advisor
    # Inject risk into bundle for model selection
    bundle.risk_assessment = classifier_risk
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


def _get_retry_policy(risk_class: str) -> int:
    """Return max retry count based on risk class.

    Policy (from 3-critic consensus):
      LOW:  1 auto-retry with tightened directive
      SEMI: 1 retry with auditor critique attached
      CORE: 0 retries (always escalate)
    """
    return {"LOW": 1, "SEMI": 1, "CORE": 0}.get(risk_class, 0)


def _build_retry_directive(
    original_directive: str,
    attempt: int,
    acceptance_failures: list[dict],
    audit_critique: str = "",
    out_of_scope_files: list[str] | None = None,
) -> str:
    """Build a tightened directive for retry based on previous failures.

    Appends correction instructions to original directive so executor
    knows what went wrong and how to fix it.
    """
    corrections = []

    if acceptance_failures:
        corrections.append("## Previous Attempt Failed — Corrections Required\n")
        corrections.append(f"This is retry attempt {attempt + 1}. "
                           "Your previous attempt was rejected for the following reasons:\n")
        for check in acceptance_failures:
            if not check.get("passed", True):
                corrections.append(f"- **{check['check_id']}**: {check['detail']}")

    if out_of_scope_files:
        corrections.append(f"\n**Out-of-scope files detected ({len(out_of_scope_files)}):**")
        for f in out_of_scope_files[:10]:
            corrections.append(f"- {f}")
        corrections.append("\nDo NOT touch these files. Only modify files listed in ## Scope.")

    if audit_critique:
        corrections.append("\n## Auditor Critique\n")
        corrections.append("An automated auditor reviewed your changes and found issues:\n")
        corrections.append(audit_critique)
        corrections.append("\nAddress all issues above in this retry.")

    if not corrections:
        return original_directive

    correction_block = "\n".join(corrections)

    # Insert correction block before the final "---" separator
    if "\n---\n" in original_directive:
        parts = original_directive.rsplit("\n---\n", 1)
        return f"{parts[0]}\n\n{correction_block}\n\n---\n{parts[1]}"
    else:
        return f"{original_directive}\n\n{correction_block}"


def _run_executor_bridge(manifest: dict, trace_id: str, cfg: dict) -> None:
    """M4: run Claude Code autonomously, verify, and record experience.

    Control loop with retry (P0.5+P3):
      executor → gate → acceptance check → [SEMI/CORE: audit] → experience
      On failure: build correction directive → retry (policy-limited)
    """
    import json
    import executor_bridge as _eb
    import acceptance_checker as _ac
    import experience_writer as _ew

    timeout = int(cfg.get("executor_timeout_seconds", 600))
    run_pytest = bool(cfg.get("auto_pytest", False))
    base_commit = cfg.get("base_commit") or None
    task_id = manifest.get("current_task_id", "unknown")
    risk_class = manifest.get("_last_risk_class", "LOW")

    # Snapshot HEAD before executor runs — diff only executor's changes
    if not base_commit:
        import subprocess as _sp
        _head = _sp.run(["git", "rev-parse", "HEAD"], capture_output=True,
                        text=True, cwd=str(ROOT))
        if _head.returncode == 0:
            base_commit = _head.stdout.strip()

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

    # P0-3: Separate three outcomes: success, collect failure, executor failure
    if exec_result.status == "completed" and packet is not None:
        # P1: write packet to per-run dir + legacy path
        run_dir_str = manifest.get("_run_dir")
        if run_dir_str:
            run_packet = Path(run_dir_str) / "packet.json"
            run_packet.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
        PACKET_PATH.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")

        # Batch Quality Gate — deterministic check on execution packet
        import batch_quality_gate as _bqg
        _expected_risk = risk_class
        gate_result = _bqg.check_packet(packet, expected_risk=_expected_risk)

        print(f"[orchestrator] Packet collected: "
              f"files={len(packet.get('changed_files', []))} "
              f"tiers={packet.get('affected_tiers', [])}")
        print(f"[orchestrator] Batch gate: passed={gate_result.passed} "
              f"rule={gate_result.rule} auto_merge={gate_result.auto_merge_eligible}")

        # --- ACCEPTANCE CHECK (P0a: closes the deterministic control loop) ---
        directive_text = ""
        # P1: prefer directive from per-run dir
        _run_dir_str = manifest.get("_run_dir")
        _run_directive = Path(_run_dir_str) / "directive.md" if _run_dir_str else None
        if _run_directive and _run_directive.exists():
            directive_text = _run_directive.read_text(encoding="utf-8")
        elif DIRECTIVE_PATH.exists():
            directive_text = DIRECTIVE_PATH.read_text(encoding="utf-8")
        acceptance = _ac.check(
            packet=packet,
            directive_text=directive_text,
            trace_id=trace_id,
        )
        print(f"[orchestrator] Acceptance: passed={acceptance.passed} "
              f"drift={acceptance.drift_detected} "
              f"checks={[c.check_id for c in acceptance.checks if not c.passed]}")

        # --- EXPERIENCE RECORD (P0: trace-linked learning) ---
        acceptance_checks_dicts = [
            {"check_id": c.check_id, "passed": c.passed, "detail": c.detail}
            for c in acceptance.checks
        ]
        exp_record = _ew.write_execution_experience(
            trace_id=trace_id,
            task_id=task_id,
            risk_class=risk_class,
            acceptance_passed=acceptance.passed,
            acceptance_checks=acceptance_checks_dicts,
            drift_detected=acceptance.drift_detected,
            changed_files=packet.get("changed_files", []),
            elapsed_seconds=exec_result.elapsed_seconds,
            executor_status=exec_result.status,
            gate_passed=gate_result.passed,
            gate_rule=gate_result.rule,
            out_of_scope_files=acceptance.out_of_scope_files,
            correction_needed=not acceptance.passed,
            correction_detail="drift: executor touched out-of-scope files"
            if acceptance.drift_detected else None,
        )
        print(f"[orchestrator] Experience: verdict={exp_record.get('overall_verdict')} "
              f"trace_id={trace_id}")

        if gate_result.passed:
            retry_count = manifest.get("retry_count", 0)
            max_retries = _get_retry_policy(risk_class)
            failed_checks = [c.check_id for c in acceptance.checks if not c.passed]

            # --- P0.5: POST-EXECUTION AUDIT (SEMI/CORE only, after acceptance) ---
            audit_verdict = None  # None = no audit needed/run
            audit_critique_text = ""
            if acceptance.passed and risk_class in ("SEMI", "CORE"):
                print("[orchestrator] SEMI/CORE — running post-execution audit...")
                try:
                    from core_gate_bridge import (
                        run_post_execution_audit_sync,
                        extract_critique_text,
                        _determine_fsm_state,
                        _determine_last_verdict,
                    )
                    audit_result = run_post_execution_audit_sync(
                        packet=packet,
                        directive_text=directive_text,
                        trace_id=trace_id,
                        risk_class=risk_class,
                        manifest=manifest,
                    )
                    audit_verdict = _determine_fsm_state(audit_result)
                    audit_critique_text = extract_critique_text(audit_result)
                    manifest["last_audit_result"] = {
                        "run_id": audit_result.run_id,
                        "gate_passed": audit_result.quality_gate.passed
                        if audit_result.quality_gate else None,
                        "approval_route": audit_result.approval_route.value
                        if audit_result.approval_route else None,
                        "verdict": audit_verdict,
                    }
                    print(f"[orchestrator] Post-exec audit: verdict={audit_verdict} "
                          f"run_id={audit_result.run_id}")
                except Exception as exc:
                    print(f"[orchestrator] Post-exec audit ERROR: {exc}")
                    print("[orchestrator] Continuing without audit result.")
                    audit_verdict = None

            # --- DETERMINE FINAL STATE ---
            if acceptance.passed:
                if audit_verdict is None or audit_verdict == "audit_passed":
                    # Clean success (LOW, or SEMI/CORE with audit pass)
                    manifest["fsm_state"] = "ready"
                    manifest["last_verdict"] = None
                    manifest["retry_count"] = 0
                    manifest.pop("_retry_reason", None)
                elif audit_verdict == "blocked":
                    # Auditor blocked — escalate, no retry
                    manifest["fsm_state"] = "blocked"
                    manifest["last_verdict"] = "AUDIT_BLOCKED"
                elif risk_class == "SEMI" and retry_count < max_retries:
                    # P3: SEMI retry with auditor critique
                    retry_directive = _build_retry_directive(
                        original_directive=directive_text,
                        attempt=retry_count,
                        acceptance_failures=[],
                        audit_critique=audit_critique_text,
                    )
                    _retry_path = DIRECTIVE_PATH
                    _retry_path.write_text(retry_directive, encoding="utf-8")
                    manifest["retry_count"] = retry_count + 1
                    manifest["fsm_state"] = "awaiting_execution"
                    manifest["last_verdict"] = "AUDIT_RETRY_SCHEDULED"
                    manifest["_retry_reason"] = f"Audit failed: {audit_verdict}"
                    print()
                    print("=" * 60)
                    print(f"P3 AUDIT-RETRY {retry_count + 1}/{max_retries} (SEMI risk)")
                    print(f"Critique: {audit_critique_text[:200]}")
                    print("[orchestrator] Tightened directive written. Re-executing...")
                    print("=" * 60)
                else:
                    # CORE or retries exhausted — owner review
                    manifest["fsm_state"] = "awaiting_owner_reply"
                    manifest["last_verdict"] = "AUDIT_FAILED"
            else:
                # Acceptance failed
                retry_reason = (
                    f"Acceptance failed: checks={failed_checks}, "
                    f"drift={acceptance.drift_detected}, "
                    f"out_of_scope={acceptance.out_of_scope_files[:5]}"
                )
                if retry_count < max_retries:
                    # P3: AUTO-RETRY — tighten directive and restart
                    retry_directive = _build_retry_directive(
                        original_directive=directive_text,
                        attempt=retry_count,
                        acceptance_failures=acceptance_checks_dicts,
                        out_of_scope_files=acceptance.out_of_scope_files,
                    )
                    DIRECTIVE_PATH.write_text(retry_directive, encoding="utf-8")
                    manifest["retry_count"] = retry_count + 1
                    manifest["fsm_state"] = "awaiting_execution"
                    manifest["last_verdict"] = "RETRY_SCHEDULED"
                    manifest["_retry_reason"] = retry_reason
                    print()
                    print("=" * 60)
                    print(f"P3 AUTO-RETRY {retry_count + 1}/{max_retries} ({risk_class} risk)")
                    print(f"Reason: {retry_reason}")
                    print("[orchestrator] Tightened directive written. Re-executing...")
                    print("=" * 60)
                else:
                    manifest["fsm_state"] = "awaiting_owner_reply"
                    manifest["last_verdict"] = "ACCEPTANCE_FAILED"

            save_manifest(manifest)
            append_run({"ts": _now(), "event": "auto_execute_completed",
                        "status": "pass" if acceptance.passed else "acceptance_failed",
                        "state_before": "awaiting_execution",
                        "state_after": manifest["fsm_state"],
                        "trace_id": trace_id,
                        "changed_files": len(packet.get("changed_files", [])),
                        "elapsed_seconds": exec_result.elapsed_seconds,
                        "gate_rule": gate_result.rule,
                        "auto_merge": gate_result.auto_merge_eligible,
                        "acceptance_passed": acceptance.passed,
                        "drift_detected": acceptance.drift_detected,
                        "retry_count": manifest.get("retry_count", 0),
                        "audit_verdict": audit_verdict})

            # --- AUTO RE-EXECUTE on retry ---
            if manifest.get("last_verdict") in ("RETRY_SCHEDULED", "AUDIT_RETRY_SCHEDULED"):
                if cfg.get("auto_execute", False):
                    print("[orchestrator] Auto re-executing retry...")
                    manifest["fsm_state"] = "awaiting_execution"
                    save_manifest(manifest)
                    _run_executor_bridge(manifest, trace_id, cfg)
                    return

            if acceptance.passed and manifest["fsm_state"] == "ready":
                print("[orchestrator] FSM -> ready. Run main.py for next cycle.")
            elif manifest["fsm_state"] == "blocked":
                print()
                print("=" * 60)
                print("AUDIT BLOCKED — auditor flagged critical issues.")
                print(f"Critique: {audit_critique_text[:300]}")
                print("Owner review required. Set fsm_state=ready after resolution.")
                print("=" * 60)
            elif manifest["fsm_state"] == "awaiting_owner_reply" and not acceptance.passed:
                print()
                print("=" * 60)
                print("ACCEPTANCE CHECK FAILED (gate passed but executor drifted)")
                for c in acceptance.checks:
                    if not c.passed:
                        print(f"  {c.check_id}: {c.detail}")
                print("Resolve and set fsm_state=ready in manifest.json")
                print("=" * 60)
            elif manifest["fsm_state"] == "awaiting_owner_reply":
                print()
                print("=" * 60)
                print("AUDIT FAILED — owner review required.")
                print(f"Critique: {audit_critique_text[:300]}")
                print("Resolve and set fsm_state=ready in manifest.json")
                print("=" * 60)
        else:
            manifest["fsm_state"] = "awaiting_owner_reply"
            manifest["last_verdict"] = "BATCH_GATE_FAILED"
            save_manifest(manifest)
            append_run({"ts": _now(), "event": "batch_gate_failed",
                        "status": "gate_failed",
                        "state_before": "awaiting_execution",
                        "state_after": "awaiting_owner_reply",
                        "trace_id": trace_id,
                        "gate_rule": gate_result.rule,
                        "gate_reason": gate_result.reason,
                        "acceptance_passed": acceptance.passed})
            print()
            print("=" * 60)
            print(f"BATCH GATE FAILED: {gate_result.rule}")
            print(f"Reason: {gate_result.reason}")
            print("Resolve and set fsm_state=ready in manifest.json")
            print("=" * 60)

    elif exec_result.status == "completed" and packet is None:
        # P0-3: Executor succeeded but packet collection FAILED — do NOT mask as success
        manifest["fsm_state"] = "error"
        manifest["last_verdict"] = "COLLECT_FAILED"
        save_manifest(manifest)
        _ew.write_failure_experience(
            trace_id=trace_id, task_id=task_id, risk_class=risk_class,
            failure_reason="executor completed but packet collection returned None",
            failure_stage="collect",
            elapsed_seconds=exec_result.elapsed_seconds,
        )
        append_run({"ts": _now(), "event": "collect_failed",
                    "status": "collect_failed",
                    "trace_id": trace_id,
                    "reason": "executor completed but packet collection returned None",
                    "executor_status": exec_result.status})
        print()
        print("=" * 60)
        print("COLLECT FAILED: executor completed but packet collection failed.")
        print("FSM -> error. Check logs for collect_packet errors.")
        print("After fixing: set fsm_state=ready in manifest.json")
        print("=" * 60)

    else:
        # Execution failed — set FSM to error, report honestly
        manifest["fsm_state"] = "error"
        manifest["last_verdict"] = "EXECUTOR_FAILED"
        save_manifest(manifest)
        _ew.write_failure_experience(
            trace_id=trace_id, task_id=task_id, risk_class=risk_class,
            failure_reason=f"executor {exec_result.status} exit_code={exec_result.exit_code}",
            failure_stage="executor",
            elapsed_seconds=exec_result.elapsed_seconds,
        )
        append_run({"ts": _now(), "event": "auto_execute_failed",
                    "status": "executor_failed",
                    "state_after": "error",
                    "trace_id": trace_id,
                    "exit_code": exec_result.exit_code,
                    "error_class": exec_result.error_class})
        print()
        print("=" * 60)
        print(f"EXECUTOR FAILED: status={exec_result.status} "
              f"exit_code={exec_result.exit_code}")
        if exec_result.stderr:
            print(f"stderr: {exec_result.stderr[:300]}")
        print("FSM -> error. Directive preserved. Manual fallback:")
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


def _build_directive(
    manifest: dict,
    trace_id: str,
    bundle,
    classification,
    verdict,
    synth=None,
    retry_context: str | None = None,
    audit_critique: str | None = None,
) -> str:
    """Build directive with synthesizer-approved scope (M3).

    P3: retry_context injects acceptance failure reason for tightened retry.
    P0.5: audit_critique injects pre-execution SEMI audit findings.
    """
    task_id = manifest.get("current_task_id") or "UNSET_TASK_ID"
    sprint_goal = manifest.get("current_sprint_goal") or "(no sprint goal set)"
    attempt = manifest.get("attempt_count", 1)
    retry_count = manifest.get("retry_count", 0)

    # Use synthesizer approved_scope when available (Tier-3 guaranteed)
    if synth is not None and synth.approved_scope:
        scope_source = synth.approved_scope
        scope_note = f"synthesizer_action={synth.action} rule_trace={synth.rule_trace}"
    else:
        scope_source = verdict.scope or []
        scope_note = "scope from advisor (synthesizer not applied)"

    scope_lines = "\n".join(f"- {f}" for f in scope_source) or "- (no scope specified)"
    constraints_lines = "\n".join(f"- {c}" for c in bundle.dna_constraints)

    # P3: retry annotation
    retry_section = ""
    if retry_context or retry_count > 0:
        retry_section = f"""
## RETRY CONTEXT (attempt {attempt}, retry {retry_count})
Previous attempt failed acceptance check. Address these issues:
{retry_context or '(see acceptance_checker output)'}

"""

    # P0.5: SEMI audit critique annotation
    audit_section = ""
    if audit_critique:
        audit_section = f"""
## PRE-EXECUTION AUDIT CRITIQUE (SEMI risk)
Auditor reviewed this task before execution. Address findings:
{audit_critique}

"""

    return f"""# Orchestrator Directive
trace_id: {trace_id}
task_id: {task_id}
attempt: {attempt}
generated_at: {_now()}
risk_class: {classification.risk_class}  governance_route: {classification.governance_route}
advisor_risk: {verdict.risk_assessment}  advisor_route: {verdict.governance_route}
scope_source: {scope_note}
{retry_section}{audit_section}
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

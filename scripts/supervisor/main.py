from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

if __package__ in {None, ""}:
    scripts_dir = Path(__file__).resolve().parents[1]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

from supervisor import EVIDENCE_DIR, LOCK_TTL_SECONDS, LOGS_DIR, SCOUT_CACHE_DIR, STATE_ROOT
from supervisor.config import load_batch_limits, load_supervisor_config, load_telegram_runtime
from supervisor.journal import append_run_event
from supervisor.launcher import run_command
from supervisor.manifest import load_manifest, write_manifest
from supervisor.packets import append_packet_event, load_packet_states
from supervisor.reader import compute_active_evidence_fingerprint, select_latest_snapshot
from supervisor.rules import build_incident_packet, build_trace_id, determine_next_action, isoformat_z
from supervisor.telegram import send_packet
from supervisor.telegram_reader import apply_callback_updates, poll_updates


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else dict(default)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def telegram_state_path(state_root: Path) -> Path:
    return state_root / "telegram_state.json"


def load_telegram_state(state_root: Path) -> dict[str, Any]:
    return _load_json(telegram_state_path(state_root), {"last_update_id": 0, "last_poll_ts": None})


def write_telegram_state(state_root: Path, payload: dict[str, Any]) -> None:
    _atomic_write_json(telegram_state_path(state_root), payload)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _lock_file_path(state_root: Path) -> Path:
    state_root.mkdir(parents=True, exist_ok=True)
    return state_root / "supervisor.lock"


@contextmanager
def acquire_lock(state_root: Path) -> Iterator[bool]:
    path = _lock_file_path(state_root)
    now = datetime.now(timezone.utc)
    payload = {"pid": os.getpid(), "acquired_at": isoformat_z(now)}
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            existing = _load_json(path, {})
            existing_pid = int(existing.get("pid") or 0)
            stale = not _pid_alive(existing_pid)
            if not stale and path.exists():
                age = max((now - datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)).total_seconds(), 0.0)
                stale = age > LOCK_TTL_SECONDS
            if stale:
                path.unlink(missing_ok=True)
                with acquire_lock(state_root) as acquired:
                    yield acquired
                return
        except Exception:
            pass
        yield False
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
        yield True
    finally:
        path.unlink(missing_ok=True)


def _build_base_event(
    *,
    trace_id: str,
    decision: Any,
    snapshot: Any,
    current_fingerprint: str,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "ts": isoformat_z(datetime.now(timezone.utc)),
        "trace_id": trace_id,
        "rule": decision.rule_name,
        "action": decision.action,
        "status": decision.status,
        "reason": decision.reason,
        "result_kind": decision.result_kind,
        "dispatch_id": decision.dispatch_id,
        "snapshot_id": snapshot.snapshot_id if snapshot else None,
        "snapshot_summary_path": str(snapshot.summary_path) if snapshot else None,
        "current_evidence_fingerprint": current_fingerprint,
        "dry_run": dry_run,
    }


def _write_pre_action_manifest(
    *,
    state_root: Path,
    manifest: dict[str, Any],
    trace_id: str,
    decision: Any,
    snapshot: Any,
    current_fingerprint: str,
) -> dict[str, Any]:
    next_manifest = dict(manifest)
    next_manifest.update(
        {
            "trace_id": trace_id,
            "timestamp": isoformat_z(datetime.now(timezone.utc)),
            "rule_matched": decision.rule_name,
            "last_rule": decision.rule_name,
            "action": decision.action,
            "write_phase": "pre_action",
            "status": "ready" if decision.kind == "launch" else decision.status,
            "snapshot_summary_path": str(snapshot.summary_path) if snapshot else None,
            "snapshot_generated_at": snapshot.snapshot_generated_at if snapshot else None,
            "snapshot_id": snapshot.snapshot_id if snapshot else None,
            "source_evidence_fingerprint": current_fingerprint,
            "command": decision.command_spec.command if decision.command_spec else None,
            "params": decision.command_spec.params if decision.command_spec else None,
            "dispatch_id": decision.dispatch_id or None,
            "rerun_intent_id": decision.rerun_intent_id or None,
        }
    )
    write_manifest(state_root, next_manifest)
    return next_manifest


def _option_actions(packet: dict[str, Any]) -> dict[str, str]:
    actions: dict[str, str] = {}
    for option in list(packet.get("options") or []):
        option_id = str(option.get("id") or "").strip()
        next_action = str(option.get("next_action") or "").strip()
        if option_id and next_action:
            actions[option_id] = next_action
    return actions


def _apply_delivery_result(
    *,
    current_manifest: dict[str, Any],
    packet: dict[str, Any],
    delivery_event: dict[str, Any],
    decision: Any,
    current_fingerprint: str,
) -> dict[str, Any]:
    terminal_manifest = dict(current_manifest)
    terminal_manifest.update(
        {
            "write_phase": "terminal",
            "pending_packet_id": packet["packet_id"],
            "pending_packet_type": packet["type"],
            "last_action": decision.action,
            "last_evidence_fingerprint": current_fingerprint,
        }
    )
    if str(delivery_event.get("delivery_status") or "") == "sent":
        if str(packet.get("type") or "") == "owner_decision":
            terminal_manifest.update(
                {
                    "status": "awaiting_owner_reply",
                    "awaiting_owner_reply": True,
                    "decision_deadline_at": packet.get("decision_deadline_at"),
                    "default_option_id": packet.get("default_if_no_reply"),
                    "next_actions": _option_actions(packet),
                    "result_kind": "owner_packet_sent",
                }
            )
        else:
            terminal_manifest.update(
                {
                    "status": "error",
                    "awaiting_owner_reply": False,
                    "next_actions": {},
                    "result_kind": "incident_sent",
                }
            )
        return terminal_manifest

    terminal_manifest.update(
        {
            "status": "awaiting_packet_delivery",
            "awaiting_owner_reply": False,
            "next_actions": {},
            "result_kind": "delivery_failed",
        }
    )
    return terminal_manifest


def run_supervisor_cycle(
    *,
    state_root: Path = STATE_ROOT,
    scout_cache_dir: Path = SCOUT_CACHE_DIR,
    evidence_dir: Path = EVIDENCE_DIR,
    dry_run: bool = False,
    force_rerun: bool = False,
) -> dict[str, Any]:
    trace_id = build_trace_id()
    with acquire_lock(state_root) as acquired:
        if not acquired:
            event = {
                "ts": isoformat_z(datetime.now(timezone.utc)),
                "trace_id": trace_id,
                "rule": "RULE 0",
                "action": "lock_busy",
                "status": "completed",
                "reason": "supervisor_lock_busy",
                "result_kind": "lock_busy",
                "dry_run": dry_run,
            }
            append_run_event(state_root, event)
            return event

        try:
            config = load_supervisor_config()
            batch_limits = load_batch_limits(config)
            manifest = load_manifest(state_root)
            packet_states = load_packet_states(state_root)
            telegram_state = load_telegram_state(state_root)
            runtime = None if dry_run else load_telegram_runtime(config=config)
            if runtime is not None:
                try:
                    updates, telegram_state = poll_updates(runtime, telegram_state)
                    for event in apply_callback_updates(updates, packet_states):
                        append_packet_event(state_root, event)
                    packet_states = load_packet_states(state_root)
                except Exception as exc:
                    append_run_event(
                        state_root,
                        {
                            "ts": isoformat_z(datetime.now(timezone.utc)),
                            "trace_id": trace_id,
                            "rule": "TELEGRAM_POLL",
                            "action": "poll_updates",
                            "status": "error",
                            "reason": "telegram_poll_failed",
                            "result_kind": "telegram_poll_failed",
                            "error_class": "TRANSIENT",
                            "severity": "WARNING",
                            "retriable": True,
                            "error": str(exc),
                            "dry_run": dry_run,
                        },
                    )
            snapshot = select_latest_snapshot(scout_cache_dir)
            current_fingerprint = compute_active_evidence_fingerprint(evidence_dir)

            decision = determine_next_action(
                manifest=manifest,
                snapshot=snapshot,
                current_evidence_fingerprint=current_fingerprint,
                packet_states=packet_states,
                photo_limit=batch_limits["photo"],
                price_limit=batch_limits["price"],
                force_rerun=force_rerun,
            )
            current_manifest = _write_pre_action_manifest(
                state_root=state_root,
                manifest=manifest,
                trace_id=trace_id,
                decision=decision,
                snapshot=snapshot,
                current_fingerprint=current_fingerprint,
            )
            base_event = _build_base_event(
                trace_id=trace_id,
                decision=decision,
                snapshot=snapshot,
                current_fingerprint=current_fingerprint,
                dry_run=dry_run,
            )

            if decision.kind == "packet":
                packet = dict(decision.packet or {})
                packet.setdefault("trace_id", trace_id)
                packet.setdefault("ts", base_event["ts"])
                append_packet_event(state_root, packet)
                if runtime is not None and not dry_run:
                    delivery_event = send_packet(packet, runtime)
                    append_packet_event(state_root, delivery_event)
                    terminal_manifest = _apply_delivery_result(
                        current_manifest=current_manifest,
                        packet=packet,
                        delivery_event=delivery_event,
                        decision=decision,
                        current_fingerprint=current_fingerprint,
                    )
                    append_run_event(
                        state_root,
                        {
                            **base_event,
                            "packet_id": packet["packet_id"],
                            "packet_type": packet["type"],
                            "delivery_status": delivery_event["delivery_status"],
                            "telegram_message_id": delivery_event.get("telegram_message_id"),
                        },
                    )
                    write_manifest(state_root, terminal_manifest)
                    write_telegram_state(state_root, telegram_state)
                    return terminal_manifest
                terminal_manifest = dict(current_manifest)
                terminal_manifest.update(
                    {
                        "status": "awaiting_packet_delivery",
                        "write_phase": "terminal",
                        "pending_packet_id": packet["packet_id"],
                        "pending_packet_type": packet["type"],
                        "awaiting_owner_reply": False,
                        "last_action": decision.action,
                        "result_kind": decision.result_kind,
                        "last_evidence_fingerprint": current_fingerprint,
                    }
                )
                append_run_event(
                    state_root,
                    {
                        **base_event,
                        "packet_id": packet["packet_id"],
                        "packet_type": packet["type"],
                    },
                )
                write_manifest(state_root, terminal_manifest)
                write_telegram_state(state_root, telegram_state)
                return terminal_manifest

            if decision.kind == "deliver":
                packet = dict(decision.packet or {})
                if runtime is not None and not dry_run:
                    delivery_event = send_packet(packet, runtime)
                    append_packet_event(state_root, delivery_event)
                    terminal_manifest = _apply_delivery_result(
                        current_manifest=current_manifest,
                        packet=packet,
                        delivery_event=delivery_event,
                        decision=decision,
                        current_fingerprint=current_fingerprint,
                    )
                    append_run_event(
                        state_root,
                        {
                            **base_event,
                            "packet_id": packet["packet_id"],
                            "packet_type": packet["type"],
                            "delivery_status": delivery_event["delivery_status"],
                            "telegram_message_id": delivery_event.get("telegram_message_id"),
                        },
                    )
                    write_manifest(state_root, terminal_manifest)
                    write_telegram_state(state_root, telegram_state)
                    return terminal_manifest
                terminal_manifest = dict(current_manifest)
                terminal_manifest.update(
                    {
                        "status": "awaiting_packet_delivery",
                        "write_phase": "terminal",
                        "pending_packet_id": packet.get("packet_id"),
                        "pending_packet_type": packet.get("type"),
                        "last_action": decision.action,
                        "result_kind": "delivery_pending",
                    }
                )
                append_run_event(
                    state_root,
                    {
                        **base_event,
                        "packet_id": packet.get("packet_id"),
                        "packet_type": packet.get("type"),
                    },
                )
                write_manifest(state_root, terminal_manifest)
                write_telegram_state(state_root, telegram_state)
                return terminal_manifest

            if decision.kind == "launch":
                command = list(decision.command_spec.command)
                command_result = {
                    "exit_code": 0,
                    "stdout_path": "",
                    "stderr_path": "",
                    "result_summary": None,
                }
                if not dry_run:
                    command_result = run_command(command, trace_id=trace_id, logs_dir=LOGS_DIR)

                terminal_manifest = dict(current_manifest)
                terminal_manifest.update(
                    {
                        "write_phase": "terminal",
                        "last_action": decision.action,
                        "last_dispatch_id": decision.dispatch_id or None,
                        "rerun_intent_id": decision.rerun_intent_id or None,
                        "exit_code": int(command_result["exit_code"]),
                        "stdout_path": command_result["stdout_path"] or None,
                        "stderr_path": command_result["stderr_path"] or None,
                        "result_summary": command_result["result_summary"],
                        "last_evidence_fingerprint": current_fingerprint,
                        "result_kind": decision.result_kind or ("dry_run_selected" if dry_run else "completed"),
                    }
                )

                if decision.action == "refresh" and int(command_result["exit_code"]) == 0:
                    post_refresh_fingerprint = current_fingerprint if dry_run else compute_active_evidence_fingerprint(evidence_dir)
                    terminal_manifest.update(
                        {
                            "refresh_generation": int(current_manifest.get("refresh_generation") or 0) + 1,
                            "post_refresh_fingerprint": post_refresh_fingerprint,
                        }
                    )
                if decision.action == "rebuild_queues" and int(command_result["exit_code"]) == 0:
                    terminal_manifest.update(
                        {
                            "last_rebuild_generation": int(current_manifest.get("refresh_generation") or 0),
                        }
                    )
                if int(command_result["exit_code"]) != 0:
                    incident_packet = build_incident_packet(
                        trace_id=trace_id,
                        action=decision.action,
                        command=command,
                        exit_code=int(command_result["exit_code"]),
                        stdout_path=str(command_result["stdout_path"]),
                        stderr_path=str(command_result["stderr_path"]),
                        snapshot=snapshot,
                    )
                    append_packet_event(state_root, incident_packet)
                    terminal_manifest.update(
                        {
                            "status": "awaiting_packet_delivery",
                            "pending_packet_id": incident_packet["packet_id"],
                            "pending_packet_type": incident_packet["type"],
                            "result_kind": "incident_created",
                        }
                    )
                    append_run_event(
                        state_root,
                        {
                            **base_event,
                            "exit_code": int(command_result["exit_code"]),
                            "packet_id": incident_packet["packet_id"],
                            "packet_type": incident_packet["type"],
                            "stdout_path": command_result["stdout_path"],
                            "stderr_path": command_result["stderr_path"],
                        },
                    )
                    write_manifest(state_root, terminal_manifest)
                    write_telegram_state(state_root, telegram_state)
                    return terminal_manifest

                terminal_manifest["status"] = "completed"
                append_run_event(
                    state_root,
                    {
                        **base_event,
                        "command": command,
                        "exit_code": int(command_result["exit_code"]),
                        "stdout_path": command_result["stdout_path"],
                        "stderr_path": command_result["stderr_path"],
                    },
                )
                write_manifest(state_root, terminal_manifest)
                write_telegram_state(state_root, telegram_state)
                return terminal_manifest

            terminal_manifest = dict(current_manifest)
            terminal_manifest.update(
                {
                    "status": decision.status,
                    "write_phase": "terminal",
                    "last_action": decision.action,
                    "result_kind": decision.result_kind,
                    "last_evidence_fingerprint": current_fingerprint,
                }
            )
            if decision.result_kind in {"owner_reply_applied", "default_applied"}:
                terminal_manifest["awaiting_owner_reply"] = False
            if decision.result_kind == "still_waiting":
                terminal_manifest["awaiting_owner_reply"] = True
            if decision.result_kind == "owner_reply_applied":
                terminal_manifest["status"] = "completed"
            if decision.result_kind == "default_applied":
                terminal_manifest["default_applied_at"] = base_event["ts"]
                pending_packet_id = str(current_manifest.get("pending_packet_id") or "").strip()
                if pending_packet_id:
                    append_packet_event(
                        state_root,
                        {
                            "event_type": "default_applied",
                            "packet_id": pending_packet_id,
                            "decision_status": "expired",
                            "applied_option_id": decision.extra.get("applied_option_id"),
                            "default_applied_at": base_event["ts"],
                            "telegram_update_id": None,
                        },
                    )
            append_run_event(state_root, base_event)
            write_manifest(state_root, terminal_manifest)
            write_telegram_state(state_root, telegram_state)
            return terminal_manifest
        except Exception as exc:
            packet = build_incident_packet(
                trace_id=trace_id,
                action="supervisor_main",
                command=[sys.executable, str(Path(__file__).resolve())],
                exit_code=1,
                stdout_path="",
                stderr_path="",
                snapshot=None,
                error_class="PERMANENT",
            )
            packet.update({"error": str(exc), "severity": "ERROR", "retriable": False})
            append_packet_event(state_root, packet)
            append_run_event(
                state_root,
                {
                    "ts": isoformat_z(datetime.now(timezone.utc)),
                    "trace_id": trace_id,
                    "rule": "CRASH_GUARD",
                    "action": "supervisor_main",
                    "status": "error",
                    "reason": "unhandled_exception",
                    "result_kind": "crash_guard_triggered",
                    "error_class": "PERMANENT",
                    "severity": "ERROR",
                    "retriable": False,
                    "error": str(exc),
                    "packet_id": packet["packet_id"],
                },
            )
            error_manifest = load_manifest(state_root)
            error_manifest.update(
                {
                    "trace_id": trace_id,
                    "status": "awaiting_packet_delivery",
                    "write_phase": "terminal",
                    "last_action": "supervisor_main",
                    "pending_packet_id": packet["packet_id"],
                    "pending_packet_type": packet["type"],
                    "result_kind": "crash_guard_triggered",
                    "error_class": "PERMANENT",
                    "severity": "ERROR",
                    "retriable": False,
                }
            )
            write_manifest(state_root, error_manifest)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one deterministic supervisor cycle.")
    parser.add_argument("--state-root", default=str(STATE_ROOT))
    parser.add_argument("--scout-cache-dir", default=str(SCOUT_CACHE_DIR))
    parser.add_argument("--evidence-dir", default=str(EVIDENCE_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-rerun", action="store_true")
    args = parser.parse_args()

    result = run_supervisor_cycle(
        state_root=Path(args.state_root),
        scout_cache_dir=Path(args.scout_cache_dir),
        evidence_dir=Path(args.evidence_dir),
        dry_run=bool(args.dry_run),
        force_rerun=bool(args.force_rerun),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

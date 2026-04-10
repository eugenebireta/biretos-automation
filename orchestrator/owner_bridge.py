"""
owner_bridge.py — Deterministic FSM processor for owner Telegram messages.

Reads owner_inbox.jsonl, classifies input, mutates manifest, writes responses
to owner_outbox.jsonl. Runs as a separate process from Gateway.

Architecture:
    Gateway (polling) -> owner_inbox.jsonl -> Bridge (this) -> owner_outbox.jsonl -> Gateway (send)
    Bridge -> manifest.json (FSM mutations only)

Invariants:
    - No Telegram API calls
    - No subprocess / network side-effects
    - No hidden mutations
    - Duplicate approve/reject = safe no-op
    - Unprocessable input -> DLQ, queue continues
    - All manifest writes use file locking

Usage:
    python orchestrator/owner_bridge.py              # one-shot: process pending inbox
    python orchestrator/owner_bridge.py --daemon      # loop every 5s

FSM Transition Matrix:
    See _TRANSITION_TABLE below for the complete deterministic mapping.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"
MANIFEST_PATH = ORCH_DIR / "manifest.json"
INBOX_PATH = ORCH_DIR / "owner_inbox.jsonl"
OUTBOX_PATH = ORCH_DIR / "owner_outbox.jsonl"
BRIDGE_STATE_PATH = ORCH_DIR / "bridge_state.json"
DLQ_PATH = ORCH_DIR / "owner_dlq.jsonl"
BRIDGE_LOG_PATH = ORCH_DIR / "bridge.log"
LOCK_PATH = ORCH_DIR / "orchestrator.lock"

logging.basicConfig(
    format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
    level=logging.INFO, stream=sys.stdout,
)
log = logging.getLogger("owner_bridge")


# ── Park states — must match main.py / telegram_bot.py ──────────────────

PARK_STATES = frozenset({
    "awaiting_owner_reply", "error", "blocked", "blocked_by_consensus",
    "parked_budget_daily", "parked_budget_run", "parked_api_outage",
})

# ── Input classification ────────────────────────────────────────────────

APPROVE_WORDS = frozenset({"ок", "ok", "да", "yes", "го", "давай", "продолжай"})
REJECT_WORDS = frozenset({"нет", "no", "стоп", "stop"})
STATUS_COMMANDS = frozenset({"/status", "/ping", "/health"})
MIN_FREETEXT_LEN = 5


def classify_input(text: str, manifest: dict) -> tuple[str, dict[str, Any]]:
    """Classify owner message into an action type.

    Returns:
        (input_type, payload) where input_type is one of:
        "approve", "reject", "decision", "freetext", "status",
        "too_short", "no_pending_state"
    """
    lower = text.lower().strip()

    # Status commands — always allowed regardless of FSM state
    if lower in STATUS_COMMANDS:
        return "status", {}

    fsm_state = manifest.get("fsm_state", "")

    # A/B/C decision — check pending_decision first
    pending = manifest.get("pending_decision")
    if pending and isinstance(pending, dict):
        options = pending.get("options", {})
        key = text.strip().upper()
        if key in options:
            return "decision", {"key": key, "text": options[key]}
        # Single letter not in options — falls through

    # Not in a park state — owner actions not applicable
    if fsm_state not in PARK_STATES:
        return "no_pending_state", {"fsm_state": fsm_state}

    # Approve / reject
    if lower in APPROVE_WORDS:
        return "approve", {}
    if lower in REJECT_WORDS:
        return "reject", {}

    # Free-text instruction
    if len(text) >= MIN_FREETEXT_LEN:
        return "freetext", {"instruction": text}

    return "too_short", {"length": len(text)}


# ═══════════════════════════════════════════════════════════════════════
# FSM TRANSITION TABLE
#
# (fsm_state ∈ PARK_STATES, input_type) -> handler
#
# Each handler returns: (manifest_updates: dict, outbox_text: str)
# If manifest_updates is empty -> no mutation (idempotent / reject)
# ═══════════════════════════════════════════════════════════════════════

def _handle_approve(manifest: dict, payload: dict) -> tuple[dict, str]:
    """Resume task — set fsm_state=ready, clear park_reason."""
    return (
        {
            "fsm_state": "ready",
            "last_verdict": None,
            "park_reason": None,
        },
        "Принято. Стройка продолжит при следующем цикле.",
    )


def _handle_reject(manifest: dict, payload: dict) -> tuple[dict, str]:
    """Keep task parked — no manifest mutation."""
    state = manifest.get("fsm_state", "?")
    return {}, f"Понял. Задача остаётся на паузе ({state})."


def _handle_decision(manifest: dict, payload: dict) -> tuple[dict, str]:
    """Apply A/B/C decision."""
    key = payload["key"]
    text = payload["text"]
    return (
        {
            "owner_decision": key,
            "owner_decision_text": text,
            "pending_decision": None,
            "fsm_state": "ready",
        },
        f"Принято: {key} — {text}",
    )


def _handle_freetext(manifest: dict, payload: dict) -> tuple[dict, str]:
    """Save owner instruction and resume."""
    instruction = payload["instruction"]
    preview = instruction[:120] + ("…" if len(instruction) > 120 else "")
    return (
        {
            "owner_instruction": instruction,
            "fsm_state": "ready",
            "last_verdict": None,
            "park_reason": None,
        },
        f"Принял инструкцию:\n\"{preview}\"\n\nСтройка учтёт при следующем цикле.",
    )


def _handle_status(manifest: dict, payload: dict) -> tuple[dict, str]:
    """Read-only status response — no manifest mutation."""
    state = manifest.get("fsm_state", "?")
    task = manifest.get("current_task_id") or "—"
    goal = (manifest.get("current_sprint_goal") or "—")[:200]
    verdict = manifest.get("last_verdict") or "—"
    park = manifest.get("park_reason") or "—"
    return {}, (
        f"Состояние: {state}\n"
        f"Задача: {task}\n"
        f"Цель: {goal}\n"
        f"Вердикт: {verdict}\n"
        f"Причина паузы: {park}"
    )


def _handle_no_pending(manifest: dict, payload: dict) -> tuple[dict, str]:
    """Owner sent message but no pending action. Save to inbox, no mutation."""
    state = payload.get("fsm_state", "?")
    return {}, f"Сейчас нет ожидающих действий (состояние: {state}). Сообщение сохранено."


def _handle_too_short(manifest: dict, payload: dict) -> tuple[dict, str]:
    """Message too short to be instruction, not a known command."""
    return {}, "Не понял. Напиши 'ок' / 'нет' или инструкцию (минимум 5 символов)."


# Dispatch table: input_type -> handler
_HANDLERS: dict[str, Any] = {
    "approve": _handle_approve,
    "reject": _handle_reject,
    "decision": _handle_decision,
    "freetext": _handle_freetext,
    "status": _handle_status,
    "no_pending_state": _handle_no_pending,
    "too_short": _handle_too_short,
}


# ── File helpers (reuse gateway patterns) ───────────────────────────────

def _iso_z(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


def _locked_append(path: Path, line: str) -> None:
    """Append one line with file locking (Windows + POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a", encoding="utf-8")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        fh.write(line.rstrip("\n") + "\n")
        fh.flush()
    finally:
        if sys.platform == "win32":
            import msvcrt
            try:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except (IOError, OSError):
                pass
        fh.close()


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _load_json(path: Path, default: dict) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return dict(default)


# ── Manifest locking (same pattern as main.py) ─────────────────────────

def _acquire_manifest_lock():
    """Non-blocking file lock for manifest writes. Returns fh or None."""
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


def _release_manifest_lock(fh) -> None:
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


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"fsm_state": "idle"}


def _save_manifest(m: dict) -> None:
    m["updated_at"] = _iso_z()
    MANIFEST_PATH.write_text(
        json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Bridge state (cursor + dedup) ──────────────────────────────────────

def _load_bridge_state() -> dict:
    return _load_json(BRIDGE_STATE_PATH, {
        "last_processed_update_id": 0,
        "last_processed_line": 0,
        "processed_count": 0,
        "dlq_count": 0,
    })


def _save_bridge_state(state: dict) -> None:
    _atomic_write_json(BRIDGE_STATE_PATH, state)


# ── Outbox helper ───────────────────────────────────────────────────────

def _enqueue_response(text: str, *, run_id: str | None = None,
                      event_type: str = "bridge_reply") -> str:
    """Write response to outbox for Gateway to deliver."""
    msg_id = f"br_{hashlib.md5(f'{time.time()}'.encode()).hexdigest()[:12]}"
    dedup_key = hashlib.md5(f"{run_id}|{event_type}|{text[:80]}".encode()).hexdigest()
    entry = {
        "ts": _iso_z(),
        "msg_id": msg_id,
        "text": text,
        "priority": "normal",
        "dedup_key": dedup_key,
        "status": "pending",
        "run_id": run_id,
        "event_type": event_type,
    }
    _locked_append(OUTBOX_PATH, json.dumps(entry, ensure_ascii=False))
    return msg_id


# ── Structured logging ──────────────────────────────────────────────────

def _log_event(level: str, event: str, **kw: Any) -> None:
    entry = {"ts": _iso_z(), "level": level, "event": event, **kw}
    try:
        _locked_append(BRIDGE_LOG_PATH, json.dumps(entry, ensure_ascii=False))
    except Exception:
        pass
    log.info("%s %s %s", level, event, kw or "")


# ── DLQ ─────────────────────────────────────────────────────────────────

def _send_to_dlq(inbox_entry: dict, reason: str) -> None:
    dlq_entry = {
        "ts": _iso_z(),
        "original": inbox_entry,
        "reason": reason,
    }
    _locked_append(DLQ_PATH, json.dumps(dlq_entry, ensure_ascii=False))
    _log_event("WARNING", "dlq_entry", reason=reason,
               update_id=inbox_entry.get("update_id"))


# ═══════════════════════════════════════════════════════════════════════
# CORE PROCESSING
# ═══════════════════════════════════════════════════════════════════════

def process_inbox_entry(entry: dict, bridge_state: dict) -> bool:
    """Process one inbox entry. Returns True if processed (or DLQ'd).

    Idempotency: entries with update_id <= last_processed_update_id are skipped.
    """
    update_id = entry.get("update_id") or 0
    last_processed = bridge_state.get("last_processed_update_id", 0)

    # Dedup: already processed
    if update_id and update_id <= last_processed:
        return True  # skip, already handled

    text = (entry.get("text") or "").strip()
    if not text:
        _send_to_dlq(entry, "empty_text")
        return True

    # Load manifest under lock
    lock_fh = _acquire_manifest_lock()
    if lock_fh is None:
        # Orchestrator is running — skip this cycle, retry later
        _log_event("INFO", "manifest_locked", update_id=update_id)
        return False  # don't advance cursor

    try:
        manifest = _load_manifest()

        # Classify input
        input_type, payload = classify_input(text, manifest)
        _log_event("INFO", "classify", input_type=input_type,
                   text_preview=text[:60], fsm_state=manifest.get("fsm_state"))

        # Get handler
        handler = _HANDLERS.get(input_type)
        if handler is None:
            _send_to_dlq(entry, f"unknown_input_type:{input_type}")
            return True

        # Execute handler — deterministic, no side-effects beyond dict
        updates, response_text = handler(manifest, payload)

        # Apply manifest updates if any
        if updates:
            # Idempotency: check fsm_state hasn't changed since classification
            current_state = manifest.get("fsm_state", "")
            if input_type in ("approve", "freetext", "decision"):
                if current_state not in PARK_STATES and current_state != "awaiting_owner_reply":
                    # State already changed (another process resumed) — no-op
                    _log_event("INFO", "idempotent_skip",
                               reason="state_already_changed",
                               expected_park=True, actual=current_state)
                    response_text = f"Задача уже в работе (состояние: {current_state})."
                    updates = {}

            if updates:
                for k, v in updates.items():
                    if v is None:
                        manifest.pop(k, None)
                    else:
                        manifest[k] = v
                _save_manifest(manifest)
                _log_event("INFO", "manifest_updated",
                           updates=list(updates.keys()),
                           new_state=manifest.get("fsm_state"))

        # Write response to outbox
        run_id = manifest.get("trace_id")
        _enqueue_response(response_text, run_id=run_id, event_type=f"bridge_{input_type}")

    except Exception as exc:
        _send_to_dlq(entry, f"processing_error:{exc!s:.200}")
        _log_event("ERROR", "process_error", error=str(exc)[:200],
                   update_id=update_id)
        return True  # DLQ'd — don't block queue
    finally:
        _release_manifest_lock(lock_fh)

    # Advance cursor
    if update_id:
        bridge_state["last_processed_update_id"] = max(
            bridge_state.get("last_processed_update_id", 0), update_id
        )
    bridge_state["processed_count"] = bridge_state.get("processed_count", 0) + 1
    return True


def process_all_pending() -> int:
    """Process all unprocessed inbox entries. Returns count processed.

    Uses dual cursor:
    - last_processed_line: line index in inbox file (handles entries without update_id)
    - last_processed_update_id: Telegram update_id (extra safety for gateway-format entries)
    """
    if not INBOX_PATH.exists():
        return 0

    bridge_state = _load_bridge_state()
    last_line = bridge_state.get("last_processed_line", 0)
    last_uid = bridge_state.get("last_processed_update_id", 0)

    # Read inbox
    try:
        raw_lines = INBOX_PATH.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return 0

    # Parse all non-empty lines with their index
    entries: list[tuple[int, dict]] = []
    for idx, raw in enumerate(raw_lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            entries.append((idx, json.loads(raw)))
        except json.JSONDecodeError:
            continue

    count = 0
    for idx, entry in entries:
        # Skip by line index (primary cursor)
        if idx < last_line:
            continue

        # Also skip by update_id if present (secondary cursor)
        update_id = entry.get("update_id") or 0
        if update_id and update_id <= last_uid:
            continue

        ok = process_inbox_entry(entry, bridge_state)
        if ok:
            count += 1
            # Advance line cursor
            bridge_state["last_processed_line"] = idx + 1
            _save_bridge_state(bridge_state)
        else:
            break  # manifest locked — retry later

    return count


# ── Entry points ────────────────────────────────────────────────────────

def run_once() -> int:
    """Process all pending inbox entries once."""
    count = process_all_pending()
    if count > 0:
        _log_event("INFO", "cycle_done", processed=count)
    return count


def run_daemon(interval: float = 5.0) -> None:
    """Loop: process inbox every `interval` seconds."""
    _log_event("INFO", "bridge_daemon_start", pid=os.getpid(), interval=interval)
    print(flush=True)
    print("=" * 50, flush=True)
    print("  OWNER BRIDGE v1.0", flush=True)
    print(f"  Polling inbox every {interval}s", flush=True)
    print("=" * 50, flush=True)
    print(flush=True)

    try:
        while True:
            try:
                run_once()
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                _log_event("ERROR", "daemon_error", error=str(exc)[:200])
            time.sleep(interval)
    except KeyboardInterrupt:
        _log_event("INFO", "bridge_daemon_stop", reason="keyboard_interrupt")
        print("\nBridge stopped.", flush=True)


def main():
    if "--daemon" in sys.argv:
        run_daemon()
    else:
        count = run_once()
        print(f"Processed {count} inbox entries.")


if __name__ == "__main__":
    main()

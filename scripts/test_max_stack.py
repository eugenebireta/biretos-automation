"""
test_max_stack.py — Self-test for MAX → Bridge → Claude pipeline.

Injects a test message with source="selftest" so the gateway NEVER
delivers it to MAX (target filter: gateway only sends target=="max").
Waits for a response in outbox, validates content.

Usage:
    python scripts/test_max_stack.py            # single test
    python scripts/test_max_stack.py --verbose  # show full response

Exit codes:
    0 — PASS (pipeline working)
    1 — FAIL (timeout, empty response, or error)

Run this BEFORE showing any MAX results to owner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCH = ROOT / "orchestrator"
INBOX_PATH = ORCH / "owner_inbox.jsonl"
OUTBOX_PATH = ORCH / "owner_outbox.jsonl"

TEST_SOURCE = "selftest"          # gateway ignores target=="selftest"
TIMEOUT_S = 120                   # max wait for response
POLL_INTERVAL = 1.0


def _append(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _outbox_lines_after(snapshot_count: int) -> list[dict]:
    if not OUTBOX_PATH.exists():
        return []
    lines = OUTBOX_PATH.read_text(encoding="utf-8").splitlines()
    result = []
    for ln in lines[snapshot_count:]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            result.append(json.loads(ln))
        except json.JSONDecodeError:
            pass
    return result


def _advance_bridge_cursor_to_end() -> None:
    """Set bridge last_processed_line to current inbox end.

    This skips all historical inbox entries so the bridge only processes
    the selftest entry, avoiding a long queue of old messages.
    """
    state_path = ORCH / "bridge_state.json"
    try:
        if not INBOX_PATH.exists():
            return
        line_count = len([
            ln for ln in INBOX_PATH.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ])
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            state = {}
        state["last_processed_line"] = line_count
        tmp = state_path.with_suffix(".tmp.selftest")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        import os
        os.replace(str(tmp), str(state_path))
    except Exception:
        pass


def run_selftest(question: str, verbose: bool = False) -> tuple[bool, str]:
    """
    Inject question → wait for bridge response → return (pass, response_text).
    Advances bridge cursor to skip old inbox entries before injecting.
    """
    uid = f"selftest_{hashlib.md5(f'{time.time()}'.encode()).hexdigest()[:8]}"

    # Skip old inbox backlog — bridge only processes this new entry
    _advance_bridge_cursor_to_end()

    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "msg_id": uid,
        "update_id": uid,
        "chat_id": "selftest",           # not a real chat_id — gateway ignores
        "text": question,
        "source": TEST_SOURCE,           # → target="selftest" in outbox
        "event_type": "message",
        "callback_data": "",
        "raw_hash": hashlib.md5(question.encode()).hexdigest(),
    }

    # Snapshot outbox size before inject
    outbox_before = 0
    if OUTBOX_PATH.exists():
        outbox_before = len(OUTBOX_PATH.read_text(encoding="utf-8").splitlines())

    _append(INBOX_PATH, entry)

    if verbose:
        print(f"[selftest] Injected uid={uid}")
        print(f"[selftest] Question: {question}")
        print(f"[selftest] Waiting up to {TIMEOUT_S}s for bridge response...")

    deadline = time.time() + TIMEOUT_S
    seen_msg_ids: set[str] = set()

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        new_entries = _outbox_lines_after(outbox_before)
        for msg in new_entries:
            msg_id = msg.get("msg_id", "")
            if msg_id in seen_msg_ids:
                continue
            seen_msg_ids.add(msg_id)
            # Only look at selftest-targeted responses
            if msg.get("target") != TEST_SOURCE:
                continue
            text = msg.get("text", "").strip()
            if not text:
                continue
            return True, text

    return False, f"TIMEOUT — no response within {TIMEOUT_S}s"


def main() -> None:
    parser = argparse.ArgumentParser(description="MAX stack self-test")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--question", default="что такое DR в проекте? одно предложение",
    )
    args = parser.parse_args()

    if not INBOX_PATH.parent.exists():
        print("FAIL: orchestrator/ directory not found", file=sys.stderr)
        sys.exit(1)

    # Check bridge is running (bridge.log modified in last 30s)
    bridge_log = ORCH / "bridge.log"
    if bridge_log.exists():
        age = time.time() - bridge_log.stat().st_mtime
        if age > 30:
            print(
                f"WARNING: bridge.log last modified {age:.0f}s ago — bridge may not be running",
                file=sys.stderr,
            )

    print(f"[selftest] Question: {args.question}")
    ok, text = run_selftest(args.question, verbose=args.verbose)

    if ok:
        # Validate response is meaningful (not an error/empty)
        if len(text) < 10:
            print(f"FAIL: response too short: {repr(text)}")
            sys.exit(1)
        if text.startswith("Ошибка:") or text.startswith("TIMEOUT"):
            print(f"FAIL: {text}")
            sys.exit(1)
        print(f"PASS — response ({len(text)} chars):")
        print(text[:500])
        sys.exit(0)
    else:
        print(f"FAIL: {text}")
        sys.exit(1)


if __name__ == "__main__":
    main()

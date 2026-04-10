"""
start_telegram.py — Unified launcher for the Telegram Control Plane.

Starts all 3 processes in one terminal:
    1. Gateway  — Telegram polling + outbox delivery
    2. Bridge   — inbox FSM processor (manifest mutations)
    3. Watcher  — polls manifest, spawns main.py on ready

All processes run as child subprocesses. If any crashes, it is
automatically restarted after a brief delay. Ctrl+C stops all.

Usage:
    python orchestrator/start_telegram.py
    python orchestrator/start_telegram.py --no-watcher   # gateway + bridge only
"""
from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"

PYTHON = sys.executable

PROCESSES = {
    "gateway": {
        "cmd": [PYTHON, str(ORCH_DIR / "telegram_gateway.py")],
        "label": "Gateway",
        "restart_delay": 5,
    },
    "bridge": {
        "cmd": [PYTHON, str(ORCH_DIR / "owner_bridge.py"), "--daemon"],
        "label": "Bridge",
        "restart_delay": 3,
    },
    "watcher": {
        "cmd": [PYTHON, str(ORCH_DIR / "resume_watcher.py")],
        "label": "Watcher",
        "restart_delay": 5,
    },
}

# Global state
_children: dict[str, subprocess.Popen] = {}
_stopping = False


def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [launcher] {msg}", flush=True)


def _start_process(name: str) -> subprocess.Popen | None:
    """Start a named process. Returns Popen or None on error."""
    spec = PROCESSES[name]
    _log(f"Starting {spec['label']}...")
    try:
        proc = subprocess.Popen(
            spec["cmd"],
            cwd=str(ROOT),
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        _log(f"{spec['label']} started (PID {proc.pid})")
        return proc
    except OSError as exc:
        _log(f"Failed to start {spec['label']}: {exc}")
        return None


def _stop_all() -> None:
    """Gracefully terminate all children."""
    global _stopping
    _stopping = True
    for name, proc in _children.items():
        if proc and proc.poll() is None:
            label = PROCESSES[name]["label"]
            _log(f"Stopping {label} (PID {proc.pid})...")
            proc.terminate()

    # Wait for graceful exit
    deadline = time.time() + 5
    for name, proc in _children.items():
        if proc and proc.poll() is None:
            remaining = max(0, deadline - time.time())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                _log(f"Force-killing {PROCESSES[name]['label']} (PID {proc.pid})")
                proc.kill()
                proc.wait()

    _log("All processes stopped.")


def _signal_handler(signum, frame):
    _log("Shutdown signal received.")
    _stop_all()
    sys.exit(0)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Telegram Control Plane — unified launcher",
    )
    parser.add_argument(
        "--no-watcher", action="store_true",
        help="Don't start the Resume Watcher",
    )
    args = parser.parse_args()

    # Determine which processes to run
    names = ["gateway", "bridge"]
    if not args.no_watcher:
        names.append("watcher")

    print()
    print("=" * 56)
    print("  TELEGRAM CONTROL PLANE")
    print(f"  Launching: {', '.join(PROCESSES[n]['label'] for n in names)}")
    print("=" * 56)
    print()

    # Register signal handlers
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Start all processes
    for name in names:
        proc = _start_process(name)
        if proc:
            _children[name] = proc
        else:
            _log(f"FATAL: Could not start {PROCESSES[name]['label']}. Aborting.")
            _stop_all()
            sys.exit(1)

    _log(f"All {len(names)} processes running. Press Ctrl+C to stop.")

    # Supervisor loop: restart crashed children
    try:
        while not _stopping:
            for name in names:
                proc = _children.get(name)
                if proc and proc.poll() is not None:
                    rc = proc.returncode
                    label = PROCESSES[name]["label"]
                    delay = PROCESSES[name]["restart_delay"]
                    _log(f"{label} exited (rc={rc}). Restarting in {delay}s...")
                    time.sleep(delay)
                    if _stopping:
                        break
                    new_proc = _start_process(name)
                    if new_proc:
                        _children[name] = new_proc
                    else:
                        _log(f"Failed to restart {label}. Continuing without it.")

            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        _stop_all()


if __name__ == "__main__":
    main()

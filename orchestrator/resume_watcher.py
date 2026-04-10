"""
resume_watcher.py — Polling launcher: watches manifest, spawns main.py on ready.

Dumb launcher. Read-only to manifest. No Telegram. No manifest writes.

Architecture:
    Bridge sets manifest.fsm_state = "ready"
    Watcher detects "ready" -> spawns `python orchestrator/main.py` as child
    main.py runs one cycle, mutates manifest itself

Invariants:
    - Singleton: only one watcher process via PID lock file
    - Read-only to manifest (never writes)
    - At most one child process at a time
    - Cooldown after each spawn (prevents tight loops)
    - Sidecar state: won't re-spawn on same manifest.updated_at
    - No Telegram, no network, no imports from bridge/gateway

Usage:
    python orchestrator/resume_watcher.py              # run forever
    python orchestrator/resume_watcher.py --once       # single check, exit
    python orchestrator/resume_watcher.py --interval 10  # custom poll interval
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"
MANIFEST_PATH = ORCH_DIR / "manifest.json"
MAIN_PY = ORCH_DIR / "main.py"
WATCHER_LOCK_PATH = ORCH_DIR / "watcher.lock"
WATCHER_STATE_PATH = ORCH_DIR / "watcher_state.json"
WATCHER_LOG_PATH = ORCH_DIR / "watcher.log"

DEFAULT_INTERVAL = 10  # seconds between polls
DEFAULT_COOLDOWN = 30  # seconds after spawn before next check
MAX_CONSECUTIVE_SPAWNS = 5  # safety: max spawns without manifest change

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ── Singleton lock ─────────────────────────────────────────────────────

def acquire_singleton() -> object | None:
    """Acquire singleton PID lock. Returns file handle or None."""
    try:
        fh = open(WATCHER_LOCK_PATH, "w")
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


def release_singleton(fh) -> None:
    """Release singleton lock."""
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


# ── Sidecar state ──────────────────────────────────────────────────────

def _load_watcher_state() -> dict:
    if WATCHER_STATE_PATH.exists():
        try:
            return json.loads(WATCHER_STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_spawned_at": None,
        "last_manifest_updated_at": None,
        "consecutive_spawns": 0,
        "total_spawns": 0,
    }


def _save_watcher_state(state: dict) -> None:
    WATCHER_STATE_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── Manifest reader (read-only) ───────────────────────────────────────

def read_manifest() -> dict | None:
    """Read manifest without locking. Returns None on failure."""
    if not MANIFEST_PATH.exists():
        return None
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ── Spawn logic ────────────────────────────────────────────────────────

def should_spawn(manifest: dict, watcher_state: dict, cooldown: float) -> tuple[bool, str]:
    """Decide whether to spawn main.py.

    Returns (should_spawn, reason).
    """
    fsm_state = manifest.get("fsm_state", "")
    if fsm_state != "ready":
        return False, f"fsm_state={fsm_state} (not ready)"

    # Cooldown check
    last_spawned = watcher_state.get("last_spawned_at")
    if last_spawned is not None:
        elapsed = time.time() - last_spawned
        if elapsed < cooldown:
            return False, f"cooldown ({elapsed:.0f}s / {cooldown:.0f}s)"

    # Sidecar dedup: don't re-spawn on same manifest.updated_at
    manifest_ts = manifest.get("updated_at", "")
    last_ts = watcher_state.get("last_manifest_updated_at", "")
    if manifest_ts and manifest_ts == last_ts:
        return False, f"same manifest.updated_at={manifest_ts}"

    # Safety: max consecutive spawns without manifest change
    if watcher_state.get("consecutive_spawns", 0) >= MAX_CONSECUTIVE_SPAWNS:
        return False, f"consecutive_spawns={watcher_state['consecutive_spawns']} >= {MAX_CONSECUTIVE_SPAWNS}"

    return True, "ready"


def spawn_main(watcher_state: dict, manifest: dict) -> subprocess.Popen | None:
    """Spawn main.py as subprocess. Updates watcher_state. Returns Popen or None."""
    python = sys.executable
    cmd = [python, str(MAIN_PY)]

    logger.info("spawn %s", {"cmd": " ".join(cmd), "manifest_state": manifest.get("fsm_state")})

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        logger.error("spawn_failed %s", {"error": str(exc)})
        return None

    manifest_ts = manifest.get("updated_at", "")
    last_ts = watcher_state.get("last_manifest_updated_at", "")

    watcher_state["last_spawned_at"] = time.time()
    watcher_state["total_spawns"] = watcher_state.get("total_spawns", 0) + 1

    if manifest_ts == last_ts:
        watcher_state["consecutive_spawns"] = watcher_state.get("consecutive_spawns", 0) + 1
    else:
        watcher_state["consecutive_spawns"] = 1
        watcher_state["last_manifest_updated_at"] = manifest_ts

    _save_watcher_state(watcher_state)
    return proc


# ── Main loop ──────────────────────────────────────────────────────────

def run_once(cooldown: float = DEFAULT_COOLDOWN) -> bool:
    """Single poll check. Returns True if spawned."""
    manifest = read_manifest()
    if manifest is None:
        logger.debug("no manifest")
        return False

    watcher_state = _load_watcher_state()

    ok, reason = should_spawn(manifest, watcher_state, cooldown)
    if not ok:
        logger.debug("skip: %s", reason)
        return False

    proc = spawn_main(watcher_state, manifest)
    if proc is None:
        return False

    # Wait for child to complete (blocking — one child at a time)
    try:
        stdout, _ = proc.communicate(timeout=600)  # 10 min max
        rc = proc.returncode
        logger.info("child_done %s", {"pid": proc.pid, "rc": rc, "output_lines": len((stdout or b"").splitlines())})

        # Log child output to watcher log
        if stdout:
            try:
                with open(WATCHER_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(f"\n--- child pid={proc.pid} rc={rc} ---\n")
                    f.write(stdout.decode("utf-8", errors="replace"))
            except OSError:
                pass
    except subprocess.TimeoutExpired:
        logger.warning("child_timeout %s", {"pid": proc.pid})
        proc.kill()
        proc.wait()

    return True


def run_loop(interval: float = DEFAULT_INTERVAL, cooldown: float = DEFAULT_COOLDOWN) -> None:
    """Poll forever."""
    logger.info("watcher_start %s", {"pid": os.getpid(), "interval": interval, "cooldown": cooldown})
    print(f"\n{'=' * 50}")
    print("  RESUME WATCHER v1.0")
    print(f"  Polling manifest every {interval}s, cooldown {cooldown}s")
    print(f"{'=' * 50}\n")

    while True:
        try:
            run_once(cooldown=cooldown)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            logger.error("loop_error %s", {"error": str(exc)})

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            break

    logger.info("watcher_stop %s", {"pid": os.getpid()})


# ── CLI ────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Resume Watcher — poll manifest, spawn main.py")
    parser.add_argument("--once", action="store_true", help="Single check, then exit")
    parser.add_argument(
        "--interval", type=float, default=DEFAULT_INTERVAL,
        help=f"Poll interval (default {DEFAULT_INTERVAL}s)",
    )
    parser.add_argument(
        "--cooldown", type=float, default=DEFAULT_COOLDOWN,
        help=f"Cooldown after spawn (default {DEFAULT_COOLDOWN}s)",
    )
    args = parser.parse_args()

    lock_fh = acquire_singleton()
    if lock_fh is None:
        print("[watcher] Another watcher is already running. Exiting.", file=sys.stderr)
        sys.exit(1)

    try:
        if args.once:
            spawned = run_once(cooldown=args.cooldown)
            print(f"[watcher] {'Spawned' if spawned else 'No spawn needed'}")
        else:
            run_loop(interval=args.interval, cooldown=args.cooldown)
    finally:
        release_singleton(lock_fh)


if __name__ == "__main__":
    main()

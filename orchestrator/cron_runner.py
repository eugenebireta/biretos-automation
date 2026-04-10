"""
cron_runner.py — runs orchestrator/main.py on a timer.

Usage:
    python orchestrator/cron_runner.py                  # run every 10 min
    python orchestrator/cron_runner.py --interval 300   # run every 5 min
    python orchestrator/cron_runner.py --once            # run once and exit

Loads ANTHROPIC_API_KEY from .env.auditors automatically.
Logs to orchestrator/cron.log.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"
LOG_PATH = ORCH_DIR / "cron.log"
DEFAULT_INTERVAL = 600  # 10 minutes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("cron_runner")


def _load_api_key() -> str:
    """Load ANTHROPIC_API_KEY from .env.auditors or environment."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        try:
            from dotenv import dotenv_values
            env_path = ROOT / "auditor_system" / "config" / ".env.auditors"
            key = dotenv_values(env_path).get("ANTHROPIC_API_KEY", "")
        except Exception:
            pass
    return key


def run_cycle() -> int:
    """Run one orchestrator cycle. Returns exit code."""
    key = _load_api_key()
    env = os.environ.copy()
    if key:
        env["ANTHROPIC_API_KEY"] = key
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        result = subprocess.run(
            [sys.executable, str(ORCH_DIR / "main.py")],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
            cwd=str(ROOT),
        )
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                log.info(line)
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                log.warning(line)
        return result.returncode
    except subprocess.TimeoutExpired:
        log.error("TIMEOUT after 300s")
        return -1
    except Exception as e:
        log.error("ERROR: %s", e)
        return -2


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Orchestrator cron runner")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help="Seconds between runs (default: 600)")
    parser.add_argument("--once", action="store_true",
                        help="Run once and exit")
    args = parser.parse_args()

    log.info("=== CRON RUNNER START (interval=%ds) ===", args.interval)

    while True:
        log.info("--- cycle start ---")
        code = run_cycle()
        log.info("--- cycle end (exit=%d) ---", code)

        if args.once:
            break

        log.info("sleeping %ds...", args.interval)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

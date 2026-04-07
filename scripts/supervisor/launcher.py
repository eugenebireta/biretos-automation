from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from supervisor import LOGS_DIR, PHOTO_LIMIT, PRICE_LIMIT, REFRESH_PREFIX, ROOT


@dataclass(frozen=True)
class CommandSpec:
    action: str
    command: list[str]
    params: dict[str, Any]


def build_photo_command(queue_path: Path, *, limit: int = PHOTO_LIMIT) -> CommandSpec:
    batch_limit = max(int(limit), 1)
    return CommandSpec(
        action="photo_pipeline",
        command=[
            sys.executable,
            str(ROOT / "scripts" / "photo_pipeline.py"),
            "--queue",
            str(queue_path),
            "--limit",
            str(batch_limit),
        ],
        params={"queue": str(queue_path), "limit": batch_limit},
    )


def build_price_command(queue_path: Path, *, limit: int = PRICE_LIMIT) -> CommandSpec:
    batch_limit = max(int(limit), 1)
    return CommandSpec(
        action="price_scout",
        command=[
            sys.executable,
            str(ROOT / "scripts" / "run_price_only_scout_pilot.py"),
            "--queue",
            str(queue_path),
            "--limit",
            str(batch_limit),
        ],
        params={"queue": str(queue_path), "limit": batch_limit},
    )


def build_refresh_command() -> CommandSpec:
    return CommandSpec(
        action="refresh",
        command=[
            sys.executable,
            str(ROOT / "scripts" / "local_catalog_refresh.py"),
            "--promote-canonical",
        ],
        params={"promote_canonical": True},
    )


def build_rebuild_command() -> CommandSpec:
    return CommandSpec(
        action="rebuild_queues",
        command=[
            sys.executable,
            str(ROOT / "scripts" / "build_catalog_followup_queues.py"),
            "--prefix",
            REFRESH_PREFIX,
        ],
        params={"prefix": REFRESH_PREFIX},
    )


def parse_summary_from_stdout(stdout: str) -> dict[str, Any] | None:
    text = str(stdout or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def run_command(command: list[str], *, trace_id: str, logs_dir: Path = LOGS_DIR) -> dict[str, Any]:
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / f"{trace_id}.stdout.log"
    stderr_path = logs_dir / f"{trace_id}.stderr.log"

    env = os.environ.copy()
    env["BIRETOS_TRACE_ID"] = trace_id

    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    return {
        "exit_code": int(completed.returncode),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "result_summary": parse_summary_from_stdout(completed.stdout or ""),
    }

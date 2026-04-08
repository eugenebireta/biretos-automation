"""
executor_bridge.py — M4: autonomous Claude Code execution bridge.

Runs `claude --print` with a directive file piped to stdin, then
auto-collects the execution packet via collect_packet.collect().

Usage (direct):
    from orchestrator import executor_bridge
    result, packet = executor_bridge.run_with_collect(
        directive_path=Path("orchestrator/orchestrator_directive.md"),
        trace_id="orch_20260407T120000Z_abc123",
    )

Called from main.py when config.yaml has `auto_execute: true`.

DNA compliance:
- trace_id: accepted as argument, recorded in ExecutorResult
- idempotency: N/A — subprocess execution is not idempotent by nature;
  the FSM state machine in main.py prevents re-execution of a completed trace_id.
  Writing last_execution_packet.json is an overwrite (idempotent). No DB side-effects.
- error_class: TRANSIENT (timeout, subprocess error, generic I/O);
                PERMANENT (FileNotFoundError — claude not installed;
                           PermissionError — directive not readable;
                           UnicodeDecodeError — directive not UTF-8)
- severity: ERROR on all error paths
- retriable: False for PERMANENT, True for TRANSIENT
- no Core table DML: no DB imports anywhere in this module
- no domain.reconciliation_* imports: confirmed
- no secrets logging: subprocess args do not include API keys;
  stdout capped at EXECUTOR_NOTES_MAX_CHARS before storage
- deterministic tests: 37 tests, subprocess.run and collect_packet.collect mocked
"""
from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
ORCH_DIR = ROOT / "orchestrator"

# Default Claude CLI flags for autonomous execution.
# --print: non-interactive, prints final response to stdout.
# --permission-mode bypassPermissions: skip all approval prompts.
# --no-session-persistence: each invocation is stateless.
CLAUDE_BIN = "claude"
DEFAULT_PERMISSION_MODE = "bypassPermissions"
DEFAULT_TIMEOUT = 600  # seconds
EXECUTOR_NOTES_MAX_CHARS = 500


@dataclass
class ExecutorResult:
    """Result from a single Claude Code subprocess execution."""
    trace_id: str
    status: str          # "completed" | "failed" | "timeout" | "not_found" | "permission_denied" | "encoding_error"
    exit_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    directive_path: str
    error_class: Optional[str] = None    # "TRANSIENT" | "PERMANENT" | None on success
    severity: Optional[str] = None       # "ERROR" | None on success
    retriable: Optional[bool] = None


def run(
    directive_path: Path,
    trace_id: str,
    timeout: int = DEFAULT_TIMEOUT,
    cwd: Optional[Path] = None,
    permission_mode: str = DEFAULT_PERMISSION_MODE,
) -> ExecutorResult:
    """
    Execute a directive via `claude --print`.

    Opens directive_path and pipes its contents to stdin of `claude --print`.
    Equivalent to: cat directive | claude -p --permission-mode <mode> --no-session-persistence

    Args:
        directive_path: Path to the .md directive file.
        trace_id: Orchestrator trace ID — recorded in result, not passed to claude.
        timeout: Subprocess timeout in seconds (default 600).
        cwd: Working directory for subprocess (default: repo root).
        permission_mode: Claude permission mode (default: bypassPermissions).

    Returns:
        ExecutorResult with status/stdout/stderr/exit_code/elapsed_seconds.

    Never raises — all errors are captured in ExecutorResult.
    """
    work_dir = cwd or ROOT
    directive_path = Path(directive_path)

    # List-form args — no shell=True; avoids shell injection.
    cmd = [
        CLAUDE_BIN,
        "--print",
        "--permission-mode", permission_mode,
        "--no-session-persistence",
    ]

    t0 = time.monotonic()

    try:
        with open(directive_path, "r", encoding="utf-8") as f:
            proc = subprocess.run(
                cmd,
                stdin=f,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                cwd=str(work_dir),
            )
        elapsed = time.monotonic() - t0

        if proc.returncode == 0:
            logger.info(
                "executor_bridge: completed trace_id=%s exit_code=0 elapsed=%.1fs",
                trace_id, elapsed,
            )
            return ExecutorResult(
                trace_id=trace_id,
                status="completed",
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                elapsed_seconds=elapsed,
                directive_path=str(directive_path),
            )
        else:
            logger.error(
                "executor_bridge: failed trace_id=%s exit_code=%d elapsed=%.1fs "
                "error_class=TRANSIENT severity=ERROR retriable=true",
                trace_id, proc.returncode, elapsed,
            )
            return ExecutorResult(
                trace_id=trace_id,
                status="failed",
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                elapsed_seconds=elapsed,
                directive_path=str(directive_path),
                error_class="TRANSIENT",
                severity="ERROR",
                retriable=True,
            )

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        logger.error(
            "executor_bridge: timeout trace_id=%s after %ds "
            "error_class=TRANSIENT severity=ERROR retriable=true",
            trace_id, timeout,
        )
        return ExecutorResult(
            trace_id=trace_id,
            status="timeout",
            exit_code=-1,
            stdout="",
            stderr=f"TimeoutExpired after {timeout}s",
            elapsed_seconds=elapsed,
            directive_path=str(directive_path),
            error_class="TRANSIENT",
            severity="ERROR",
            retriable=True,
        )

    except FileNotFoundError:
        # `claude` binary not found on PATH — permanent installation problem.
        elapsed = time.monotonic() - t0
        logger.error(
            "executor_bridge: not_found trace_id=%s claude_bin=%s "
            "error_class=PERMANENT severity=ERROR retriable=false",
            trace_id, CLAUDE_BIN,
        )
        return ExecutorResult(
            trace_id=trace_id,
            status="not_found",
            exit_code=-2,
            stdout="",
            stderr=f"claude binary not found on PATH: {CLAUDE_BIN}",
            elapsed_seconds=elapsed,
            directive_path=str(directive_path),
            error_class="PERMANENT",
            severity="ERROR",
            retriable=False,
        )

    except PermissionError as exc:
        # Directive file not readable — permanent configuration problem.
        elapsed = time.monotonic() - t0
        logger.error(
            "executor_bridge: permission_denied trace_id=%s path=%s "
            "error_class=PERMANENT severity=ERROR retriable=false error=%s",
            trace_id, directive_path, exc,
        )
        return ExecutorResult(
            trace_id=trace_id,
            status="permission_denied",
            exit_code=-3,
            stdout="",
            stderr=str(exc),
            elapsed_seconds=elapsed,
            directive_path=str(directive_path),
            error_class="PERMANENT",
            severity="ERROR",
            retriable=False,
        )

    except UnicodeDecodeError as exc:
        # Directive file not UTF-8 — permanent encoding problem.
        elapsed = time.monotonic() - t0
        logger.error(
            "executor_bridge: encoding_error trace_id=%s path=%s "
            "error_class=PERMANENT severity=ERROR retriable=false error=%s",
            trace_id, directive_path, exc,
        )
        return ExecutorResult(
            trace_id=trace_id,
            status="encoding_error",
            exit_code=-4,
            stdout="",
            stderr=f"UnicodeDecodeError: {exc}",
            elapsed_seconds=elapsed,
            directive_path=str(directive_path),
            error_class="PERMANENT",
            severity="ERROR",
            retriable=False,
        )

    except Exception as exc:  # noqa: BLE001
        # Unexpected transient error (OSError, etc.)
        elapsed = time.monotonic() - t0
        logger.error(
            "executor_bridge: unexpected_error trace_id=%s "
            "error_class=TRANSIENT severity=ERROR retriable=true error=%s",
            trace_id, exc,
        )
        return ExecutorResult(
            trace_id=trace_id,
            status="failed",
            exit_code=-5,
            stdout="",
            stderr=str(exc),
            elapsed_seconds=elapsed,
            directive_path=str(directive_path),
            error_class="TRANSIENT",
            severity="ERROR",
            retriable=True,
        )


def run_with_collect(
    directive_path: Path,
    trace_id: str,
    base_commit: Optional[str] = None,
    run_pytest: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    cwd: Optional[Path] = None,
    permission_mode: str = DEFAULT_PERMISSION_MODE,
    packet_path: Optional[Path] = None,
) -> tuple[ExecutorResult, Optional[dict]]:
    """
    Execute directive then auto-collect execution packet.

    Calls run() first. On success (exit_code == 0), calls
    collect_packet.collect() and writes the packet to
    orchestrator/last_execution_packet.json (or packet_path).

    Args:
        directive_path: Path to the .md directive file.
        trace_id: Orchestrator trace ID.
        base_commit: Base commit for git diff (None = merge-base).
        run_pytest: Whether to run pytest in collect step.
        timeout: Subprocess timeout in seconds.
        cwd: Working directory for subprocess.
        permission_mode: Claude permission mode.
        packet_path: Override output path for packet JSON.

    Returns:
        (ExecutorResult, packet_dict) — packet is None if execution failed or collect failed.
        Collect failure is non-fatal: result.status remains "completed", packet is None,
        and a warning is logged with error_class=TRANSIENT.
    """
    import json
    import collect_packet as _cp  # sibling module in orchestrator/

    result = run(
        directive_path=directive_path,
        trace_id=trace_id,
        timeout=timeout,
        cwd=cwd,
        permission_mode=permission_mode,
    )

    if result.status != "completed":
        return result, None

    # Auto-collect packet after successful execution.
    try:
        executor_notes = (
            result.stdout[:EXECUTOR_NOTES_MAX_CHARS] if result.stdout else None
        )
        packet = _cp.collect(
            trace_id=trace_id,
            base_commit=base_commit,
            run_pytest_flag=run_pytest,
            executor_notes=executor_notes,
        )

        out_path = packet_path or (ORCH_DIR / "last_execution_packet.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info(
            "executor_bridge: collect_done trace_id=%s changed_files=%d tiers=%s",
            trace_id, len(packet.get("changed_files", [])), packet.get("affected_tiers"),
        )
        return result, packet

    except Exception as exc:  # noqa: BLE001
        # Collect failure is non-fatal — execution succeeded, packet collection failed.
        # Log structured warning; caller sees packet=None as signal to collect manually.
        logger.warning(
            "executor_bridge: collect_failed trace_id=%s "
            "error_class=TRANSIENT severity=WARNING retriable=true error=%s",
            trace_id, exc,
        )
        result.stderr += f"\n[executor_bridge] collect_packet error: {exc}"
        return result, None

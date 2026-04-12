"""
auditor_system/execution_gate.py — L2 Execution Gate.

Consensus Pipeline Protocol v1: L2 runs BEFORE L1 critics.
Critics receive code + execution evidence, not just code text.

What this does:
  1. Runs test_commands from TaskPack (pytest, dry-run scripts, etc.)
  2. Checks coverage assertions if applicable
  3. Captures stdout/stderr (trimmed to 8KB max for critic context)
  4. Returns L2Report with pass/fail + evidence

Design rules:
  - Zero LLM calls — deterministic CPU-only gate
  - Max output 8KB (critics must not drown in logs)
  - Frozen validation scripts: if builder touched them → hard block
  - Circuit breaker: max 3 attempts, then HALTED
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from pathlib import Path

from .hard_shell.contracts import AssertionResult, L2Report, TaskPack

logger = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 8 * 1024        # 8KB total cap for L2Report
MAX_TRACEBACK_LINES = 50
OUTPUT_SAMPLE_BYTES = 2 * 1024     # 2KB stdout sample


class FrozenScriptViolationError(Exception):
    """Builder touched a frozen validation script — hard block."""

    def __init__(self, script: str, task_id: str):
        self.script = script
        self.task_id = task_id
        super().__init__(
            f"HARD_BLOCK: Builder modified frozen validation script "
            f"'{script}' for task {task_id} — "
            "this is not allowed (Consensus Pipeline Protocol v1, §4)"
        )


class ExecutionGate:
    """
    L2 gate: runs commands, checks assertions, returns L2Report.
    Stateless — create once, call run() per attempt.
    """

    def __init__(
        self,
        cwd: str | Path | None = None,
        timeout_seconds: int = 120,
    ):
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self.timeout_seconds = timeout_seconds

    def check_frozen_scripts(
        self,
        task: TaskPack,
        changed_files: list[str],
    ) -> None:
        """
        Hard block if builder touched a frozen validation script.
        Call this BEFORE running L2 (detect violation early).
        """
        if not task.frozen_validation_scripts:
            return
        for frozen in task.frozen_validation_scripts:
            for changed in changed_files:
                # Normalize paths for comparison
                if Path(frozen).resolve() == Path(changed).resolve():
                    raise FrozenScriptViolationError(frozen, task.task_id)
                # Also catch by filename if paths differ
                if Path(frozen).name == Path(changed).name:
                    logger.warning(
                        "execution_gate: possible frozen script touch "
                        "frozen=%s changed=%s task_id=%s",
                        frozen, changed, task.task_id,
                    )

    def _run_command(self, cmd: str) -> tuple[int, str, str]:
        """
        Run a shell command, return (exit_code, stdout, stderr).
        Enforces timeout.
        """
        logger.info("execution_gate: running command=%r cwd=%s", cmd, self.cwd)
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=str(self.cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.error(
                "execution_gate: command timed out after %ds cmd=%r",
                self.timeout_seconds, cmd,
            )
            return -1, "", f"TIMEOUT after {self.timeout_seconds}s"
        except Exception as exc:
            logger.error("execution_gate: command error cmd=%r error=%s", cmd, exc)
            return -1, "", str(exc)

    def _build_assertions(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        cmd: str,
    ) -> list[AssertionResult]:
        """
        Build machine-readable assertions from execution output.
        These are deterministic checks, not LLM interpretations.
        """
        assertions = []

        # Assertion 1: exit code
        assertions.append(AssertionResult(
            name="exit_code_zero",
            expected="0",
            actual=str(exit_code),
            status="PASS" if exit_code == 0 else "FAIL",
        ))

        # Assertion 2: no Python traceback
        has_traceback = "Traceback (most recent call last)" in stderr
        assertions.append(AssertionResult(
            name="no_python_traceback",
            expected="no traceback",
            actual="traceback found" if has_traceback else "no traceback",
            status="FAIL" if has_traceback else "PASS",
        ))

        # Assertion 3: pytest-specific — parse pass/fail counts
        if "pytest" in cmd.lower() and stdout:
            pytest_pass = self._check_pytest_output(stdout, stderr)
            assertions.append(pytest_pass)

        # Assertion 4: dry-run scripts should not modify real data
        if "--dry-run" in cmd:
            dry_run_ok = "DRY RUN" in stdout.upper() or exit_code == 0
            assertions.append(AssertionResult(
                name="dry_run_completed",
                expected="dry_run_ok",
                actual="ok" if dry_run_ok else "failed",
                status="PASS" if dry_run_ok else "FAIL",
            ))

        return assertions

    def _check_pytest_output(self, stdout: str, stderr: str) -> AssertionResult:
        """Parse pytest output for pass/fail summary."""
        combined = stdout + stderr
        # Look for pytest summary line: "X passed", "X failed", "X error"
        import re
        failed_match = re.search(r"(\d+) failed", combined)
        error_match = re.search(r"(\d+) error", combined)
        passed_match = re.search(r"(\d+) passed", combined)

        has_failures = bool(failed_match or error_match)
        passed_count = int(passed_match.group(1)) if passed_match else 0
        failed_count = int(failed_match.group(1)) if failed_match else 0
        error_count = int(error_match.group(1)) if error_match else 0

        actual = f"{passed_count} passed"
        if failed_count:
            actual += f", {failed_count} failed"
        if error_count:
            actual += f", {error_count} errors"

        return AssertionResult(
            name="pytest_no_failures",
            expected="0 failed, 0 errors",
            actual=actual,
            status="FAIL" if has_failures else "PASS",
        )

    def _trim_output(self, stdout: str, stderr: str) -> tuple[str, str | None]:
        """
        Trim output to stay within 8KB total for L2Report.
        Returns (output_sample, traceback_tail | None).
        """
        # stdout: first 2KB sample
        output_sample = stdout[:OUTPUT_SAMPLE_BYTES]
        if len(stdout) > OUTPUT_SAMPLE_BYTES:
            output_sample += f"\n... [{len(stdout) - OUTPUT_SAMPLE_BYTES} more bytes truncated]"

        # stderr: last 50 lines (most recent = most relevant for traceback)
        traceback_tail: str | None = None
        if stderr.strip():
            lines = stderr.splitlines()
            tail_lines = lines[-MAX_TRACEBACK_LINES:]
            traceback_tail = "\n".join(tail_lines)
            if len(lines) > MAX_TRACEBACK_LINES:
                traceback_tail = f"[first {len(lines) - MAX_TRACEBACK_LINES} lines omitted]\n" + traceback_tail

        return output_sample, traceback_tail

    async def run(
        self,
        task: TaskPack,
        git_diff_stat: str = "",
    ) -> L2Report:
        """
        Run L2 gate for a task.

        If task.test_commands is empty → returns a passing L2Report (backward compat).
        """
        if not task.test_commands:
            logger.info(
                "execution_gate: no test_commands configured, soft pass task_id=%s",
                task.task_id,
            )
            return L2Report(
                exit_code=0,
                diff_stat=git_diff_stat,
                output_sample="[L2 skipped: no test_commands configured]",
                command_run="(none)",
            )

        # Run commands sequentially; stop on first failure
        all_assertions: list[AssertionResult] = []
        final_exit_code = 0
        final_stdout = ""
        final_stderr = ""
        commands_run = []
        start_time = time.monotonic()

        for cmd in task.test_commands:
            exit_code, stdout, stderr = await asyncio.get_running_loop().run_in_executor(
                None, lambda c=cmd: self._run_command(c)
            )
            commands_run.append(cmd)
            assertions = self._build_assertions(exit_code, stdout, stderr, cmd)
            all_assertions.extend(assertions)

            if exit_code != 0:
                final_exit_code = exit_code
                final_stdout = stdout
                final_stderr = stderr
                logger.warning(
                    "execution_gate: command failed, stopping pipeline "
                    "cmd=%r exit_code=%d task_id=%s",
                    cmd, exit_code, task.task_id,
                )
                break
            else:
                final_stdout += stdout
                final_stderr += stderr
                logger.info(
                    "execution_gate: command passed cmd=%r task_id=%s",
                    cmd, task.task_id,
                )

        duration = time.monotonic() - start_time
        output_sample, traceback_tail = self._trim_output(final_stdout, final_stderr)

        report = L2Report(
            exit_code=final_exit_code,
            duration_seconds=round(duration, 2),
            assertions=all_assertions,
            diff_stat=git_diff_stat,
            traceback_tail=traceback_tail,
            output_sample=output_sample,
            command_run=" && ".join(commands_run),
        )

        logger.info(
            "execution_gate: L2Report exit_code=%d all_pass=%s "
            "assertions=%d duration=%.1fs task_id=%s",
            report.exit_code, report.all_pass,
            len(report.assertions), report.duration_seconds,
            task.task_id,
        )
        return report

    def get_git_diff_stat(self) -> str:
        """Get current git diff --stat for inclusion in L2Report."""
        exit_code, stdout, _ = self._run_command("git diff --stat HEAD")
        if exit_code == 0:
            return stdout.strip()[:500]  # cap at 500 chars
        return "(git diff --stat failed)"

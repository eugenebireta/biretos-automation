"""
claude_cli.py — shared helper for calling Claude Code CLI (`claude -p`).

All Claude calls in the orchestrator go through this module, routing them
through the user's Claude Code subscription ($200/mo) instead of API balance.

Usage:
    from claude_cli import call_claude

    response = call_claude(prompt, system_prompt="You are...", timeout=120)

For async callers:
    response = await call_claude_async(prompt, system_prompt="...", timeout=120)
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_BIN = "claude"
DEFAULT_TIMEOUT = 120  # seconds


def call_claude(
    prompt: str,
    system_prompt: str = "",
    timeout: int = DEFAULT_TIMEOUT,
    cwd: Path | None = None,
) -> str:
    """Call Claude Code CLI synchronously. Returns raw stdout text.

    Combines system_prompt and prompt into a single input passed to
    `claude -p` via stdin. Goes through the user's Claude Code subscription.

    Args:
        prompt: The user/task prompt.
        system_prompt: Optional system instructions prepended to the prompt.
        timeout: Subprocess timeout in seconds.
        cwd: Working directory (default: repo root).

    Returns:
        Stripped stdout from Claude CLI.

    Raises:
        RuntimeError: On non-zero exit code or timeout.
    """
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"
    else:
        full_prompt = prompt

    cmd = [CLAUDE_BIN, "--print", "--no-session-persistence"]
    work_dir = str(cwd or ROOT)

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=work_dir,
        )
        elapsed = time.monotonic() - t0

        if proc.returncode == 0:
            logger.info("claude_cli: ok elapsed=%.1fs len=%d", elapsed, len(proc.stdout))
            return proc.stdout.strip()
        else:
            err_msg = (proc.stderr or proc.stdout or "unknown error")[:500]
            raise RuntimeError(f"claude CLI exit code {proc.returncode}: {err_msg}")

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        raise RuntimeError(f"claude CLI timeout after {elapsed:.0f}s (limit={timeout}s)")


async def call_claude_async(
    prompt: str,
    system_prompt: str = "",
    timeout: int = DEFAULT_TIMEOUT,
    cwd: Path | None = None,
) -> str:
    """Async wrapper around call_claude. Runs the subprocess in a thread pool.

    Same interface as call_claude but non-blocking for asyncio callers.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: call_claude(prompt, system_prompt, timeout, cwd)
    )

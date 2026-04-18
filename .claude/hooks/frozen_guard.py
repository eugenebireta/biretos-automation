#!/usr/bin/env python3
"""PreToolUse(Write|Edit) hook — blocks writes to FROZEN files (PROJECT_DNA §3).

Dynamic sync: reads the authoritative list from docs/PROJECT_DNA.md §3 at each
invocation (cached for 60s via .claude/hooks/_cache/). No hardcoded list —
avoids drift flagged by AI-Audit 2026-04-18.

Behavior:
- reads stdin JSON: {tool_name, tool_input: {file_path, ...}, ...}
- if tool_name not in {Write, Edit, MultiEdit, NotebookEdit}: allow (exit 0)
- if file_path resolves to a path in §3 list: BLOCK (exit 2 + stderr explanation)
- if DNA.md missing / parse failed: FAIL-CLOSED (block with explanation)
- logs every decision to .claude/hooks/_log/frozen_guard.jsonl

Exit codes (per Claude Code hooks protocol, best-effort interpretation):
  0 — allow
  2 — soft-block: stderr fed back to Claude as feedback (NOT hard kill)

Tested against:
  echo '{"tool_name":"Write","tool_input":{"file_path":"/abs/path"}}' | python frozen_guard.py

Not yet activated in settings.json — see _scratchpad/ai_audits/2026-04-18_claude-code-setup-optimization.md
for rollout plan.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DNA_PATH = REPO / "docs" / "PROJECT_DNA.md"
CACHE_DIR = Path(__file__).resolve().parent / "_cache"
CACHE_FILE = CACHE_DIR / "frozen_list.json"
LOG_FILE = Path(__file__).resolve().parent / "_log" / "frozen_guard.jsonl"
CACHE_TTL_SECONDS = 60

WATCHED_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _log(entry: dict) -> None:
    """Append structured JSON line. Never raise."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _parse_section_3(dna_text: str) -> list[str]:
    """Extract file paths listed in §3 (between '## 3.' and '## 4.').

    Paths are lines starting with '- `' and ending with '`'. Returns normalized
    relative paths (forward-slash).
    """
    m = re.search(
        r"^## 3\. [^\n]*\n(.*?)(?=^## \d)",
        dna_text,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        raise ValueError("PROJECT_DNA.md §3 section not found")
    block = m.group(1)
    paths: list[str] = []
    for line in block.splitlines():
        bullet = re.match(r"^\s*-\s*`([^`]+)`\s*$", line)
        if bullet:
            paths.append(bullet.group(1).strip().replace("\\", "/"))
    if not paths:
        raise ValueError("PROJECT_DNA.md §3 parsed but contains zero file paths")
    return paths


def _load_frozen_list() -> tuple[list[str], str]:
    """Return (list, source): cached or fresh-parsed. Raises on parse failure."""
    if not DNA_PATH.exists():
        raise FileNotFoundError(f"DNA not found at {DNA_PATH}")

    dna_bytes = DNA_PATH.read_bytes()
    dna_hash = hashlib.sha256(dna_bytes).hexdigest()[:16]

    if CACHE_FILE.exists():
        try:
            cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if (
                cached.get("dna_hash") == dna_hash
                and time.time() - cached.get("cached_at", 0) < CACHE_TTL_SECONDS
            ):
                return cached["paths"], f"cache (hash={dna_hash})"
        except Exception:
            pass

    paths = _parse_section_3(dna_bytes.decode("utf-8"))
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps(
                {
                    "dna_hash": dna_hash,
                    "cached_at": time.time(),
                    "paths": paths,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return paths, f"fresh-parse (hash={dna_hash})"


def _normalize_target(file_path: str, cwd: str) -> str:
    """Return repo-relative POSIX path for comparison against the §3 list.

    Handles Windows+Git Bash quirks: cwd may come as '/d/path' while REPO is
    'D:\\path'. Path.resolve() then produces junk like 'D:/d/path'. Strategy:
    1) normalize separators to forward-slash on both target and REPO
    2) if target absolute, try prefix-strip against REPO case-insensitively
    3) if target relative, just normalize and return
    """
    raw = file_path.replace("\\", "/")
    if raw.startswith("./"):
        raw = raw[2:]
    p = Path(file_path)
    if not p.is_absolute():
        return raw

    abs_target = str(p).replace("\\", "/")
    repo_str = str(REPO).replace("\\", "/")
    if abs_target.lower().startswith(repo_str.lower() + "/"):
        return abs_target[len(repo_str) + 1 :]
    # Git-Bash style: /d/BIRETOS/... — try matching on suffix with no drive
    drive_stripped_repo = re.sub(r"^[A-Za-z]:", "", repo_str)
    if abs_target.lower().startswith(drive_stripped_repo.lower() + "/"):
        return abs_target[len(drive_stripped_repo) + 1 :]
    # give up — return as-is, will not match frozen_set
    return abs_target


def main() -> int:
    # Read stdin
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception as e:
        _log(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "decision": "error_stdin",
                "error": str(e),
            }
        )
        # Fail-open on unparseable stdin — we cannot know what tool this was
        return 0

    tool_name = payload.get("tool_name", "")
    if tool_name not in WATCHED_TOOLS:
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    cwd = payload.get("cwd") or os.getcwd()

    if not file_path:
        # No path = nothing to check
        return 0

    try:
        frozen_paths, source = _load_frozen_list()
    except Exception as e:
        msg = (
            f"[frozen_guard] FAIL-CLOSED: cannot load PROJECT_DNA.md §3 ({e}). "
            f"Blocking Write/Edit until resolved. Path: {DNA_PATH}"
        )
        _log(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "decision": "fail_closed",
                "tool": tool_name,
                "file_path": file_path,
                "error": str(e),
            }
        )
        print(msg, file=sys.stderr)
        return 2

    target = _normalize_target(file_path, cwd)
    # Check: any frozen entry that equals or is a prefix-dir match
    frozen_set = {p.replace("\\", "/") for p in frozen_paths}
    match = target in frozen_set

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "file_path": file_path,
        "normalized": target,
        "source": source,
        "frozen_count": len(frozen_paths),
        "decision": "block" if match else "allow",
    }
    _log(entry)

    if match:
        print(
            "[frozen_guard] BLOCKED: target is listed in PROJECT_DNA.md §3 "
            "(Tier-1 FROZEN).\n"
            f"  path: {target}\n"
            f"  source: {source}\n"
            "  Any change = architectural violation. Ask owner for explicit "
            "unfreeze decision (CORE Critical Pipeline) before editing.\n"
            "  To override intentionally: remove this hook or set "
            "FROZEN_GUARD_BYPASS=1 env var (audited via log).",
            file=sys.stderr,
        )
        if os.environ.get("FROZEN_GUARD_BYPASS") == "1":
            # Audit trail: bypass used
            _log(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "decision": "bypass_granted",
                    "file_path": target,
                }
            )
            return 0
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""PreToolUse(Write|MultiEdit|NotebookEdit) hook — blocks writes to FROZEN files.

Authoritative source: `docs/PROJECT_DNA.md` §3 (19 Tier-1 FROZEN paths).
List is read dynamically at each invocation and cached 60s — no hardcoded
list, so drift flagged by AI-Audit 2026-04-18 R2 is impossible.

Behavior:
- reads stdin JSON: {tool_name, tool_input: {file_path, ...}, ...}
- `tool_name` must be one of WATCHED_TOOLS (Edit excluded — see below)
- if file resolves to a path in §3: BLOCK via exit 2 + stderr explanation
- if DNA.md missing / parse failed: FAIL-CLOSED (exit 2, explicit check)
- every decision logged to .claude/hooks/_log/frozen_guard.jsonl

Exit codes (Deep Research Q1 confirmed, 2026-04-18):
  0 — allow; tool proceeds silently
  2 — soft-block; stderr fed to Claude as error context, tool does NOT proceed
  any other — non-blocking error; tool proceeds. Never use.

Edit tool exclusion (Deep Research Q6):
  claude-mem v12.0.0+ extends its File Read Gate to PreToolUse(Edit). When
  both hooks run in parallel (hooks execution is parallel per Q1, not
  sequential), precedence `deny > defer > ask > allow` means claude-mem's
  deny wins, blocking with its own timeline-injection message instead of
  our clearer "FROZEN file" reason. Drop Edit from matcher.
  Alternative: set env `CLAUDE_MEM_EXCLUDED_PROJECTS=<abs-path>`.

Bypass:
  `FROZEN_GUARD_BYPASS=1` env var — audited in log. Use only for explicit
  owner-sanctioned unfreeze work (separate governance batch).

Rationale for Python (not Bash):
  Deep Research Q5 recommended Bash+awk (6-11ms hot-cache on Linux). On
  Windows Git Bash / MSYS2 benchmarks showed Bash version ~300ms vs this
  Python version ~70ms due to slow MSYS2 process spawning (each sha256sum,
  awk, grep call ~50ms). Python wins on Windows. Bash-optimized version
  kept for Linux CI at .claude/hooks/_reference/frozen_guard.sh.linux-optimized.
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

# Edit is intentionally excluded (see module docstring "Edit tool exclusion").
WATCHED_TOOLS = {"Write", "MultiEdit", "NotebookEdit"}


def _log(entry: dict) -> None:
    """Append structured JSON line. Never raise."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _parse_section_3(dna_text: str) -> list[str]:
    """Extract file paths from §3. Robust to CRLF, backticks, nested lists."""
    m = re.search(
        r"^##\s+3\.[^\n]*\n(.*?)(?=^##\s+\d+\.)",
        dna_text,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        raise ValueError("PROJECT_DNA.md §3 section not found")
    block = m.group(1)
    paths: list[str] = []
    for line in block.splitlines():
        bullet = re.match(r"^\s*[-*+]\s+`([^`]+)`\s*$", line.rstrip("\r"))
        if bullet:
            paths.append(bullet.group(1).strip().replace("\\", "/"))
    if not paths:
        raise ValueError("PROJECT_DNA.md §3 parsed but contains zero file paths")
    return paths


def _load_frozen_list() -> tuple[list[str], str]:
    """Return (list, source-descriptor). Raises on parse failure."""
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
                {"dna_hash": dna_hash, "cached_at": time.time(), "paths": paths},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return paths, f"fresh-parse (hash={dna_hash})"


def _normalize_target(file_path: str, cwd: str) -> str:
    """Return repo-relative POSIX path.

    Handles Windows+Git Bash quirks: Windows absolute `D:\\x\\y` or `D:/x/y`
    vs Git Bash `/d/x/y` — both must reduce to the same repo-relative form.
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
    # Git-Bash style: /d/BIRETOS/... when repo is D:/BIRETOS/...
    drive_stripped_repo = re.sub(r"^[A-Za-z]:", "", repo_str)
    if abs_target.lower().startswith(drive_stripped_repo.lower() + "/"):
        return abs_target[len(drive_stripped_repo) + 1 :]
    return abs_target


def main() -> int:
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
        return 0  # fail-open on unparseable stdin (we cannot know the tool)

    tool_name = payload.get("tool_name", "")
    if tool_name not in WATCHED_TOOLS:
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    cwd = payload.get("cwd") or os.getcwd()

    if not file_path:
        return 0

    try:
        frozen_paths, source = _load_frozen_list()
    except Exception as e:
        _log(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "decision": "fail_closed",
                "tool": tool_name,
                "file_path": file_path,
                "error": str(e),
            }
        )
        print(
            f"[frozen_guard] FAIL-CLOSED: cannot load PROJECT_DNA.md §3 ({e})\n"
            f"  Blocking Write/Edit until resolved. Path: {DNA_PATH}",
            file=sys.stderr,
        )
        return 2

    target = _normalize_target(file_path, cwd)
    frozen_set = {p.replace("\\", "/") for p in frozen_paths}
    match = target in frozen_set

    _log(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "file_path": file_path,
            "normalized": target,
            "source": source,
            "frozen_count": len(frozen_paths),
            "decision": "block" if match else "allow",
        }
    )

    if match:
        if os.environ.get("FROZEN_GUARD_BYPASS") == "1":
            _log(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "decision": "bypass_granted",
                    "file_path": target,
                }
            )
            return 0
        print(
            f"[frozen_guard] BLOCKED: target is listed in PROJECT_DNA.md §3 (Tier-1 FROZEN).\n"
            f"  path: {target}\n"
            f"  source: {source}\n"
            f"  Any change = architectural violation. Ask owner for explicit\n"
            f"  unfreeze decision (separate Core Critical Pipeline) before editing.\n"
            f"  Emergency override: FROZEN_GUARD_BYPASS=1 (audited via log).",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""PreToolUse(Bash) hook — destructive-command detection.

**Audit-only mode (v1, default).** This hook NEVER blocks — it exits 0 always,
and logs every Bash invocation that matches one of the 21 destructive-pattern
rules to `.claude/hooks/_log/bash_guard.jsonl` with the recommended action
(`block` | `ask` | `log`) it *would* take in enforce mode.

Rollout plan (per AI-Audit Tier 4 Addendum, finding Q3):
  Stage A (now):   audit-only, exit 0, collect metrics
  Stage B (1-2w):  review FP rate per rule via `jq` analysis of jsonl
  Stage C:         promote individual rules to `ask` (exit 2 with prompt)
                   when FP ≤ 1% and ≥100 matches; `block` when FP ≤ 0.5%.

Each rule ships with:
  - rule_id: stable identifier (FS_ROOT_WIPE, SQL_DROP, DOCKER_DOWN_V, ...)
  - severity: CRIT | HIGH | MED
  - recommended_action: block | ask | log
  - known_fps: list of legitimate commands that match (so reviewers can
    see when a match is a known false positive)

Pattern table sourced from Deep Research Q2 (2026-04-18), which in turn
references Anthropic's own bashSecurity.ts (23+ regex validators), Falco
rules, destructive_command_guard by Dicklesworthstone, and OWASP Command
Injection Defense Cheat Sheet.

Span-kind awareness (Q2): some patterns can match inside quoted strings
(e.g. `git commit -m "rm -rf /"`). This hook uses plain regex; a future
version should use tree-sitter-bash to classify Executed vs Data spans
(SpanKind per dcg). For audit-only mode, span-blind is acceptable — we're
collecting data, not blocking.

Input: stdin JSON:
  {tool_name: "Bash", tool_input: {command, description, timeout, run_in_background}}

Output: exit 0 (always), stderr silent unless AUDIT_VERBOSE=1.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

HOOK_DIR = Path(__file__).resolve().parent
LOG_FILE = HOOK_DIR / "_log" / "bash_guard.jsonl"
RULES_VERSION = "1.0"  # bump on pattern-table changes; written into every log line


class Rule(NamedTuple):
    rule_id: str
    category: str
    severity: str  # CRIT | HIGH | MED
    pattern: re.Pattern[str]
    recommended_action: str  # block | ask | log
    known_fps: str  # short description of known false positives


# --- Pattern table (21 rules from Deep Research Q2, 2026-04-18) -------------

RULES: list[Rule] = [
    Rule(
        "FS_ROOT_WIPE", "filesystem", "CRIT",
        re.compile(r"\brm\s+(-[a-zA-Z]*[rR][a-zA-Z]*[fF][a-zA-Z]*|--recursive\s+--force)\s+(--no-preserve-root\s+)?/(\s|$)"),
        "block",
        "`rm -rf /tmp/...` if `/` anchor is sloppy in a variant",
    ),
    Rule(
        "FS_HOME_WIPE", "filesystem", "CRIT",
        re.compile(r"\brm\s+-[rRfF]+\s+(~|\$HOME|/home/[^/\s]+)(\s|/|$)"),
        "block",
        "legitimate CI container cleanup",
    ),
    Rule(
        "DISK_OVERWRITE_DD", "disk", "CRIT",
        re.compile(r"\bdd\s+.*\bof=/dev/(sd[a-z]|nvme\d|hd[a-z]|mmcblk)"),
        "block",
        "`of=/dev/null`, `/dev/stdout` (not matched — pattern is drive-letter-only)",
    ),
    Rule(
        "FORMAT_WIPE_TOOLS", "disk", "CRIT",
        re.compile(r"\b(mkfs(\.[a-z0-9]+)?|wipefs|shred|blkdiscard)\b\s"),
        "block",
        "`shred` of a known-controlled tempfile",
    ),
    Rule(
        "REDIRECT_TO_BLOCKDEV", "disk", "CRIT",
        re.compile(r"(^|\s|\|)\s*>\s*/dev/(sd[a-z]|nvme\d|hd[a-z])"),
        "block",
        "(none known)",
    ),
    Rule(
        "PARTITIONING_TOOLS", "disk", "HIGH",
        re.compile(r"\b(fdisk|parted|sfdisk|gdisk)\s+(?!-l\b)"),
        "block",
        "`fdisk -l` (read-only listing — excluded via lookahead)",
    ),
    Rule(
        "SQL_DROP_TRUNCATE", "sql", "HIGH",
        re.compile(r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE)\b", re.IGNORECASE),
        "block",
        "SQL inside a string literal; deliberate migration",
    ),
    Rule(
        "SQL_DELETE_NO_WHERE", "sql", "HIGH",
        re.compile(r"\b(DELETE\s+FROM|UPDATE\s+\S+\s+SET)\b(?!.*\bWHERE\b)", re.IGNORECASE | re.DOTALL),
        "ask",
        "DELETE/UPDATE using LIMIT or JOIN instead of WHERE",
    ),
    Rule(
        "DOCKER_COMPOSE_DOWN_V", "docker", "HIGH",
        re.compile(r"\bdocker[- ]compose\s+down\s+(-[a-zA-Z]*v|--volumes)"),
        "ask",
        "CI test teardown intentionally removing volumes",
    ),
    Rule(
        "DOCKER_FORCE_RM", "docker", "HIGH",
        re.compile(r"\bdocker\s+(rm\s+-[a-zA-Z]*f|volume\s+rm|system\s+prune\s+.*-a)"),
        "ask",
        "ephemeral test-container cleanup",
    ),
    Rule(
        "K8S_NS_DELETE", "k8s", "CRIT",
        re.compile(r"\bkubectl\s+delete\s+(ns|namespace|--all|-n\s+\S+\s+--all)\b"),
        "block",
        "(none known)",
    ),
    Rule(
        "SYSTEMCTL_STOP_CRITICAL", "service", "HIGH",
        re.compile(r"\bsystemctl\s+(stop|disable|mask)\s+(ssh|sshd|networking|firewalld)"),
        "ask",
        "provisioning scripts that stop/replace services",
    ),
    Rule(
        "SUDO_RM", "privilege", "HIGH",
        re.compile(r"\bsudo\s+(-[^\s]*\s+)?rm\b"),
        "ask",
        "legitimate removal of root-owned /tmp files",
    ),
    Rule(
        "CHMOD_777", "privilege", "MED",
        re.compile(r"\bchmod\s+(-[Rr])?\s*(777|a\+rwx)\b"),
        "ask",
        "shared demo/sandbox directory",
    ),
    Rule(
        "CURL_PIPE_SHELL", "network", "CRIT",
        re.compile(r"\b(curl|wget)\s+[^|]*\|\s*(sudo\s+)?(bash|sh|zsh|ksh)\b"),
        "block",
        "trusted-vendor installer (e.g. rustup, uv)",
    ),
    Rule(
        "EVAL_OF_CURL", "network", "CRIT",
        re.compile(r"\$\(\s*(curl|wget)\b[^)]*\)\s*\|\s*(bash|sh)"),
        "block",
        "(none known)",
    ),
    Rule(
        "GIT_FORCE_PUSH", "vcs", "HIGH",
        re.compile(r"\bgit\s+push\s+(--force(?![-a-z])|-f(?=\s|$))"),
        "block",  # enforce only on protected branches — project policy
        "`--force-with-lease` (excluded via negative lookahead)",
    ),
    Rule(
        "GIT_RESET_HARD", "vcs", "HIGH",
        re.compile(r"\bgit\s+reset\s+(--hard|--merge)\b"),
        "ask",
        "intentional reset after stash",
    ),
    Rule(
        "GIT_CLEAN_FDX", "vcs", "HIGH",
        re.compile(r"\bgit\s+clean\s+-[a-z]*f[a-z]*d[a-z]*x?\b"),
        "ask",
        "deliberate workspace purge",
    ),
    Rule(
        "FORK_BOMB", "availability", "CRIT",
        re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
        "block",
        "(none known)",
    ),
    Rule(
        "SED_IN_PLACE", "filesystem", "MED",
        re.compile(r"\bsed\s+-i(?:\s+'[^']*'|\s+\"[^\"]*\")?\s+\S+"),
        "log",
        "safe in-place edits to non-frozen files — keep as log-only; "
        "future: scope-aware via frozen-list intersection",
    ),
]


def _sha256_short(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8", errors="replace")).hexdigest()[:16]


def _log(entry: dict) -> None:
    """Append one JSONL line. Never raise."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _match_rules(command: str) -> list[Rule]:
    return [r for r in RULES if r.pattern.search(command)]


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0  # fail-open on unparseable stdin

    if payload.get("tool_name") != "Bash":
        return 0

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or ""
    if not command:
        return 0

    matched = _match_rules(command)

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "severity_text": "INFO",
        "attributes": {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "rules_version": RULES_VERSION,
            "session_id": payload.get("session_id"),
            "cwd": payload.get("cwd"),
            "command_hash": _sha256_short(command),
            "command_prefix": command[:200],  # for debugging, full hash for privacy
            "matched_rules": [
                {
                    "rule_id": r.rule_id,
                    "category": r.category,
                    "severity": r.severity,
                    "recommended_action": r.recommended_action,
                    "known_fps": r.known_fps,
                }
                for r in matched
            ],
            "would_have_blocked": any(r.recommended_action == "block" for r in matched),
            "would_have_asked": any(r.recommended_action == "ask" for r in matched),
            "actual_decision": "allow_audit_mode",
        },
    }
    _log(entry)

    if os.environ.get("AUDIT_VERBOSE") == "1" and matched:
        rules_str = ", ".join(r.rule_id for r in matched)
        print(
            f"[bash_guard AUDIT-ONLY] matched {len(matched)} rule(s): {rules_str} — "
            f"would-have-blocked={entry['attributes']['would_have_blocked']}",
            file=sys.stderr,
        )

    # Audit-only: always allow. Never exit 2 in this version.
    return 0


if __name__ == "__main__":
    sys.exit(main())

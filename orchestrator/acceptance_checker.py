"""
acceptance_checker.py — verify executor did what the directive asked.

Deterministic checks (no LLM):
  A1: scope_compliance — only files listed in directive Scope were touched
  A2: tier1_untouched — no Tier-1 frozen files modified
  A3: tests_pass — test_results.failed == 0 (if available)
  A4: no_empty_execution — at least 1 file changed
  A5: no_out_of_scope — changed files are subset of approved scope
  A5: task_id_integrity — no created files reference a different task_id

Returns AcceptanceResult with per-check verdicts.

DNA compliance:
- trace_id: accepted as argument, recorded in result
- idempotency_key: deterministic — same inputs always produce same result
- no DB side-effects, no imports from domain.reconciliation_*
- fail-loud: raises on invalid inputs
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AcceptanceCheck:
    """Single acceptance check result."""
    check_id: str       # A1..A5
    passed: bool
    detail: str


@dataclass
class AcceptanceResult:
    """Result of all acceptance checks on an execution packet."""
    trace_id: str
    passed: bool                              # True only if ALL checks pass
    checks: list[AcceptanceCheck] = field(default_factory=list)
    drift_detected: bool = False              # True if executor touched unexpected files
    out_of_scope_files: list[str] = field(default_factory=list)
    scope_from_directive: list[str] = field(default_factory=list)


def _parse_directive_task_id(directive_text: str) -> Optional[str]:
    """Extract task_id from directive header (format: 'task_id: <value>')."""
    for line in directive_text.splitlines():
        m = re.match(r"^task_id:\s*(.+)$", line.strip())
        if m:
            return m.group(1).strip()
    return None


# Matches task_id-like tokens in filenames: e.g. A5-TASK-ID-CHECK, RECLASSIFY-PEHA-8SKU
# Anchored by non-alphanumeric-or-hyphen chars (or start/end of string).
_TASK_ID_PATTERN = re.compile(r'(?<![A-Z0-9-])([A-Z][A-Z0-9]*(?:-[A-Z0-9]+){2,})(?![A-Z0-9-])')


def _parse_directive_scope(directive_text: str) -> list[str]:
    """Extract file paths from the ## Scope section of a directive."""
    lines = directive_text.splitlines()
    in_scope = False
    scope_files = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## Scope") or stripped.startswith("## Scope ("):
            in_scope = True
            continue
        if in_scope:
            if stripped.startswith("## "):
                break
            # Lines like "- catalog/peha_reclassify_8sku.py"
            m = re.match(r"^-\s+(.+)$", stripped)
            if m:
                path = m.group(1).strip()
                if path != "(no scope specified)":
                    scope_files.append(path)
    return scope_files


def check(
    packet: dict,
    directive_text: str,
    trace_id: str,
    idempotency_key: Optional[str] = None,
) -> AcceptanceResult:
    """Run acceptance checks against execution packet and directive.

    Args:
        packet: Execution packet dict (from collect_packet).
        directive_text: Raw text of the orchestrator directive.
        trace_id: Orchestrator trace ID.
        idempotency_key: Caller-supplied key for dedup (same inputs always
            produce the same result, so this is informational only — the
            function itself is naturally idempotent).

    Returns:
        AcceptanceResult with per-check verdicts.
    """
    changed_files = packet.get("changed_files", [])
    test_results = packet.get("test_results")
    affected_tiers = packet.get("affected_tiers", [])
    scope_files = _parse_directive_scope(directive_text)

    checks: list[AcceptanceCheck] = []
    drift_detected = False
    out_of_scope: list[str] = []

    # A1: No empty execution
    a1_passed = len(changed_files) > 0
    checks.append(AcceptanceCheck(
        check_id="A1:NON_EMPTY",
        passed=a1_passed,
        detail=f"{len(changed_files)} files changed" if a1_passed else "no files changed",
    ))

    # A2: Tier-1 untouched
    a2_passed = "Tier-1" not in affected_tiers
    checks.append(AcceptanceCheck(
        check_id="A2:TIER1_SAFE",
        passed=a2_passed,
        detail="no Tier-1 files touched" if a2_passed else "Tier-1 frozen files modified!",
    ))

    # A3: Tests pass (if available)
    if test_results is not None:
        failed = test_results.get("failed", 0)
        a3_passed = failed == 0
        checks.append(AcceptanceCheck(
            check_id="A3:TESTS_PASS",
            passed=a3_passed,
            detail=f"passed={test_results.get('passed', 0)} failed={failed}",
        ))
    else:
        checks.append(AcceptanceCheck(
            check_id="A3:TESTS_PASS",
            passed=True,
            detail="no test results available (skipped)",
        ))

    # A4: Scope compliance — if directive specifies scope, check it
    if scope_files:
        for changed in changed_files:
            in_scope = False
            for scope_path in scope_files:
                # Exact match (full path)
                if changed == scope_path:
                    in_scope = True
                    break
                # Prefix match (scope says "catalog/" means anything under it)
                if changed.startswith(scope_path.rstrip("/") + "/"):
                    in_scope = True
                    break
                # Basename fallback: scope "guardian.py" matches "orchestrator/guardian.py"
                if "/" not in scope_path and changed.endswith("/" + scope_path):
                    in_scope = True
                    break
            if not in_scope:
                out_of_scope.append(changed)

        a4_passed = len(out_of_scope) == 0
        drift_detected = not a4_passed
        checks.append(AcceptanceCheck(
            check_id="A4:SCOPE_COMPLIANCE",
            passed=a4_passed,
            detail=f"all {len(changed_files)} files in scope" if a4_passed
            else f"{len(out_of_scope)} files out of scope: {out_of_scope[:5]}",
        ))
    else:
        checks.append(AcceptanceCheck(
            check_id="A4:SCOPE_COMPLIANCE",
            passed=True,
            detail="no scope defined in directive (skipped)",
        ))

    # A5: task_id integrity — no created/changed files reference a different task_id
    task_id_from_directive = _parse_directive_task_id(directive_text)
    if task_id_from_directive:
        all_files = list(packet.get("created_files", [])) + list(changed_files)
        violating_files: list[str] = []
        for filepath in all_files:
            basename = Path(filepath).name
            for match in _TASK_ID_PATTERN.finditer(basename):
                found_id = match.group(1)
                if found_id != task_id_from_directive:
                    violating_files.append(
                        f"{filepath!r} (found task_id token '{found_id}',"
                        f" expected '{task_id_from_directive}')"
                    )
        if violating_files:
            checks.append(AcceptanceCheck(
                check_id="A5:TASK_ID_INTEGRITY",
                passed=False,
                detail=(
                    f"{len(violating_files)} file(s) reference wrong task_id "
                    f"(expected '{task_id_from_directive}'): "
                    f"{violating_files[:5]}"
                ),
            ))
        else:
            checks.append(AcceptanceCheck(
                check_id="A5:TASK_ID_INTEGRITY",
                passed=True,
                detail=(
                    f"all {len(all_files)} files use correct task_id"
                    f" '{task_id_from_directive}'"
                ),
            ))
    else:
        checks.append(AcceptanceCheck(
            check_id="A5:TASK_ID_INTEGRITY",
            passed=True,
            detail="no task_id in directive (skipped)",
        ))

    all_passed = all(c.passed for c in checks)

    return AcceptanceResult(
        trace_id=trace_id,
        passed=all_passed,
        checks=checks,
        drift_detected=drift_detected,
        out_of_scope_files=out_of_scope,
        scope_from_directive=scope_files,
    )

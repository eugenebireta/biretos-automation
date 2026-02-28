from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


_WHITELIST_REL = {
    "domain/observability_service.py",
    "domain/reconciliation_service.py",
    "domain/reconciliation_verify.py",
    "domain/structural_checks.py",
    "domain/reconciliation_alerts.py",
    # Repo has this file under side_effects/, but keep both spellings to avoid path drift.
    "side_effects/telegram_command_worker.py",
    "telegram_command_worker.py",
}


_CACHE_FIELDS = ("payment_status", "cdek_uuid", "invoice_request_key")
_SNAPSHOT_DECISION_FIELDS = ("quantity_available", "quantity_reserved", "quantity_on_hand")


@dataclass(frozen=True)
class _Violation:
    path: str
    kind: str
    needle: str
    snippet: str


_TRIPLE_QUOTED_RE = re.compile(r"(?s)(\"\"\"|''')(.*?)(\1)")


def _iter_python_files(base: Path) -> Iterable[Path]:
    for folder in ("side_effects", "ru_worker", "domain"):
        root = base / folder
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            yield p


def _rel_posix(base: Path, p: Path) -> str:
    return p.relative_to(base).as_posix()


def _is_whitelisted(rel: str) -> bool:
    if rel in _WHITELIST_REL:
        return True
    if "/tests/" in f"/{rel}/" or rel.startswith("tests/"):
        return True
    return False


def _extract_triple_quoted_blocks(text: str) -> List[str]:
    return [m.group(2) for m in _TRIPLE_QUOTED_RE.finditer(text)]


def _find_sql_cache_where_violations(sql: str, *, field: str) -> List[str]:
    """
    Flags 'decision-like' predicates on cache fields in WHERE clause.

    Heuristics (to avoid false positives):
    - Only inside triple-quoted blocks (caller enforces).
    - Field must appear as identifier, not as a quoted JSON key (e.g., ->>'cdek_uuid').
    - Predicate must look semantic: IS NULL / IN (...) / string literal present.
      This intentionally does not flag key lookups like `WHERE cdek_uuid = %s`.
    """
    lower = sql.lower()
    if "where" not in lower or field not in lower:
        return []

    # Work only on the WHERE clause tail to reduce accidental matches.
    where_idx = lower.find("where")
    tail = lower[where_idx:]

    # Fast skip: if field never appears after WHERE, nothing to do.
    if field not in tail:
        return []

    # If field appears only as a quoted token (e.g., ->>'cdek_uuid'), do not flag.
    hits: List[int] = [m.start() for m in re.finditer(rf"\b{re.escape(field)}\b", tail)]
    if not hits:
        return []
    meaningful_hit = False
    for h in hits:
        before = tail[h - 1] if h > 0 else ""
        after = tail[h + len(field)] if (h + len(field)) < len(tail) else ""
        if before == "'" or after == "'":
            continue
        meaningful_hit = True
        break
    if not meaningful_hit:
        return []

    # Decision-like predicate patterns.
    decision_markers = (" is null", " is not null", " in (", " in\\n(", "'")
    if not any(marker in tail for marker in decision_markers):
        return []

    # Provide a short snippet from the WHERE clause for error message.
    snippet = tail.strip().replace("\n", " ")
    snippet = re.sub(r"\s+", " ", snippet)
    return [snippet[:240]]


def _find_sql_snapshot_decision_violations(sql: str) -> List[str]:
    lower = sql.lower()
    if "from availability_snapshot" not in lower:
        return []
    if "where" not in lower:
        return []
    where_idx = lower.find("where")
    tail = lower[where_idx:]

    # Decision on snapshot values (not key lookups).
    for f in _SNAPSHOT_DECISION_FIELDS:
        if re.search(rf"\b{re.escape(f)}\b", tail):
            snippet = tail.strip().replace("\n", " ")
            snippet = re.sub(r"\s+", " ", snippet)
            return [snippet[:240]]
    return []


def _find_py_control_flow_violations(text: str) -> List[Tuple[str, str]]:
    """
    Flags control-flow decisions on cache fields.

    Heuristic to avoid false positives on unrelated variables:
    - Require key-like usage in the same line: \"payment_status\" / ['payment_status'] / .get('payment_status')
    """
    violations: List[Tuple[str, str]] = []
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        if "if" not in line:
            continue
        lowered = line.lower()
        if not re.search(r"\bif\b", lowered):
            continue
        for field in _CACHE_FIELDS:
            if field not in lowered:
                continue
            key_like = (
                f"'{field}'" in lowered
                or f"\"{field}\"" in lowered
                or f"get('{field}')" in lowered
                or f'get(\"{field}\")' in lowered
                or f"[\"{field}\"]" in lowered
                or f"['{field}']" in lowered
            )
            if key_like:
                violations.append((f"line:{i}", line.strip()[:240]))
    return violations


def _scan_file_for_violations(base: Path, p: Path) -> List[_Violation]:
    rel = _rel_posix(base, p)
    if _is_whitelisted(rel):
        return []
    text = p.read_text(encoding="utf-8", errors="replace")
    violations: List[_Violation] = []

    # SQL checks: only inside triple-quoted blocks.
    for block in _extract_triple_quoted_blocks(text):
        for field in _CACHE_FIELDS:
            for snippet in _find_sql_cache_where_violations(block, field=field):
                violations.append(_Violation(rel, "sql_where_cache_field", field, snippet))
        for snippet in _find_sql_snapshot_decision_violations(block):
            violations.append(_Violation(rel, "sql_where_snapshot_value", "availability_snapshot", snippet))

    # Python control flow checks.
    for loc, snippet in _find_py_control_flow_violations(text):
        violations.append(_Violation(rel, "py_if_cache_field", "if", f"{loc}: {snippet}"))

    return violations


def test_cache_read_model_only_contract():
    base = _project_root()
    all_violations: List[_Violation] = []
    for p in _iter_python_files(base):
        all_violations.extend(_scan_file_for_violations(base, p))

    if all_violations:
        lines = ["CACHE-READ-MODEL-ONLY contract violations detected:"]
        for v in all_violations[:20]:
            lines.append(f"- {v.path} :: {v.kind} :: {v.needle} :: {v.snippet}")
        if len(all_violations) > 20:
            lines.append(f"... and {len(all_violations) - 20} more")
        raise AssertionError("\n".join(lines))


def test_detector_catches_synthetic_violation_strings():
    # Synthetic SQL predicate on cache field.
    fake = """
    cursor.execute(
        \"\"\"
        SELECT order_id FROM order_ledger
        WHERE payment_status = 'paid'
        LIMIT 1
        \"\"\"
    )
    if row.get('payment_status') == 'paid':
        pass
    """
    blocks = _extract_triple_quoted_blocks(fake)
    assert blocks, "expected to extract triple-quoted blocks"
    sql_hits = _find_sql_cache_where_violations(blocks[0], field="payment_status")
    assert sql_hits, "expected SQL detector to catch synthetic payment_status WHERE predicate"

    py_hits = _find_py_control_flow_violations(fake)
    assert py_hits, "expected Python control-flow detector to catch synthetic if on payment_status key"


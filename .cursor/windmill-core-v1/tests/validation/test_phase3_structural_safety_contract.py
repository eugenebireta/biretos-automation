from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class _Hit:
    pattern_name: str
    line_no: int
    line: str


def _iter_matches(text: str, pattern: re.Pattern[str]) -> Iterable[Tuple[int, str]]:
    for m in pattern.finditer(text):
        start = m.start()
        line_no = text.count("\n", 0, start) + 1
        line = text.splitlines()[line_no - 1] if text.splitlines() else ""
        yield line_no, line


def _scan_forbidden_patterns(*, path: Path, patterns: List[Tuple[str, re.Pattern[str]]]) -> List[_Hit]:
    text = path.read_text(encoding="utf-8", errors="replace")
    hits: List[_Hit] = []
    for name, pat in patterns:
        for line_no, line in _iter_matches(text, pat):
            hits.append(_Hit(name, line_no, line.strip()))
    return hits


def _assert_no_hits(path: Path, hits: List[_Hit]) -> None:
    if not hits:
        return
    lines = [f"Structural safety contract violation in {path.as_posix()}:"]
    for h in hits[:20]:
        lines.append(f"- {h.pattern_name} at line {h.line_no}: {h.line}")
    if len(hits) > 20:
        lines.append(f"... and {len(hits) - 20} more")
    raise AssertionError("\n".join(lines))


def _assert_stock_ledger_inserts_are_release_only(path: Path) -> None:
    """
    Reconciliation may append to stock_ledger_entries only as release (RC-4/expiry),
    and must use idempotent ON CONFLICT (idempotency_key) DO NOTHING.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    needle = "INSERT INTO stock_ledger_entries"
    idx = 0
    while True:
        pos = text.find(needle, idx)
        if pos < 0:
            break
        window = text[pos : pos + 1200]
        if "'release'" not in window and "\"release\"" not in window:
            line_no = text.count("\n", 0, pos) + 1
            raise AssertionError(
                f"Forbidden stock_ledger_entries INSERT (non-release) in {path.as_posix()} at line {line_no}"
            )
        if "ON CONFLICT (idempotency_key) DO NOTHING" not in window:
            line_no = text.count("\n", 0, pos) + 1
            raise AssertionError(
                f"stock_ledger_entries INSERT must be idempotent (missing ON CONFLICT) in {path.as_posix()} at line {line_no}"
            )
        idx = pos + len(needle)


def test_structural_safety_contract_static_scan():
    base = _project_root()
    reconciliation_service = base / "domain" / "reconciliation_service.py"
    reconciliation_alerts = base / "domain" / "reconciliation_alerts.py"
    structural_checks = base / "domain" / "structural_checks.py"

    assert reconciliation_service.exists(), "expected reconciliation_service.py"
    assert reconciliation_alerts.exists(), "expected reconciliation_alerts.py"
    assert structural_checks.exists(), "expected structural_checks.py"

    # 1) Forbidden destructive operations in truth ledgers (all three files).
    forbidden_truth_ops = [
        ("insert_stock_ledger_entries", re.compile(r"\bINSERT\s+INTO\s+stock_ledger_entries\b", re.IGNORECASE)),
        ("insert_payment_transactions", re.compile(r"\bINSERT\s+INTO\s+payment_transactions\b", re.IGNORECASE)),
        ("insert_shipments", re.compile(r"\bINSERT\s+INTO\s+shipments\b", re.IGNORECASE)),
        ("insert_documents", re.compile(r"\bINSERT\s+INTO\s+documents\b", re.IGNORECASE)),
        ("delete_stock_ledger_entries", re.compile(r"\bDELETE\s+FROM\s+stock_ledger_entries\b", re.IGNORECASE)),
        ("delete_payment_transactions", re.compile(r"\bDELETE\s+FROM\s+payment_transactions\b", re.IGNORECASE)),
        ("delete_shipments", re.compile(r"\bDELETE\s+FROM\s+shipments\b", re.IGNORECASE)),
        ("delete_documents", re.compile(r"\bDELETE\s+FROM\s+documents\b", re.IGNORECASE)),
    ]

    # structural_checks.py must be strictly read-only.
    ro_hits = _scan_forbidden_patterns(
        path=structural_checks,
        patterns=[
            ("insert_any", re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE)),
            ("update_any", re.compile(r"\bUPDATE\b", re.IGNORECASE)),
            ("delete_any", re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE)),
        ],
    )
    _assert_no_hits(structural_checks, ro_hits)

    # reconciliation_alerts.py is allowed to write only to reconciliation_alerts.
    alerts_hits = _scan_forbidden_patterns(path=reconciliation_alerts, patterns=forbidden_truth_ops)
    _assert_no_hits(reconciliation_alerts, alerts_hits)

    # Also ensure it doesn't touch business tables by UPDATE/DELETE other than reconciliation_alerts.
    alerts_text = reconciliation_alerts.read_text(encoding="utf-8", errors="replace").lower()
    if "update " in alerts_text and "update reconciliation_alerts" not in alerts_text:
        raise AssertionError("reconciliation_alerts.py must not UPDATE non-reconciliation_alerts tables")
    if "delete from" in alerts_text:
        raise AssertionError("reconciliation_alerts.py must not DELETE from any table")

    # reconciliation_service.py: forbid INSERT into payment_transactions/shipments/documents and any DELETE on truth tables.
    svc_hits = _scan_forbidden_patterns(
        path=reconciliation_service,
        patterns=[
            ("insert_payment_transactions", re.compile(r"\bINSERT\s+INTO\s+payment_transactions\b", re.IGNORECASE)),
            ("insert_shipments", re.compile(r"\bINSERT\s+INTO\s+shipments\b", re.IGNORECASE)),
            ("insert_documents", re.compile(r"\bINSERT\s+INTO\s+documents\b", re.IGNORECASE)),
            ("delete_stock_ledger_entries", re.compile(r"\bDELETE\s+FROM\s+stock_ledger_entries\b", re.IGNORECASE)),
            ("delete_payment_transactions", re.compile(r"\bDELETE\s+FROM\s+payment_transactions\b", re.IGNORECASE)),
            ("delete_shipments", re.compile(r"\bDELETE\s+FROM\s+shipments\b", re.IGNORECASE)),
            ("delete_documents", re.compile(r"\bDELETE\s+FROM\s+documents\b", re.IGNORECASE)),
        ],
    )
    _assert_no_hits(reconciliation_service, svc_hits)

    # Special-case: stock_ledger_entries INSERTs are allowed only for release and must be idempotent.
    _assert_stock_ledger_inserts_are_release_only(reconciliation_service)

    # 2) FSM bypass: reconciliation must not update order_ledger.state or order_ledger.status.
    fsm_bypass_hits = _scan_forbidden_patterns(
        path=reconciliation_service,
        patterns=[
            (
                "update_order_ledger_state",
                re.compile(r"\bUPDATE\s+order_ledger\b[\s\S]{0,300}\bSET\b[\s\S]{0,300}\bstate\b\s*=",
                           re.IGNORECASE),
            ),
            (
                "update_order_ledger_status",
                re.compile(r"\bUPDATE\s+order_ledger\b[\s\S]{0,300}\bSET\b[\s\S]{0,300}\bstatus\b\s*=",
                           re.IGNORECASE),
            ),
        ],
    )
    _assert_no_hits(reconciliation_service, fsm_bypass_hits)

    # 3) Governance bypass: reconciliation must not self-approve or mark executing directly.
    governance_bypass_hits = _scan_forbidden_patterns(
        path=reconciliation_service,
        patterns=[
            (
                "approve_review_case",
                re.compile(
                    r"\bUPDATE\s+review_cases\b[\s\S]{0,300}\bSET\b[\s\S]{0,300}\bstatus\b\s*=\s*'approved'",
                    re.IGNORECASE,
                ),
            ),
            (
                "execute_review_case",
                re.compile(
                    r"\bUPDATE\s+review_cases\b[\s\S]{0,300}\bSET\b[\s\S]{0,300}\bstatus\b\s*=\s*'executing'",
                    re.IGNORECASE,
                ),
            ),
        ],
    )
    _assert_no_hits(reconciliation_service, governance_bypass_hits)


def test_structural_safety_detector_catches_synthetic_forbidden_insert():
    # Synthetic self-check: ensure forbidden INSERT into payment_transactions is detected.
    fake = """
    cursor.execute(
        \"\"\"
        INSERT INTO payment_transactions (id) VALUES ('x')
        \"\"\"
    )
    """
    pat = re.compile(r"\bINSERT\s+INTO\s+payment_transactions\b", re.IGNORECASE)
    hits = list(_iter_matches(fake, pat))
    assert hits, "synthetic forbidden INSERT must be detected"


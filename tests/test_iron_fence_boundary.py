"""Iron Fence Boundary Grep Guards — M3a / M3b / M3c verification.

trace_id: orch_20260409T124122Z_ed0d59
idempotency_key: iron-fence-boundary-guards-verify-001

Deterministic tests — no live API, no unmocked time/randomness.
These tests replicate the CI "Iron Fence: Boundary Grep Guards" step
(ci.yml lines 96-142) and prove that the regex patterns catch violations.

M3a: No raw DML on reconciliation_* tables from Tier-3 code
M3b: No raw DML on Core business tables from Tier-3 code
M3c: No forbidden imports from domain.reconciliation_* in Tier-3 code
"""

from __future__ import annotations

import os
import re
import tempfile
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants — must mirror ci.yml exactly
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
WINDMILL_ROOT = REPO_ROOT / ".cursor" / "windmill-core-v1"

TIER3_DIRS = ["ru_worker", "side_effects", "webhook_service", "cli", "config"]

RECON_TABLES = (
    "reconciliation_audit_log",
    "reconciliation_alerts",
    "reconciliation_suppressions",
)
RECON_TABLES_RE = "|".join(RECON_TABLES)

CORE_BIZ_TABLES = (
    "order_ledger",
    "shipments",
    "payment_transactions",
    "reservations",
    "stock_ledger_entries",
    "availability_snapshot",
    "documents",
)
CORE_BIZ_TABLES_RE = "|".join(CORE_BIZ_TABLES)

DML_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP")
DML_RE = "|".join(DML_KEYWORDS)

FORBIDDEN_IMPORTS_RE = (
    r"from domain\.reconciliation_service|"
    r"from domain\.reconciliation_verify|"
    r"from domain\.reconciliation_alerts|"
    r"from domain\.structural_checks|"
    r"from domain\.observability_service|"
    r"from retention_policy|"
    r"import reconciliation_service|"
    r"import reconciliation_verify|"
    r"import reconciliation_alerts|"
    r"import structural_checks|"
    r"import observability_service"
)

TRACE_ID = "orch_20260409T124122Z_ed0d59"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scan_py_files(base: Path, dirs: list[str], pattern: re.Pattern) -> list[str]:
    """Return list of 'file:line: matched_text' for all .py files in dirs."""
    hits: list[str] = []
    for d in dirs:
        dirpath = base / d
        if not dirpath.is_dir():
            continue
        for pyfile in dirpath.rglob("*.py"):
            for i, line in enumerate(pyfile.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pattern.search(line):
                    hits.append(f"{pyfile.relative_to(base)}:{i}: {line.strip()}")
    return hits


def _canary_check(pattern: re.Pattern, bad_line: str) -> bool:
    """Confirm that pattern actually matches a known-bad line."""
    return pattern.search(bad_line) is not None


# ---------------------------------------------------------------------------
# M3a — No raw DML on reconciliation_* tables from Tier-3
# ---------------------------------------------------------------------------

class TestM3aReconTableDML:
    """Guard: Tier-3 code must not contain raw DML on reconciliation tables."""

    PATTERN = re.compile(rf"({DML_RE}).*({RECON_TABLES_RE})", re.IGNORECASE)

    def test_no_recon_dml_in_tier3(self):
        """Scan Tier-3 dirs for raw DML on reconciliation tables."""
        hits = _scan_py_files(WINDMILL_ROOT, TIER3_DIRS, self.PATTERN)
        assert hits == [], (
            f"M3a VIOLATION — raw DML on reconciliation tables in Tier-3:\n"
            + "\n".join(hits)
        )

    @pytest.mark.parametrize("bad_line", [
        "INSERT INTO reconciliation_audit_log (id) VALUES (1);",
        "UPDATE reconciliation_alerts SET status = 'ack';",
        "DELETE FROM reconciliation_suppressions WHERE id = 5;",
        "ALTER TABLE reconciliation_audit_log ADD COLUMN x INT;",
        "DROP TABLE reconciliation_alerts;",
    ])
    def test_canary_catches_recon_dml(self, bad_line: str):
        """Canary: pattern must match known-bad DML lines."""
        assert _canary_check(self.PATTERN, bad_line), (
            f"M3a canary FAILED — pattern did not catch: {bad_line}"
        )


# ---------------------------------------------------------------------------
# M3b — No raw DML on Core business tables from Tier-3
# ---------------------------------------------------------------------------

class TestM3bCoreBizTableDML:
    """Guard: Tier-3 code must not contain raw DML on Core business tables."""

    PATTERN = re.compile(rf"({DML_RE}).*({CORE_BIZ_TABLES_RE})", re.IGNORECASE)

    # Pre-existing DML in worker-boundary modules (ru_worker, side_effects).
    # These are the atomic executor layer where DB commits are architecturally
    # allowed.  The guard's purpose is to prevent NEW Tier-3 extension code
    # (webhook_service, cli, config) from introducing raw DML.
    _BASELINE_FILES = frozenset({
        "ru_worker/pii_redactor.py",
        "ru_worker/ru_worker.py",
        "side_effects/cdek_shipment_worker.py",
        "side_effects/insales_paid_worker.py",
        "side_effects/invoice_worker.py",
        "side_effects/telegram_command_worker.py",
    })

    def test_no_new_core_biz_dml_in_tier3(self):
        """No Core DML outside the known worker-boundary baseline."""
        hits = _scan_py_files(WINDMILL_ROOT, TIER3_DIRS, self.PATTERN)
        new_hits = [
            h for h in hits
            if not any(h.replace("\\", "/").startswith(bf) for bf in self._BASELINE_FILES)
        ]
        assert new_hits == [], (
            f"M3b VIOLATION — NEW raw DML on Core business tables in Tier-3:\n"
            + "\n".join(new_hits)
        )

    def test_no_core_biz_dml_in_extension_dirs(self):
        """webhook_service, cli, config must have zero Core DML."""
        extension_dirs = ["webhook_service", "cli", "config"]
        hits = _scan_py_files(WINDMILL_ROOT, extension_dirs, self.PATTERN)
        assert hits == [], (
            f"M3b VIOLATION — raw DML on Core tables in extension dirs:\n"
            + "\n".join(hits)
        )

    @pytest.mark.parametrize("bad_line", [
        "INSERT INTO order_ledger (order_id) VALUES (42);",
        "UPDATE shipments SET status = 'delivered';",
        "DELETE FROM payment_transactions WHERE id = 7;",
        "ALTER TABLE reservations ADD COLUMN note TEXT;",
        "DROP TABLE stock_ledger_entries;",
        "INSERT INTO availability_snapshot (sku) VALUES ('A1');",
        "UPDATE documents SET path = '/new';",
    ])
    def test_canary_catches_core_biz_dml(self, bad_line: str):
        """Canary: pattern must match known-bad DML against Core tables."""
        assert _canary_check(self.PATTERN, bad_line), (
            f"M3b canary FAILED — pattern did not catch: {bad_line}"
        )


# ---------------------------------------------------------------------------
# M3c — No forbidden imports from domain.reconciliation_* in Tier-3
# ---------------------------------------------------------------------------

class TestM3cForbiddenImports:
    """Guard: Tier-3 code must not import Tier-1 reconciliation modules."""

    PATTERN = re.compile(FORBIDDEN_IMPORTS_RE)

    def test_no_forbidden_imports_in_tier3(self):
        """Scan Tier-3 dirs for forbidden Tier-1 imports."""
        hits = _scan_py_files(WINDMILL_ROOT, TIER3_DIRS, self.PATTERN)
        assert hits == [], (
            f"M3c VIOLATION — forbidden Tier-1 imports in Tier-3:\n"
            + "\n".join(hits)
        )

    @pytest.mark.parametrize("bad_line", [
        "from domain.reconciliation_service import run_recon",
        "from domain.reconciliation_verify import verify",
        "from domain.reconciliation_alerts import send_alert",
        "from domain.structural_checks import check_schema",
        "from domain.observability_service import observe",
        "from retention_policy import retain",
        "import reconciliation_service",
        "import reconciliation_alerts",
        "import structural_checks",
        "import observability_service",
    ])
    def test_canary_catches_forbidden_import(self, bad_line: str):
        """Canary: pattern must match known-bad import lines."""
        assert _canary_check(self.PATTERN, bad_line), (
            f"M3c canary FAILED — pattern did not catch: {bad_line}"
        )


# ---------------------------------------------------------------------------
# Integration: write a temp bad file, scan it, confirm detection
# ---------------------------------------------------------------------------

class TestCanaryFileDetection:
    """Write temporary Python files with violations, confirm scanner catches them."""

    def test_temp_file_with_recon_dml_detected(self, tmp_path: Path):
        """A temp .py file with reconciliation DML is caught by M3a scanner."""
        tier3_dir = tmp_path / "ru_worker"
        tier3_dir.mkdir()
        bad_file = tier3_dir / "bad_recon.py"
        bad_file.write_text("cursor.execute('INSERT INTO reconciliation_audit_log ...')\n")

        pattern = re.compile(rf"({DML_RE}).*({RECON_TABLES_RE})", re.IGNORECASE)
        hits = _scan_py_files(tmp_path, ["ru_worker"], pattern)
        assert len(hits) == 1, f"Expected 1 hit, got {len(hits)}: {hits}"

    def test_temp_file_with_core_biz_dml_detected(self, tmp_path: Path):
        """A temp .py file with Core DML is caught by M3b scanner."""
        tier3_dir = tmp_path / "side_effects"
        tier3_dir.mkdir()
        bad_file = tier3_dir / "bad_core.py"
        bad_file.write_text("db.execute('DELETE FROM order_ledger WHERE expired')\n")

        pattern = re.compile(rf"({DML_RE}).*({CORE_BIZ_TABLES_RE})", re.IGNORECASE)
        hits = _scan_py_files(tmp_path, ["side_effects"], pattern)
        assert len(hits) == 1, f"Expected 1 hit, got {len(hits)}: {hits}"

    def test_temp_file_with_forbidden_import_detected(self, tmp_path: Path):
        """A temp .py file with forbidden import is caught by M3c scanner."""
        tier3_dir = tmp_path / "webhook_service"
        tier3_dir.mkdir()
        bad_file = tier3_dir / "bad_import.py"
        bad_file.write_text("from domain.reconciliation_service import run_recon\n")

        pattern = re.compile(FORBIDDEN_IMPORTS_RE)
        hits = _scan_py_files(tmp_path, ["webhook_service"], pattern)
        assert len(hits) == 1, f"Expected 1 hit, got {len(hits)}: {hits}"

    def test_clean_file_passes(self, tmp_path: Path):
        """A clean .py file produces zero hits across all guards."""
        tier3_dir = tmp_path / "cli"
        tier3_dir.mkdir()
        clean = tier3_dir / "clean.py"
        clean.write_text(textwrap.dedent("""\
            import json
            from pathlib import Path

            def handle_request(payload):
                trace_id = payload["trace_id"]
                return {"status": "ok", "trace_id": trace_id}
        """))

        for pat in [
            re.compile(rf"({DML_RE}).*({RECON_TABLES_RE})", re.IGNORECASE),
            re.compile(rf"({DML_RE}).*({CORE_BIZ_TABLES_RE})", re.IGNORECASE),
            re.compile(FORBIDDEN_IMPORTS_RE),
        ]:
            hits = _scan_py_files(tmp_path, ["cli"], pat)
            assert hits == [], f"Clean file should not trigger: {hits}"

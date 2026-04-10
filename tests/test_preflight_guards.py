"""Sentinel tests for preflight guards — batch #2.

Each guard must catch known-bad inputs and pass known-good inputs.
These tests prove that guards are LIVE, not decorative.

Deterministic — no live API, no unmocked time/randomness.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

from core_gate_bridge import (  # noqa: E402
    _STUB_VALUE,
    _check_forbidden_dml,
    _check_forbidden_imports,
    _check_pinned_api,
    _extract_signature,
    run_preflight_guards,
)


# =============================================================================
# Sentinel: no stubs remain
# =============================================================================

class TestNoStubsRemain:
    """All guards must be implemented — no _STUB_VALUE in results."""

    def test_no_stubs_in_results(self):
        result = run_preflight_guards(changed_files=[], trace_id="sentinel-001")
        for guard, status in result["results"].items():
            assert status != _STUB_VALUE, (
                f"Guard '{guard}' still returns stub — not implemented"
            )

    def test_all_four_guards_present(self):
        result = run_preflight_guards(changed_files=[], trace_id="sentinel-002")
        expected = {"frozen_files", "forbidden_imports", "forbidden_dml", "pinned_api"}
        assert set(result["results"].keys()) == expected


# =============================================================================
# Sentinel: forbidden_imports
# =============================================================================

class TestForbiddenImports:
    """Guard must catch imports from domain.reconciliation_* and friends."""

    def test_catches_recon_import(self, tmp_path):
        bad_file = tmp_path / "evil.py"
        bad_file.write_text(
            "from domain.reconciliation_service import verify\n",
            encoding="utf-8",
        )
        status, violations = _check_forbidden_imports([str(bad_file)])
        assert status == "fail"
        assert len(violations) == 1

    def test_catches_observability_import(self, tmp_path):
        bad_file = tmp_path / "evil2.py"
        bad_file.write_text(
            "from domain.observability_service import check_health\n",
            encoding="utf-8",
        )
        status, violations = _check_forbidden_imports([str(bad_file)])
        assert status == "fail"

    def test_passes_clean_file(self, tmp_path):
        good_file = tmp_path / "clean.py"
        good_file.write_text(
            "from pathlib import Path\nimport json\n",
            encoding="utf-8",
        )
        status, violations = _check_forbidden_imports([str(good_file)])
        assert status == "pass"
        assert violations == []

    def test_ignores_non_python(self, tmp_path):
        md_file = tmp_path / "readme.md"
        md_file.write_text(
            "from domain.reconciliation_service import verify\n",
            encoding="utf-8",
        )
        status, violations = _check_forbidden_imports([str(md_file)])
        assert status == "pass"


# =============================================================================
# Sentinel: forbidden_dml
# =============================================================================

class TestForbiddenDml:
    """Guard must catch DML on reconciliation and Core business tables."""

    def test_catches_insert_recon(self, tmp_path):
        bad_file = tmp_path / "evil.py"
        bad_file.write_text(
            'db.execute("INSERT INTO reconciliation_audit_log (id) VALUES (1)")\n',
            encoding="utf-8",
        )
        status, violations = _check_forbidden_dml([str(bad_file)])
        assert status == "fail"

    def test_catches_update_core_table(self, tmp_path):
        bad_file = tmp_path / "evil2.py"
        bad_file.write_text(
            'cursor.execute("UPDATE order_ledger SET status = \'paid\'")\n',
            encoding="utf-8",
        )
        status, violations = _check_forbidden_dml([str(bad_file)])
        assert status == "fail"

    def test_catches_drop_recon(self, tmp_path):
        bad_file = tmp_path / "evil3.py"
        bad_file.write_text(
            'DROP TABLE reconciliation_alerts;\n',
            encoding="utf-8",
        )
        status, violations = _check_forbidden_dml([str(bad_file)])
        assert status == "fail"

    def test_passes_clean_dml(self, tmp_path):
        good_file = tmp_path / "clean.py"
        good_file.write_text(
            'db.execute("INSERT INTO rev_catalog_jobs (id) VALUES (1)")\n',
            encoding="utf-8",
        )
        status, violations = _check_forbidden_dml([str(good_file)])
        assert status == "pass"

    def test_passes_no_dml(self, tmp_path):
        good_file = tmp_path / "clean2.py"
        good_file.write_text(
            'result = db.execute("SELECT * FROM order_ledger")\n',
            encoding="utf-8",
        )
        status, violations = _check_forbidden_dml([str(good_file)])
        assert status == "pass"


# =============================================================================
# Sentinel: pinned_api
# =============================================================================

class TestPinnedApi:
    """Guard must detect when a pinned function signature changes."""

    def test_passes_unchanged_signature(self, tmp_path):
        """A file with the correct signatures should pass."""
        source = textwrap.dedent("""\
            from typing import Dict, Any
            def _derive_payment_status(net_paid_minor: int, order_total_minor: int, has_pending_refund: bool) -> str:
                return "paid"
            def _extract_order_total_minor(order_row: Dict[str, Any]) -> int:
                return order_row.get("total", 0)
        """)
        (tmp_path / "domain").mkdir()
        (tmp_path / "domain" / "payment_service.py").write_text(source, encoding="utf-8")

        # The guard checks files matching pinned paths
        status, violations = _check_pinned_api(
            [str(tmp_path / "domain" / "payment_service.py")]
        )
        assert status == "pass", f"Expected pass, got violations: {violations}"

    def test_catches_changed_signature(self, tmp_path):
        """A file where a pinned function has different args should fail."""
        source = textwrap.dedent("""\
            from typing import Dict, Any
            def _derive_payment_status(net_paid_minor: int, order_total_minor: int, has_pending_refund: bool) -> str:
                return "paid"
            def _extract_order_total_minor(order_row: Dict[str, Any], currency: str) -> int:
                return order_row.get("total", 0)
        """)
        (tmp_path / "domain").mkdir()
        (tmp_path / "domain" / "payment_service.py").write_text(source, encoding="utf-8")

        status, violations = _check_pinned_api(
            [str(tmp_path / "domain" / "payment_service.py")]
        )
        assert status == "fail"
        assert any("signature changed" in v for v in violations)

    def test_catches_deleted_function(self, tmp_path):
        """A file where a pinned function is missing should fail."""
        source = textwrap.dedent("""\
            from typing import Dict, Any
            def _derive_payment_status(net_paid_minor: int, order_total_minor: int, has_pending_refund: bool) -> str:
                return "paid"
            def some_other_function() -> None:
                pass
        """)
        (tmp_path / "domain").mkdir()
        (tmp_path / "domain" / "payment_service.py").write_text(source, encoding="utf-8")

        status, violations = _check_pinned_api(
            [str(tmp_path / "domain" / "payment_service.py")]
        )
        assert status == "fail"
        assert any("not found" in v for v in violations)

    def test_skips_unrelated_files(self):
        """Files not matching pinned module paths should be skipped (pass)."""
        status, violations = _check_pinned_api(
            ["catalog/datasheet/schema.py", "scripts/export_pipeline.py"]
        )
        assert status == "pass"
        assert violations == []


# =============================================================================
# Sentinel: extract_signature helper
# =============================================================================

class TestExtractSignature:
    """Verify the AST signature extraction works correctly."""

    def test_function_signature(self):
        source = "def foo(a: int, b: str = 'x') -> bool:\n    return True\n"
        sig = _extract_signature(source, "foo")
        assert sig is not None
        assert "foo" in sig
        assert "int" in sig
        assert "bool" in sig

    def test_class_signature(self):
        source = textwrap.dedent("""\
            class MyRequest:
                provider_id: str
                trace_id: Optional[str]
        """)
        sig = _extract_signature(source, "MyRequest")
        assert sig is not None
        assert "MyRequest" in sig
        assert "provider_id: str" in sig

    def test_missing_name_returns_none(self):
        source = "def bar() -> None:\n    pass\n"
        assert _extract_signature(source, "foo") is None

    def test_syntax_error_returns_none(self):
        assert _extract_signature("def broken(", "broken") is None


# =============================================================================
# Integration: full preflight with all guards
# =============================================================================

class TestFullPreflight:
    """Integration: run_preflight_guards with all 4 guards active."""

    def test_clean_files_pass(self):
        result = run_preflight_guards(
            changed_files=["catalog/datasheet/schema.py"],
            trace_id="sentinel-int-001",
        )
        assert result["passed"] is True
        assert all(v == "pass" for v in result["results"].values())

    def test_frozen_file_blocks(self):
        result = run_preflight_guards(
            changed_files=["core/domain/reconciliation_service.py"],
            trace_id="sentinel-int-002",
        )
        assert result["passed"] is False
        assert result["results"]["frozen_files"] == "fail"

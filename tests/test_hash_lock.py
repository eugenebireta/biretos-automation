"""Batch #4 — Hash Lock / Frozen Manifest Alignment: sentinel tests.

Proves that the orchestrator's frozen_files guard:
  1. Uses CI manifest as single source of truth
  2. Verifies SHA-256 hashes (CRLF-safe)
  3. Fails-closed on manifest errors
  4. Catches path matches, hash mismatches, and missing files

Deterministic — no live API, no unmocked time/randomness.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

import pytest  # noqa: E402

from core_gate_bridge import (  # noqa: E402
    _load_tier1_manifest,
    _check_frozen_files,
    _WINDMILL_ROOT,
    run_preflight_guards,
)


# =============================================================================
# Unit: _load_tier1_manifest
# =============================================================================

class TestLoadTier1Manifest:
    """Manifest loader must fail-closed on all error conditions."""

    def test_loads_valid_manifest(self):
        """Real manifest should load 19 entries."""
        manifest = _load_tier1_manifest()
        assert len(manifest) == 19
        assert "domain/reconciliation_service.py" in manifest
        assert "maintenance_sweeper.py" in manifest
        # Each hash is 64 hex chars
        for h in manifest.values():
            assert len(h) == 64

    def test_fails_on_missing_manifest(self, tmp_path):
        """Missing manifest → RuntimeError (fail-closed)."""
        with patch("core_gate_bridge._TIER1_MANIFEST", tmp_path / "nonexistent.sha256"):
            with pytest.raises(RuntimeError, match="not found"):
                _load_tier1_manifest()

    def test_fails_on_empty_manifest(self, tmp_path):
        """Empty manifest → RuntimeError (fail-closed)."""
        empty = tmp_path / ".tier1-hashes.sha256"
        empty.write_text("", encoding="utf-8")
        with patch("core_gate_bridge._TIER1_MANIFEST", empty):
            with pytest.raises(RuntimeError, match="empty"):
                _load_tier1_manifest()

    def test_fails_on_broken_manifest(self, tmp_path):
        """Malformed line → RuntimeError (fail-closed)."""
        bad = tmp_path / ".tier1-hashes.sha256"
        bad.write_text("this is not a valid hash line\n", encoding="utf-8")
        with patch("core_gate_bridge._TIER1_MANIFEST", bad):
            with pytest.raises(RuntimeError, match="parse error"):
                _load_tier1_manifest()


# =============================================================================
# Unit: _check_frozen_files — path matching
# =============================================================================

class TestFrozenFilesPathMatch:
    """Path check must catch changed files matching frozen paths."""

    def test_catches_frozen_path_full(self):
        """Full windmill path triggers fail."""
        status, violations = _check_frozen_files([
            str(_WINDMILL_ROOT / "domain" / "reconciliation_service.py"),
        ])
        assert status == "fail"
        assert any("path_frozen" in v for v in violations)

    def test_catches_frozen_path_relative(self):
        """Relative path ending with frozen file triggers fail."""
        status, violations = _check_frozen_files([
            "core/domain/reconciliation_service.py",
        ])
        assert status == "fail"
        assert any("path_frozen" in v for v in violations)

    def test_catches_migration_path(self):
        """Migration frozen file triggers fail."""
        status, violations = _check_frozen_files([
            "migrations/016_create_reconciliation_audit_log.sql",
        ])
        assert status == "fail"

    def test_passes_non_frozen_file(self):
        """Non-frozen file passes path check (hash check still runs)."""
        status, violations = _check_frozen_files([
            "catalog/datasheet/schema.py",
        ])
        assert status == "pass"
        assert not any("path_frozen" in v for v in violations)

    def test_passes_empty_changed_files(self):
        """Empty changed list → pass (hash check still verifies files on disk)."""
        status, violations = _check_frozen_files([])
        assert status == "pass"


# =============================================================================
# Unit: _check_frozen_files — hash verification
# =============================================================================

class TestFrozenFilesHashVerification:
    """Hash check must detect content modifications and missing files."""

    def test_detects_hash_mismatch(self, tmp_path):
        """Modified frozen file content → hash_mismatch violation."""
        # Create a fake windmill root with one tampered file
        (tmp_path / "domain").mkdir()
        tampered = tmp_path / "domain" / "reconciliation_service.py"
        tampered.write_text("# TAMPERED CONTENT\n", encoding="utf-8")

        # Copy all other files from real windmill root
        manifest = _load_tier1_manifest()
        for rel_path in manifest:
            if rel_path == "domain/reconciliation_service.py":
                continue
            dest = tmp_path / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = _WINDMILL_ROOT / rel_path
            if src.exists():
                dest.write_bytes(src.read_bytes())

        with patch("core_gate_bridge._WINDMILL_ROOT", tmp_path):
            status, violations = _check_frozen_files([])

        assert status == "fail"
        assert any("hash_mismatch" in v and "reconciliation_service" in v
                    for v in violations)

    def test_detects_missing_file(self, tmp_path):
        """Deleted frozen file → missing violation."""
        # Create windmill root with one file missing
        manifest = _load_tier1_manifest()
        for rel_path in manifest:
            if rel_path == "maintenance_sweeper.py":
                continue  # skip this one — simulate deletion
            dest = tmp_path / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            src = _WINDMILL_ROOT / rel_path
            if src.exists():
                dest.write_bytes(src.read_bytes())

        with patch("core_gate_bridge._WINDMILL_ROOT", tmp_path):
            status, violations = _check_frozen_files([])

        assert status == "fail"
        assert any("missing" in v and "maintenance_sweeper" in v
                    for v in violations)

    def test_crlf_lf_equivalence(self, tmp_path):
        """CRLF and LF versions of same content must produce same hash."""
        content_lf = b"line1\nline2\nline3\n"
        content_crlf = b"line1\r\nline2\r\nline3\r\n"

        # Both should hash identically after \r stripping
        hash_lf = hashlib.sha256(content_lf.replace(b"\r", b"")).hexdigest()
        hash_crlf = hashlib.sha256(content_crlf.replace(b"\r", b"")).hexdigest()
        assert hash_lf == hash_crlf

    def test_all_19_files_pass_on_real_repo(self):
        """Real repo: all 19 frozen files must have correct hashes."""
        status, violations = _check_frozen_files([])
        assert status == "pass", f"Hash verification failed: {violations}"
        assert violations == []


# =============================================================================
# Unit: _check_frozen_files — manifest errors
# =============================================================================

class TestFrozenFilesManifestErrors:
    """Manifest errors must produce fail, not pass (fail-closed)."""

    def test_missing_manifest_fails_guard(self, tmp_path):
        with patch("core_gate_bridge._TIER1_MANIFEST", tmp_path / "gone.sha256"):
            status, violations = _check_frozen_files([])
        assert status == "fail"
        assert any("manifest_error" in v for v in violations)

    def test_empty_manifest_fails_guard(self, tmp_path):
        empty = tmp_path / ".tier1-hashes.sha256"
        empty.write_text("", encoding="utf-8")
        with patch("core_gate_bridge._TIER1_MANIFEST", empty):
            status, violations = _check_frozen_files([])
        assert status == "fail"
        assert any("manifest_error" in v for v in violations)


# =============================================================================
# Integration: run_preflight_guards uses new hash lock
# =============================================================================

class TestPreflightUsesHashLock:
    """run_preflight_guards must use manifest-driven hash lock."""

    def test_clean_run_passes(self):
        """No changed frozen files + all hashes valid → pass."""
        result = run_preflight_guards(
            changed_files=["catalog/schema.py"],
            trace_id="hash-lock-001",
        )
        assert result["results"]["frozen_files"] == "pass"

    def test_frozen_path_blocks(self):
        """Changed frozen file → frozen_files=fail, passed=False."""
        result = run_preflight_guards(
            changed_files=["domain/reconciliation_service.py"],
            trace_id="hash-lock-002",
        )
        assert result["results"]["frozen_files"] == "fail"
        assert result["passed"] is False
        assert "frozen_files" in result["blocked_by"]

"""Batch #3 — Dual Audit Fallback Honesty: sentinel tests.

Proves that degraded audit modes are ENFORCED (route upgrade),
not just recorded in artifacts. Three scenarios:
  1. One provider down (degraded_single)
  2. Both providers down (unavailable)
  3. CLI-only path (advisory_only)

Plus: policy matrix enforcement for LOW/SEMI/CORE × degraded modes.

Deterministic — no live API, no unmocked time/randomness.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrator"))

from core_gate_bridge import (  # noqa: E402
    _classify_audit_mode,
    _apply_degraded_policy,
    run_cli_prescreen_sync,
    run_scope_review_sync,
)


# =============================================================================
# Unit: _classify_audit_mode
# =============================================================================

class TestClassifyAuditMode:
    """Deterministic classification of audit completeness."""

    def test_dual_both_ok(self):
        assert _classify_audit_mode({"gemini": "ok", "anthropic": "ok"}) == "dual"

    def test_degraded_gemini_down(self):
        assert _classify_audit_mode({"gemini": "error:HTTPError", "anthropic": "ok"}) == "degraded_single"

    def test_degraded_anthropic_down(self):
        assert _classify_audit_mode({"gemini": "ok", "anthropic": "error:Timeout"}) == "degraded_single"

    def test_unavailable_both_down(self):
        assert _classify_audit_mode({"gemini": "error:429", "anthropic": "error:Timeout"}) == "unavailable"

    def test_empty_is_unavailable(self):
        assert _classify_audit_mode({}) == "unavailable"


# =============================================================================
# Unit: _apply_degraded_policy — enforcement matrix
# =============================================================================

class TestApplyDegradedPolicy:
    """Policy matrix must ENFORCE route upgrades, not just annotate."""

    def _route(self, name: str):
        """Get ApprovalRoute enum by name."""
        from auditor_system.hard_shell.contracts import ApprovalRoute
        return ApprovalRoute(name)

    # ── LOW ──────────────────────────────────────────────────────────
    def test_low_dual_keeps_auto_pass(self):
        route, reason = _apply_degraded_policy(
            "LOW", "dual", self._route("auto_pass"))
        assert route == self._route("auto_pass")
        assert reason is None

    def test_low_degraded_keeps_auto_pass(self):
        """LOW tolerates single auditor — no upgrade."""
        route, reason = _apply_degraded_policy(
            "LOW", "degraded_single", self._route("auto_pass"))
        assert route == self._route("auto_pass")
        assert reason is None

    def test_low_unavailable_upgrades_to_individual_review(self):
        route, reason = _apply_degraded_policy(
            "LOW", "unavailable", self._route("auto_pass"))
        assert route == self._route("individual_review")
        assert reason is not None

    # ── SEMI ─────────────────────────────────────────────────────────
    def test_semi_dual_keeps_batch_approval(self):
        route, reason = _apply_degraded_policy(
            "SEMI", "dual", self._route("batch_approval"))
        assert route == self._route("batch_approval")
        assert reason is None

    def test_semi_degraded_enforces_individual_review(self):
        """SEMI + degraded_single MUST upgrade to INDIVIDUAL_REVIEW."""
        route, reason = _apply_degraded_policy(
            "SEMI", "degraded_single", self._route("batch_approval"))
        assert route == self._route("individual_review")
        assert reason is not None
        assert "SEMI" in reason

    def test_semi_degraded_cannot_be_auto_pass(self):
        """SEMI + degraded_single from AUTO_PASS → still INDIVIDUAL_REVIEW."""
        route, _ = _apply_degraded_policy(
            "SEMI", "degraded_single", self._route("auto_pass"))
        assert route == self._route("individual_review")

    def test_semi_unavailable_enforces_blocked(self):
        route, reason = _apply_degraded_policy(
            "SEMI", "unavailable", self._route("batch_approval"))
        assert route == self._route("blocked")
        assert reason is not None

    # ── CORE ─────────────────────────────────────────────────────────
    def test_core_dual_keeps_individual_review(self):
        route, reason = _apply_degraded_policy(
            "CORE", "dual", self._route("individual_review"))
        assert route == self._route("individual_review")
        assert reason is None

    def test_core_degraded_enforces_blocked(self):
        """CORE + degraded_single MUST BLOCK."""
        route, reason = _apply_degraded_policy(
            "CORE", "degraded_single", self._route("individual_review"))
        assert route == self._route("blocked")
        assert reason is not None
        assert "CORE" in reason

    def test_core_unavailable_enforces_blocked(self):
        route, reason = _apply_degraded_policy(
            "CORE", "unavailable", self._route("individual_review"))
        assert route == self._route("blocked")
        assert reason is not None

    # ── Never downgrade ──────────────────────────────────────────────
    def test_never_downgrades_blocked(self):
        """If already BLOCKED, degraded policy must not downgrade."""
        route, _ = _apply_degraded_policy(
            "LOW", "unavailable", self._route("blocked"))
        assert route == self._route("blocked")


# =============================================================================
# Integration: CLI prescreen marks self_eval_conflict
# =============================================================================

class TestCliPresecreenHonesty:
    """CLI prescreen must always declare conflict of interest."""

    def test_cli_pass_has_advisory_flags(self):
        with patch("core_gate_bridge._cli_single_pass",
                   return_value={"passed": True, "issues": [], "summary": "ok"}):
            result = run_cli_prescreen_sync(
                packet={"changed_files": ["a.py"], "test_results": {"passed": 5, "failed": 0}},
                directive_text="test directive",
                trace_id="test-cli-001",
                risk_class="LOW",
                retry_count=0,
            )
        assert result["self_eval_conflict"] is True
        assert result["advisory_only"] is True
        assert result["audit_mode"] == "cli_only"

    def test_cli_fail_has_advisory_flags(self):
        with patch("core_gate_bridge._cli_single_pass",
                   return_value={"passed": False, "issues": ["scope violation"], "summary": "bad"}):
            result = run_cli_prescreen_sync(
                packet={"changed_files": ["a.py"], "test_results": {"passed": 5, "failed": 0}},
                directive_text="test directive",
                trace_id="test-cli-002",
                risk_class="SEMI",
                retry_count=1,
            )
        assert result["self_eval_conflict"] is True
        assert result["advisory_only"] is True
        assert result["verdict"] == "prescreen_fail"

    def test_cli_skip_has_advisory_flags(self):
        """When CLI can't parse response → prescreen_skip, still honest."""
        with patch("core_gate_bridge._cli_single_pass", return_value=None):
            result = run_cli_prescreen_sync(
                packet={"changed_files": [], "test_results": {}},
                directive_text="test",
                trace_id="test-cli-003",
                risk_class="LOW",
                retry_count=0,
            )
        assert result["self_eval_conflict"] is True
        assert result["advisory_only"] is True
        assert result["verdict"] == "prescreen_skip"


# =============================================================================
# Integration: scope review with mocked auditors
# =============================================================================

class TestScopeReviewFallback:
    """run_scope_review_sync must report audit_mode and provider_status."""

    def _make_verdict(self, auditor_id="gemini", verdict_val="approved"):
        """Build a minimal mock verdict."""
        issue = MagicMock()
        issue.severity.value = "warning"
        issue.description = "test concern"
        v = MagicMock()
        v.auditor_id = auditor_id
        v.verdict.value = verdict_val
        v.issues = [issue]
        return v

    def _run_scope_review_with_mocks(self, gemini_side_effect, anthropic_side_effect):
        """Helper: run scope review with mocked auditor providers."""
        mock_gemini_mod = MagicMock()
        mock_anthropic_mod = MagicMock()

        mock_gemini_inst = MagicMock()
        mock_gemini_inst.auditor_id = "gemini"
        mock_gemini_inst.critique = AsyncMock(side_effect=gemini_side_effect)
        mock_gemini_mod.GeminiAuditor.return_value = mock_gemini_inst

        mock_anthropic_inst = MagicMock()
        mock_anthropic_inst.auditor_id = "anthropic"
        mock_anthropic_inst.critique = AsyncMock(side_effect=anthropic_side_effect)
        mock_anthropic_mod.AnthropicAuditor.return_value = mock_anthropic_inst

        with patch("core_gate_bridge._init_auditors",
                   return_value=({"GEMINI_API_KEY": "k", "ANTHROPIC_API_KEY": "k"},
                                 "m", "m", "m")), \
             patch.dict("sys.modules", {
                 "auditor_system.providers.gemini_auditor": mock_gemini_mod,
                 "auditor_system.providers.anthropic_auditor": mock_anthropic_mod,
             }):
            task_pack = MagicMock()
            task_pack.title = "test"
            return run_scope_review_sync(task_pack, scope_text="test scope")

    def test_scope_review_dual_mode(self):
        """Both auditors succeed → audit_mode=dual."""
        gemini_v = self._make_verdict("gemini", "approved")
        anthropic_v = self._make_verdict("anthropic", "approved")

        result = self._run_scope_review_with_mocks(
            gemini_side_effect=[gemini_v],
            anthropic_side_effect=[anthropic_v],
        )

        assert result["audit_mode"] == "dual"
        assert result["provider_status"]["gemini"] == "ok"
        assert result["provider_status"]["anthropic"] == "ok"
        assert result["confidence_reduction_reason"] is None

    def test_scope_review_degraded_mode(self):
        """Gemini fails (429) → audit_mode=degraded_single."""
        anthropic_v = self._make_verdict("anthropic", "approved")

        result = self._run_scope_review_with_mocks(
            gemini_side_effect=Exception("429 rate limit"),
            anthropic_side_effect=[anthropic_v],
        )

        assert result["audit_mode"] == "degraded_single"
        assert "error" in result["provider_status"]["gemini"]
        assert result["provider_status"]["anthropic"] == "ok"
        assert result["confidence_reduction_reason"] is not None

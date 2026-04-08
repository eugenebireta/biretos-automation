"""
test_classifier.py — deterministic unit tests for orchestrator/classifier.py

All tests are mocked/parameterized — no file I/O, no live API, no subprocess.
"""
from __future__ import annotations

import pytest
from classifier import classify, ClassifierResult, _check_tier, _migration_seq


# ---------------------------------------------------------------------------
# _check_tier
# ---------------------------------------------------------------------------
class TestCheckTier:
    def test_tier1_reconciliation(self):
        assert _check_tier(".cursor/windmill-core-v1/domain/reconciliation_service.py") == "Tier-1"

    def test_tier1_maintenance_sweeper(self):
        assert _check_tier(".cursor/windmill-core-v1/maintenance_sweeper.py") == "Tier-1"

    def test_tier1_migrations_016(self):
        assert _check_tier(".cursor/windmill-core-v1/migrations/016_init.sql") == "Tier-1"

    def test_tier1_migrations_019(self):
        assert _check_tier(".cursor/windmill-core-v1/migrations/019_foo.sql") == "Tier-1"

    def test_tier1_validation(self):
        assert _check_tier(".cursor/windmill-core-v1/tests/validation/test_something.py") == "Tier-1"

    def test_tier2_domain_non_reconciliation(self):
        assert _check_tier(".cursor/windmill-core-v1/domain/cdm_models.py") == "Tier-2"

    def test_tier2_migrations_non_frozen(self):
        assert _check_tier(".cursor/windmill-core-v1/migrations/020_revenue.sql") == "Tier-2"

    def test_tier3_scripts(self):
        assert _check_tier("scripts/export_pipeline.py") == "Tier-3"

    def test_tier3_orchestrator(self):
        assert _check_tier("orchestrator/main.py") == "Tier-3"

    def test_tier3_random(self):
        assert _check_tier("some/random/file.py") == "Tier-3"


# ---------------------------------------------------------------------------
# _migration_seq
# ---------------------------------------------------------------------------
class TestMigrationSeq:
    def test_seq_016(self):
        assert _migration_seq("migrations/016_init.sql") == 16

    def test_seq_025(self):
        assert _migration_seq(".cursor/windmill-core-v1/migrations/025_create_foo.sql") == 25

    def test_no_seq(self):
        assert _migration_seq("scripts/some_file.py") == 0

    def test_seq_001(self):
        assert _migration_seq("migrations/001_bootstrap.sql") == 1


# ---------------------------------------------------------------------------
# classify — LOW path
# ---------------------------------------------------------------------------
class TestClassifyLow:
    def test_empty_files_is_low(self):
        result = classify([])
        assert result.risk_class == "LOW"
        assert result.governance_route == "none"
        assert not result.tier_violations
        assert not result.blocking_rules

    def test_tier3_files_is_low(self):
        result = classify(["scripts/export_pipeline.py", "tests/test_foo.py"])
        assert result.risk_class == "LOW"
        assert result.governance_route == "none"

    def test_low_rationale_mentions_tier3(self):
        result = classify(["scripts/foo.py"])
        assert "Tier-3" in result.rationale

    def test_low_no_violations(self):
        result = classify(["orchestrator/collect_packet.py"])
        assert result.tier_violations == []
        assert result.blocking_rules == []


# ---------------------------------------------------------------------------
# classify — SEMI / S1 (Tier-2)
# ---------------------------------------------------------------------------
class TestClassifySemiTier2:
    def test_tier2_domain_is_semi(self):
        result = classify([".cursor/windmill-core-v1/domain/cdm_models.py"])
        assert result.risk_class == "SEMI"
        assert result.governance_route == "audit"

    def test_tier2_violation_listed(self):
        path = ".cursor/windmill-core-v1/domain/some_model.py"
        result = classify([path])
        assert any(path in v for v in result.tier_violations)

    def test_tier2_rationale_mentions_pinned(self):
        result = classify([".cursor/windmill-core-v1/domain/foo.py"])
        assert "pinned" in result.rationale.lower() or "Tier-2" in result.rationale


# ---------------------------------------------------------------------------
# classify — SEMI / S2 (revenue migrations)
# ---------------------------------------------------------------------------
class TestClassifySemiMigrations:
    def test_migration_020_is_semi(self):
        result = classify([".cursor/windmill-core-v1/migrations/020_revenue.sql"])
        # migrations/020+ are Tier-2 prefix but also S2
        assert result.risk_class == "SEMI"

    def test_migration_025_is_semi(self):
        result = classify(["migrations/025_create_foo.sql"])
        assert result.risk_class == "SEMI"
        assert result.governance_route == "critique"

    def test_migration_015_is_tier1(self):
        # 015 is not in frozen range (016-019 are frozen), falls to Tier-2 prefix check
        # migrations/015_xxx is Tier-2 prefix but seq < 20 → not S2
        # Tier-2 prefix match → SEMI/audit
        result = classify([".cursor/windmill-core-v1/migrations/015_foo.sql"])
        assert result.risk_class == "SEMI"


# ---------------------------------------------------------------------------
# classify — SEMI / S3 (orchestrator policy files)
# ---------------------------------------------------------------------------
class TestClassifySemiPolicy:
    def test_synthesizer_file_is_semi(self):
        result = classify(["orchestrator/synthesizer.py"])
        assert result.risk_class == "SEMI"
        assert result.governance_route == "critique"

    def test_advisor_file_is_semi(self):
        result = classify(["orchestrator/advisor.py"])
        assert result.risk_class == "SEMI"
        assert "advisor" in result.rationale.lower() or "policy" in result.rationale.lower()

    def test_classifier_file_itself_is_semi(self):
        result = classify(["orchestrator/classifier.py"])
        assert result.risk_class == "SEMI"


# ---------------------------------------------------------------------------
# classify — CORE / C1 (Tier-1 files)
# ---------------------------------------------------------------------------
class TestClassifyCoreC1:
    def test_tier1_reconciliation_is_core(self):
        result = classify([".cursor/windmill-core-v1/domain/reconciliation_service.py"])
        assert result.risk_class == "CORE"
        assert result.governance_route == "spec_full"

    def test_tier1_maintenance_sweeper_is_core(self):
        result = classify([".cursor/windmill-core-v1/maintenance_sweeper.py"])
        assert result.risk_class == "CORE"

    def test_tier1_blocking_rule_c1(self):
        result = classify([".cursor/windmill-core-v1/domain/reconciliation_alerts.py"])
        assert any("C1" in r for r in result.blocking_rules)

    def test_tier1_violation_lists_files(self):
        path = ".cursor/windmill-core-v1/migrations/017_foo.sql"
        result = classify([path])
        assert result.risk_class == "CORE"
        assert any(path in v for v in result.tier_violations)


# ---------------------------------------------------------------------------
# classify — CORE / C2 (prohibited imports in intent)
# ---------------------------------------------------------------------------
class TestClassifyCoreC2:
    def test_prohibited_import_in_intent(self):
        result = classify([], intent="use domain.reconciliation_service for this")
        assert result.risk_class == "CORE"
        assert result.governance_route == "spec_full"
        assert any("C2" in r for r in result.blocking_rules)

    def test_prohibited_import_in_task_id(self):
        result = classify([], task_id="domain.structural_checks refactor")
        assert result.risk_class == "CORE"

    def test_clean_intent_not_core(self):
        result = classify(["scripts/foo.py"], intent="add price evidence cache")
        assert result.risk_class == "LOW"


# ---------------------------------------------------------------------------
# classify — CORE / C3 (pinned API signatures in intent)
# ---------------------------------------------------------------------------
class TestClassifyCoreC3:
    def test_pinned_sig_in_intent(self):
        result = classify([], intent="refactor _derive_payment_status logic")
        assert result.risk_class == "CORE"
        assert any("C3" in r for r in result.blocking_rules)

    def test_extract_order_total_is_core(self):
        result = classify([], intent="optimize _extract_order_total_minor")
        assert result.risk_class == "CORE"

    def test_invoice_status_request_is_core(self):
        result = classify([], intent="add field to InvoiceStatusRequest")
        assert result.risk_class == "CORE"

    def test_unrelated_intent_not_core(self):
        result = classify(["scripts/foo.py"], intent="add batch export feature")
        assert result.risk_class == "LOW"


# ---------------------------------------------------------------------------
# classify — CORE / C4 (Core table DML in intent)
# ---------------------------------------------------------------------------
class TestClassifyCoreC4:
    def test_insert_on_core_table(self):
        result = classify([], intent="insert into order_ledger from worker")
        assert result.risk_class == "CORE"
        assert any("C4" in r for r in result.blocking_rules)

    def test_delete_from_shipments(self):
        result = classify([], intent="delete stale rows from shipments table")
        assert result.risk_class == "CORE"

    def test_update_payment_transactions(self):
        result = classify([], intent="update payment_transactions status field")
        assert result.risk_class == "CORE"

    def test_drop_core_table_is_core(self):
        result = classify([], intent="drop table stock_ledger_entries")
        assert result.risk_class == "CORE"

    def test_select_from_core_not_core(self):
        # SELECT is not in the DML list → not CORE
        result = classify(["scripts/foo.py"], intent="select from order_ledger view")
        assert result.risk_class == "LOW"


# ---------------------------------------------------------------------------
# priority: CORE beats SEMI (C1 before S1)
# ---------------------------------------------------------------------------
class TestClassifyPriority:
    def test_tier1_with_tier2_is_core(self):
        result = classify([
            ".cursor/windmill-core-v1/domain/reconciliation_service.py",
            ".cursor/windmill-core-v1/domain/cdm_models.py",
        ])
        assert result.risk_class == "CORE"

    def test_tier1_with_tier3_is_core(self):
        result = classify([
            ".cursor/windmill-core-v1/maintenance_sweeper.py",
            "scripts/export_pipeline.py",
        ])
        assert result.risk_class == "CORE"

    def test_affected_tiers_override_used(self):
        # If affected_tiers is provided (pre-computed), it's used for tier summary only
        # CORE/SEMI triggers still come from changed_files
        result = classify(["scripts/foo.py"], affected_tiers=["Tier-3"])
        assert result.risk_class == "LOW"

    def test_result_is_classifier_result_type(self):
        result = classify(["scripts/foo.py"])
        assert isinstance(result, ClassifierResult)
        assert isinstance(result.tier_violations, list)
        assert isinstance(result.blocking_rules, list)

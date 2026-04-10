"""
tests/orchestrator/test_schemas.py

Deterministic schema validation tests for all 5 M0.5 schemas.
No live API, no filesystem writes — pure in-memory validation.
"""

import pytest

from schemas import is_valid, list_schemas, validate, validate_soft


# ---------------------------------------------------------------------------
# Helpers: valid fixture objects
# ---------------------------------------------------------------------------

def _valid_directive():
    return {
        "schema_version": "v1",
        "trace_id": "orch_20260407_abc123",
        "task_id": "step_1a1",
        "intent": "Implement ClaudeChatAdapter",
        "scope": ["scripts/providers.py"],
        "constraints": ["Do not touch Tier-1"],
        "acceptance_criteria": ["Tests pass with mock provider"],
        "relevant_artifacts": ["scripts/photo_pipeline.py"],
        "context_summary": "Step 1A1 of Enrichment Plan",
        "max_attempts": 3,
        "attempt_number": 1,
        "base_commit": "abc123",
    }


def _valid_execution_packet():
    return {
        "schema_version": "v1",
        "trace_id": "orch_20260407_abc123",
        "status": "completed",
        "changed_files": ["scripts/providers.py"],
        "diff_summary": "Added ClaudeChatAdapter",
        "diff_char_count": 1200,
        "diff_truncated": False,
        "test_results": {"passed": 30, "failed": 0, "skipped": 0, "error": 0},
        "affected_tiers": ["Tier-3"],
        "executor_notes": None,
        "questions": [],
        "blockers": [],
        "artifacts_produced": ["tests/enrichment/test_providers.py"],
        "collected_by": "collect_packet.py",
        "collected_at": "2026-04-07T10:00:00+00:00",
        "base_commit": "abc123",
    }


def _valid_advisor_verdict():
    return {
        "schema_version": "v1",
        "trace_id": "R1-PILOT-001",
        "risk_assessment": "LOW",
        "governance_route": "none",
        "rationale": "Previous step completed cleanly. Tests are next.",
        "next_step": "Add unit tests for ClaudeChatAdapter covering idempotent re-runs.",
        "scope": ["tests/enrichment/test_providers.py"],
        "issued_at": "2026-04-08T10:00:00Z",
    }


def _valid_manifest():
    return {
        "schema_version": "v1",
        "fsm_state": "ready",
        "current_sprint_goal": "Implement enrichment provider swap",
        "current_task_id": "step_1a1",
        "trace_id": "orch_20260407_abc123",
        "attempt_count": 1,
        "last_verdict": None,
        "last_directive_hash": "deadbeef1234",
        "pending_packet_id": None,
        "deadline_at": None,
        "default_option_id": None,
        "updated_at": "2026-04-07T10:00:00+00:00",
    }


def _valid_escalation():
    return {
        "schema_version": "v1",
        "trace_id": "orch_20260407_abc123",
        "packet_id": "esc_001",
        "idempotency_key": "esc_orch_20260407_abc123_001",
        "escalation_type": "deadlock",
        "what_blocked": "attempt_count exceeded max_attempts",
        "why_not_auto": "Cannot resolve without business direction",
        "business_question": "Should we skip this step or retry with different scope?",
        "affected_entity_count": None,
        "reversible": True,
        "options": [
            {"id": "a", "label": "Skip and defer", "next_action": "defer_to_backlog"},
            {"id": "b", "label": "Retry with wider scope", "next_action": "expand_scope"},
        ],
        "recommended_option": "a",
        "default_if_no_reply": "a",
        "deadline_at": "2026-04-08T10:00:00+00:00",
        "artifact_refs": [],
    }


# ---------------------------------------------------------------------------
# Schema registry
# ---------------------------------------------------------------------------

class TestSchemaRegistry:
    def test_all_five_schemas_registered(self):
        names = list_schemas()
        assert "directive_v1" in names
        assert "execution_packet_v1" in names
        assert "advisor_verdict_v1" in names
        assert "manifest_v1" in names
        assert "escalation_v1" in names

    def test_unknown_schema_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown schema"):
            validate("nonexistent_schema_v99", {})

    def test_validate_soft_unknown_schema_returns_error(self):
        errors = validate_soft("nonexistent_v99", {})
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# directive_v1
# ---------------------------------------------------------------------------

class TestDirectiveSchema:
    def test_valid(self):
        assert is_valid("directive_v1", _valid_directive())

    def test_missing_required_intent(self):
        d = _valid_directive()
        del d["intent"]
        assert not is_valid("directive_v1", d)

    def test_missing_required_scope(self):
        d = _valid_directive()
        del d["scope"]
        assert not is_valid("directive_v1", d)

    def test_empty_scope_invalid(self):
        d = _valid_directive()
        d["scope"] = []
        assert not is_valid("directive_v1", d)

    def test_wrong_schema_version(self):
        d = _valid_directive()
        d["schema_version"] = "v2"
        assert not is_valid("directive_v1", d)

    def test_extra_field_invalid(self):
        d = _valid_directive()
        d["unexpected_field"] = "oops"
        assert not is_valid("directive_v1", d)

    def test_trace_id_must_start_with_orch(self):
        d = _valid_directive()
        d["trace_id"] = "bad_prefix_123"
        assert not is_valid("directive_v1", d)

    def test_max_attempts_must_be_positive(self):
        d = _valid_directive()
        d["max_attempts"] = 0
        assert not is_valid("directive_v1", d)

    def test_base_commit_nullable(self):
        d = _valid_directive()
        d["base_commit"] = None
        assert is_valid("directive_v1", d)

    def test_optional_fields_omittable(self):
        d = _valid_directive()
        del d["relevant_artifacts"]
        del d["context_summary"]
        del d["base_commit"]
        assert is_valid("directive_v1", d)


# ---------------------------------------------------------------------------
# execution_packet_v1
# ---------------------------------------------------------------------------

class TestExecutionPacketSchema:
    def test_valid(self):
        assert is_valid("execution_packet_v1", _valid_execution_packet())

    def test_valid_status_values(self):
        for status in ("completed", "partial", "blocked", "failed", "collection_failed"):
            p = _valid_execution_packet()
            p["status"] = status
            assert is_valid("execution_packet_v1", p), f"status={status} should be valid"

    def test_invalid_status(self):
        p = _valid_execution_packet()
        p["status"] = "unknown_status"
        assert not is_valid("execution_packet_v1", p)

    def test_missing_collected_by(self):
        p = _valid_execution_packet()
        del p["collected_by"]
        assert not is_valid("execution_packet_v1", p)

    def test_null_test_results_valid(self):
        p = _valid_execution_packet()
        p["test_results"] = None
        assert is_valid("execution_packet_v1", p)

    def test_diff_char_count_non_negative(self):
        p = _valid_execution_packet()
        p["diff_char_count"] = -1
        assert not is_valid("execution_packet_v1", p)

    def test_extra_field_invalid(self):
        p = _valid_execution_packet()
        p["surprise"] = "field"
        assert not is_valid("execution_packet_v1", p)


# ---------------------------------------------------------------------------
# advisor_verdict_v1
# ---------------------------------------------------------------------------

class TestAdvisorVerdictSchema:
    def test_valid(self):
        assert is_valid("advisor_verdict_v1", _valid_advisor_verdict())

    def test_valid_governance_routes(self):
        for route in ("none", "critique", "audit", "spec_full"):
            v = _valid_advisor_verdict()
            v["governance_route"] = route
            assert is_valid("advisor_verdict_v1", v), f"route={route} should be valid"

    def test_invalid_governance_route(self):
        v = _valid_advisor_verdict()
        v["governance_route"] = "full_spec"  # typo
        assert not is_valid("advisor_verdict_v1", v)

    def test_valid_risk_assessments(self):
        for risk in ("LOW", "SEMI", "CORE"):
            v = _valid_advisor_verdict()
            v["risk_assessment"] = risk
            assert is_valid("advisor_verdict_v1", v)

    def test_invalid_risk_assessment(self):
        v = _valid_advisor_verdict()
        v["risk_assessment"] = "low"  # must be uppercase
        assert not is_valid("advisor_verdict_v1", v)

    def test_missing_next_step(self):
        v = _valid_advisor_verdict()
        del v["next_step"]
        assert not is_valid("advisor_verdict_v1", v)

    def test_empty_next_step_invalid(self):
        v = _valid_advisor_verdict()
        v["next_step"] = ""
        assert not is_valid("advisor_verdict_v1", v)

    def test_missing_trace_id_invalid(self):
        v = _valid_advisor_verdict()
        del v["trace_id"]
        assert not is_valid("advisor_verdict_v1", v)

    def test_extra_field_invalid(self):
        v = _valid_advisor_verdict()
        v["confidence_score"] = 0.9  # rejected: AI-driven routing signal
        assert not is_valid("advisor_verdict_v1", v)

    def test_empty_scope_valid(self):
        v = _valid_advisor_verdict()
        v["scope"] = []
        assert is_valid("advisor_verdict_v1", v)


# ---------------------------------------------------------------------------
# manifest_v1
# ---------------------------------------------------------------------------

class TestManifestSchema:
    def test_valid(self):
        assert is_valid("manifest_v1", _valid_manifest())

    def test_valid_fsm_states(self):
        for state in ("ready", "awaiting_execution", "awaiting_owner_reply", "completed", "error"):
            m = _valid_manifest()
            m["fsm_state"] = state
            assert is_valid("manifest_v1", m), f"state={state} should be valid"

    def test_invalid_fsm_state(self):
        m = _valid_manifest()
        m["fsm_state"] = "unknown_state"
        assert not is_valid("manifest_v1", m)

    def test_valid_last_verdict_values(self):
        verdicts = [
            "EXECUTE_NEXT_STEP", "ASK_EXECUTOR_FOR_RECON", "RUN_CRITIQUE",
            "RUN_SPEC_GOVERNANCE", "ESCALATE_TO_OWNER", None,
        ]
        for verdict in verdicts:
            m = _valid_manifest()
            m["last_verdict"] = verdict
            assert is_valid("manifest_v1", m), f"verdict={verdict} should be valid"

    def test_invalid_last_verdict(self):
        m = _valid_manifest()
        m["last_verdict"] = "RUN_AUDIT_OR_CRITIQUE"  # old name, rejected
        assert not is_valid("manifest_v1", m)

    def test_attempt_count_non_negative(self):
        m = _valid_manifest()
        m["attempt_count"] = -1
        assert not is_valid("manifest_v1", m)

    def test_optional_nullable_fields(self):
        m = _valid_manifest()
        m["last_directive_hash"] = None
        m["pending_packet_id"] = None
        m["deadline_at"] = None
        m["default_option_id"] = None
        assert is_valid("manifest_v1", m)

    def test_extra_field_invalid(self):
        m = _valid_manifest()
        m["extra"] = "field"
        assert not is_valid("manifest_v1", m)


# ---------------------------------------------------------------------------
# escalation_v1
# ---------------------------------------------------------------------------

class TestEscalationSchema:
    def test_valid(self):
        assert is_valid("escalation_v1", _valid_escalation())

    def test_valid_escalation_types(self):
        for etype in ("business_decision", "deadlock", "guardrail_violation",
                      "collection_failure", "advisor_failure"):
            e = _valid_escalation()
            e["escalation_type"] = etype
            assert is_valid("escalation_v1", e), f"type={etype} should be valid"

    def test_invalid_escalation_type(self):
        e = _valid_escalation()
        e["escalation_type"] = "unknown_type"
        assert not is_valid("escalation_v1", e)

    def test_empty_options_invalid(self):
        e = _valid_escalation()
        e["options"] = []
        assert not is_valid("escalation_v1", e)

    def test_option_missing_field(self):
        e = _valid_escalation()
        e["options"] = [{"id": "a", "label": "Skip"}]  # missing next_action
        assert not is_valid("escalation_v1", e)

    def test_affected_entity_count_nullable(self):
        e = _valid_escalation()
        e["affected_entity_count"] = None
        assert is_valid("escalation_v1", e)

    def test_affected_entity_count_positive(self):
        e = _valid_escalation()
        e["affected_entity_count"] = 25
        assert is_valid("escalation_v1", e)

    def test_missing_idempotency_key(self):
        e = _valid_escalation()
        del e["idempotency_key"]
        assert not is_valid("escalation_v1", e)

    def test_extra_field_invalid(self):
        e = _valid_escalation()
        e["cost_estimate"] = "high"  # removed from base schema
        assert not is_valid("escalation_v1", e)

    def test_deadline_at_nullable(self):
        e = _valid_escalation()
        e["deadline_at"] = None
        assert is_valid("escalation_v1", e)


# ---------------------------------------------------------------------------
# validate_soft: error messages are strings
# ---------------------------------------------------------------------------

class TestValidateSoft:
    def test_returns_empty_list_on_valid(self):
        assert validate_soft("manifest_v1", _valid_manifest()) == []

    def test_returns_error_strings_on_invalid(self):
        m = _valid_manifest()
        m["fsm_state"] = "bad_state"
        errors = validate_soft("manifest_v1", m)
        assert len(errors) > 0
        assert all(isinstance(e, str) for e in errors)

    def test_validate_raises_on_invalid(self):
        import jsonschema
        m = _valid_manifest()
        m["fsm_state"] = "bad_state"
        with pytest.raises(jsonschema.ValidationError):
            validate("manifest_v1", m)

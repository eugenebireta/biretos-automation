"""
test_advisor.py — deterministic unit tests for orchestrator/advisor.py

All API calls are mocked — no live network, no Anthropic key required.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from advisor import (
    AdvisorResult,
    AdvisorVerdict,
    _extract_json,
    _validate_verdict_dict,
    _build_full_user_prompt,
    call,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bundle(
    sprint_goal="Ship R1",
    task_id="TASK-001",
    trace_id="orch_20260407T120000Z_abc123",
    last_changed_files=None,
    last_diff=None,
    last_status=None,
    dna_constraints=None,
    warnings=None,
    validation_errors=None,
):
    b = MagicMock()
    b.sprint_goal = sprint_goal
    b.task_id = task_id
    b.trace_id = trace_id
    b.last_changed_files = last_changed_files or []
    b.last_diff = last_diff
    b.last_status = last_status
    b.dna_constraints = dna_constraints or ["Tier-1 frozen"]
    b.warnings = warnings or []
    b.validation_errors = validation_errors or []
    b.to_advisor_prompt_context.return_value = (
        f"## Sprint Goal\n{sprint_goal}\n\n## Current Task\ntask_id: {task_id}"
    )
    return b


def _good_verdict_json(trace_id="orch_20260407T120000Z_abc123") -> str:
    return json.dumps({
        "schema_version": "v1",
        "trace_id": trace_id,
        "risk_assessment": "LOW",
        "governance_route": "none",
        "rationale": "Tier-3 only changes.",
        "next_step": "Add price evidence to cache module.",
        "scope": ["scripts/price_evidence_cache.py"],
        "issued_at": "2026-04-07T12:00:00+00:00",
    })


def _make_client_mock(response_text: str):
    """Create a mock Anthropic client that returns response_text."""
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------
class TestExtractJson:
    def test_clean_json(self):
        data = _extract_json('{"a": 1}')
        assert data == {"a": 1}

    def test_json_with_prose_before(self):
        data = _extract_json('Here is the result:\n{"key": "value"}')
        assert data == {"key": "value"}

    def test_json_with_markdown_fence(self):
        data = _extract_json('```json\n{"x": 42}\n```')
        assert data == {"x": 42}

    def test_json_with_trailing_text(self):
        data = _extract_json('{"a": 1} and some extra text')
        assert data == {"a": 1}

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="No JSON"):
            _extract_json("No JSON here at all")

    def test_unbalanced_braces_raises(self):
        with pytest.raises(ValueError):
            _extract_json("{unclosed: true")

    def test_nested_json(self):
        data = _extract_json('{"outer": {"inner": 1}}')
        assert data == {"outer": {"inner": 1}}

    def test_fence_without_language(self):
        data = _extract_json("```\n{\"k\": \"v\"}\n```")
        assert data == {"k": "v"}


# ---------------------------------------------------------------------------
# _validate_verdict_dict
# ---------------------------------------------------------------------------
class TestValidateVerdictDict:
    def _good(self, **overrides) -> dict:
        d = {
            "schema_version": "v1",
            "trace_id": "orch_xxx",
            "risk_assessment": "LOW",
            "governance_route": "none",
            "rationale": "ok",
            "next_step": "do thing",
            "scope": [],
            "issued_at": "2026-04-07T12:00:00+00:00",
        }
        d.update(overrides)
        return d

    def test_valid_returns_empty(self):
        assert _validate_verdict_dict(self._good(), "orch_xxx") == []

    def test_missing_fields(self):
        errs = _validate_verdict_dict({}, "t")
        assert any("Missing" in e for e in errs)

    def test_invalid_risk_assessment(self):
        errs = _validate_verdict_dict(self._good(risk_assessment="UNKNOWN"), "t")
        assert any("risk_assessment" in e for e in errs)

    def test_invalid_governance_route(self):
        errs = _validate_verdict_dict(self._good(governance_route="full_audit"), "t")
        assert any("governance_route" in e for e in errs)

    def test_scope_not_list(self):
        errs = _validate_verdict_dict(self._good(scope="not_a_list"), "t")
        assert any("scope" in e for e in errs)

    def test_all_valid_risk_values(self):
        for risk in ("LOW", "SEMI", "CORE"):
            errs = _validate_verdict_dict(self._good(risk_assessment=risk), "t")
            assert not any("risk_assessment" in e for e in errs)

    def test_all_valid_route_values(self):
        for route in ("none", "critique", "audit", "spec_full"):
            errs = _validate_verdict_dict(self._good(governance_route=route), "t")
            assert not any("governance_route" in e for e in errs)


# ---------------------------------------------------------------------------
# call() — success on first attempt
# ---------------------------------------------------------------------------
class TestCallSuccess:
    def test_returns_advisor_result(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock(_good_verdict_json())
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert isinstance(result, AdvisorResult)

    def test_verdict_not_none_on_success(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock(_good_verdict_json())
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.verdict is not None

    def test_escalated_false_on_success(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock(_good_verdict_json())
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.escalated is False

    def test_attempt_count_1_on_first_success(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock(_good_verdict_json())
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.attempt_count == 1

    def test_verdict_fields_populated(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock(_good_verdict_json())
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        v = result.verdict
        assert v.risk_assessment == "LOW"
        assert v.governance_route == "none"
        assert v.next_step == "Add price evidence to cache module."
        assert v.scope == ["scripts/price_evidence_cache.py"]

    def test_verdict_file_written_on_success(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock(_good_verdict_json())
        vpath = tmp_path / "verdict.json"
        call(bundle, _client=client,
             verdict_path=vpath,
             escalation_path=tmp_path / "esc.json",
             config={})
        assert vpath.exists()
        data = json.loads(vpath.read_text())
        assert data["risk_assessment"] == "LOW"
        assert data["governance_route"] == "none"

    def test_no_escalation_file_on_success(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock(_good_verdict_json())
        espath = tmp_path / "esc.json"
        call(bundle, _client=client,
             verdict_path=tmp_path / "verdict.json",
             escalation_path=espath,
             config={})
        assert not espath.exists()

    def test_json_with_prose_accepted(self, tmp_path):
        bundle = _make_bundle()
        prose_response = "Sure, here is my analysis:\n" + _good_verdict_json()
        client = _make_client_mock(prose_response)
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.verdict is not None

    def test_json_in_markdown_fence_accepted(self, tmp_path):
        bundle = _make_bundle()
        fenced = f"```json\n{_good_verdict_json()}\n```"
        client = _make_client_mock(fenced)
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.verdict is not None


# ---------------------------------------------------------------------------
# call() — retry on first parse failure, success on second
# ---------------------------------------------------------------------------
class TestCallRetry:
    def test_success_on_attempt_2(self, tmp_path):
        bundle = _make_bundle()
        # First response: not valid JSON; second: good
        msg1 = MagicMock()
        msg1.content = [MagicMock(text="not json at all")]
        msg2 = MagicMock()
        msg2.content = [MagicMock(text=_good_verdict_json())]
        client = MagicMock()
        client.messages.create.side_effect = [msg1, msg2]
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.verdict is not None
        assert result.attempt_count == 2
        assert result.escalated is False

    def test_warning_recorded_on_first_fail(self, tmp_path):
        bundle = _make_bundle()
        msg1 = MagicMock()
        msg1.content = [MagicMock(text="garbage")]
        msg2 = MagicMock()
        msg2.content = [MagicMock(text=_good_verdict_json())]
        client = MagicMock()
        client.messages.create.side_effect = [msg1, msg2]
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert len(result.warnings) >= 1

    def test_verdict_file_written_on_attempt_2(self, tmp_path):
        bundle = _make_bundle()
        msg1 = MagicMock()
        msg1.content = [MagicMock(text="bad")]
        msg2 = MagicMock()
        msg2.content = [MagicMock(text=_good_verdict_json())]
        client = MagicMock()
        client.messages.create.side_effect = [msg1, msg2]
        vpath = tmp_path / "verdict.json"
        call(bundle, _client=client,
             verdict_path=vpath,
             escalation_path=tmp_path / "esc.json",
             config={})
        assert vpath.exists()

    def test_invalid_schema_triggers_retry(self, tmp_path):
        bundle = _make_bundle()
        # First response: JSON but wrong schema (missing fields)
        bad_json = json.dumps({"schema_version": "v1", "trace_id": "x"})
        msg1 = MagicMock()
        msg1.content = [MagicMock(text=bad_json)]
        msg2 = MagicMock()
        msg2.content = [MagicMock(text=_good_verdict_json())]
        client = MagicMock()
        client.messages.create.side_effect = [msg1, msg2]
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.attempt_count == 2
        assert result.verdict is not None


# ---------------------------------------------------------------------------
# call() — escalation on both failures
# ---------------------------------------------------------------------------
class TestCallEscalation:
    def test_escalated_true_on_both_fail(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock("not json at all")
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.escalated is True

    def test_verdict_none_on_escalation(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock("bad")
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.verdict is None

    def test_escalation_file_written(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock("bad")
        espath = tmp_path / "esc.json"
        call(bundle, _client=client,
             verdict_path=tmp_path / "verdict.json",
             escalation_path=espath,
             config={})
        assert espath.exists()

    def test_escalation_file_has_trace_id(self, tmp_path):
        bundle = _make_bundle(trace_id="orch_20260407_abc")
        client = _make_client_mock("not json")
        espath = tmp_path / "esc.json"
        call(bundle, _client=client,
             verdict_path=tmp_path / "verdict.json",
             escalation_path=espath,
             config={})
        data = json.loads(espath.read_text())
        assert data["trace_id"] == "orch_20260407_abc"

    def test_escalation_file_has_idempotency_key(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock("not json")
        espath = tmp_path / "esc.json"
        call(bundle, _client=client,
             verdict_path=tmp_path / "verdict.json",
             escalation_path=espath,
             config={})
        data = json.loads(espath.read_text())
        assert "idempotency_key" in data

    def test_escalation_reason_in_result(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock("not json")
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert len(result.escalation_reason) > 0

    def test_no_verdict_file_on_escalation(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock("not json")
        vpath = tmp_path / "verdict.json"
        call(bundle, _client=client,
             verdict_path=vpath,
             escalation_path=tmp_path / "esc.json",
             config={})
        assert not vpath.exists()

    def test_api_exception_triggers_escalation(self, tmp_path):
        bundle = _make_bundle()
        client = MagicMock()
        client.messages.create.side_effect = Exception("network error")
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.escalated is True
        assert result.verdict is None

    def test_attempt_count_2_on_escalation(self, tmp_path):
        bundle = _make_bundle()
        client = _make_client_mock("bad json")
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.attempt_count == 2


# ---------------------------------------------------------------------------
# call() — missing API key
# ---------------------------------------------------------------------------
class TestCallMissingKey:
    def test_missing_key_escalates(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Also block .env.auditors fallback
        monkeypatch.setattr("advisor.dotenv_values", lambda *a, **kw: {}, raising=False)
        import advisor as _adv
        monkeypatch.setattr(_adv, "ROOT", tmp_path)  # no .env.auditors at tmp_path
        bundle = _make_bundle()
        result = call(bundle,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.escalated is True
        assert result.verdict is None

    def test_missing_key_warning_mentions_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        import advisor as _adv
        monkeypatch.setattr(_adv, "ROOT", tmp_path)  # no .env.auditors at tmp_path
        bundle = _make_bundle()
        result = call(bundle,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert any("key" in w.lower() or "ANTHROPIC" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# call() — issued_at auto-populated when absent
# ---------------------------------------------------------------------------
class TestCallIssuedAt:
    def test_issued_at_added_when_missing(self, tmp_path):
        bundle = _make_bundle()
        verdict_without_ts = json.dumps({
            "schema_version": "v1",
            "trace_id": "orch_test",
            "risk_assessment": "LOW",
            "governance_route": "none",
            "rationale": "ok",
            "next_step": "do it",
            "scope": [],
            "issued_at": "",
        })
        client = _make_client_mock(verdict_without_ts)
        result = call(bundle, _client=client,
                      verdict_path=tmp_path / "verdict.json",
                      escalation_path=tmp_path / "esc.json",
                      config={})
        assert result.verdict is not None
        assert result.verdict.issued_at != ""


# ---------------------------------------------------------------------------
# _build_full_user_prompt
# ---------------------------------------------------------------------------
class TestBuildFullUserPrompt:
    def test_calls_to_advisor_prompt_context(self):
        bundle = _make_bundle(sprint_goal="my goal")
        prompt = _build_full_user_prompt(bundle)
        assert "my goal" in prompt

    def test_returns_string(self):
        bundle = _make_bundle()
        assert isinstance(_build_full_user_prompt(bundle), str)

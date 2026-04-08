"""
test_model_selection.py — deterministic tests for advisor model selection logic.

trace_id: orch_20260408T191109Z_4fb5b2
idempotency_key: test_model_selection_v1

Covers:
  (a) Default model selection with no special context
  (b) Model override based on task complexity (risk level)
  (c) Fallback model when preferred model is unavailable (config missing/empty)

All tests are deterministic — no external I/O, no randomness, no live API.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from advisor import (
    _select_model,
    call,
    DEFAULT_MODEL,
    OPUS_MODEL,
    _OPUS_RISK_LEVELS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bundle(risk_assessment="LOW", trace_id="orch_20260408T191109Z_4fb5b2"):
    b = MagicMock()
    b.sprint_goal = "Test model selection"
    b.task_id = "TEST-ADVISOR-MODEL-SELECTION"
    b.trace_id = trace_id
    b.risk_assessment = risk_assessment
    b.to_advisor_prompt_context.return_value = (
        f"## Sprint Goal\nTest model selection\n\n## Current Task\ntask_id: TEST-ADVISOR-MODEL-SELECTION"
    )
    return b


def _good_verdict_json(trace_id="orch_20260408T191109Z_4fb5b2") -> str:
    return json.dumps({
        "schema_version": "v1",
        "trace_id": trace_id,
        "risk_assessment": "LOW",
        "governance_route": "none",
        "rationale": "Test verdict.",
        "next_step": "Done.",
        "scope": [],
        "issued_at": "2026-04-08T19:11:16+00:00",
    })


def _make_client_mock(response_text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


# ---------------------------------------------------------------------------
# (a) Default model selection — no special context / config
# ---------------------------------------------------------------------------
class TestDefaultModelSelection:
    """When no config override and no models.yaml, _select_model uses hardcoded defaults."""

    def test_low_risk_selects_sonnet_by_default(self):
        assert _select_model("LOW", {}) == DEFAULT_MODEL

    def test_empty_risk_selects_sonnet(self):
        assert _select_model("", {}) == DEFAULT_MODEL

    def test_none_risk_selects_sonnet(self):
        assert _select_model(None, {}) == DEFAULT_MODEL

    def test_default_model_is_sonnet(self):
        assert "sonnet" in DEFAULT_MODEL

    def test_opus_model_is_opus(self):
        assert "opus" in OPUS_MODEL

    def test_default_with_empty_config(self):
        """Empty config dict should not override default selection."""
        assert _select_model("LOW", {}) == DEFAULT_MODEL

    def test_default_with_none_advisor_model(self):
        """Config with advisor_model=None should not override."""
        assert _select_model("LOW", {"advisor_model": None}) == DEFAULT_MODEL

    def test_default_with_empty_advisor_model(self):
        """Config with advisor_model='' should not override."""
        assert _select_model("LOW", {"advisor_model": ""}) == DEFAULT_MODEL


# ---------------------------------------------------------------------------
# (b) Model override based on task complexity (risk level)
# ---------------------------------------------------------------------------
class TestRiskBasedModelSelection:
    """SEMI/CORE risk → Opus; LOW → Sonnet. Config override wins over risk."""

    def test_semi_risk_selects_opus(self):
        assert _select_model("SEMI", {}) == OPUS_MODEL

    def test_core_risk_selects_opus(self):
        assert _select_model("CORE", {}) == OPUS_MODEL

    def test_low_risk_selects_sonnet(self):
        assert _select_model("LOW", {}) == DEFAULT_MODEL

    def test_lowercase_semi_selects_opus(self):
        assert _select_model("semi", {}) == OPUS_MODEL

    def test_lowercase_core_selects_opus(self):
        assert _select_model("core", {}) == OPUS_MODEL

    def test_lowercase_low_selects_sonnet(self):
        assert _select_model("low", {}) == DEFAULT_MODEL

    def test_opus_risk_levels_set(self):
        """Verify the _OPUS_RISK_LEVELS constant is correct."""
        assert _OPUS_RISK_LEVELS == {"SEMI", "CORE"}

    def test_config_advisor_model_overrides_risk(self):
        """Explicit advisor_model in config takes precedence over risk-based logic."""
        override = "claude-haiku-4-5-20251001"
        assert _select_model("CORE", {"advisor_model": override}) == override
        assert _select_model("LOW", {"advisor_model": override}) == override
        assert _select_model("SEMI", {"advisor_model": override}) == override

    @pytest.mark.parametrize("risk,expected_keyword", [
        ("LOW", "sonnet"),
        ("SEMI", "opus"),
        ("CORE", "opus"),
    ])
    def test_parametrized_risk_to_model(self, risk, expected_keyword):
        model = _select_model(risk, {})
        assert expected_keyword in model


# ---------------------------------------------------------------------------
# (c) Fallback model when preferred model is unavailable
# ---------------------------------------------------------------------------
class TestFallbackModelSelection:
    """When models.yaml is missing or malformed, _select_model falls back to hardcoded defaults."""

    @patch("advisor._load_models_config", return_value={})
    def test_fallback_low_when_models_yaml_empty(self, _mock):
        assert _select_model("LOW", {}) == DEFAULT_MODEL

    @patch("advisor._load_models_config", return_value={})
    def test_fallback_semi_when_models_yaml_empty(self, _mock):
        assert _select_model("SEMI", {}) == OPUS_MODEL

    @patch("advisor._load_models_config", return_value={})
    def test_fallback_core_when_models_yaml_empty(self, _mock):
        assert _select_model("CORE", {}) == OPUS_MODEL

    @patch("advisor._load_models_config", return_value={"builder": {}})
    def test_fallback_when_builder_has_no_keys(self, _mock):
        """builder section exists but has no default/escalation keys."""
        assert _select_model("LOW", {}) == DEFAULT_MODEL
        assert _select_model("CORE", {}) == OPUS_MODEL

    @patch("advisor._load_models_config", return_value={"builder": {"default": "sonnet", "escalation": "opus"}})
    def test_short_names_map_to_full_ids(self, _mock):
        """Short names 'sonnet'/'opus' in models.yaml map to full API model IDs."""
        assert _select_model("LOW", {}) == DEFAULT_MODEL
        assert _select_model("CORE", {}) == OPUS_MODEL

    @patch("advisor._load_models_config", return_value={"builder": {"default": "custom-model-v1", "escalation": "custom-model-v2"}})
    def test_custom_model_names_passed_through(self, _mock):
        """Non-standard model names from models.yaml are returned as-is."""
        assert _select_model("LOW", {}) == "custom-model-v1"
        assert _select_model("CORE", {}) == "custom-model-v2"


# ---------------------------------------------------------------------------
# Integration: model selection through call()
# ---------------------------------------------------------------------------
class TestModelSelectionInCallIntegration:
    """Verify that call() passes the correct model to the API client."""

    def _get_model_from_call(self, client):
        kwargs = client.messages.create.call_args.kwargs
        return kwargs.get("model", client.messages.create.call_args[1].get("model", ""))

    def test_call_low_risk_uses_sonnet(self, tmp_path):
        bundle = _make_bundle(risk_assessment="LOW")
        client = _make_client_mock(_good_verdict_json())
        call(bundle, _client=client,
             verdict_path=tmp_path / "v.json",
             escalation_path=tmp_path / "e.json",
             config={})
        assert "sonnet" in self._get_model_from_call(client)

    def test_call_semi_risk_uses_opus(self, tmp_path):
        bundle = _make_bundle(risk_assessment="SEMI")
        client = _make_client_mock(_good_verdict_json())
        call(bundle, _client=client,
             verdict_path=tmp_path / "v.json",
             escalation_path=tmp_path / "e.json",
             config={})
        assert "opus" in self._get_model_from_call(client)

    def test_call_core_risk_uses_opus(self, tmp_path):
        bundle = _make_bundle(risk_assessment="CORE")
        client = _make_client_mock(_good_verdict_json())
        call(bundle, _client=client,
             verdict_path=tmp_path / "v.json",
             escalation_path=tmp_path / "e.json",
             config={})
        assert "opus" in self._get_model_from_call(client)

    def test_call_config_override_used(self, tmp_path):
        bundle = _make_bundle(risk_assessment="CORE")
        client = _make_client_mock(_good_verdict_json())
        call(bundle, _client=client,
             verdict_path=tmp_path / "v.json",
             escalation_path=tmp_path / "e.json",
             config={"advisor_model": "claude-haiku-4-5-20251001"})
        assert "haiku" in self._get_model_from_call(client)

    def test_call_no_risk_attr_defaults_sonnet(self, tmp_path):
        bundle = _make_bundle()
        if hasattr(bundle, "risk_assessment"):
            del bundle.risk_assessment
        client = _make_client_mock(_good_verdict_json())
        call(bundle, _client=client,
             verdict_path=tmp_path / "v.json",
             escalation_path=tmp_path / "e.json",
             config={})
        assert "sonnet" in self._get_model_from_call(client)

"""Tests for the shadow-mode GPT-5.4 verifier layer."""
import os
import sys

import pytest

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from catalog_shadow_runtime import activate_shadow_runtime, get_shadow_runtime_summary, reset_shadow_runtime
from catalog_verifier import (
    build_verifier_evidence_packet,
    build_verifier_request,
    build_verifier_shadow_record,
    get_verifier_runtime_config,
    load_verifier_input_schema,
    load_verifier_output_schema,
    load_verifier_policy,
    parse_verifier_output,
    route_bundle_to_verifier,
)


@pytest.fixture(autouse=True)
def _reset_shadow_runtime_state():
    reset_shadow_runtime()
    yield
    reset_shadow_runtime()


def _make_bundle(**overrides):
    bundle = {
        "generated_at": "2026-03-26T00:00:00Z",
        "pn": "00020211",
        "name": "Temperature Sensor",
        "assembled_title": "Honeywell 00020211 Temperature Sensor",
        "policy_decision_v2": {
            "decision_id": "dec_00020211",
            "policy_version": "catalog_evidence_policy_v1",
            "family_photo_policy_version": "family_photo_policy_v1",
            "source_matrix_version": "source_role_field_matrix_v1",
            "review_schema_version": "review_reason_schema_v1",
            "identity_level": "weak",
            "title_status": "ACCEPTED",
            "image_status": "REVIEW_REQUIRED",
            "price_status": "REVIEW_REQUIRED",
            "pdf_status": "REVIEW_REQUIRED",
            "card_status": "DRAFT_ONLY",
            "review_reasons": [
                {
                    "reason_code": "IDENTITY_WEAK",
                    "field": "identity",
                    "severity": "WARNING",
                    "candidate_ids": ["cand_title_1"],
                    "evidence_ids": ["ev_title_1"],
                    "policy_rule_id": "CAP-09",
                    "bucket": "IDENTITY_CONFLICT"
                },
                {
                    "reason_code": "PRICE_ROLE_NOT_ADMISSIBLE",
                    "field": "price",
                    "severity": "WARNING",
                    "candidate_ids": ["cand_price_1"],
                    "evidence_ids": ["ev_price_1"],
                    "policy_rule_id": "CAP-09",
                    "bucket": "PRICE_AMBIGUITY"
                }
            ],
            "review_buckets": ["IDENTITY_CONFLICT", "PRICE_AMBIGUITY"],
            "policy_rule_id": "CAP-09"
        },
        "structured_identity": {
            "exact_jsonld_pn_match": False,
            "exact_title_pn_match": False,
            "exact_h1_pn_match": False,
            "exact_product_context_pn_match": False,
            "exact_structured_pn_match": False,
            "structured_pn_match_location": ""
        },
        "photo": {
            "verdict": "KEEP",
            "stock_photo_flag": False,
            "mpn_confirmed_via_jsonld": False
        },
        "price": {
            "price_status": "public_price",
            "source_tier": "authorized",
            "page_product_class": "product",
            "category_mismatch": False,
            "brand_mismatch": False
        },
        "datasheet": {
            "datasheet_status": "found",
            "pdf_exact_pn_confirmed": False,
            "pn_confirmed_in_pdf": False,
            "pdf_source_tier": "authorized"
        }
    }
    for key, value in overrides.items():
        bundle[key] = value
    return bundle


class DummyResponse:
    def __init__(self, output_text, usage=None, request_id="req_test"):
        self.output_text = output_text
        self.usage = usage or {
            "input_tokens": 100,
            "output_tokens": 50,
            "reasoning_tokens": 25
        }
        self._request_id = request_id


class DummyClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.responses = self

    def create(self, **_kwargs):
        self.calls += 1
        if not self._responses:
            raise AssertionError("unexpected verifier call")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_policy_declares_gpt54_and_shadow_default():
    policy = load_verifier_policy()
    assert policy["primary_model_target"] == "gpt-5.4"
    assert policy["responses_api_required"] is True
    assert policy["shadow_mode_default"] is True


def test_route_identity_and_price_risk_to_verifier():
    route = route_bundle_to_verifier(_make_bundle())
    assert route["should_route"] is True
    assert "IDENTITY_NOT_STRONG" in route["trigger_codes"]
    assert "PRICE_REVIEW_REQUIRED" in route["trigger_codes"]
    assert "PDF_REVIEW_REQUIRED" in route["trigger_codes"]
    assert "AMBIGUOUS_EXACTNESS" in route["trigger_codes"]


def test_packet_assembly_contains_versions_and_structured_identity():
    route = route_bundle_to_verifier(_make_bundle())
    packet = build_verifier_evidence_packet(_make_bundle(), route_decision=route)
    assert packet["schema_version"] == "catalog_verifier_input_schema_v1"
    assert packet["policy_versions"]["policy_version"] == "catalog_evidence_policy_v1"
    assert packet["policy_versions"]["review_schema_version"] == "review_reason_schema_v1"
    assert packet["structured_identity"]["exact_structured_pn_match"] is False
    assert packet["risk_reason_codes"] == route["trigger_codes"]
    assert packet["idempotency_key"].startswith("catalog_verifier:00020211:")


def test_no_call_when_feature_flag_off(monkeypatch):
    monkeypatch.delenv("CATALOG_VERIFIER_ENABLED", raising=False)
    client = DummyClient([])
    record = build_verifier_shadow_record(_make_bundle(), client=client)
    assert record["call_state"] == "feature_flag_off"
    assert client.calls == 0
    assert record["decision_merger"]["decision_effect"] == "none"


def test_shadow_mode_call_parses_structured_output(monkeypatch):
    monkeypatch.setenv("CATALOG_VERIFIER_ENABLED", "1")
    monkeypatch.setenv("CATALOG_VERIFIER_MODE", "shadow")
    client = DummyClient(
        [
            DummyResponse(
                output_text=(
                    '{"verifier_model":"gpt-5.4","verifier_version":"catalog_verifier_prompt_v1",'
                    '"verdict":"CONFIRM_REVIEW","confidence":0.83,'
                    '"rationale_short":"Identity remains ambiguous.",'
                    '"blocking_reason_codes":["IDENTITY_NOT_STRONG"],'
                    '"suggested_action":"ROUTE_TO_REVIEW",'
                    '"suggested_review_bucket":"IDENTITY_CONFLICT",'
                    '"evidence_sufficiency":"PARTIAL",'
                    '"contradictions_found":[],'
                    '"safe_to_autopublish":false}'
                )
            )
        ]
    )
    record = build_verifier_shadow_record(_make_bundle(), client=client)
    assert record["call_state"] == "completed"
    assert record["response"]["verdict"] == "CONFIRM_REVIEW"
    assert record["decision_merger"]["effective_card_status"] == "DRAFT_ONLY"
    assert record["decision_merger"]["allow_auto_publish_unlock"] is False
    assert client.calls == 1


def test_retry_guard_keeps_same_idempotency_key(monkeypatch):
    monkeypatch.setenv("CATALOG_VERIFIER_ENABLED", "1")
    monkeypatch.setenv("CATALOG_VERIFIER_MODE", "shadow")
    monkeypatch.setattr("catalog_verifier.time.sleep", lambda *_args, **_kwargs: None)
    client = DummyClient(
        [
            RuntimeError("temporary"),
            DummyResponse(
                output_text=(
                    '{"verifier_model":"gpt-5.4","verifier_version":"catalog_verifier_prompt_v1",'
                    '"verdict":"CONFIRM_DRAFT","confidence":0.71,'
                    '"rationale_short":"Still weak identity.",'
                    '"blocking_reason_codes":["IDENTITY_NOT_STRONG"],'
                    '"suggested_action":"KEEP_DETERMINISTIC_DECISION",'
                    '"suggested_review_bucket":"IDENTITY_CONFLICT",'
                    '"evidence_sufficiency":"PARTIAL",'
                    '"contradictions_found":[],'
                    '"safe_to_autopublish":false}'
                )
            )
        ]
    )
    first = build_verifier_shadow_record(_make_bundle(), client=client)
    second = build_verifier_shadow_record(_make_bundle(), client=DummyClient([]))
    assert first["call_state"] == "completed"
    assert first["idempotency_key"] == second["idempotency_key"]


def test_parse_output_rejects_missing_fields():
    with pytest.raises(ValueError):
        parse_verifier_output({"output_text": '{"verdict":"CONFIRM_REVIEW"}'})


def test_input_and_output_schemas_are_explicit():
    input_schema = load_verifier_input_schema()
    output_schema = load_verifier_output_schema()
    assert "policy_versions" in input_schema["required"]
    assert "safe_to_autopublish" in output_schema["required"]


def test_runtime_config_defaults_to_high_reasoning(monkeypatch):
    monkeypatch.delenv("CATALOG_VERIFIER_REASONING_EFFORT", raising=False)
    runtime = get_verifier_runtime_config()
    assert runtime["model"] == "gpt-5.4"
    assert runtime["reasoning_effort"] == "high"
    assert runtime["responses_api_only"] is True


def test_gpt54_request_omits_temperature():
    bundle = _make_bundle()
    route = route_bundle_to_verifier(bundle)
    packet = build_verifier_evidence_packet(bundle, route_decision=route)
    request = build_verifier_request(packet)
    assert "temperature" not in request
    assert request["metadata"]["transport"] == "responses_api"


def test_verifier_shadow_runtime_counts_responses_only(monkeypatch):
    monkeypatch.setenv("CATALOG_VERIFIER_ENABLED", "1")
    monkeypatch.setenv("CATALOG_VERIFIER_MODE", "shadow")
    reset_shadow_runtime()
    activate_shadow_runtime(run_manifest_id="batch-shadow", planned_skus=1)
    client = DummyClient(
        [
            DummyResponse(
                output_text=(
                    '{"verifier_model":"gpt-5.4","verifier_version":"catalog_verifier_prompt_v1",'
                    '"verdict":"CONFIRM_REVIEW","confidence":0.83,'
                    '"rationale_short":"Identity remains ambiguous.",'
                    '"blocking_reason_codes":["IDENTITY_NOT_STRONG"],'
                    '"suggested_action":"ROUTE_TO_REVIEW",'
                    '"suggested_review_bucket":"IDENTITY_CONFLICT",'
                    '"evidence_sufficiency":"PARTIAL",'
                    '"contradictions_found":[],' 
                    '"safe_to_autopublish":false}'
                )
            )
        ]
    )
    record = build_verifier_shadow_record(_make_bundle(), client=client)
    summary = get_shadow_runtime_summary()
    assert record["transport"] == "responses_api"
    assert summary["responses_calls"] == 1
    assert summary["chat_completions_calls_verifier"] == 0


def test_search_hints_are_not_promoted_into_packet_proof():
    bundle = _make_bundle(
        structured_identity={
            "exact_jsonld_pn_match": False,
            "exact_title_pn_match": False,
            "exact_h1_pn_match": False,
            "exact_product_context_pn_match": False,
            "exact_structured_pn_match": False,
            "structured_pn_match_location": "",
            "search_hint": "00020211"
        }
    )
    packet = build_verifier_evidence_packet(
        bundle,
        route_decision=route_bundle_to_verifier(bundle),
    )
    assert packet["structured_identity"]["exact_structured_pn_match"] is False
    assert packet["risk_reason_codes"]

"""Shadow-mode GPT-5.4 verifier layer for Phase A catalog enrichment."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

from catalog_shadow_runtime import allow_verifier_call, record_verifier_call

_CONFIG_DIR = Path(__file__).parent.parent / "config"
_POLICY_PATH = _CONFIG_DIR / "catalog_verifier_policy_v1.json"
_INPUT_SCHEMA_PATH = _CONFIG_DIR / "catalog_verifier_input_schema_v1.json"
_OUTPUT_SCHEMA_PATH = _CONFIG_DIR / "catalog_verifier_output_schema_v1.json"

_cache: dict[str, dict] = {}
_AMBIGUOUS_REASON_CODES = {
    "IMAGE_UNKNOWN",
    "PDF_NOT_EXACT_CONFIRMED",
    "PRICE_ROLE_NOT_ADMISSIBLE",
}
_VALID_MODES = {"shadow"}


def _load_json(path: Path) -> dict:
    key = str(path)
    if key not in _cache:
        with open(path, encoding="utf-8") as f:
            _cache[key] = json.load(f)
    return dict(_cache[key])


def load_verifier_policy() -> dict:
    return _load_json(_POLICY_PATH)


def load_verifier_input_schema() -> dict:
    return _load_json(_INPUT_SCHEMA_PATH)


def load_verifier_output_schema() -> dict:
    return _load_json(_OUTPUT_SCHEMA_PATH)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def get_verifier_runtime_config() -> dict:
    policy = load_verifier_policy()
    requested_mode = str(
        os.getenv(
            policy["feature_flags"]["mode_env"],
            policy["decision_merger"]["default_mode"],
        )
    ).strip().lower()
    effective_mode = requested_mode if requested_mode in _VALID_MODES else "shadow"
    return {
        "enabled": _env_flag(policy["feature_flags"]["enabled_env"], False),
        "responses_api_only": bool(policy["responses_api_required"]),
        "requested_mode": requested_mode,
        "mode": effective_mode,
        "mode_override": requested_mode not in _VALID_MODES,
        "model": str(
            os.getenv("CATALOG_VERIFIER_MODEL", policy["runtime_defaults"]["model"])
        ).strip() or policy["runtime_defaults"]["model"],
        "reasoning_effort": str(
            os.getenv(
                "CATALOG_VERIFIER_REASONING_EFFORT",
                policy["runtime_defaults"]["reasoning_effort"],
            )
        ).strip() or policy["runtime_defaults"]["reasoning_effort"],
        "timeout_seconds": _env_int(
            "CATALOG_VERIFIER_TIMEOUT_SECONDS",
            policy["runtime_defaults"]["timeout_seconds"],
        ),
        "max_retries": _env_int(
            "CATALOG_VERIFIER_MAX_RETRIES",
            policy["runtime_defaults"]["max_retries"],
        ),
        "store": _env_flag(
            "CATALOG_VERIFIER_STORE", policy["runtime_defaults"]["store"]
        ),
        "base_url": str(os.getenv("OPENAI_BASE_URL", "")).strip(),
        "input_cost_per_1m": _env_float(
            "CATALOG_VERIFIER_INPUT_COST_PER_1M",
            float(policy["runtime_defaults"]["input_cost_per_1m"]),
        ),
        "output_cost_per_1m": _env_float(
            "CATALOG_VERIFIER_OUTPUT_COST_PER_1M",
            float(policy["runtime_defaults"]["output_cost_per_1m"]),
        ),
    }


def route_bundle_to_verifier(
    bundle: dict,
    *,
    prepublish_high_value: bool = False,
    batch_audit_sample: bool = False,
) -> dict:
    decision = bundle["policy_decision_v2"]
    reason_codes = {row["reason_code"] for row in decision.get("review_reasons", [])}
    buckets = set(decision.get("review_buckets", []))
    triggers: list[str] = []

    if decision["identity_level"] != "strong":
        triggers.append("IDENTITY_NOT_STRONG")
    if decision["price_status"] == "REVIEW_REQUIRED":
        triggers.append("PRICE_REVIEW_REQUIRED")
    if decision["pdf_status"] == "REVIEW_REQUIRED":
        triggers.append("PDF_REVIEW_REQUIRED")
    if "FAMILY_PHOTO_POLICY_REVIEW" in reason_codes:
        triggers.append("FAMILY_PHOTO_ONLY")
    if "MANUAL_POLICY_EXCEPTION" in buckets or "CRITICAL_MISMATCH" in reason_codes:
        triggers.append("CRITICAL_POLICY_CONFLICT")
    if reason_codes & _AMBIGUOUS_REASON_CODES:
        triggers.append("AMBIGUOUS_EXACTNESS")
    if prepublish_high_value:
        triggers.append("PREPUBLISH_HIGH_VALUE")
    if batch_audit_sample:
        triggers.append("BATCH_AUDIT_SAMPLE")

    return {
        "should_route": bool(triggers),
        "trigger_codes": sorted(set(triggers)),
        "deterministic_card_status": decision["card_status"],
        "deterministic_identity_level": decision["identity_level"],
    }


def build_verifier_trace_id(bundle: dict) -> str:
    return f"catalog_verifier:{bundle.get('pn', '')}:{bundle.get('generated_at', '')}"


def build_verifier_idempotency_key(packet: dict) -> str:
    payload = {
        "pn_primary": packet["pn_primary"],
        "trace_id": packet["trace_id"],
        "risk_reason_codes": packet["risk_reason_codes"],
        "card_status": packet["card_status"],
        "policy_versions": packet["policy_versions"],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    return f"catalog_verifier:{packet['pn_primary']}:{digest}"


def build_verifier_evidence_packet(
    bundle: dict,
    *,
    route_decision: Optional[dict] = None,
    trace_id: str = "",
    idempotency_key: str = "",
) -> dict:
    schema = load_verifier_input_schema()
    decision = bundle["policy_decision_v2"]
    packet = {
        "schema_version": schema["schema_version"],
        "trace_id": trace_id or build_verifier_trace_id(bundle),
        "idempotency_key": idempotency_key or "",
        "pn_primary": bundle["pn"],
        "normalized_title": bundle.get("assembled_title") or bundle.get("name") or "",
        "card_status": decision["card_status"],
        "field_statuses": {
            "title_status": decision["title_status"],
            "image_status": decision["image_status"],
            "price_status": decision["price_status"],
            "pdf_status": decision["pdf_status"],
        },
        "review_reasons": decision.get("review_reasons", []),
        "review_buckets": decision.get("review_buckets", []),
        "source_role_evidence_summary": {
            "title_source_role": "deterministic_title_assembly",
            "price_source_tier": bundle.get("price", {}).get("source_tier") or "",
            "pdf_source_tier": bundle.get("datasheet", {}).get("pdf_source_tier") or "",
            "image_source_tier": bundle.get("photo", {}).get("source_trust_tier")
            or bundle.get("price", {}).get("source_tier")
            or "",
        },
        "structured_identity": dict(bundle.get("structured_identity", {})),
        "pdf_evidence_summary": {
            "datasheet_status": bundle.get("datasheet", {}).get("datasheet_status", ""),
            "pdf_exact_pn_confirmed": bool(
                bundle.get("datasheet", {}).get("pdf_exact_pn_confirmed")
            ),
            "pn_confirmed_in_pdf": bool(
                bundle.get("datasheet", {}).get("pn_confirmed_in_pdf")
            ),
            "pdf_source_tier": bundle.get("datasheet", {}).get("pdf_source_tier", ""),
        },
        "image_evidence_summary": {
            "photo_verdict": bundle.get("photo", {}).get("verdict", ""),
            "stock_photo_flag": bool(bundle.get("photo", {}).get("stock_photo_flag")),
            "mpn_confirmed_via_jsonld": bool(
                bundle.get("photo", {}).get("mpn_confirmed_via_jsonld")
            ),
        },
        "price_evidence_summary": {
            "price_status": bundle.get("price", {}).get("price_status", ""),
            "source_tier": bundle.get("price", {}).get("source_tier", ""),
            "page_product_class": bundle.get("price", {}).get("page_product_class", ""),
            "category_mismatch": bool(bundle.get("price", {}).get("category_mismatch")),
            "brand_mismatch": bool(bundle.get("price", {}).get("brand_mismatch")),
        },
        "policy_versions": {
            "policy_version": decision["policy_version"],
            "family_photo_policy_version": decision["family_photo_policy_version"],
            "source_matrix_version": decision["source_matrix_version"],
            "review_schema_version": decision["review_schema_version"],
        },
        "risk_reason_codes": list((route_decision or {}).get("trigger_codes", [])),
    }
    packet["idempotency_key"] = idempotency_key or build_verifier_idempotency_key(packet)
    return packet


def build_verifier_request(packet: dict, runtime_config: Optional[dict] = None) -> dict:
    runtime = runtime_config or get_verifier_runtime_config()
    output_schema = load_verifier_output_schema()
    request_schema = dict(output_schema)
    request_schema.pop("schema_version", None)
    return {
        "model": runtime["model"],
        "instructions": (
            "You are a catalog verification layer. Use only the provided evidence packet. "
            "Do not browse, do not infer unsupported facts, do not upgrade identity from "
            "search hints, CSV, supplier feed, pn_secondary, raw PDF text, raw PDF specs, "
            "raw PDF title, or raw PDF URL. Return strict JSON only."
        ),
        "input": json.dumps(packet, ensure_ascii=False),
        "reasoning": {"effort": runtime["reasoning_effort"]},
        "store": runtime["store"],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "catalog_verifier_output",
                "strict": True,
                "schema": request_schema,
            }
        },
        "metadata": {
            "trace_id": packet["trace_id"],
            "idempotency_key": packet["idempotency_key"],
            "pn_primary": packet["pn_primary"],
            "transport": "responses_api",
        },
        "extra_headers": {
            "X-Client-Request-Id": packet["trace_id"],
        },
        "timeout": runtime["timeout_seconds"],
    }


def parse_verifier_output(response_obj: Any) -> dict:
    if isinstance(response_obj, dict) and response_obj.get("parsed_output"):
        payload = response_obj["parsed_output"]
    else:
        output_parsed = getattr(response_obj, "output_parsed", None)
        if output_parsed:
            payload = output_parsed
        else:
            raw = ""
            if isinstance(response_obj, dict):
                raw = str(response_obj.get("output_text", "")).strip()
            else:
                raw = str(getattr(response_obj, "output_text", "")).strip()
            if not raw:
                raise ValueError("verifier output_text is empty")
            payload = json.loads(raw)

    schema = load_verifier_output_schema()
    missing = [field for field in schema["required"] if field not in payload]
    if missing:
        raise ValueError(f"verifier output missing required fields: {missing}")
    allowed_verdicts = set(schema["properties"]["verdict"]["enum"])
    if payload["verdict"] not in allowed_verdicts:
        raise ValueError(f"invalid verifier verdict: {payload['verdict']}")
    return payload


def _extract_usage(response_obj: Any, runtime_config: dict) -> dict:
    usage = getattr(response_obj, "usage", None)
    if usage is None and isinstance(response_obj, dict):
        usage = response_obj.get("usage")
    usage_dict = usage if isinstance(usage, dict) else {}
    input_tokens = int(usage_dict.get("input_tokens", 0) or 0)
    output_tokens = int(usage_dict.get("output_tokens", 0) or 0)
    reasoning_tokens = int(usage_dict.get("reasoning_tokens", 0) or 0)
    estimated_cost_usd = round(
        (input_tokens / 1_000_000.0) * runtime_config["input_cost_per_1m"]
        + (output_tokens / 1_000_000.0) * runtime_config["output_cost_per_1m"],
        6,
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "estimated_cost_usd": estimated_cost_usd,
    }


def call_verifier_with_retry(
    packet: dict,
    *,
    runtime_config: Optional[dict] = None,
    client: Any = None,
) -> dict:
    runtime = runtime_config or get_verifier_runtime_config()
    if client is None:
        if OpenAI is None:
            raise RuntimeError("openai package is not available")
        api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if runtime["base_url"]:
            kwargs["base_url"] = runtime["base_url"]
        client = OpenAI(**kwargs)

    request = build_verifier_request(packet, runtime)
    attempts_total = runtime["max_retries"] + 1
    last_error = ""
    for attempt in range(1, attempts_total + 1):
        call_started = time.monotonic()
        try:
            response = client.responses.create(
                model=request["model"],
                instructions=request["instructions"],
                input=request["input"],
                reasoning=request["reasoning"],
                store=request["store"],
                text=request["text"],
                metadata=request["metadata"],
                extra_headers=request["extra_headers"],
                timeout=request["timeout"],
            )
            parsed_output = parse_verifier_output(response)
            return {
                "call_state": "completed",
                "attempt_count": attempt,
                "request": request,
                "parsed_output": parsed_output,
                "usage": _extract_usage(response, runtime),
                "llm_request_id": getattr(response, "_request_id", ""),
                "latency_sec": round(time.monotonic() - call_started, 4),
            }
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt < attempts_total:
                time.sleep(min(attempt, 2))
                continue
    return {
        "call_state": "failed",
        "attempt_count": attempts_total,
        "request": request,
        "parsed_output": None,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost_usd": 0.0,
        },
        "llm_request_id": "",
        "error": last_error,
        "latency_sec": 0.0,
    }


def build_verifier_shadow_record(
    bundle: dict,
    *,
    prepublish_high_value: bool = False,
    batch_audit_sample: bool = False,
    client: Any = None,
    runtime_config: Optional[dict] = None,
) -> dict:
    policy = load_verifier_policy()
    runtime = runtime_config or get_verifier_runtime_config()
    route = route_bundle_to_verifier(
        bundle,
        prepublish_high_value=prepublish_high_value,
        batch_audit_sample=batch_audit_sample,
    )
    trace_id = build_verifier_trace_id(bundle)
    packet = build_verifier_evidence_packet(
        bundle,
        route_decision=route,
        trace_id=trace_id,
    )

    record = {
        "schema_version": "catalog_verifier_shadow_record_v1",
        "policy_version": policy["policy_version"],
        "mode": runtime["mode"],
        "feature_enabled": runtime["enabled"],
        "trace_id": trace_id,
        "idempotency_key": packet["idempotency_key"],
        "transport": "responses_api",
        "router": route,
        "decision_merger": {
            "final_decision_source": policy["decision_merger"]["final_decision_source"],
            "decision_effect": "none",
            "allow_auto_publish_unlock": False,
            "allow_verifier_override": False,
            "owner_approval_required_for_influence": True,
            "effective_card_status": bundle["policy_decision_v2"]["card_status"],
        },
        "packet": packet if route["should_route"] else None,
        "response": None,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost_usd": 0.0,
        },
        "call_state": "not_routed",
        "error": "",
        "llm_request_id": "",
    }

    if not route["should_route"]:
        return record
    if not runtime["enabled"]:
        record["call_state"] = "feature_flag_off"
        return record
    if runtime["mode"] != "shadow":
        record["call_state"] = "unsupported_mode"
        record["error"] = (
            f"catalog verifier v1 supports shadow mode only, got {runtime['mode']}"
        )
        return record
    allowed, reason = allow_verifier_call(bundle["pn"])
    if not allowed:
        record["call_state"] = "skipped_budget"
        record["error"] = reason
        return record

    result = call_verifier_with_retry(packet, runtime_config=runtime, client=client)
    record["call_state"] = result["call_state"]
    record["response"] = result["parsed_output"]
    record["usage"] = result["usage"]
    record["llm_request_id"] = result.get("llm_request_id", "")
    record["error"] = result.get("error", "")
    timed_out = "timeout" in record["error"].lower() or "timed out" in record["error"].lower()
    record_verifier_call(
        bundle["pn"],
        latency_sec=float(result.get("latency_sec", 0.0) or 0.0),
        timed_out=timed_out,
        success=record["call_state"] == "completed",
    )
    return record

"""Fail-closed external judge runner for SEMI / R1 evidence packs.

This script does not merge, edit code, rerun tests, or approve work by itself.
It assembles an evidence pack, calls an external OpenAI judge when allowed,
validates the structured verdict, and renders a short human verdict.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

from generate_continuity_index import DEFAULT_OUTPUT_PATH as DEFAULT_CONTINUITY_PATH
from generate_continuity_index import render_continuity_index


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA_PATH = REPO_ROOT / "config" / "judge_verdict_schema.json"
DEFAULT_SHADOW_LOGGING_SCHEMA_PATH = REPO_ROOT / "config" / "shadow_logging_record_schema_v0.json"
DEFAULT_STATE_PATH = REPO_ROOT / "docs" / "autopilot" / "STATE.md"
DEFAULT_ROADMAP_PATH = REPO_ROOT / "docs" / "EXECUTION_ROADMAP_v2_3.md"
DEFAULT_COMPLETED_LOG_PATH = REPO_ROOT / "docs" / "COMPLETED_LOG.md"
DEFAULT_SHADOW_LOG_DIR = REPO_ROOT / "shadow_log"
REDACTION_MARKER = "[REDACTED]"
_URL_CREDENTIALS_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+):([^@\s/]+)@")
_QUERY_SECRET_RE = re.compile(
    r"([?&](?:access_token|api_key|token|secret|password)=)([^&#\s]+)",
    re.IGNORECASE,
)
_TEXT_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r'(?im)(["\']?authorization["\']?\s*[:=]\s*["\']?(?:bearer|basic)\s+)([^"\'\s,}]+)'
        ),
        rf"\1{REDACTION_MARKER}",
    ),
    (
        re.compile(r'(?im)(["\']?x-api-key["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)'),
        rf"\1{REDACTION_MARKER}",
    ),
    (
        re.compile(
            r"(?im)\b([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|CLIENT_SECRET|ACCESS_TOKEN|REFRESH_TOKEN)[A-Z0-9_]*)\b(\s*=\s*)([^\s'\"`]+)"
        ),
        rf"\1\2{REDACTION_MARKER}",
    ),
    (
        re.compile(
            r'(?im)(["\']?[A-Za-z0-9_]*(?:api[_-]?key|client_secret|access_token|refresh_token|password|passwd|secret)["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)'
        ),
        rf"\1{REDACTION_MARKER}",
    ),
    (
        re.compile(r"\bsk-[^\s\"'`,}]{6,}"),
        REDACTION_MARKER,
    ),
]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_judge_verdict_schema(path: Path = DEFAULT_SCHEMA_PATH) -> dict[str, Any]:
    return _load_json(path)


def load_shadow_logging_schema(path: Path = DEFAULT_SHADOW_LOGGING_SCHEMA_PATH) -> dict[str, Any]:
    return _load_json(path)


def _redact_text(text: str) -> str:
    if not text:
        return text
    redacted = _URL_CREDENTIALS_RE.sub(rf"\1:{REDACTION_MARKER}@", text)
    redacted = _QUERY_SECRET_RE.sub(rf"\1{REDACTION_MARKER}", redacted)
    for pattern, replacement in _TEXT_SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_value(item) for key, item in value.items()}
    return value


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def get_judge_runtime_config() -> dict[str, Any]:
    return {
        "model": str(os.getenv("JUDGE_RUNNER_MODEL", "gpt-5.4")).strip() or "gpt-5.4",
        "reasoning_effort": str(os.getenv("JUDGE_RUNNER_REASONING_EFFORT", "high")).strip() or "high",
        "timeout_seconds": _env_int("JUDGE_RUNNER_TIMEOUT_SECONDS", 60),
        "store": _env_flag("JUDGE_RUNNER_STORE", False),
        "base_url": str(os.getenv("OPENAI_BASE_URL", "")).strip(),
        "max_retries": _env_int("JUDGE_RUNNER_MAX_RETRIES", 0),
    }


def _run_git(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _resolve_sha(explicit_sha: str | None) -> str:
    if explicit_sha:
        return explicit_sha.strip()
    return _run_git(["rev-parse", "HEAD"])


def _resolve_branch() -> str:
    return _run_git(["rev-parse", "--abbrev-ref", "HEAD"])


def _load_text(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _read_multiline_input(path: Path | None, inline_text: str | None) -> str:
    if path is not None:
        text = _load_text(path)
        if text:
            return text
    return str(inline_text or "").strip()


def _parse_test_log_summary(text: str) -> str:
    if not text.strip():
        return "missing test log"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    summary_patterns = [
        re.compile(r"=+ .*? (\d+ failed.*?) =+$", re.IGNORECASE),
        re.compile(r"=+ .*? (\d+ passed.*?) =+$", re.IGNORECASE),
        re.compile(r"PYTEST_EXIT_CODE=(\d+)"),
    ]
    for pattern in summary_patterns:
        for line in reversed(lines):
            match = pattern.search(line)
            if match:
                if pattern.pattern.startswith("PYTEST_EXIT_CODE"):
                    code = match.group(1)
                    return "pytest exit code 0" if code == "0" else f"pytest exit code {code}"
                return match.group(1)
    if any("failed" in line.lower() for line in lines):
        return "test log indicates failure"
    if any("passed" in line.lower() for line in lines):
        return "test log indicates pass"
    return "test summary unavailable"


def _changed_files_for_sha(sha: str) -> list[str]:
    files = [
        line.strip()
        for line in _run_git(["show", "--pretty=format:", "--name-only", sha]).splitlines()
        if line.strip()
    ]
    if files:
        return files
    status_lines = _run_git(["status", "--short"]).splitlines()
    parsed: list[str] = []
    for line in status_lines:
        entry = line[3:].strip() if len(line) > 3 else line.strip()
        if entry:
            parsed.append(entry)
    return parsed


def _render_changed_files_block(files: list[str]) -> str:
    if not files:
        return "- none detected"
    return "\n".join(f"- `{path}`" for path in files)


def _build_continuity_preview(generated_on: str) -> tuple[str, str]:
    preview = render_continuity_index(
        state_path=DEFAULT_STATE_PATH,
        roadmap_path=DEFAULT_ROADMAP_PATH,
        completed_log_path=DEFAULT_COMPLETED_LOG_PATH,
        generated_on=generated_on,
    )
    current = _load_text(DEFAULT_CONTINUITY_PATH)
    if not current:
        return preview, "Current file missing; preview only."
    if current == preview.strip():
        return preview, "No diff between current continuity artifact and preview."
    diff_lines = list(
        difflib.unified_diff(
            current.splitlines(),
            preview.splitlines(),
            fromfile="CONTINUITY_INDEX.current",
            tofile="CONTINUITY_INDEX.preview",
            lineterm="",
        )
    )
    return preview, "\n".join(diff_lines[:80]) if diff_lines else "Diff unavailable."


def _extract_section(markdown_text: str, heading: str) -> str:
    lines = markdown_text.splitlines()
    capture = False
    bucket: list[str] = []
    target = f"## {heading}"
    for line in lines:
        if line.strip() == target:
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture:
            bucket.append(line)
    text = "\n".join(bucket).strip()
    return text or "- none"


def _extract_conflict_lines(blockers_text: str) -> str:
    hits = []
    for line in blockers_text.splitlines():
        lowered = line.lower()
        if "roadmap" in lowered or "drift" in lowered or "conflict" in lowered:
            hits.append(line)
    return "\n".join(hits) if hits else "- none explicitly detected"


def _load_execution_status_summary(path: Path | None) -> str:
    payload = _load_execution_status_payload(path)
    if payload is None:
        return "not provided"
    if payload.get("parse_error"):
        source_ref = payload.get("source_ref") or (path.as_posix() if path is not None else "unknown")
        return f"unparseable status artifact: {source_ref}"
    status = str(payload.get("status", "UNKNOWN")).strip() or "UNKNOWN"
    retries = payload.get("retry_count", "n/a")
    heartbeat = payload.get("last_heartbeat_ts", "n/a")
    source_ref = str(payload.get("source_ref", path.as_posix() if path is not None else "unknown"))
    return f"status={status}; retry_count={retries}; last_heartbeat_ts={heartbeat}; source={source_ref}"


def _load_execution_status_payload(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    text = _load_text(path)
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {
            "status": "UNKNOWN",
            "retry_count": None,
            "attempt_count": None,
            "last_heartbeat_ts": None,
            "source_ref": _path_ref(path),
            "parse_error": True,
        }
    if not isinstance(payload, dict):
        return {
            "status": "UNKNOWN",
            "retry_count": None,
            "attempt_count": None,
            "last_heartbeat_ts": None,
            "source_ref": _path_ref(path),
            "parse_error": True,
        }
    sanitized = _sanitize_value(payload)
    sanitized["source_ref"] = _path_ref(path)
    sanitized["parse_error"] = False
    return sanitized


def _validate_pack_inputs(
    *,
    risk: str,
    scope: str,
    changed_files: list[str],
    test_log_text: str,
    continuity_preview: str,
    deferred_text: str,
) -> list[str]:
    missing: list[str] = []
    if risk not in {"LOW", "SEMI", "CORE"}:
        missing.append("risk must be one of LOW/SEMI/CORE")
    if not scope.strip():
        missing.append("scope is required")
    if not changed_files:
        missing.append("changed files could not be determined")
    if not test_log_text.strip():
        missing.append("test log is missing or empty")
    if not continuity_preview.strip():
        missing.append("continuity preview is missing")
    if not deferred_text.strip():
        missing.append("out-of-scope/deferred declaration is missing")
    return missing


def build_evidence_pack(
    *,
    risk: str,
    scope: str,
    sha: str,
    branch: str,
    changed_files: list[str],
    test_log_path: Path,
    test_log_text: str,
    continuity_preview: str,
    continuity_diff: str,
    unresolved_blockers: str,
    detected_conflicts: str,
    deferred_text: str,
    execution_status_summary: str,
    generated_on: str,
    pack_complete: bool,
    missing_fields: list[str],
) -> str:
    test_summary = _parse_test_log_summary(test_log_text)
    changed_files_block = _render_changed_files_block(changed_files)
    missing_block = "\n".join(f"- {item}" for item in missing_fields) if missing_fields else "- none"
    pack = "\n".join(
        [
            "# Evidence Pack",
            "",
            "Audience: external judge only. User must read only `human_verdict.md`.",
            "",
            "## Batch Metadata",
            "",
            f"- generated_on: `{generated_on}`",
            f"- risk: `{risk}`",
            f"- scope: `{scope}`",
            f"- sha: `{sha}`",
            f"- branch: `{branch}`",
            f"- pack_complete: `{str(pack_complete).lower()}`",
            "",
            "## Changed Files",
            "",
            changed_files_block,
            "",
            "## Tests Executed",
            "",
            f"- log_ref: `{test_log_path.as_posix()}`",
            f"- summary: `{test_summary}`",
            "",
            "## Raw Log Reference",
            "",
            f"- `{test_log_path.as_posix()}`",
            "",
            "## Execution Outcome Summary",
            "",
            f"- {execution_status_summary}",
            "",
            "## Continuity Artifact",
            "",
            "- `CONTINUITY_INDEX` is an artifact, not proof.",
            "",
            "### Continuity Preview",
            "",
            "```md",
            continuity_preview,
            "```",
            "",
            "### Continuity Diff",
            "",
            "```diff",
            continuity_diff,
            "```",
            "",
            "## Detected STATE/ROADMAP Conflicts",
            "",
            detected_conflicts,
            "",
            "## Unresolved Blockers",
            "",
            unresolved_blockers,
            "",
            "## Out-of-Scope / Deferred",
            "",
            deferred_text,
            "",
            "## Pack Completeness Check",
            "",
            missing_block,
            "",
            "## Recommendation Request For Judge",
            "",
            "Review scope boundary, changed files, test evidence, continuity artifact, conflicts, side-effect risk, and fail closed if evidence is incomplete or the structured output cannot be trusted.",
            "",
        ]
    )
    return _redact_text(pack)


def build_fallback_verdict(
    *,
    verdict: str,
    scope_summary: str,
    checks_summary: str,
    main_risk: str,
    required_fixes: list[str] | None = None,
    rationale_short: str,
) -> dict[str, Any]:
    return _sanitize_value(
        {
            "schema_version": "judge_verdict_schema_v1",
            "verdict": verdict,
            "scope_summary": scope_summary,
            "checks_summary": checks_summary,
            "main_risk": main_risk,
            "merge": "NO",
            "required_fixes": list(required_fixes or []),
            "manual_external_judge_required": True,
            "evidence_pack_complete": False,
            "unresolved_critical_risk": True,
            "rationale_short": rationale_short,
        }
    )


def validate_judge_verdict(payload: dict[str, Any], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = schema or load_judge_verdict_schema()
    required = spec["required"]
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"judge verdict missing required fields: {missing}")
    allowed_fields = set(spec["properties"])
    extra = sorted(set(payload) - allowed_fields)
    if extra:
        raise ValueError(f"judge verdict contains unexpected fields: {extra}")
    if payload.get("schema_version") != spec["properties"]["schema_version"]["const"]:
        raise ValueError("invalid judge verdict schema_version")
    for field in ("verdict", "merge"):
        allowed = set(spec["properties"][field]["enum"])
        if payload[field] not in allowed:
            raise ValueError(f"invalid {field}: {payload[field]}")
    for field in ("scope_summary", "checks_summary", "main_risk", "rationale_short"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
    if not isinstance(payload.get("required_fixes"), list):
        raise ValueError("required_fixes must be a list")
    for key in ("manual_external_judge_required", "evidence_pack_complete", "unresolved_critical_risk"):
        if not isinstance(payload.get(key), bool):
            raise ValueError(f"{key} must be boolean")
    if payload["verdict"] == "APPROVE":
        if payload["merge"] != "YES":
            raise ValueError("APPROVE verdict must set merge=YES")
        if payload["manual_external_judge_required"]:
            raise ValueError("APPROVE verdict cannot require manual external judge")
        if payload["unresolved_critical_risk"]:
            raise ValueError("APPROVE verdict cannot keep unresolved critical risk")
        if not payload["evidence_pack_complete"]:
            raise ValueError("APPROVE verdict requires complete evidence pack")
    return payload


def build_judge_request(
    *,
    evidence_pack: str,
    risk: str,
    sha: str,
    runtime_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime = runtime_config or get_judge_runtime_config()
    schema = load_judge_verdict_schema()
    return {
        "model": runtime["model"],
        "instructions": (
            "You are an external software delivery judge. "
            "You are not the executor. "
            "Read the evidence pack only. "
            "Treat CONTINUITY_INDEX as an artifact, not proof. "
            "Fail closed: if the pack is incomplete, the API context is insufficient, or risk remains unresolved, do not approve. "
            "Do not suggest merge automation. Return strict JSON only."
        ),
        "input": evidence_pack,
        "reasoning": {"effort": runtime["reasoning_effort"]},
        "store": runtime["store"],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "judge_verdict",
                "strict": True,
                "schema": schema,
            }
        },
        "metadata": {
            "sha": sha,
            "risk": risk,
            "artifact_type": "external_judge_verdict",
        },
        "timeout": runtime["timeout_seconds"],
    }


def _extract_usage(response_obj: Any) -> dict[str, Any]:
    usage = getattr(response_obj, "usage", None)
    if usage is None and isinstance(response_obj, dict):
        usage = response_obj.get("usage")
    if isinstance(usage, dict):
        return dict(usage)
    return {}


def _serialize_raw_response(response_obj: Any) -> dict[str, Any]:
    if isinstance(response_obj, dict):
        return _sanitize_value(
            {
                "output_text": response_obj.get("output_text", ""),
                "output_parsed": response_obj.get("parsed_output"),
                "usage": response_obj.get("usage", {}),
                "request_id": response_obj.get("openai_request_id", ""),
                "call_state": response_obj.get("call_state", ""),
                "error": response_obj.get("error", ""),
            }
        )
    return _sanitize_value(
        {
            "output_text": getattr(response_obj, "output_text", ""),
            "output_parsed": getattr(response_obj, "output_parsed", None),
            "usage": _extract_usage(response_obj),
            "request_id": getattr(response_obj, "_request_id", ""),
        }
    )


def parse_judge_output(response_obj: Any) -> dict[str, Any]:
    if isinstance(response_obj, dict) and response_obj.get("parsed_output") is not None:
        payload = response_obj["parsed_output"]
    else:
        output_parsed = getattr(response_obj, "output_parsed", None)
        if output_parsed is not None:
            payload = output_parsed
        else:
            raw = ""
            if isinstance(response_obj, dict):
                raw = str(response_obj.get("output_text", "")).strip()
            else:
                raw = str(getattr(response_obj, "output_text", "")).strip()
            if not raw:
                raise ValueError("judge output_text is empty")
            payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("judge output must be a JSON object")
    return validate_judge_verdict(_sanitize_value(payload))


def call_external_judge(
    *,
    evidence_pack: str,
    risk: str,
    sha: str,
    runtime_config: dict[str, Any] | None = None,
    client: Any = None,
) -> dict[str, Any]:
    runtime = runtime_config or get_judge_runtime_config()
    request = build_judge_request(
        evidence_pack=evidence_pack,
        risk=risk,
        sha=sha,
        runtime_config=runtime,
    )
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

    attempts_total = runtime["max_retries"] + 1
    last_error = ""
    for attempt in range(1, attempts_total + 1):
        started = time.monotonic()
        try:
            response = client.responses.create(
                model=request["model"],
                instructions=request["instructions"],
                input=request["input"],
                reasoning=request["reasoning"],
                store=request["store"],
                text=request["text"],
                metadata=request["metadata"],
                timeout=request["timeout"],
            )
            parsed = parse_judge_output(response)
            raw_response = _serialize_raw_response(response)
            raw_response["call_state"] = "completed"
            return {
                "call_state": "completed",
                "attempt_count": attempt,
                "request": request,
                "parsed_output": parsed,
                "raw_response": raw_response,
                "openai_request_id": getattr(response, "_request_id", ""),
                "usage": _extract_usage(response),
                "latency_sec": round(time.monotonic() - started, 4),
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
        "raw_response": {
            "call_state": "failed",
            "error": last_error,
        },
        "openai_request_id": "",
        "usage": {},
        "latency_sec": 0.0,
        "error": last_error,
    }


def render_human_verdict(verdict: dict[str, Any]) -> str:
    return _redact_text(
        "\n".join(
        [
            f"VERDICT: {verdict['verdict']}",
            f"SCOPE: {verdict['scope_summary']}",
            f"CHECKS: {verdict['checks_summary']}",
            f"MAIN RISK: {verdict['main_risk']}",
            f"MERGE: {verdict['merge']}",
        ]
        )
    ) + "\n"


def _path_ref(path: Path | None) -> str | None:
    if path is None:
        return None
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _stable_token(*parts: str) -> str:
    digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


def _default_shadow_log_dir(outdir: Path) -> Path:
    try:
        outdir.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return outdir.parent / "shadow_log"
    return DEFAULT_SHADOW_LOG_DIR


def _build_judge_shadow_identity(
    *,
    risk: str,
    scope: str,
    sha: str,
    outdir: Path,
    generated_on: str,
) -> dict[str, str]:
    scope_token = _stable_token(risk, sha, scope)
    run_token = outdir.name or _stable_token(outdir.as_posix(), generated_on)
    return {
        "scope_token": scope_token,
        "run_token": run_token,
        "trajectory_id": f"judge_trajectory:{sha[:12]}:{scope_token}",
        "run_id": f"judge_runner:{run_token}",
        "continuity_id": f"continuity:{generated_on}",
        "evidence_pack_id": f"evidence_pack:{run_token}",
        "status_id": f"status_event:{run_token}",
        "judge_verdict_id": f"judge_verdict:{run_token}",
        "human_verdict_id": f"human_verdict:{run_token}",
        "outcome_id": f"final_outcome:{run_token}",
        "request_id": f"judge_request:{scope_token}",
    }


def validate_shadow_logging_record(
    payload: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = schema or load_shadow_logging_schema()
    required = spec["required"]
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"shadow logging record missing required fields: {missing}")
    allowed_fields = set(spec["properties"])
    extra = sorted(set(payload) - allowed_fields)
    if extra:
        raise ValueError(f"shadow logging record contains unexpected fields: {extra}")
    if payload.get("schema_version") != spec["properties"]["schema_version"]["const"]:
        raise ValueError("invalid shadow logging record schema_version")
    for field in (
        "record_kind",
        "role",
        "risk",
        "final_outcome_label",
        "trajectory_quality_label",
        "redaction_status",
    ):
        allowed = set(spec["properties"][field]["enum"])
        if payload.get(field) not in allowed:
            raise ValueError(f"invalid {field}: {payload.get(field)}")
    run_status = payload.get("run_status")
    allowed_run_status = set(spec["properties"]["run_status"]["enum"])
    if run_status not in allowed_run_status:
        raise ValueError(f"invalid run_status: {run_status}")
    correction_type = payload.get("correction_type")
    allowed_correction = set(spec["properties"]["correction_type"]["enum"])
    if correction_type not in allowed_correction:
        raise ValueError(f"invalid correction_type: {correction_type}")
    label_source = payload.get("authoritative_label_source")
    allowed_sources = set(spec["properties"]["authoritative_label_source"]["enum"])
    if label_source not in allowed_sources:
        raise ValueError(f"invalid authoritative_label_source: {label_source}")
    linkage = payload.get("linkage_ids")
    if not isinstance(linkage, dict):
        raise ValueError("linkage_ids must be an object")
    linkage_spec = spec["properties"]["linkage_ids"]
    linkage_missing = [field for field in linkage_spec["required"] if field not in linkage]
    if linkage_missing:
        raise ValueError(f"linkage_ids missing required fields: {linkage_missing}")
    linkage_extra = sorted(set(linkage) - set(linkage_spec["properties"]))
    if linkage_extra:
        raise ValueError(f"linkage_ids contains unexpected fields: {linkage_extra}")
    if not isinstance(payload.get("auxiliary_trace"), bool):
        raise ValueError("auxiliary_trace must be boolean")
    return payload


def _make_shadow_record(
    *,
    record_kind: str,
    record_id: str,
    trajectory_id: str,
    parent_id: str | None,
    timestamp: str,
    role: str,
    task_type: str,
    risk: str,
    provider: str,
    model: str,
    input_ref: str | None,
    output_ref: str | None,
    evidence_ref: str | None,
    verdict_ref: str | None,
    final_outcome_label: str,
    trajectory_quality_label: str,
    redaction_status: str,
    linkage_ids: dict[str, Any],
    run_status: str | None = None,
    attempt_index: int | None = None,
    retry_count: int | None = None,
    correction_type: str | None = None,
    authoritative_label_source: str | None = "none",
    auxiliary_trace: bool = False,
    notes: str | None = None,
) -> dict[str, Any]:
    return _sanitize_value(
        {
            "schema_version": "shadow_logging_record_schema_v0",
            "record_kind": record_kind,
            "record_id": record_id,
            "trajectory_id": trajectory_id,
            "parent_id": parent_id,
            "timestamp": timestamp,
            "role": role,
            "task_type": task_type,
            "risk": risk,
            "provider": provider,
            "model": model,
            "input_ref": input_ref,
            "output_ref": output_ref,
            "evidence_ref": evidence_ref,
            "verdict_ref": verdict_ref,
            "final_outcome_label": final_outcome_label,
            "trajectory_quality_label": trajectory_quality_label,
            "redaction_status": redaction_status,
            "linkage_ids": linkage_ids,
            "run_status": run_status,
            "attempt_index": attempt_index,
            "retry_count": retry_count,
            "correction_type": correction_type,
            "authoritative_label_source": authoritative_label_source,
            "auxiliary_trace": auxiliary_trace,
            "notes": notes,
        }
    )


def build_judge_shadow_corpus_records(
    *,
    risk: str,
    scope: str,
    sha: str,
    outdir: Path,
    generated_on: str,
    test_log_path: Path,
    evidence_pack_path: Path,
    judge_verdict_path: Path,
    human_verdict_path: Path,
    judge_raw_response_path: Path,
    verdict: dict[str, Any],
    raw_response: dict[str, Any],
    runtime_config: dict[str, Any],
    execution_status_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    identity = _build_judge_shadow_identity(
        risk=risk,
        scope=scope,
        sha=sha,
        outdir=outdir,
        generated_on=generated_on,
    )
    trajectory_id = identity["trajectory_id"]
    run_id = identity["run_id"]
    continuity_id = identity["continuity_id"]
    evidence_pack_id = identity["evidence_pack_id"]
    status_id = identity["status_id"]
    judge_verdict_id = identity["judge_verdict_id"]
    human_verdict_id = identity["human_verdict_id"]
    outcome_id = identity["outcome_id"]
    linkage_ids = {
        "task_id": None,
        "request_id": identity["request_id"],
        "run_id": run_id,
        "attempt_id": identity["run_token"],
        "evidence_pack_id": evidence_pack_id,
        "continuity_id": continuity_id,
        "judge_verdict_id": judge_verdict_id,
        "human_verdict_id": human_verdict_id,
        "outcome_id": outcome_id,
        "correction_id": None,
    }
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    task_type = "coding_review"
    evidence_ref = _path_ref(evidence_pack_path)
    verdict_ref = _path_ref(judge_verdict_path)
    continuity_ref = _path_ref(DEFAULT_CONTINUITY_PATH)
    records: list[dict[str, Any]] = [
        _make_shadow_record(
            record_kind="continuity_artifact",
            record_id=f"continuity_artifact:{identity['run_token']}",
            trajectory_id=trajectory_id,
            parent_id=None,
            timestamp=timestamp,
            role="system",
            task_type=task_type,
            risk=risk,
            provider="internal",
            model="generate_continuity_index",
            input_ref=continuity_ref,
            output_ref=continuity_ref,
            evidence_ref=None,
            verdict_ref=None,
            final_outcome_label="needs_human_review",
            trajectory_quality_label="inconclusive_trajectory",
            redaction_status="ref_only",
            linkage_ids=linkage_ids,
            run_status="COMPLETED",
            attempt_index=1,
            retry_count=0,
            authoritative_label_source="none",
            auxiliary_trace=True,
            notes="Continuity artifact referenced only; preview stays embedded in evidence pack.",
        )
    ]
    parent_id = records[-1]["record_id"]
    if execution_status_payload is not None:
        status_ref = execution_status_payload.get("source_ref")
        retry_count = execution_status_payload.get("retry_count")
        attempt_count = execution_status_payload.get("attempt_count")
        records.append(
            _make_shadow_record(
                record_kind="status_event",
                record_id=status_id,
                trajectory_id=trajectory_id,
                parent_id=parent_id,
                timestamp=timestamp,
                role="system",
                task_type=task_type,
                risk=risk,
                provider="internal",
                model="bounded_execution_status_artifact",
                input_ref=status_ref,
                output_ref=status_ref,
                evidence_ref=evidence_ref,
                verdict_ref=None,
                final_outcome_label="needs_human_review",
                trajectory_quality_label="inconclusive_trajectory",
                redaction_status="ref_only",
                linkage_ids=linkage_ids,
                run_status=str(execution_status_payload.get("status") or "UNKNOWN").strip().upper(),
                attempt_index=attempt_count if isinstance(attempt_count, int) else None,
                retry_count=retry_count if isinstance(retry_count, int) else None,
                authoritative_label_source="none",
                auxiliary_trace=False,
                notes="Execution status artifact referenced for timeout/retry/stall lineage.",
            )
        )
        parent_id = records[-1]["record_id"]
    records.append(
        _make_shadow_record(
            record_kind="evidence_pack",
            record_id=evidence_pack_id,
            trajectory_id=trajectory_id,
            parent_id=parent_id,
            timestamp=timestamp,
            role="system",
            task_type=task_type,
            risk=risk,
            provider="internal",
            model="judge_runner_evidence_pack",
            input_ref=_path_ref(test_log_path),
            output_ref=evidence_ref,
            evidence_ref=evidence_ref,
            verdict_ref=None,
            final_outcome_label="needs_human_review",
            trajectory_quality_label="inconclusive_trajectory",
            redaction_status="ref_only",
            linkage_ids=linkage_ids,
            run_status="COMPLETED",
            attempt_index=1,
            retry_count=0,
            authoritative_label_source="none",
            auxiliary_trace=False,
            notes="Evidence pack assembled for external judge review.",
        )
    )
    judge_provider = "openai" if raw_response.get("call_state") == "completed" else "internal"
    judge_model = runtime_config["model"] if judge_provider == "openai" else "judge_runner_fallback"
    records.append(
        _make_shadow_record(
            record_kind="judge_verdict",
            record_id=judge_verdict_id,
            trajectory_id=trajectory_id,
            parent_id=evidence_pack_id,
            timestamp=timestamp,
            role="judge",
            task_type=task_type,
            risk=risk,
            provider=judge_provider,
            model=judge_model,
            input_ref=evidence_ref,
            output_ref=_path_ref(judge_raw_response_path),
            evidence_ref=evidence_ref,
            verdict_ref=verdict_ref,
            final_outcome_label="needs_human_review",
            trajectory_quality_label="inconclusive_trajectory",
            redaction_status="ref_only",
            linkage_ids=linkage_ids,
            run_status="COMPLETED",
            attempt_index=1,
            retry_count=0,
            authoritative_label_source="none",
            auxiliary_trace=False,
            notes=f"judge_call_state={raw_response.get('call_state', 'unknown')}",
        )
    )
    records.append(
        _make_shadow_record(
            record_kind="human_verdict",
            record_id=human_verdict_id,
            trajectory_id=trajectory_id,
            parent_id=judge_verdict_id,
            timestamp=timestamp,
            role="system",
            task_type=task_type,
            risk=risk,
            provider="internal",
            model="judge_runner_renderer",
            input_ref=verdict_ref,
            output_ref=_path_ref(human_verdict_path),
            evidence_ref=evidence_ref,
            verdict_ref=verdict_ref,
            final_outcome_label="needs_human_review",
            trajectory_quality_label="inconclusive_trajectory",
            redaction_status="ref_only",
            linkage_ids=linkage_ids,
            run_status="COMPLETED",
            attempt_index=1,
            retry_count=0,
            authoritative_label_source="none",
            auxiliary_trace=False,
            notes=f"user_facing_summary_for={verdict.get('verdict', 'UNKNOWN')}",
        )
    )
    records.append(
        _make_shadow_record(
            record_kind="final_outcome",
            record_id=outcome_id,
            trajectory_id=trajectory_id,
            parent_id=human_verdict_id,
            timestamp=timestamp,
            role="system",
            task_type=task_type,
            risk=risk,
            provider="internal",
            model="shadow_logging_contract_v0",
            input_ref=_path_ref(human_verdict_path),
            output_ref=None,
            evidence_ref=evidence_ref,
            verdict_ref=verdict_ref,
            final_outcome_label="needs_human_review",
            trajectory_quality_label="inconclusive_trajectory",
            redaction_status="not_required",
            linkage_ids=linkage_ids,
            run_status="COMPLETED",
            attempt_index=1,
            retry_count=0,
            authoritative_label_source="none",
            auxiliary_trace=False,
            notes="Provisional outcome only; authoritative owner decision is still required.",
        )
    )
    return records


def build_shadow_corpus_status(
    *,
    risk: str,
    scope: str,
    sha: str,
    outdir: Path,
    generated_on: str,
    status: str,
    shadow_corpus_path: Path | None,
    records_written: int,
    error: str | None,
    reason: str,
) -> dict[str, Any]:
    if status not in {"written", "failed"}:
        raise ValueError(f"invalid shadow corpus status: {status}")
    identity = _build_judge_shadow_identity(
        risk=risk,
        scope=scope,
        sha=sha,
        outdir=outdir,
        generated_on=generated_on,
    )
    return _sanitize_value(
        {
            "schema_version": "shadow_corpus_status_v0",
            "trajectory_id": identity["trajectory_id"],
            "run_id": identity["run_id"],
            "status": status,
            "shadow_corpus_path": _path_ref(shadow_corpus_path) if shadow_corpus_path is not None else None,
            "records_written": records_written,
            "error": error,
            "reason": reason,
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    )


def write_shadow_corpus_status_artifact(
    *,
    outdir: Path,
    status_payload: dict[str, Any],
) -> Path:
    status_path = outdir / "shadow_corpus_status.json"
    status_path.write_text(
        json.dumps(status_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return status_path


def write_judge_shadow_corpus_records(
    *,
    risk: str,
    scope: str,
    sha: str,
    outdir: Path,
    generated_on: str,
    test_log_path: Path,
    evidence_pack_path: Path,
    judge_verdict_path: Path,
    human_verdict_path: Path,
    judge_raw_response_path: Path,
    verdict: dict[str, Any],
    raw_response: dict[str, Any],
    runtime_config: dict[str, Any],
    execution_status_payload: dict[str, Any] | None,
    shadow_log_dir: Path,
) -> dict[str, Any]:
    records = build_judge_shadow_corpus_records(
        risk=risk,
        scope=scope,
        sha=sha,
        outdir=outdir,
        generated_on=generated_on,
        test_log_path=test_log_path,
        evidence_pack_path=evidence_pack_path,
        judge_verdict_path=judge_verdict_path,
        human_verdict_path=human_verdict_path,
        judge_raw_response_path=judge_raw_response_path,
        verdict=verdict,
        raw_response=raw_response,
        runtime_config=runtime_config,
        execution_status_payload=execution_status_payload,
    )
    schema = load_shadow_logging_schema()
    sanitized_records = [validate_shadow_logging_record(record, schema=schema) for record in records]
    month = generated_on[:7] if re.match(r"^\d{4}-\d{2}-\d{2}$", generated_on) else datetime.now(timezone.utc).strftime("%Y-%m")
    corpus_dir = shadow_log_dir / "corpus_v0"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = corpus_dir / f"trajectory_records_{month}.jsonl"
    with corpus_path.open("a", encoding="utf-8") as handle:
        for record in sanitized_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {
        "shadow_corpus_path": corpus_path,
        "shadow_corpus_records_written": len(sanitized_records),
        "shadow_corpus_write_error": None,
    }


def _default_output_dir(sha: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return REPO_ROOT / "artifacts" / "judge" / f"{timestamp}_{sha[:12]}"


def run_judge_flow(
    *,
    risk: str,
    scope: str,
    test_log_path: Path,
    deferred_text: str,
    outdir: Path,
    sha: str | None = None,
    execution_status_path: Path | None = None,
    generated_on: str | None = None,
    client: Any = None,
    runtime_config: dict[str, Any] | None = None,
    shadow_log_dir: Path | None = None,
) -> dict[str, Any]:
    resolved_sha = _resolve_sha(sha)
    branch = _resolve_branch()
    day = generated_on or date.today().isoformat()
    resolved_runtime_config = runtime_config or get_judge_runtime_config()
    changed_files = _changed_files_for_sha(resolved_sha)
    test_log_text = _load_text(test_log_path)
    continuity_preview, continuity_diff = _build_continuity_preview(day)
    unresolved_blockers = _extract_section(continuity_preview, "Active Blockers")
    detected_conflicts = _extract_conflict_lines(unresolved_blockers)
    execution_status_payload = _load_execution_status_payload(execution_status_path)
    execution_status_summary = _load_execution_status_summary(execution_status_path)
    missing_fields = _validate_pack_inputs(
        risk=risk,
        scope=scope,
        changed_files=changed_files,
        test_log_text=test_log_text,
        continuity_preview=continuity_preview,
        deferred_text=deferred_text,
    )
    pack_complete = not missing_fields

    evidence_pack = build_evidence_pack(
        risk=risk,
        scope=scope,
        sha=resolved_sha,
        branch=branch,
        changed_files=changed_files,
        test_log_path=test_log_path,
        test_log_text=test_log_text,
        continuity_preview=continuity_preview,
        continuity_diff=continuity_diff,
        unresolved_blockers=unresolved_blockers,
        detected_conflicts=detected_conflicts,
        deferred_text=deferred_text,
        execution_status_summary=execution_status_summary,
        generated_on=day,
        pack_complete=pack_complete,
        missing_fields=missing_fields,
    )

    outdir.mkdir(parents=True, exist_ok=True)
    evidence_pack_path = outdir / "evidence_pack.md"
    evidence_pack_path.write_text(evidence_pack, encoding="utf-8")

    if risk == "CORE":
        verdict = build_fallback_verdict(
            verdict="BLOCK",
            scope_summary=scope,
            checks_summary="Evidence pack assembled, but CORE final gate stays manual external judge only.",
            main_risk="CORE work is not eligible for API-judge final approval in this MVP.",
            required_fixes=["Use manual external judge path for CORE."],
            rationale_short="CORE remains outside automatic judge approval scope.",
        )
        raw_response = {
            "call_state": "skipped_core_manual_path",
            "reason": "CORE manual external judge required",
        }
    elif not pack_complete:
        verdict = build_fallback_verdict(
            verdict="FIX",
            scope_summary=scope,
            checks_summary="Evidence pack completeness check failed before judge call.",
            main_risk="Incomplete evidence pack prevents safe external approval.",
            required_fixes=missing_fields,
            rationale_short="Pack is incomplete, so judge approval is fail-closed.",
        )
        raw_response = {
            "call_state": "skipped_incomplete_pack",
            "missing_fields": missing_fields,
        }
    else:
        try:
            api_result = call_external_judge(
                evidence_pack=evidence_pack,
                risk=risk,
                sha=resolved_sha,
                runtime_config=resolved_runtime_config,
                client=client,
            )
        except Exception as exc:  # noqa: BLE001
            api_result = {
                "call_state": "failed",
                "parsed_output": None,
                "raw_response": {
                    "call_state": "failed",
                    "error": str(exc),
                },
                "error": str(exc),
            }
        if api_result["call_state"] != "completed":
            verdict = build_fallback_verdict(
                verdict="BLOCK",
                scope_summary=scope,
                checks_summary="External judge call failed or returned unusable output.",
                main_risk="Judge API unavailable or malformed response; manual external judge required.",
                required_fixes=[api_result.get("error", "judge API call failed")],
                rationale_short="The external judge path failed, so approval is blocked.",
            )
            raw_response = api_result["raw_response"]
        else:
            verdict = validate_judge_verdict(_sanitize_value(api_result["parsed_output"]))
            raw_response = _sanitize_value(api_result["raw_response"])

    judge_verdict_path = outdir / "judge_verdict.json"
    judge_verdict_path.write_text(
        json.dumps(_sanitize_value(verdict), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    human_verdict_path = outdir / "human_verdict.md"
    human_verdict_path.write_text(render_human_verdict(verdict), encoding="utf-8")

    judge_raw_response_path = outdir / "judge_raw_response.json"
    judge_raw_response_path.write_text(
        json.dumps(_sanitize_value(raw_response), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shadow_result = {
        "shadow_corpus_path": None,
        "shadow_corpus_records_written": 0,
        "shadow_corpus_write_error": None,
        "shadow_corpus_status_path": None,
        "shadow_corpus_status": None,
        "shadow_corpus_status_write_error": None,
    }
    try:
        shadow_result.update(
            write_judge_shadow_corpus_records(
                risk=risk,
                scope=scope,
                sha=resolved_sha,
                outdir=outdir,
                generated_on=day,
                test_log_path=test_log_path,
                evidence_pack_path=evidence_pack_path,
                judge_verdict_path=judge_verdict_path,
                human_verdict_path=human_verdict_path,
                judge_raw_response_path=judge_raw_response_path,
                verdict=verdict,
                raw_response=raw_response,
                runtime_config=resolved_runtime_config,
                execution_status_payload=execution_status_payload,
                shadow_log_dir=shadow_log_dir or _default_shadow_log_dir(outdir),
            )
        )
        shadow_status = build_shadow_corpus_status(
            risk=risk,
            scope=scope,
            sha=resolved_sha,
            outdir=outdir,
            generated_on=day,
            status="written",
            shadow_corpus_path=shadow_result["shadow_corpus_path"],
            records_written=shadow_result["shadow_corpus_records_written"],
            error=None,
            reason="corpus_write_succeeded",
        )
    except Exception as exc:  # noqa: BLE001
        shadow_result["shadow_corpus_write_error"] = str(exc)
        shadow_status = build_shadow_corpus_status(
            risk=risk,
            scope=scope,
            sha=resolved_sha,
            outdir=outdir,
            generated_on=day,
            status="failed",
            shadow_corpus_path=shadow_result["shadow_corpus_path"],
            records_written=shadow_result["shadow_corpus_records_written"],
            error=str(exc),
            reason="corpus_write_failed",
        )
    try:
        shadow_result["shadow_corpus_status_path"] = write_shadow_corpus_status_artifact(
            outdir=outdir,
            status_payload=shadow_status,
        )
        shadow_result["shadow_corpus_status"] = shadow_status
    except Exception as exc:  # noqa: BLE001
        shadow_result["shadow_corpus_status_write_error"] = str(exc)

    return {
        "evidence_pack_path": evidence_pack_path,
        "judge_verdict_path": judge_verdict_path,
        "human_verdict_path": human_verdict_path,
        "judge_raw_response_path": judge_raw_response_path,
        "verdict": verdict,
        "raw_response": raw_response,
        **shadow_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build evidence pack and call external judge.")
    parser.add_argument("--risk", required=True, choices=["LOW", "SEMI", "CORE"])
    parser.add_argument("--scope", required=True)
    parser.add_argument("--test-log", type=Path, required=True)
    parser.add_argument("--deferred-file", type=Path, default=None)
    parser.add_argument("--deferred-text", default=None)
    parser.add_argument("--execution-status", type=Path, default=None)
    parser.add_argument("--sha", default=None)
    parser.add_argument("--date", default=None, help="Override evidence date (YYYY-MM-DD).")
    parser.add_argument("--outdir", type=Path, default=None)
    args = parser.parse_args()

    deferred_text = _read_multiline_input(args.deferred_file, args.deferred_text)
    resolved_sha = _resolve_sha(args.sha)
    outdir = args.outdir or _default_output_dir(resolved_sha)

    result = run_judge_flow(
        risk=args.risk,
        scope=args.scope,
        test_log_path=args.test_log,
        deferred_text=deferred_text,
        outdir=outdir,
        sha=resolved_sha,
        execution_status_path=args.execution_status,
        generated_on=args.date,
    )
    shadow_status = result.get("shadow_corpus_status") or {}
    status_value = shadow_status.get("status")
    if status_value == "failed":
        print(
            f"shadow corpus status: {status_value}; "
            f"reason={shadow_status.get('reason', 'unknown')}; "
            f"error={shadow_status.get('error', '')}",
            file=sys.stderr,
        )
    print(result["human_verdict_path"].as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

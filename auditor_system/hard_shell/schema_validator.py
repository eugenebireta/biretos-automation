"""
hard_shell/schema_validator.py — response schema validation after every API call (SPEC §19.3).

After each auditor API call:
  - Parse JSON
  - Check required fields
  - Parse AuditVerdict

SchemaViolationError → BLOCKED + owner alert + ExperienceSink entry.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .contracts import (
    AuditIssue,
    AuditVerdict,
    AuditVerdictValue,
    ErrorClass,
    IssueSeverity,
)

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"verdict", "summary", "issues"}


class SchemaViolationError(Exception):
    """
    Raised when auditor response is missing required fields or unparseable.
    This is NOT a transient timeout — it indicates a breaking API change or
    garbage response. Route: BLOCKED + owner alert.
    """

    def __init__(self, auditor_id: str, message: str):
        self.auditor_id = auditor_id
        self.error_class = ErrorClass.SCHEMA_VIOLATION
        super().__init__(f"[{auditor_id}] SchemaViolation: {message}")


def validate_and_parse(auditor_id: str, raw_text: str) -> AuditVerdict:
    """
    Parses auditor raw response text → AuditVerdict.

    Steps:
      1. Parse JSON (raises SchemaViolationError on failure)
      2. Check required fields present (raises SchemaViolationError if missing)
      3. Parse issues list (non-fatal: skips malformed individual issues)
      4. Parse verdict enum (raises SchemaViolationError on invalid value)

    Returns: AuditVerdict with schema_valid=True
    Raises:  SchemaViolationError
    """
    # Step 1: parse JSON
    try:
        data: Any = json.loads(raw_text.strip())
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error(
            "schema_validator: JSON parse error auditor_id=%s error=%s raw_len=%d",
            auditor_id, exc, len(raw_text),
        )
        raise SchemaViolationError(auditor_id, f"JSON parse error: {exc}") from exc

    if not isinstance(data, dict):
        raise SchemaViolationError(
            auditor_id,
            f"Response is not a JSON object, got {type(data).__name__}",
        )

    # Step 2: required fields
    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        logger.error(
            "schema_validator: missing_fields auditor_id=%s missing=%s present=%s",
            auditor_id, sorted(missing), sorted(data.keys()),
        )
        raise SchemaViolationError(auditor_id, f"Missing required fields: {sorted(missing)}")

    # Step 3: parse issues (non-fatal per issue)
    issues: list[AuditIssue] = []
    raw_issues = data.get("issues") or []
    if not isinstance(raw_issues, list):
        logger.warning(
            "schema_validator: issues not a list auditor_id=%s type=%s",
            auditor_id, type(raw_issues).__name__,
        )
        raw_issues = []

    for idx, item in enumerate(raw_issues):
        if not isinstance(item, dict):
            logger.warning(
                "schema_validator: issue[%d] not a dict auditor_id=%s", idx, auditor_id
            )
            continue
        try:
            severity_raw = item.get("severity", "info")
            try:
                severity = IssueSeverity(severity_raw)
            except ValueError:
                severity = IssueSeverity.INFO
                logger.warning(
                    "schema_validator: unknown severity=%r auditor_id=%s → INFO",
                    severity_raw, auditor_id,
                )
            issues.append(AuditIssue(
                severity=severity,
                area=str(item.get("area", "unknown")),
                description=str(item.get("description", "")),
                line_ref=str(item.get("line_ref", "")),
            ))
        except Exception as exc:
            logger.warning(
                "schema_validator: issue[%d] parse error auditor_id=%s error=%s",
                idx, auditor_id, exc,
            )

    # Step 4: parse verdict enum
    verdict_raw = data["verdict"]
    try:
        verdict_val = AuditVerdictValue(verdict_raw)
    except ValueError as exc:
        raise SchemaViolationError(
            auditor_id,
            f"Invalid verdict value: {verdict_raw!r}. Expected one of: {[v.value for v in AuditVerdictValue]}",
        ) from exc

    return AuditVerdict(
        auditor_id=auditor_id,
        verdict=verdict_val,
        summary=str(data["summary"]),
        issues=issues,
        schema_valid=True,
    )

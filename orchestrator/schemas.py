"""
schemas.py — JSON Schema validation for Meta Orchestrator artifacts.

All 5 schemas (directive, execution_packet, advisor_verdict, manifest, escalation)
are loaded once and cached. Validates via jsonschema draft-07.

Usage:
    from orchestrator.schemas import validate, ValidationError

    try:
        validate("directive_v1", my_dict)
    except ValidationError as e:
        print(e.message)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import jsonschema
    from jsonschema import Draft7Validator, ValidationError  # re-export ValidationError
    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False
    ValidationError = Exception  # type: ignore[misc,assignment]

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"

# Schema name → filename (without .json)
SCHEMA_FILES: dict[str, str] = {
    "directive_v1":       "directive_v1",
    "execution_packet_v1": "execution_packet_v1",
    "advisor_verdict_v1": "advisor_verdict_v1",
    "manifest_v1":        "manifest_v1",
    "escalation_v1":      "escalation_v1",
}

_cache: dict[str, dict] = {}


def _load_schema(name: str) -> dict:
    if name not in _cache:
        filename = SCHEMA_FILES.get(name)
        if not filename:
            raise KeyError(f"Unknown schema: {name!r}. Available: {list(SCHEMA_FILES)}")
        path = SCHEMAS_DIR / f"{filename}.json"
        _cache[name] = json.loads(path.read_text(encoding="utf-8"))
    return _cache[name]


def validate(schema_name: str, data: Any) -> None:
    """
    Validate data against the named schema.
    Raises ValidationError (jsonschema) on failure.
    Raises RuntimeError if jsonschema is not installed.
    """
    if not _JSONSCHEMA_AVAILABLE:
        raise RuntimeError(
            "jsonschema is required for schema validation. "
            "Install with: pip install jsonschema"
        )
    schema = _load_schema(schema_name)
    Draft7Validator(schema).validate(data)


def validate_soft(schema_name: str, data: Any) -> list[str]:
    """
    Validate and return list of error messages (empty = valid).
    Never raises. Safe to use in rule engine logic.
    """
    if not _JSONSCHEMA_AVAILABLE:
        return [f"jsonschema not installed; cannot validate {schema_name}"]
    try:
        schema = _load_schema(schema_name)
        validator = Draft7Validator(schema)
        return [e.message for e in sorted(validator.iter_errors(data), key=str)]
    except Exception as exc:
        return [f"schema load error: {exc}"]


def is_valid(schema_name: str, data: Any) -> bool:
    """Return True if data is valid against schema, False otherwise."""
    return len(validate_soft(schema_name, data)) == 0


def list_schemas() -> list[str]:
    """Return names of all registered schemas."""
    return list(SCHEMA_FILES)

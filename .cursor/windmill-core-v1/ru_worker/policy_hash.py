from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

from config import get_config

try:
    from pii_dependency_registry import get_pii_dependency_hash
except ImportError:
    from .pii_dependency_registry import get_pii_dependency_hash  # type: ignore


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def parse_expected_tax_rates(raw_value: str) -> Any:
    try:
        parsed = json.loads(raw_value or "{}")
    except Exception:
        return {}
    if isinstance(parsed, (dict, list)):
        return parsed
    return {}


def build_policy_inputs(config=None) -> Dict[str, Any]:
    cfg = config or get_config()
    return {
        "csg_config": {
            "MAX_PRICE_DEVIATION": cfg.max_price_deviation,
            "ROUNDING_TOLERANCE": cfg.rounding_tolerance,
            "CSG_ENABLED": cfg.csg_enabled,
        },
        "expected_tax_rates": parse_expected_tax_rates(cfg.expected_tax_rates),
        "canary_config": {
            "CANARY_SAMPLE_RATE": cfg.canary_sample_rate,
            "CANARY_HASH_ALGO_ID": cfg.canary_hash_algo_id,
        },
        "pii_dependency_hash": get_pii_dependency_hash(),
        "gate_chain_version": cfg.gate_chain_version,
    }


def compute_policy_hash(policy_inputs: Dict[str, Any]) -> str:
    canonical = _canonical_json(policy_inputs)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def current_policy_context(config=None) -> Dict[str, Any]:
    policy_inputs = build_policy_inputs(config=config)
    return {
        "policy_hash": compute_policy_hash(policy_inputs),
        "policy_inputs": policy_inputs,
    }


def upsert_config_snapshot(db_conn, policy_hash: str, policy_inputs: Dict[str, Any]) -> None:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO config_snapshots (policy_hash, config_content)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (policy_hash) DO NOTHING
            """,
            (policy_hash, _canonical_json(policy_inputs)),
        )
    finally:
        cursor.close()


def get_config_snapshot(db_conn, policy_hash: str) -> Optional[Dict[str, Any]]:
    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
            SELECT config_content
            FROM config_snapshots
            WHERE policy_hash = %s
            LIMIT 1
            """,
            (policy_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        payload = row[0]
        if isinstance(payload, str):
            return json.loads(payload)
        if isinstance(payload, dict):
            return payload
        return None
    finally:
        cursor.close()


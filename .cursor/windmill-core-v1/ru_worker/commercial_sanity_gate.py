from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


@dataclass(frozen=True)
class GateVerdict:
    verdict: str  # ALLOW | NEEDS_HUMAN | REJECT | SKIPPED_MISSING_CONFIG
    reason: str
    details: Dict[str, Any]


def _to_minor_units(value: Any, *, assume_minor_when_int: bool = False) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if assume_minor_when_int else int(round(float(value) * 100))
    try:
        return int(round(float(value) * 100))
    except Exception:
        return None


def _extract_raw_input_size_bytes(payload: Dict[str, Any]) -> int:
    explicit = payload.get("raw_input_size_bytes")
    if isinstance(explicit, int) and explicit >= 0:
        return explicit
    try:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return len(raw.encode("utf-8"))
    except Exception:
        return 0


def _extract_tax_rates(expected_tax_rates: Any) -> set[float]:
    rates: set[float] = set()
    if isinstance(expected_tax_rates, dict):
        source: Iterable[Any] = expected_tax_rates.get("rates", [])
    elif isinstance(expected_tax_rates, list):
        source = expected_tax_rates
    else:
        source = []
    for item in source:
        try:
            rates.add(round(float(item), 4))
        except Exception:
            continue
    return rates


def _extract_reference_price_minor(payload: Dict[str, Any]) -> Optional[int]:
    if "reference_price_minor" in payload and payload.get("reference_price_minor") is not None:
        try:
            return int(payload.get("reference_price_minor"))
        except Exception:
            return None
    if "reference_price" in payload:
        return _to_minor_units(payload.get("reference_price"))
    if "expected_amount_minor" in payload and payload.get("expected_amount_minor") is not None:
        try:
            return int(payload.get("expected_amount_minor"))
        except Exception:
            return None
    return None


def _extract_total_minor(payload: Dict[str, Any]) -> Optional[int]:
    if "total_minor" in payload and payload.get("total_minor") is not None:
        try:
            return int(payload.get("total_minor"))
        except Exception:
            return None
    if "amount_minor" in payload and payload.get("amount_minor") is not None:
        try:
            return int(payload.get("amount_minor"))
        except Exception:
            return None
    if "total_amount" in payload:
        return _to_minor_units(payload.get("total_amount"))
    if "amount" in payload:
        return _to_minor_units(payload.get("amount"))
    return None


def _extract_net_tax_minor(payload: Dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
    net_minor = payload.get("net_minor")
    tax_minor = payload.get("tax_minor")
    if net_minor is not None:
        try:
            net_minor = int(net_minor)
        except Exception:
            net_minor = None
    if tax_minor is not None:
        try:
            tax_minor = int(tax_minor)
        except Exception:
            tax_minor = None

    if net_minor is None and payload.get("net_amount") is not None:
        net_minor = _to_minor_units(payload.get("net_amount"))
    if tax_minor is None and payload.get("tax_amount") is not None:
        tax_minor = _to_minor_units(payload.get("tax_amount"))
    return net_minor, tax_minor


def _extract_tax_rate(payload: Dict[str, Any]) -> Optional[float]:
    for key in ("tax_rate", "vat_rate"):
        value = payload.get(key)
        if value is None:
            continue
        try:
            return round(float(value), 4)
        except Exception:
            continue
    return None


def evaluate_commercial_sanity(
    action: Dict[str, Any],
    *,
    config_values: Dict[str, Any],
    execution_mode: str,
    replay_config_snapshot: Optional[Dict[str, Any]] = None,
) -> GateVerdict:
    payload = action.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    action_type = str(action.get("action_type") or "")

    # Replay passthrough when policy snapshot is missing.
    if execution_mode == "REPLAY" and replay_config_snapshot is None:
        return GateVerdict(
            verdict="SKIPPED_MISSING_CONFIG",
            reason="replay_config_unavailable",
            details={"replay_config_status": "REPLAY_CONFIG_UNAVAILABLE"},
        )

    source_cfg = replay_config_snapshot if execution_mode == "REPLAY" and replay_config_snapshot else config_values

    max_input_size = int(source_cfg.get("MAX_INPUT_SIZE_BYTES", 102400))
    max_price_deviation = float(source_cfg.get("MAX_PRICE_DEVIATION", 0.15))
    rounding_tolerance = int(source_cfg.get("ROUNDING_TOLERANCE", 1))
    expected_tax_rates = _extract_tax_rates(source_cfg.get("expected_tax_rates", {}))

    raw_input_size_bytes = _extract_raw_input_size_bytes(payload)
    if raw_input_size_bytes > max_input_size:
        return GateVerdict(
            verdict="REJECT",
            reason="input_too_large",
            details={
                "raw_input_size_bytes": raw_input_size_bytes,
                "max_input_size_bytes": max_input_size,
            },
        )

    total_minor = _extract_total_minor(payload)
    reference_price_minor = _extract_reference_price_minor(payload)
    if total_minor is not None and reference_price_minor is not None and reference_price_minor > 0:
        deviation = abs(total_minor - reference_price_minor) / float(reference_price_minor)
        if deviation > max_price_deviation:
            return GateVerdict(
                verdict="NEEDS_HUMAN",
                reason="price_anomaly",
                details={
                    "action_type": action_type,
                    "total_minor": total_minor,
                    "reference_price_minor": reference_price_minor,
                    "deviation": deviation,
                    "max_price_deviation": max_price_deviation,
                    "reference_price_snapshot": {
                        "reference_price_minor": reference_price_minor,
                        "reference_source": payload.get("reference_source", "payload"),
                    },
                },
            )

    net_minor, tax_minor = _extract_net_tax_minor(payload)
    if total_minor is not None and net_minor is not None and tax_minor is not None:
        mismatch = abs(total_minor - (net_minor + tax_minor))
        if mismatch > rounding_tolerance:
            return GateVerdict(
                verdict="NEEDS_HUMAN",
                reason="tax_arithmetic_mismatch",
                details={
                    "action_type": action_type,
                    "total_minor": total_minor,
                    "net_minor": net_minor,
                    "tax_minor": tax_minor,
                    "mismatch": mismatch,
                    "rounding_tolerance": rounding_tolerance,
                },
            )

    tax_rate = _extract_tax_rate(payload)
    if tax_rate is not None and expected_tax_rates and tax_rate not in expected_tax_rates:
        return GateVerdict(
            verdict="NEEDS_HUMAN",
            reason="tax_rate_anomaly",
            details={
                "action_type": action_type,
                "tax_rate": tax_rate,
                "expected_tax_rates": sorted(expected_tax_rates),
            },
        )

    return GateVerdict(verdict="ALLOW", reason="ok", details={"action_type": action_type})


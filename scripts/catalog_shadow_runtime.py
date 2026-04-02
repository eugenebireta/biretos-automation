"""Bounded runtime state for Phase A sanity shadow runs."""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "catalog_shadow_execution_profile_v1.json"
_config_cache: dict | None = None


def load_shadow_profile() -> dict:
    global _config_cache
    if _config_cache is None:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            _config_cache = json.load(f)
    return dict(_config_cache)


def _default_state() -> dict:
    return {
        "active": False,
        "profile_name": "",
        "start_monotonic": 0.0,
        "limits": {},
        "responses_only_verifier": True,
        "weak_marketplace_policy": {},
        "completed_skus": [],
        "skipped_due_to_budget": [],
        "timed_out_sources": [],
        "verifier_calls_used": 0,
        "responses_calls": 0,
        "chat_completions_calls_verifier": 0,
        "timeout_count": 0,
        "consecutive_timeouts": 0,
        "reason_for_early_stop": "",
        "early_stop": False,
        "per_source_failure_summary": Counter(),
        "verifier_calls_per_sku": Counter(),
        "external_source_attempts_per_sku": Counter(),
        "datasheet_attempts_per_sku": Counter(),
        "latencies_sec": [],
        "run_manifest_id": "",
        "planned_skus": 0,
    }


_state = _default_state()


def reset_shadow_runtime() -> None:
    global _state
    _state = _default_state()


def activate_shadow_runtime(*, run_manifest_id: str = "", planned_skus: int = 0) -> None:
    profile = load_shadow_profile()
    reset_shadow_runtime()
    _state["active"] = True
    _state["profile_name"] = profile["profile_name"]
    _state["start_monotonic"] = time.monotonic()
    _state["limits"] = dict(profile["limits"])
    _state["responses_only_verifier"] = bool(profile["responses_only_verifier"])
    _state["weak_marketplace_policy"] = dict(profile["weak_marketplace_policy"])
    _state["run_manifest_id"] = run_manifest_id
    _state["planned_skus"] = planned_skus


def shadow_runtime_active() -> bool:
    return bool(_state["active"])


def _elapsed() -> float:
    if not _state["start_monotonic"]:
        return 0.0
    return round(time.monotonic() - _state["start_monotonic"], 3)


def _blocked_domain_keywords() -> list[str]:
    return list(_state["weak_marketplace_policy"].get("blocked_domain_keywords", []))


def _domain_hint(url: str) -> str:
    netloc = (urlparse(url).netloc or "").lower()
    return netloc.removeprefix("www.")


def _set_early_stop(reason: str) -> None:
    if not _state["early_stop"]:
        _state["early_stop"] = True
        _state["reason_for_early_stop"] = reason


def check_wallclock_budget() -> bool:
    if not shadow_runtime_active():
        return False
    limit = int(_state["limits"].get("MAX_RUN_WALLCLOCK_SEC", 0) or 0)
    if limit and _elapsed() >= limit:
        _set_early_stop(f"wallclock_budget_reached:{limit}")
        return True
    return _state["early_stop"]


def allow_next_sku(pn: str) -> tuple[bool, str]:
    if not shadow_runtime_active():
        return True, ""
    if check_wallclock_budget():
        _state["skipped_due_to_budget"].append({"pn_primary": pn, "reason": _state["reason_for_early_stop"]})
        return False, _state["reason_for_early_stop"]
    limit = int(_state["limits"].get("MAX_SHADOW_SKUS", 0) or 0)
    if limit and len(_state["completed_skus"]) >= limit:
        reason = f"max_shadow_skus_reached:{limit}"
        _set_early_stop(reason)
        _state["skipped_due_to_budget"].append({"pn_primary": pn, "reason": reason})
        return False, reason
    return True, ""


def record_completed_sku(pn: str) -> None:
    if shadow_runtime_active():
        _state["completed_skus"].append(pn)


def record_skipped_due_to_budget(pn: str, reason: str) -> None:
    if shadow_runtime_active():
        _state["skipped_due_to_budget"].append({"pn_primary": pn, "reason": reason})


def allow_verifier_call(pn: str) -> tuple[bool, str]:
    if not shadow_runtime_active():
        return True, ""
    if check_wallclock_budget():
        return False, _state["reason_for_early_stop"]
    max_run = int(_state["limits"].get("MAX_VERIFIER_CALLS_PER_RUN", 0) or 0)
    if max_run and _state["verifier_calls_used"] >= max_run:
        reason = f"max_verifier_calls_per_run_reached:{max_run}"
        _set_early_stop(reason)
        return False, reason
    max_sku = int(_state["limits"].get("MAX_VERIFIER_CALLS_PER_SKU", 0) or 0)
    if max_sku and _state["verifier_calls_per_sku"][pn] >= max_sku:
        return False, f"max_verifier_calls_per_sku_reached:{max_sku}"
    return True, ""


def record_verifier_call(
    pn: str,
    *,
    latency_sec: float,
    timed_out: bool,
    success: bool,
) -> None:
    if not shadow_runtime_active():
        return
    _state["verifier_calls_used"] += 1
    _state["responses_calls"] += 1
    _state["verifier_calls_per_sku"][pn] += 1
    _state["latencies_sec"].append(round(latency_sec, 4))
    if timed_out:
        _state["timeout_count"] += 1
        _state["consecutive_timeouts"] += 1
        _state["timed_out_sources"].append({"channel": "verifier", "pn_primary": pn})
        max_timeouts = int(_state["limits"].get("MAX_CONSECUTIVE_TIMEOUTS", 0) or 0)
        if max_timeouts and _state["consecutive_timeouts"] >= max_timeouts:
            _set_early_stop(f"max_consecutive_timeouts_reached:{max_timeouts}")
    elif success:
        _state["consecutive_timeouts"] = 0


def allow_external_source_candidate(url: str) -> bool:
    if not shadow_runtime_active():
        return True
    lowered = url.lower()
    for token in _blocked_domain_keywords():
        if token in lowered:
            return False
    return True


def allow_external_source_attempt(pn: str, url: str) -> tuple[bool, str]:
    if not shadow_runtime_active():
        return True, ""
    if not allow_external_source_candidate(url):
        return False, "weak_marketplace_disabled"
    if check_wallclock_budget():
        return False, _state["reason_for_early_stop"]
    max_attempts = int(_state["limits"].get("MAX_EXTERNAL_SOURCE_ATTEMPTS_PER_SKU", 0) or 0)
    if max_attempts and _state["external_source_attempts_per_sku"][pn] >= max_attempts:
        return False, f"max_external_source_attempts_per_sku_reached:{max_attempts}"
    _state["external_source_attempts_per_sku"][pn] += 1
    return True, ""


def allow_datasheet_attempt(pn: str, url: str) -> tuple[bool, str]:
    if not shadow_runtime_active():
        return True, ""
    if check_wallclock_budget():
        return False, _state["reason_for_early_stop"]
    max_attempts = int(_state["limits"].get("MAX_DATASHEET_ATTEMPTS_PER_SKU", 0) or 0)
    if max_attempts and _state["datasheet_attempts_per_sku"][pn] >= max_attempts:
        return False, f"max_datasheet_attempts_per_sku_reached:{max_attempts}"
    _state["datasheet_attempts_per_sku"][pn] += 1
    return True, ""


def record_source_failure(url: str, *, timed_out: bool, channel: str) -> None:
    if not shadow_runtime_active():
        return
    domain = _domain_hint(url) or channel
    _state["per_source_failure_summary"][domain] += 1
    if timed_out:
        _state["timeout_count"] += 1
        _state["consecutive_timeouts"] += 1
        _state["timed_out_sources"].append({"channel": channel, "source": domain})
        max_timeouts = int(_state["limits"].get("MAX_CONSECUTIVE_TIMEOUTS", 0) or 0)
        if max_timeouts and _state["consecutive_timeouts"] >= max_timeouts:
            _set_early_stop(f"max_consecutive_timeouts_reached:{max_timeouts}")
    else:
        _state["consecutive_timeouts"] = 0


def record_source_success() -> None:
    if shadow_runtime_active():
        _state["consecutive_timeouts"] = 0


def get_shadow_runtime_summary() -> dict:
    avg_latency = round(sum(_state["latencies_sec"]) / len(_state["latencies_sec"]), 4) if _state["latencies_sec"] else 0.0
    return {
        "profile_name": _state["profile_name"],
        "active": _state["active"],
        "completed_skus": list(_state["completed_skus"]),
        "skipped_due_to_budget": list(_state["skipped_due_to_budget"]),
        "timed_out_sources": list(_state["timed_out_sources"]),
        "verifier_calls_used": _state["verifier_calls_used"],
        "responses_calls": _state["responses_calls"],
        "chat_completions_calls_verifier": _state["chat_completions_calls_verifier"],
        "timeout_count": _state["timeout_count"],
        "per_source_failure_summary": dict(_state["per_source_failure_summary"]),
        "reason_for_early_stop": _state["reason_for_early_stop"],
        "early_stop": _state["early_stop"],
        "total_wall_clock_sec": _elapsed(),
        "avg_verifier_latency_sec": avg_latency,
        "max_verifier_latency_sec": max(_state["latencies_sec"], default=0.0),
        "limits": dict(_state["limits"]),
        "responses_only_verifier": _state["responses_only_verifier"],
        "run_manifest_id": _state["run_manifest_id"],
        "planned_skus": _state["planned_skus"],
    }

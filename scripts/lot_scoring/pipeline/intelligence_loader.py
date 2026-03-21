from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Pattern

from scripts.lot_scoring.pipeline.helpers import clamp, to_float, to_str

ALLOWED_PATTERN_TYPES = {"regex", "substring", "exact"}
ALLOWED_COMBINATOR_MODES = {"max"}


@dataclass(frozen=True)
class VerticalConfig:
    tier: str
    purity_weight: float
    obsolescence_score: float
    freshness_score: float | None
    freshness_score_by_value: dict[str, float] | None
    reject: bool


@dataclass(frozen=True)
class LegacyPatternRule:
    pattern: str
    pattern_type: str
    penalty: float
    reason: str
    compiled_regex: Pattern[str] | None


@dataclass(frozen=True)
class BrandProfile:
    brand: str
    metadata: dict[str, Any]
    tuning_params: dict[str, Any]
    verticals: dict[str, VerticalConfig]
    category_mapping: dict[str, Any]
    legacy_patterns: tuple[LegacyPatternRule, ...]
    classification_precedence: tuple[str, ...]
    fallback_vertical: str


def _root_dir(base_dir: Path | None = None) -> Path:
    if base_dir is not None:
        return base_dir
    return Path(__file__).resolve().parents[1] / "data" / "brand_intelligence"


def validate_brand_profile(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_top = (
        "metadata",
        "tuning_params",
        "verticals",
        "category_mapping",
        "legacy_patterns",
        "classification_precedence",
    )
    for key in required_top:
        if key not in raw:
            errors.append(f"missing top-level key: {key}")

    tuning = raw.get("tuning_params", {})
    if not isinstance(tuning, dict):
        errors.append("tuning_params must be object")
        tuning = {}
    alpha = to_float(tuning.get("alpha_freshness_impact"), -1.0)
    if not (0.0 <= alpha <= 1.0):
        errors.append("tuning_params.alpha_freshness_impact must be in [0,1]")
    cps_floor = to_float(tuning.get("cps_floor"), -1.0)
    if not (0.0 <= cps_floor <= 1.0):
        errors.append("tuning_params.cps_floor must be in [0,1]")
    reject_abs = to_float(tuning.get("reject_abs_usd_ceil"), -1.0)
    if reject_abs < 0.0:
        errors.append("tuning_params.reject_abs_usd_ceil must be >= 0")
    combinator = to_str(tuning.get("legacy_combinator_mode"), "").lower()
    if combinator and combinator not in ALLOWED_COMBINATOR_MODES:
        errors.append(f"unsupported legacy_combinator_mode: {combinator}")

    verticals = raw.get("verticals", {})
    if not isinstance(verticals, dict) or not verticals:
        errors.append("verticals must be non-empty object")
        verticals = {}
    for name, payload in verticals.items():
        if not isinstance(payload, dict):
            errors.append(f"verticals.{name} must be object")
            continue
        purity_weight = to_float(payload.get("purity_weight"), -1.0)
        if not (0.0 <= purity_weight <= 1.0):
            errors.append(f"verticals.{name}.purity_weight must be in [0,1]")
        obs = to_float(payload.get("obsolescence_score"), -1.0)
        if not (0.0 <= obs <= 1.0):
            errors.append(f"verticals.{name}.obsolescence_score must be in [0,1]")
        reject = payload.get("reject")
        if not isinstance(reject, bool):
            errors.append(f"verticals.{name}.reject must be bool")
        has_freshness_score = "freshness_score" in payload
        has_dynamic = "freshness_score_by_value" in payload
        if not has_freshness_score and not has_dynamic:
            errors.append(f"verticals.{name} must define freshness_score or freshness_score_by_value")
        if has_freshness_score:
            fres = to_float(payload.get("freshness_score"), -1.0)
            if not (0.0 <= fres <= 1.0):
                errors.append(f"verticals.{name}.freshness_score must be in [0,1]")
        if has_dynamic:
            dynamic = payload.get("freshness_score_by_value")
            if not isinstance(dynamic, dict):
                errors.append(f"verticals.{name}.freshness_score_by_value must be object")
            else:
                threshold = to_float(dynamic.get("high_threshold_usd"), -1.0)
                high = to_float(dynamic.get("high"), -1.0)
                low = to_float(dynamic.get("low"), -1.0)
                if threshold < 0.0:
                    errors.append(f"verticals.{name}.freshness_score_by_value.high_threshold_usd must be >= 0")
                if not (0.0 <= high <= 1.0):
                    errors.append(f"verticals.{name}.freshness_score_by_value.high must be in [0,1]")
                if not (0.0 <= low <= 1.0):
                    errors.append(f"verticals.{name}.freshness_score_by_value.low must be in [0,1]")

    category_mapping = raw.get("category_mapping", {})
    if not isinstance(category_mapping, dict):
        errors.append("category_mapping must be object")
        category_mapping = {}
    keywords = category_mapping.get("keywords", {})
    if not isinstance(keywords, dict):
        errors.append("category_mapping.keywords must be object")
    fallback = to_str(category_mapping.get("fallback_vertical"))
    if not fallback:
        errors.append("category_mapping.fallback_vertical must be non-empty")
    elif fallback not in verticals:
        errors.append("category_mapping.fallback_vertical must exist in verticals")

    legacy_patterns = raw.get("legacy_patterns", [])
    if not isinstance(legacy_patterns, list):
        errors.append("legacy_patterns must be list")
        legacy_patterns = []
    for idx, item in enumerate(legacy_patterns):
        if not isinstance(item, dict):
            errors.append(f"legacy_patterns[{idx}] must be object")
            continue
        pattern = to_str(item.get("pattern"))
        if not pattern:
            errors.append(f"legacy_patterns[{idx}].pattern must be non-empty")
        pattern_type = to_str(item.get("pattern_type"), "substring").lower()
        if pattern_type not in ALLOWED_PATTERN_TYPES:
            errors.append(f"legacy_patterns[{idx}].pattern_type unsupported: {pattern_type}")
        penalty = to_float(item.get("penalty"), -1.0)
        if not (0.0 <= penalty <= 1.0):
            errors.append(f"legacy_patterns[{idx}].penalty must be in [0,1]")
        if pattern and pattern_type == "regex":
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(f"legacy_patterns[{idx}].pattern regex compile failed: {exc}")

    precedence = raw.get("classification_precedence")
    if not isinstance(precedence, list) or not precedence:
        errors.append("classification_precedence must be non-empty list")

    return errors


def _build_profile(raw: dict[str, Any], *, filename_brand: str) -> BrandProfile:
    brand = to_str(raw.get("brand"), filename_brand).lower() or filename_brand
    tuning = dict(raw.get("tuning_params", {}))
    tuning.setdefault("alpha_freshness_impact", 0.65)
    tuning.setdefault("cps_floor", 0.35)
    tuning.setdefault("reject_abs_usd_ceil", 50000.0)
    tuning.setdefault("legacy_combinator_mode", "max")

    verticals_raw = raw.get("verticals", {})
    verticals: dict[str, VerticalConfig] = {}
    for name in sorted(verticals_raw.keys()):
        payload = verticals_raw[name]
        if not isinstance(payload, dict):
            continue
        freshness_score = payload.get("freshness_score")
        verticals[name] = VerticalConfig(
            tier=to_str(payload.get("tier"), "unknown"),
            purity_weight=clamp(to_float(payload.get("purity_weight"), 0.0), 0.0, 1.0),
            obsolescence_score=clamp(to_float(payload.get("obsolescence_score"), 0.0), 0.0, 1.0),
            freshness_score=None if freshness_score is None else clamp(to_float(freshness_score, 0.0), 0.0, 1.0),
            freshness_score_by_value=(
                dict(payload.get("freshness_score_by_value"))
                if isinstance(payload.get("freshness_score_by_value"), dict)
                else None
            ),
            reject=bool(payload.get("reject")),
        )

    category_mapping = raw.get("category_mapping", {})
    fallback_vertical = to_str(category_mapping.get("fallback_vertical"))

    legacy_patterns_raw = raw.get("legacy_patterns", [])
    compiled_patterns: list[LegacyPatternRule] = []
    for item in legacy_patterns_raw:
        if not isinstance(item, dict):
            continue
        pattern = to_str(item.get("pattern"))
        pattern_type = to_str(item.get("pattern_type"), "substring").lower()
        penalty = clamp(to_float(item.get("penalty"), 0.0), 0.0, 1.0)
        reason = to_str(item.get("reason"))
        compiled_regex: Pattern[str] | None = None
        if pattern_type == "regex":
            compiled_regex = re.compile(pattern)
        compiled_patterns.append(
            LegacyPatternRule(
                pattern=pattern,
                pattern_type=pattern_type,
                penalty=penalty,
                reason=reason,
                compiled_regex=compiled_regex,
            )
        )

    precedence_raw = raw.get("classification_precedence", [])
    precedence = tuple(to_str(item).lower() for item in precedence_raw if to_str(item))
    if not precedence:
        precedence = ("legacy_patterns", "category_mapping.keywords", "fallback_vertical")

    return BrandProfile(
        brand=brand,
        metadata=dict(raw.get("metadata", {})),
        tuning_params=tuning,
        verticals=verticals,
        category_mapping=dict(category_mapping),
        legacy_patterns=tuple(compiled_patterns),
        classification_precedence=precedence,
        fallback_vertical=fallback_vertical,
    )


def load_brand_profile(brand: str, base_dir: Path | None = None) -> BrandProfile | None:
    normalized = to_str(brand).strip().lower()
    if not normalized:
        return None
    candidate = _root_dir(base_dir) / f"{normalized}.json"
    if not candidate.exists():
        return None
    raw_payload = json.loads(candidate.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, dict):
        raise ValueError(f"Expected JSON object in {candidate}")
    errors = validate_brand_profile(raw_payload)
    if errors:
        raise ValueError(f"Invalid brand profile {candidate}: " + "; ".join(errors))
    return _build_profile(raw_payload, filename_brand=normalized)


def load_all_brand_profiles(base_dir: Path | None = None) -> dict[str, BrandProfile]:
    root = _root_dir(base_dir)
    if not root.exists() or not root.is_dir():
        return {}
    profiles: dict[str, BrandProfile] = {}
    for path in sorted(root.glob("*.json")):
        brand = path.stem.lower()
        profile = load_brand_profile(brand, base_dir=root)
        if profile is None:
            continue
        profiles[profile.brand] = profile
    return profiles
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from re import Pattern
from typing import Any

from scripts.lot_scoring.pipeline.helpers import clamp, to_float, to_str

_REQUIRED_TOP_LEVEL = (
    "schema_version",
    "brand",
    "metadata",
    "tuning_params",
    "verticals",
    "category_mapping",
    "legacy_patterns",
    "classification_precedence",
)
_ALLOWED_PATTERN_TYPES = {"regex", "substring", "exact"}
_ALLOWED_PRECEDENCE_STEPS = {"legacy_patterns", "category_mapping.keywords", "fallback_vertical"}


@dataclass(frozen=True)
class LegacyPatternRule:
    pattern: str
    pattern_type: str
    penalty: float
    reason: str
    compiled_regex: Pattern[str] | None = None


@dataclass(frozen=True)
class VerticalRule:
    name: str
    tier: str
    purity_weight: float
    obsolescence_score: float
    freshness_score: float
    reject: bool
    freshness_score_by_value: dict[str, float] | None = None


@dataclass(frozen=True)
class BrandProfile:
    schema_version: str
    brand: str
    metadata: dict[str, Any]
    alpha_freshness_impact: float
    cps_floor: float
    reject_abs_usd_ceil: float
    legacy_combinator_mode: str
    verticals: dict[str, VerticalRule]
    keyword_map: dict[str, str]
    fallback_vertical: str
    legacy_patterns: tuple[LegacyPatternRule, ...]
    classification_precedence: tuple[str, ...]


def _brand_data_root(base_dir: Path | None = None) -> Path:
    if base_dir is not None:
        return base_dir
    return Path(__file__).resolve().parents[1] / "data" / "brand_intelligence"


def _is_number(value: object) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def validate_brand_profile(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in _REQUIRED_TOP_LEVEL:
        if key not in payload:
            errors.append(f"Missing required top-level key: {key}")

    if errors:
        return errors

    tuning_params = payload.get("tuning_params")
    if not isinstance(tuning_params, dict):
        errors.append("tuning_params must be an object.")
    else:
        for key in ("alpha_freshness_impact", "cps_floor", "reject_abs_usd_ceil", "legacy_combinator_mode"):
            if key not in tuning_params:
                errors.append(f"tuning_params.{key} is required.")
        if "alpha_freshness_impact" in tuning_params and not _is_number(tuning_params.get("alpha_freshness_impact")):
            errors.append("tuning_params.alpha_freshness_impact must be numeric.")
        if "cps_floor" in tuning_params and not _is_number(tuning_params.get("cps_floor")):
            errors.append("tuning_params.cps_floor must be numeric.")
        if "reject_abs_usd_ceil" in tuning_params and not _is_number(tuning_params.get("reject_abs_usd_ceil")):
            errors.append("tuning_params.reject_abs_usd_ceil must be numeric.")
        combinator = to_str(tuning_params.get("legacy_combinator_mode"), "").lower()
        if combinator and combinator != "max":
            errors.append("tuning_params.legacy_combinator_mode must be 'max'.")

    verticals = payload.get("verticals")
    if not isinstance(verticals, dict) or not verticals:
        errors.append("verticals must be a non-empty object.")
    else:
        for vertical_name, vertical_payload in verticals.items():
            if not isinstance(vertical_payload, dict):
                errors.append(f"verticals.{vertical_name} must be an object.")
                continue
            required_vertical_keys = ("tier", "purity_weight", "obsolescence_score", "reject")
            for key in required_vertical_keys:
                if key not in vertical_payload:
                    errors.append(f"verticals.{vertical_name}.{key} is required.")
            if "purity_weight" in vertical_payload and not _is_number(vertical_payload.get("purity_weight")):
                errors.append(f"verticals.{vertical_name}.purity_weight must be numeric.")
            if "obsolescence_score" in vertical_payload and not _is_number(vertical_payload.get("obsolescence_score")):
                errors.append(f"verticals.{vertical_name}.obsolescence_score must be numeric.")
            has_freshness_score = "freshness_score" in vertical_payload and _is_number(vertical_payload.get("freshness_score"))
            has_by_value = isinstance(vertical_payload.get("freshness_score_by_value"), dict)
            if not has_freshness_score and not has_by_value:
                errors.append(
                    f"verticals.{vertical_name} must define freshness_score or freshness_score_by_value."
                )
            if has_by_value:
                by_value = vertical_payload.get("freshness_score_by_value")
                assert isinstance(by_value, dict)
                for key in ("high_threshold_usd", "high", "low"):
                    if key not in by_value or not _is_number(by_value.get(key)):
                        errors.append(f"verticals.{vertical_name}.freshness_score_by_value.{key} must be numeric.")

    category_mapping = payload.get("category_mapping")
    if not isinstance(category_mapping, dict):
        errors.append("category_mapping must be an object.")
    else:
        keywords = category_mapping.get("keywords")
        if not isinstance(keywords, dict):
            errors.append("category_mapping.keywords must be an object.")
        fallback_vertical = to_str(category_mapping.get("fallback_vertical"))
        if not fallback_vertical:
            errors.append("category_mapping.fallback_vertical is required.")
        elif isinstance(verticals, dict) and fallback_vertical not in verticals:
            errors.append("category_mapping.fallback_vertical must reference existing vertical.")
        if isinstance(keywords, dict) and isinstance(verticals, dict):
            for keyword, vertical_name in keywords.items():
                if not to_str(keyword):
                    errors.append("category_mapping.keywords contains empty keyword.")
                if to_str(vertical_name) not in verticals:
                    errors.append(f"category_mapping.keywords[{keyword}] references unknown vertical {vertical_name}.")

    legacy_patterns = payload.get("legacy_patterns")
    if not isinstance(legacy_patterns, list):
        errors.append("legacy_patterns must be a list.")
    else:
        for idx, entry in enumerate(legacy_patterns):
            if not isinstance(entry, dict):
                errors.append(f"legacy_patterns[{idx}] must be an object.")
                continue
            pattern = to_str(entry.get("pattern"))
            if not pattern:
                errors.append(f"legacy_patterns[{idx}].pattern is required.")
            pattern_type = to_str(entry.get("pattern_type")).lower()
            if pattern_type not in _ALLOWED_PATTERN_TYPES:
                errors.append(
                    f"legacy_patterns[{idx}].pattern_type must be one of: {sorted(_ALLOWED_PATTERN_TYPES)}"
                )
            penalty = entry.get("penalty")
            if not _is_number(penalty):
                errors.append(f"legacy_patterns[{idx}].penalty must be numeric.")
            else:
                penalty_f = to_float(penalty, -1.0)
                if penalty_f < 0.0 or penalty_f > 1.0:
                    errors.append(f"legacy_patterns[{idx}].penalty must be in [0,1].")
            if not to_str(entry.get("reason")):
                errors.append(f"legacy_patterns[{idx}].reason is required.")
            if pattern_type == "regex" and pattern:
                try:
                    re.compile(pattern, flags=re.IGNORECASE)
                except re.error as exc:
                    errors.append(f"legacy_patterns[{idx}] regex compile error: {exc}")

    precedence = payload.get("classification_precedence")
    if not isinstance(precedence, list) or not precedence:
        errors.append("classification_precedence must be a non-empty list.")
    else:
        for idx, step in enumerate(precedence):
            step_text = to_str(step)
            if step_text not in _ALLOWED_PRECEDENCE_STEPS:
                errors.append(
                    f"classification_precedence[{idx}] must be one of: {sorted(_ALLOWED_PRECEDENCE_STEPS)}"
                )

    return sorted(errors)


def _parse_legacy_rules(raw_rules: list[dict[str, Any]]) -> tuple[LegacyPatternRule, ...]:
    parsed: list[LegacyPatternRule] = []
    for entry in raw_rules:
        pattern = to_str(entry.get("pattern"))
        pattern_type = to_str(entry.get("pattern_type")).lower()
        compiled: Pattern[str] | None = None
        if pattern_type == "regex":
            compiled = re.compile(pattern, flags=re.IGNORECASE)
        parsed.append(
            LegacyPatternRule(
                pattern=pattern,
                pattern_type=pattern_type,
                penalty=clamp(to_float(entry.get("penalty"), 0.0), 0.0, 1.0),
                reason=to_str(entry.get("reason")),
                compiled_regex=compiled,
            )
        )
    return tuple(parsed)


def _parse_verticals(raw_verticals: dict[str, Any]) -> dict[str, VerticalRule]:
    parsed: dict[str, VerticalRule] = {}
    for name in sorted(raw_verticals.keys()):
        item = raw_verticals[name]
        by_value_raw = item.get("freshness_score_by_value")
        freshness_by_value: dict[str, float] | None = None
        if isinstance(by_value_raw, dict):
            freshness_by_value = {
                "high_threshold_usd": max(0.0, to_float(by_value_raw.get("high_threshold_usd"), 0.0)),
                "high": clamp(to_float(by_value_raw.get("high"), 0.0), 0.0, 1.0),
                "low": clamp(to_float(by_value_raw.get("low"), 0.0), 0.0, 1.0),
            }
        parsed[name] = VerticalRule(
            name=name,
            tier=to_str(item.get("tier")),
            purity_weight=clamp(to_float(item.get("purity_weight"), 0.0), 0.0, 1.0),
            obsolescence_score=clamp(to_float(item.get("obsolescence_score"), 0.0), 0.0, 1.0),
            freshness_score=clamp(to_float(item.get("freshness_score"), 0.0), 0.0, 1.0),
            reject=bool(item.get("reject")),
            freshness_score_by_value=freshness_by_value,
        )
    return parsed


def _build_profile(payload: dict[str, Any]) -> BrandProfile:
    tuning_params = payload["tuning_params"]
    category_mapping = payload["category_mapping"]
    keyword_map_raw = category_mapping.get("keywords", {})
    keyword_map = {
        to_str(keyword).lower(): to_str(vertical_name)
        for keyword, vertical_name in sorted(keyword_map_raw.items(), key=lambda pair: to_str(pair[0]).lower())
        if to_str(keyword)
    }
    profile = BrandProfile(
        schema_version=to_str(payload.get("schema_version")),
        brand=to_str(payload.get("brand")).lower(),
        metadata=dict(payload.get("metadata", {})),
        alpha_freshness_impact=clamp(to_float(tuning_params.get("alpha_freshness_impact"), 0.65), 0.0, 1.0),
        cps_floor=clamp(to_float(tuning_params.get("cps_floor"), 0.35), -1.0, 1.0),
        reject_abs_usd_ceil=max(0.0, to_float(tuning_params.get("reject_abs_usd_ceil"), 50000.0)),
        legacy_combinator_mode=to_str(tuning_params.get("legacy_combinator_mode"), "max").lower(),
        verticals=_parse_verticals(payload["verticals"]),
        keyword_map=keyword_map,
        fallback_vertical=to_str(category_mapping.get("fallback_vertical")),
        legacy_patterns=_parse_legacy_rules(payload.get("legacy_patterns", [])),
        classification_precedence=tuple(to_str(step) for step in payload.get("classification_precedence", [])),
    )
    return profile


def load_brand_profile(brand: str, *, base_dir: Path | None = None) -> BrandProfile | None:
    brand_key = to_str(brand).lower()
    if not brand_key:
        return None
    root = _brand_data_root(base_dir)
    target = root / f"{brand_key}.json"
    if not target.exists():
        return None
    with target.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Brand profile must be a JSON object: {target}")
    errors = validate_brand_profile(payload)
    if errors:
        joined = "; ".join(errors)
        raise ValueError(f"Invalid brand profile {target.name}: {joined}")
    return _build_profile(payload)


def load_all_brand_profiles(*, base_dir: Path | None = None) -> dict[str, BrandProfile]:
    root = _brand_data_root(base_dir)
    if not root.exists() or not root.is_dir():
        return {}
    profiles: dict[str, BrandProfile] = {}
    for path in sorted(root.glob("*.json"), key=lambda file: file.name.lower()):
        profile = load_brand_profile(path.stem, base_dir=root)
        if profile is not None:
            profiles[profile.brand] = profile
    return profiles

"""


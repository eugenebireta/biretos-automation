from __future__ import annotations

from typing import Any

from scripts.lot_scoring.pipeline.helpers import clamp, to_float, to_str
from scripts.lot_scoring.pipeline.intelligence_loader import BrandProfile, VerticalConfig

KEYWORD_PRECEDENCE_KEYS = {"category_mapping.keywords", "keyword_map", "keywords"}
FALLBACK_PRECEDENCE_KEYS = {"fallback_vertical", "fallback"}
LEGACY_PRECEDENCE_KEYS = {"legacy_patterns", "pn_patterns", "legacy"}


def _normalize_pn(value: object) -> str:
    return "".join(ch for ch in to_str(value).upper() if ch.isalnum())


def _extract_sku_pn(sku: dict[str, Any]) -> str:
    for key in ("sku_code_normalized", "sku_code", "sku", "part_number", "model"):
        token = _normalize_pn(sku.get(key))
        if token:
            return token
    return ""


def _sku_text(sku: dict[str, Any]) -> str:
    candidates = (
        sku.get("description"),
        sku.get("name"),
        sku.get("title"),
        sku.get("full_row_text"),
        sku.get("category_raw"),
        sku.get("category"),
    )
    return " ".join(to_str(item).lower() for item in candidates if to_str(item))


def _match_keyword_vertical(sku: dict[str, Any], profile: BrandProfile) -> str | None:
    mapping = profile.category_mapping.get("keywords", {})
    if not isinstance(mapping, dict):
        return None
    haystack = _sku_text(sku)
    if not haystack:
        return None

    pairs = []
    for key, vertical in mapping.items():
        keyword = to_str(key).strip().lower()
        vertical_name = to_str(vertical).strip()
        if not keyword or not vertical_name:
            continue
        pairs.append((keyword, vertical_name))
    pairs.sort(key=lambda pair: (-len(pair[0]), pair[0], pair[1]))

    for keyword, vertical in pairs:
        if keyword in haystack:
            return vertical
    return None


def _legacy_penalty_max(sku: dict[str, Any], profile: BrandProfile) -> float:
    pn = _extract_sku_pn(sku)
    if not pn:
        return 0.0
    pn_lower = pn.lower()
    penalties: list[float] = []
    for rule in profile.legacy_patterns:
        if rule.pattern_type == "regex":
            if rule.compiled_regex is not None and rule.compiled_regex.search(pn):
                penalties.append(rule.penalty)
            continue
        if rule.pattern_type == "exact":
            if rule.pattern.lower() == pn_lower:
                penalties.append(rule.penalty)
            continue
        if rule.pattern.lower() in pn_lower:
            penalties.append(rule.penalty)

    if not penalties:
        return 0.0
    combinator = to_str(profile.tuning_params.get("legacy_combinator_mode"), "max").lower()
    if combinator == "max":
        return clamp(max(penalties), 0.0, 1.0)
    return clamp(max(penalties), 0.0, 1.0)


def _resolve_vertical(sku: dict[str, Any], profile: BrandProfile) -> str:
    keyword_vertical = _match_keyword_vertical(sku, profile)
    fallback_vertical = profile.fallback_vertical

    for stage in profile.classification_precedence:
        normalized_stage = to_str(stage).lower()
        if normalized_stage in LEGACY_PRECEDENCE_KEYS:
            continue
        if normalized_stage in KEYWORD_PRECEDENCE_KEYS:
            if keyword_vertical:
                return keyword_vertical
            continue
        if normalized_stage in FALLBACK_PRECEDENCE_KEYS:
            return fallback_vertical

    if keyword_vertical:
        return keyword_vertical
    return fallback_vertical


def _resolve_freshness(vertical: VerticalConfig, sku: dict[str, Any]) -> float:
    dynamic = vertical.freshness_score_by_value
    if isinstance(dynamic, dict):
        threshold = max(0.0, to_float(dynamic.get("high_threshold_usd"), 0.0))
        high = clamp(to_float(dynamic.get("high"), 0.0), 0.0, 1.0)
        low = clamp(to_float(dynamic.get("low"), 0.0), 0.0, 1.0)
        line_value = max(0.0, to_float(sku.get("effective_line_usd"), 0.0))
        return high if line_value >= threshold else low
    return clamp(to_float(vertical.freshness_score, 0.0), 0.0, 1.0)


def detect_brand(sku: dict[str, Any], profiles: dict[str, BrandProfile]) -> str | None:
    brand = to_str(sku.get("brand")).strip().lower()
    if brand in profiles:
        return brand
    return None


def classify_sku(sku: dict[str, Any], profile: BrandProfile) -> dict[str, Any]:
    vertical_name = _resolve_vertical(sku, profile)
    vertical = profile.verticals.get(vertical_name)
    if vertical is None:
        vertical_name = profile.fallback_vertical
        vertical = profile.verticals.get(vertical_name)
    if vertical is None:
        return {}

    legacy_penalty = _legacy_penalty_max(sku, profile)
    freshness_base = _resolve_freshness(vertical, sku)
    freshness_adjusted = clamp(freshness_base * (1.0 - legacy_penalty), 0.0, 1.0)
    alpha = clamp(to_float(profile.tuning_params.get("alpha_freshness_impact"), 0.65), 0.0, 1.0)
    brand_obs = clamp(vertical.obsolescence_score * (1.0 - freshness_adjusted * alpha), 0.0, 1.0)

    return {
        "brand_detected": profile.brand,
        "brand_vertical": vertical_name,
        "brand_legacy_penalty": round(legacy_penalty, 6),
        "brand_freshness_score": round(freshness_adjusted, 6),
        "brand_obs": round(brand_obs, 6),
    }


def classify_lot_skus(all_skus: list[dict[str, Any]], profiles: dict[str, BrandProfile]) -> list[dict[str, Any]]:
    if not profiles:
        return all_skus
    for sku in all_skus:
        if not isinstance(sku, dict):
            continue
        brand = detect_brand(sku, profiles)
        if not brand:
            continue
        payload = classify_sku(sku, profiles[brand])
        if payload:
            sku.update(payload)
    return all_skus
"""
from __future__ import annotations

from typing import Any

from scripts.lot_scoring.pipeline.helpers import clamp, to_float, to_str
from scripts.lot_scoring.pipeline.intelligence_loader import BrandProfile, VerticalConfig

KEYWORD_PRECEDENCE_KEYS = {"category_mapping.keywords", "keyword_map", "keywords"}
FALLBACK_PRECEDENCE_KEYS = {"fallback_vertical", "fallback"}
LEGACY_PRECEDENCE_KEYS = {"legacy_patterns", "pn_patterns", "legacy"}


def _normalize_pn(value: object) -> str:
    return "".join(ch for ch in to_str(value).upper() if ch.isalnum())


def _extract_sku_pn(sku: dict[str, Any]) -> str:
    for key in ("sku_code_normalized", "sku_code", "sku", "part_number", "model"):
        token = _normalize_pn(sku.get(key))
        if token:
            return token
    return ""


def _sku_text(sku: dict[str, Any]) -> str:
    candidates = (
        sku.get("description"),
        sku.get("name"),
        sku.get("title"),
        sku.get("full_row_text"),
        sku.get("category_raw"),
        sku.get("category"),
    )
    return " ".join(to_str(item).lower() for item in candidates if to_str(item))


def _match_keyword_vertical(sku: dict[str, Any], profile: BrandProfile) -> str | None:
    mapping = profile.category_mapping.get("keywords", {})
    if not isinstance(mapping, dict):
        return None
    haystack = _sku_text(sku)
    if not haystack:
        return None

    pairs = []
    for key, vertical in mapping.items():
        keyword = to_str(key).strip().lower()
        vertical_name = to_str(vertical).strip()
        if not keyword or not vertical_name:
            continue
        pairs.append((keyword, vertical_name))
    pairs.sort(key=lambda pair: (-len(pair[0]), pair[0], pair[1]))

    for keyword, vertical in pairs:
        if keyword in haystack:
            return vertical
    return None


def _legacy_penalty_max(sku: dict[str, Any], profile: BrandProfile) -> float:
    pn = _extract_sku_pn(sku)
    if not pn:
        return 0.0
    pn_lower = pn.lower()
    penalties: list[float] = []
    for rule in profile.legacy_patterns:
        if rule.pattern_type == "regex":
            if rule.compiled_regex is not None and rule.compiled_regex.search(pn):
                penalties.append(rule.penalty)
            continue
        if rule.pattern_type == "exact":
            if rule.pattern.lower() == pn_lower:
                penalties.append(rule.penalty)
            continue
        if rule.pattern.lower() in pn_lower:
            penalties.append(rule.penalty)

    if not penalties:
        return 0.0
    combinator = to_str(profile.tuning_params.get("legacy_combinator_mode"), "max").lower()
    if combinator == "max":
        return clamp(max(penalties), 0.0, 1.0)
    return clamp(max(penalties), 0.0, 1.0)


def _resolve_vertical(sku: dict[str, Any], profile: BrandProfile) -> str:
    keyword_vertical = _match_keyword_vertical(sku, profile)
    fallback_vertical = profile.fallback_vertical

    for stage in profile.classification_precedence:
        normalized_stage = to_str(stage).lower()
        if normalized_stage in LEGACY_PRECEDENCE_KEYS:
            continue
        if normalized_stage in KEYWORD_PRECEDENCE_KEYS:
            if keyword_vertical:
                return keyword_vertical
            continue
        if normalized_stage in FALLBACK_PRECEDENCE_KEYS:
            return fallback_vertical

    if keyword_vertical:
        return keyword_vertical
    return fallback_vertical


def _resolve_freshness(vertical: VerticalConfig, sku: dict[str, Any]) -> float:
    dynamic = vertical.freshness_score_by_value
    if isinstance(dynamic, dict):
        threshold = max(0.0, to_float(dynamic.get("high_threshold_usd"), 0.0))
        high = clamp(to_float(dynamic.get("high"), 0.0), 0.0, 1.0)
        low = clamp(to_float(dynamic.get("low"), 0.0), 0.0, 1.0)
        line_value = max(0.0, to_float(sku.get("effective_line_usd"), 0.0))
        return high if line_value >= threshold else low
    return clamp(to_float(vertical.freshness_score, 0.0), 0.0, 1.0)


def detect_brand(sku: dict[str, Any], profiles: dict[str, BrandProfile]) -> str | None:
    brand = to_str(sku.get("brand")).strip().lower()
    if brand in profiles:
        return brand
    return None


def classify_sku(sku: dict[str, Any], profile: BrandProfile) -> dict[str, Any]:
    vertical_name = _resolve_vertical(sku, profile)
    vertical = profile.verticals.get(vertical_name)
    if vertical is None:
        vertical_name = profile.fallback_vertical
        vertical = profile.verticals.get(vertical_name)
    if vertical is None:
        return {}

    legacy_penalty = _legacy_penalty_max(sku, profile)
    freshness_base = _resolve_freshness(vertical, sku)
    freshness_adjusted = clamp(freshness_base * (1.0 - legacy_penalty), 0.0, 1.0)
    alpha = clamp(to_float(profile.tuning_params.get("alpha_freshness_impact"), 0.65), 0.0, 1.0)
    brand_obs = clamp(vertical.obsolescence_score * (1.0 - freshness_adjusted * alpha), 0.0, 1.0)

    return {
        "brand_detected": profile.brand,
        "brand_vertical": vertical_name,
        "brand_legacy_penalty": round(legacy_penalty, 6),
        "brand_freshness_score": round(freshness_adjusted, 6),
        "brand_obs": round(brand_obs, 6),
    }


def classify_lot_skus(all_skus: list[dict[str, Any]], profiles: dict[str, BrandProfile]) -> list[dict[str, Any]]:
    if not profiles:
        return all_skus
    for sku in all_skus:
        if not isinstance(sku, dict):
            continue
        brand = detect_brand(sku, profiles)
        if not brand:
            continue
        payload = classify_sku(sku, profiles[brand])
        if payload:
            sku.update(payload)
    return all_skus
from __future__ import annotations

from typing import Any

from scripts.lot_scoring.pipeline.helpers import clamp, to_float, to_str
from scripts.lot_scoring.pipeline.intelligence_loader import BrandProfile, VerticalConfig

KEYWORD_PRECEDENCE_KEYS = {"category_mapping.keywords", "keyword_map", "keywords"}
FALLBACK_PRECEDENCE_KEYS = {"fallback_vertical", "fallback"}
LEGACY_PRECEDENCE_KEYS = {"legacy_patterns", "pn_patterns", "legacy"}


def _normalize_pn(value: object) -> str:
    return "".join(ch for ch in to_str(value).upper() if ch.isalnum())


def _extract_sku_pn(sku: dict[str, Any]) -> str:
    for key in ("sku_code_normalized", "sku_code", "sku", "part_number", "model"):
        token = _normalize_pn(sku.get(key))
        if token:
            return token
    return ""


def _sku_text(sku: dict[str, Any]) -> str:
    candidates = (
        sku.get("description"),
        sku.get("name"),
        sku.get("title"),
        sku.get("full_row_text"),
        sku.get("category_raw"),
        sku.get("category"),
    )
    return " ".join(to_str(item).lower() for item in candidates if to_str(item))


def _match_keyword_vertical(sku: dict[str, Any], profile: BrandProfile) -> str | None:
    mapping = profile.category_mapping.get("keywords", {})
    if not isinstance(mapping, dict):
        return None
    haystack = _sku_text(sku)
    if not haystack:
        return None

    pairs = []
    for key, vertical in mapping.items():
        keyword = to_str(key).strip().lower()
        vertical_name = to_str(vertical).strip()
        if not keyword or not vertical_name:
            continue
        pairs.append((keyword, vertical_name))
    pairs.sort(key=lambda pair: (-len(pair[0]), pair[0], pair[1]))

    for keyword, vertical in pairs:
        if keyword in haystack:
            return vertical
    return None


def _legacy_penalty_max(sku: dict[str, Any], profile: BrandProfile) -> float:
    pn = _extract_sku_pn(sku)
    if not pn:
        return 0.0
    pn_lower = pn.lower()
    penalties: list[float] = []
    for rule in profile.legacy_patterns:
        if rule.pattern_type == "regex":
            if rule.compiled_regex is not None and rule.compiled_regex.search(pn):
                penalties.append(rule.penalty)
            continue
        if rule.pattern_type == "exact":
            if rule.pattern.lower() == pn_lower:
                penalties.append(rule.penalty)
            continue
        if rule.pattern.lower() in pn_lower:
            penalties.append(rule.penalty)

    if not penalties:
        return 0.0
    combinator = to_str(profile.tuning_params.get("legacy_combinator_mode"), "max").lower()
    if combinator == "max":
        return clamp(max(penalties), 0.0, 1.0)
    return clamp(max(penalties), 0.0, 1.0)


def _resolve_vertical(sku: dict[str, Any], profile: BrandProfile) -> str:
    keyword_vertical = _match_keyword_vertical(sku, profile)
    fallback_vertical = profile.fallback_vertical

    for stage in profile.classification_precedence:
        normalized_stage = to_str(stage).lower()
        if normalized_stage in LEGACY_PRECEDENCE_KEYS:
            continue
        if normalized_stage in KEYWORD_PRECEDENCE_KEYS:
            if keyword_vertical:
                return keyword_vertical
            continue
        if normalized_stage in FALLBACK_PRECEDENCE_KEYS:
            return fallback_vertical

    if keyword_vertical:
        return keyword_vertical
    return fallback_vertical


def _resolve_freshness(vertical: VerticalConfig, sku: dict[str, Any]) -> float:
    dynamic = vertical.freshness_score_by_value
    if isinstance(dynamic, dict):
        threshold = max(0.0, to_float(dynamic.get("high_threshold_usd"), 0.0))
        high = clamp(to_float(dynamic.get("high"), 0.0), 0.0, 1.0)
        low = clamp(to_float(dynamic.get("low"), 0.0), 0.0, 1.0)
        line_value = max(0.0, to_float(sku.get("effective_line_usd"), 0.0))
        return high if line_value >= threshold else low
    return clamp(to_float(vertical.freshness_score, 0.0), 0.0, 1.0)


def detect_brand(sku: dict[str, Any], profiles: dict[str, BrandProfile]) -> str | None:
    brand = to_str(sku.get("brand")).strip().lower()
    if brand in profiles:
        return brand
    return None


def classify_sku(sku: dict[str, Any], profile: BrandProfile) -> dict[str, Any]:
    vertical_name = _resolve_vertical(sku, profile)
    vertical = profile.verticals.get(vertical_name)
    if vertical is None:
        vertical_name = profile.fallback_vertical
        vertical = profile.verticals.get(vertical_name)
    if vertical is None:
        return {}

    legacy_penalty = _legacy_penalty_max(sku, profile)
    freshness_base = _resolve_freshness(vertical, sku)
    freshness_adjusted = clamp(freshness_base * (1.0 - legacy_penalty), 0.0, 1.0)
    alpha = clamp(to_float(profile.tuning_params.get("alpha_freshness_impact"), 0.65), 0.0, 1.0)
    brand_obs = clamp(vertical.obsolescence_score * (1.0 - freshness_adjusted * alpha), 0.0, 1.0)

    return {
        "brand_detected": profile.brand,
        "brand_vertical": vertical_name,
        "brand_legacy_penalty": round(legacy_penalty, 6),
        "brand_freshness_score": round(freshness_adjusted, 6),
        "brand_obs": round(brand_obs, 6),
    }


def classify_lot_skus(all_skus: list[dict[str, Any]], profiles: dict[str, BrandProfile]) -> list[dict[str, Any]]:
    if not profiles:
        return all_skus
    for sku in all_skus:
        if not isinstance(sku, dict):
            continue
        brand = detect_brand(sku, profiles)
        if not brand:
            continue
        payload = classify_sku(sku, profiles[brand])
        if payload:
            sku.update(payload)
    return all_skus
from __future__ import annotations

import re
from dataclasses import dataclass

from scripts.lot_scoring.pipeline.helpers import clamp, to_float, to_str
from scripts.lot_scoring.pipeline.intelligence_loader import BrandProfile, VerticalRule


@dataclass(frozen=True)
class BrandSkuClassification:
    brand: str
    vertical: str
    legacy_penalty: float
    freshness_score: float
    freshness_adjusted: float
    brand_obs: float


def _normalize_brand(value: object) -> str:
    text = to_str(value).lower()
    text = text.replace("-", "_").replace(" ", "_")
    return re.sub(r"[^a-z0-9_]+", "", text)


def _normalize_pn(value: object) -> str:
    text = to_str(value).upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def _line_eligible_for_total(sku: dict) -> bool:
    q_has_qty = sku.get("q_has_qty")
    has_qty = q_has_qty is not False
    has_line = sku.get("effective_line_usd") is not None
    return has_qty and has_line


def _line_effective_usd(sku: dict) -> float:
    return max(0.0, to_float(sku.get("effective_line_usd"), 0.0))


def _sku_text_blob(sku: dict) -> str:
    parts = [
        to_str(sku.get("raw_text")),
        to_str(sku.get("description")),
        to_str(sku.get("sku_description")),
        to_str(sku.get("full_text")),
        to_str(sku.get("sku")),
        to_str(sku.get("sku_code")),
        to_str(sku.get("sku_code_normalized")),
        to_str(sku.get("part_number")),
        to_str(sku.get("model")),
    ]
    return " ".join(part for part in parts if part).lower()


def _sku_pn_blob(sku: dict) -> str:
    candidates = (
        sku.get("sku_code_normalized"),
        sku.get("sku_code"),
        sku.get("sku"),
        sku.get("part_number"),
        sku.get("model"),
    )
    for candidate in candidates:
        normalized = _normalize_pn(candidate)
        if normalized:
            return normalized
    return ""


def _resolve_legacy_penalty(sku: dict, profile: BrandProfile) -> float:
    pn_blob = _sku_pn_blob(sku)
    if not pn_blob:
        return 0.0
    penalties: list[float] = []
    for rule in profile.legacy_patterns:
        if rule.pattern_type == "regex":
            compiled = rule.compiled_regex
            if compiled is not None and compiled.search(pn_blob):
                penalties.append(clamp(rule.penalty, 0.0, 1.0))
            continue
        pattern_normalized = _normalize_pn(rule.pattern)
        if not pattern_normalized:
            continue
        if rule.pattern_type == "exact" and pn_blob == pattern_normalized:
            penalties.append(clamp(rule.penalty, 0.0, 1.0))
        elif rule.pattern_type == "substring" and pattern_normalized in pn_blob:
            penalties.append(clamp(rule.penalty, 0.0, 1.0))
    if not penalties:
        return 0.0
    # Contract v4.1: combinator_mode == "max"
    return max(penalties)


def _resolve_keyword_vertical(sku: dict, profile: BrandProfile) -> str:
    text_blob = _sku_text_blob(sku)
    if not text_blob:
        return ""
    ordered_keywords = sorted(profile.keyword_map.keys(), key=lambda item: (-len(item), item))
    for keyword in ordered_keywords:
        if keyword and keyword in text_blob:
            return profile.keyword_map[keyword]
    return ""


def _resolve_freshness(vertical: VerticalRule, sku: dict) -> float:
    by_value = vertical.freshness_score_by_value
    if isinstance(by_value, dict):
        threshold = max(0.0, to_float(by_value.get("high_threshold_usd"), 0.0))
        high_value = clamp(to_float(by_value.get("high"), vertical.freshness_score), 0.0, 1.0)
        low_value = clamp(to_float(by_value.get("low"), vertical.freshness_score), 0.0, 1.0)
        line_usd = _line_effective_usd(sku) if _line_eligible_for_total(sku) else 0.0
        return high_value if line_usd >= threshold else low_value
    return clamp(vertical.freshness_score, 0.0, 1.0)


def detect_brand(sku: dict, profiles: dict[str, BrandProfile]) -> str | None:
    if not profiles:
        return None
    brand_token = _normalize_brand(sku.get("brand"))
    if brand_token in profiles:
        return brand_token

    text_blob = _sku_text_blob(sku)
    if text_blob:
        for candidate in sorted(profiles.keys()):
            if candidate and candidate in text_blob:
                return candidate
    return None


def classify_sku(sku: dict, profile: BrandProfile) -> BrandSkuClassification:
    vertical_name = ""
    legacy_penalty = 0.0
    seen_legacy_step = False

    for step in profile.classification_precedence:
        if step == "legacy_patterns":
            legacy_penalty = _resolve_legacy_penalty(sku, profile)
            seen_legacy_step = True
        elif step == "category_mapping.keywords" and not vertical_name:
            vertical_name = _resolve_keyword_vertical(sku, profile)
        elif step == "fallback_vertical" and not vertical_name:
            vertical_name = profile.fallback_vertical

    if not seen_legacy_step:
        legacy_penalty = _resolve_legacy_penalty(sku, profile)
    if not vertical_name:
        vertical_name = profile.fallback_vertical

    vertical = profile.verticals.get(vertical_name, profile.verticals[profile.fallback_vertical])
    freshness_score = _resolve_freshness(vertical, sku)
    freshness_adjusted = clamp(freshness_score * (1.0 - legacy_penalty), 0.0, 1.0)
    brand_obs = clamp(
        vertical.obsolescence_score * (1.0 - freshness_adjusted * profile.alpha_freshness_impact),
        0.0,
        1.0,
    )
    return BrandSkuClassification(
        brand=profile.brand,
        vertical=vertical.name,
        legacy_penalty=round(legacy_penalty, 6),
        freshness_score=round(freshness_score, 6),
        freshness_adjusted=round(freshness_adjusted, 6),
        brand_obs=round(brand_obs, 6),
    )


def classify_lot_skus(all_skus: list[dict], profiles: dict[str, BrandProfile]) -> list[dict]:
    if not profiles:
        return all_skus

    for sku in all_skus:
        for field in (
            "brand_detected",
            "brand_vertical",
            "brand_legacy_penalty",
            "brand_freshness_score",
            "brand_freshness_adjusted",
            "brand_obs",
        ):
            sku.pop(field, None)

        detected_brand = detect_brand(sku, profiles)
        if detected_brand is None:
            continue
        profile = profiles.get(detected_brand)
        if profile is None:
            continue
        classified = classify_sku(sku, profile)
        sku["brand_detected"] = classified.brand
        sku["brand_vertical"] = classified.vertical
        sku["brand_legacy_penalty"] = classified.legacy_penalty
        sku["brand_freshness_score"] = classified.freshness_score
        sku["brand_freshness_adjusted"] = classified.freshness_adjusted
        sku["brand_obs"] = classified.brand_obs
    return all_skus

"""


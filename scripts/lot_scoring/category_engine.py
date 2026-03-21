from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from scripts.lot_scoring.pipeline.helpers import normalize_category_key, to_str


CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "gas_safety": ("gas", "h2s", "lel", "xnx", "bwc", "газ", "газо"),
    "fire_safety": ("fire", "smoke", "esser", "notifier", "iq8", "пожар", "извещ"),
    "hvac_components": ("hvac", "bacnet", "cpo", "controller", "климат", "вентиля"),
    "industrial_sensors": ("sensor", "transmitter", "plc", "relay", "датчик"),
    "valves_actuators": ("valve", "actuator", "клапан", "привод"),
    "it_hardware": ("mouse", "keyboard", "monitor", "pc", "server", "router", "switch", "ноутбук"),
    "packaging_materials": ("packaging", "box", "tape", "упаков", "короб"),
    "construction_supplies": ("screw", "bolt", "nut", "washer", "pipe", "винт", "труба"),
}

BRAND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "honeywell": ("honeywell",),
    "esser": ("esser",),
    "notifier": ("notifier",),
    "siemens": ("siemens",),
    "draeger": ("draeger",),
    "endress_hauser": ("endress", "hauser"),
    "schneider": ("schneider",),
    "abb": ("abb",),
    "emerson": ("emerson",),
}

VALID_CATEGORIES: frozenset[str] = frozenset(
    {
        "gas_safety",
        "fire_safety",
        "hvac_components",
        "industrial_sensors",
        "valves_actuators",
        "it_hardware",
        "packaging_materials",
        "construction_supplies",
        "toxic_fake",
        "unknown",
    }
)

# Invariant: multi-category brands are forbidden here.
# Brands like honeywell/siemens/abb/schneider/emerson must be resolved by P2/P3/P5.
BRAND_CATEGORY_MAP: dict[str, str] = {
    "esser": "fire_safety",
    "notifier": "fire_safety",
    "draeger": "gas_safety",
    "endress_hauser": "industrial_sensors",
}


@dataclass(frozen=True)
class CategoryResolution:
    category: str
    reason: str
    matched_rule: str


_DATA_DIR = Path(__file__).resolve().parent / "data"
_DEFAULT_SKU_LOOKUP_PATH = _DATA_DIR / "sku_lookup.json"
_DEFAULT_PN_PATTERNS_PATH = _DATA_DIR / "pn_patterns.json"
_DEFAULT_TAXONOMY_VERSION_PATH = _DATA_DIR / "taxonomy_version.json"
_LOOKUP_ALLOWED_CATEGORIES: frozenset[str] = frozenset(VALID_CATEGORIES - {"toxic_fake", "unknown"})

_SKU_LOOKUP: dict[str, str] = {}
_PN_PATTERN_RULES: list[tuple[str, re.Pattern[str], str]] = []
_TAXONOMY_VERSION: str = "v0.0-empty"


def _normalize_sku_key(value: object) -> str:
    text = to_str(value).upper().replace(" ", "")
    return re.sub(r"[^A-Z0-9]", "", text)


def _fixed_prefix_length(pattern: str) -> int:
    stripped = pattern[1:] if pattern.startswith("^") else pattern
    length = 0
    for ch in stripped:
        if ch in {".", "[", "]", "(", ")", "+", "*", "?", "{", "\\", "|", "^", "$"}:
            break
        length += 1
    return length


def _has_forbidden_dot_quantifier(pattern: str) -> bool:
    in_class = False
    escaped = False
    for idx, ch in enumerate(pattern):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "[" and not in_class:
            in_class = True
            continue
        if ch == "]" and in_class:
            in_class = False
            continue
        if not in_class and ch == "." and idx + 1 < len(pattern) and pattern[idx + 1] in {"*", "+"}:
            return True
    return False


def _validate_pn_pattern(entry: dict, index: int) -> tuple[str, str]:
    for field in ("pattern", "category", "comment", "author"):
        if field not in entry:
            raise ValueError(f"pn_patterns entry #{index} missing required field: {field}")

    pattern = to_str(entry.get("pattern"))
    category = normalize_category_key(entry.get("category"))
    comment = to_str(entry.get("comment"))
    author = to_str(entry.get("author"))

    if not pattern.startswith("^"):
        raise ValueError(f"pn_patterns entry #{index} must start with '^': {pattern}")
    if len(pattern) > 60:
        raise ValueError(f"pn_patterns entry #{index} exceeds max length 60: {pattern}")
    if _has_forbidden_dot_quantifier(pattern):
        raise ValueError(f"pn_patterns entry #{index} contains forbidden dot quantifier: {pattern}")
    if category not in _LOOKUP_ALLOWED_CATEGORIES:
        raise ValueError(
            f"pn_patterns entry #{index} category must be one of "
            f"{sorted(_LOOKUP_ALLOWED_CATEGORIES)}: {category}"
        )
    if not comment:
        raise ValueError(f"pn_patterns entry #{index} must include non-empty comment")
    if not author:
        raise ValueError(f"pn_patterns entry #{index} must include non-empty author")
    return pattern, category


def _load_sku_lookup(path: Path | None = None) -> dict[str, str]:
    target = path or _DEFAULT_SKU_LOOKUP_PATH
    if not target.exists():
        return {}
    with target.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"sku_lookup must be a JSON object: {target}")

    lookup: dict[str, str] = {}
    for raw_key, raw_category in payload.items():
        key = _normalize_sku_key(raw_key)
        if not key:
            raise ValueError(f"sku_lookup contains empty/invalid PN key: {raw_key!r}")
        category = normalize_category_key(raw_category)
        if category not in _LOOKUP_ALLOWED_CATEGORIES:
            raise ValueError(
                f"sku_lookup category must be one of {sorted(_LOOKUP_ALLOWED_CATEGORIES)}: {raw_category!r}"
            )
        lookup[key] = category
    return lookup


def _load_pn_patterns(path: Path | None = None) -> list[tuple[str, re.Pattern[str], str]]:
    target = path or _DEFAULT_PN_PATTERNS_PATH
    if not target.exists():
        return []
    with target.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"pn_patterns must be a JSON array: {target}")

    patterns: list[tuple[str, re.Pattern[str], str]] = []
    for idx, entry in enumerate(payload, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"pn_patterns entry #{idx} must be a JSON object")
        pattern_text, category = _validate_pn_pattern(entry, idx)
        try:
            compiled = re.compile(pattern_text, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"Invalid regex in pn_patterns entry #{idx}: {pattern_text}") from exc
        patterns.append((pattern_text, compiled, category))

    patterns.sort(key=lambda item: (-_fixed_prefix_length(item[0]), item[0]))
    return patterns


def _load_taxonomy_version(path: Path | None = None) -> str:
    target = path or _DEFAULT_TAXONOMY_VERSION_PATH
    if not target.exists():
        return "v0.0-empty"
    with target.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"taxonomy_version must be a JSON object: {target}")
    version = to_str(payload.get("version"))
    if not version:
        raise ValueError(f"taxonomy_version missing non-empty 'version': {target}")
    return version


def _init_taxonomy(
    *,
    sku_path: Path | None = None,
    patterns_path: Path | None = None,
    version_path: Path | None = None,
) -> None:
    global _SKU_LOOKUP, _PN_PATTERN_RULES, _TAXONOMY_VERSION
    _SKU_LOOKUP = _load_sku_lookup(sku_path)
    _PN_PATTERN_RULES = _load_pn_patterns(patterns_path)
    _TAXONOMY_VERSION = _load_taxonomy_version(version_path)


def reload_taxonomy(
    *,
    sku_path: str | Path | None = None,
    patterns_path: str | Path | None = None,
    version_path: str | Path | None = None,
) -> None:
    resolved_sku = Path(sku_path) if sku_path is not None else None
    resolved_patterns = Path(patterns_path) if patterns_path is not None else None
    resolved_version = Path(version_path) if version_path is not None else None
    _init_taxonomy(sku_path=resolved_sku, patterns_path=resolved_patterns, version_path=resolved_version)


def get_taxonomy_version() -> str:
    return _TAXONOMY_VERSION


_init_taxonomy()


def _matched_brands(text: str) -> list[str]:
    lowered = to_str(text).lower()
    matches: list[str] = []
    for brand, markers in BRAND_KEYWORDS.items():
        if all(marker in lowered for marker in markers):
            matches.append(brand)
    return matches


def normalize_brand(raw: str) -> str:
    matches = _matched_brands(raw)
    if len(matches) == 1:
        return matches[0]
    return ""


def infer_brand_from_text(full_row_text: str) -> str:
    matches = _matched_brands(full_row_text)
    if len(matches) == 1:
        return matches[0]
    return ""


def infer_category_from_text(full_row_text: str) -> str:
    lowered = to_str(full_row_text).lower()
    for category, markers in CATEGORY_KEYWORDS.items():
        if any(marker in lowered for marker in markers):
            return category
    return "unknown"


def resolve_category_detailed(
    *,
    explicit_category: str,
    explicit_brand: str,
    sku_code: str,
    full_row_text: str,
) -> CategoryResolution:
    normalized_explicit = normalize_category_key(explicit_category)
    if to_str(explicit_category) and normalized_explicit in VALID_CATEGORIES:
        return CategoryResolution(category=normalized_explicit, reason="P0_EXPLICIT", matched_rule=normalized_explicit)

    sku_key = _normalize_sku_key(sku_code)
    mapped_from_sku = _SKU_LOOKUP.get(sku_key, "")
    if mapped_from_sku in VALID_CATEGORIES:
        return CategoryResolution(category=mapped_from_sku, reason="P2_SKU_LOOKUP", matched_rule=sku_key)

    for pattern_text, pattern, category in _PN_PATTERN_RULES:
        if sku_key and pattern.search(sku_key):
            return CategoryResolution(category=category, reason="P3_PN_PATTERN", matched_rule=pattern_text)

    brand = normalize_brand(explicit_brand) or infer_brand_from_text(full_row_text)
    mapped_from_brand = BRAND_CATEGORY_MAP.get(brand, "")
    if mapped_from_brand:
        return CategoryResolution(category=mapped_from_brand, reason="P4_BRAND_MAP", matched_rule=brand)

    inferred = infer_category_from_text(full_row_text)
    if inferred in VALID_CATEGORIES and inferred != "unknown":
        return CategoryResolution(category=inferred, reason="P5_TEXT_KEYWORD", matched_rule=inferred)
    return CategoryResolution(category="unknown", reason="P6_UNKNOWN", matched_rule="")


def resolve_category(
    *,
    explicit_category: str,
    explicit_brand: str,
    sku_code: str,
    full_row_text: str,
) -> str:
    resolved = resolve_category_detailed(
        explicit_category=explicit_category,
        explicit_brand=explicit_brand,
        sku_code=sku_code,
        full_row_text=full_row_text,
    )
    return resolved.category


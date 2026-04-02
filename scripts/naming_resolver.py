"""Deterministic family-aware naming resolver."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional


CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "naming_families"
SCOUT_CACHE_DIR = Path(__file__).resolve().parent.parent / "downloads" / "scout_cache"
SCOUT_CACHE_FILE = SCOUT_CACHE_DIR / "naming_scout_cache.jsonl"
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
SCOUT_TOP_LEVEL_FIELDS = {
    "part_number",
    "brand_hint",
    "scouted_at",
    "scout_provider",
    "facts",
}
SCOUT_FACT_FIELDS = {
    "brand",
    "series",
    "product_type",
    "gang_count",
    "color",
    "source_url",
}


def _normalize_spaces(value: str) -> str:
    return " ".join(str(value).split()).strip()


def _stringify_specs(specs: Optional[dict[str, Any]]) -> str:
    if not isinstance(specs, dict):
        return ""
    bits: list[str] = []
    for key, value in specs.items():
        if value in (None, ""):
            continue
        bits.append(f"{key} {value}")
    return " ".join(bits)


def _contains(text: str, token: str) -> bool:
    return token.lower() in text.lower()


def load_scout_cache(cache_path: Optional[Path] = None) -> dict[str, dict[str, Any]]:
    SCOUT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = Path(cache_path) if cache_path else SCOUT_CACHE_FILE
    if not cache_file.exists():
        return {}

    cache: dict[str, dict[str, Any]] = {}
    for raw_line in cache_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if set(record.keys()) != SCOUT_TOP_LEVEL_FIELDS:
            continue
        facts = record.get("facts")
        if not isinstance(facts, dict) or set(facts.keys()) != SCOUT_FACT_FIELDS:
            continue
        part_number = str(record.get("part_number", "")).strip()
        if not part_number:
            continue
        cache[part_number] = record
    return cache


@lru_cache(maxsize=1)
def load_family_rules() -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    if not CONFIG_DIR.exists():
        return rules
    for path in sorted(CONFIG_DIR.glob("peha_*.json")):
        rules.append(json.loads(path.read_text(encoding="utf-8")))
    return rules


def _match_rule(rule: dict[str, Any], fields: dict[str, str], specs: dict[str, Any]) -> bool:
    match_fields = rule.get("match_fields", [])
    haystacks: list[str] = []
    for field in match_fields:
        if field == "specs":
            haystacks.append(_stringify_specs(specs))
        else:
            haystacks.append(str(fields.get(field, "")))

    for token in rule.get("match_any", []):
        if any(_contains(haystack, token) for haystack in haystacks):
            return True

    regex = rule.get("match_regex")
    if regex:
        compiled = re.compile(regex, re.IGNORECASE)
        if any(compiled.search(haystack) for haystack in haystacks):
            return True

    spec_key = rule.get("spec_key")
    if spec_key:
        return specs.get(spec_key) not in (None, "")

    return False


def _best_confidence(current: str, candidate: str) -> str:
    return candidate if CONFIDENCE_RANK[candidate] > CONFIDENCE_RANK[current] else current


def _confidence_from_basis(basis: str) -> str:
    if basis in {"explicit", "spec", "cache"}:
        return "high"
    if basis in {"token", "cluster", "series_frame_mapping"}:
        return "medium"
    return "low"


def _format_title(template: str, values: dict[str, Any]) -> str:
    safe_values = {key: value for key, value in values.items() if value not in (None, "")}
    try:
        formatted = template.format(**safe_values)
    except KeyError:
        return ""
    return _normalize_spaces(formatted.replace(", ,", ",").strip(" ,"))


def _family_id_from_series(series: Optional[str]) -> Optional[str]:
    if not series:
        return None
    series_upper = str(series).strip().upper()
    if series_upper == "NOVA":
        return "peha_nova"
    if series_upper == "AURA":
        return "peha_aura"
    if series_upper == "DIALOG":
        return "peha_dialog"
    if series_upper == "COMPACTA":
        return "peha_compacta"
    if series_upper == "GENERIC":
        return "peha_generic"
    return None


def _is_pattern_basis(basis: Optional[str]) -> bool:
    return basis in {"cluster", "series_frame_mapping"}


def _apply_cached_facts(
    decision: dict[str, Any],
    *,
    cached_record: Optional[dict[str, Any]],
) -> None:
    if not cached_record:
        return

    facts = cached_record.get("facts") or {}
    if not isinstance(facts, dict):
        return

    if facts.get("source_url"):
        decision["scout_source_url"] = facts["source_url"]

    series_basis = decision["field_basis"].get("series")
    if facts.get("series") and (not decision.get("series") or _is_pattern_basis(series_basis)):
        decision["series"] = facts["series"]
        decision["field_basis"]["series"] = "cache"
        decision["basis"].append(f"series:{decision['series']}:cache")
        decision["confidence_band"] = _best_confidence(decision["confidence_band"], "high")

    type_basis = decision["field_basis"].get("canonical_product_type")
    if facts.get("product_type") and (
        not decision.get("canonical_product_type") or _is_pattern_basis(type_basis)
    ):
        decision["canonical_product_type"] = facts["product_type"]
        decision["field_basis"]["canonical_product_type"] = "cache"
        decision["basis"].append(f"type:{decision['canonical_product_type']}:cache")
        decision["confidence_band"] = _best_confidence(decision["confidence_band"], "high")

    for attr_name, attr_value in {
        "gang_count": facts.get("gang_count"),
        "color": facts.get("color"),
    }.items():
        basis_key = f"attr:{attr_name}"
        attr_basis = decision["field_basis"].get(basis_key)
        if attr_value not in (None, "") and (
            decision["attributes"].get(attr_name) in (None, "")
            or _is_pattern_basis(attr_basis)
        ):
            decision["attributes"][attr_name] = attr_value
            decision["field_basis"][basis_key] = "cache"
            decision["basis"].append(f"attr:{attr_name}:cache")
            decision["confidence_band"] = _best_confidence(decision["confidence_band"], "high")


def _canonical_type_ru(canonical_type: Optional[str]) -> Optional[str]:
    mapping = {
        "rocker": "Клавиша",
        "socket": "Розетка",
        "insert": "Вставка",
        "decorative_element": "Центральная накладка",
        "switch": "Выключатель",
        "pushbutton": "Кнопка",
        "dimmer": "Диммер",
        "speaker_socket": "Акустическая розетка",
        "device_box": "Монтажная коробка",
        "frame": "Рамка",
    }
    return mapping.get(canonical_type)


def resolve_naming(
    *,
    part_number: str,
    raw_title: str,
    brand: str,
    subbrand: str = "",
    specs: Optional[dict[str, Any]] = None,
    cache_path: Optional[Path] = None,
) -> dict[str, Any]:
    specs = specs or {}
    scout_cache = load_scout_cache(cache_path)
    cached_record = scout_cache.get(part_number)
    cached_facts = cached_record.get("facts") if cached_record else {}
    cached_family = (
        _family_id_from_series(cached_facts.get("series"))
        if isinstance(cached_facts, dict)
        else None
    )
    fields = {
        "source_name": _normalize_spaces(raw_title),
        "raw_title": _normalize_spaces(raw_title),
        "brand": _normalize_spaces(brand),
        "subbrand": _normalize_spaces(subbrand),
        "spec_values": _stringify_specs(specs),
    }
    decision: dict[str, Any] = {
        "matched_family": None,
        "brand_final": None,
        "series": None,
        "canonical_product_type": None,
        "type_ru": None,
        "title_ru": None,
        "confidence_band": "low",
        "review_required": True,
        "review_reason_codes": ["family_unmatched"],
        "attributes": {},
        "basis": [],
        "field_basis": {},
        "scout_source_url": None,
    }

    family_rules_list = load_family_rules()
    if cached_family:
        family_rules_list = sorted(
            family_rules_list,
            key=lambda item: item["family"] != cached_family,
        )

    for family_rules in family_rules_list:
        matched_family = any(
            _match_rule(rule, fields, specs)
            for rule in family_rules.get("family_matchers", [])
        )
        if not matched_family and family_rules["family"] != cached_family:
            continue

        decision["matched_family"] = family_rules["family"]
        decision["brand_final"] = (
            family_rules.get("brand_final")
            or cached_facts.get("brand")
            or subbrand
            or brand
        )
        decision["review_reason_codes"] = []

        for series_rule in family_rules.get("series_patterns", []):
            if not _match_rule(series_rule, fields, specs):
                continue
            decision["series"] = series_rule.get("series")
            decision["field_basis"]["series"] = series_rule.get("basis", "unknown")
            decision["basis"].append(
                f"series:{decision['series']}:{series_rule.get('basis', 'unknown')}"
            )
            decision["confidence_band"] = _best_confidence(
                decision["confidence_band"],
                _confidence_from_basis(series_rule.get("basis", "")),
            )
            break

        for type_rule in family_rules.get("product_type_rules", []):
            if not _match_rule(type_rule, fields, specs):
                continue
            decision["canonical_product_type"] = type_rule.get("canonical_type")
            decision["type_ru"] = type_rule.get("type_ru")
            decision["field_basis"]["canonical_product_type"] = type_rule.get("basis", "unknown")
            decision["basis"].append(
                f"type:{decision['canonical_product_type']}:{type_rule.get('basis', 'unknown')}"
            )
            decision["confidence_band"] = _best_confidence(
                decision["confidence_band"],
                _confidence_from_basis(type_rule.get("basis", "")),
            )
            break

        for attr_name, attr_rules in family_rules.get("attribute_rules", {}).items():
            for attr_rule in attr_rules:
                if not _match_rule(attr_rule, fields, specs):
                    continue
                if "spec_key" in attr_rule:
                    decision["attributes"][attr_name] = specs.get(attr_rule["spec_key"])
                else:
                    decision["attributes"][attr_name] = attr_rule.get("value")
                decision["field_basis"][f"attr:{attr_name}"] = attr_rule.get("basis", "unknown")
                decision["basis"].append(
                    f"attr:{attr_name}:{attr_rule.get('basis', 'unknown')}"
                )
                decision["confidence_band"] = _best_confidence(
                    decision["confidence_band"],
                    _confidence_from_basis(attr_rule.get("basis", "")),
                )
                break

        _apply_cached_facts(decision, cached_record=cached_record)
        if not decision.get("type_ru"):
            decision["type_ru"] = _canonical_type_ru(decision.get("canonical_product_type"))

        missing = [
            field
            for field in family_rules.get("review_if_missing", [])
            if not decision.get(field)
        ]
        if missing:
            decision["review_reason_codes"].extend(f"missing_{field}" for field in missing)
            return decision

        template_id = decision["canonical_product_type"]
        if template_id == "frame" and decision["attributes"].get("gang_count"):
            template_id = "frame_with_gang_count"
        template = family_rules.get("title_templates", {}).get(template_id)
        if not template:
            decision["review_reason_codes"].append("missing_template")
            return decision

        decision["title_ru"] = _format_title(
            template,
            {
                "type_ru": decision["type_ru"],
                "brand": decision["brand_final"],
                "series": decision["series"],
                "part_number": part_number,
                "gang_count": decision["attributes"].get("gang_count"),
                "color": decision["attributes"].get("color"),
                "material": decision["attributes"].get("material"),
                "orientation": decision["attributes"].get("orientation"),
            },
        )
        if not decision["title_ru"]:
            decision["review_reason_codes"].append("missing_template_fields")
            return decision

        if any(
            forbidden.lower() in decision["title_ru"].lower()
            for forbidden in family_rules.get("forbidden_generic_titles", [])
        ):
            decision["review_reason_codes"].append("generic_title_detected")
            return decision

        decision["review_required"] = decision["confidence_band"] == "low"
        if decision["review_required"]:
            decision["review_reason_codes"].append("low_confidence")
        return decision

    return decision


def resolve_title_or_fallback(
    *,
    part_number: str,
    raw_title: str,
    brand: str,
    fallback_title: str,
    subbrand: str = "",
    specs: Optional[dict[str, Any]] = None,
    cache_path: Optional[Path] = None,
) -> tuple[str, dict[str, Any]]:
    decision = resolve_naming(
        part_number=part_number,
        raw_title=raw_title,
        brand=brand,
        subbrand=subbrand,
        specs=specs,
        cache_path=cache_path,
    )
    if not decision["review_required"] and decision.get("title_ru"):
        return decision["title_ru"], decision
    return fallback_title, decision

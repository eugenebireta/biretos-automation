from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.lot_scoring.category_engine import (
    BRAND_CATEGORY_MAP,
    CategoryResolution,
    get_taxonomy_version,
    infer_brand_from_text,
    infer_category_from_text,
    normalize_brand,
    reload_taxonomy,
    resolve_category,
    resolve_category_detailed,
)
from scripts.lot_scoring.run_full_ranking_v341 import _build_full_row_text, _first_non_empty_cell


def test_resolve_category_p0_explicit_wins() -> None:
    category = resolve_category(
        explicit_category="gas_safety",
        explicit_brand="",
        sku_code="ABC123",
        full_row_text="Esser smoke detector",
    )
    assert category == "gas_safety"


def test_resolve_category_p0_invalid_falls_through() -> None:
    category = resolve_category(
        explicit_category="not_a_real_category",
        explicit_brand="",
        sku_code="ABC123",
        full_row_text="Esser smoke detector",
    )
    assert category == "fire_safety"


def test_resolve_category_modern_missing_category_becomes_unknown() -> None:
    category = resolve_category(
        explicit_category="",
        explicit_brand="",
        sku_code="ROW1",
        full_row_text="783002",
    )
    assert category == "unknown"


def test_resolve_category_p2_brand_from_explicit_brand() -> None:
    category = resolve_category(
        explicit_category="",
        explicit_brand="Esser",
        sku_code="ABC123",
        full_row_text="unlabeled transponder",
    )
    assert category == "fire_safety"


def test_resolve_category_p2_brand_from_text_only() -> None:
    category = resolve_category(
        explicit_category="",
        explicit_brand="",
        sku_code="ABC123",
        full_row_text="783002 Esser module",
    )
    assert category == "fire_safety"


def test_resolve_category_p3_keyword_match() -> None:
    category = resolve_category(
        explicit_category="",
        explicit_brand="",
        sku_code="ABC123",
        full_row_text="industrial gas detector xnx h2s",
    )
    assert category == "gas_safety"


def test_resolve_category_p4_fallback_unknown_not_construction_supplies() -> None:
    category = resolve_category(
        explicit_category="",
        explicit_brand="",
        sku_code="ABC123",
        full_row_text="ABCD1234",
    )
    assert category == "unknown"


def test_infer_category_from_text_fire_beats_construction_in_mixed_text() -> None:
    assert infer_category_from_text("esser smoke detector pipe mount") == "fire_safety"


def test_infer_brand_from_text_returns_empty_on_ambiguity() -> None:
    assert infer_brand_from_text("honeywell esser module") == ""


def test_normalize_brand_maps_known_brand() -> None:
    assert normalize_brand("  ESSER  ") == "esser"


def test_lot16_report_merge_regression_full_row_text_restores_fire_safety() -> None:
    row_values = ["783002", "", "Esser IQ8 smoke detector transponder"]
    raw_text = _first_non_empty_cell(row_values)
    full_row_text = _build_full_row_text(row_values)

    # This reproduces the old failure mode: first non-empty cell is just SKU code.
    assert raw_text == "783002"
    assert infer_category_from_text(raw_text) == "unknown"

    resolved = resolve_category(
        explicit_category="",
        explicit_brand="",
        sku_code="783002",
        full_row_text=full_row_text,
    )
    assert resolved == "fire_safety"


def test_build_full_row_text_is_deterministic_and_skips_numeric_cells() -> None:
    row_values = ["783002", "  Esser IQ8 smoke detector  ", "10", "150.50", ""]
    text1 = _build_full_row_text(row_values)
    text2 = _build_full_row_text(list(row_values))

    assert text1 == "Esser IQ8 smoke detector"
    assert text1 == text2


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    return path


def test_resolve_category_returns_str_type() -> None:
    category = resolve_category(
        explicit_category="",
        explicit_brand="",
        sku_code="ABC123",
        full_row_text="unknown product",
    )
    assert isinstance(category, str)


def test_resolve_category_detailed_returns_dataclass() -> None:
    resolved = resolve_category_detailed(
        explicit_category="gas_safety",
        explicit_brand="",
        sku_code="ABC123",
        full_row_text="Esser smoke detector",
    )
    assert isinstance(resolved, CategoryResolution)
    assert resolved.category == "gas_safety"
    assert resolved.reason == "P0_EXPLICIT"


def test_p0_explicit_reason() -> None:
    resolved = resolve_category_detailed(
        explicit_category="fire_safety",
        explicit_brand="",
        sku_code="ABC123",
        full_row_text="anything",
    )
    assert resolved.reason == "P0_EXPLICIT"


def test_p2_sku_lookup_overrides_brand_and_text(tmp_path: Path) -> None:
    sku_path = _write_json(tmp_path / "sku_lookup.json", {"ABC123": "gas_safety"})
    patterns_path = _write_json(
        tmp_path / "pn_patterns.json",
        [
            {
                "pattern": "^ABC\\d+",
                "category": "fire_safety",
                "comment": "broad pattern",
                "author": "test",
            }
        ],
    )
    version_path = _write_json(tmp_path / "taxonomy_version.json", {"version": "v-test"})
    try:
        reload_taxonomy(sku_path=sku_path, patterns_path=patterns_path, version_path=version_path)
        resolved = resolve_category_detailed(
            explicit_category="",
            explicit_brand="Esser",
            sku_code="ABC123",
            full_row_text="Esser smoke detector",
        )
        assert resolved.category == "gas_safety"
        assert resolved.reason == "P2_SKU_LOOKUP"
    finally:
        reload_taxonomy()


def test_p2_overrides_p3(tmp_path: Path) -> None:
    sku_path = _write_json(tmp_path / "sku_lookup.json", {"EDA5200": "gas_safety"})
    patterns_path = _write_json(
        tmp_path / "pn_patterns.json",
        [
            {
                "pattern": "^EDA\\d+",
                "category": "fire_safety",
                "comment": "broad pattern",
                "author": "test",
            }
        ],
    )
    version_path = _write_json(tmp_path / "taxonomy_version.json", {"version": "v-test"})
    try:
        reload_taxonomy(sku_path=sku_path, patterns_path=patterns_path, version_path=version_path)
        resolved = resolve_category_detailed(
            explicit_category="",
            explicit_brand="Esser",
            sku_code="EDA5200",
            full_row_text="Esser smoke detector",
        )
        assert resolved.category == "gas_safety"
        assert resolved.reason == "P2_SKU_LOOKUP"
    finally:
        reload_taxonomy()


def test_p3_pattern_overrides_p4_brand(tmp_path: Path) -> None:
    sku_path = _write_json(tmp_path / "sku_lookup.json", {})
    patterns_path = _write_json(
        tmp_path / "pn_patterns.json",
        [
            {
                "pattern": "^EDA\\d+",
                "category": "it_hardware",
                "comment": "EDA handhelds",
                "author": "test",
            }
        ],
    )
    version_path = _write_json(tmp_path / "taxonomy_version.json", {"version": "v-test"})
    try:
        reload_taxonomy(sku_path=sku_path, patterns_path=patterns_path, version_path=version_path)
        resolved = resolve_category_detailed(
            explicit_category="",
            explicit_brand="Esser",
            sku_code="EDA5200",
            full_row_text="Esser smoke detector",
        )
        assert resolved.category == "it_hardware"
        assert resolved.reason == "P3_PN_PATTERN"
    finally:
        reload_taxonomy()


def test_p3_specificity_ordering(tmp_path: Path) -> None:
    sku_path = _write_json(tmp_path / "sku_lookup.json", {})
    patterns_path = _write_json(
        tmp_path / "pn_patterns.json",
        [
            {
                "pattern": "^EDA\\d+",
                "category": "fire_safety",
                "comment": "broad",
                "author": "test",
            },
            {
                "pattern": "^EDA52\\d+",
                "category": "it_hardware",
                "comment": "specific",
                "author": "test",
            },
        ],
    )
    version_path = _write_json(tmp_path / "taxonomy_version.json", {"version": "v-test"})
    try:
        reload_taxonomy(sku_path=sku_path, patterns_path=patterns_path, version_path=version_path)
        resolved = resolve_category_detailed(
            explicit_category="",
            explicit_brand="",
            sku_code="EDA52123",
            full_row_text="generic device",
        )
        assert resolved.category == "it_hardware"
        assert resolved.reason == "P3_PN_PATTERN"
    finally:
        reload_taxonomy()


def test_p6_unknown_reason() -> None:
    resolved = resolve_category_detailed(
        explicit_category="",
        explicit_brand="",
        sku_code="ZZZ",
        full_row_text="nondescript item",
    )
    assert resolved.category == "unknown"
    assert resolved.reason == "P6_UNKNOWN"


def test_empty_taxonomy_preserves_v35_behavior(tmp_path: Path) -> None:
    sku_path = _write_json(tmp_path / "sku_lookup.json", {})
    patterns_path = _write_json(tmp_path / "pn_patterns.json", [])
    version_path = _write_json(tmp_path / "taxonomy_version.json", {"version": "v-empty"})
    try:
        reload_taxonomy(sku_path=sku_path, patterns_path=patterns_path, version_path=version_path)
        cases = [
            (
                {
                    "explicit_category": "not_a_real_category",
                    "explicit_brand": "",
                    "sku_code": "ABC123",
                    "full_row_text": "Esser smoke detector",
                },
                "fire_safety",
            ),
            (
                {
                    "explicit_category": "",
                    "explicit_brand": "Esser",
                    "sku_code": "ABC123",
                    "full_row_text": "unlabeled transponder",
                },
                "fire_safety",
            ),
            (
                {
                    "explicit_category": "",
                    "explicit_brand": "",
                    "sku_code": "ABC123",
                    "full_row_text": "industrial gas detector xnx h2s",
                },
                "gas_safety",
            ),
            (
                {
                    "explicit_category": "",
                    "explicit_brand": "",
                    "sku_code": "ABC123",
                    "full_row_text": "ABCD1234",
                },
                "unknown",
            ),
        ]
        for payload, expected in cases:
            assert resolve_category(**payload) == expected
    finally:
        reload_taxonomy()


def test_pn_pattern_rejects_no_anchor(tmp_path: Path) -> None:
    sku_path = _write_json(tmp_path / "sku_lookup.json", {})
    patterns_path = _write_json(
        tmp_path / "pn_patterns.json",
        [
            {
                "pattern": "EDA\\d+",
                "category": "it_hardware",
                "comment": "missing anchor",
                "author": "test",
            }
        ],
    )
    with pytest.raises(ValueError):
        reload_taxonomy(sku_path=sku_path, patterns_path=patterns_path)
    reload_taxonomy()


def test_pn_pattern_rejects_dot_star(tmp_path: Path) -> None:
    sku_path = _write_json(tmp_path / "sku_lookup.json", {})
    patterns_path = _write_json(
        tmp_path / "pn_patterns.json",
        [
            {
                "pattern": "^EDA.*",
                "category": "it_hardware",
                "comment": "forbidden wildcard",
                "author": "test",
            }
        ],
    )
    with pytest.raises(ValueError):
        reload_taxonomy(sku_path=sku_path, patterns_path=patterns_path)
    reload_taxonomy()


def test_pn_pattern_rejects_over_max_length(tmp_path: Path) -> None:
    sku_path = _write_json(tmp_path / "sku_lookup.json", {})
    patterns_path = _write_json(
        tmp_path / "pn_patterns.json",
        [
            {
                "pattern": "^" + ("A" * 60),
                "category": "it_hardware",
                "comment": "too long",
                "author": "test",
            }
        ],
    )
    with pytest.raises(ValueError):
        reload_taxonomy(sku_path=sku_path, patterns_path=patterns_path)
    reload_taxonomy()


def test_brand_category_map_invariant() -> None:
    forbidden = {"honeywell", "siemens", "abb", "schneider", "emerson"}
    assert forbidden.isdisjoint(set(BRAND_CATEGORY_MAP.keys()))


def test_reload_taxonomy_changes_classification(tmp_path: Path) -> None:
    sku_empty = _write_json(tmp_path / "sku_empty.json", {})
    sku_non_empty = _write_json(tmp_path / "sku_non_empty.json", {"ABC123": "gas_safety"})
    patterns_path = _write_json(tmp_path / "pn_patterns.json", [])
    version_path = _write_json(tmp_path / "taxonomy_version.json", {"version": "v-test"})
    try:
        reload_taxonomy(sku_path=sku_empty, patterns_path=patterns_path, version_path=version_path)
        baseline = resolve_category(
            explicit_category="",
            explicit_brand="",
            sku_code="ABC123",
            full_row_text="nondescript item",
        )
        reload_taxonomy(sku_path=sku_non_empty, patterns_path=patterns_path, version_path=version_path)
        changed = resolve_category(
            explicit_category="",
            explicit_brand="",
            sku_code="ABC123",
            full_row_text="nondescript item",
        )
        assert baseline == "unknown"
        assert changed == "gas_safety"
    finally:
        reload_taxonomy()


def test_get_taxonomy_version_from_custom_file(tmp_path: Path) -> None:
    sku_path = _write_json(tmp_path / "sku_lookup.json", {})
    patterns_path = _write_json(tmp_path / "pn_patterns.json", [])
    version_path = _write_json(tmp_path / "taxonomy_version.json", {"version": "v-test-123"})
    try:
        reload_taxonomy(sku_path=sku_path, patterns_path=patterns_path, version_path=version_path)
        assert get_taxonomy_version() == "v-test-123"
    finally:
        reload_taxonomy()

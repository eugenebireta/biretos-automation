from __future__ import annotations

from scripts.lot_scoring import run_llm_classify_v2 as v2


def test_extract_json_object_fallback_first_object():
    payload = 'noise before {"proposed_category":"gas_safety","confidence":0.9,"reasoning":"detector xnx"} trailing noise'
    parsed = v2._extract_json_object(payload)
    assert parsed["proposed_category"] == "gas_safety"
    assert parsed["confidence"] == 0.9


def test_reasoning_grounding_uses_tokens_len_ge_4():
    sample_text = "abc xnx valve123 sensor"
    assert v2._reasoning_has_sample_text_facts(sample_text, "Uses valve123 for operation")
    assert not v2._reasoning_has_sample_text_facts(sample_text, "Mentions only abc and xnx")


def test_compose_core_rows_sorted_by_usd_desc_then_pn_asc():
    core_set = {
        "BBB200": 100.0,
        "AAA100": 100.0,
        "CCC300": 50.0,
    }
    aggregate = {}
    rows = v2._compose_core_rows(core_set, aggregate, max_pn=300)
    assert [row["pn"] for row in rows] == ["AAA100", "BBB200", "CCC300"]

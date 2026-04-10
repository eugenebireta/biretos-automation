"""Tests for merge_manifests.py — deterministic first+second pass merge."""

import json
import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from merge_manifests import _row_key, _second_pass_wins, merge


# ── Helpers ──────────────────────────────────────────────────────────────────

def _row(pn="1015021", domain="example.com", price=None, lineage=False, confidence=0, **kw):
    r = {
        "part_number": pn,
        "source_domain": domain,
        "price_per_unit": price,
        "price_source_exact_product_lineage_confirmed": lineage,
        "price_confidence": confidence,
    }
    r.update(kw)
    return r


# ── _row_key ─────────────────────────────────────────────────────────────────

def test_row_key_basic():
    assert _row_key(_row()) == "1015021::example.com"


def test_row_key_strips_whitespace():
    r = {"part_number": " 1015021 ", "source_domain": " example.com "}
    assert _row_key(r) == "1015021::example.com"


def test_row_key_missing_fields():
    assert _row_key({}) == "::"


# ── _second_pass_wins ────────────────────────────────────────────────────────

def test_second_wins_lineage_upgrade():
    first = _row(lineage=False)
    second = _row(lineage=True)
    assert _second_pass_wins(first, second) is True


def test_second_wins_price_upgrade():
    first = _row(price=None)
    second = _row(price=100.0)
    assert _second_pass_wins(first, second) is True


def test_second_wins_higher_confidence():
    first = _row(lineage=True, confidence=70)
    second = _row(lineage=True, confidence=90)
    assert _second_pass_wins(first, second) is True


def test_first_kept_same_lineage_same_confidence():
    first = _row(lineage=True, confidence=80)
    second = _row(lineage=True, confidence=80)
    assert _second_pass_wins(first, second) is False


def test_first_kept_both_no_lineage():
    first = _row(lineage=False, price=50.0)
    second = _row(lineage=False, price=60.0)
    assert _second_pass_wins(first, second) is False


def test_first_kept_first_has_lineage_second_does_not():
    first = _row(lineage=True, price=50.0)
    second = _row(lineage=False, price=60.0)
    assert _second_pass_wins(first, second) is False


# ── merge() ──────────────────────────────────────────────────────────────────

def test_merge_no_overlap_appends():
    """Second-pass rows with new keys are appended."""
    fp = [_row(domain="a.com", price=10.0)]
    sp = [_row(domain="b.com", price=20.0)]
    merged, stats = merge(fp, sp)
    assert len(merged) == 2
    assert stats["appended"] == 1
    assert stats["replaced"] == 0
    assert merged[0]["merge_source"] == "first_pass"
    assert merged[1]["merge_source"] == "second_pass_new"


def test_merge_replacement():
    """Second-pass wins on lineage upgrade."""
    fp = [_row(domain="a.com", lineage=False)]
    sp = [_row(domain="a.com", lineage=True, price=100.0)]
    merged, stats = merge(fp, sp)
    assert len(merged) == 1
    assert stats["replaced"] == 1
    assert merged[0]["merge_source"] == "second_pass_replaced"
    assert merged[0]["price_per_unit"] == 100.0
    assert merged[0]["price_admissibility_schema_version"] == "price_admissibility_v1"
    assert merged[0]["string_lineage_status"] in {"exact", "weak"}


def test_merge_keeps_first_when_second_blocked():
    """Blocked second-pass with no lineage is dropped."""
    fp = [_row(domain="a.com", price=50.0, lineage=True)]
    sp = [_row(domain="a.com", blocked_ui_detected=True, lineage=False)]
    merged, stats = merge(fp, sp)
    assert len(merged) == 1
    assert stats["second_blocked"] == 1
    assert merged[0]["merge_source"] == "first_pass"


def test_merge_preserves_first_pass_order():
    """Merged output preserves first-pass ordering."""
    fp = [
        _row(pn="A", domain="x.com"),
        _row(pn="B", domain="x.com"),
        _row(pn="C", domain="x.com"),
    ]
    sp = [_row(pn="B", domain="x.com", lineage=True)]
    merged, stats = merge(fp, sp)
    assert [r["part_number"] for r in merged] == ["A", "B", "C"]


def test_merge_deduplicates_first_pass():
    """Duplicate keys in first-pass: last one wins in index, first order kept."""
    fp = [
        _row(domain="a.com", price=10.0),
        _row(domain="a.com", price=20.0),  # same key, overwrites in dict
    ]
    sp = []
    merged, stats = merge(fp, sp)
    # Dedup by seen_keys means only one output row
    assert len(merged) == 1


def test_merge_empty_inputs():
    merged, stats = merge([], [])
    assert merged == []
    assert stats["merged_count"] if "merged_count" in stats else len(merged) == 0


def test_merge_stats_counts():
    fp = [_row(domain="a.com"), _row(pn="X", domain="b.com", lineage=True)]
    sp = [
        _row(domain="a.com", lineage=True),  # replaces
        _row(domain="c.com"),  # new
        _row(pn="Y", domain="d.com", blocked_ui_detected=True),  # blocked
    ]
    merged, stats = merge(fp, sp)
    assert stats["replaced"] == 1
    assert stats["kept_first"] == 0
    assert stats["appended"] == 1
    assert stats["second_blocked"] == 1
    assert len(merged) == 3  # 2 from first + 1 appended


def test_merge_strips_run_scoped_bvs_fields():
    sp = [_row(
        domain="b.com",
        price=20.0,
        browser_mode="headed",
        browser_channel="cdp",
        screenshot_taken=True,
        screenshot_path="D:/tmp/snap.png",
        vision_model="claude-sonnet-4-6",
        vision_confidence=99,
        blocked_ui_detected=False,
        final_url="https://example.com/final",
        page_title="Example",
        escalated_to_opus=False,
        trace_id="bvs-123",
        idempotency_key="bvs:123",
        browser_vision_source=True,
    )]
    merged, stats = merge([], sp)

    assert stats["appended"] == 1
    assert merged[0]["merge_source"] == "second_pass_new"
    assert merged[0]["price_per_unit"] == 20.0
    for field in (
        "browser_mode",
        "browser_channel",
        "screenshot_taken",
        "screenshot_path",
        "vision_model",
        "vision_confidence",
        "blocked_ui_detected",
        "final_url",
        "page_title",
        "escalated_to_opus",
        "trace_id",
        "idempotency_key",
        "browser_vision_source",
    ):
        assert field not in merged[0]


def test_merge_materializes_ambiguous_offer_for_semantic_component_page():
    fp = [_row(
        pn="101411",
        domain="conrad.sk",
        price=60.15,
        lineage=True,
        confidence=95,
        price_status="public_price",
        source_tier="authorized",
        http_status=200,
        page_product_class="cover frame switchgear",
    )]
    merged, stats = merge(fp, [])

    assert stats["merged_count"] if "merged_count" in stats else len(merged) == 1
    assert merged[0]["commercial_identity_status"] == "component_or_accessory"
    assert merged[0]["offer_admissibility_status"] == "ambiguous_offer"
    assert merged[0]["review_required"] is True



# ── Integration: run() with real files ───────────────────────────────────────

def test_run_writes_jsonl(tmp_path):
    from merge_manifests import run

    fp_path = tmp_path / "first.jsonl"
    sp_path = tmp_path / "second.jsonl"
    out_path = tmp_path / "merged.jsonl"

    fp_path.write_text(json.dumps(_row(domain="a.com", price=10.0)) + "\n", encoding="utf-8")
    sp_path.write_text(json.dumps(_row(domain="b.com", price=20.0)) + "\n", encoding="utf-8")

    stats = run(fp_path, sp_path, out_path)

    assert out_path.exists()
    lines = [json.loads(l) for l in out_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert stats["merged_count"] == 2
    assert stats["first_pass_count"] == 1
    assert stats["second_pass_count"] == 1

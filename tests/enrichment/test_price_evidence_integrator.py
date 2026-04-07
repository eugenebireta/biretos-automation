"""
test_price_evidence_integrator.py -- deterministic unit tests.

All tests are pure: no live API, no HTTP, no real file I/O except tmp_path.
price_admissibility is imported (pure function, no I/O), file reads/writes use tmp_path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from price_evidence_integrator import (
    build_price_section,
    _evidence_path,
    integrate_manifest,
    INTEGRATION_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admissible_row(pn="1000106", price=68.25, currency="AED", rub=1865.0):
    """Manifest row that classifies as admissible_public_price."""
    return {
        "part_number": pn,
        "price_status": "public_price",
        "price_per_unit": price,
        "currency": currency,
        "rub_price": rub,
        "fx_rate_used": 27.33,
        "fx_provider": "stub",
        "page_url": "https://example.com/product",
        "source_type": "authorized_distributor",
        "source_role": "authorized_distributor",
        "source_tier": "authorized",
        "price_confidence": 90,
        "offer_qty": 1,
        "offer_unit_basis": "piece",
        "stock_status": "in_stock",
        "lead_time_detected": False,
        "category_mismatch": False,
        "brand_mismatch": False,
        "suffix_conflict": False,
        "page_product_class": "Датчик",
        # Lineage fields for admissibility to pass
        "price_source_exact_product_lineage_confirmed": True,
        "price_source_seen": True,
        "price_source_lineage_reason_code": "structured_exact_product_page",
        "price_source_surface_conflict_detected": False,
    }


def _non_admissible_row(pn="bad_pn"):
    """Manifest row that does NOT classify as admissible."""
    return {
        "part_number": pn,
        "price_status": "no_price_found",
        "price_per_unit": None,
        "currency": "",
    }


def _ambiguous_row(pn="amb_pn"):
    """Manifest row that classifies as ambiguous_offer."""
    return {
        "part_number": pn,
        "price_status": "public_price",
        "price_per_unit": 10.0,
        "currency": "USD",
        "rub_price": 900.0,
        "category_mismatch": True,  # triggers component_or_accessory -> ambiguous
        "price_source_exact_product_lineage_confirmed": False,
        "price_source_seen": False,
    }


def _evidence_bundle(pn="1000106"):
    return {
        "schema_version": "v1",
        "pn": pn,
        "card_status": "DRAFT_ONLY",
        "price": {},
        "field_statuses_v2": {"price_status": "INSUFFICIENT"},
        "policy_decision_v2": {"price_status": "INSUFFICIENT"},
    }


def _write_manifest(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "manifest.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def _write_evidence(evidence_dir: Path, pn: str, bundle: dict) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    p = evidence_dir / f"evidence_{pn}.json"
    p.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# build_price_section
# ---------------------------------------------------------------------------
class TestBuildPriceSection:
    def test_price_per_unit_mapped(self):
        row = _admissible_row(price=68.25)
        section = build_price_section(row)
        assert section["price_per_unit"] == 68.25

    def test_currency_mapped(self):
        section = build_price_section(_admissible_row(currency="AED"))
        assert section["currency"] == "AED"

    def test_rub_price_mapped(self):
        section = build_price_section(_admissible_row(rub=1865.0))
        assert section["rub_price"] == 1865.0

    def test_source_url_from_page_url(self):
        row = _admissible_row()
        row["page_url"] = "https://example.com/page"
        section = build_price_section(row)
        assert section["source_url"] == "https://example.com/page"

    def test_source_url_fallback_to_source_url(self):
        row = _admissible_row()
        row.pop("page_url", None)
        row["source_url"] = "https://fallback.com/page"
        section = build_price_section(row)
        assert section["source_url"] == "https://fallback.com/page"

    def test_source_type_from_source_type(self):
        row = _admissible_row()
        row["source_type"] = "official"
        section = build_price_section(row)
        assert section["source_type"] == "official"

    def test_source_type_fallback_to_source_role(self):
        row = _admissible_row()
        row.pop("source_type", None)
        row["source_role"] = "authorized_distributor"
        section = build_price_section(row)
        assert section["source_type"] == "authorized_distributor"

    def test_boolean_fields_coerced(self):
        row = _admissible_row()
        row["lead_time_detected"] = "true"
        section = build_price_section(row)
        assert section["lead_time_detected"] is True

    def test_category_mismatch_false_by_default(self):
        row = _admissible_row()
        row.pop("category_mismatch", None)
        section = build_price_section(row)
        assert section["category_mismatch"] is False

    def test_price_sample_size_is_1(self):
        section = build_price_section(_admissible_row())
        assert section["price_sample_size"] == 1

    def test_price_median_clean_is_none(self):
        section = build_price_section(_admissible_row())
        assert section["price_median_clean"] is None

    def test_source_tier_mapped(self):
        row = _admissible_row()
        row["source_tier"] = "official"
        section = build_price_section(row)
        assert section["source_tier"] == "official"


# ---------------------------------------------------------------------------
# _evidence_path
# ---------------------------------------------------------------------------
class TestEvidencePath:
    def test_direct_match(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        f = ev_dir / "evidence_1000106.json"
        f.write_text("{}")
        result = _evidence_path(ev_dir, "1000106")
        assert result == f

    def test_not_found_returns_none(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        result = _evidence_path(ev_dir, "NOTEXIST")
        assert result is None

    def test_case_insensitive_fallback(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        f = ev_dir / "evidence_010130.10.json"
        f.write_text("{}")
        result = _evidence_path(ev_dir, "010130.10")
        assert result == f


# ---------------------------------------------------------------------------
# integrate_manifest -- success
# ---------------------------------------------------------------------------
class TestIntegrateManifestSuccess:
    def test_integrated_count(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "1000106", _evidence_bundle("1000106"))
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106")])
        summary = integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                                     trace_id="test_t1", _now_fn=lambda: "2026-04-07T00:00:00Z")
        assert summary["integrated_count"] == 1

    def test_price_section_written_to_bundle(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "1000106", _evidence_bundle("1000106"))
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106", price=68.25, currency="AED")])
        integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                           trace_id="test_t2", _now_fn=lambda: "2026-04-07T00:00:00Z")
        bundle = json.loads((ev_dir / "evidence_1000106.json").read_text())
        assert bundle["price"]["price_per_unit"] == 68.25
        assert bundle["price"]["currency"] == "AED"

    def test_field_statuses_price_status_set_to_accepted(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "1000106", _evidence_bundle("1000106"))
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106")])
        integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                           trace_id="test_t3", _now_fn=lambda: "2026-04-07T00:00:00Z")
        bundle = json.loads((ev_dir / "evidence_1000106.json").read_text())
        assert bundle["field_statuses_v2"]["price_status"] == "ACCEPTED"

    def test_policy_decision_price_status_set_to_accepted(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "1000106", _evidence_bundle("1000106"))
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106")])
        integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                           trace_id="test_t4", _now_fn=lambda: "2026-04-07T00:00:00Z")
        bundle = json.loads((ev_dir / "evidence_1000106.json").read_text())
        assert bundle["policy_decision_v2"]["price_status"] == "ACCEPTED"

    def test_refresh_trace_written(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "1000106", _evidence_bundle("1000106"))
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106")])
        integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                           trace_id="test_t5", _now_fn=lambda: "2026-04-07T00:00:00Z")
        bundle = json.loads((ev_dir / "evidence_1000106.json").read_text())
        rt = bundle.get("refresh_trace", {}).get("price_integration", {})
        assert rt["trace_id"] == "test_t5"
        assert rt["schema_version"] == INTEGRATION_SCHEMA_VERSION

    def test_card_status_not_modified(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "1000106", _evidence_bundle("1000106"))
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106")])
        integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                           trace_id="test_t6", _now_fn=lambda: "2026-04-07T00:00:00Z")
        bundle = json.loads((ev_dir / "evidence_1000106.json").read_text())
        # card_status must remain unchanged (left for local_catalog_refresh.py)
        assert bundle["card_status"] == "DRAFT_ONLY"

    def test_audit_trace_written_to_disk(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "1000106", _evidence_bundle("1000106"))
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106")])
        integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                           trace_id="test_t7", _now_fn=lambda: "2026-04-07T00:00:00Z")
        traces = list((tmp_path / "audits").glob("price_integration_*/integration_trace.json"))
        assert len(traces) == 1
        trace = json.loads(traces[0].read_text())
        assert trace["trace_id"] == "test_t7"
        assert trace["integrated_count"] == 1

    def test_summary_total_rows(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "1000106", _evidence_bundle("1000106"))
        _write_evidence(ev_dir, "bad_pn", _evidence_bundle("bad_pn"))
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106"), _non_admissible_row("bad_pn")])
        summary = integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                                     trace_id="test_t8", _now_fn=lambda: "2026-04-07T00:00:00Z")
        assert summary["total_rows"] == 2
        assert summary["integrated_count"] == 1
        assert summary["skipped_count"] == 1


# ---------------------------------------------------------------------------
# integrate_manifest -- skipped (non-admissible)
# ---------------------------------------------------------------------------
class TestIntegrateManifestSkips:
    def test_non_admissible_row_skipped(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "bad_pn", _evidence_bundle("bad_pn"))
        manifest = _write_manifest(tmp_path, [_non_admissible_row("bad_pn")])
        summary = integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                                     trace_id="test_s1", _now_fn=lambda: "2026-04-07T00:00:00Z")
        assert summary["integrated_count"] == 0
        assert summary["skipped_count"] == 1

    def test_non_admissible_evidence_unchanged(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        original = _evidence_bundle("bad_pn")
        _write_evidence(ev_dir, "bad_pn", original)
        manifest = _write_manifest(tmp_path, [_non_admissible_row("bad_pn")])
        integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                           trace_id="test_s2", _now_fn=lambda: "2026-04-07T00:00:00Z")
        bundle = json.loads((ev_dir / "evidence_bad_pn.json").read_text())
        assert bundle["field_statuses_v2"]["price_status"] == "INSUFFICIENT"

    def test_ambiguous_row_skipped(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "amb_pn", _evidence_bundle("amb_pn"))
        manifest = _write_manifest(tmp_path, [_ambiguous_row("amb_pn")])
        summary = integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                                     trace_id="test_s3", _now_fn=lambda: "2026-04-07T00:00:00Z")
        assert summary["skipped_count"] == 1

    def test_evidence_not_found_skipped(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        manifest = _write_manifest(tmp_path, [_admissible_row("missing_pn")])
        summary = integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                                     trace_id="test_s4", _now_fn=lambda: "2026-04-07T00:00:00Z")
        assert summary["skipped_count"] == 1
        assert summary["integrated_count"] == 0

    def test_missing_part_number_skipped(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        ev_dir.mkdir()
        row = {"price_status": "public_price"}  # no part_number
        manifest = _write_manifest(tmp_path, [row])
        summary = integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                                     trace_id="test_s5", _now_fn=lambda: "2026-04-07T00:00:00Z")
        assert summary["skipped_count"] == 1


# ---------------------------------------------------------------------------
# integrate_manifest -- dry_run
# ---------------------------------------------------------------------------
class TestIntegrateManifestDryRun:
    def test_dry_run_no_file_written(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        original = _evidence_bundle("1000106")
        _write_evidence(ev_dir, "1000106", original)
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106")])
        integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                           trace_id="test_d1", dry_run=True, _now_fn=lambda: "2026-04-07T00:00:00Z")
        # Evidence file must be unchanged
        bundle = json.loads((ev_dir / "evidence_1000106.json").read_text())
        assert bundle["price"] == {}

    def test_dry_run_no_audit_trace(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "1000106", _evidence_bundle("1000106"))
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106")])
        integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                           trace_id="test_d2", dry_run=True, _now_fn=lambda: "2026-04-07T00:00:00Z")
        assert not (tmp_path / "audits").exists()

    def test_dry_run_summary_count_correct(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "1000106", _evidence_bundle("1000106"))
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106")])
        summary = integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                                     trace_id="test_d3", dry_run=True,
                                     _now_fn=lambda: "2026-04-07T00:00:00Z")
        assert summary["integrated_count"] == 1
        assert summary["dry_run"] is True


# ---------------------------------------------------------------------------
# idempotency
# ---------------------------------------------------------------------------
class TestIdempotency:
    def test_double_integration_same_result(self, tmp_path):
        ev_dir = tmp_path / "evidence"
        _write_evidence(ev_dir, "1000106", _evidence_bundle("1000106"))
        manifest = _write_manifest(tmp_path, [_admissible_row("1000106")])
        now_fn = lambda: "2026-04-07T00:00:00Z"
        integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                           trace_id="idp_1", _now_fn=now_fn)
        integrate_manifest(manifest, ev_dir, tmp_path / "audits",
                           trace_id="idp_1", _now_fn=now_fn)  # same trace_id
        bundle = json.loads((ev_dir / "evidence_1000106.json").read_text())
        assert bundle["field_statuses_v2"]["price_status"] == "ACCEPTED"
        assert bundle["price"]["price_per_unit"] == 68.25

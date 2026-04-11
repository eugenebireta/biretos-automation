"""tests/enrichment/test_exporter_insales.py — InSales exporter unit tests.

Covers:
  A. Photo mapping from manifest
  B. Specs formatting (structured, raw, blocked)
  C. Missing fields handling
  D. Multi-vendor safety — no hardcoded brand bias
  E. Export eligibility
"""
import sys
import os

_scripts = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from exporter_insales import (
    format_specs_html,
    check_exportable,
    build_export_row,
    build_skipped_row,
)


def _make_ev(**overrides):
    """Build a minimal valid evidence dict."""
    base = {
        "_pn": "TEST001",
        "brand": "TestBrand",
        "assembled_title": "Test Product TEST001",
        "identity_level": "strong",
        "card_status": "REVIEW_REQUIRED",
        "dr_price": 100.0,
        "dr_currency": "EUR",
        "our_price_raw": "0,00",
    }
    base.update(overrides)
    return base


# ══════════════════════════════════════════════════════════════════════════════
# A. Photo mapping
# ══════════════════════════════════════════════════════════════════════════════

class TestPhotoMapping:

    def test_photo_present(self):
        ev = _make_ev()
        row = build_export_row(ev, "https://cdn.example.com/products/test/TEST001.jpg")
        assert row["Изображение"] == "https://cdn.example.com/products/test/TEST001.jpg"

    def test_photo_missing(self):
        ev = _make_ev()
        row = build_export_row(ev, "")
        assert row["Изображение"] == ""
        assert "no_photo" in row["Примечание"]

    def test_photo_missing_sku_still_exported(self):
        """Missing photo should not prevent export."""
        ev = _make_ev()
        eligible, reason = check_exportable(ev)
        assert eligible is True  # photo is not required

    def test_photo_url_from_manifest_not_reconstructed(self):
        """Photo URL should be used as-is from manifest, not rebuilt."""
        url = "https://custom-cdn.io/images/some_brand/ABC.jpg"
        ev = _make_ev()
        row = build_export_row(ev, url)
        assert row["Изображение"] == url


# ══════════════════════════════════════════════════════════════════════════════
# B. Specs formatting
# ══════════════════════════════════════════════════════════════════════════════

class TestSpecsFormatting:

    def test_structured_specs_html(self):
        specs = {"voltage": "24V DC", "power": "5W", "raw": "some raw text"}
        html = format_specs_html(specs)
        assert "<ul>" in html
        assert "<li><b>Voltage:</b> 24V DC</li>" in html
        assert "<li><b>Power:</b> 5W</li>" in html
        assert "raw" not in html.lower().split("<ul>")[0]  # raw key not in output

    def test_raw_only_specs(self):
        specs = {"raw": "2-fach; Reinweiß; 83×154 mm"}
        html = format_specs_html(specs)
        assert "<p>" in html
        assert "2-fach" in html

    def test_empty_specs(self):
        assert format_specs_html({}) == ""
        assert format_specs_html(None) == ""

    def test_aliases_excluded(self):
        specs = {"raw": "text", "aliases": ["A", "B"]}
        html = format_specs_html(specs)
        assert "aliases" not in html

    def test_internal_keys_excluded(self):
        specs = {"merge_ts": "2026-01-01", "confidence": 0.9, "voltage": "12V"}
        html = format_specs_html(specs)
        assert "merge_ts" not in html
        assert "confidence" not in html
        assert "12V" in html

    def test_blocked_specs_not_exported(self):
        """specs_raw_unvalidated should result in empty specs."""
        ev = _make_ev(specs_status="blocked_identity_unresolved",
                      deep_research={"specs": {"raw": "should not appear"}})
        row = build_export_row(ev, "")
        assert row["Краткое описание"] == ""

    def test_none_values_excluded(self):
        specs = {"voltage": None, "power": "5W", "raw": ""}
        html = format_specs_html(specs)
        assert "None" not in html
        assert "5W" in html


# ══════════════════════════════════════════════════════════════════════════════
# C. Missing fields
# ══════════════════════════════════════════════════════════════════════════════

class TestMissingFields:

    def test_no_brand_skipped(self):
        ev = _make_ev(brand="")
        eligible, reason = check_exportable(ev)
        assert eligible is False
        assert reason == "no_brand"

    def test_no_title_skipped(self):
        ev = _make_ev(assembled_title="")
        eligible, reason = check_exportable(ev)
        assert eligible is False
        assert reason == "no_title"

    def test_no_price_skipped(self):
        ev = _make_ev(dr_price=None, our_price_raw="0,00")
        eligible, reason = check_exportable(ev)
        assert eligible is False
        assert reason == "no_usable_price"

    def test_blocked_price_skipped(self):
        ev = _make_ev(dr_price_blocked=True)
        eligible, reason = check_exportable(ev)
        assert eligible is False
        assert reason == "no_usable_price"

    def test_identity_unknown_skipped(self):
        ev = _make_ev(identity_level="unknown")
        eligible, reason = check_exportable(ev)
        assert eligible is False
        assert reason == "identity_unknown"

    def test_identity_gate_block(self):
        ev = _make_ev(identity_gate={"gate_result": "block", "reason_codes": ["brand_guard_block"]})
        eligible, reason = check_exportable(ev)
        assert eligible is False
        assert "identity_blocked" in reason

    def test_empty_category_allowed(self):
        """Missing category should not block export."""
        ev = _make_ev()
        row = build_export_row(ev, "")
        assert row["Категория"] == ""  # empty but row still produced

    def test_our_price_preferred(self):
        """our_price_raw (RUB) should be preferred over dr_price."""
        ev = _make_ev(dr_price=50.0, dr_currency="EUR", our_price_raw="5000,00")
        row = build_export_row(ev, "")
        assert row["Цена"] == "5000,00"
        assert row["Валюта"] == "RUB"

    def test_dr_price_fallback(self):
        """If our_price is 0, use dr_price."""
        ev = _make_ev(dr_price=50.0, dr_currency="EUR", our_price_raw="0,00")
        row = build_export_row(ev, "")
        assert row["Цена"] == "50.0"
        assert row["Валюта"] == "EUR"


# ══════════════════════════════════════════════════════════════════════════════
# D. Multi-vendor safety
# ══════════════════════════════════════════════════════════════════════════════

class TestMultiVendor:

    def test_brand_from_evidence_not_hardcoded(self):
        """Brand must come from evidence, not hardcoded."""
        ev = _make_ev(brand="Siemens")
        row = build_export_row(ev, "")
        assert row["Бренд"] == "Siemens"

    def test_photo_url_not_vendor_specific(self):
        """Photo URL comes from manifest as-is, no vendor reconstruction."""
        url = "https://cdn.example.com/products/siemens/XYZ.jpg"
        ev = _make_ev(brand="Siemens")
        row = build_export_row(ev, url)
        assert "honeywell" not in row["Изображение"].lower()
        assert row["Изображение"] == url

    def test_skipped_row_has_brand_from_evidence(self):
        ev = _make_ev(brand="ABB")
        row = build_skipped_row(ev, "no_usable_price")
        assert row["Бренд"] == "ABB"


# ══════════════════════════════════════════════════════════════════════════════
# E. Export status
# ══════════════════════════════════════════════════════════════════════════════

class TestExportStatus:

    def test_ready_draft_no_gaps(self):
        ev = _make_ev(deep_research={"specs": {"voltage": "24V"}})
        row = build_export_row(ev, "https://cdn.example.com/photo.jpg")
        assert row["Статус экспорта"] == "export_ready_draft"
        assert row["Примечание"] == ""

    def test_export_with_gaps_flagged(self):
        ev = _make_ev(identity_level="weak")
        row = build_export_row(ev, "")
        assert row["Статус экспорта"] == "export_with_gaps"
        assert "weak_identity" in row["Примечание"]
        assert "no_photo" in row["Примечание"]

    def test_pack_suspect_noted(self):
        ev = _make_ev(dr_price_flag="PACK_SUSPECT")
        row = build_export_row(ev, "https://cdn.example.com/photo.jpg")
        assert "pack_suspect_price" in row["Примечание"]

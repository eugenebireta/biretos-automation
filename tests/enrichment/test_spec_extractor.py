"""Tests for spec_extractor.py (Block 3)."""
from __future__ import annotations

import os
import sys

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from spec_extractor import extract_specs_from_html, _normalize_spec_key


class TestNormalizeSpecKey:
    def test_spaces_to_underscore(self):
        assert _normalize_spec_key("Operating Temperature") == "operating_temperature"

    def test_dashes_to_underscore(self):
        assert _normalize_spec_key("Input-Voltage") == "input_voltage"

    def test_lowercase(self):
        assert _normalize_spec_key("POWER") == "power"

    def test_truncated_at_50(self):
        long_key = "a" * 60
        assert len(_normalize_spec_key(long_key)) == 50

    def test_empty_returns_empty(self):
        assert _normalize_spec_key("") == ""

    def test_special_chars_stripped(self):
        assert _normalize_spec_key("Weight (kg)") == "weight_kg"


class TestExtractSpecsFromHtml:
    def test_two_column_table_extracted(self):
        html = """
        <html><body>
        <table>
          <tr><td>Voltage</td><td>24 VDC</td></tr>
          <tr><td>Current</td><td>100 mA</td></tr>
          <tr><td>IP Rating</td><td>IP65</td></tr>
        </table>
        </body></html>
        """
        specs = extract_specs_from_html(html)
        assert "voltage" in specs
        assert specs["voltage"] == "24 VDC"
        assert "current" in specs
        assert "ip_rating" in specs

    def test_definition_list_extracted(self):
        html = """
        <html><body>
        <dl>
          <dt>Brand</dt><dd>Honeywell</dd>
          <dt>Part Number</dt><dd>1000106</dd>
          <dt>Color</dt><dd>White</dd>
        </dl>
        </body></html>
        """
        specs = extract_specs_from_html(html)
        assert "brand" in specs
        assert specs["brand"] == "Honeywell"
        assert "part_number" in specs
        assert "color" in specs

    def test_spec_div_class_extracted(self):
        html = """
        <html><body>
        <div class="product-specifications">
          <span>Weight: 0.5 kg</span>
          <span>Dimensions: 80x120x10 mm</span>
        </div>
        </body></html>
        """
        specs = extract_specs_from_html(html)
        assert "weight" in specs
        assert specs["weight"] == "0.5 kg"

    def test_empty_html_returns_empty_dict(self):
        specs = extract_specs_from_html("<html><body><p>No specs here</p></body></html>")
        assert specs == {}

    def test_keys_normalised(self):
        html = """
        <table>
          <tr><td>Operating Temperature</td><td>-10 to +55°C</td></tr>
        </table>
        """
        specs = extract_specs_from_html(html)
        assert "operating_temperature" in specs

    def test_no_exception_on_malformed_html(self):
        # Should not raise
        result = extract_specs_from_html("<<not html at all>><<")
        assert isinstance(result, dict)

    def test_three_column_table_ignored(self):
        """Three-column tables are NOT two-column, should be ignored."""
        html = """
        <table>
          <tr><td>A</td><td>B</td><td>C</td></tr>
        </table>
        """
        specs = extract_specs_from_html(html)
        assert specs == {}

    def test_max_specs_cap(self):
        """Should not return more than 100 specs."""
        rows = "".join(f"<tr><td>Key{i}</td><td>Val{i}</td></tr>" for i in range(150))
        html = f"<table>{rows}</table>"
        specs = extract_specs_from_html(html)
        assert len(specs) <= 100

    def test_pn_argument_accepted(self):
        """pn argument is accepted, doesn't affect basic extraction."""
        html = "<table><tr><td>Voltage</td><td>12V</td></tr></table>"
        specs = extract_specs_from_html(html, pn="1000106")
        assert "voltage" in specs

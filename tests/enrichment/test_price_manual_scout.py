from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import price_manual_scout as scout  # noqa: E402
import run_price_only_scout_pilot as pilot  # noqa: E402


class DummyResponse:
    def __init__(self, text: str, status_code: int = 200, content_type: str = "text/html; charset=utf-8"):
        self.text = text
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}


def test_materialize_seed_record_keeps_manual_public_price_with_lineage(monkeypatch):
    html = """
    <html>
      <head>
        <title>Honeywell 010130.10 exact page</title>
        <script type="application/ld+json">
          {"mpn":"010130.10"}
        </script>
      </head>
      <body><h1>Honeywell 010130.10 BUS-2/BUS-1</h1></body>
    </html>
    """
    monkeypatch.setattr(scout.requests, "get", lambda *_args, **_kwargs: DummyResponse(html))
    monkeypatch.setattr(scout, "get_source_role", lambda *_args, **_kwargs: "authorized_distributor")
    monkeypatch.setattr(scout, "get_source_trust", lambda *_args, **_kwargs: {"tier": "authorized", "weight": 0.9, "domain": "rs-online.com"})
    monkeypatch.setattr(scout, "is_denied", lambda *_args, **_kwargs: False)

    row = scout.materialize_seed_record(
        {
            "part_number": "010130.10",
            "brand": "Honeywell",
            "product_name": "BUS module",
            "expected_category": "Модуль",
            "page_url": "https://example.com/product",
            "source_provider": "codex_manual",
            "price_status": "public_price",
            "price_per_unit": 225.0,
            "currency": "EUR",
            "offer_qty": 1,
            "offer_unit_basis": "piece",
            "stock_status": "in_stock",
            "lead_time_detected": False,
            "quote_cta_url": "",
            "page_product_class": "bus module",
            "category_mismatch": False,
            "brand_mismatch": False,
            "price_confidence": 95,
            "source_price_value": 225.0,
            "source_price_currency": "EUR",
            "source_offer_qty": 1,
            "source_offer_unit_basis": "piece",
            "price_basis_note": "public list price on exact product page",
            "notes": "",
        },
        surface_cache_payload=None,
    )

    assert row["price_status"] == "public_price"
    assert row["price_per_unit"] == 225.0
    assert row["price_source_exact_product_lineage_confirmed"] is True
    assert row["review_required"] is False
    assert row["fx_normalization_status"] == "normalized"
    assert row["fx_gap_reason_code"] == ""


def test_load_seed_records_skips_invalid_rows(tmp_path):
    seed_path = tmp_path / "seed.jsonl"
    seed_path.write_text(
        "\n".join(
            [
                json.dumps({"part_number": "010130.10", "page_url": "https://example.com", "price_status": "public_price"}),
                json.dumps({"part_number": "", "page_url": "https://example.com", "price_status": "public_price"}),
                json.dumps({"part_number": "bad", "page_url": "", "price_status": "public_price"}),
                json.dumps({"part_number": "bad2", "page_url": "https://example.com", "price_status": "unsupported"}),
            ]
        ),
        encoding="utf-8",
    )

    rows = scout.load_seed_records(seed_path)

    assert len(rows) == 1
    assert rows[0]["part_number"] == "010130.10"


def test_normalize_source_role_uses_trust_tier_when_registry_is_missing():
    role = scout._normalize_source_role(
        "https://www.modern-eastern.com/honeywell-bilsom-304l-foamplug-corded.html",
        "organic_discovery",
        {"tier": "industrial", "weight": 0.72, "domain": "modern-eastern.com"},
    )

    assert role == "industrial_distributor"


def test_materialize_seed_record_marks_explicit_fx_gap(monkeypatch):
    html = """
    <html>
      <head>
        <title>Honeywell 1006186 exact page</title>
        <script type="application/ld+json">
          {"mpn":"1006186"}
        </script>
      </head>
      <body><h1>Honeywell 1006186 303L FOAMPLUG</h1></body>
    </html>
    """
    monkeypatch.setattr(scout.requests, "get", lambda *_args, **_kwargs: DummyResponse(html))
    monkeypatch.setattr(scout, "get_source_role", lambda *_args, **_kwargs: "authorized_distributor")
    monkeypatch.setattr(scout, "get_source_trust", lambda *_args, **_kwargs: {"tier": "authorized", "weight": 0.9, "domain": "rs-online.com"})
    monkeypatch.setattr(scout, "is_denied", lambda *_args, **_kwargs: False)

    row = scout.materialize_seed_record(
        {
            "part_number": "1006186",
            "brand": "Honeywell",
            "product_name": "303L FOAMPLUG",
            "expected_category": "Беруши",
            "page_url": "https://example.com/product",
            "source_provider": "codex_manual",
            "price_status": "public_price",
            "price_per_unit": 1794.0,
            "currency": "TWD",
            "offer_qty": 1,
            "offer_unit_basis": "box",
            "stock_status": "in_stock",
            "lead_time_detected": True,
            "quote_cta_url": "",
            "page_product_class": "ear plugs",
            "category_mismatch": False,
            "brand_mismatch": False,
            "price_confidence": 95,
            "source_price_value": 1794.0,
            "source_price_currency": "TWD",
            "source_offer_qty": 1,
            "source_offer_unit_basis": "box",
            "price_basis_note": "public price on exact product page",
            "notes": "",
        },
        surface_cache_payload=None,
    )

    assert row["rub_price"] is None
    assert row["fx_normalization_status"] == "fx_gap"
    assert row["fx_gap_reason_code"] == "fx_rate_unavailable_for_currency"


def test_price_only_pilot_accepts_manual_seed_results(tmp_path, monkeypatch):
    manifest_rows = [
        {
            "part_number": "010130.10",
            "brand": "Honeywell",
            "product_name": "BUS module",
            "expected_category": "Модуль",
            "source_provider": "codex_manual",
            "page_url": "https://example.com/product",
            "source_tier": "authorized",
            "source_type": "authorized_distributor",
            "price_status": "public_price",
            "price_confidence": 95,
            "price_source_seen": True,
            "price_source_exact_product_lineage_confirmed": True,
            "price_source_lineage_reason_code": "structured_exact_product_page",
            "price_source_surface_stable": True,
            "price_source_surface_conflict_detected": False,
            "price_source_surface_conflict_reason_code": "",
            "transient_failure_codes": [],
            "price_per_unit": 225.0,
            "currency": "EUR",
            "rub_price": 0,
            "offer_qty": 1,
            "offer_unit_basis": "piece",
            "source_price_value": 225.0,
            "source_price_currency": "EUR",
            "source_offer_qty": 1,
            "source_offer_unit_basis": "piece",
            "price_basis_note": "public list price",
            "review_required": False,
            "fx_normalization_status": "normalized",
            "fx_gap_reason_code": "",
            "fx_provider": "stub",
            "fx_rate_used": 95.0,
        }
    ]

    def _fake_manual_run(seed_path, manifest_path, *, limit=None):
        manifest_path.write_text(json.dumps(manifest_rows[0], ensure_ascii=False) + "\n", encoding="utf-8")
        return manifest_rows[:limit]

    monkeypatch.setattr(pilot, "run_manual_price_scout", _fake_manual_run)
    monkeypatch.setattr(pilot, "AUDITS_DIR", tmp_path)
    monkeypatch.setattr(pilot, "discover_prior_run_dirs", lambda *_args, **_kwargs: [])

    summary = pilot.run(limit=1, manual_seed_path=tmp_path / "manual_seed.jsonl")

    assert summary["processed_rows_count"] == 1
    assert summary["price_status_counts"] == {"public_price": 1}
    assert summary["exact_product_lineage_confirmed_count"] == 1
    assert summary["fx_status_counts"] == {"normalized": 1}
    assert summary["fx_gap_count"] == 0

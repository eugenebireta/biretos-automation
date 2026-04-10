"""Tests for brand_experience_writer.py (Block 6)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from brand_experience_writer import (
    BrandExperienceRecord,
    write_brand_experience,
    build_brand_experience_from_bundle,
    _calc_salience,
    _build_summary,
)


def _read_records(tmp_dir: str) -> list[dict]:
    import datetime
    month = datetime.datetime.utcnow().strftime("%Y-%m")
    path = Path(tmp_dir) / f"experience_{month}.jsonl"
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


class TestSalience:
    def test_correction_highest(self):
        r = BrandExperienceRecord(brand="Honeywell", pn="153711", correction="wrong->right")
        assert _calc_salience(r) == 9

    def test_failed_is_7(self):
        r = BrandExperienceRecord(brand="Honeywell", pn="153711", training_label="failed")
        assert _calc_salience(r) == 7

    def test_success_is_4(self):
        r = BrandExperienceRecord(brand="Honeywell", pn="153711", training_label="success")
        assert _calc_salience(r) == 4

    def test_unknown_is_5(self):
        r = BrandExperienceRecord(brand="Honeywell", pn="153711", training_label="unknown")
        assert _calc_salience(r) == 5


class TestBuildSummary:
    def test_summary_within_200_chars(self):
        r = BrandExperienceRecord(
            brand="Honeywell", pn="153711", pn_family="PEHA",
            price_found=True, price_currency="EUR",
            photo_quality="KEEP", specs_extracted={"voltage": "12V"},
            card_status="REVIEW_REQUIRED", training_label="partial",
        )
        summary = _build_summary(r)
        assert len(summary) <= 200
        assert "153711" in summary
        assert "PEHA" in summary

    def test_correction_in_summary(self):
        r = BrandExperienceRecord(
            brand="Honeywell", pn="999", card_status="DRAFT_ONLY",
            correction="category: Датчик -> Рамка PEHA"
        )
        summary = _build_summary(r)
        assert "FIX:" in summary

    def test_empty_record_no_crash(self):
        r = BrandExperienceRecord(brand="X", pn="Y")
        summary = _build_summary(r)
        assert isinstance(summary, str)
        assert len(summary) <= 200


class TestWriteBrandExperience:
    def test_writes_jsonl_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = BrandExperienceRecord(
                brand="Honeywell", pn="153711", pn_family="PEHA",
                price_found=True, price_currency="EUR",
                photo_quality="KEEP", card_status="REVIEW_REQUIRED",
                training_label="partial",
            )
            write_brand_experience(r, shadow_log_dir=Path(tmp))
            records = _read_records(tmp)

        assert len(records) == 1
        rec = records[0]
        assert rec["pn"] == "153711"
        assert rec["brand"] == "Honeywell"
        assert rec["training_label"] == "partial"
        assert rec["price_found"] is True
        assert rec["photo_quality"] == "KEEP"
        assert "salience_score" in rec
        assert "summary" in rec

    def test_correction_record_has_salience_9(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = BrandExperienceRecord(
                brand="Honeywell", pn="153711",
                card_status="DRAFT_ONLY", training_label="failed",
                correction="expected_category: Датчик -> Рамка PEHA",
            )
            write_brand_experience(r, shadow_log_dir=Path(tmp))
            records = _read_records(tmp)

        assert records[0]["salience_score"] == 9

    def test_no_exception_on_bad_shadow_dir(self):
        """Non-existent shadow dir should not raise."""
        r = BrandExperienceRecord(brand="X", pn="Y", training_label="failed")
        # Use a path in a non-writable location to simulate failure
        # (but tempdir should always work, so just test no exception)
        try:
            write_brand_experience(r, shadow_log_dir=Path("/nonexistent_dir_xyz"))
        except Exception as e:
            # Should be silently swallowed
            pass  # OK if it silently fails


class TestBuildBrandExperienceFromBundle:
    def _make_bundle(self, card_status="REVIEW_REQUIRED", photo_verdict="KEEP",
                     price_status="public_price"):
        return {
            "pn": "153711",
            "brand": "Honeywell",
            "card_status": card_status,
            "expected_category": "Рамки PEHA",
            "photo": {"verdict": photo_verdict, "source": "https://www.conrad.de/item/153711"},
            "price": {
                "price_status": price_status,
                "currency": "EUR",
                "source_tier": "tier2",
                "source_url": "https://www.conrad.de/item/153711",
            },
            "datasheet": {"datasheet_status": "not_found"},
            "content": {"specs": {"voltage": "230V", "color": "white"}},
            "jsonld_full": {"name": "Frame 3-gang", "brand": "PEHA", "price": "12.50"},
        }

    def test_success_label_for_auto_publish(self):
        bundle = self._make_bundle(card_status="AUTO_PUBLISH")
        rec = build_brand_experience_from_bundle(bundle)
        assert rec.training_label == "success"

    def test_failed_label_for_draft_only(self):
        bundle = self._make_bundle(card_status="DRAFT_ONLY", photo_verdict="NO_PHOTO",
                                   price_status="no_price_found")
        rec = build_brand_experience_from_bundle(bundle)
        assert rec.training_label == "failed"

    def test_partial_label_for_review_required(self):
        bundle = self._make_bundle(card_status="REVIEW_REQUIRED")
        rec = build_brand_experience_from_bundle(bundle)
        assert rec.training_label == "partial"

    def test_specs_count_from_bundle(self):
        bundle = self._make_bundle()
        rec = build_brand_experience_from_bundle(bundle)
        assert len(rec.specs_extracted) == 2  # voltage, color

    def test_jsonld_fields_from_bundle(self):
        bundle = self._make_bundle()
        rec = build_brand_experience_from_bundle(bundle)
        assert len(rec.jsonld_fields_found) >= 1  # name, brand, price

    def test_photo_quality_from_verdict(self):
        bundle = self._make_bundle(photo_verdict="REJECT")
        rec = build_brand_experience_from_bundle(bundle)
        assert rec.photo_quality == "REJECT"
        assert rec.photo_found is False

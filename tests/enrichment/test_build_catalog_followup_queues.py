import json
import sys
from pathlib import Path


_scripts = Path(__file__).resolve().parents[2] / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from build_catalog_followup_queues import run


def test_build_catalog_followup_queues_splits_photo_and_price_followups(tmp_path):
    evidence_dir = tmp_path / "evidence"
    output_dir = tmp_path / "queues"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    reject_bundle = {
        "pn": "010130.10",
        "name": "Module",
        "brand": "Honeywell",
        "card_status": "REVIEW_REQUIRED",
        "photo": {"verdict": "REJECT", "verdict_reason": "wrong image"},
        "merchandising": {"image_status": "rejected", "image_local_path": ""},
        "price": {"price_status": "public_price", "source_url": "https://example.com/module"},
        "content": {"site_placement": "Каталог/Системы безопасности", "product_type": "Модуль", "description_source": "seed"},
    }
    price_gap_bundle = {
        "pn": "1011994",
        "name": "Earmuff",
        "brand": "Honeywell",
        "card_status": "REVIEW_REQUIRED",
        "photo": {"verdict": "KEEP"},
        "merchandising": {"image_status": "placeholder", "image_local_path": "D:/tmp/example.jpg"},
        "price": {"price_status": "no_price_found", "source_url": ""},
        "content": {"site_placement": "Каталог/СИЗ", "product_type": "Наушники", "description_source": "seed"},
    }
    (evidence_dir / "evidence_010130.10.json").write_text(json.dumps(reject_bundle, ensure_ascii=False), encoding="utf-8")
    (evidence_dir / "evidence_1011994.json").write_text(json.dumps(price_gap_bundle, ensure_ascii=False), encoding="utf-8")

    summary = run(evidence_dir=evidence_dir, output_dir=output_dir, prefix="test")

    assert summary["source_bundle_count"] == 2
    assert summary["photo_recovery_count"] == 1
    assert summary["price_followup_count"] == 1

    photo_rows = [json.loads(line) for line in Path(summary["photo_recovery_queue"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    price_rows = [json.loads(line) for line in Path(summary["price_followup_queue"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    assert photo_rows[0]["part_number"] == "010130.10"
    assert photo_rows[0]["suggested_action"] == "find_replacement_photo_from_trusted_source"
    assert price_rows[0]["part_number"] == "1011994"
    assert price_rows[0]["suggested_action"] == "find_admissible_price_source_or_confirm_no_price"

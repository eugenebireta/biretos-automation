import csv
import json
import sys
from pathlib import Path

import pandas as pd


_scripts = Path(__file__).resolve().parents[2] / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from export_pipeline import build_evidence_bundle
from local_catalog_refresh import run


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_local_catalog_refresh_applies_seeded_content_and_merchandising(tmp_path):
    input_file = tmp_path / "honeywell.tsv"
    evidence_dir = tmp_path / "evidence"
    output_root = tmp_path / "refresh_output"
    export_dir = tmp_path / "canonical_export"
    product_data_file = tmp_path / "product_data.json"
    photo_manifest = tmp_path / "photo_manifest.jsonl"
    photo_verdict_file = tmp_path / "photo_verdict.json"
    enhanced_path = tmp_path / "photos_enhanced" / "1000106__catalog_placeholder_v1__deadbeef.jpg"

    evidence_dir.mkdir(parents=True, exist_ok=True)
    enhanced_path.parent.mkdir(parents=True, exist_ok=True)
    enhanced_path.write_bytes(b"fake-enhanced")

    df = pd.DataFrame(
        [
            {
                "Параметр: Партномер": "1000106",
                "Название товара или услуги": "Беруши 304L CORDED EARPLUG",
                "Описание": "Seeded описание для карточки.",
                "Размещение на сайте": "Каталог/СИЗ",
                "Параметр: Тип товара": "Беруши",
                "Цена продажи": "13095,00",
                "Параметр: Бренд": "Honeywell",
            }
        ]
    )
    df.to_csv(input_file, sep="\t", index=False, encoding="utf-16")

    bundle = build_evidence_bundle(
        pn="1000106",
        name="Беруши 304L CORDED EARPLUG",
        brand="Honeywell",
        photo_result={
            "path": str(tmp_path / "photos" / "1000106.jpg"),
            "sha1": "deadbeef1234567890",
            "width": 344,
            "height": 426,
            "size_kb": 43,
            "source": "cached",
        },
        vision_verdict={"verdict": "KEEP", "reason": "ok"},
        price_result={
            "price_status": "public_price",
            "price_usd": 68.25,
            "currency": "AED",
            "rub_price": 1638.0,
            "source_url": "https://example.com/1000106",
            "source_tier": "industrial",
            "stock_status": "out_of_stock",
            "offer_unit_basis": "piece",
            "offer_qty": 1,
        },
        datasheet_result={"datasheet_status": "skipped"},
        run_ts="2026-04-01T00:00:00Z",
    )
    (evidence_dir / "evidence_1000106.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    photo_verdict_file.write_text(
        json.dumps(
            {
                "1000106": {
                    "verdict": "KEEP",
                    "reason": "image matches product",
                    "path": str(tmp_path / "photos" / "1000106.jpg"),
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_jsonl(
        photo_manifest,
        [
            {
                "part_number": "1000106",
                "enhanced_local_path": str(enhanced_path),
                "enhanced_exists": True,
                "output_photo_status": "placeholder",
                "derivative_kind": "placeholder_enhanced",
                "replacement_required": True,
                "lineage_preserved": True,
                "source_photo_verdict": "KEEP",
                "cleanup_recommended": False,
            }
        ],
    )

    summary = run(
        input_file=input_file,
        evidence_dir=evidence_dir,
        canonical_evidence_dir=evidence_dir,
        photo_manifest=photo_manifest,
        photo_verdict_file=photo_verdict_file,
        output_root=output_root,
        canonical_export_dir=export_dir,
        canonical_data_file=product_data_file,
        promote_canonical=True,
    )

    assert summary["refreshed_bundle_count"] == 1
    assert summary["content_seeded_count"] == 1
    assert summary["merchandising_attached_count"] == 1

    refreshed_bundle = json.loads((evidence_dir / "evidence_1000106.json").read_text(encoding="utf-8"))
    assert refreshed_bundle["content"]["description"] == "Seeded описание для карточки."
    assert refreshed_bundle["content"]["description_source"] == "insales_import_seed"
    assert refreshed_bundle["content"]["site_placement"] == "Каталог/СИЗ"
    assert refreshed_bundle["content"]["product_type"] == "Беруши"
    assert refreshed_bundle["merchandising"]["image_local_path"] == str(enhanced_path)
    assert refreshed_bundle["merchandising"]["image_status"] == "placeholder"

    rows = list(csv.DictReader((export_dir / "insales_export.csv").open(encoding="utf-8-sig")))
    assert len(rows) == 1
    assert rows[0]["Изображение"] == f"[LOCAL:{enhanced_path}]"
    assert rows[0]["Описание"] == "Seeded описание для карточки."
    assert rows[0]["Источник описания"] == "insales_import_seed"
    assert rows[0]["Размещение на сайте"] == "Каталог/СИЗ"
    assert rows[0]["Тип товара"] == "Беруши"
    assert rows[0]["Статус изображения"] == "placeholder"

    product_data = json.loads(product_data_file.read_text(encoding="utf-8"))
    assert product_data["1000106"]["description"] == "Seeded описание для карточки."
    assert product_data["1000106"]["image_local_path"] == str(enhanced_path)

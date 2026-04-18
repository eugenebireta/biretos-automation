"""Export collected data in format ready for the categorizer chat.

Output: downloads/staging/from_datasheet_for_categorizer.json
Format suitable for merging into catalog_knowledge_base.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
OUT_FILE = ROOT / "downloads" / "staging" / "from_datasheet_for_categorizer.json"


def main():
    output = {}
    stats = {"total": 0, "with_ean": 0, "with_specs": 0, "with_photos": 0, "with_datasheet": 0, "with_description": 0, "brand_corrected": 0}

    # Load descriptions
    seo_file = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "descriptions_seo.json"
    seo_desc = json.loads(seo_file.read_text(encoding="utf-8")) if seo_file.exists() else {}

    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "" or pn in {"---", "--", "_", "PN", "-----"}:
            continue
        stats["total"] += 1
        ds = d.get("from_datasheet", {})
        if not ds:
            continue

        entry = {
            "pn": pn,
            "brand": d.get("brand", ""),
            "subbrand": d.get("subbrand", ""),
        }
        # Brand correction flag
        corrections = ds.get("_corrections") or {}
        if corrections.get("original_brand"):
            entry["brand_corrected"] = True
            entry["original_brand"] = corrections["original_brand"]
            entry["brand_correction_reason"] = corrections.get("brand_correction_reason", "")
            stats["brand_corrected"] += 1
        if corrections.get("marked_wrong"):
            entry["marked_wrong"] = True
            entry["marked_wrong_reason"] = corrections.get("reason", "")
        if corrections.get("needs_new_datasheet"):
            entry["needs_new_datasheet"] = True
        # SEO description
        pn_safe = pn.replace("/", "_").replace(" ", "_")
        sd = seo_desc.get(pn) or seo_desc.get(pn_safe, {})
        if sd.get("word_count", 0) >= 150:
            entry["description_seo_ru"] = sd["description_seo_ru"]
            entry["description_words"] = sd["word_count"]
            entry["description_model"] = sd.get("model", "")
            stats["with_description"] += 1
        if ds.get("title"):
            entry["title"] = ds["title"]
        if ds.get("description"):
            entry["description"] = ds["description"][:1000]
        if ds.get("series"):
            entry["series"] = ds["series"]
        if ds.get("category"):
            entry["category_from_datasheet"] = ds["category"]
        if ds.get("article_no"):
            entry["article_no"] = ds["article_no"]
        if ds.get("ean"):
            entry["ean"] = ds["ean"]
            entry["ean_source"] = ds.get("ean_source", "")
            stats["with_ean"] += 1
        if ds.get("specs"):
            entry["specs"] = ds["specs"]
            stats["with_specs"] += 1
        if ds.get("weight_g"):
            entry["weight_g"] = ds["weight_g"]
        if ds.get("dimensions_mm"):
            entry["dimensions_mm"] = ds["dimensions_mm"]
        if ds.get("certifications"):
            entry["certifications"] = ds["certifications"]
        if ds.get("datasheet_pdf"):
            entry["datasheet_pdf"] = ds["datasheet_pdf"]
            stats["with_datasheet"] += 1
        if ds.get("product_photos"):
            entry["product_photos"] = ds["product_photos"]
            stats["with_photos"] += 1

        output[pn] = entry

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Exported: {OUT_FILE}")
    print(f"Total SKUs: {stats['total']}")
    print(f"With from_datasheet block: {len(output)}")
    print(f"  with EAN: {stats['with_ean']}")
    print(f"  with specs: {stats['with_specs']}")
    print(f"  with datasheet PDF: {stats['with_datasheet']}")
    print(f"  with product photos: {stats['with_photos']}")
    print(f"  with description (>=150 words): {stats['with_description']}")
    print(f"  brand auto-corrected: {stats['brand_corrected']}")


if __name__ == "__main__":
    main()

"""Build training dataset for LOCAL AI models.

Collects training pairs for 3 tasks:
1. PDF -> specs/EAN extraction (Gemini → local Qwen2-VL/LayoutLMv3)
2. URL -> is_correct_product classification (GPT/Haiku → local binary classifier)
3. Photo -> product identity (Haiku → local CLIP fine-tune)

Output:
- downloads/training_v2/datasheet_extraction.jsonl (PDF path + extracted JSON)
- downloads/training_v2/url_validation.jsonl (URL + verdict)
- downloads/training_v2/photo_identity.jsonl (photo path + label)
"""
from __future__ import annotations

import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent
TRAINING_DIR = ROOT / "downloads" / "training_v2"
TRAINING_DIR.mkdir(parents=True, exist_ok=True)


def build_datasheet_training():
    """PDF → extracted JSON pairs for fine-tuning PDF parser."""
    parsed = json.loads((ROOT / "downloads/staging/tier_collector_output/datasheet_extracted.json").read_text(encoding="utf-8"))
    validation = json.loads((ROOT / "downloads/staging/tier_collector_output/datasheet_validation.json").read_text(encoding="utf-8")) if (ROOT / "downloads/staging/tier_collector_output/datasheet_validation.json").exists() else {}

    out_file = TRAINING_DIR / "datasheet_extraction.jsonl"

    with open(out_file, "w", encoding="utf-8") as f:
        count = 0
        for pn, data in parsed.items():
            pdf_path = ROOT / "downloads" / "datasheets_v2" / f"{pn}.pdf"
            if not pdf_path.exists():
                continue

            # Only use validated-as-correct entries for training
            verdict = validation.get(pn, {}).get("verdict", "UNCERTAIN")

            # Skip WRONG/EMPTY for training
            if verdict in ("WRONG", "EMPTY"):
                continue

            # Only use records with real data
            has_real_data = bool(data.get("ean") or len(data.get("specs", {})) >= 3 or data.get("weight_g"))
            if not has_real_data and verdict != "CORRECT":
                continue

            record = {
                "pdf_path": str(pdf_path.relative_to(ROOT)),
                "pdf_size_kb": pdf_path.stat().st_size // 1024,
                "pn": pn,
                "verdict": verdict,
                "extracted": {
                    "pn": data.get("pn", ""),
                    "brand": data.get("brand", ""),
                    "title": data.get("title", ""),
                    "description": data.get("description", ""),
                    "specs": data.get("specs", {}),
                    "ean": data.get("ean", ""),
                    "dimensions_mm": data.get("dimensions_mm", ""),
                    "weight_g": data.get("weight_g", ""),
                    "series": data.get("series", ""),
                    "category": data.get("category", ""),
                },
                "labeled_by": "gemini-2.5-flash",
                "use_for_training": verdict == "CORRECT" or bool(data.get("ean")),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    return count


def build_url_validation_training():
    """URL → correct/wrong classification from SerpAPI search + validation."""
    validation = json.loads((ROOT / "downloads/staging/tier_collector_output/datasheet_validation.json").read_text(encoding="utf-8")) if (ROOT / "downloads/staging/tier_collector_output/datasheet_validation.json").exists() else {}
    search_stats = json.loads((ROOT / "downloads/staging/pipeline_v2_output/datasheet_search_stats.json").read_text(encoding="utf-8")) if (ROOT / "downloads/staging/pipeline_v2_output/datasheet_search_stats.json").exists() else {}

    out_file = TRAINING_DIR / "url_datasheet_validation.jsonl"

    with open(out_file, "w", encoding="utf-8") as f:
        count = 0
        # Known-good domains
        search_stats.get("domains_downloaded", {})
        # Known-bad: domains that downloaded but PDF was wrong
        for pn, val in validation.items():
            if val.get("verdict") == "WRONG":
                # This domain-PN combo was a false positive
                record = {
                    "pn": pn,
                    "verdict": "WRONG",
                    "reason": val.get("reason", ""),
                    "extracted_pn": val.get("extracted_pn", ""),
                    "extracted_title": val.get("extracted_title", ""),
                    "use_for_training": True,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1
            elif val.get("verdict") == "CORRECT":
                record = {
                    "pn": pn,
                    "verdict": "CORRECT",
                    "reason": val.get("reason", ""),
                    "use_for_training": True,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    return count


def build_evidence_training():
    """Evidence snapshots → structured product data pairs (for entity resolution training)."""
    out_file = TRAINING_DIR / "evidence_to_structured.jsonl"

    ev_dir = ROOT / "downloads" / "evidence"
    parsed = json.loads((ROOT / "downloads/staging/tier_collector_output/datasheet_extracted.json").read_text(encoding="utf-8"))

    with open(out_file, "w", encoding="utf-8") as f:
        count = 0
        for ef in sorted(ev_dir.glob("evidence_*.json")):
            d = json.loads(ef.read_text(encoding="utf-8"))
            pn = d.get("pn", "")
            if not pn or pn.strip("-_") == "":
                continue

            # Input: raw evidence (Excel data)
            content = d.get("content") or {}
            input_data = {
                "pn": pn,
                "brand_hint": d.get("brand", ""),
                "seed_name": content.get("seed_name", ""),
                "our_price_raw": d.get("our_price_raw", ""),
                "expected_category": d.get("expected_category", ""),
            }

            # Output: structured data from datasheet + DR
            ds_data = parsed.get(pn, {})
            norm = d.get("normalized") or {}
            dr = d.get("deep_research") or {}

            output_data = {
                "confirmed_brand": d.get("brand", "") or (d.get("structured_identity") or {}).get("confirmed_manufacturer", ""),
                "subbrand": d.get("subbrand", ""),
                "title": ds_data.get("title") or dr.get("title_ru", "") or d.get("assembled_title", ""),
                "description": ds_data.get("description") or norm.get("best_description", ""),
                "price": norm.get("best_price"),
                "price_currency": norm.get("best_price_currency", ""),
                "photo_url": norm.get("best_photo_url", ""),
                "ean": ds_data.get("ean", ""),
                "specs": ds_data.get("specs", {}),
                "weight_g": ds_data.get("weight_g", ""),
                "dimensions_mm": ds_data.get("dimensions_mm", ""),
                "series": ds_data.get("series", ""),
                "identity_level": d.get("identity_level", ""),
            }

            record = {
                "pn": pn,
                "input": input_data,
                "output": output_data,
                "has_datasheet": bool(ds_data),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    return count


def main():
    print("=" * 90)
    print("BUILD TRAINING DATA for local AI models")
    print("=" * 90)

    c1 = build_datasheet_training()
    print(f"  datasheet_extraction.jsonl:       {c1} records")

    c2 = build_url_validation_training()
    print(f"  url_datasheet_validation.jsonl:   {c2} records")

    c3 = build_evidence_training()
    print(f"  evidence_to_structured.jsonl:     {c3} records")

    print(f"\n  Output dir: {TRAINING_DIR}")
    print()
    print("USE FOR:")
    print("  1. Fine-tune Qwen2-VL on datasheet_extraction.jsonl -> local PDF parser")
    print("  2. Train binary classifier on url_datasheet_validation.jsonl -> filter wrong PDFs")
    print("  3. Fine-tune NER/entity-extraction model on evidence_to_structured.jsonl")


if __name__ == "__main__":
    main()

"""Lineage report for a single SKU.

Answers the question: "for SKU X, where did each field come from,
what was dropped, which model version produced which data, and when?"

Per external audit ext-3 (2026-04-18): without per-SKU lineage, silent
failures accumulate faster than audits find them. 249→0 specs in
canonical builder existed "for weeks" before discovery. This CLI is
the preventive that catches the next one instantly.

Usage:
    python scripts/pipeline_v2/lineage.py <pn>
    python scripts/pipeline_v2/lineage.py <pn> --json         # machine-readable
    python scripts/pipeline_v2/lineage.py <pn> --show-rejects # include normalizer rejects
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
CANONICAL_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "canonical_products.json"
UNIFIED_FILE = ROOT / "downloads" / "knowledge" / "unified_product_dataset.json"
REJECTIONS_FILE = ROOT / "downloads" / "staging" / "normalizer_rejections.jsonl"
TRAIN_DIR = ROOT / "downloads" / "knowledge" / "training_data" / "specs_extraction"
GOLDEN_DIR = ROOT / "golden" / "specs_extraction"


def load_evidence(pn: str) -> dict | None:
    f = EV_DIR / f"evidence_{pn}.json"
    if not f.exists():
        # Try variants (slash vs underscore)
        f = EV_DIR / f"evidence_{pn.replace('/', '_')}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def load_canonical(pn: str) -> dict | None:
    if not CANONICAL_FILE.exists():
        return None
    data = json.loads(CANONICAL_FILE.read_text(encoding="utf-8"))
    for p in data:
        if (p.get("identity") or {}).get("pn") == pn:
            return p
    return None


def load_unified(pn: str) -> dict | None:
    if not UNIFIED_FILE.exists():
        return None
    data = json.loads(UNIFIED_FILE.read_text(encoding="utf-8"))
    for p in data.get("products", []):
        if p.get("pn") == pn:
            return p
    return None


def load_rejections(pn: str) -> list[dict]:
    if not REJECTIONS_FILE.exists():
        return []
    out = []
    for line in REJECTIONS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("pn") == pn:
            out.append(rec)
    return out


def load_training_pairs(pn: str) -> list[dict]:
    """All training pair files for this PN (one per model, each with output)."""
    out = []
    for model_tag in ["gemini_flash", "haiku", "sonnet"]:
        f = TRAIN_DIR / f"{pn}__{model_tag}.json"
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                specs = d.get("output", {}).get("specs") or {}
                out.append({
                    "model": d.get("model", model_tag),
                    "model_tag": model_tag,
                    "specs_count": len(specs) if isinstance(specs, dict) else 0,
                    "usage": d.get("usage", {}),
                    "prompt_bytes": len(d.get("prompt", "")),
                })
            except Exception:
                pass
    return out


def load_golden(pn: str) -> dict | None:
    f = GOLDEN_DIR / f"{pn}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def build_report(pn: str) -> dict:
    ev = load_evidence(pn) or {}
    can = load_canonical(pn) or {}
    uni = load_unified(pn) or {}
    rej = load_rejections(pn)
    train = load_training_pairs(pn)
    golden = load_golden(pn)

    fd = ev.get("from_datasheet") or {}
    norm = ev.get("normalized") or {}
    si = ev.get("structured_identity") or {}
    dr = ev.get("deep_research") or {}

    report = {
        "pn": pn,
        "evidence_present": bool(ev),
        "canonical_present": bool(can),
        "unified_present": bool(uni),
        "identity": {
            "brand": ev.get("brand") or si.get("confirmed_manufacturer") or "",
            "subbrand": ev.get("subbrand", ""),
            "series": si.get("series") or fd.get("series") or "",
            "product_type": si.get("product_type") or ev.get("content", {}).get("product_type") or "",
            "source": "structured_identity + evidence.brand",
        },
        "title": {
            "title_ru_canonical": (can.get("title_ru") or "")[:100],
            "title_datasheet": (fd.get("title") or "")[:100],
            "source": "canonical.title_ru (normalized via Layer 5.5 → datasheet/dr/assembled)",
        },
        "price": {
            "best_price": can.get("best_price"),
            "currency": can.get("best_price_currency"),
            "source_domain": can.get("best_price_source"),
            "tier": can.get("best_price_tier"),
            "evidence_id": can.get("best_price_evidence_id"),
        },
        "photo": {
            "best_photo_url": can.get("best_photo_url"),
            "tier": can.get("best_photo_tier"),
            "total_in_set": len(can.get("photo_set") or []),
        },
        "description": {
            "has_seo": bool(norm.get("best_description_ru") and
                            (norm.get("best_description_ru_source") or "").startswith("seo_merger")),
            "word_count": norm.get("best_description_ru_word_count"),
            "source": norm.get("best_description_ru_source") or "unknown",
            "char_count": len(norm.get("best_description_ru") or ""),
        },
        "specs": {
            "count_in_evidence": len(fd.get("specs") or {}) if isinstance(fd.get("specs"), dict) else 0,
            "count_in_canonical_raw_merged": len(can.get("specs", {}).get("raw_merged") or {}),
            "weight_g_canonical": can.get("specs", {}).get("weight_g"),
            "length_mm_canonical": can.get("specs", {}).get("length_mm"),
            "width_mm_canonical": can.get("specs", {}).get("width_mm"),
            "height_mm_canonical": can.get("specs", {}).get("height_mm"),
            "material_canonical": can.get("specs", {}).get("material"),
            "ip_rating_canonical": can.get("specs", {}).get("ip_rating"),
        },
        "ean": {
            "datasheet_ean": fd.get("ean") or "",
            "canonical_ean": can.get("identity", {}).get("ean") or "",
        },
        "extraction_provenance": fd.get("latest_extraction") or {},
        "extraction_history": fd.get("extraction_history") or [],
        "normalizer_rejections": [
            {"field": r["field"], "raw_value": r["raw_value"], "reason": r["reason"],
             "source_key": r.get("source_key", ""), "ts": r["ts"]}
            for r in rej
        ],
        "training_pairs": train,
        "golden_entry": bool(golden),
        "golden_expected_specs_count": len((golden or {}).get("expected_output", {}).get("specs", {}) or {}) if golden else 0,
        "category": {
            "canonical_from_mapping": (uni.get("category") or {}).get("canonical"),
            "insales_paths": (uni.get("category") or {}).get("insales", "").split(" ## ") if uni else [],
            "ozon": (uni.get("category") or {}).get("ozon"),
            "wb": (uni.get("category") or {}).get("wb"),
        },
        "readiness": can.get("readiness") or {},
        "brand_corrected": fd.get("brand_corrected", False),
        "quality_flags": uni.get("quality_flags") or {},
    }
    return report


def print_human(rep: dict) -> None:
    pn = rep["pn"]
    print(f"═══ LINEAGE REPORT — {pn} ═══\n")

    if not rep["evidence_present"]:
        print(f"  ⚠ No evidence file found for {pn}")
        return

    idn = rep["identity"]
    print("IDENTITY")
    print(f"  brand:        {idn['brand']}  (subbrand: {idn['subbrand'] or '-'})")
    print(f"  series:       {idn['series'] or '-'}")
    print(f"  product_type: {idn['product_type'] or '-'}")

    print("\nTITLE")
    print(f"  canonical:  {rep['title']['title_ru_canonical'] or '(none)'}")
    print(f"  datasheet:  {rep['title']['title_datasheet'] or '(none)'}")

    price = rep["price"]
    print("\nPRICE")
    if price.get("best_price"):
        print(f"  {price['best_price']} {price.get('currency', '?')}  source={price.get('source_domain', '?')}  tier={price.get('tier', '?')}")
    else:
        print("  (none)")

    photo = rep["photo"]
    print("\nPHOTO")
    if photo.get("best_photo_url"):
        print(f"  url:       {photo['best_photo_url'][:100]}")
        print(f"  tier:      {photo.get('tier', '?')}, {photo['total_in_set']} in set")
    else:
        print("  (none)")

    desc = rep["description"]
    print("\nDESCRIPTION")
    print(f"  seo:       {desc['has_seo']}  wc={desc['word_count']}  chars={desc['char_count']}")
    print(f"  source:    {desc['source']}")

    specs = rep["specs"]
    print("\nSPECS")
    print(f"  evidence count:     {specs['count_in_evidence']}")
    print(f"  canonical merged:   {specs['count_in_canonical_raw_merged']}")
    print(f"  weight_g:           {specs.get('weight_g_canonical', '-')}")
    print(f"  LxWxH mm:           {specs.get('length_mm_canonical', '-')}x{specs.get('width_mm_canonical', '-')}x{specs.get('height_mm_canonical', '-')}")
    print(f"  material:           {specs.get('material_canonical', '-')}")
    print(f"  IP:                 {specs.get('ip_rating_canonical', '-')}")

    print("\nEAN")
    print(f"  datasheet: {rep['ean']['datasheet_ean'] or '(none)'}")
    print(f"  canonical: {rep['ean']['canonical_ean'] or '(none)'}")

    prov = rep["extraction_provenance"]
    print("\nEXTRACTION PROVENANCE (latest run)")
    if prov:
        print(f"  model:        {prov.get('model_id', '-')}")
        print(f"  prompt_sha:   {prov.get('prompt_sha_16', '-')}")
        print(f"  pdf_sha:      {(prov.get('pdf_sha256') or '')[:32]}...")
        print(f"  ran:          {prov.get('extracted_at', '-')}")
        print(f"  specs_count:  {prov.get('specs_count', '-')}")
        if prov.get("reason"):
            print(f"  reason:       {prov['reason']}")
    else:
        print("  (never extracted, or pre-dates provenance tracking)")

    hist = rep["extraction_history"]
    if len(hist) > 1:
        print(f"\n  FULL HISTORY ({len(hist)} runs):")
        for i, h in enumerate(hist):
            print(f"    [{i+1}] {h.get('extracted_at', '-')}  {h.get('model_id', '-')}  specs={h.get('specs_count', '?')}")

    rej = rep["normalizer_rejections"]
    if rej:
        print(f"\nNORMALIZER REJECTIONS ({len(rej)}):")
        for r in rej[:15]:
            print(f"  {r['field']:<15}  {r['reason']:<15}  raw={r['raw_value']!r}  key={r.get('source_key', '')}")
        if len(rej) > 15:
            print(f"  ... +{len(rej)-15} more")

    train = rep["training_pairs"]
    if train:
        print("\nTRAINING PAIRS (used for golden / local fine-tune):")
        for t in train:
            print(f"  {t['model_tag']:<15}  specs={t['specs_count']}  tokens_in={(t.get('usage') or {}).get('input_tokens', '-')}")

    if rep["golden_entry"]:
        print(f"\nGOLDEN ENTRY: present — expected_specs_count={rep['golden_expected_specs_count']}")

    cat = rep["category"]
    print("\nCATEGORY")
    insales = cat.get("insales_paths") or []
    print(f"  canonical: {cat.get('canonical_from_mapping') or '(none)'}")
    if insales:
        for p in insales[:5]:
            print(f"    insales:  {p}")
    if cat.get("ozon"):
        print(f"    ozon:     {cat['ozon'].get('type_name') or cat['ozon'].get('path') or '?'}")
    if cat.get("wb"):
        print(f"    wb:       {cat['wb'].get('subject_name') or '?'}")

    rd = rep["readiness"]
    print(f"\nREADINESS  insales={rd.get('insales', '?')}  ozon={rd.get('ozon', '?')}  wb={rd.get('wb', '?')}")

    if rep["brand_corrected"]:
        print("\n⚠ brand was auto-corrected during enrichment — verify against datasheet")

    qf = rep["quality_flags"]
    if qf:
        flags_set = {k: v for k, v in qf.items() if v}
        if flags_set:
            print(f"\nQUALITY FLAGS: {flags_set}")

    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pn", help="Part number to trace")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--show-rejects", action="store_true", help="Show all normalizer rejection lines (default: first 15)")
    args = parser.parse_args()

    rep = build_report(args.pn)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print_human(rep)


if __name__ == "__main__":
    main()

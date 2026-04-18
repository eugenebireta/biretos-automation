"""Collect ALL experience data for local AI training.

Consolidates:
1. datasheet_extraction — PDF → specs (primary training for local PDF parser)
2. photo_audit — image → category classifier
3. ean_prediction_rules — brand patterns for symbolic AI
4. gemini_vs_claude — model comparison for routing decisions
5. description_generation — text generation examples
6. domain_strategies — learned strategies per brand

Runs automatically after every pipeline batch.
Pairs saved with source, confidence, verified status for quality filtering.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
TRAINING_DIR = ROOT / "downloads" / "training_v2"
TRAINING_DIR.mkdir(parents=True, exist_ok=True)

EV_DIR = ROOT / "downloads" / "evidence"
OUT_DIR = ROOT / "downloads" / "training_v2"


def collect_datasheet_pairs():
    """PDF path + extracted JSON → for local PDF parser fine-tune (Qwen2-VL, LayoutLMv3)."""
    ds_data = json.loads((ROOT / "downloads/staging/tier_collector_output/datasheet_extracted.json").read_text(encoding="utf-8"))
    validation = json.loads((ROOT / "downloads/staging/tier_collector_output/datasheet_validation.json").read_text(encoding="utf-8")) if (ROOT / "downloads/staging/tier_collector_output/datasheet_validation.json").exists() else {}

    out = OUT_DIR / "datasheet_extraction.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        count = 0
        for pn, data in ds_data.items():
            pdf_path = ROOT / "downloads" / "datasheets_v2" / f"{pn}.pdf"
            if not pdf_path.exists():
                continue

            verdict = validation.get(pn, {}).get("verdict", "UNCERTAIN")
            if verdict in ("WRONG", "EMPTY"):
                continue

            has_data = bool(data.get("ean") or len(data.get("specs", {})) >= 3 or data.get("weight_g"))
            if not has_data and verdict != "CORRECT":
                continue

            record = {
                "pdf_path": str(pdf_path.relative_to(ROOT)),
                "pdf_size_kb": pdf_path.stat().st_size // 1024,
                "pn": pn,
                "verdict": verdict,
                "teacher_model": data.get("_model") or "gemini-2.5-flash",
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
                "use_for_training": verdict == "CORRECT" or bool(data.get("ean")),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def collect_ean_pairs():
    """PN + brand → EAN. For learning brand-specific EAN prediction."""
    out = OUT_DIR / "ean_prediction.jsonl"
    pairs_by_brand = defaultdict(list)

    for f in sorted(EV_DIR.glob("evidence_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        if not pn or pn.strip("-_") == "":
            continue
        si = d.get("structured_identity") or {}
        sub = d.get("subbrand", "")
        brand = sub or d.get("brand", "") or si.get("confirmed_manufacturer", "")
        from_ds = d.get("from_datasheet", {})
        ean = from_ds.get("ean", "")
        source = from_ds.get("ean_source", "")
        if ean and str(ean).isdigit() and len(str(ean)) == 13:
            pairs_by_brand[brand].append({
                "pn": pn, "brand": brand, "ean": ean,
                "source": source,
                "verified": source in ("datasheet_parse", "datasheet_focused"),
            })

    with open(out, "w", encoding="utf-8") as f:
        count = 0
        for brand, pairs in pairs_by_brand.items():
            for p in pairs:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
                count += 1
    return count


def collect_photo_audit_pairs():
    """Photo path + Gemini verdict → for local image classifier training."""
    audit_file = ROOT / "downloads" / "staging" / "tier_collector_output" / "photo_audit.json"
    if not audit_file.exists():
        return 0
    audit = json.loads(audit_file.read_text(encoding="utf-8"))

    out = OUT_DIR / "photo_classification.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        count = 0
        for photo_name, data in audit.items():
            if data.get("verdict") == "error":
                continue
            photo_path = ROOT / "downloads" / "datasheet_photos" / photo_name
            if not photo_path.exists():
                continue
            record = {
                "photo_path": str(photo_path.relative_to(ROOT)),
                "photo_size_kb": photo_path.stat().st_size // 1024,
                "verdict": data.get("verdict", ""),
                "pn": data.get("pn", ""),
                "brand": data.get("brand", ""),
                "teacher_model": "gemini-2.5-flash",
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def collect_description_pairs():
    """Product context → SEO description. For text-generation fine-tune."""
    desc_file = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "descriptions_seo.json"
    if not desc_file.exists():
        return 0
    desc = json.loads(desc_file.read_text(encoding="utf-8"))

    out = OUT_DIR / "description_generation.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        count = 0
        for pn, data in desc.items():
            word_count = data.get("word_count", 0)
            if word_count < 150:
                continue  # low-quality, skip for training

            # Get context from evidence
            ev_file = EV_DIR / f"evidence_{pn}.json"
            if not ev_file.exists():
                ev_file = EV_DIR / f"evidence_{pn.replace('_','/')}.json"
            if not ev_file.exists():
                continue
            d = json.loads(ev_file.read_text(encoding="utf-8"))
            si = d.get("structured_identity") or {}
            from_ds = d.get("from_datasheet", {})

            input_data = {
                "pn": pn,
                "brand": d.get("brand", "") or si.get("confirmed_manufacturer", ""),
                "series": from_ds.get("series", ""),
                "title": from_ds.get("title", "") or d.get("assembled_title", ""),
                "specs": from_ds.get("specs", {}),
                "weight_g": from_ds.get("weight_g", ""),
                "dimensions_mm": from_ds.get("dimensions_mm", ""),
                "ean": from_ds.get("ean", ""),
            }

            record = {
                "input": input_data,
                "output_html": data.get("description_seo_ru", ""),
                "word_count": word_count,
                "teacher_model": data.get("model", "gemini-2.5-flash"),
                "cost_usd": data.get("cost_usd", 0),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def collect_identity_pairs():
    """Excel seed_name → confirmed brand+pn+series. For entity resolution training."""
    out = OUT_DIR / "identity_resolution.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        count = 0
        for ef in sorted(EV_DIR.glob("evidence_*.json")):
            d = json.loads(ef.read_text(encoding="utf-8"))
            pn = d.get("pn", "")
            if not pn or pn.strip("-_") == "":
                continue
            il = d.get("identity_level", "")
            if il not in ("strong", "weak"):
                continue  # only labelled entries

            content = d.get("content") or {}
            si = d.get("structured_identity") or {}
            from_ds = d.get("from_datasheet", {})

            record = {
                "input": {
                    "raw_pn": pn,
                    "seed_name": content.get("seed_name", "") or d.get("name", ""),
                    "brand_hint": d.get("brand", ""),
                },
                "output": {
                    "confirmed_brand": d.get("brand", "") or si.get("confirmed_manufacturer", ""),
                    "subbrand": d.get("subbrand", ""),
                    "series": from_ds.get("series", ""),
                    "identity_level": il,
                    "ean": from_ds.get("ean", ""),
                    "datasheet_pdf": from_ds.get("datasheet_pdf", ""),
                },
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def collect_model_comparison():
    """Gemini vs Claude results — for AI router to learn which model to use when."""
    comp_file = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "gemini_vs_claude_comparison.json"
    if not comp_file.exists():
        return 0
    data = json.loads(comp_file.read_text(encoding="utf-8"))

    out = OUT_DIR / "model_comparison.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        count = 0
        for pn, pair in data.get("results", {}).items():
            gem = pair.get("gemini", {})
            claude = pair.get("claude", {})
            record = {
                "pn": pn,
                "task": "datasheet_parsing",
                "gemini": {
                    "time": gem.get("elapsed_sec"),
                    "cost_usd": gem.get("cost_usd"),
                    "ean_found": bool(gem.get("data", {}).get("ean")),
                    "specs_count": len(gem.get("data", {}).get("specs", {})) if isinstance(gem.get("data", {}).get("specs"), dict) else 0,
                },
                "claude_haiku": {
                    "time": claude.get("elapsed_sec"),
                    "cost_usd": claude.get("cost_usd"),
                    "ean_found": bool(claude.get("data", {}).get("ean")),
                    "specs_count": len(claude.get("data", {}).get("specs", {})) if isinstance(claude.get("data", {}).get("specs"), dict) else 0,
                },
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def collect_quality_audit_pairs():
    """Sonnet quality check results → training pairs for local QA model.

    Input: product data (brand, pn, title, ean, specs, description)
    Output: verdict + issues + recommendations

    This teaches local model to find same issues Sonnet finds.
    """
    qc_file = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "quality_check.json"
    if not qc_file.exists():
        return 0
    qc = json.loads(qc_file.read_text(encoding="utf-8"))

    out = OUT_DIR / "quality_audit.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        count = 0
        for pn, result in qc.items():
            if "error" in result:
                continue
            # Load evidence for input context
            ev_file = EV_DIR / f"evidence_{pn}.json"
            if not ev_file.exists():
                ev_file = EV_DIR / f"evidence_{pn.replace('_','/')}.json"
            if not ev_file.exists():
                continue
            d = json.loads(ev_file.read_text(encoding="utf-8"))
            fd = d.get("from_datasheet", {})
            si = d.get("structured_identity") or {}

            record = {
                "input": {
                    "pn": pn,
                    "brand": d.get("brand", "") or si.get("confirmed_manufacturer", ""),
                    "seed_name": (d.get("content") or {}).get("seed_name", "") or d.get("name", ""),
                    "title": fd.get("title", ""),
                    "ean": fd.get("ean", ""),
                    "specs_count": len(fd.get("specs", {})),
                    "has_description": bool(fd.get("description") or (d.get("normalized") or {}).get("best_description")),
                    "has_weight": bool(fd.get("weight_g")),
                    "has_dimensions": bool(fd.get("dimensions_mm")),
                },
                "output": {
                    "pn_brand_match": result.get("pn_brand_match"),
                    "title_quality": result.get("title_quality"),
                    "ean_plausibility": result.get("ean_plausibility"),
                    "description_quality": result.get("description_quality"),
                    "specs_completeness": result.get("specs_completeness"),
                    "overall_verdict": result.get("overall_verdict"),
                    "issues": result.get("issues", []),
                    "recommendations": result.get("recommendations", []),
                },
                "teacher_model": "claude-sonnet-4-5",
                "cost_usd": result.get("_cost_usd", 0),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def collect_fix_log_pairs():
    """Auto-fix decisions → training for corrector model."""
    fix_file = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "auto_fix_log.jsonl"
    if not fix_file.exists():
        return 0

    out = OUT_DIR / "auto_fix_decisions.jsonl"
    with open(out, "w", encoding="utf-8") as wf:
        count = 0
        for line in fix_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                wf.write(line + "\n")
                count += 1
    return count


def collect_domain_strategies():
    """Save domain strategies as training data for policy learning."""
    strat_dir = ROOT / "config" / "domain_strategies"
    if not strat_dir.exists():
        return 0
    out = OUT_DIR / "domain_strategies.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        count = 0
        for strat_file in strat_dir.glob("*.json"):
            strat = json.loads(strat_file.read_text(encoding="utf-8"))
            f.write(json.dumps(strat, ensure_ascii=False) + "\n")
            count += 1
    return count


def main():
    print("=" * 80)
    print(f"Experience Collector ({datetime.now().isoformat()})")
    print("=" * 80)

    stats = {}
    stats["datasheet_extraction"] = collect_datasheet_pairs()
    print(f"  datasheet_extraction.jsonl:     {stats['datasheet_extraction']:>5}")

    stats["ean_prediction"] = collect_ean_pairs()
    print(f"  ean_prediction.jsonl:           {stats['ean_prediction']:>5}")

    stats["photo_classification"] = collect_photo_audit_pairs()
    print(f"  photo_classification.jsonl:     {stats['photo_classification']:>5}")

    stats["description_generation"] = collect_description_pairs()
    print(f"  description_generation.jsonl:   {stats['description_generation']:>5}")

    stats["identity_resolution"] = collect_identity_pairs()
    print(f"  identity_resolution.jsonl:      {stats['identity_resolution']:>5}")

    stats["model_comparison"] = collect_model_comparison()
    print(f"  model_comparison.jsonl:         {stats['model_comparison']:>5}")

    stats["domain_strategies"] = collect_domain_strategies()
    print(f"  domain_strategies.jsonl:        {stats['domain_strategies']:>5}")

    stats["quality_audit"] = collect_quality_audit_pairs()
    print(f"  quality_audit.jsonl:            {stats['quality_audit']:>5}")

    stats["auto_fix_decisions"] = collect_fix_log_pairs()
    print(f"  auto_fix_decisions.jsonl:       {stats['auto_fix_decisions']:>5}")

    # Save meta
    meta_file = TRAINING_DIR / "experience_stats.json"
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "datasets": stats,
    }
    if meta_file.exists():
        history = json.loads(meta_file.read_text(encoding="utf-8"))
        if isinstance(history, dict):
            history = [history]
    else:
        history = []
    history.append(meta)
    # Keep last 20 snapshots
    history = history[-20:]
    meta_file.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n  Total training pairs: {sum(stats.values())}")
    print(f"  Meta log: {meta_file}")


if __name__ == "__main__":
    main()

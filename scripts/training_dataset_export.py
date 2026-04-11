"""training_dataset_export.py — Export shadow_log data as training datasets for local AI.

7 dataset types (Phase 4.2 expanded):
1. price_extraction — (prompt, response_raw, pn, brand) → structured price output
2. photo_verdict    — (image_url, pn, brand, page_title) → KEEP/REJECT + reason
3. spec_extraction  — (page_text, pn, brand) → structured specs dict
4. category_classification — (pn, title, page_class, brand) → correct_category
5. search_strategy  — (pn, brand, family) → {queries_used, worked, failed}
6. page_ranking     — (candidate_urls, ranked_result, method) → page rank decision
7. unit_judge       — (price, currency, context_text) → unit_basis verdict

Output: training_data/{dataset_name}.json (one file per dataset)

Usage:
  python scripts/training_dataset_export.py [--shadow-dir shadow_log] [--evidence-dir downloads/evidence]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

_ROOT = Path(_scripts_dir).parent
_DEFAULT_SHADOW_DIR = _ROOT / "shadow_log"
_DEFAULT_EVIDENCE_DIR = _ROOT / "downloads" / "evidence"
_DEFAULT_OUTPUT_DIR = _ROOT / "training_data"


def _read_jsonl(path: Path) -> list[dict]:
    """Read all records from a JSONL file. Returns empty list on error."""
    records = []
    if not path.exists():
        return records
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass
    return records


def _read_all_jsonl_in_dir(directory: Path, pattern: str) -> list[dict]:
    """Read all JSONL files matching pattern from directory."""
    records = []
    if not directory.exists():
        return records
    for f in sorted(directory.glob(pattern)):
        records.extend(_read_jsonl(f))
    return records


def export_price_extraction_dataset(shadow_dir: Path = _DEFAULT_SHADOW_DIR) -> list[dict]:
    """Export price extraction training pairs.

    Each record: {pn, brand, prompt, response_raw, response_parsed, parse_success,
                  source_url, source_type, model, ts}
    Only includes records where response_raw is not None/empty (actual model responses).
    """
    all_records = _read_all_jsonl_in_dir(shadow_dir, "price_extraction_*.jsonl")
    dataset = []
    for r in all_records:
        raw = r.get("response_raw")
        if not raw:  # Skip None and empty string (API failures)
            continue
        if not r.get("parse_success"):  # Only usable training pairs
            continue
        parsed = r.get("response_parsed") or {}
        if not parsed.get("pn_found") and not parsed.get("pn_exact_confirmed"):
            continue  # Skip low-quality responses
        dataset.append({
            "dataset": "price_extraction",
            "pn": r.get("pn", ""),
            "brand": r.get("brand", ""),
            "prompt": r.get("prompt", ""),
            "prompt_version": r.get("prompt_version"),
            "response_raw": raw,
            "response_parsed": parsed,
            "source_url": r.get("source_url", ""),
            "source_type": r.get("source_type", ""),
            "model": r.get("model", ""),
            "model_resolved": r.get("model_resolved", ""),
            "pipeline_stage": r.get("pipeline_stage", ""),
            "ts": r.get("ts", ""),
        })
    return dataset


def export_photo_verdict_dataset(shadow_dir: Path = _DEFAULT_SHADOW_DIR) -> list[dict]:
    """Export photo verdict training pairs.

    Each record: {pn, brand, prompt, response_raw, verdict, reason, model, ts}
    Reads from image_validation_*.jsonl files.
    """
    all_records = _read_all_jsonl_in_dir(shadow_dir, "image_validation_*.jsonl")
    dataset = []
    for r in all_records:
        raw = r.get("response_raw")
        if not raw:
            continue
        parsed = r.get("response_parsed") or {}
        verdict = parsed.get("verdict") or ""
        if not verdict:
            continue
        dataset.append({
            "dataset": "photo_verdict",
            "pn": r.get("pn", ""),
            "brand": r.get("brand", ""),
            "prompt": r.get("prompt", ""),
            "prompt_version": r.get("prompt_version"),
            "response_raw": raw,
            "verdict": verdict,
            "reason": parsed.get("reason", ""),
            "confidence": parsed.get("confidence", ""),
            "source_url": r.get("source_url", ""),
            "model": r.get("model", ""),
            "model_resolved": r.get("model_resolved", ""),
            "pipeline_stage": r.get("pipeline_stage", ""),
            "ts": r.get("ts", ""),
        })
    return dataset


def export_spec_extraction_dataset(shadow_dir: Path = _DEFAULT_SHADOW_DIR) -> list[dict]:
    """Export spec extraction training pairs.

    Each record: {pn, brand, page_text_snippet, extracted_specs, spec_count,
                  source_url, prompt_version, model_resolved, pipeline_stage, ts}
    Reads from spec_extraction_*.jsonl files in shadow_log.
    """
    all_records = _read_all_jsonl_in_dir(shadow_dir, "spec_extraction_*.jsonl")
    dataset = []
    for r in all_records:
        parsed = r.get("response_parsed") or {}
        if not parsed:
            continue
        dataset.append({
            "dataset": "spec_extraction",
            "pn": r.get("pn", ""),
            "brand": r.get("brand", ""),
            "page_text_snippet": r.get("prompt", ""),
            "extracted_specs": parsed,
            "spec_count": len(parsed) if isinstance(parsed, dict) else 0,
            "source_url": r.get("source_url", ""),
            "prompt_version": r.get("prompt_version"),
            "model_resolved": r.get("model_resolved", ""),
            "pipeline_stage": r.get("pipeline_stage", ""),
            "ts": r.get("ts", ""),
        })
    return dataset


def export_category_classification_dataset(
    evidence_dir: Path = _DEFAULT_EVIDENCE_DIR,
    shadow_dir: Path = _DEFAULT_SHADOW_DIR,
) -> list[dict]:
    """Export category classification training pairs.

    Reads evidence bundles for correct categories.
    Also includes correction records (wrong→correct pairs) from category_fix logs.
    """
    dataset = []

    # From evidence bundles: (assembled_title, brand, pn) → correct_category
    if evidence_dir.exists():
        for f in sorted(evidence_dir.glob("evidence_*.json")):
            try:
                bundle = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            pn = bundle.get("pn", "")
            brand = bundle.get("brand", "")
            title = bundle.get("assembled_title", "") or bundle.get("name", "")
            expected_cat = bundle.get("expected_category", "")
            card_status = bundle.get("card_status", "")
            page_class = bundle.get("price", {}).get("page_product_class", "")

            if not expected_cat:
                continue
            dataset.append({
                "dataset": "category_classification",
                "pn": pn,
                "brand": brand,
                "assembled_title": title,
                "page_product_class": page_class,
                "correct_category": expected_cat,
                "card_status": card_status,
                "correction": False,
            })

    # From category fix corrections
    cat_fix = _read_all_jsonl_in_dir(shadow_dir, "category_fix_*.jsonl")
    for r in cat_fix:
        pn = r.get("pn", "")
        if not pn:
            continue
        original = r.get("original_category", "") or r.get("old_expected_category", "")
        corrected = r.get("corrected_category", "") or r.get("new_expected_category", "")
        if original and corrected and original != corrected:
            dataset.append({
                "dataset": "category_classification",
                "pn": pn,
                "brand": r.get("brand", ""),
                "assembled_title": r.get("assembled_title", ""),
                "page_product_class": "",
                "correct_category": corrected,
                "original_category": original,
                "card_status": "",
                "correction": True,
            })

    return dataset


def export_search_strategy_dataset(shadow_dir: Path = _DEFAULT_SHADOW_DIR) -> list[dict]:
    """Export search strategy training examples from brand experience records.

    Each record: {pn, brand, pn_family, sources_worked, sources_failed, card_status, training_label}
    Reads from experience_*.jsonl files where task_type=brand_enrichment.
    """
    all_records = _read_all_jsonl_in_dir(shadow_dir, "experience_*.jsonl")
    dataset = []
    for r in all_records:
        if r.get("task_type") != "brand_enrichment":
            continue
        sources_worked = r.get("sources_worked", [])
        sources_failed = r.get("sources_failed", [])
        if not sources_worked and not sources_failed:
            continue  # Skip records with no search data
        dataset.append({
            "dataset": "search_strategy",
            "pn": r.get("pn", ""),
            "brand": r.get("brand", ""),
            "pn_family": r.get("pn_family"),
            "sources_worked": sources_worked,
            "sources_failed": sources_failed,
            "price_found": r.get("price_found", False),
            "price_currency": r.get("price_currency"),
            "photo_quality": r.get("photo_quality"),
            "specs_count": r.get("specs_count", 0),
            "card_status": r.get("decision", ""),
            "training_label": r.get("training_label", ""),
            "salience_score": r.get("salience_score", 5),
            "ts": r.get("ts", ""),
        })
    return dataset


def export_jsonl_dataset(
    jsonl_path: Path,
    dataset_name: str,
) -> list[dict]:
    """Export a training_data JSONL file as a list of records."""
    records = []
    if not jsonl_path.exists():
        return records
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass
    return records


def export_all_datasets(
    output_dir: Path = _DEFAULT_OUTPUT_DIR,
    shadow_dir: Path = _DEFAULT_SHADOW_DIR,
    evidence_dir: Path = _DEFAULT_EVIDENCE_DIR,
) -> dict[str, int]:
    """Export all 6 datasets to output_dir. Returns {dataset_name: count}."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Core 5 datasets (from shadow_log)
    datasets = {
        "price_extraction": export_price_extraction_dataset(shadow_dir),
        "photo_verdict": export_photo_verdict_dataset(shadow_dir),
        "spec_extraction": export_spec_extraction_dataset(shadow_dir),
        "category_classification": export_category_classification_dataset(evidence_dir, shadow_dir),
        "search_strategy": export_search_strategy_dataset(shadow_dir),
    }

    # Phase 4.1: 2 additional datasets (from training_data JSONL)
    datasets["page_ranking"] = export_jsonl_dataset(output_dir / "page_ranking_examples.jsonl", "page_ranking")
    datasets["unit_judge"] = export_jsonl_dataset(output_dir / "unit_judge_examples.jsonl", "unit_judge")

    stats: dict[str, int] = {}
    for name, records in datasets.items():
        out_path = output_dir / f"{name}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        stats[name] = len(records)

    # Write summary
    summary = {
        "exported_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "datasets": stats,
        "total": sum(stats.values()),
    }
    with open(output_dir / "export_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export enrichment training datasets")
    parser.add_argument("--shadow-dir", default=str(_DEFAULT_SHADOW_DIR))
    parser.add_argument("--evidence-dir", default=str(_DEFAULT_EVIDENCE_DIR))
    parser.add_argument("--output-dir", default=str(_DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    stats = export_all_datasets(
        output_dir=Path(args.output_dir),
        shadow_dir=Path(args.shadow_dir),
        evidence_dir=Path(args.evidence_dir),
    )

    MIN_NEEDED = {
        "price_extraction": 200, "photo_verdict": 50,
        "spec_extraction": 100,
        "category_classification": 100, "search_strategy": 50,
        "page_ranking": 100, "unit_judge": 50,
    }
    print("\n=== Training Dataset Export (7-point) ===")
    for name, count in stats.items():
        needed = MIN_NEEDED.get(name, 50)
        status = "ready" if count >= needed else f"need {needed - count} more"
        print(f"  {name:35s}: {count:4d} examples  [{status}]")
    print(f"  {'TOTAL':35s}: {sum(stats.values()):4d}")
    print(f"\nOutput: {args.output_dir}/")

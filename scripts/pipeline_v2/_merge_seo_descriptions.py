"""Merge descriptions_seo.json back into evidence files.

Problem: descriptions generated via Gemini/Haiku SEO pipeline live in a
separate JSON file and never flow into evidence. Downstream tools
(canonical builder, InSales transformer) only see the short
`normalized.best_description` (~46 words) instead of the 300+ word SEO
version. Result: InSales CSV ships with stub descriptions.

Fix: one-shot merger. For every PN with SEO description >=150 words in
descriptions_seo.json, write it into evidence as:
  - `from_datasheet.description_seo_ru` (new field, provenance tagged)
  - `normalized.best_description_ru` (replace if SEO is longer/better)

Keeps the original short description available under
`normalized.best_description_ru_short` for audit.
"""
from __future__ import annotations

import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
SEO_FILE = ROOT / "downloads" / "staging" / "pipeline_v2_output" / "descriptions_seo.json"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Mutate evidence files (default: dry-run)")
    parser.add_argument("--min-words", type=int, default=150)
    args = parser.parse_args()

    seo = json.loads(SEO_FILE.read_text(encoding="utf-8"))
    merged = 0
    skipped_short = 0
    skipped_missing = 0

    for pn, sd in seo.items():
        if not isinstance(sd, dict):
            continue
        word_count = sd.get("word_count", 0)
        desc = sd.get("description_seo_ru", "")
        if word_count < args.min_words or not desc:
            skipped_short += 1
            continue

        ev_file = EV_DIR / f"evidence_{pn}.json"
        if not ev_file.exists():
            ev_file = EV_DIR / f"evidence_{pn.replace('_', '/')}.json"
        if not ev_file.exists():
            skipped_missing += 1
            continue

        d = json.loads(ev_file.read_text(encoding="utf-8"))
        fd = d.get("from_datasheet") or {}
        norm = d.get("normalized") or {}

        # Preserve original short description
        old_desc = norm.get("best_description_ru") or norm.get("best_description") or ""
        if old_desc and "best_description_ru_short" not in norm:
            norm["best_description_ru_short"] = old_desc

        # Promote SEO description to best
        norm["best_description_ru"] = desc
        norm["best_description_ru_word_count"] = word_count
        norm["best_description_ru_source"] = "seo_merger_" + (sd.get("model", "unknown"))

        # Also store in from_datasheet for provenance
        fd["description_seo_ru"] = desc
        fd["description_seo_word_count"] = word_count
        fd["description_seo_model"] = sd.get("model", "")

        d["from_datasheet"] = fd
        d["normalized"] = norm

        if args.apply:
            ev_file.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        merged += 1

    mode = "APPLIED" if args.apply else "DRY-RUN (use --apply)"
    print(f"{mode}: merged {merged} descriptions")
    print(f"  skipped (too short): {skipped_short}")
    print(f"  skipped (no evidence file): {skipped_missing}")


if __name__ == "__main__":
    main()

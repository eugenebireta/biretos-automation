"""Promote training pairs to golden regression set.

One-shot script: takes existing training pairs in
downloads/knowledge/training_data/specs_extraction/*__gemini_flash.json
and writes them to golden/specs_extraction/ with:
  - pdf_sha256 hash of source PDF (cache key)
  - expected extraction output
  - model_id + prompt_version + extracted_at metadata

Rationale per 4th reviewer (2026-04-18):
LLM deprecations cause ~3-5% silent regression per major version bump
(arXiv 2311.11123, 2409.03928). Without a frozen golden set, model
upgrades will quietly degrade extraction quality until discovered via
marketplace rejection ("SKU sells badly on Ozon" 3 months later).

Cache key: (pdf_sha256, prompt_version, model_id, schema_version).
Re-extraction is free if all four match; model bumps invalidate just
the model_id dimension.
"""
from __future__ import annotations

import hashlib
import json
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent
TRAIN_DIR = ROOT / "downloads" / "knowledge" / "training_data" / "specs_extraction"
PDF_DIR = ROOT / "downloads" / "datasheets_v2"
GOLDEN_DIR = ROOT / "golden" / "specs_extraction"

SCHEMA_VERSION = "1.0"


def pdf_sha256(pdf_path: Path) -> str:
    h = hashlib.sha256()
    h.update(pdf_path.read_bytes())
    return h.hexdigest()


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def main():
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    pairs = sorted(TRAIN_DIR.glob("*__gemini_flash.json"))
    print(f"Found {len(pairs)} Gemini Flash training pairs")

    promoted = 0
    skipped_no_pdf = 0
    manifest_entries = []

    for pair_file in pairs:
        d = json.loads(pair_file.read_text(encoding="utf-8"))
        pn = d.get("pn", "")
        model = d.get("model", "")
        prompt = d.get("prompt", "")
        output = d.get("output", {})

        pdf_path = PDF_DIR / f"{pn}.pdf"
        if not pdf_path.exists():
            skipped_no_pdf += 1
            continue

        pdf_hash = pdf_sha256(pdf_path)
        p_hash = prompt_sha256(prompt)

        golden_entry = {
            "pn": pn,
            "pdf_sha256": pdf_hash,
            "pdf_bytes": pdf_path.stat().st_size,
            "model_id": model,
            "prompt_sha256_16": p_hash,
            "schema_version": SCHEMA_VERSION,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "expected_output": output,
        }

        out_file = GOLDEN_DIR / f"{pn}.json"
        out_file.write_text(json.dumps(golden_entry, indent=2, ensure_ascii=False), encoding="utf-8")
        promoted += 1

        # Summary for manifest
        specs = output.get("specs") or {}
        manifest_entries.append({
            "pn": pn,
            "pdf_sha256": pdf_hash,
            "model_id": model,
            "prompt_sha256_16": p_hash,
            "expected_specs_count": len(specs) if isinstance(specs, dict) else 0,
            "expected_weight_g": output.get("weight_g", ""),
            "expected_dims_mm": output.get("dimensions_mm", ""),
            "expected_ean": output.get("ean", ""),
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "total_entries": promoted,
        "source": "downloads/knowledge/training_data/specs_extraction/*__gemini_flash.json",
        "cache_key_fields": ["pdf_sha256", "prompt_sha256_16", "model_id", "schema_version"],
        "entries": manifest_entries,
    }
    (GOLDEN_DIR.parent / "specs_extraction_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nPromoted {promoted} entries to {GOLDEN_DIR}")
    print(f"Skipped (no PDF): {skipped_no_pdf}")
    print(f"Manifest: {GOLDEN_DIR.parent / 'specs_extraction_manifest.json'}")


if __name__ == "__main__":
    main()

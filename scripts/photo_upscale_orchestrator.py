"""photo_upscale_orchestrator.py — Upscale needs_upscale photos via realesrgan-ncnn-vulkan.

Pipeline:
  1. Fail-fast: verify binary + model files exist
  2. Load needs_upscale.json subset
  3. Upscale each raw photo 4x via realesrgan-ncnn-vulkan + realesrnet-x4plus
  4. Enhance upscaled output via photo_enhance_local.py (1400x1400 canvas)
  5. Validate: dimensions grew, enhanced asset exists
  6. Update triage state: promote success to good_quality, keep fails in needs_upscale

Usage:
    python scripts/photo_upscale_orchestrator.py [--limit N] [--gpu 0,1] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
TRIAGE_DIR = DOWNLOADS / "photo_triage"
RAW_PHOTOS_DIR = DOWNLOADS / "photos"
UPSCALED_DIR = DOWNLOADS / "photos_upscaled"
ENHANCED_DIR = DOWNLOADS / "photos_enhanced"

NEEDS_UPSCALE_JSON = TRIAGE_DIR / "needs_upscale.json"
GOOD_QUALITY_JSON = TRIAGE_DIR / "good_quality.json"
UPSCALE_REPORT_JSON = TRIAGE_DIR / "upscale_report.json"

# Engine paths
TOOLS_DIR = ROOT / "tools" / "realesrgan-ncnn-vulkan"
ENGINE_EXE = TOOLS_DIR / "realesrgan-ncnn-vulkan.exe"
MODEL_DIR = TOOLS_DIR / "models"
MODEL_NAME = "realesrnet-x4plus"

# Model files that must exist (realesrnet-x4plus uses .param + .bin)
REQUIRED_MODEL_FILES = [
    MODEL_DIR / f"{MODEL_NAME}.param",
    MODEL_DIR / f"{MODEL_NAME}.bin",
]


# ── Engine detection ────────────────────────────────────────────────────────

def check_engine() -> tuple[bool, list[str]]:
    """Verify realesrgan-ncnn-vulkan binary and model files exist.

    Returns (ok, list_of_problems).
    """
    problems = []

    if not TOOLS_DIR.exists():
        problems.append(f"Directory not found: {TOOLS_DIR}")
    if not ENGINE_EXE.exists():
        problems.append(f"Binary not found: {ENGINE_EXE}")
    if not MODEL_DIR.exists():
        problems.append(f"Models directory not found: {MODEL_DIR}")

    for mf in REQUIRED_MODEL_FILES:
        if not mf.exists():
            problems.append(f"Model file not found: {mf}")

    return (len(problems) == 0, problems)


def fail_loud_engine_missing(problems: list[str]) -> None:
    """Print diagnostic and exit."""
    print("\n" + "=" * 70)
    print("FATAL: realesrgan-ncnn-vulkan engine NOT FOUND")
    print("=" * 70)
    print()
    for p in problems:
        print(f"  [MISSING] {p}")
    print()
    print("Expected layout:")
    print(f"  {TOOLS_DIR}\\")
    print("    realesrgan-ncnn-vulkan.exe")
    print("    models\\")
    print(f"      {MODEL_NAME}.param")
    print(f"      {MODEL_NAME}.bin")
    print()
    print("Installation:")
    print("  1. Download from: https://github.com/xinntao/Real-ESRGAN/releases")
    print("     File: realesrgan-ncnn-vulkan-*-windows.zip")
    print(f"  2. Extract into: {TOOLS_DIR}")
    print("  3. Verify:")
    print(f"     {ENGINE_EXE} -h")
    print()
    print("Cannot proceed without engine. Exiting.")
    print("=" * 70)
    sys.exit(1)


# ── Upscale command ─────────────────────────────────────────────────────────

def build_upscale_command(
    input_path: Path,
    output_path: Path,
    gpu_id: int = 0,
) -> list[str]:
    """Build subprocess command for realesrgan-ncnn-vulkan.

    CLI reference (from realesrgan-ncnn-vulkan -h):
      -i input_path
      -o output_path
      -s scale (4)
      -n model_name
      -g gpu_id
      -f output_format (jpg/png/webp)
    """
    return [
        str(ENGINE_EXE),
        "-i", str(input_path),
        "-o", str(output_path),
        "-s", "4",
        "-n", MODEL_NAME,
        "-g", str(gpu_id),
        "-f", "png",  # lossless intermediate; enhance converts to JPEG
    ]


def run_upscale(
    input_path: Path,
    output_path: Path,
    gpu_id: int = 0,
    timeout_sec: int = 120,
) -> tuple[bool, str]:
    """Run upscale subprocess. Returns (success, error_message)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_upscale_command(input_path, output_path, gpu_id)
    log.info(f"[GPU {gpu_id}] Upscaling: {input_path.name} → {output_path.name}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=str(TOOLS_DIR),
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            return False, f"upscale_error: {err[:300]}"
        if not output_path.exists():
            return False, "upscale_output_missing"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, f"upscale_timeout_{timeout_sec}s"
    except Exception as e:
        return False, f"upscale_exception: {str(e)[:200]}"


# ── Enhance integration ─────────────────────────────────────────────────────

# Import enhance function from existing script
_scripts_dir = str(Path(__file__).parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from photo_enhance_local import (
    enhance_to_placeholder,
    output_path_for_record,
    compute_sha1,
    get_size,
)


def run_enhance(
    upscaled_path: Path,
    part_number: str,
    profile: str = "catalog_placeholder_v1",
) -> tuple[bool, str, Path | None]:
    """Run enhance on upscaled image. Returns (success, error, output_path)."""
    try:
        sha1 = compute_sha1(upscaled_path)
        dest = output_path_for_record(part_number, profile, sha1)
        enhance_to_placeholder(
            upscaled_path,
            dest,
            canvas_px=1400,
            content_ratio=0.84,
            background_hex="#F4F1EB",
        )
        if not dest.exists():
            return False, "enhance_output_missing", None
        return True, "", dest
    except Exception as e:
        return False, f"enhance_exception: {str(e)[:200]}", None


# ── Validation ──────────────────────────────────────────────────────────────

def validate_upscale(
    raw_path: Path,
    upscaled_path: Path,
    raw_min_dim: int,
) -> tuple[bool, str]:
    """Check upscale output is valid and dimensions grew."""
    if not upscaled_path.exists():
        return False, "upscale_output_missing"
    try:
        w, h = get_size(upscaled_path)
    except Exception as e:
        return False, f"upscale_unreadable: {str(e)[:100]}"
    if w == 0 or h == 0:
        return False, "upscale_zero_dimensions"
    new_min = min(w, h)
    if new_min <= raw_min_dim:
        return False, f"upscale_no_growth: {raw_min_dim}→{new_min}"
    return True, ""


# ── Single SKU pipeline ─────────────────────────────────────────────────────

def process_one_sku(
    sku: dict,
    gpu_id: int,
    dry_run: bool = False,
) -> dict:
    """Full pipeline for one SKU: upscale → validate → enhance → validate.

    Returns result dict with outcome field.
    """
    pn = sku["part_number"]
    raw_path = Path(sku["raw_photo_path"])
    raw_min_dim = sku.get("min_dimension", 0)

    result = {
        "part_number": pn,
        "gpu_id": gpu_id,
        "raw_path": str(raw_path),
        "raw_min_dim": raw_min_dim,
        "upscaled_path": "",
        "upscaled_width": 0,
        "upscaled_height": 0,
        "enhanced_path": "",
        "enhanced_width": 0,
        "enhanced_height": 0,
        "outcome": "",
        "error": "",
    }

    # Dry-run: report what would happen, don't run binary
    if dry_run:
        upscaled = UPSCALED_DIR / f"{pn}_x4.png"
        cmd = build_upscale_command(raw_path, upscaled, gpu_id)
        result["outcome"] = "dry_run_skipped"
        result["upscaled_path"] = str(upscaled)
        result["error"] = f"DRY RUN — would execute: {' '.join(cmd)}"
        return result

    # Check source exists
    if not raw_path.exists():
        result["outcome"] = "source_missing"
        result["error"] = f"Raw file not found: {raw_path}"
        return result

    # Upscale
    upscaled = UPSCALED_DIR / f"{pn}_x4.png"
    ok, err = run_upscale(raw_path, upscaled, gpu_id)
    if not ok:
        result["outcome"] = "upscale_failed"
        result["error"] = err
        return result

    result["upscaled_path"] = str(upscaled)

    # Validate upscale
    ok, err = validate_upscale(raw_path, upscaled, raw_min_dim)
    if not ok:
        result["outcome"] = "upscale_failed"
        result["error"] = err
        return result

    uw, uh = get_size(upscaled)
    result["upscaled_width"] = uw
    result["upscaled_height"] = uh

    # Enhance
    ok, err, enhanced_path = run_enhance(upscaled, pn)
    if not ok:
        result["outcome"] = "enhance_failed"
        result["error"] = err
        return result

    result["enhanced_path"] = str(enhanced_path)
    ew, eh = get_size(enhanced_path)
    result["enhanced_width"] = ew
    result["enhanced_height"] = eh

    result["outcome"] = "upscale_success_promoted"
    return result


# ── Parallel execution ──────────────────────────────────────────────────────

def run_batch(
    skus: list[dict],
    gpu_ids: list[int],
    dry_run: bool = False,
) -> list[dict]:
    """Run upscale batch across GPUs using ThreadPoolExecutor.

    Round-robin assignment: SKU[0] → GPU[0], SKU[1] → GPU[1], SKU[2] → GPU[0], ...
    Each GPU gets its own thread — realesrgan-ncnn-vulkan is single-GPU per process.
    """
    num_gpus = len(gpu_ids)
    results: list[dict] = [None] * len(skus)  # type: ignore

    # Assign GPUs round-robin
    assignments = [(i, skus[i], gpu_ids[i % num_gpus]) for i in range(len(skus))]

    with ThreadPoolExecutor(max_workers=num_gpus) as pool:
        futures = {}
        for idx, sku, gpu_id in assignments:
            future = pool.submit(process_one_sku, sku, gpu_id, dry_run)
            futures[future] = idx

        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                pn = skus[idx]["part_number"]
                results[idx] = {
                    "part_number": pn,
                    "gpu_id": gpu_ids[idx % num_gpus],
                    "outcome": "upscale_failed",
                    "error": f"thread_exception: {str(e)[:200]}",
                }
                log.error(f"Thread error for {pn}: {e}")

    return results


# ── State update ────────────────────────────────────────────────────────────

def update_triage_state(results: list[dict]) -> dict:
    """Move successful SKUs from needs_upscale to good_quality.

    Returns stats dict.
    """
    # Load current state
    needs = []
    if NEEDS_UPSCALE_JSON.exists():
        needs = json.loads(NEEDS_UPSCALE_JSON.read_text(encoding="utf-8"))
    good = []
    if GOOD_QUALITY_JSON.exists():
        good = json.loads(GOOD_QUALITY_JSON.read_text(encoding="utf-8"))

    success_pns = {r["part_number"] for r in results if r["outcome"] == "upscale_success_promoted"}
    success_map = {r["part_number"]: r for r in results if r["outcome"] == "upscale_success_promoted"}

    # Remove promoted SKUs from needs_upscale
    remaining_needs = [s for s in needs if s["part_number"] not in success_pns]

    # Add promoted SKUs to good_quality
    for pn in sorted(success_pns):
        r = success_map[pn]
        # Find original entry for raw dimensions
        orig = next((s for s in needs if s["part_number"] == pn), {})
        good.append({
            "part_number": pn,
            "raw_photo_path": orig.get("raw_photo_path", r.get("raw_path", "")),
            "raw_width": orig.get("raw_width", 0),
            "raw_height": orig.get("raw_height", 0),
            "min_dimension": max(r.get("upscaled_width", 0), r.get("upscaled_height", 0)),
            "bucket": "good_quality",
            "enhanced_photo_path": r.get("enhanced_path", ""),
            "enhanced_generated": True,
            "photo_ready_for_future_cloud": True,
            "next_action": "keep_enhanced",
            "upscale_source": "realesrgan_x4",
        })

    # Write updated state
    NEEDS_UPSCALE_JSON.write_text(
        json.dumps(remaining_needs, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    GOOD_QUALITY_JSON.write_text(
        json.dumps(good, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return {
        "promoted": len(success_pns),
        "remaining_needs_upscale": len(remaining_needs),
        "total_good_quality": len(good),
    }


# ── Manifest rebuild ────────────────────────────────────────────────────────

def rebuild_photo_manifest() -> int:
    """Rebuild unified photo_manifest.csv from triage JSONs.

    Returns number of rows written.
    """
    import csv

    manifest_path = TRIAGE_DIR / "photo_manifest.csv"
    fieldnames = [
        "part_number", "raw_photo_path", "raw_width", "raw_height",
        "min_dimension", "bucket", "enhanced_photo_path", "enhanced_generated",
        "photo_ready_for_future_cloud", "next_action",
    ]

    all_rows = []
    for json_file in ["tiny_quarantine.json", "needs_upscale.json", "good_quality.json"]:
        path = TRIAGE_DIR / json_file
        if not path.exists():
            continue
        entries = json.loads(path.read_text(encoding="utf-8"))
        for entry in entries:
            all_rows.append({k: entry.get(k, "") for k in fieldnames})

    all_rows.sort(key=lambda r: r["part_number"])

    with open(manifest_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    log.info(f"Photo manifest rebuilt: {len(all_rows)} rows → {manifest_path}")
    return len(all_rows)


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upscale needs_upscale photos via realesrgan-ncnn-vulkan + enhance"
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit SKUs to process (0=all)")
    parser.add_argument("--gpu", type=str, default="0,1",
                        help="Comma-separated GPU IDs (default: 0,1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show commands without running engine")
    parser.add_argument("--rebuild-manifest", action="store_true",
                        help="Only rebuild photo_manifest.csv from existing triage JSONs")
    args = parser.parse_args()

    # Manifest rebuild only
    if args.rebuild_manifest:
        count = rebuild_photo_manifest()
        print(f"Manifest rebuilt: {count} rows")
        return

    # ── FAIL-FAST: engine check ──
    ok, problems = check_engine()
    if not ok and not args.dry_run:
        fail_loud_engine_missing(problems)

    if not ok and args.dry_run:
        log.warning("Engine not found — running in dry-run mode, will show commands only")
        for p in problems:
            log.warning(f"  [MISSING] {p}")

    # ── Load subset ──
    if not NEEDS_UPSCALE_JSON.exists():
        log.error(f"Subset file not found: {NEEDS_UPSCALE_JSON}")
        sys.exit(1)

    skus = json.loads(NEEDS_UPSCALE_JSON.read_text(encoding="utf-8"))
    log.info(f"needs_upscale SKUs: {len(skus)}")

    if args.limit:
        skus = skus[:args.limit]
        log.info(f"Limited to: {len(skus)} SKUs")

    if not skus:
        log.info("Nothing to upscale")
        return

    # Parse GPU IDs
    gpu_ids = [int(g.strip()) for g in args.gpu.split(",") if g.strip()]
    if not gpu_ids:
        gpu_ids = [0]
    log.info(f"GPUs: {gpu_ids} ({len(gpu_ids)} parallel workers)")

    # Create output dir
    UPSCALED_DIR.mkdir(parents=True, exist_ok=True)

    # ── Run batch ──
    t0 = time.time()
    results = run_batch(skus, gpu_ids, dry_run=args.dry_run)
    elapsed = time.time() - t0

    # ── Write report ──
    TRIAGE_DIR.mkdir(parents=True, exist_ok=True)
    UPSCALE_REPORT_JSON.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ── Stats ──
    by_outcome: dict[str, int] = {}
    for r in results:
        o = r.get("outcome", "unknown")
        by_outcome[o] = by_outcome.get(o, 0) + 1

    print("\n=== UPSCALE BATCH RESULTS ===")
    print(f"  Total SKUs:    {len(results)}")
    print(f"  Elapsed:       {elapsed:.1f}s")
    for outcome, count in sorted(by_outcome.items()):
        print(f"  {outcome}: {count}")

    # ── State update (only if real run with successes) ──
    promoted = by_outcome.get("upscale_success_promoted", 0)
    if promoted > 0 and not args.dry_run:
        state_stats = update_triage_state(results)
        print("\n  State update:")
        print(f"    Promoted to good_quality: {state_stats['promoted']}")
        print(f"    Remaining needs_upscale:  {state_stats['remaining_needs_upscale']}")
        print(f"    Total good_quality:       {state_stats['total_good_quality']}")

        # Rebuild photo manifest
        manifest_rows = rebuild_photo_manifest()
        print(f"    Photo manifest rebuilt:   {manifest_rows} rows")

    elif args.dry_run:
        print("\n  DRY RUN — no state changes made")

    # Print errors
    errors = [r for r in results if r.get("outcome") not in ("upscale_success_promoted", "dry_run_skipped")]
    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for r in errors[:20]:
            print(f"    {r['part_number']}: {r['outcome']} — {r.get('error','')[:100]}")

    print(f"\n  Report: {UPSCALE_REPORT_JSON}")
    print(f"  Output: {OUTPUT_EXPORT if promoted else 'no changes'}")


OUTPUT_EXPORT = ENHANCED_DIR  # alias for final print


if __name__ == "__main__":
    main()

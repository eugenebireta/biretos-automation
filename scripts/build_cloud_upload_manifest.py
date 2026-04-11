"""build_cloud_upload_manifest.py — Build upload manifest for photo-ready enhanced assets.

Reads photo_manifest.csv + rescue delta to find photo-ready SKUs,
then uploads (or dry-runs) via S3Uploader and writes upload manifest.

Usage:
    python scripts/build_cloud_upload_manifest.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
TRIAGE_DIR = DOWNLOADS / "photo_triage"
EVIDENCE_DIR = DOWNLOADS / "evidence"
ENHANCED_DIR = DOWNLOADS / "photos_enhanced"
ENV_FILE = DOWNLOADS / ".env"

MANIFEST_CSV = TRIAGE_DIR / "photo_manifest.csv"
DELTA_CSV = TRIAGE_DIR / "rescue_tiny_delta.csv"
UPLOAD_MANIFEST = TRIAGE_DIR / "cloud_upload_manifest.csv"

_scripts = str(Path(__file__).parent)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)


def safe_key(value: str) -> str:
    """Sanitize PN for use as S3 object key component."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()) or "unnamed"


def load_ready_subset() -> list[dict]:
    """Load photo-ready SKUs from manifest + rescue delta."""
    base = {}
    if MANIFEST_CSV.exists():
        with open(MANIFEST_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                base[row["part_number"]] = row

    # Apply rescue delta
    if DELTA_CSV.exists():
        with open(DELTA_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                pn = row["part_number"]
                if pn in base:
                    base[pn].update(row)

    ready = []
    for pn, row in sorted(base.items()):
        is_ready = row.get("photo_ready_for_future_cloud", "").lower() in ("true", "1")
        enh_path = row.get("enhanced_photo_path", "")
        if is_ready and enh_path and Path(enh_path).exists():
            ready.append(row)

    return ready


def load_evidence_brand(pn: str) -> str:
    """Get brand from evidence file."""
    ev_path = EVIDENCE_DIR / f"evidence_{pn}.json"
    if ev_path.exists():
        try:
            ev = json.loads(ev_path.read_text(encoding="utf-8-sig"))
            return ev.get("brand", "Honeywell") or "Honeywell"
        except Exception:
            pass
    return "Honeywell"


def build_object_key(pn: str, brand: str) -> str:
    """Build deterministic S3 object key."""
    brand_key = safe_key(brand).lower()
    pn_key = safe_key(pn)
    return f"products/{brand_key}/{pn_key}.jpg"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build cloud upload manifest for photo-ready assets")
    parser.add_argument("--dry-run", action="store_true",
                        help="Force dry-run even if S3 credentials exist")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of SKUs to process (0=all)")
    args = parser.parse_args()

    # Load ready subset
    ready = load_ready_subset()
    if args.limit:
        ready = ready[:args.limit]
    log.info(f"Photo-ready subset: {len(ready)} SKUs")

    if not ready:
        log.error("No photo-ready assets found")
        return

    # Set up uploader
    if args.dry_run:
        os.environ["S3_DRY_RUN"] = "true"

    from cloud_uploader import S3Uploader
    uploader = S3Uploader.from_env(env_file=ENV_FILE)
    log.info(f"Upload mode: {uploader.mode}")

    # Build upload items
    results = []
    for row in ready:
        pn = row["part_number"]
        brand = load_evidence_brand(pn)
        enh_path = row["enhanced_photo_path"]
        obj_key = build_object_key(pn, brand)

        result = uploader.upload_file(enh_path, obj_key)
        results.append({
            "part_number": pn,
            "brand": brand,
            "local_path": result.local_path,
            "object_key": result.object_key,
            "upload_mode": result.upload_mode,
            "upload_status": "ok" if result.upload_mode in ("dry_run", "uploaded") else "error",
            "public_url": result.public_url,
            "size_kb": result.size_kb,
            "error": result.error,
        })

    # Write manifest
    UPLOAD_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "part_number", "brand", "local_path", "object_key",
        "upload_mode", "upload_status", "public_url", "size_kb", "error",
    ]
    with open(UPLOAD_MANIFEST, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Stats
    ok = sum(1 for r in results if r["upload_status"] == "ok")
    errors = sum(1 for r in results if r["upload_status"] == "error")
    dry = sum(1 for r in results if r["upload_mode"] == "dry_run")
    real = sum(1 for r in results if r["upload_mode"] == "uploaded")

    total_kb = sum(r["size_kb"] for r in results)
    total_mb = total_kb / 1024

    log.info(f"Manifest written: {UPLOAD_MANIFEST}")
    print("\n=== CLOUD UPLOAD MANIFEST ===")
    print(f"  Total: {len(results)} SKUs")
    print(f"  OK: {ok} | Errors: {errors}")
    print(f"  Dry-run: {dry} | Real uploads: {real}")
    print(f"  Total size: {total_mb:.1f} MB")
    print(f"  Output: {UPLOAD_MANIFEST}")


if __name__ == "__main__":
    main()

"""photo_quality_triage.py — Classify raw photos into quality buckets.

Reads raw photos from downloads/photos/, measures dimensions,
and classifies each SKU into:
  - tiny_quarantine: min(w,h) < 200
  - needs_upscale:   200 <= min(w,h) < 400
  - good_quality:    min(w,h) >= 400

Also checks whether an enhanced derivative exists.
Outputs three JSON files + a unified manifest CSV.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
RAW_PHOTOS_DIR = DOWNLOADS / "photos"
ENHANCED_PHOTOS_DIR = DOWNLOADS / "photos_enhanced"
OUTPUT_DIR = DOWNLOADS / "photo_triage"

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
EXT_PRIORITY = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]
SKIP_PNS = {"---", "-----", "PN", "_", ""}


def get_dimensions(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as img:
            return img.size  # (width, height)
    except Exception:
        return (0, 0)


def select_best_photo(paths: list[Path]) -> Path:
    if len(paths) == 1:
        return paths[0]
    return sorted(paths, key=lambda p: (
        EXT_PRIORITY.index(p.suffix.lower()) if p.suffix.lower() in EXT_PRIORITY else 99,
        p.name,
    ))[0]


def find_enhanced(pn: str) -> Path | None:
    """Find enhanced derivative for PN."""
    for p in ENHANCED_PHOTOS_DIR.glob(f"{pn}__*"):
        return p
    return None


def classify(min_dim: int) -> str:
    if min_dim < 200:
        return "tiny_quarantine"
    if min_dim < 400:
        return "needs_upscale"
    return "good_quality"


def next_action(bucket: str, enhanced_exists: bool) -> str:
    if bucket == "tiny_quarantine":
        return "re_search_required"
    if bucket == "needs_upscale":
        return "upscale_then_review"
    if enhanced_exists:
        return "keep_enhanced"
    return "manual_review"


def run_triage(dry_run: bool = False) -> dict:
    # Collect raw photos
    pn_to_photos: dict[str, list[Path]] = {}
    for p in RAW_PHOTOS_DIR.iterdir():
        if p.suffix.lower() not in PHOTO_EXTS:
            continue
        pn = p.stem
        if pn in SKIP_PNS:
            continue
        pn_to_photos.setdefault(pn, []).append(p)

    tiny: list[dict] = []
    needs_up: list[dict] = []
    good: list[dict] = []
    all_records: list[dict] = []

    for pn in sorted(pn_to_photos.keys()):
        selected = select_best_photo(pn_to_photos[pn])
        w, h = get_dimensions(selected)
        min_dim = min(w, h)
        bucket = classify(min_dim)
        enhanced = find_enhanced(pn)
        enhanced_exists = enhanced is not None
        action = next_action(bucket, enhanced_exists)

        record = {
            "part_number": pn,
            "raw_photo_path": str(selected),
            "raw_width": w,
            "raw_height": h,
            "min_dimension": min_dim,
            "bucket": bucket,
            "enhanced_photo_path": str(enhanced) if enhanced else "",
            "enhanced_generated": enhanced_exists,
            "photo_ready_for_future_cloud": bucket == "good_quality" and enhanced_exists,
            "next_action": action,
        }
        all_records.append(record)

        if bucket == "tiny_quarantine":
            tiny.append(record)
        elif bucket == "needs_upscale":
            needs_up.append(record)
        else:
            good.append(record)

    stats = {
        "total": len(all_records),
        "tiny_quarantine": len(tiny),
        "needs_upscale": len(needs_up),
        "good_quality": len(good),
        "photo_ready": sum(1 for r in all_records if r["photo_ready_for_future_cloud"]),
    }

    if not dry_run:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        for name, data in [("tiny_quarantine", tiny), ("needs_upscale", needs_up), ("good_quality", good)]:
            (OUTPUT_DIR / f"{name}.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        # Unified manifest CSV
        manifest_path = OUTPUT_DIR / "photo_manifest.csv"
        fieldnames = [
            "part_number", "raw_photo_path", "raw_width", "raw_height",
            "min_dimension", "bucket", "enhanced_photo_path", "enhanced_generated",
            "photo_ready_for_future_cloud", "next_action",
        ]
        with open(manifest_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_records)

    return stats


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Photo quality triage")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stats = run_triage(dry_run=args.dry_run)
    mode = "DRY RUN" if args.dry_run else "DONE"
    print(f"[{mode}] total={stats['total']} "
          f"tiny={stats['tiny_quarantine']} "
          f"needs_upscale={stats['needs_upscale']} "
          f"good={stats['good_quality']} "
          f"photo_ready={stats['photo_ready']}")


if __name__ == "__main__":
    main()

"""generate_enhance_seed.py — Create photo_enhance_seed.jsonl for all SKUs with raw photos.

Walks downloads/photos/ and downloads/evidence/ to build a seed file
compatible with photo_enhance_local.py.

Deterministic: sorted by part_number, .jpg preferred over .webp/.png.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
RAW_PHOTOS_DIR = DOWNLOADS / "photos"
EVIDENCE_DIR = DOWNLOADS / "evidence"
SCOUT_CACHE_DIR = DOWNLOADS / "scout_cache"
DEFAULT_SEED_FILE = SCOUT_CACHE_DIR / "photo_enhance_seed.jsonl"

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
# Priority: lower index = preferred
EXT_PRIORITY = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]

SKIP_PNS = {"---", "-----", "PN", "_", ""}


def select_best_photo(paths: list[Path]) -> Path:
    """Pick best photo when multiple exist for same PN. Prefer .jpg."""
    if len(paths) == 1:
        return paths[0]
    by_priority = sorted(paths, key=lambda p: (
        EXT_PRIORITY.index(p.suffix.lower()) if p.suffix.lower() in EXT_PRIORITY else 99,
        p.name,
    ))
    return by_priority[0]


def load_evidence(pn: str) -> dict:
    """Load evidence file for PN if it exists."""
    ev_path = EVIDENCE_DIR / f"evidence_{pn}.json"
    if not ev_path.exists():
        return {}
    try:
        return json.loads(ev_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def build_seed(output_path: Path | None = None, dry_run: bool = False) -> dict:
    """Build seed JSONL and return stats."""
    output_path = output_path or DEFAULT_SEED_FILE

    # Collect all raw photos
    pn_to_photos: dict[str, list[Path]] = {}
    for p in RAW_PHOTOS_DIR.iterdir():
        if p.suffix.lower() not in PHOTO_EXTS:
            continue
        pn = p.stem
        if pn in SKIP_PNS:
            continue
        pn_to_photos.setdefault(pn, []).append(p)

    records = []
    ambiguous = []

    for pn in sorted(pn_to_photos.keys()):
        paths = pn_to_photos[pn]
        selected = select_best_photo(paths)

        if len(paths) > 1:
            ambiguous.append({
                "part_number": pn,
                "all_files": [p.name for p in paths],
                "selected": selected.name,
                "reason": "preferred_ext_priority",
            })

        ev = load_evidence(pn)
        brand = ev.get("brand", "")
        title = ev.get("assembled_title", "")

        record = {
            "part_number": pn,
            "brand": brand,
            "product_name": title,
            "source_local_path": str(selected.resolve()),
            "source_photo_status": "placeholder",
            "source_storage_role": "canonical_raw_photo",
            "source_provider": "local_raw",
            "enhancement_profile": "catalog_placeholder_v1",
            "background_hex": "#F4F1EB",
            "canvas_px": 1400,
            "content_ratio": 0.84,
            "notes": "",
        }
        records.append(record)

    stats = {
        "total_photo_files": sum(len(v) for v in pn_to_photos.values()),
        "unique_pns": len(pn_to_photos),
        "seed_records": len(records),
        "ambiguous_pns": len(ambiguous),
    }

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

        if ambiguous:
            amb_path = output_path.parent / "photo_enhance_ambiguous.json"
            amb_path.write_text(
                json.dumps(ambiguous, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    return stats


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Generate photo_enhance_seed.jsonl")
    parser.add_argument("--output", default=str(DEFAULT_SEED_FILE))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stats = build_seed(Path(args.output), dry_run=args.dry_run)
    mode = "DRY RUN" if args.dry_run else "WRITTEN"
    print(f"[{mode}] seed_records={stats['seed_records']} "
          f"unique_pns={stats['unique_pns']} "
          f"photo_files={stats['total_photo_files']} "
          f"ambiguous={stats['ambiguous_pns']}")


if __name__ == "__main__":
    main()

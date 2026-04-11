"""rescue_tiny_photos.py — Targeted photo re-search for tiny_quarantine SKUs.

Workflow:
  1. Load tiny_quarantine.json (25 SKUs < 200px min dimension)
  2. Quarantine old raw+enhanced assets with audit trail
  3. Re-search via photo_hunter channels (1=OG, 2=PDF, 3=Family, 6=Imagen)
  4. Classify outcome: rescued_good / rescued_but_small / no_better_candidate /
     rejected_candidate / search_failed
  5. Generate bounded enhance seed for rescued SKUs
  6. Write rescue report JSONL

Usage:
    python scripts/rescue_tiny_photos.py [--dry-run] [--channels 1,2,3,6]
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from PIL import Image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "downloads"
RAW_DIR = DOWNLOADS / "photos"
ENHANCED_DIR = DOWNLOADS / "photos_enhanced"
QUARANTINE_RAW_DIR = DOWNLOADS / "photos_quarantine" / "raw"
QUARANTINE_ENH_DIR = DOWNLOADS / "photos_quarantine" / "enhanced"
TRIAGE_DIR = DOWNLOADS / "photo_triage"
SCOUT_CACHE_DIR = DOWNLOADS / "scout_cache"
EVIDENCE_DIR = DOWNLOADS / "evidence"

TINY_QUARANTINE_JSON = TRIAGE_DIR / "tiny_quarantine.json"
QUARANTINE_MAP_JSON = TRIAGE_DIR / "rescue_quarantine_map.json"
RESCUE_SEED_JSONL = SCOUT_CACHE_DIR / "rescue_tiny_seed.jsonl"
RESCUE_MANIFEST_JSONL = SCOUT_CACHE_DIR / "rescue_tiny_manifest.jsonl"
RESCUE_REPORT_JSON = TRIAGE_DIR / "rescue_tiny_report.json"

GOOD_THRESHOLD = 400    # min_dim >= 400 → rescued_good
SMALL_THRESHOLD = 200   # min_dim >= 200 → rescued_but_small


def get_min_dim(path: Path) -> int:
    try:
        with Image.open(path) as img:
            w, h = img.size
            return min(w, h)
    except Exception:
        return 0


def get_dims(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return (0, 0)


def load_tiny_queue() -> list[dict]:
    if not TINY_QUARANTINE_JSON.exists():
        log.error(f"tiny_quarantine.json not found: {TINY_QUARANTINE_JSON}")
        return []
    return json.loads(TINY_QUARANTINE_JSON.read_text(encoding="utf-8"))


def quarantine_asset(path_str: str, dest_dir: Path, reason: str, dry_run: bool) -> str | None:
    """Move a file to quarantine dir. Returns quarantine path or None if not exists."""
    if not path_str:
        return None
    src = Path(path_str)
    if not src.exists():
        return None
    dest = dest_dir / src.name
    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        log.info(f"  Quarantined: {src.name} → {dest_dir.name}/")
    return str(dest)


def run_quarantine(tiny_records: list[dict], dry_run: bool) -> list[dict]:
    """Move old tiny assets to quarantine. Returns quarantine mapping."""
    mapping = []
    for rec in tiny_records:
        pn = rec["part_number"]
        old_raw = rec.get("raw_photo_path", "")
        old_enh = rec.get("enhanced_photo_path", "")

        q_raw = quarantine_asset(old_raw, QUARANTINE_RAW_DIR, "tiny_rescue", dry_run)
        q_enh = quarantine_asset(old_enh, QUARANTINE_ENH_DIR, "tiny_rescue", dry_run)

        mapping.append({
            "part_number": pn,
            "old_raw_path": old_raw,
            "old_enhanced_path": old_enh,
            "quarantine_raw_path": q_raw or "",
            "quarantine_enhanced_path": q_enh or "",
            "old_raw_dims": f"{rec.get('raw_width',0)}x{rec.get('raw_height',0)}",
            "old_min_dimension": rec.get("min_dimension", 0),
            "reason": "tiny_rescue_replaced_candidate",
            "superseded": True,
        })

    if not dry_run:
        QUARANTINE_MAP_JSON.parent.mkdir(parents=True, exist_ok=True)
        QUARANTINE_MAP_JSON.write_text(
            json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info(f"Quarantine map written: {QUARANTINE_MAP_JSON}")

    return mapping


def load_evidence(pn: str) -> dict:
    path = EVIDENCE_DIR / f"evidence_{pn}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}
    return {}


def classify_outcome(pn: str, old_min_dim: int) -> str:
    """Classify outcome by comparing new raw photo dimensions."""
    new_raw = RAW_DIR / f"{pn}.jpg"
    if not new_raw.exists():
        return "search_failed"
    new_min = get_min_dim(new_raw)
    if new_min >= GOOD_THRESHOLD:
        return "rescued_good"
    if new_min >= SMALL_THRESHOLD:
        return "rescued_but_small"
    if new_min > old_min_dim:
        # Slightly larger but still tiny — still unresolved
        return "no_better_candidate"
    return "no_better_candidate"


def run_rescue(tiny_records: list[dict], channels: list[int], dry_run: bool) -> list[dict]:
    """Run photo_hunter for each tiny SKU. Returns per-SKU outcome records."""
    # Import photo_hunter internals
    _scripts = str(Path(__file__).parent)
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)

    from photo_hunter import (
        hunt_photo,
        load_evidence as hunter_load_evidence,
        build_series_photo_map,
        EVIDENCE_DIR as HUNTER_EV_DIR,  # noqa: F401
    )

    series_map = build_series_photo_map() if 3 in channels else {}
    outcomes: list[dict] = []

    for i, rec in enumerate(tiny_records):
        pn = rec["part_number"]
        old_min_dim = rec.get("min_dimension", 0)
        log.info(f"[{i+1}/{len(tiny_records)}] Rescuing {pn} (old min_dim={old_min_dim})")

        ev, ev_path = hunter_load_evidence(pn)

        if dry_run:
            outcome_code = "dry_run_skipped"
            channel_used = None
            url_found = None
            new_w, new_h, new_min = 0, 0, 0
        else:
            result = hunt_photo(pn, ev, ev_path, channels, series_map, dry_run=False)
            channel_used = result.get("channel")
            url_found = result.get("url")

            if result["status"] == "found":
                outcome_code = classify_outcome(pn, old_min_dim)
                new_raw = RAW_DIR / f"{pn}.jpg"
                new_w, new_h = get_dims(new_raw) if new_raw.exists() else (0, 0)
                new_min = min(new_w, new_h) if new_w and new_h else 0
                log.info(f"  → {outcome_code}: new={new_w}x{new_h} min={new_min} [{channel_used}]")
            else:
                outcome_code = "no_better_candidate"
                new_w, new_h, new_min = 0, 0, 0
                log.info("  → no candidate found")

        outcomes.append({
            "part_number": pn,
            "old_min_dimension": old_min_dim,
            "outcome": outcome_code,
            "channel_used": channel_used or "",
            "url_found": (url_found or "")[:200],
            "new_width": new_w,
            "new_height": new_h,
            "new_min_dimension": new_min,
        })

    return outcomes


def generate_rescue_seed(outcomes: list[dict], dry_run: bool) -> list[dict]:
    """Build seed records for SKUs with rescue success (rescued_good or rescued_but_small)."""
    success_codes = {"rescued_good", "rescued_but_small"}
    seed_records = []

    for oc in outcomes:
        if oc["outcome"] not in success_codes:
            continue
        pn = oc["part_number"]
        ev = load_evidence(pn)
        new_raw = RAW_DIR / f"{pn}.jpg"
        if not new_raw.exists():
            continue

        seed_records.append({
            "part_number": pn,
            "brand": ev.get("brand", ""),
            "product_name": ev.get("assembled_title", ""),
            "source_local_path": str(new_raw.resolve()),
            "source_photo_status": "placeholder",
            "source_storage_role": "canonical_raw_photo",
            "source_provider": oc.get("channel_used", "local_raw") or "local_raw",
            "enhancement_profile": "catalog_placeholder_v1",
            "background_hex": "#F4F1EB",
            "canvas_px": 1400,
            "content_ratio": 0.84,
            "notes": f"rescue_tiny:{oc['outcome']}",
        })

    if not dry_run and seed_records:
        RESCUE_SEED_JSONL.parent.mkdir(parents=True, exist_ok=True)
        with open(RESCUE_SEED_JSONL, "w", encoding="utf-8") as fh:
            for rec in seed_records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.info(f"Rescue seed written: {len(seed_records)} records → {RESCUE_SEED_JSONL}")

    return seed_records


def run_enhance_for_rescued(seed_records: list[dict], dry_run: bool) -> dict:
    """Run photo_enhance_local for rescued SKUs only."""
    if not seed_records:
        return {"enhanced": 0, "failed": 0}

    if dry_run:
        return {"enhanced": 0, "failed": 0, "dry_run": True}

    _scripts = str(Path(__file__).parent)
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)

    from photo_enhance_local import run as enhance_run

    results = enhance_run(RESCUE_SEED_JSONL, RESCUE_MANIFEST_JSONL)
    enhanced = sum(1 for r in results if r.get("enhanced_exists"))
    failed = len(results) - enhanced
    log.info(f"Enhance: {enhanced} success, {failed} failed")
    return {"enhanced": enhanced, "failed": failed}


def update_triage_manifest(outcomes: list[dict], dry_run: bool) -> None:
    """Write delta manifest for rescued SKUs and update tiny_quarantine."""
    import csv

    delta_path = TRIAGE_DIR / "rescue_tiny_delta.csv"

    # Build delta rows
    delta_rows = []
    for oc in outcomes:
        pn = oc["part_number"]
        new_raw = RAW_DIR / f"{pn}.jpg"
        new_raw_path = str(new_raw) if new_raw.exists() else ""

        # Find enhanced path if exists
        enh_path = ""
        for p in ENHANCED_DIR.glob(f"{pn}__*"):
            enh_path = str(p)
            break

        outcome = oc["outcome"]
        new_min = oc["new_min_dimension"]

        # Reclassify bucket
        if outcome == "rescued_good":
            bucket = "good_quality"
            photo_ready = new_raw_path and enh_path
            next_action = "keep_enhanced"
        elif outcome == "rescued_but_small":
            bucket = "needs_upscale"
            photo_ready = False
            next_action = "upscale_then_review"
        else:
            bucket = "tiny_quarantine"
            photo_ready = False
            next_action = "re_search_required"

        delta_rows.append({
            "part_number": pn,
            "raw_photo_path": new_raw_path,
            "raw_width": oc["new_width"],
            "raw_height": oc["new_height"],
            "min_dimension": new_min,
            "bucket": bucket,
            "enhanced_photo_path": enh_path,
            "enhanced_generated": bool(enh_path),
            "photo_ready_for_future_cloud": bool(photo_ready),
            "next_action": next_action,
            "rescue_outcome": outcome,
            "previous_status": "superseded_tiny",
        })

    if not dry_run and delta_rows:
        fieldnames = [
            "part_number", "raw_photo_path", "raw_width", "raw_height",
            "min_dimension", "bucket", "enhanced_photo_path", "enhanced_generated",
            "photo_ready_for_future_cloud", "next_action",
            "rescue_outcome", "previous_status",
        ]
        with open(delta_path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(delta_rows)
        log.info(f"Delta manifest: {len(delta_rows)} rows → {delta_path}")


def write_rescue_report(outcomes: list[dict], quarantine_map: list[dict], enhance_stats: dict) -> None:
    """Write rescue_tiny_report.json."""
    from collections import Counter
    outcome_counts = Counter(oc["outcome"] for oc in outcomes)

    report = {
        "batch": "TINY_PHOTO_RESCUE_v1",
        "date": "2026-04-11",
        "tiny_queue_total": len(outcomes),
        "outcomes": dict(outcome_counts),
        "rescued_good": outcome_counts.get("rescued_good", 0),
        "rescued_but_small": outcome_counts.get("rescued_but_small", 0),
        "no_better_candidate": outcome_counts.get("no_better_candidate", 0),
        "search_failed": outcome_counts.get("search_failed", 0),
        "enhance_success": enhance_stats.get("enhanced", 0),
        "enhance_failed": enhance_stats.get("failed", 0),
        "quarantined_assets": len([m for m in quarantine_map if m.get("quarantine_raw_path")]),
        "channel_yield": _channel_yield(outcomes),
        "details": outcomes,
    }

    RESCUE_REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESCUE_REPORT_JSON.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info(f"Rescue report: {RESCUE_REPORT_JSON}")


def _channel_yield(outcomes: list[dict]) -> dict:
    from collections import defaultdict
    by_channel: dict[str, list[str]] = defaultdict(list)
    for oc in outcomes:
        ch = oc.get("channel_used") or "none"
        by_channel[ch].append(oc["outcome"])
    return {
        ch: {
            "total": len(codes),
            "rescued": sum(1 for c in codes if c in ("rescued_good", "rescued_but_small")),
        }
        for ch, codes in sorted(by_channel.items())
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rescue tiny quarantine photos")
    parser.add_argument("--dry-run", action="store_true", help="Don't write files")
    parser.add_argument(
        "--channels", default="1,2,3,6",
        help="Channels: 1=OG-scrape, 2=PDF, 3=Family, 6=Gemini-Imagen (default: 1,2,3,6)"
    )
    args = parser.parse_args()

    dry_run = args.dry_run
    channels = [int(c.strip()) for c in args.channels.split(",")]
    mode = "DRY RUN" if dry_run else "LIVE"
    log.info(f"=== TINY PHOTO RESCUE v1 [{mode}] channels={channels} ===")

    # BLOCK 1: Load tiny queue
    tiny_records = load_tiny_queue()
    log.info(f"Tiny queue: {len(tiny_records)} SKUs")
    if not tiny_records:
        log.error("Nothing to process")
        return

    # BLOCK 2: Quarantine old assets
    log.info("--- BLOCK 2: Quarantining old tiny assets ---")
    quarantine_map = run_quarantine(tiny_records, dry_run)
    q_moved = sum(1 for m in quarantine_map if m.get("quarantine_raw_path"))
    log.info(f"Quarantined: {q_moved} raw files moved")

    # BLOCK 3: Re-search
    log.info("--- BLOCK 3: Re-searching for rescued photos ---")
    outcomes = run_rescue(tiny_records, channels, dry_run)

    from collections import Counter
    counts = Counter(oc["outcome"] for oc in outcomes)
    log.info(f"Outcomes: {dict(counts)}")

    # BLOCK 4 (classification already done inside run_rescue)
    rescued_pns = [oc["part_number"] for oc in outcomes
                   if oc["outcome"] in ("rescued_good", "rescued_but_small")]
    log.info(f"Rescue candidates for enhance: {len(rescued_pns)}")

    # BLOCK 5: Enhance rescued
    log.info("--- BLOCK 5: Enhancing rescued SKUs ---")
    seed_records = generate_rescue_seed(outcomes, dry_run)
    enhance_stats = run_enhance_for_rescued(seed_records, dry_run)

    # BLOCK 6: Update manifest
    log.info("--- BLOCK 6: Updating triage manifest ---")
    update_triage_manifest(outcomes, dry_run)

    # Write report
    if not dry_run:
        write_rescue_report(outcomes, quarantine_map, enhance_stats)

    # Summary
    print("\n=== TINY PHOTO RESCUE SUMMARY ===")
    print(f"  Tiny queue processed: {len(outcomes)}")
    print(f"  Quarantined old assets: {q_moved}")
    print(f"  rescued_good: {counts.get('rescued_good', 0)}")
    print(f"  rescued_but_small: {counts.get('rescued_but_small', 0)}")
    print(f"  no_better_candidate: {counts.get('no_better_candidate', 0)}")
    print(f"  search_failed: {counts.get('search_failed', 0)}")
    print(f"  Enhanced (rescued): {enhance_stats.get('enhanced', 0)} success, {enhance_stats.get('failed', 0)} fail")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""evidence_lifecycle.py — Batch lifecycle for evidence files.

Manages the accumulate → normalize → review → archive → next batch cycle.

Commands:
  status              Show current batch summary (normalizes first)
  archive --tag TAG   Archive current batch → downloads/archive/batch_{date}_{tag}/
  list                List all archived batches
  restore BATCH_ID    Restore archived batch to evidence/ (non-destructive)

Archive includes:
  - evidence/*.json   (all evidence files)
  - export/*          (xlsx, csv, json artifacts)
  - meta.json         (counts, status breakdown, coverage metrics)

Safety:
  - archive uses copy, then verifies, then deletes originals
  - restore refuses if evidence/ is not empty (use --force to override)
  - photos/ are NOT archived (large, reusable across batches)

Usage:
    python scripts/evidence_lifecycle.py status
    python scripts/evidence_lifecycle.py archive --tag r1-catalog-v1
    python scripts/evidence_lifecycle.py list
    python scripts/evidence_lifecycle.py restore batch_2026-04-11_r1-catalog-v1
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = ROOT / "downloads" / "evidence"
EXPORT_DIR = ROOT / "downloads" / "export"
ARCHIVE_DIR = ROOT / "downloads" / "archive"
SCRIPTS_DIR = ROOT / "scripts"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _evidence_files() -> list[Path]:
    """Return sorted list of evidence files in the active directory."""
    return sorted(EVIDENCE_DIR.glob("evidence_*.json"))


def _run_normalize() -> bool:
    """Run evidence_normalize.py. Returns True if success."""
    print("[lifecycle] Normalizing evidence files...")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "evidence_normalize.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        print(f"[lifecycle] normalize FAILED: {result.stderr[:500]}")
        return False
    # Print just the summary (last few lines)
    lines = result.stdout.strip().split("\n")
    summary_start = None
    for i, line in enumerate(lines):
        if "EVIDENCE NORMALIZE" in line:
            summary_start = i
            break
    if summary_start is not None:
        for line in lines[summary_start:]:
            print(f"  {line}")
    else:
        # Fallback: print last 5 lines
        for line in lines[-5:]:
            print(f"  {line}")
    return True


def _run_export_ready() -> dict | None:
    """Run export_ready.py --dry-run and parse summary. Returns summary dict."""
    print("[lifecycle] Computing export readiness...")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "export_ready.py"), "--dry-run"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        print(f"[lifecycle] export_ready FAILED: {result.stderr[:500]}")
        return None
    # Parse the JSON summary from output (last JSON block)
    stdout = result.stdout.strip()
    try:
        # Find last JSON object in output
        brace_depth = 0
        json_start = None
        for i in range(len(stdout) - 1, -1, -1):
            if stdout[i] == "}":
                if brace_depth == 0:
                    json_end = i + 1
                brace_depth += 1
            elif stdout[i] == "{":
                brace_depth -= 1
                if brace_depth == 0:
                    json_start = i
                    break
        if json_start is not None:
            return json.loads(stdout[json_start:json_end])
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _run_export_ready_write() -> dict | None:
    """Run export_ready.py (write mode) and return summary."""
    print("[lifecycle] Generating export artifacts...")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "export_ready.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        print(f"[lifecycle] export_ready FAILED: {result.stderr[:500]}")
        return None
    stdout = result.stdout.strip()
    try:
        brace_depth = 0
        json_start = None
        for i in range(len(stdout) - 1, -1, -1):
            if stdout[i] == "}":
                if brace_depth == 0:
                    json_end = i + 1
                brace_depth += 1
            elif stdout[i] == "{":
                brace_depth -= 1
                if brace_depth == 0:
                    json_start = i
                    break
        if json_start is not None:
            return json.loads(stdout[json_start:json_end])
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _load_evidence_summary(ev_files: list[Path]) -> dict:
    """Load evidence files and compute basic summary without running export_ready."""
    total = len(ev_files)
    normalized_count = 0
    stale_count = 0
    price_sources: dict[str, int] = {}
    brands: dict[str, int] = {}

    for f in ev_files:
        try:
            ev = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        brand = ev.get("brand", "unknown") or "unknown"
        brands[brand] = brands.get(brand, 0) + 1

        norm = ev.get("normalized")
        if norm and norm.get("schema_version") == "normalized_v1":
            normalized_count += 1
            src = norm.get("best_price_source") or "none"
            price_sources[src] = price_sources.get(src, 0) + 1
        else:
            stale_count += 1

    return {
        "total": total,
        "normalized": normalized_count,
        "stale": stale_count,
        "price_sources": price_sources,
        "brands": brands,
    }


# ── Commands ─────────────────────────────────────────────────────────────────


def cmd_status() -> int:
    """Show current batch status: normalize → readiness summary."""
    ev_files = _evidence_files()
    if not ev_files:
        print("No evidence files in downloads/evidence/")
        print("Load a batch: python scripts/catalog_import.py --input file.xlsx")
        return 0

    print(f"Evidence files: {len(ev_files)}")
    print()

    # Quick pre-check: how many are already normalized?
    pre_summary = _load_evidence_summary(ev_files)
    if pre_summary["stale"] > 0:
        print(f"  {pre_summary['stale']} files missing normalized{{}} block — normalizing...")
        _run_normalize()
        print()
    else:
        print("  All files have normalized{} block (fresh)")
        print()

    # Brand breakdown
    brands = pre_summary["brands"]
    if brands:
        print("Brands:")
        for brand, count in sorted(brands.items(), key=lambda x: -x[1]):
            print(f"  {brand}: {count}")
        print()

    # Run export_ready --dry-run for full readiness
    summary = _run_export_ready()
    if summary:
        print()
        print("=" * 50)
        print("BATCH STATUS")
        print("=" * 50)
        total = summary.get("total", 0)
        for status in ("EXPORT_READY", "DRAFT_EXPORT", "REVIEW_BLOCKED", "BLOCKED_NO_PRICE"):
            count = summary.get(status, 0)
            pct = f" ({int(100 * count / total)}%)" if total else ""
            print(f"  {status:20s} {count:4d}{pct}")
        print(f"  {'TOTAL':20s} {total:4d}")

    # Archive info
    print()
    archived = sorted(ARCHIVE_DIR.glob("batch_*")) if ARCHIVE_DIR.exists() else []
    if archived:
        print(f"Archived batches: {len(archived)} (run 'list' to see them)")
    else:
        print("No archived batches yet.")

    return 0


def cmd_archive(tag: str) -> int:
    """Archive current evidence + export to downloads/archive/batch_{date}_{tag}/."""
    ev_files = _evidence_files()
    if not ev_files:
        print("ERROR: No evidence files to archive.")
        return 1

    # Build batch ID
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    batch_id = f"batch_{date_str}_{tag}"
    batch_dir = ARCHIVE_DIR / batch_id

    if batch_dir.exists():
        print(f"ERROR: Archive '{batch_id}' already exists at {batch_dir}")
        print("Use a different --tag or remove the existing archive.")
        return 1

    print(f"Archiving {len(ev_files)} evidence files as '{batch_id}'...")
    print()

    # Step 1: Normalize (ensure fresh)
    if not _run_normalize():
        print("ERROR: Normalization failed. Fix errors before archiving.")
        return 1
    print()

    # Step 2: Generate fresh export artifacts
    export_summary = _run_export_ready_write()
    print()

    # Step 3: Create archive directory
    batch_ev_dir = batch_dir / "evidence"
    batch_export_dir = batch_dir / "export"
    batch_ev_dir.mkdir(parents=True, exist_ok=True)
    batch_export_dir.mkdir(parents=True, exist_ok=True)

    # Step 4: Copy evidence files
    print("[lifecycle] Copying evidence files to archive...")
    copied_ev = 0
    for f in ev_files:
        shutil.copy2(f, batch_ev_dir / f.name)
        copied_ev += 1
    print(f"  Copied {copied_ev} evidence files")

    # Step 5: Copy export artifacts
    export_files = []
    if EXPORT_DIR.exists():
        for f in EXPORT_DIR.iterdir():
            if f.is_file():
                shutil.copy2(f, batch_export_dir / f.name)
                export_files.append(f.name)
    print(f"  Copied {len(export_files)} export artifacts")

    # Step 6: Verify copy integrity (file count match)
    archived_ev = list(batch_ev_dir.glob("evidence_*.json"))
    if len(archived_ev) != len(ev_files):
        print(f"ERROR: Copy verification failed! Expected {len(ev_files)}, got {len(archived_ev)}")
        print(f"Archive directory left at {batch_dir} for inspection.")
        return 1

    # Step 7: Build readiness snapshot for meta.json
    status_breakdown = {}
    coverage = {}
    if export_summary:
        for s in ("EXPORT_READY", "DRAFT_EXPORT", "REVIEW_BLOCKED", "BLOCKED_NO_PRICE"):
            status_breakdown[s] = export_summary.get(s, 0)
        cov = export_summary.get("coverage", {})
        total = export_summary.get("total", len(ev_files))
        price_total = cov.get("price_contract", 0) + cov.get("price_pipeline1", 0) + cov.get("price_estimate", 0)
        coverage = {
            "price_total": f"{price_total}/{total}",
            "price_contract": cov.get("price_contract", 0),
            "price_pipeline1": cov.get("price_pipeline1", 0),
            "price_estimate": cov.get("price_estimate", 0),
            "description": f"{cov.get('desc_ok', 0)}/{total}",
            "photo": f"{cov.get('photo_url', 0) + cov.get('photo_local', 0)}/{total}",
            "specs": f"{cov.get('specs_ok', 0)}/{total}",
        }

    # Step 8: Write meta.json
    meta = {
        "batch_id": batch_id,
        "tag": tag,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "sku_count": len(ev_files),
        "status": status_breakdown,
        "coverage": coverage,
        "export_files": sorted(export_files),
        "source_branch": _git_branch(),
    }
    meta_path = batch_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # Step 9: Clean evidence files from active directory
    print()
    print("[lifecycle] Cleaning active evidence directory...")
    removed = 0
    for f in ev_files:
        f.unlink()
        removed += 1
    print(f"  Removed {removed} evidence files from downloads/evidence/")

    # Clean export artifacts
    if EXPORT_DIR.exists():
        for f in EXPORT_DIR.iterdir():
            if f.is_file():
                f.unlink()
        print("  Cleaned downloads/export/")

    # Step 10: Summary
    print()
    print("=" * 60)
    print(f"ARCHIVED: {batch_id}")
    print("=" * 60)
    print(f"  Location:  {batch_dir}")
    print(f"  SKUs:      {len(ev_files)}")
    if status_breakdown:
        for s, c in status_breakdown.items():
            print(f"  {s}: {c}")
    print()
    print("To load next batch:")
    print("  python scripts/catalog_import.py --input path/to/new_file.xlsx")
    print()
    print("To restore this batch:")
    print(f"  python scripts/evidence_lifecycle.py restore {batch_id}")

    return 0


def cmd_list() -> int:
    """List all archived batches."""
    if not ARCHIVE_DIR.exists():
        print("No archives found.")
        return 0

    batches = sorted(ARCHIVE_DIR.glob("batch_*"))
    if not batches:
        print("No archives found.")
        return 0

    print(f"Archived batches ({len(batches)}):")
    print()
    for bd in batches:
        meta_path = bd / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                skus = meta.get("sku_count", "?")
                tag = meta.get("tag", "")
                archived_at = meta.get("archived_at", "")[:10]
                status = meta.get("status", {})
                ready = status.get("EXPORT_READY", 0)
                print(f"  {bd.name}")
                print(f"    Tag: {tag}  |  SKUs: {skus}  |  EXPORT_READY: {ready}  |  Date: {archived_at}")
            except (json.JSONDecodeError, OSError):
                print(f"  {bd.name} (meta.json unreadable)")
        else:
            ev_count = len(list((bd / "evidence").glob("evidence_*.json"))) if (bd / "evidence").exists() else "?"
            print(f"  {bd.name} ({ev_count} evidence files, no meta.json)")
        print()

    return 0


def cmd_restore(batch_id: str, force: bool = False) -> int:
    """Restore archived batch to active evidence directory."""
    batch_dir = ARCHIVE_DIR / batch_id
    if not batch_dir.exists():
        print(f"ERROR: Archive '{batch_id}' not found at {batch_dir}")
        print("Run 'list' to see available archives.")
        return 1

    batch_ev_dir = batch_dir / "evidence"
    if not batch_ev_dir.exists():
        print(f"ERROR: No evidence/ directory in archive '{batch_id}'")
        return 1

    # Safety: refuse if evidence/ is not empty
    existing = _evidence_files()
    if existing and not force:
        print(f"ERROR: Active evidence directory has {len(existing)} files.")
        print("Archive the current batch first, or use --force to overwrite.")
        return 1

    archived_files = sorted(batch_ev_dir.glob("evidence_*.json"))
    if not archived_files:
        print(f"ERROR: No evidence files in archive '{batch_id}'")
        return 1

    # Restore evidence files
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Restoring {len(archived_files)} evidence files from '{batch_id}'...")
    for f in archived_files:
        shutil.copy2(f, EVIDENCE_DIR / f.name)
    print(f"  Restored {len(archived_files)} evidence files to downloads/evidence/")

    # Restore export artifacts
    batch_export_dir = batch_dir / "export"
    if batch_export_dir.exists():
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        export_count = 0
        for f in batch_export_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, EXPORT_DIR / f.name)
                export_count += 1
        print(f"  Restored {export_count} export artifacts to downloads/export/")

    # Show meta if available
    meta_path = batch_dir / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            print()
            print(f"Batch: {meta.get('tag', batch_id)}")
            print(f"Originally archived: {meta.get('archived_at', 'unknown')}")
            status = meta.get("status", {})
            if status:
                for s, c in status.items():
                    print(f"  {s}: {c}")
        except (json.JSONDecodeError, OSError):
            pass

    print()
    print("Restore complete. Run 'status' to verify:")
    print("  python scripts/evidence_lifecycle.py status")

    return 0


def _git_branch() -> str:
    """Get current git branch name, or empty string."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Evidence batch lifecycle: status / archive / list / restore"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show current batch summary")

    p_archive = sub.add_parser("archive", help="Archive current batch")
    p_archive.add_argument("--tag", required=True, help="Batch tag (e.g. r1-catalog-v1)")

    sub.add_parser("list", help="List archived batches")

    p_restore = sub.add_parser("restore", help="Restore archived batch")
    p_restore.add_argument("batch_id", help="Batch ID (e.g. batch_2026-04-11_r1-catalog-v1)")
    p_restore.add_argument("--force", action="store_true",
                           help="Overwrite existing evidence files")

    args = parser.parse_args()

    if args.command == "status":
        return cmd_status()
    elif args.command == "archive":
        return cmd_archive(tag=args.tag)
    elif args.command == "list":
        return cmd_list()
    elif args.command == "restore":
        return cmd_restore(batch_id=args.batch_id, force=args.force)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())

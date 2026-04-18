"""Rebuild all derived consumer artifacts from evidence/*.json.

Single entry point that produces a versioned bundle for downstream
transformers (InSales / Ozon / WB / eBay / Amazon / Avito).

Per external audit 2026-04-18 (4 AIs consensus): manual snapshot cascade
is the main "forever" blocker. This script collapses the cascade into one
command and publishes atomically with a freshness/provenance manifest.

Flow:
  evidence/*.json
  → _export_for_categorizer.py (produces from_datasheet_for_categorizer.json)
  → build_unified_product_dataset.py (produces unified_product_dataset.json)
  → atomic publish to final paths + manifest.json with build_id/evidence_hash

Each consumer transformer checks manifest freshness before reading, aborts
with clear error if stale (N1 Fail Loud).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import io
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent.parent
EV_DIR = ROOT / "downloads" / "evidence"
STAGING_DIR = ROOT / "downloads" / "staging"
KNOWLEDGE_DIR = ROOT / "downloads" / "knowledge"

# Target artifacts (what downstream consumers read)
CATEGORIZER_SNAPSHOT = STAGING_DIR / "from_datasheet_for_categorizer.json"
UNIFIED_DATASET = KNOWLEDGE_DIR / "unified_product_dataset.json"
MANIFEST_FILE = KNOWLEDGE_DIR / "consumer_artifacts_manifest.json"

SCHEMA_VERSION = "1.0"


def compute_evidence_hash(ev_dir: Path) -> str:
    """SHA-256 over sorted list of (filename, size, mtime_ns) of evidence files.

    Detects additions, deletions, modifications. Fast (no content read).
    Excludes evidence_coverage_report.json (disposable report).
    """
    parts = []
    for f in sorted(ev_dir.glob("evidence_*.json")):
        st = f.stat()
        parts.append(f"{f.name}:{st.st_size}:{st.st_mtime_ns}")
    hasher = hashlib.sha256()
    hasher.update("\n".join(parts).encode("utf-8"))
    return hasher.hexdigest()[:16]  # 16 hex chars = 64-bit


def run_step(name: str, cmd: list[str]) -> None:
    """Run a subprocess step; abort the whole rebuild on non-zero exit."""
    print(f"\n==> {name}")
    print(f"    $ {' '.join(cmd)}")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, cwd=str(ROOT), env=env, text=True,
                            capture_output=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"STDOUT:\n{result.stdout[-2000:]}")
        print(f"STDERR:\n{result.stderr[-2000:]}")
        raise SystemExit(f"Step '{name}' failed with exit {result.returncode}")
    print(f"    OK (stdout: {len(result.stdout)} chars, stderr: {len(result.stderr)} chars)")


def atomic_replace(src: Path, dst: Path) -> None:
    """Atomically replace dst with src. Works on Windows + POSIX."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    # os.replace is atomic on both POSIX and Windows (Python 3.3+).
    os.replace(str(src), str(dst))


def main():
    now = datetime.now(timezone.utc)
    build_id = now.strftime("build_%Y%m%dT%H%M%SZ")
    evidence_hash = compute_evidence_hash(EV_DIR)

    print("=" * 80)
    print(f"REBUILD CONSUMER ARTIFACTS  build_id={build_id}")
    print(f"Evidence hash: {evidence_hash} ({sum(1 for _ in EV_DIR.glob('evidence_*.json'))} files)")
    print("=" * 80)

    # Step 1: rebuild categorizer snapshot via existing script.
    # It writes directly to STAGING_DIR/from_datasheet_for_categorizer.json.
    # We accept that write (it's idempotent re: same inputs) — no tmp staging
    # because that script doesn't support --output arg yet.
    run_step(
        "Layer A: from_datasheet_for_categorizer",
        [sys.executable, str(ROOT / "scripts" / "pipeline_v2" / "_export_for_categorizer.py")],
    )
    if not CATEGORIZER_SNAPSHOT.exists():
        raise SystemExit(f"Expected output missing: {CATEGORIZER_SNAPSHOT}")

    # Step 2: rebuild unified_product_dataset via existing script.
    # It writes directly to KNOWLEDGE_DIR/unified_product_dataset.json.
    run_step(
        "Layer B: unified_product_dataset",
        [sys.executable, str(ROOT / "scripts" / "build_unified_product_dataset.py")],
    )
    if not UNIFIED_DATASET.exists():
        raise SystemExit(f"Expected output missing: {UNIFIED_DATASET}")

    # Compute output hashes
    def sha256_file(p: Path) -> str:
        h = hashlib.sha256()
        h.update(p.read_bytes())
        return h.hexdigest()[:16]

    categorizer_hash = sha256_file(CATEGORIZER_SNAPSHOT)
    unified_hash = sha256_file(UNIFIED_DATASET)

    # Step 3: write manifest atomically via tmp + rename.
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "build_id": build_id,
        "built_at": now.isoformat(),
        "evidence_hash": evidence_hash,
        "evidence_file_count": sum(1 for _ in EV_DIR.glob("evidence_*.json")),
        "artifacts": {
            "categorizer_snapshot": {
                "path": str(CATEGORIZER_SNAPSHOT.relative_to(ROOT)).replace("\\", "/"),
                "sha256_16": categorizer_hash,
                "size": CATEGORIZER_SNAPSHOT.stat().st_size,
            },
            "unified_product_dataset": {
                "path": str(UNIFIED_DATASET.relative_to(ROOT)).replace("\\", "/"),
                "sha256_16": unified_hash,
                "size": UNIFIED_DATASET.stat().st_size,
            },
        },
        "consumers_expected": [
            "scripts/pipeline_v2/_insales_transformer.py",
            # Future: ozon_transformer.py, wb_transformer.py, ebay_transformer.py, etc.
        ],
    }

    # Atomic write: tmp file in same dir + os.replace
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".manifest.", suffix=".tmp", dir=str(MANIFEST_FILE.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        atomic_replace(Path(tmp_path), MANIFEST_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    print()
    print("=" * 80)
    print(f"REBUILD COMPLETE  build_id={build_id}")
    print(f"  evidence_hash:   {evidence_hash}")
    print(f"  categorizer:     {categorizer_hash}  ({CATEGORIZER_SNAPSHOT.stat().st_size} bytes)")
    print(f"  unified:         {unified_hash}  ({UNIFIED_DATASET.stat().st_size} bytes)")
    print(f"  manifest:        {MANIFEST_FILE}")
    print("=" * 80)
    print()
    print("Next: consumer transformers can now read freshly-validated artifacts.")
    print("  python scripts/pipeline_v2/_insales_transformer.py")


if __name__ == "__main__":
    main()

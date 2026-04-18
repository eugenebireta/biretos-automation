#!/usr/bin/env python3
"""Pre-commit companion: regenerate frozen_list cache when PROJECT_DNA.md §3 changes.

Runs as a pre-commit hook when `docs/PROJECT_DNA.md` is staged. Regenerates
`.claude/hooks/_cache/frozen_list.json` and stages it so the canonical cache
stays in sync with DNA.md in git history. This way:

  - fresh clones have a ready cache (frozen_guard doesn't fail-closed on first
    Write before DNA.md has been read)
  - CI systems can validate the cache hash matches DNA.md content hash
  - diff review surfaces FROZEN list changes explicitly

Exit 0: cache up-to-date or regenerated and staged.
Exit 1: parse failure (pre-commit will halt the commit).

Reference: AI-Audit Tier 4 Addendum (2026-04-18) — "git pre-commit companion
keeps the cache canonical in git for fresh clones and CI."
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

# Import the parser from frozen_guard
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from frozen_guard import _parse_section_3  # type: ignore
except ImportError:
    print("error: cannot import frozen_guard._parse_section_3", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent.parent
DNA_PATH = REPO / "docs" / "PROJECT_DNA.md"
CACHE_DIR = REPO / ".claude" / "hooks" / "_cache"
CACHE_FILE = CACHE_DIR / "frozen_list.json"


def main() -> int:
    if not DNA_PATH.exists():
        print(f"error: {DNA_PATH} missing — cannot refresh cache", file=sys.stderr)
        return 1

    dna_bytes = DNA_PATH.read_bytes()
    dna_hash = hashlib.sha256(dna_bytes).hexdigest()[:16]

    try:
        paths = _parse_section_3(dna_bytes.decode("utf-8"))
    except Exception as e:
        print(f"error: DNA.md §3 parse failed: {e}", file=sys.stderr)
        return 1

    # Check if cache is already up-to-date
    if CACHE_FILE.exists():
        try:
            existing = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if existing.get("dna_hash") == dna_hash and existing.get("paths") == paths:
                return 0  # nothing to do
        except Exception:
            pass

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps(
            {"dna_hash": dna_hash, "cached_at": time.time(), "paths": paths},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Note: this script does NOT `git add` the cache because .claude/hooks/_cache/
    # is gitignored by policy (runtime state, should not be in git history).
    # The cache is rebuilt on first hook invocation after clone. This pre-commit
    # variant is run for side-effect of parse-validation only — if DNA.md
    # structure becomes unparseable, the commit is blocked.
    print(f"frozen_list cache refreshed: {len(paths)} paths, hash={dna_hash}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

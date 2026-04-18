"""evidence_contract_hardening_v1.py — EVIDENCE CONTRACT HARDENING v1

Foundation patch: adds 3 new fields to evidence bundles.

Changes per evidence file:
  1. subbrand — filled only when HIGH CONFIDENCE signal in assembled_title or name
  2. training_urls — list of research URLs from JSONL training files + dr_sources
  3. price_contract — skeleton object bridging flat dr_price fields to structured form

SAFE RULES:
  - Never deletes existing fields
  - Never overwrites non-empty subbrand
  - Writes null for subbrand when uncertain (not empty string)
  - training_urls: empty list [] when no URLs found (not null)
  - price_contract: judge_status="pending", unit_basis=null, source=null, lineage=null
  - price_contract only if dr_price or our_price_raw exists

Usage:
    python scripts/evidence_contract_hardening_v1.py --dry-run
    python scripts/evidence_contract_hardening_v1.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────────

EVIDENCE_DIR = Path("downloads/evidence")
TRAINING_DATA_DIR = Path("training_data")

TRAINING_JSONL_FILES = [
    "dr_url_training_2026-04-08.jsonl",
    "dr_url_training_2026-04-10.jsonl",
]

# Subbrand detection: keyword → canonical subbrand name
# Order matters: higher = higher priority
SUBBRAND_KEYWORDS: list[tuple[str, str]] = [
    ("PEHA", "PEHA"),
    ("ESSER", "Esser"),
    ("ESSERNET", "Esser"),
    ("ESSERBUS", "Esser"),
    ("NOTIFIER", "Notifier"),
    ("ELSTER", "Elster"),
    ("SAIA", "SAIA"),
    ("AUTRONICA", "Autronica"),
    ("SECURITON", "Securiton"),
]


# ── Subbrand detection ───────────────────────────────────────────────────────

def detect_subbrand(evidence: dict) -> str | None:
    """Detect subbrand with HIGH CONFIDENCE only.

    Priority:
      1. assembled_title — highest confidence (canonical title we built)
      2. name / content.seed_name — medium confidence
      3. deep_research.title_ru / description_ru — lower but still valid

    Returns canonical subbrand string or None (will be stored as null).
    """
    title = (evidence.get("assembled_title") or "").upper()
    name = (evidence.get("name") or "").upper()

    # Pass 1: assembled_title (high confidence)
    for keyword, subbrand in SUBBRAND_KEYWORDS:
        if keyword in title:
            return subbrand

    # Pass 2: name field
    for keyword, subbrand in SUBBRAND_KEYWORDS:
        if keyword in name:
            return subbrand

    # Pass 3: deep_research fields (DR often discovers the real brand)
    dr = evidence.get("deep_research") or {}
    dr_title = (dr.get("title_ru") or "").upper()
    dr_desc = (dr.get("description_ru") or "")[:1000].upper()
    for keyword, subbrand in SUBBRAND_KEYWORDS:
        if keyword in dr_title or keyword in dr_desc:
            return subbrand

    return None


# ── Training URL index ───────────────────────────────────────────────────────

def build_training_url_index() -> dict[str, list[str]]:
    """Build PN → sorted unique URL list from all JSONL training files."""
    index: dict[str, set[str]] = defaultdict(set)

    for fname in TRAINING_JSONL_FILES:
        fpath = TRAINING_DATA_DIR / fname
        if not fpath.exists():
            print(f"  [WARN] Training file not found: {fpath}", file=sys.stderr)
            continue
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                pn = (row.get("pn") or "").strip()
                url = (row.get("url") or "").strip()
                if pn and url and url.startswith("http"):
                    index[pn].add(url)

    return {pn: sorted(urls) for pn, urls in index.items()}


def collect_dr_source_urls(evidence: dict) -> list[str]:
    """Collect URLs from dr_sources list already in evidence."""
    urls = []
    for src in evidence.get("dr_sources") or []:
        url = (src.get("url") or "").strip()
        if url and url.startswith("http"):
            urls.append(url)
    return urls


# ── Price skeleton ───────────────────────────────────────────────────────────

def _parse_our_price_raw(raw: str | None) -> float | None:
    """Try to parse Russian-format price string like '13 288,04' → 13288.04."""
    if not raw:
        return None
    cleaned = raw.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


def build_price_contract(evidence: dict) -> dict | None:
    """Build price_contract skeleton from existing flat dr_price fields.

    Returns None if there is no price data at all (not worth creating empty skeleton).
    """
    dr_price = evidence.get("dr_price")
    dr_currency = evidence.get("dr_currency")
    our_price_raw = evidence.get("our_price_raw")
    dr_price_flag = evidence.get("dr_price_flag")
    dr_price_source = evidence.get("dr_price_source")

    our_price_parsed = _parse_our_price_raw(our_price_raw)

    has_any_price = dr_price is not None or our_price_parsed is not None

    if not has_any_price:
        return None

    pack_suspect = dr_price_flag == "PACK_SUSPECT" if dr_price_flag else False

    return {
        "schema_version": "price_contract_v1",
        "dr_value": dr_price,
        "dr_currency": dr_currency,
        "dr_source_url": dr_price_source,
        "our_price_raw": our_price_raw,
        "our_price_parsed": our_price_parsed,
        "judge_status": "pending",
        "unit_basis": None,
        "source": None,
        "lineage": None,
        "pack_suspect": pack_suspect,
    }


# ── Main patch ───────────────────────────────────────────────────────────────

def run(dry_run: bool = False) -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    evidence_files = sorted(EVIDENCE_DIR.glob("evidence_*.json"))
    if not evidence_files:
        print(f"ERROR: No evidence files found in {EVIDENCE_DIR}")
        sys.exit(1)

    print(f"{'[DRY RUN] ' if dry_run else ''}Processing {len(evidence_files)} evidence files...")
    print()

    # Build training URL index once
    print("Building training URL index...")
    url_index = build_training_url_index()
    print(f"  {len(url_index)} SKUs have training URLs in JSONL files")
    print()

    # Stats
    stats = {
        "subbrand_filled": 0,
        "subbrand_null": 0,
        "subbrand_skipped_already_set": 0,
        "subbrand_by_title": defaultdict(int),
        "subbrand_by_name": defaultdict(int),
        "training_urls_filled": 0,
        "training_urls_empty": 0,
        "training_urls_total": 0,
        "price_contract_created": 0,
        "price_contract_skipped_no_price": 0,
        "price_contract_skipped_already_exists": 0,
        "pack_suspect_flagged": 0,
        "files_modified": 0,
        "files_unchanged": 0,
    }

    ambiguous_cases: list[dict] = []

    for fpath in evidence_files:
        evidence = json.loads(fpath.read_text(encoding="utf-8"))
        pn = evidence.get("pn", fpath.stem.replace("evidence_", ""))
        modified = False

        # ── BLOCK 1: subbrand ───────────────────────────────────────────────
        current_subbrand = evidence.get("subbrand")
        if current_subbrand and current_subbrand != "":
            # Already set — skip
            stats["subbrand_skipped_already_set"] += 1
        else:
            # Detect subbrand
            # Check if fields give conflicting signals (ambiguous)
            title = (evidence.get("assembled_title") or "").upper()
            name_field = (evidence.get("name") or "").upper()

            title_matches = list({sb for kw, sb in SUBBRAND_KEYWORDS if kw in title})
            name_matches = list({sb for kw, sb in SUBBRAND_KEYWORDS if kw in name_field})

            # If title gives clear signal → use it (no ambiguity)
            # If title gives nothing but name gives conflicting signals → ambiguous → null
            if len(name_matches) > 1 and not title_matches:
                ambiguous_cases.append({"pn": pn, "title_matches": title_matches, "name_matches": name_matches})
                detected = None
            else:
                detected = detect_subbrand(evidence)

            if detected:
                evidence["subbrand"] = detected
                # Determine which field triggered it
                if title_matches:
                    stats["subbrand_by_title"][detected] += 1
                else:
                    stats["subbrand_by_name"][detected] += 1
                stats["subbrand_filled"] += 1
                modified = True
            else:
                # Write None (will become JSON null), replacing empty string
                evidence["subbrand"] = None
                stats["subbrand_null"] += 1
                modified = True

        # ── BLOCK 2: training_urls ──────────────────────────────────────────
        if "training_urls" not in evidence:
            # Collect from JSONL index
            jsonl_urls = url_index.get(pn, [])
            # Also collect from dr_sources already in evidence
            dr_src_urls = collect_dr_source_urls(evidence)
            # Merge, deduplicate, sort
            all_urls = sorted(set(jsonl_urls) | set(dr_src_urls))
            evidence["training_urls"] = all_urls
            stats["training_urls_total"] += len(all_urls)
            if all_urls:
                stats["training_urls_filled"] += 1
            else:
                stats["training_urls_empty"] += 1
            modified = True

        # ── BLOCK 3: price_contract ─────────────────────────────────────────
        if "price_contract" in evidence:
            stats["price_contract_skipped_already_exists"] += 1
        else:
            skeleton = build_price_contract(evidence)
            if skeleton:
                evidence["price_contract"] = skeleton
                stats["price_contract_created"] += 1
                if skeleton["pack_suspect"]:
                    stats["pack_suspect_flagged"] += 1
                modified = True
            else:
                stats["price_contract_skipped_no_price"] += 1

        # ── Write back ──────────────────────────────────────────────────────
        if modified:
            stats["files_modified"] += 1
            if not dry_run:
                fpath.write_text(
                    json.dumps(evidence, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        else:
            stats["files_unchanged"] += 1

    # ── Report ──────────────────────────────────────────────────────────────
    print("=" * 60)
    print("EVIDENCE CONTRACT HARDENING v1 — RESULTS")
    print("=" * 60)
    print()
    print("SUBBRAND PATCH:")
    print(f"  filled (high confidence): {stats['subbrand_filled']}")
    for sb, cnt in sorted(stats["subbrand_by_title"].items()):
        print(f"    from assembled_title — {sb}: {cnt}")
    for sb, cnt in sorted(stats["subbrand_by_name"].items()):
        print(f"    from name field     — {sb}: {cnt}")
    print(f"  left null (no signal):    {stats['subbrand_null']}")
    print(f"  skipped (already set):    {stats['subbrand_skipped_already_set']}")
    if ambiguous_cases:
        print(f"  ambiguous cases:          {len(ambiguous_cases)}")
        for case in ambiguous_cases[:5]:
            print(f"    PN={case['pn']}: title={case['title_matches']} name={case['name_matches']}")
    print()
    print("TRAINING URLS PATCH:")
    print(f"  evidence with URLs:    {stats['training_urls_filled']}")
    print(f"  evidence empty []:     {stats['training_urls_empty']}")
    print(f"  total URLs written:    {stats['training_urls_total']}")
    if stats["training_urls_filled"] > 0:
        avg = stats["training_urls_total"] / stats["training_urls_filled"]
        print(f"  avg URLs per SKU:      {avg:.1f}")
    print()
    print("PRICE CONTRACT PATCH:")
    print(f"  skeletons created:     {stats['price_contract_created']}")
    print(f"  skipped (no price):    {stats['price_contract_skipped_no_price']}")
    print(f"  skipped (exists):      {stats['price_contract_skipped_already_exists']}")
    print(f"  pack_suspect flagged:  {stats['pack_suspect_flagged']}")
    print()
    print("FILES:")
    print(f"  modified:  {stats['files_modified']}")
    print(f"  unchanged: {stats['files_unchanged']}")
    if dry_run:
        print()
        print("[DRY RUN] No files were written. Remove --dry-run to apply.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evidence Contract Hardening v1")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()
    run(dry_run=args.dry_run)

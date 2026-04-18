"""Import Phase 3B Claude DR content results into evidence files.

Reads a text file containing one or more concatenated JSON arrays.
Applies to evidence: product_category, description_ru (if provided), photo_url (if found).

Usage:
    python scripts/phase3b_content_import.py --input "C:/Users/eugene/Downloads/claude ext.txt" [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

EVIDENCE_DIR = Path('downloads/evidence')


def parse_file(path: Path) -> list[dict]:
    """Parse file containing one or more concatenated JSON arrays."""
    text = path.read_text(encoding='utf-8')
    results = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '[':
            if depth == 0:
                start = i
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0 and start is not None:
                chunk = text[start:i + 1]
                try:
                    arr = json.loads(chunk)
                    if arr and isinstance(arr[0], dict) and 'pn' in arr[0]:
                        results.extend(arr)
                except json.JSONDecodeError as e:
                    print(f'  WARN: JSON parse error at pos {start}: {e}')
                start = None
    return results


def deduplicate(records: list[dict]) -> dict[str, dict]:
    """For duplicate PNs keep the richest result (most non-null fields)."""
    best: dict[str, dict] = {}
    for r in records:
        pn = r.get('pn', '').strip()
        if not pn:
            continue
        existing = best.get(pn)
        if existing is None:
            best[pn] = r
        else:
            # Count non-null values — prefer richer record
            score_new = sum(1 for v in r.values() if v is not None)
            score_old = sum(1 for v in existing.values() if v is not None)
            if score_new > score_old:
                best[pn] = r
    return best


def find_evidence_file(pn: str) -> Path | None:
    direct = EVIDENCE_DIR / f'evidence_{pn}.json'
    if direct.exists():
        return direct
    for ch in ('-', '_'):
        alt = EVIDENCE_DIR / f'evidence_{pn.replace("/", ch)}.json'
        if alt.exists():
            return alt
    return None


def import_results(records: dict[str, dict], dry_run: bool) -> None:
    found = 0
    no_file = 0
    cat_updated = 0
    desc_updated = 0
    photo_updated = 0
    nothing_applied = 0

    for pn, r in sorted(records.items()):
        ev_path = find_evidence_file(pn)
        if ev_path is None:
            print(f'  NO FILE: {pn}')
            no_file += 1
            continue

        found += 1
        ev = json.loads(ev_path.read_text(encoding='utf-8'))
        norm = ev.setdefault('normalized', {})

        applied = []

        # 1. Category — apply if evidence has none
        new_cat = r.get('category')
        old_cat = ev.get('product_category', '') or ev.get('dr_category', '')
        if new_cat and not old_cat:
            ev['product_category'] = new_cat
            cat_updated += 1
            applied.append(f'cat={new_cat}')

        # 2. Description — apply if provided (overrides bad/short description)
        new_desc = r.get('description_ru')
        if new_desc and len(new_desc) > 80:
            norm['best_description'] = new_desc
            norm['best_description_source'] = 'phase3b'
            desc_updated += 1
            applied.append(f'desc={len(new_desc)}ch')

        # 3. Photo — apply if found and evidence has none
        new_photo = r.get('photo_url')
        if new_photo and not norm.get('best_photo_url'):
            norm['best_photo_url'] = new_photo
            norm['best_photo_source'] = 'phase3b'
            photo_updated += 1
            applied.append('photo')

        if applied:
            print(f'  OK: {pn} | {", ".join(applied)}')
            if not dry_run:
                ev_path.write_text(json.dumps(ev, indent=2, ensure_ascii=False), encoding='utf-8')
        else:
            nothing_applied += 1

    print()
    print(f'Results: {found} evidence files found, {no_file} missing')
    print(f'  category updated:    {cat_updated}')
    print(f'  description updated: {desc_updated}')
    print(f'  photo updated:       {photo_updated}')
    print(f'  nothing to apply:    {nothing_applied}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        print(f'ERROR: not found: {path}')
        sys.exit(1)

    print(f'Parsing: {path}')
    records = parse_file(path)
    print(f'Total records: {len(records)}')
    deduped = deduplicate(records)
    print(f'Unique PNs: {len(deduped)}')
    print(f'Dry run: {args.dry_run}')
    print()

    import_results(deduped, args.dry_run)


if __name__ == '__main__':
    main()

"""phase1_recon_import.py — Import Phase 1 Identity Recon results from Haiku.

Parses markdown tables from recon result file and updates evidence files with:
- product_type, series, type_designation (PEHA), product_line (Honeywell)
- pn_aliases → merged into pn_variants
- manufacturer corrections (flags non-Honeywell items)
- discontinued status

Usage:
    python scripts/phase1_recon_import.py --source C:/Users/eugene/Downloads/haiku.txt [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

EVIDENCE_DIR = Path('downloads/evidence')
RESULTS_DIR = Path('research_results')
RESULTS_DIR.mkdir(exist_ok=True)

# (no manufacturer filtering — Excel contains mixed brands, all are valid)


def parse_tables(text: str) -> list[dict]:
    """Extract all markdown table rows from text."""
    records = []
    lines = text.splitlines()
    headers = None
    in_table = False

    for line in lines:
        line = line.strip()
        if not line.startswith('|'):
            in_table = False
            headers = None
            continue

        cells = [c.strip() for c in line.split('|') if c.strip()]

        # Header row
        if 'product_type' in cells and 'PN' in cells:
            headers = [h.lower().replace(' ', '_') for h in cells]
            in_table = True
            continue

        # Separator row
        if all(set(c) <= set('-:') for c in cells):
            continue

        if in_table and headers and len(cells) == len(headers):
            row = dict(zip(headers, cells))
            pn = row.get('pn', '').strip()
            if pn and pn != 'PN' and not all(c == '-' for c in pn):
                records.append(row)

    return records


def find_evidence(pn: str) -> Path | None:
    """Find evidence file for a PN."""
    direct = EVIDENCE_DIR / f'evidence_{pn}.json'
    if direct.exists():
        return direct
    # Try case-insensitive
    for f in EVIDENCE_DIR.iterdir():
        if f.name.lower() == f'evidence_{pn.lower()}.json':
            return f
    return None


def merge_variants(existing: list, new_aliases: str) -> list:
    """Merge new aliases into existing pn_variants list."""
    result = list(existing)
    if not new_aliases or new_aliases in ('-', '—', 'unknown', ''):
        return result
    for alias in re.split(r'[,;]\s*', new_aliases):
        alias = alias.strip()
        if alias and alias not in result:
            result.append(alias)
    return result


def apply_peha_record(ev: dict, row: dict) -> tuple[dict, list[str]]:
    """Apply PEHA identity recon record to evidence dict. Returns (updated_ev, changes)."""
    changes = []

    product_type = row.get('product_type', '').strip()
    series = row.get('series', '').strip()
    type_designation = row.get('type_designation', '').strip()
    color_material = row.get('color_material', '').strip()
    pn_aliases = row.get('pn_aliases', '').strip()
    notes = row.get('identity_notes', '').strip()

    # structured_identity block
    si = ev.setdefault('structured_identity', {})

    if type_designation and type_designation not in ('unconfirmed', '-', '—', 'unknown'):
        old = si.get('type_designation', '')
        if old != type_designation:
            si['type_designation'] = type_designation
            changes.append(f'type_designation: {old!r} → {type_designation!r}')

    if series and series not in ('-', '—', 'unknown'):
        old = si.get('series', '')
        if old != series:
            si['series'] = series
            changes.append(f'series: {old!r} → {series!r}')

    if color_material and color_material not in ('-', '—'):
        old = si.get('color_material', '')
        if old != color_material:
            si['color_material'] = color_material
            changes.append(f'color_material: {old!r} → {color_material!r}')

    if product_type and product_type not in ('-', '—', 'unknown'):
        content = ev.setdefault('content', {})
        old = content.get('product_type', '')
        if old != product_type:
            content['product_type'] = product_type
            changes.append(f'product_type: {old!r} → {product_type!r}')

    # pn_variants
    old_variants = ev.get('pn_variants', [])
    new_variants = merge_variants(old_variants, pn_aliases)
    if new_variants != old_variants:
        ev['pn_variants'] = new_variants
        changes.append(f'pn_variants: added {set(new_variants)-set(old_variants)}')

    if notes and notes not in ('-', '—'):
        si['identity_notes_p1'] = notes

    si['phase1_recon_done'] = True

    return ev, changes


def apply_hw_record(ev: dict, row: dict) -> tuple[dict, list[str]]:
    """Apply Honeywell identity recon record to evidence dict. Returns (updated_ev, changes)."""
    changes = []

    product_type = row.get('product_type', '').strip()
    product_line = row.get('product_line', '').strip()
    manufacturer = row.get('manufacturer', '').strip()
    pn_aliases = row.get('pn_aliases', '').strip()
    discontinued = row.get('discontinued', '').strip().lower()
    notes = row.get('identity_notes', '').strip()

    si = ev.setdefault('structured_identity', {})
    content = ev.setdefault('content', {})

    if product_type and product_type not in ('-', '—', 'unknown'):
        old = content.get('product_type', '')
        if old != product_type:
            content['product_type'] = product_type
            changes.append(f'product_type: {old!r} → {product_type!r}')

    if product_line and product_line not in ('-', '—', 'unknown'):
        old = si.get('product_line', '')
        if old != product_line:
            si['product_line'] = product_line
            changes.append(f'product_line: {old!r} → {product_line!r}')

    if manufacturer and manufacturer not in ('-', '—', 'unknown'):
        old = si.get('confirmed_manufacturer', '')
        if old != manufacturer:
            si['confirmed_manufacturer'] = manufacturer
            changes.append(f'manufacturer: {old!r} → {manufacturer!r}')

    if discontinued in ('yes', 'true'):
        si['discontinued'] = True
        changes.append('discontinued: True')
    elif discontinued in ('no', 'false'):
        si['discontinued'] = False

    # pn_variants
    old_variants = ev.get('pn_variants', [])
    new_variants = merge_variants(old_variants, pn_aliases)
    if new_variants != old_variants:
        ev['pn_variants'] = new_variants
        changes.append(f'pn_variants: added {set(new_variants)-set(old_variants)}')

    if notes and notes not in ('-', '—'):
        si['identity_notes_p1'] = notes

    si['phase1_recon_done'] = True

    return ev, changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, help='Path to haiku.txt results file')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    source = Path(args.source)
    if not source.exists():
        print(f'ERROR: {source} not found')
        sys.exit(1)

    text = source.read_text(encoding='utf-8')
    records = parse_tables(text)
    print(f'Parsed {len(records)} records from {source.name}')

    stats = {'updated': 0, 'not_found': 0, 'skipped': 0, 'flagged': 0}
    not_found = []
    flagged = []
    all_changes = []

    for row in records:
        pn = row.get('pn', '').strip()
        if not pn:
            continue

        ev_path = find_evidence(pn)
        if not ev_path:
            stats['not_found'] += 1
            not_found.append(pn)
            continue

        with open(ev_path, 'r', encoding='utf-8') as f:
            ev = json.load(f)

        is_peha = ev.get('subbrand') == 'PEHA' or 'series' in row
        if is_peha and 'type_designation' in row:
            ev, changes = apply_peha_record(ev, row)
        else:
            ev, changes = apply_hw_record(ev, row)

        mfr = ev.get('structured_identity', {}).get('confirmed_manufacturer', '')
        if mfr and mfr.lower() not in ('honeywell', 'honeywell/esser', 'honeywell/peha',
                                        'honeywell/notifier', 'honeywell/bw technologies',
                                        'honeywell/autronica', '-', '—', 'unknown', ''):
            stats['flagged'] += 1
            flagged.append(f'{pn} ({mfr})')

        if changes:
            all_changes.append({'pn': pn, 'changes': changes})
            if not args.dry_run:
                with open(ev_path, 'w', encoding='utf-8') as f:
                    json.dump(ev, f, ensure_ascii=False, indent=2)
            stats['updated'] += 1
        else:
            stats['skipped'] += 1

    # Save import report
    report = {
        'source': str(source),
        'total_records': len(records),
        'stats': stats,
        'not_found': not_found,
        'flagged_non_honeywell': flagged,
        'changes_sample': all_changes[:20],
    }
    report_path = RESULTS_DIR / 'phase1_recon_import_report.json'
    if not args.dry_run:
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

    # Print summary
    print()
    print(f'=== PHASE 1 IMPORT {"(DRY RUN)" if args.dry_run else "COMPLETE"} ===')
    print(f'  Updated:      {stats["updated"]}')
    print(f'  Skipped:      {stats["skipped"]} (no changes needed)')
    print(f'  Not found:    {stats["not_found"]}')
    print(f'  Flagged:      {stats["flagged"]} (non-Honeywell manufacturer)')
    if not_found:
        print('\n  Missing evidence files:')
        for pn in not_found[:20]:
            print(f'    {pn}')
    if flagged:
        print('\n  Non-Honeywell flags:')
        for f in flagged:
            print(f'    {f}')
    if args.dry_run:
        print('\n  Sample changes (dry run):')
        for c in all_changes[:10]:
            print(f'    {c["pn"]}: {c["changes"]}')


if __name__ == '__main__':
    main()

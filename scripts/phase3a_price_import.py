"""Import Phase 3A GPT Think price results into evidence files.

Reads a text file containing one or more concatenated JSON arrays.
Merges results into evidence: phase3a_price block + updates normalized.best_price.

Usage:
    python scripts/phase3a_price_import.py --input C:/Users/eugene/Downloads/GPT.txt [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

EVIDENCE_DIR = Path('downloads/evidence')

CONF_RANK = {'high': 3, 'medium': 2, 'low': 1}

# These PNs had confirmed bad price sources — force-replace normalized even if price_contract exists
BAD_SOURCE_PNS = {'171411', '1006186', '183791', '184791'}


def extract_url(raw: str) -> str:
    """Strip markdown link syntax [text](url) → url, or return as-is."""
    if not raw:
        return ''
    m = re.search(r'\]\((https?://[^\)]+)\)', raw)
    if m:
        return m.group(1)
    if raw.startswith('http'):
        return raw
    return ''


def parse_file(path: Path) -> list[dict]:
    """Parse file containing one or more concatenated JSON arrays."""
    text = path.read_text(encoding='utf-8')
    # Split on array boundaries: find all [...] blocks
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
                    results.extend(arr)
                except json.JSONDecodeError as e:
                    print(f'  WARN: JSON parse error in chunk at pos {start}: {e}')
                start = None
    return results


def deduplicate(records: list[dict]) -> dict[str, dict]:
    """For duplicate PNs, keep the highest-confidence result with a price."""
    best: dict[str, dict] = {}
    for r in records:
        pn = r.get('pn', '').strip()
        if not pn:
            continue
        price = r.get('price')
        if price is None:
            # Only keep not_found if we have nothing else
            if pn not in best:
                best[pn] = r
            continue
        existing = best.get(pn)
        if existing is None or existing.get('price') is None:
            best[pn] = r
        else:
            # Both have price — keep higher confidence
            ec = CONF_RANK.get(existing.get('confidence', 'low'), 0)
            nc = CONF_RANK.get(r.get('confidence', 'low'), 0)
            if nc > ec:
                best[pn] = r
    return best


def find_evidence_file(pn: str) -> Path | None:
    """Find evidence file for a given PN."""
    # Direct match
    direct = EVIDENCE_DIR / f'evidence_{pn}.json'
    if direct.exists():
        return direct
    # Try with slash replaced by dash or underscore (e.g., L-VOM40A/EN → L-VOM40A_EN)
    for ch in ('-', '_'):
        alt = EVIDENCE_DIR / f'evidence_{pn.replace("/", ch)}.json'
        if alt.exists():
            return alt
    return None


def import_results(records: dict[str, dict], dry_run: bool) -> None:
    found = 0
    skipped_not_found = 0
    skipped_no_file = 0
    updated = 0
    price_updated = 0

    for pn, r in sorted(records.items()):
        ev_path = find_evidence_file(pn)

        if ev_path is None:
            print(f'  NO FILE: {pn}')
            skipped_no_file += 1
            continue

        found += 1
        price = r.get('price')
        unit_basis = r.get('unit_basis', 'not_found')

        if price is None or unit_basis == 'not_found':
            skipped_not_found += 1
            print(f'  NOT FOUND: {pn} — {r.get("notes", "")}')
            continue

        ev = json.loads(ev_path.read_text(encoding='utf-8'))
        pn_in_ev = ev.get('pn', pn)

        source_url = extract_url(r.get('source_url', ''))
        confidence = r.get('confidence', 'low')
        currency = r.get('currency', '')
        notes = r.get('notes', '')
        search_used = r.get('search_used', '')

        # Write phase3a_price block
        ev['phase3a_price'] = {
            'price': price,
            'currency': currency,
            'unit_basis': unit_basis,
            'source_url': source_url,
            'confidence': confidence,
            'notes': notes,
            'search_used': search_used,
        }

        # Update normalized.best_price if:
        # - current source is 'our_estimate' (own ref price) or missing
        # - AND this is a unit price (not pack) OR there's no alternative
        # - AND confidence is not low (or no price at all currently)
        norm = ev.setdefault('normalized', {})
        current_src = norm.get('best_price_source', '')
        current_price = norm.get('best_price')

        force_update = pn_in_ev in BAD_SOURCE_PNS or pn in BAD_SOURCE_PNS
        should_update_norm = (
            (force_update or not current_price or current_src in ('our_estimate', ''))
            and unit_basis == 'unit'
            and confidence in ('high', 'medium')
        )

        if should_update_norm:
            norm['best_price'] = price
            norm['best_price_currency'] = currency
            norm['best_price_source'] = 'phase3a'
            norm['best_price_url'] = source_url
            price_updated += 1
            price_flag = ' → normalized updated'
        else:
            price_flag = f' (norm kept: src={current_src}, price={current_price})'

        print(f'  OK: {pn_in_ev} | {price} {currency} | {unit_basis} | conf={confidence}{price_flag}')

        if not dry_run:
            ev_path.write_text(json.dumps(ev, indent=2, ensure_ascii=False), encoding='utf-8')
        updated += 1

    print()
    print(f'Results: {found} evidence files found')
    print(f'  Updated: {updated}')
    print(f'  Normalized price updated: {price_updated}')
    print(f'  Not found (no price): {skipped_not_found}')
    print(f'  No evidence file: {skipped_no_file}')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, help='Path to GPT Think results file')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f'ERROR: File not found: {input_path}')
        sys.exit(1)

    print(f'Parsing: {input_path}')
    records = parse_file(input_path)
    print(f'Total records parsed: {len(records)}')

    deduped = deduplicate(records)
    print(f'Unique PNs: {len(deduped)}')
    print(f'Dry run: {args.dry_run}')
    print()

    import_results(deduped, args.dry_run)


if __name__ == '__main__':
    main()

"""Generate Phase 3A Price Search prompts for GPT Think.

Phase 3A goal: find current market price per unit.
Targets: SKUs with no normalized.best_price OR known bad price sources.

Usage:
    python scripts/_gen_phase3a_prompts.py [--dry-run]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

EVIDENCE_DIR = Path('downloads/evidence')
OUT_DIR = Path('research_queue/dr_prompts/phase3a_price')
OUT_DIR.mkdir(parents=True, exist_ok=True)

# SKUs where dr_price came from wrong sources — must reprice
BAD_SOURCE_PNS = {'171411', '1006186', '183791', '184791'}

BATCH_SIZE = 20


def collect_targets() -> list[dict]:
    targets = []
    for f in sorted(os.listdir(EVIDENCE_DIR)):
        if not f.startswith('evidence_') or not f.endswith('.json'):
            continue
        with open(EVIDENCE_DIR / f, encoding='utf-8') as fh:
            ev = json.load(fh)

        pn = ev.get('pn', '')
        if not pn or pn in ['PN', '_'] or set(pn) <= set('-_'):
            continue

        norm = ev.get('normalized', {})
        bp = norm.get('best_price')
        si = ev.get('structured_identity', {})

        needs_price = not bp
        needs_our_estimate = bp and norm.get('best_price_source') == 'our_estimate'
        needs_reprice = pn in BAD_SOURCE_PNS

        if not needs_price and not needs_our_estimate and not needs_reprice:
            continue

        mfr = si.get('confirmed_manufacturer') or ev.get('brand') or 'unknown'
        real_model = si.get('real_model', '')
        search_hint = si.get('search_hint', '')
        type_des = si.get('type_designation', '')
        our_price = ev.get('our_price_raw', '')
        subbrand = ev.get('subbrand', '')
        title = ev.get('assembled_title', '') or ''
        # strip garbled bytes
        try:
            title.encode('utf-8')
        except Exception:
            title = ''

        # Build search term: type_designation > real_model > pn
        if type_des and type_des not in ('-', 'unconfirmed'):
            search_term = type_des
        elif real_model and real_model not in ('-', 'UNRESOLVABLE', ''):
            search_term = real_model
        else:
            search_term = pn

        fallback = search_hint if search_hint else '-'

        targets.append({
            'pn': pn,
            'mfr': mfr,
            'search_term': search_term,
            'fallback': fallback,
            'our_price': our_price,
            'subbrand': subbrand,
            'needs_reprice': needs_reprice,
            'needs_our_estimate': needs_our_estimate,
            'title': title[:60] if title else '',
        })
    return targets


def make_prompt(skus: list[dict], batch_num: int, total: int) -> str:
    rows = []
    for i, s in enumerate(skus, 1):
        if s['needs_reprice']:
            flag = ' ⚠ REPRICE'
        elif s['needs_our_estimate']:
            flag = f" (our ref: {s['our_price']} RUB)"
        else:
            flag = ''
        rows.append(
            f"| {i} | {s['pn']} | {s['mfr']} | {s['search_term']} | {s['fallback']} | {s['our_price']} |{flag}"
        )
    table = '\n'.join(rows)

    peha_present = any(s['subbrand'] == 'PEHA' for s in skus)
    peha_block = ''
    if peha_present:
        peha_block = """
## PEHA unit-price rules (mandatory)
- Search on: watt24.com, pehastore.de, heiz24.de, elektroversand-schmidt.de, alles-mit-stecker.de
- AVOID for price: Conrad.at, Voelkner.de, computersalg.de — they sell in PACKS (5 St. / 10 St.)
- If Conrad/Voelkner is only source: note pack size, divide price, return unit price
- 1-gang frame (D 20.671.xxx): typical unit price 5-20 EUR
- Combination/multi-gang frame (D 20.574.xxx): typical unit price 15-60 EUR
- ⚠ REPRICE rows: prior price was from wrong URL (government PDF, wrong product) — ignore it
"""

    return f"""# Phase 3A — Price Search (batch {batch_num}/{total})

## Your role
You are an experienced industrial equipment buyer. You have web access and know how to find
real market prices — not list prices, not distributor catalogs, not government PDFs.
{peha_block}
## Task
Find the current market price (single unit, today) for each SKU below.

Search strategy per row:
- "Search Term" = use this as primary search query
- "Fallback" = if Search Term gives no results, use this
- "Manufacturer" = always include in search, never substitute

## {len(skus)} SKUs (batch {batch_num}/{total})

| # | PN | Manufacturer | Search Term | Fallback | Our ref price (RUB) |
|---|----|----|----|----|---|
{table}

## Required output — JSON array only, no prose

```json
[
  {{
    "pn": "CATALIST",
    "search_used": "Cisco Catalyst 3850",
    "price": 850.00,
    "currency": "USD",
    "unit_basis": "unit",
    "source_url": "https://example.com/...",
    "confidence": "high",
    "notes": ""
  }}
]
```

Field rules:
- price: number only, no currency symbols
- currency: USD / EUR / GBP / RUB
- unit_basis: "unit" | "pack:N" (e.g. "pack:5") | "rfq_only" | "not_found"
- If pack: unit_basis = "pack:5", price = ALREADY divided by N (unit price)
- confidence: "high" | "medium" | "low"
- source_url: exact product page URL, not search result, not PDF, not homepage
- Return null price + "not_found" unit_basis if genuinely unavailable
- Return the JSON array only — no explanation, no markdown outside the code block
"""


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    targets = collect_targets()
    if not targets:
        print('No targets found — all SKUs have price or no price needed.')
        return

    print(f'Phase 3A targets: {len(targets)} SKUs')
    print(f'  No price: {sum(1 for t in targets if not t["needs_reprice"] and not t["needs_our_estimate"])}')
    print(f'  Our estimate only (need market price): {sum(1 for t in targets if t["needs_our_estimate"])}')
    print(f'  Reprice (bad source): {sum(1 for t in targets if t["needs_reprice"])}')
    print()

    import math
    total = math.ceil(len(targets) / BATCH_SIZE)
    for i in range(total):
        chunk = targets[i * BATCH_SIZE:(i + 1) * BATCH_SIZE]
        prompt = make_prompt(chunk, i + 1, total)
        fname = OUT_DIR / f'gpt_think_batch{i+1}_{len(chunk)}skus.txt'
        if args.dry_run:
            print(f'[DRY RUN] Would write: {fname.name} ({len(prompt)} chars)')
            continue
        fname.write_text(prompt, encoding='utf-8')
        print(f'Wrote: {fname.name}')

    manifest = {
        'phase': '3A',
        'purpose': 'Price Search — current market price per unit. NOT market recon.',
        'model': 'GPT Think (o1, NOT thinking ext)',
        'total_skus': len(targets),
        'total_batches': total,
        'batch_size': BATCH_SIZE,
        'targets_no_price': sum(1 for t in targets if not t['needs_reprice'] and not t['needs_our_estimate']),
        'targets_our_estimate': sum(1 for t in targets if t['needs_our_estimate']),
        'targets_reprice': sum(1 for t in targets if t['needs_reprice']),
        'next_phase': 'Phase 3B — Content (Opus ext) for specs/description/category',
    }
    if not args.dry_run:
        (OUT_DIR / 'manifest.json').write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8'
        )
        print(f'\nTotal: {total} batch(es). Manifest written.')


if __name__ == '__main__':
    main()

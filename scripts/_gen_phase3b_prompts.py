"""Generate Phase 3B Content prompts for Claude DR (Opus with web access).

Phase 3B goal: fill content gaps — photo URL, category, description (where wrong/missing).
Targets: SKUs with no photo, no category, or bad/hallucinated description.

Usage:
    python scripts/_gen_phase3b_prompts.py [--dry-run]
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

EVIDENCE_DIR = Path('downloads/evidence')
OUT_DIR = Path('research_queue/dr_prompts/phase3b_content')
OUT_DIR.mkdir(parents=True, exist_ok=True)

PEHA_BATCH = 25
MIXED_BATCH = 25
MIN_BATCH_SIZE = 5  # merge last chunk if smaller than this into the previous batch

# Descriptions matching these patterns are wrong/hallucinated — need rewrite
BAD_DESC_PATTERNS = [
    'вентиль', 'термостатический вентиль', 'датчик давления',
    'модуль mp3', 'радиоприемник для приема',
]

CANONICAL_CATEGORIES = [
    # PEHA electrical accessories
    'PEHA AURA frame', 'PEHA NOVA frame', 'PEHA DIALOG frame',
    'PEHA COMPACTA frame', 'PEHA frame', 'PEHA rocker switch',
    'PEHA push button', 'PEHA insert', 'PEHA socket',
    'PEHA electrical accessory',
    # Generic electrical
    'switch frame', 'rocker switch', 'rocker cover (wippe)',
    'socket insert (SCHUKO)', 'socket cover plate', 'cover plate',
    'blank plate', 'blanking cover',
    # Cable / fiber
    'fiber pigtail', 'fiber patch cable', 'fiber patch panel',
    'cable', 'wire duct / raceway',
    # Small components
    'fuse', 'terminal', 'terminal block',
    # PPE
    'earplugs (PPE)', 'hearing protection',
    # Fire safety
    'fire detector', 'detector base', 'PA speaker', 'Esser transponder',
    # HVAC
    'valve', 'valve actuator', 'actuator', 'thermostat',
    # IT / computing
    'monitor', 'workstation', 'media converter', 'network switch',
    'printer', 'scanner', 'server', 'IP phone',
    # Automation / instrumentation
    'PLC module', 'HMI panel', 'sensor', 'transmitter', 'controller',
    'power supply', 'relay', 'scanner / barcode reader',
    # Other
    'other',
]


def is_bad_description(desc: str) -> bool:
    d = desc.lower()
    return len(desc) < 150 or any(p in d for p in BAD_DESC_PATTERNS)


def collect_targets() -> tuple[list[dict], list[dict]]:
    peha_skus = []
    mixed_skus = []

    for f in sorted(os.listdir(EVIDENCE_DIR)):
        if not f.startswith('evidence_') or not f.endswith('.json'):
            continue
        with open(EVIDENCE_DIR / f, encoding='utf-8') as fh:
            ev = json.load(fh)

        pn = ev.get('pn', '')
        if not pn or pn in ['PN', '_'] or set(pn) <= set('-_'):
            continue

        norm = ev.get('normalized', {})
        desc = norm.get('best_description', '')
        photo = norm.get('best_photo_url', '')
        category = ev.get('product_category', '') or ev.get('dr_category', '')
        si = ev.get('structured_identity', {})

        needs_photo = not photo
        needs_category = not category
        needs_desc = is_bad_description(desc)

        if not needs_photo and not needs_category and not needs_desc:
            continue

        mfr = si.get('confirmed_manufacturer') or ev.get('brand') or 'unknown'
        real_model = si.get('real_model', '')
        type_des = si.get('type_designation', '')
        our_price = ev.get('our_price_raw', '')
        subbrand = ev.get('subbrand', '')
        title = ev.get('assembled_title', '') or ''

        # Build search term
        if type_des and type_des not in ('-', 'unconfirmed'):
            search_term = type_des
        elif real_model and real_model not in ('-', 'UNRESOLVABLE', ''):
            search_term = real_model
        else:
            search_term = pn

        gaps = []
        if needs_photo:
            gaps.append('photo')
        if needs_category:
            gaps.append('category')
        if needs_desc:
            gaps.append('description')

        row = {
            'pn': pn,
            'mfr': mfr,
            'search_term': search_term,
            'title': title[:60],
            'our_price': our_price,
            'subbrand': subbrand,
            'gaps': gaps,
            'needs_photo': needs_photo,
            'needs_category': needs_category,
            'needs_desc': needs_desc,
        }

        if subbrand == 'PEHA':
            peha_skus.append(row)
        else:
            mixed_skus.append(row)

    return peha_skus, mixed_skus


def make_prompt(skus: list[dict], batch_num: int, total: int, brand_type: str) -> str:
    rows = []
    for i, s in enumerate(skus, 1):
        gap_str = '+'.join(s['gaps'])
        rows.append(
            f"| {i} | {s['pn']} | {s['mfr']} | {s['search_term']} | {gap_str} |"
        )
    table = '\n'.join(rows)
    cats_str = '\n'.join(f'  - {c}' for c in CANONICAL_CATEGORIES)

    peha_note = ''
    if brand_type == 'PEHA':
        peha_note = """
## PEHA search rules
- Primary search: type designation (D 20.xxx.xxx) on pehastore.de, watt24.com, heiz24.de
- Photo: prefer manufacturer site (peha.de) or pehastore.de — direct .jpg/.png/.webp URL
- Category: use "PEHA NOVA frame", "PEHA AURA frame", "PEHA DIALOG frame", etc.
"""

    return f"""# Phase 3B — Content Enrichment ({brand_type}, batch {batch_num}/{total})

## Your role
You are a product content specialist. You have web access. For each SKU:
1. Find a direct photo URL (not a page — a .jpg/.png/.webp image URL)
2. Assign a product category from the canonical list below
3. Write/fix a Russian description ONLY if flagged as "description" in the Gaps column
{peha_note}
## Canonical categories (pick the best match):
{cats_str}

## {len(skus)} SKUs — gaps to fill

| # | PN | Manufacturer | Search Term | Gaps |
|---|----|----|----|----|
{table}

## Required output — JSON array only

```json
[
  {{
    "pn": "171411",
    "photo_url": "https://cdn.pehastore.de/images/171411_large.jpg",
    "category": "PEHA AURA frame",
    "description_ru": null
  }}
]
```

Field rules:
- photo_url: direct image URL (ends in .jpg/.png/.webp/.gif) or null if not found
- category: exact string from canonical list above, or null if truly uncategorizable
- description_ru: 100-200 word Russian description ONLY if "description" is in Gaps; \
otherwise null
- Do NOT write description_ru for SKUs not flagged with "description" gap
- Return ONLY the JSON array — no prose, no markdown outside the code block
"""


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    peha_skus, mixed_skus = collect_targets()
    total = len(peha_skus) + len(mixed_skus)

    print(f'Phase 3B targets: {total} SKUs')
    print(f'  PEHA: {len(peha_skus)}, Mixed: {len(mixed_skus)}')

    def make_chunks_divisible_by_3(items: list, max_size: int) -> list[list]:
        """Split items into N chunks where N is divisible by 3, max chunk size <= max_size."""
        if not items:
            return []
        min_batches = math.ceil(len(items) / max_size)
        # Round up to nearest multiple of 3
        n = math.ceil(min_batches / 3) * 3
        size = math.ceil(len(items) / n)
        chunks = [items[i:i + size] for i in range(0, len(items), size)]
        return chunks

    peha_chunks = make_chunks_divisible_by_3(peha_skus, PEHA_BATCH)
    mixed_chunks = make_chunks_divisible_by_3(mixed_skus, MIXED_BATCH)
    total_peha = len(peha_chunks)
    total_mixed = len(mixed_chunks)

    for i, chunk in enumerate(peha_chunks):
        prompt = make_prompt(chunk, i + 1, total_peha, 'PEHA')
        fname = OUT_DIR / f'opus_peha_batch{i+1}_{len(chunk)}skus.txt'
        if args.dry_run:
            print(f'[DRY RUN] Would write: {fname.name}')
            continue
        fname.write_text(prompt, encoding='utf-8')
        print(f'Wrote: {fname.name}')

    for i, chunk in enumerate(mixed_chunks):
        prompt = make_prompt(chunk, i + 1, total_mixed, 'Mixed')
        fname = OUT_DIR / f'opus_mixed_batch{i+1}_{len(chunk)}skus.txt'
        if args.dry_run:
            print(f'[DRY RUN] Would write: {fname.name}')
            continue
        fname.write_text(prompt, encoding='utf-8')
        print(f'Wrote: {fname.name}')

    manifest = {
        'phase': '3B',
        'purpose': 'Content — photo URL, category, description fix. NOT price search.',
        'model': 'Claude DR (Opus with web access)',
        'total_skus': total,
        'peha_skus': len(peha_skus),
        'mixed_skus': len(mixed_skus),
        'total_batches': total_peha + total_mixed,
        'gaps': {
            'no_photo': sum(1 for s in peha_skus + mixed_skus if s['needs_photo']),
            'no_category': sum(1 for s in peha_skus + mixed_skus if s['needs_category']),
            'bad_desc': sum(1 for s in peha_skus + mixed_skus if s['needs_desc']),
        },
    }
    if not args.dry_run:
        (OUT_DIR / 'manifest.json').write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8'
        )
        print(f'\nTotal: {total_peha + total_mixed} batches. Manifest written.')


if __name__ == '__main__':
    main()

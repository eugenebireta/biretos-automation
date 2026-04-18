"""Generate Phase 1 Identity Recon prompts for Haiku."""
import json
import os
import sys
import math
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

EVIDENCE_DIR = Path('downloads/evidence')
OUT_DIR = Path('research_queue/dr_prompts/phase1_recon')
PEHA_BATCH_SIZE = 25
HW_BATCH_SIZE = 30

peha_skus = []
hw_skus = []

for f in sorted(os.listdir(EVIDENCE_DIR)):
    if not f.startswith('evidence_') or not f.endswith('.json'):
        continue
    with open(EVIDENCE_DIR / f, 'r', encoding='utf-8') as fh:
        ev = json.load(fh)

    pn = ev.get('pn', '')
    if not pn or pn in ['PN', '_'] or set(pn) <= set('-_'):
        continue

    dr = ev.get('deep_research', {})
    has_price = bool(ev.get('dr_price'))
    has_photo = bool(ev.get('dr_image_url'))
    has_desc = bool(dr.get('description_ru') if dr else False)
    has_dr = bool(dr and len(dr) > 2)

    if not has_dr or not has_price or not has_photo or not has_desc:
        gaps = []
        if not has_dr:
            gaps.append('no_dr')
        if not has_price:
            gaps.append('no_price')
        if not has_photo:
            gaps.append('no_photo')
        if not has_desc:
            gaps.append('no_desc')

        row = {
            'pn': pn,
            'title': ev.get('assembled_title', ''),
            'seed': ev.get('content', {}).get('seed_name', ''),
            'variants': ev.get('pn_variants', []),
            'gaps': gaps,
        }
        if ev.get('subbrand') == 'PEHA':
            peha_skus.append(row)
        else:
            hw_skus.append(row)

OUT_DIR.mkdir(parents=True, exist_ok=True)


def make_peha_prompt(skus, batch_num, total_batches):
    rows = []
    for i, s in enumerate(skus, 1):
        vars_str = ', '.join(s['variants']) if s['variants'] else '-'
        gaps_str = ', '.join(s['gaps'])
        seed = s['seed'][:60] if s['seed'] else '-'
        rows.append(f"| {i} | {s['pn']} | {s['title']} | {seed} | {vars_str} | {gaps_str} |")
    table = '\n'.join(rows)

    return f"""# Phase 1 — Identity Recon: PEHA electrical accessories (batch {batch_num}/{total_batches})

## Your task
Identify each PEHA product and confirm/correct its identity. RECON ONLY — do NOT search for prices or photos.

## PEHA rules
- PEHA is a Honeywell sub-brand for electrical accessories (switches, frames, sockets)
- Products have type designations like **D 20.xxx.xxx** — find the correct one
- Series: NOVA, AURA, DIALOG, COMPACTA, NOVA MEDIA
- Search as "PEHA {{PN}}" — NEVER "Honeywell {{PN}}"
- Sites: peha.de, pehastore.de, voltking.de, elektroversand.de

## What I need per SKU
1. **product_type** — e.g. "frame 1-gang", "socket", "switch insert"
2. **series** — NOVA / AURA / DIALOG / COMPACTA
3. **type_designation** — the D 20.xxx.xxx code (most important!)
4. **color_material** — if variants exist
5. **pn_aliases** — alternative PNs on distributor sites
6. **identity_notes** — discontinued, replaced by, kit contents

## Products ({len(skus)} SKUs)

| # | PN | Our title | Seed name | Known variants | Gaps |
|---|----|-----------|-----------|----------------|------|
{table}

## Required output — markdown table only

| PN | product_type | series | type_designation | color_material | pn_aliases | identity_notes |
|----|-------------|--------|-----------------|----------------|-----------|----------------|

- Cannot confirm → write "unconfirmed" in type_designation
- Return ONLY the table, no preamble
"""


def make_hw_prompt(skus, batch_num, total_batches):
    rows = []
    for i, s in enumerate(skus, 1):
        vars_str = ', '.join(s['variants']) if s['variants'] else '-'
        gaps_str = ', '.join(s['gaps'])
        seed = s['seed'][:60] if s['seed'] else '-'
        rows.append(f"| {i} | {s['pn']} | {s['title']} | {seed} | {vars_str} | {gaps_str} |")
    table = '\n'.join(rows)

    return f"""# Phase 1 — Identity Recon: Honeywell products (batch {batch_num}/{total_batches})

## Your task
Identify each product and confirm/correct its identity. RECON ONLY — do NOT search for prices or photos.

## Search rules
- Search as "Honeywell {{PN}}" or just "{{PN}}" in quotes
- Suffix -RU: try without suffix too (Russian market variant)
- Suffix -L3: kit — search base PN without suffix
- Sites: honeywellsensors.com, distech-controls.com, automation24.com, rs-components.com

## What I need per SKU
1. **product_type** — short English name: "smoke detector", "HVAC sensor", "gas detector"
2. **product_line** — family/series name
3. **manufacturer** — confirm Honeywell or identify real OEM
4. **pn_aliases** — alternative PNs on distributor sites
5. **discontinued** — yes/no
6. **identity_notes** — OEM info, replaced by, kit contents, regional variant

## Products ({len(skus)} SKUs)

| # | PN | Our title | Seed name | Known variants | Gaps |
|---|----|-----------|-----------|----------------|------|
{table}

## Required output — markdown table only

| PN | product_type | product_line | manufacturer | pn_aliases | discontinued | identity_notes |
|----|-------------|-------------|-------------|-----------|-------------|----------------|

- Cannot confirm → write "unknown" in product_type
- manufacturer: "Honeywell" only if confirmed, else real OEM name
- Return ONLY the table, no preamble
"""


# Generate PEHA batches
total_peha = math.ceil(len(peha_skus) / PEHA_BATCH_SIZE)
for i in range(total_peha):
    chunk = peha_skus[i*PEHA_BATCH_SIZE:(i+1)*PEHA_BATCH_SIZE]
    prompt = make_peha_prompt(chunk, i+1, total_peha)
    fname = OUT_DIR / f'haiku_peha_batch{i+1}_{len(chunk)}skus.txt'
    fname.write_text(prompt, encoding='utf-8')
    print(f'Wrote: {fname.name}')

# Generate Honeywell batches
total_hw = math.ceil(len(hw_skus) / HW_BATCH_SIZE)
for i in range(total_hw):
    chunk = hw_skus[i*HW_BATCH_SIZE:(i+1)*HW_BATCH_SIZE]
    prompt = make_hw_prompt(chunk, i+1, total_hw)
    fname = OUT_DIR / f'haiku_honeywell_batch{i+1}_{len(chunk)}skus.txt'
    fname.write_text(prompt, encoding='utf-8')
    print(f'Wrote: {fname.name}')

# Save manifest
manifest = {
    'phase': 1,
    'purpose': 'Identity Recon — product_type, series, type_designation, aliases. NO prices, NO photos.',
    'model': 'claude-haiku-4-5',
    'total_skus': len(peha_skus) + len(hw_skus),
    'peha_skus': len(peha_skus),
    'hw_skus': len(hw_skus),
    'peha_batches': total_peha,
    'hw_batches': total_hw,
    'total_batches': total_peha + total_hw,
    'next_phase': 'Phase 2 — Market Recon (unit vs pack, dangerous distributors)'
}
(OUT_DIR / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'\nTotal: {total_peha + total_hw} batches ({total_peha} PEHA + {total_hw} Honeywell)')
print(f'PEHA: {len(peha_skus)} SKUs in {total_peha} batches')
print(f'Honeywell: {len(hw_skus)} SKUs in {total_hw} batches')

"""Build 3 rich Claude Deep Research batches for multi-field enrichment.

Max-coverage DR task: for each SKU, return **complete enrichment** record
with EAN + price + weight + dims + photo + corrected datasheet URL. Uses
priority tags (P1 no-price, P2 wrong-datasheet, P3 no-EAN) so DR prioritizes
business-blocking gaps first.

Replaces EAN-only batches at research_queue/dr_prompts/ean_2026-04-18/.
"""
from __future__ import annotations
import json
import io
import sys
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
TARGETS_FILE = ROOT / "_scratchpad" / "dr_enrichment_targets.json"
OUT_DIR = ROOT / "research_queue" / "dr_prompts" / "enrichment_2026-04-18"

PROMPT_TEMPLATE = """# DR Batch ENRICH-{batch_num}/3 — Biretos Multi-Field Enrichment — {date}

**TASK:** For each SKU below, find missing product data from authoritative web sources.
Return a single JSON array — one object per SKU, preserving input order.

## Output schema (strict)
```json
[
  {{
    "pn": "<exact PN from input>",
    "ean": "<13 digits EAN-13, or null if not found; checksum must pass>",
    "ean_source_url": "<URL of page where EAN was seen>",
    "ean_confidence": "high | medium | low | null",
    "price_eur": "<numeric EUR price if found, or null>",
    "price_source_url": "<URL>",
    "price_confidence": "high | medium | low | null",
    "photo_url": "<direct image URL, https, or null>",
    "photo_source_page": "<URL of product page where photo was found>",
    "weight_g": "<integer grams if found, or null>",
    "weight_source_url": "<URL>",
    "dimensions_mm": "<LxWxH in mm, e.g. 120x80x45, or null>",
    "dimensions_source_url": "<URL>",
    "corrected_datasheet_url": "<URL to correct product datasheet PDF if flagged wrong_datasheet>",
    "notes": "<short English note: anything noteworthy, conflicts, or why fields null>"
  }},
  ...
]
```

Return **only** the JSON array — no prose before or after.

## Priority interpretation (per-SKU tags)

Each SKU has one or more of:
- `P1_NO_PRICE`  — critical: InSales catalog launch blocked without this price. ALWAYS return price if findable.
- `P2_WRONG_DATASHEET`  — our current PDF is a generic catalog / report / not a product datasheet. Find correct product-specific datasheet URL. Without this, other fields are unreliable — prioritize finding right datasheet FIRST, then extract fields from it.
- `P3_NO_EAN`  — need 13-digit EAN for Ozon/WB marketplace listing.

**If a SKU has multiple tags, address all.** If only P3_NO_EAN, still fill price/weight/dims if trivially findable (same page). Don't chase fields with low ROI.

## Source priority

### Tier 1 (accept as `high` confidence) — manufacturer + top component distributors
`honeywell.com`, `esser-systems.com`, `dkc.ru`, `dkc.eu`, `dell.com`, `hp.com`, `weidmuller.com`, `phoenixcontact.com`, `siemon.com`, `notifier.com`, `howardleight.com`, `peha.com`, `mouser.com`, `digikey.com`, `farnell.com`, `rs-online.com`, `arrow.com`, `newark.com`.

### Tier 2 (accept as `medium`)
`adiglobal.com`, `voltking.de`, `rtexpress.ru`, `elec.ru`, `energopostachbud.com`, `roteiv-shop.de`, `mytub.co.uk` and similar authorized distributors.

### REJECT (never use)
`ebay.com`, `amazon.com`, `aliexpress.com`, `avito.ru`, `ozon.ru`, `wildberries.ru`, Chinese marketplaces, seller aggregators.

## Rules

### EAN validation
- Must be exactly 13 digits. Must pass EAN-13 mod-10 checksum.
- 2+ tier-1 sources agree → `ean_confidence: "high"`
- 1 tier-1 source → `medium`
- Only tier-2 → `medium`
- Fail checksum → return null with `notes: "checksum_fail"`
- Conflict between sources → null with `notes: "conflict: X vs Y"`

### Price
- Prefer manufacturer list price when available (`dell.com`, `honeywell.com`).
- Distributor prices acceptable (`mouser.com`, `rs-online.com`, etc.).
- Convert to EUR using current rate (acceptable margin ±5%; note currency in `notes` if converted).
- Reject "quote on request" / login-walled prices.

### Photo
- Must be direct `.jpg/.png/.webp` URL or CDN endpoint.
- Prefer manufacturer-hosted (`honeywell.scene7.com`, `media.dell.com`) or distributor CDN.
- Avoid stock-photo/generic images.

### Weight / dimensions
- From official datasheet or manufacturer product page only.
- Convert units: kg→×1000, cm→×10, lb→×453.592.
- Return null if ambiguous (e.g., "up to 500g" not acceptable).

### Corrected datasheet (for P2_WRONG_DATASHEET only)
- Search `"<brand> <pn> datasheet pdf" site:<manufacturer-domain>`.
- Verify the PDF contains the exact PN as product.
- Do NOT return catalog/brochure/NASA-report/journal URLs — only product-specific datasheet.
- If none found, `corrected_datasheet_url: null, notes: "no_product_datasheet_exists"`.

### Anti-hallucination (critical)
- Never invent values from patterns. Each field needs an actual source URL.
- If multiple conflicting values → return null with reason, not a guess.
- Max 5 Google queries per SKU; if still not found, fields = null.
- For Honeywell sub-brands (Esser, System Sensor, Notifier, Morley-IAS, PEHA) — search using the sub-brand name, not "Honeywell".

## SKUs to process ({sku_count} items)

| # | PN | Brand | Tags | Series | Title (trimmed) |
|---|----|-------|------|--------|-----------------|
{sku_table}

---

**Reminder:** return only a JSON array conforming to the schema above. One object per SKU, preserving input order. Missing/not-found fields → `null` with explanatory `notes`. Never fabricate."""


def main():
    targets = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    # Sort: P1 first (blockers), then P2, then P3. Within each, alphabetical PN.
    def sort_key(t):
        tags = t["tags"]
        tier = 0 if "P1_NO_PRICE" in tags else (1 if "P2_WRONG_DATASHEET" in tags else 2)
        return (tier, t["pn"])
    targets.sort(key=sort_key)

    # Split into 3 balanced-count batches
    per_batch = (len(targets) + 2) // 3
    batches = [targets[i*per_batch:(i+1)*per_batch] for i in range(3)]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")

    for i, batch in enumerate(batches, 1):
        rows = []
        for j, sku in enumerate(batch, 1):
            tags = ",".join(sku["tags"])
            title = (sku["title"] or "").replace("|", "/").replace("\n", " ")[:60]
            series = (sku["series"] or "").replace("|", "/")[:30]
            rows.append(f"| {j} | `{sku['pn']}` | {sku['brand']} | {tags} | {series or '-'} | {title or '-'} |")
        sku_table = "\n".join(rows)

        prompt = PROMPT_TEMPLATE.format(
            batch_num=i,
            date=date,
            sku_count=len(batch),
            sku_table=sku_table,
        )
        out_file = OUT_DIR / f"batch_{i}.md"
        out_file.write_text(prompt, encoding="utf-8")
        p1 = sum(1 for s in batch if "P1_NO_PRICE" in s["tags"])
        p2 = sum(1 for s in batch if "P2_WRONG_DATASHEET" in s["tags"])
        p3 = sum(1 for s in batch if "P3_NO_EAN" in s["tags"])
        print(f"Wrote {out_file}  ({len(batch)} SKUs:  P1={p1}  P2={p2}  P3={p3}, {len(prompt)} chars)")


if __name__ == "__main__":
    main()

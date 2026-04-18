"""Generate 3 parallel Claude Deep Research prompts for EAN closure.

Input:  research_queue/dr_prompts/ean_2026-04-18/_sku_batches.json (3 groups of 83)
Output: batch_{1,2,3}.md — copy-paste-ready prompts for Claude DR UI

Rules (from KNOW_HOW):
- Trusted sources first (manufacturer, mouser, digikey, farnell, rs, arrow)
- No Gemini (fabricates EANs)
- Strict JSON output with checksum-validated 13-digit EAN
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
BATCHES_FILE = ROOT / "research_queue" / "dr_prompts" / "ean_2026-04-18" / "_sku_batches.json"
OUT_DIR = ROOT / "research_queue" / "dr_prompts" / "ean_2026-04-18"
LOG_FILE = ROOT / "downloads" / "DR_BATCH_LOG.json"

PROMPT_TEMPLATE = """# DR Batch EAN-{batch_num}/3 — Biretos Catalog — {date}

**TASK:** find the 13-digit EAN/GTIN barcode for each SKU below. Return a single JSON array.

## Output schema (strict)
```json
[
  {{
    "pn": "<exact PN from input>",
    "ean": "<13 digits, or null if not found>",
    "ean_source_url": "<URL of source page, or null>",
    "confidence": "high | medium | low | null",
    "notes": "<short English note>"
  }},
  ...
]
```

Return **only** the JSON array — no prose before or after.

## Rules

### Source priority (tier 1 — accept as `high`)
- manufacturer sites: `honeywell.com`, `esser-systems.com`, `dkc.ru`, `dkc.eu`, `dell.com`, `hp.com`, `weidmuller.com`, `phoenixcontact.com`, `siemon.com`, `notifier.com`
- component distributors: `mouser.com`, `digikey.com`, `farnell.com`, `rs-online.com`, `arrow.com`, `newark.com`
- 2+ tier-1 sources agree → `confidence: "high"`
- 1 tier-1 source → `confidence: "medium"`

### Tier 2 (accept as `medium`)
Authorized distributors: `adiglobal.com`, `voltking.de`, `rtexpress.ru`, `elec.ru`, `energopostachbud.com`.

### REJECT (never return their EAN)
`ebay.com`, `amazon.com`, `aliexpress.com`, `avito.ru`, `ozon.ru`, `wildberries.ru`, random chinese marketplaces, seller aggregators, eBay archives.

### Validation
- EAN must be exactly **13 digits**.
- Must pass **EAN-13 checksum** (mod-10 on weighted sum of first 12 digits).
- If found value fails checksum — treat as not found, return `null` with `notes: "checksum_fail"`.

### Anti-hallucination (critical)
- **Never invent an EAN from a pattern or parent SKU.** If not found on a product page with the exact PN visible, return `null`.
- If two sources disagree → return `ean: null, confidence: "low", notes: "conflict: X on sourceA vs Y on sourceB"`.
- PN variants (`-RU`, color suffix like `.10`, kit suffix like `-L3`): search parent PN first, then variant. If only parent EAN is found, return it with `notes: "parent_pn_ean"`.
- After 3 failed searches → return `ean: null, confidence: null, notes: "not_found"`.

### Search strategy
1. Google `"<brand> <pn>" EAN` and `"<brand> <pn>" GTIN`.
2. Visit top 5 non-rejected domain results.
3. Cross-check on 2nd source if ambiguous.
4. For Honeywell sub-brands (Esser, System Sensor, Notifier, Morley-IAS, PEHA) — search using the sub-brand, not "Honeywell".

## SKUs to process ({sku_count} items)

| PN | Brand | Series | Title (trimmed) |
|----|-------|--------|-----------------|
{sku_table}

---

**Reminder:** return only a JSON array conforming to the schema above. One object per SKU, preserving input order. Missing/not-found → `null` fields with explanatory `notes`. Never fabricate."""


def main():
    batches = json.loads(BATCHES_FILE.read_text(encoding="utf-8"))
    date = datetime.now().strftime("%Y-%m-%d")
    batch_ids = []

    for i, batch in enumerate(batches, 1):
        rows = []
        for sku in batch:
            title = (sku["title"] or "").replace("|", "/").replace("\n", " ")[:80]
            series = (sku["series"] or "").replace("|", "/")[:40]
            brand = sku["brand"] or "?"
            pn = sku["pn"]
            rows.append(f"| `{pn}` | {brand} | {series or '-'} | {title or '-'} |")
        sku_table = "\n".join(rows)

        prompt = PROMPT_TEMPLATE.format(
            batch_num=i,
            date=date,
            sku_count=len(batch),
            sku_table=sku_table,
        )
        out_file = OUT_DIR / f"batch_{i}.md"
        out_file.write_text(prompt, encoding="utf-8")
        print(f"Wrote {out_file}  ({len(batch)} SKUs, {len(prompt)} chars)")

        batch_ids.append({
            "batch_id": f"claude_dr_ean_2026-04-18_b{i}",
            "group_id": "claude_dr_ean_2026-04-18",
            "source": "claude_dr",
            "type": "ean",
            "sku_count": len(batch),
            "status": "PREPARED",
            "file": str(out_file.relative_to(ROOT)).replace("\\", "/"),
        })

    # Log in DR_BATCH_LOG.json
    log = json.loads(LOG_FILE.read_text(encoding="utf-8")) if LOG_FILE.exists() else {"batches": []}
    log.setdefault("batches", []).extend(batch_ids)
    LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nLogged 3 PREPARED entries in {LOG_FILE}")


if __name__ == "__main__":
    main()

# Research Brief — 27711

**Priority:** high | **Reason:** category_mismatch
**Goal:** Close unresolved enrichment gaps for PN 27711 (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Датчик Honeywell D 20.610.022 AT
- Expected Category: Датчик
- Our Price (xlsx): 1318,20

## Questions to Resolve
- What is the correct product category for Honeywell 27711 (Датчик Honeywell D 20.610.022 AT)?
- Is the expected category 'Датчик' correct for this product?
- What similar part numbers exist in the same product family?
- Provide any relevant Russian-language product description for Honeywell 27711

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "strong",
  "photo_verdict": "REJECT",
  "price_status": "category_mismatch_only",
  "price_source_url": "https://www.conrad.fr/fr/p/peha-by-honeywell-cache-cache-27711-1-pc-s-2856187.html",
  "category_mismatch": true,
  "overall_confidence": "VERY_LOW",
  "review_reasons": [
    "IDENTITY_WEAK",
    "CRITICAL_MISMATCH",
    "NO_IMAGE_EVIDENCE",
    "TERMINAL_WEAK_NO_PRICE_LINEAGE",
    "NO_PDF_EVIDENCE"
  ]
}
```

## Constraints
- Use public web evidence only
- Do not use xlsx price as market price
- Do not invent specs if not found
- If uncertain, return ambiguity explicitly
- Prefer exact PN evidence over family-level evidence
- Cite specific URLs for any claim
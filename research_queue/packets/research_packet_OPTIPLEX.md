# Research Brief — OPTIPLEX

**Priority:** low | **Reason:** no_price_lineage
**Goal:** Close unresolved enrichment gaps for PN OPTIPLEX (Honeywell)

## Known Facts
- Brand: Honeywell
- Name: Системный блок Dell Optiplex
- Expected Category: Системный блок
- Our Price (xlsx): 0,00

## Questions to Resolve
- Find a public market price for Honeywell OPTIPLEX from a verifiable distributor
- Is OPTIPLEX RFQ-only or available with published pricing?
- Which authorized distributors carry this part number?
- Provide any relevant Russian-language product description for Honeywell OPTIPLEX

## Current State
```json
{
  "card_status": "DRAFT_ONLY",
  "identity_level": "weak",
  "photo_verdict": "REJECT",
  "price_status": "no_price_found",
  "price_source_url": "https://www.scribd.com/document/1020482281/PMT-HPS-Dell-Optiplex-XE3-Planning-Installation-and-Service-Guide-Hwdoc-x635-en-A",
  "category_mismatch": false,
  "overall_confidence": "VERY_LOW",
  "review_reasons": [
    "IDENTITY_WEAK",
    "NO_IMAGE_EVIDENCE",
    "NO_PRICE_EVIDENCE",
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
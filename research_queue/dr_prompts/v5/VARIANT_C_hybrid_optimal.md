# Variant C -- Hybrid Optimal

Hypothesis: combining the best elements from all previous versions:
- v3's structured columns (Datasheet, Certs, EAN)
- v4-B's narrative description approach
- v4-A's search protocol
- Explicit Russian price sources
- Family context from v4-C

This is the "best of everything" variant.

## Prompt

---

Research {COUNT} industrial part numbers for a B2B catalog. You will produce
both a narrative technical review AND structured data tables.

## SEARCH PROTOCOL

For each part number, follow this sequence:
1. Google `"{PN}"` in quotes → identify the product
2. Google `"{PN}" datasheet` or `"{PN}" PDF` → find official documentation
3. If nothing: remove suffix (`.10`, `-RU`, `-L3`, `/U`) and retry
4. If still nothing: add brand prefix (`Honeywell {PN}`, `PEHA {PN}`, `Esser {PN}`)
5. Check eBay (ebay.de + ebay.com + ebay.co.uk) for photos and surplus pricing
6. Check Russian sources for RUB prices: vseinstrumenti.ru, lemanapro.ru, etm.ru, electropara.ru, tinko.ru, bionic.spb.ru

## PRODUCT CONTEXT

These products belong to the Honeywell ecosystem of brands:

| Brand | Products | PN Pattern | Best Search Sites |
|---|---|---|---|
| PEHA | Frames, switches, sockets | 5-6 digits, `.10`=white `.20`=cream | ebay.de, conrad.de, electropara.ru |
| Esser | Fire detectors, modules, PA | 80xxxx, 58xxxx | brandmelde-shop.de, tinko.ru |
| Honeywell BT | Valves V5xxx, actuators ML6xxx, thermostats T7xxx | V5011, ML6421 | carrier.com, radwell.com, prolinkpro.ru |
| Trend | BMS controllers FX808xxx | FX808313 | trendcontrols.com, ebay.co.uk |
| Saia-Burgess | PLCs PCD2/3/7 | PCD2.A200 | saia-burgess.com, distrelec.com |
| Honeywell Safety | PPE, gas detectors BW | 1000106, 121679-L3 | grainger.com, amazon.com |
| Weidmuller | Terminals, markers | 10 digits | weidmuller.com, automation24.com |
| Micro Switch | Toggle switches, boots | 5-6 digits (101411, 109411) | mouser.com, digikey.com, newark.com |

## Part Numbers

| # | PN | Product Hint |
|---|-----|-------------|
{TABLE}

## Required Output

### Part 1: Technical Review (Russian narrative)

Write a comprehensive technical article in Russian, covering ALL products.
Group by product family. For each product write 100-200 words:
- What it is, series/family, manufacturer
- How it works, key technical principle
- Specifications with real numbers (dimensions, ratings, ranges)
- Application areas (types of facilities, systems)
- What makes this modification unique (suffix meaning, variant)
- Compatibility and ecosystem context

Write as a senior technical editor. Use natural Russian.
This text will be used directly in our product catalog descriptions.

### Part 2: Structured Tables

**Table 1 -- Product data (ALL {COUNT} rows, every PN must appear)**

| Part Number | Brand | Product Name (Russian) | Description (Russian, 3-5 sentences) | Category | Price | Currency | Price Source URL | Photo URL | Datasheet PDF URL | Key Specs (structured: param: value; param: value) | Certifications | EAN/GTIN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

Column requirements:
- **Part Number**: exact PN from input list
- **Brand**: real manufacturer (not always Honeywell -- could be PEHA, Esser, Weidmuller, etc.)
- **Product Name (Russian)**: concise name, 5-15 words
- **Description (Russian)**: 3-5 sentences, professional tone. What, why, where, how.
- **Category**: Russian category name (e.g. "Рамка для выключателя", "Клапан регулирующий")
- **Price**: real found price or "Not found". NEVER estimate or guess.
- **Datasheet PDF URL**: direct link to the PDF file (not just the product page)
- **Key Specs**: structured format: `param: value; param: value` (e.g. `DN: 15; Kvs: 0.63; PN: 16`)
- **EAN/GTIN**: barcode number if found on any listing

**Table 2 -- Documents found**

| Part Number | Document URL | Document Type | Language |
|---|---|---|---|

Only include rows where you actually found a document.
Document Type: Datasheet, Installation Manual, Wiring Diagram, Certificate, Technical Manual

**Table 3 -- All URLs visited (ALL {COUNT} PNs)**

| Part Number | URL | Page Type | Has Price | Has Specs | Has Photo | Has Datasheet |
|---|---|---|---|---|---|---|

2-5 URLs per PN. This data trains our search AI -- include even failed searches.
Page Type: distributor / manufacturer / marketplace / datasheet / catalog / forum

## Critical Rules

1. NEVER invent or estimate prices. "Not found" is always better than a guess.
2. Every input PN MUST appear in Table 1 and Table 3.
3. Russian prices (RUB) from vseinstrumenti.ru, lemanapro.ru are HIGH PRIORITY.
4. Description quality matters more than finding prices.
5. If PN has an alias (different number for same product), mention it in Key Specs.
6. Photos from eBay listings are acceptable.
7. The narrative review text will be published in our catalog -- make it excellent.

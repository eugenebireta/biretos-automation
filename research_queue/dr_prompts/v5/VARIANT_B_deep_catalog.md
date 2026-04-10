# Variant B -- Deep Catalog Writer

Hypothesis: making the NARRATIVE DESCRIPTION the primary task (not price)
produces both better descriptions AND better product identification,
because DR has to deeply understand the product first.

## Prompt

---

I am building a professional industrial equipment catalog in Russian language.
For each part number below, your MAIN task is to create a detailed technical
article about the product. Finding prices is secondary -- understanding the
product deeply is primary.

## Your workflow for EACH part number

1. **IDENTIFY**: What exactly is this product? What series/family? What manufacturer?
2. **UNDERSTAND**: How does it work? What problem does it solve? What systems does it integrate with?
3. **DESCRIBE**: Write a rich technical description in Russian (see format below)
4. **DOCUMENT**: Find datasheet PDFs, photos, specifications
5. **PRICE**: Find current market price if available (any currency)

## Brand context (use this to guide your search)

These products come from the Honeywell ecosystem:
- **PEHA** -- German electrical installation (frames, switches, sockets). PN format: 5-6 digits, suffix `.10`=white, `.20`=cream. Search: ebay.de, conrad.de, voelkner.de, electropara.ru
- **Esser by Honeywell** -- Fire detection (detectors, modules, PA). PN: 6 digits starting 80xxxx, 58xxxx. Search: brandmelde-shop.de, tinko.ru, fireshield.co.uk
- **Honeywell Building Tech** -- HVAC valves (V5xxx), actuators (ML6xxx), thermostats (T7xxx). Search: carrier.com, radwell.com, indiamart.com, prolinkpro.ru
- **Trend Controls** -- BMS controllers (FX808xxx). Search: trendcontrols.com, ebay.co.uk
- **Saia-Burgess** -- PLCs (PCD2/3/7.xxx). Search: saia-burgess.com, distrelec.com
- **Honeywell Safety** -- PPE, gas detectors (BW). Search: grainger.com, amazon.com
- **Weidmuller** -- Terminal blocks, markers. PN: 10-digit codes. Search: weidmuller.com, automation24.com

Russian price sources (HIGH PRIORITY):
vseinstrumenti.ru, lemanapro.ru, etm.ru, bionic.spb.ru, electropara.ru, prolinkpro.ru

## Part Numbers

| # | PN | Product Hint |
|---|-----|-------------|
{TABLE}

## Output -- TWO sections

### SECTION 1: Narrative technical review (REQUIRED)

Write a single cohesive technical article in Russian covering all {COUNT} products.
Group products by category/family. For each product, write 100-250 words explaining:
- What it is, what series/family it belongs to
- Physical principle of operation or key function
- Main technical specifications
- Where and how it is used (types of facilities, systems, applications)
- What makes this specific model/modification special
- Compatibility with other components

Write as a technical editor for a professional industrial catalog.
Use natural Russian, NOT literal translation from English.
Include specific numbers: dimensions, ratings, temperature ranges, standards.

### SECTION 2: Structured data tables

**Table 1 -- Product data (ALL {COUNT} rows)**

| Part Number | Brand | Product Name (Russian) | Description (Russian, 3-5 sentences) | Category | Price | Currency | Price Source URL | Photo URL | Datasheet PDF URL | Key Specs (structured: param: value; param: value) | Certifications | EAN/GTIN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

- **Description (Russian, 3-5 sentences)**: краткая версия описания из нарратива выше. Что это, назначение, ключевые характеристики, применение. 3-5 предложений.
- Every input PN MUST have a row, even if price is "Not found"
- NEVER invent prices

**Table 2 -- Sources visited (ALL {COUNT} PNs)**

| Part Number | URL | Page Type | Has Price | Has Specs | Has Photo | Has Datasheet |
|---|---|---|---|---|---|---|

List 2-4 real URLs per PN. Even for "not found" items, show where you searched.

## Rules

- Description quality is MORE important than finding prices
- Any currency accepted (EUR, USD, GBP, RUB, CHF)
- Russian prices are high priority
- Surplus/eBay photos are acceptable
- If exact PN not found, search without suffix (.10, -RU, -L3, /U)
- If product has an alias (different PN), mention it and search that too

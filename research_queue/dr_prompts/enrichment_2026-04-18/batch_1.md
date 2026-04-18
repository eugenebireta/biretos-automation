# DR Batch ENRICH-1/3 — Biretos Multi-Field Enrichment — 2026-04-18

**TASK:** For each SKU below, find missing product data from authoritative web sources.
Return a single JSON array — one object per SKU, preserving input order.

## Output schema (strict)
```json
[
  {
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
  },
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

## SKUs to process (88 items)

| # | PN | Brand | Tags | Series | Title (trimmed) |
|---|----|-------|------|--------|-----------------|
| 1 | `00020211` | PEHA | P1_NO_PRICE | NOVA | combination frames, 2 gang, pure white high-gloss |
| 2 | `1000106` | Howard Leight | P1_NO_PRICE | Bilsom 300 Series | Bilsom 304L Foamplug (Corded) |
| 3 | `280870645` | Honeywell | P1_NO_PRICE,P3_NO_EAN | - | Кабель Honeywell 280870645 |
| 4 | `600GB-SAS2.5` | Honeywell | P1_NO_PRICE,P3_NO_EAN | Secure KVM | HP LIGHTWEIGHT NOTEBOOK |
| 5 | `600GB-SAS3.5` | Honeywell | P1_NO_PRICE,P3_NO_EAN | Warehouse Star Apps | Fulfillment for Contract Logistics |
| 6 | `773111` | PEHA | P1_NO_PRICE | DIALOG exclusiv | combination frame, single, aluminium/chrome |
| 7 | `775511` | PEHA | P1_NO_PRICE | STANDARD | SCHUKO socket STANDARD red |
| 8 | `788013.40.RU` | Honeywell | P1_NO_PRICE,P3_NO_EAN | IQ8Control | Fire alarm control panel IQ8Control C |
| 9 | `EDA61K-SH-DC` | Honeywell | P1_NO_PRICE,P3_NO_EAN | ScanPal EDA61K | SCANPAL EDA61K Enterprise Mobile Computer |
| 10 | `LATITUDE` | Honeywell | P1_NO_PRICE,P3_NO_EAN | RESCU 406 | Ноутбук Honeywell LATITUDE |
| 11 | `LUX` | Produal | P1_NO_PRICE,P2_WRONG_DATASHEET,P3_NO_EAN | - | SW-DCT-USB Configuration Cable |
| 12 | `OPTIPLEX` | Honeywell | P1_NO_PRICE,P3_NO_EAN | - | Системный блок Honeywell OPTIPLEX |
| 13 | `P2210F` | Honeywell | P1_NO_PRICE,P3_NO_EAN | - | Монитор Honeywell P2210F |
| 14 | `P2213T` | Honeywell | P1_NO_PRICE,P3_NO_EAN | - | Монитор Honeywell P2213T |
| 15 | `P2421D` | Dell | P1_NO_PRICE,P3_NO_EAN | Dell P Series | Dell 24 Monitor P2421D |
| 16 | `P2422H` | Dell | P1_NO_PRICE,P3_NO_EAN | Dell P Series | Dell 24 Monitor - P2422H |
| 17 | `PAVILION` | Honeywell | P1_NO_PRICE,P3_NO_EAN | Hanwha Techwin Product Portfol | 4K AI IR Bullet Camera |
| 18 | `PRECISION` | Dell | P1_NO_PRICE | Honeywell Precision Barometer | Honeywell Precision Barometer HPB |
| 19 | `RA100Z` | System Sensor | P1_NO_PRICE,P3_NO_EAN | DNR | DNR Duct Smoke Detector |
| 20 | `U2412M` | Honeywell | P1_NO_PRICE,P3_NO_EAN | - | Монитор Honeywell U2412M |
| 21 | `VQ450MA1015` | Honeywell | P1_NO_PRICE,P3_NO_EAN | SLATE system | SLATE system |
| 22 | `VQ450MB1006` | Honeywell | P1_NO_PRICE,P3_NO_EAN | SLATE system, VE series gas va | SLATE(TM) Combustion Management System - Base Module |
| 23 | `129625-L3` | Honeywell | P2_WRONG_DATASHEET,P3_NO_EAN | - | Набор Honeywell 129625-L3 |
| 24 | `174411` | PEHA | P2_WRONG_DATASHEET | AURA | Рамка 4-постовая PEHA AURA, 174411 |
| 25 | `179433` | PEHA | P2_WRONG_DATASHEET | NOVA | Installations covered by ETS in Germany 2021 (02/05/2022) |
| 26 | `188091` | PEHA | P2_WRONG_DATASHEET | NOVA | Audited annual report CANDRIAM BONDS |
| 27 | `190891` | PEHA | P2_WRONG_DATASHEET | NOVA | ANNUAL REPORT 2015 |
| 28 | `191591` | PEHA | P2_WRONG_DATASHEET | NOVA | Рамка 4-постовая PEHA NOVA, 191591 |
| 29 | `239053` | PEHA | P2_WRONG_DATASHEET | DIALOG | Produktkatalog Løft 2020/2021 |
| 30 | `3240248` | Honeywell | P2_WRONG_DATASHEET,P3_NO_EAN | - | Канал Honeywell 3240248 |
| 31 | `775611` | PEHA | P2_WRONG_DATASHEET | - | AIRBUS DEFENCE AND SPACE GMBH |
| 32 | `786711` | PEHA | P2_WRONG_DATASHEET | - | PUBLIC REGISTER NOTICE - EMPLOYMENT EQUITY ACT, 1998 |
| 33 | `806602` | Honeywell | P2_WRONG_DATASHEET,P3_NO_EAN | - | 2026 Notice of Annual Meeting of Shareholders and Proxy Stat |
| 34 | `CR-P_M42` | Honeywell | P2_WRONG_DATASHEET | № 2 (370) 2025 | Fundamental and Applied Problems of Engineering and Technolo |
| 35 | `DCPSU-24-1.3` | Honeywell | P2_WRONG_DATASHEET,P3_NO_EAN | - | Блок питания Honeywell DCPSU-24-1.3 |
| 36 | `FT6960-60` | Honeywell | P2_WRONG_DATASHEET,P3_NO_EAN | - | Adapter ring |
| 37 | `GLATRON` | GLATRON | P2_WRONG_DATASHEET,P3_NO_EAN | - | De la smart city à la réalité des territoires connectés - L' |
| 38 | `SC-SC` | Hyperline | P2_WRONG_DATASHEET,P3_NO_EAN | - | E3 Series® Control Panel |
| 39 | `SM-0.9-SC-UPC-1.5` | Optcom | P2_WRONG_DATASHEET,P3_NO_EAN | - | Сборник трудов IX Международной научной конференции «ИТ – СТ |
| 40 | `VQ440MB1005` | Honeywell | P2_WRONG_DATASHEET,P3_NO_EAN | - | Solenoid gas valve, normally closed VE400AA |
| 41 | `010130.10` | Esser | P3_NO_EAN | 4MG/2A Modul BUS-2/BUS-1 | 4MG/2A Modul BUS-2/BUS-1, aP |
| 42 | `027913.10` | Esser | P3_NO_EAN | MB-Secure PRO | MB-Secure PRO Base Board |
| 43 | `033588.17` | Esser | P3_NO_EAN | WINMAG plus | WINMAG plus installation medium |
| 44 | `1011893-RU` | Sperian | P3_NO_EAN | - | Привязь Sperian 1011893-RU |
| 45 | `1012541` | Howard Leight | P3_NO_EAN | - | Система обеспечения персонала средствами индивидуальной защи |
| 46 | `1015021` | Howard Leight | P3_NO_EAN | - | Honeywell Catalog 2025 |
| 47 | `121679-L3` | Honeywell | P3_NO_EAN | - | Аспиратор Honeywell 121679-L3 |
| 48 | `13960` | Esser | P3_NO_EAN | Axial Flow Valves | Axial Flow Valves Technical Bulletin |
| 49 | `272369098` | Honeywell | P3_NO_EAN | - | Разъем Honeywell 272369098 |
| 50 | `280869341` | Honeywell | P3_NO_EAN | - | Комплект Honeywell 280869341 |
| 51 | `2904617` | Phoenix Contact | P3_NO_EAN | Safety Manager Release 162 | Источник питания Honeywell 2904617 |
| 52 | `2SM-3.0-SCU-SCU-1` | Optcom | P3_NO_EAN | - | Шнур Optcom 2SM-3.0-SCU-SCU-1 |
| 53 | `2SM-3.0-SCU-SCU-15` | Optcom | P3_NO_EAN | - | Шнур Optcom 2SM-3.0-SCU-SCU-15 |
| 54 | `3240190` | Honeywell | P3_NO_EAN | - | Рейка Honeywell 3240190 |
| 55 | `3240199` | Phoenix Contact | P3_NO_EAN | - | Канал Honeywell 3240199 |
| 56 | `3240348` | Phoenix Contact | P3_NO_EAN | - | Канал Honeywell 3240348 |
| 57 | `3240357` | Honeywell | P3_NO_EAN | BITRON N16/S16, ELECTRICA C4AZ | Microswitches, mechanical |
| 58 | `3240605` | Honeywell | P3_NO_EAN | Multiple series: N16, S16, C4A | Microswitch |
| 59 | `36022-RU` | DKC | P3_NO_EAN | - | Угол DKC 36022-RU |
| 60 | `36024-RU` | DKC | P3_NO_EAN | - | Угол DKC 36024-RU |
| 61 | `36026-RU` | DKC | P3_NO_EAN | Signalling System No. 7 | Угол DKC 36026-RU |
| 62 | `36142-RU` | DKC | P3_NO_EAN | - | Соединитель DKC 36142-RU |
| 63 | `36144-RU` | DKC | P3_NO_EAN | October 2020 | African Journal of Agricultural Research |
| 64 | `36204-RU` | DKC | P3_NO_EAN | - | Соединитель DKC 36204-RU |
| 65 | `36206-RU` | DKC | P3_NO_EAN | None | QST Amateur Radio |
| 66 | `36299-RU` | DKC | P3_NO_EAN | DIXI | DIXI 1101 Centre Drill |
| 67 | `400-ATII` | Honeywell | P3_NO_EAN | Fusion IV NVR | Fusion IV NVR Series |
| 68 | `42511` | Esser | P3_NO_EAN | Admiral 976 G7 Series | Transistor |
| 69 | `50017460-001/U` |  | P3_NO_EAN | - | - |
| 70 | `57511` | Esser | P3_NO_EAN | RHEDV Direct Vent Insert | Устройство Honeywell 57511 |
| 71 | `580249.11` | Honeywell | P3_NO_EAN | - | Усилитель Honeywell 580249.11 |
| 72 | `581263` | Honeywell | P3_NO_EAN | - | Громкоговоритель Honeywell 581263 |
| 73 | `581270` | Honeywell | P3_NO_EAN | - | Громкоговоритель Honeywell 581270 |
| 74 | `581276` | Honeywell | P3_NO_EAN | - | Громкоговоритель Honeywell 581276 |
| 75 | `583491A` | Esser | P3_NO_EAN | - | Кабель Honeywell 583491A |
| 76 | `583520` | Honeywell | P3_NO_EAN | VARIODYN ONE | VARIODYN ONE Digital Call Station DCS plus / DKM plus |
| 77 | `6500-LRK` | Honeywell | P3_NO_EAN | - | Извещатель Honeywell 6500-LRK |
| 78 | `65UL3J` | Honeywell | P3_NO_EAN | - | Wireless Doorbell and Chime |
| 79 | `704960` | Honeywell | P3_NO_EAN | - | Запасное стекло Honeywell 704960 |
| 80 | `7508001857` | Weidmuller | P3_NO_EAN | - | Модуль ввода Weidmuller 7508001857 |
| 81 | `7508001858` | Weidmuller | P3_NO_EAN | - | Модуль ввода Weidmuller 7508001858 |
| 82 | `7508002114` | Weidmuller | P3_NO_EAN | - | 8-местная стойка с резервным источником питания |
| 83 | `788600` | Esser | P3_NO_EAN | esserbus alarm transponder | esserbus alarm transponder, 4 IN/2 OUT with isolator |
| 84 | `7910180000` | Weidmüller | P3_NO_EAN | W-Series | WTR 4 |
| 85 | `802371` | Esser | P3_NO_EAN | IQ8Quad | Optical smoke detector IQ8Quad with isolator |
| 86 | `802374` | Honeywell | P3_NO_EAN | IQ8Quad-ST | IQ8Quad-ST - Self-Test series of detectors |
| 87 | `804791` | Esser | P3_NO_EAN | esserbus | Loop LED remote indicator panel for 32 messages |
| 88 | `804905` | Esser | P3_NO_EAN | IQ8 | IQ8MCP electronic module with isolator |

---

**Reminder:** return only a JSON array conforming to the schema above. One object per SKU, preserving input order. Missing/not-found fields → `null` with explanatory `notes`. Never fabricate.
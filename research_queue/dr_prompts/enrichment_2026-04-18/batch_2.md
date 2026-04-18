# DR Batch ENRICH-2/3 — Biretos Multi-Field Enrichment — 2026-04-18

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
| 1 | `805576` | Honeywell | P3_NO_EAN | IQ8Quad-ST | IQ8Quad-ST - Self-Test series of detectors |
| 2 | `805577` | Honeywell | P3_NO_EAN | - | esserbus® alarm transponder |
| 3 | `805590` | Honeywell | P3_NO_EAN | ES Detect | Base for ES Detect range |
| 4 | `808606` | Esser | P3_NO_EAN | IQ8FCT XS | esserbus® -Transponder IQ8FCT XS |
| 5 | `808610.10` | Honeywell | P3_NO_EAN | esserbus | esserbus transponder 12 relays (8 bit) |
| 6 | `808621` | Honeywell | P3_NO_EAN | - | Транспондер Honeywell 808621 |
| 7 | `871-229-201` | Honeywell | P3_NO_EAN | CK65/CK3X/CK3R | Single Dock, Standard |
| 8 | `91940-RU` | Honeywell | P3_NO_EAN | Radar and Electronic Warfare S | TMMR |
| 9 | `A133230-00` | Honeywell | P3_NO_EAN | COMMANDER | COMMANDER Shotblasting Helmet |
| 10 | `AF00-B65` | Honeywell | P3_NO_EAN | AF00, AF10, AF12, AF20 | AF00, AF10, AF12 and AF20 OUTSIDE TEMPERATURE SENSORS |
| 11 | `AT-MMC200LX` | Honeywell | P3_NO_EAN | - | Медиаконвертер Honeywell AT-MMC200LX |
| 12 | `AT-MMCR18-60-RU` | Honeywell | P3_NO_EAN | - | Шасси Honeywell AT-MMCR18-60-RU |
| 13 | `AT-TRAY4` | Honeywell | P3_NO_EAN | Sky Connect Tracker III | Sky Connect™ Tracking System |
| 14 | `BF-HWC4-PN16-0125` | Honeywell | P3_NO_EAN | - | Задвижка Honeywell BF-HWC4-PN16-0125 |
| 15 | `BS-420G2` | Autronica | P3_NO_EAN | - | 6242Y Twin & Earth Cable |
| 16 | `BWC4-Y-R` | Honeywell | P3_NO_EAN | BW™ Clip4 | BW™ Clip4 |
| 17 | `C7355A1050` | Honeywell | P3_NO_EAN | - | C7355A Room IAQ Monitor |
| 18 | `CAB-010-SC-SM` | Hyperline | P3_NO_EAN | HYPERLINE Cabling Systems | CATALOG 2009 |
| 19 | `CABLE-0.22-8T` | Honeywell | P3_NO_EAN | Honeywell I/O Modules (16UIO,  | I/O Modules, Expansion Modules & Wiring Adapter |
| 20 | `CATALIST` | Honeywell | P3_NO_EAN | None | UOP R-264 CCR Platforming™ Catalyst |
| 21 | `CB015A` | HP | P3_NO_EAN | HP Officejet Pro K8600 Color P | HP Officejet Pro K8600 Color Printer series |
| 22 | `CF274A` | HP | P3_NO_EAN | HP LaserJet Pro 400 M401 | HP LaserJet Pro 400 Printer M401 series |
| 23 | `CM010610` | DKC | P3_NO_EAN | C5 Combitech | Винт DKC CM010610 |
| 24 | `CM100600-RU` | DKC | P3_NO_EAN | COMBITECH (S5, F5, L5, B5, M5) | Металлорукав из оцинкованной стали |
| 25 | `CN80-HB-CNV-0` | Honeywell | P3_NO_EAN | Dolphin CN80 | CN80 Handheld Computer |
| 26 | `CPO-RL4` | Honeywell | P3_NO_EAN | ComfortPoint Open CPO-Rxx Room | ComfortPoint Open CPO-Rxx ROOM CONTROLLERS |
| 27 | `CR-M024DC2` | ABB | P3_NO_EAN | ABB Electrification Products C | ESB 24 Installation Contactor (2 N.O., 24V) |
| 28 | `CR-M4LC` | Honeywell | P3_NO_EAN | ABB Electrification Products - | Electrification UK Contractor handbook |
| 29 | `CR-P/M42` |  | P3_NO_EAN | - | - |
| 30 | `CWR` | Honeywell | P3_NO_EAN | Sounders | Non-Addressable Audible Visual Devices (Sounders) |
| 31 | `CWSS-RB-S8` | System Sensor | P3_NO_EAN | EVCS Network 8 | Emergency Voice Communication Systems EVCS Network 8 Data Sh |
| 32 | `DPTE1000S` | Honeywell | P3_NO_EAN | DPTE | 3-WIRE DIFFERENTIAL PRESSURE TRANSMITTERS WITH CURRENT AND V |
| 33 | `DTI6` | Honeywell | P3_NO_EAN | DTI/DTU Differential Pressure  | DIFFERENTIAL PRESSURE TRANSMITTER |
| 34 | `EDA61K-HB-2` | Honeywell | P3_NO_EAN | - | Зарядное устройство Honeywell EDA61K-HB-2 |
| 35 | `EVCS-HSB` | Notifier | P3_NO_EAN | EVCS Type B Outstation | TYPE B OUTSTATION |
| 36 | `EVCS-MS` | Notifier | P3_NO_EAN | Network 8 | NETWORK 8 MASTER HANDSET |
| 37 | `F750E-S0` | Dell | P3_NO_EAN | F750E | 80 PLUS Verification and Testing Report - Dell F750E-S0 750W |
| 38 | `FCP3-RACK` | Siemon | P3_NO_EAN | Fiber Connect Panel (FCP3) | Fiber Connect Panel (FCP3) |
| 39 | `FH973A` | HP | P3_NO_EAN | - | Переходник Honeywell FH973A |
| 40 | `FO-WBI-12A-GY` | Hyperline | P3_NO_EAN | - | Бокс Hyperline FO-WBI-12A-GY |
| 41 | `FP1B-LCUL-01H` | Siemon | P3_NO_EAN | XGLO | Пигтейл Honeywell FP1B-LCUL-01H |
| 42 | `FUSE-0.5A-5X20` | Honeywell | P3_NO_EAN | - | Предохранитель Honeywell FUSE-0.5A-5X20 |
| 43 | `FUSE-20A-5X20` | Honeywell | P3_NO_EAN | H-S81-HS & S81-HS/C Industrial | H-S81-HS & S81-HS/C Industrial Fire Panels |
| 44 | `FUSE-2A-5X20-RU` | Honeywell | P3_NO_EAN | GASTER N | GASTER N 119 ÷ 289 AW |
| 45 | `FUSE-6.3A-5X20` | Honeywell | P3_NO_EAN | ARC300 | ELECTRONIC CONTROL SYSTEM ARC 300 |
| 46 | `FX808313` | Honeywell | P3_NO_EAN | - | Akku-Erweiterungsgehäuse für 2 x 12 V/24 Ah |
| 47 | `FX808324` | Esser | P3_NO_EAN | ES Line | FACP ES Line for 8 zones, German |
| 48 | `FX808332` | Esser | P3_NO_EAN | ES Line | FACP ES Line for 8 zones, German |
| 49 | `FX808338` | Honeywell | P3_NO_EAN | IQ8Control | Declaration of Performance |
| 50 | `FX808341` | Esser | P3_NO_EAN | ES Line | FACP ES Line for 8 zones, German |
| 51 | `FX808363` | Honeywell | P3_NO_EAN | - | Power supply extension 24 V/12 Ah |
| 52 | `FX808364` | Esser | P3_NO_EAN | ES Line | FACP ES Line for 8 zones, German |
| 53 | `FX808397` | Esser | P3_NO_EAN | FlexES Control FX18 | FACP FlexES Control FX18 (18 loops) |
| 54 | `FX808430.18R` | Esser | P3_NO_EAN | ES Line / Compact | Conventional MCP electronic module |
| 55 | `FX808431` | Esser | P3_NO_EAN | - | Heavy-duty drawer with power supply unit, 5 HU |
| 56 | `FX808439` | Esser | P3_NO_EAN | - | Ящик Honeywell FX808439 |
| 57 | `H3D1F1X` | Honeywell | P3_NO_EAN | equIP® Series H3D1F | H3D1F equlP® SERIES 720p VFAI TRUE DAY/NIGHT H.264 INDOOR FI |
| 58 | `H4L6GR2` | Honeywell | P3_NO_EAN | equIP Cameras | H4L6GR2 Network TDN Low-Light 6 MP IR Rugged Dome Camera |
| 59 | `H4W4GR1Y` | Honeywell | P3_NO_EAN | EQUIP Series | 4MP Network TDN Ultra Low-light WDR IR Rugged Dome Cameras |
| 60 | `H4W4PER2` | Honeywell | P3_NO_EAN | Performance Series | WDR 4 MP IR Rugged Mini Dome Camera |
| 61 | `HBL6GR2` | Honeywell | P3_NO_EAN | Network TDN Low-Light 2 MP IR  | Network TDN Low-Light 2 MP IR LPR Rugged Bullet Camera |
| 62 | `HCM-4-2U` | Siemon | P3_NO_EAN | RouteIT | RouteIT™ Cable Managers |
| 63 | `HVAC23C5` | Honeywell | P3_NO_EAN | NXL HVAC INVERTERS | Инвертор Honeywell HVAC23C5 |
| 64 | `HVAC31C5` | Honeywell | P3_NO_EAN | NXL HVAC | Инвертор Honeywell HVAC31C5 |
| 65 | `HVAC46C5` | Honeywell | P3_NO_EAN | NXL HVAC | NXL HVAC INVERTERS |
| 66 | `IMC-101-S-SC` | Honeywell | P3_NO_EAN | ControlEdge PLC 900 Series | ControlEdge PLC Specification |
| 67 | `KCD2090XI` | Honeywell | P3_NO_EAN | - | Монитор Honeywell KCD2090XI |
| 68 | `KD-050` | Kale Kilit | P3_NO_EAN | - | Лампа Kale Kilit KD-050 |
| 69 | `KTF00-65-2M` | Honeywell | P3_NO_EAN | KTFxx | KTFxx CABLE-TYPE BULB TEMPERATURE SENSORS |
| 70 | `KZDS` | unknown | P3_NO_EAN | - | Гильза unknown KZDS |
| 71 | `L-VOM40A/EN` |  | P3_NO_EAN | - | - |
| 72 | `LA5496411314` | Schneider Electric | P3_NO_EAN | - | Крепления Schneider Electric LA5496411314 |
| 73 | `LEONARDO-OT` | Honeywell | P3_NO_EAN | - | Successes in Chemistry and Chemical Technology |
| 74 | `LF20-3P65-5M` | Honeywell | P3_NO_EAN | LF20, PF20 Duct Temperature Se | LF20, PF20 DUCT TEMPERATURE SENSORS |
| 75 | `M200E-SMB` | Esser | P3_NO_EAN | - | Embodied Carbon Calculator: Basic Report for M200E-SMB |
| 76 | `M7294Q1015/U` |  | P3_NO_EAN | - | - |
| 77 | `MAU8/MS` |  | P3_NO_EAN | - | - |
| 78 | `MB3480` | Honeywell | P3_NO_EAN | Type Approved Equipment | TABLET PC - HUAWEI DBY-W09 |
| 79 | `MCP-PRO-M` | Esser | P3_NO_EAN | ECO1000 | Извещатель пожарный дымовой оптико-электронный ECO1003М |
| 80 | `ML6420A3072` | Honeywell | P3_NO_EAN | WP FLYPPER | COMPLETE SET OF PACKINGS |
| 81 | `ML6421A3005` | Honeywell | P3_NO_EAN | BF-HWC4, BF-MWC5 | Привод Honeywell ML6421A3005 |
| 82 | `ML6421A3013` | Honeywell | P3_NO_EAN | BF-HWC4, BF-MWC5, SS-REJ | Дисковые поворотные затворы, с ручным управлением через руко |
| 83 | `ML6425A3014` | Honeywell | P3_NO_EAN | - | Дисковые поворотные затворы с ручным управлением |
| 84 | `MZ-PCWS77` | Honeywell | P3_NO_EAN | SYSTEM HINTS NEWSLETTER | SYSTEM HINTS NEWSLETTER APRIL 2024 |
| 85 | `MZ-PCWS84` | Honeywell | P3_NO_EAN | Experion Collaboration Station | Experion Collaboration Station |
| 86 | `N05010` | Honeywell | P3_NO_EAN | VSxF-2 | Низовая автоматика |
| 87 | `N05230-2POS` | Honeywell | P3_NO_EAN | BF-HWC4, BF-MWC5 | Дисковые поворотные затворы, с ручным управлением через руко |
| 88 | `N0524` | Honeywell | P3_NO_EAN | BF-HWC4, BF-MWC5 SERIES | ДИСКОВОВЫЕ ПОВОРОТНЫЕ ЗАТВОРЫ, С РУЧНЫМ УПРАВЛЕНИЕМ ЧЕРЕЗ РУ |

---

**Reminder:** return only a JSON array conforming to the schema above. One object per SKU, preserving input order. Missing/not-found fields → `null` with explanatory `notes`. Never fabricate.
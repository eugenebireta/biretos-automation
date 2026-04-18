# DR Batch EAN-1/3 — Biretos Catalog — 2026-04-18

**TASK:** find the 13-digit EAN/GTIN barcode for each SKU below. Return a single JSON array.

## Output schema (strict)
```json
[
  {
    "pn": "<exact PN from input>",
    "ean": "<13 digits, or null if not found>",
    "ean_source_url": "<URL of source page, or null>",
    "confidence": "high | medium | low | null",
    "notes": "<short English note>"
  },
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

## SKUs to process (83 items)

| PN | Brand | Series | Title (trimmed) |
|----|-------|--------|-----------------|
| `CR-M024DC2` | ABB | ABB Electrification Products Contractor  | ESB 24 Installation Contactor (2 N.O., 24V) |
| `BS-420G2` | Autronica | - | 6242Y Twin & Earth Cable |
| `PTSRB0101V3` | Brevini | - | Датчик Honeywell PTSRB0101V3 |
| `36022-RU` | DKC | - | Угол DKC 36022-RU |
| `36024-RU` | DKC | - | Угол DKC 36024-RU |
| `36026-RU` | DKC | Signalling System No. 7 | Угол DKC 36026-RU |
| `36142-RU` | DKC | - | Соединитель DKC 36142-RU |
| `36144-RU` | DKC | October 2020 | African Journal of Agricultural Research |
| `36204-RU` | DKC | - | Соединитель DKC 36204-RU |
| `36206-RU` | DKC | None | QST Amateur Radio |
| `36299-RU` | DKC | DIXI | DIXI 1101 Centre Drill |
| `CM010610` | DKC | C5 Combitech | Винт DKC CM010610 |
| `CM100600-RU` | DKC | COMBITECH (S5, F5, L5, B5, M5), FS, COSM | Металлорукав из оцинкованной стали |
| `F750E-S0` | Dell | F750E | 80 PLUS Verification and Testing Report - Dell F750E-S0 750W Power Supply |
| `P2212HB` | Dell | - | Монитор Honeywell P2212HB |
| `P2217H` | Dell | - | Системный блок Honeywell P2217H |
| `P2421D` | Dell | Dell P Series | Dell 24 Monitor P2421D |
| `P2422H` | Dell | Dell P Series | Dell 24 Monitor - P2422H |
| `PP11L` | Dell | - | Ноутбук Dell PP11L |
| `U2410F` | Dell | U2410 | Dell U2410 Flat Panel Monitor |
| `U2412MB` | Dell | - | Монитор Honeywell U2412MB |
| `U2421M` | Dell | - | Монитор Honeywell U2421M |
| `WD19DCS` | Dell | Type Approved Equipment List | Док-станция Honeywell WD19DCS |
| `RDU300504` | Eaton | - | Редуктор Eaton RDU300504 |
| `010130.10` | Esser | 4MG/2A Modul BUS-2/BUS-1 | 4MG/2A Modul BUS-2/BUS-1, aP |
| `027913.10` | Esser | MB-Secure PRO | MB-Secure PRO Base Board |
| `033588.17` | Esser | WINMAG plus | WINMAG plus installation medium |
| `13960` | Esser | Axial Flow Valves | Axial Flow Valves Technical Bulletin |
| `42511` | Esser | Admiral 976 G7 Series | Transistor |
| `57511` | Esser | RHEDV Direct Vent Insert | Устройство Honeywell 57511 |
| `583491A` | Esser | - | Кабель Honeywell 583491A |
| `788600` | Esser | esserbus alarm transponder | esserbus alarm transponder, 4 IN/2 OUT with isolator |
| `802371` | Esser | IQ8Quad | Optical smoke detector IQ8Quad with isolator |
| `804791` | Esser | esserbus | Loop LED remote indicator panel for 32 messages |
| `804905` | Esser | IQ8 | IQ8MCP electronic module with isolator |
| `808606` | Esser | IQ8FCT XS | esserbus® -Transponder IQ8FCT XS |
| `FX808324` | Esser | ES Line | FACP ES Line for 8 zones, German |
| `FX808332` | Esser | ES Line | FACP ES Line for 8 zones, German |
| `FX808341` | Esser | ES Line | FACP ES Line for 8 zones, German |
| `FX808364` | Esser | ES Line | FACP ES Line for 8 zones, German |
| `FX808397` | Esser | FlexES Control FX18 | FACP FlexES Control FX18 (18 loops) |
| `FX808430.18R` | Esser | ES Line / Compact | Conventional MCP electronic module |
| `FX808431` | Esser | - | Heavy-duty drawer with power supply unit, 5 HU |
| `FX808439` | Esser | - | Ящик Honeywell FX808439 |
| `M200E-SMB` | Esser | - | Embodied Carbon Calculator: Basic Report for M200E-SMB |
| `MCP-PRO-M` | Esser | ECO1000 | Извещатель пожарный дымовой оптико-электронный ECO1003М |
| `PROFI-O` | Esser | Castrol | Извещатель Honeywell PROFI-O |
| `SMB500` | Esser | None | SMB500-WH Surface Mount Box |
| `GLATRON` | GLATRON | - | De la smart city à la réalité des territoires connectés - L'émergence d'un modèl |
| `CB015A` | HP | HP Officejet Pro K8600 Color Printer | HP Officejet Pro K8600 Color Printer series |
| `CF274A` | HP | HP LaserJet Pro 400 M401 | HP LaserJet Pro 400 Printer M401 series |
| `FH973A` | HP | - | Переходник Honeywell FH973A |
| `121679-L3` | Honeywell | - | Аспиратор Honeywell 121679-L3 |
| `129625-L3` | Honeywell | - | Набор Honeywell 129625-L3 |
| `272369098` | Honeywell | - | Разъем Honeywell 272369098 |
| `280869341` | Honeywell | - | Комплект Honeywell 280869341 |
| `280870645` | Honeywell | - | Кабель Honeywell 280870645 |
| `3240190` | Honeywell | - | Рейка Honeywell 3240190 |
| `3240248` | Honeywell | - | Канал Honeywell 3240248 |
| `3240357` | Honeywell | BITRON N16/S16, ELECTRICA C4AZN/C23ZN/C2 | Microswitches, mechanical |
| `3240605` | Honeywell | Multiple series: N16, S16, C4AZN, C23ZN, | Microswitch |
| `400-ATII` | Honeywell | Fusion IV NVR | Fusion IV NVR Series |
| `50017460-001/U` | Honeywell | Series 61 and Series 62 Modutrol IV | Трансформатор Honeywell 50017460-001/U |
| `580249.11` | Honeywell | - | Усилитель Honeywell 580249.11 |
| `581263` | Honeywell | - | Громкоговоритель Honeywell 581263 |
| `581270` | Honeywell | - | Громкоговоритель Honeywell 581270 |
| `581276` | Honeywell | - | Громкоговоритель Honeywell 581276 |
| `583520` | Honeywell | VARIODYN ONE | VARIODYN ONE Digital Call Station DCS plus / DKM plus |
| `600GB-SAS2.5` | Honeywell | Secure KVM | HP LIGHTWEIGHT NOTEBOOK |
| `600GB-SAS3.5` | Honeywell | Warehouse Star Apps | Fulfillment for Contract Logistics |
| `6500-LRK` | Honeywell | - | Извещатель Honeywell 6500-LRK |
| `65UL3J` | Honeywell | - | Wireless Doorbell and Chime |
| `704960` | Honeywell | - | Запасное стекло Honeywell 704960 |
| `788013.40.RU` | Honeywell | IQ8Control | Fire alarm control panel IQ8Control C |
| `802374` | Honeywell | IQ8Quad-ST | IQ8Quad-ST - Self-Test series of detectors |
| `805576` | Honeywell | IQ8Quad-ST | IQ8Quad-ST - Self-Test series of detectors |
| `805577` | Honeywell | - | esserbus® alarm transponder |
| `805590` | Honeywell | ES Detect | Base for ES Detect range |
| `806602` | Honeywell | - | 2026 Notice of Annual Meeting of Shareholders and Proxy Statement |
| `808610.10` | Honeywell | esserbus | esserbus transponder 12 relays (8 bit) |
| `808621` | Honeywell | - | Транспондер Honeywell 808621 |
| `871-229-201` | Honeywell | CK65/CK3X/CK3R | Single Dock, Standard |
| `91940-RU` | Honeywell | Radar and Electronic Warfare Systems | TMMR |

---

**Reminder:** return only a JSON array conforming to the schema above. One object per SKU, preserving input order. Missing/not-found → `null` fields with explanatory `notes`. Never fabricate.
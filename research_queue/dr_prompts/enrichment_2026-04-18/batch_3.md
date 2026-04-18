# DR Batch ENRICH-3/3 — Biretos Multi-Field Enrichment — 2026-04-18

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

## SKUs to process (87 items)

| # | PN | Brand | Tags | Series | Title (trimmed) |
|---|----|-------|------|--------|-----------------|
| 1 | `N0524-SW2` | Honeywell | P3_NO_EAN | N0524/N1024, N05230-2POS/N1023 | Привод Honeywell N0524-SW2 |
| 2 | `N10010` | Honeywell | P3_NO_EAN | BF-HWC4, BF-MWC5 SERIES | Дисковые поворотные затворы, с ручным управлением через руко |
| 3 | `N34230` | Honeywell | P3_NO_EAN | BF-HWC4, BF-MWC5 SERIES | ДИСКОВЫЕ ПОВОРОТНЫЕ ЗАТВОРЫ, С РУЧНЫМ УПРАВЛЕНИЕМ ЧЕРЕЗ РУКО |
| 4 | `N3424` | Honeywell | P3_NO_EAN | BF-HWC4, BF-MWC5 | Низовая автоматика и трубопроводная арматура |
| 5 | `NE-NICS02` | NEC | P3_NO_EAN | Honeywell TPS | Сетевая карта Honeywell NE-NICS02 |
| 6 | `NMF-RP16SCUS2-RU` | NIKOMAX | P3_NO_EAN | - | Оптический кросс NIKOMAX NMF-RP16SCUS2-RU |
| 7 | `P2212HB` | Dell | P3_NO_EAN | - | Монитор Honeywell P2212HB |
| 8 | `P2213F` | Honeywell | P3_NO_EAN | - | Системный блок Honeywell P2213F |
| 9 | `P2217H` | Dell | P3_NO_EAN | - | Системный блок Honeywell P2217H |
| 10 | `P400-RU` | NVIDIA | P3_NO_EAN | Quadro | NVIDIA Quadro P400 Professional Graphics Card |
| 11 | `P600` | Honeywell | P3_NO_EAN | Street Smart Home Control | Street Smart Home Control |
| 12 | `PANC300-03` | Honeywell | P3_NO_EAN | Experion PKS | PROCESS CONTROLLER OF THE FUTURE |
| 13 | `PANC300-04` | Honeywell | P3_NO_EAN | - | Панель Honeywell PANC300-04 |
| 14 | `PCD2.A200` | Saia-Burgess | P3_NO_EAN | PCD2 | Digitales Ausgangsmodul, 4 Relais, 250 VAC/2 A, Schliesserko |
| 15 | `PCD3.M3360` | Saia-Burgess Controls | P3_NO_EAN | PCD3.M3 | PCD3.M3360 CPU basic power module with Ethernet TCP/IP, 1023 |
| 16 | `PCD3.W340` | SAIA | P3_NO_EAN | PCD3 | Analoges Eingangsmodul, 8 Kanäle, 12 Bit, 0...2.5 V, 0...10  |
| 17 | `PCD7.L500` | Saia-Burgess | P3_NO_EAN | Saia PCD | Saia PCD3.Mxx60 controllers |
| 18 | `PERTHECTION` | Honeywell | P3_NO_EAN | - | Сканер Honeywell PERTHECTION |
| 19 | `PHASER` | Xerox | P3_NO_EAN | LT AC Three Phase Four Wire 40 | TECHNICAL SPECIFICATION OF LT AC THREE PHASE, FOUR WIRE, 40  |
| 20 | `PIP-003` | Honeywell | P3_NO_EAN | VESDA-E | Safety Solutions Product Catalogue |
| 21 | `PP11L` | Dell | P3_NO_EAN | - | Ноутбук Dell PP11L |
| 22 | `PRECITHION` | Honeywell | P3_NO_EAN | - | Системный блок Honeywell PRECITHION |
| 23 | `PRECITION` | Honeywell | P3_NO_EAN | - | Fault Tolerant Power Systems |
| 24 | `PROFI-O` | Esser | P3_NO_EAN | Castrol | Извещатель Honeywell PROFI-O |
| 25 | `PTSRB0101V3` | Brevini | P3_NO_EAN | - | Датчик Honeywell PTSRB0101V3 |
| 26 | `PW5K1ENC3E` | Honeywell | P3_NO_EAN | Pro-Watch 5000 | Pro-Watch 5000 Remote Enclosure |
| 27 | `R4343E1048-ST005` | Honeywell | P3_NO_EAN | SLATE system | SLATE system |
| 28 | `RDU300504` | Eaton | P3_NO_EAN | - | Редуктор Eaton RDU300504 |
| 29 | `RIC-F-BLNK-01` | Siemon | P3_NO_EAN | RIC3 | Rack Mount Interconnect Center (RIC3) |
| 30 | `RIC-F-LCU24-01C` | Siemon | P3_NO_EAN | - | Панель Honeywell RIC-F-LCU24-01C |
| 31 | `RMK400AP-IV` | Honeywell | P3_NO_EAN | LEONARDO | Извещатель пожарный дымовой оптико-электронный ЕСО1003М |
| 32 | `ROL15-2761-04` | Honeywell | P3_NO_EAN | I-Class Mark II | I-Class™ Mark II Replacement Parts Catalog |
| 33 | `S0324-2POS-SW1` | Honeywell | P3_NO_EAN | S03, S05 Series Low-Torque Spr | S03, S05 Series Low-Torque Spring-Return Direct-Coupled Actu |
| 34 | `S05230-2POS` | Honeywell | P3_NO_EAN | BF-HWC4, BF-MWC5 SERIES | Низовая автоматика и трубопроводная арматура |
| 35 | `S10010` | Honeywell | P3_NO_EAN | SmartAct S10010 / S20010 | S10010 / S20010 Damper Actuators 10/20 N-m (88/177 lb-in) fo |
| 36 | `S10010-SW2` | Honeywell | P3_NO_EAN | SmartAct S10010 / S20010 | S10010 / S20010 Damper Actuators 10/20 N-m (88/177 inch-poun |
| 37 | `SC-SCDUPLEX9/125-1` |  | P3_NO_EAN | - | - |
| 38 | `SC-SCDUPLEX9/125-2` |  | P3_NO_EAN | - | - |
| 39 | `SC-SCDUPLEX9/125-5` |  | P3_NO_EAN | - | - |
| 40 | `SCDUPLEX9/125-10` |  | P3_NO_EAN | - | - |
| 41 | `SCDUPLEX9/125-15` |  | P3_NO_EAN | - | - |
| 42 | `SDM-S93` | Honeywell | P3_NO_EAN | Справочник | Справочник военного переводчика |
| 43 | `SF00-B54` | Honeywell | P3_NO_EAN | SF00, SF10, SF20 Strap-On Temp | SF00, SF10, SF20 Strap-On Temperature Sensors |
| 44 | `SK8115` | Honeywell | P3_NO_EAN | BOUNTI BP | BOUNTI BP20/20T/25T/50T/85T Billing Printer User Guide |
| 45 | `SMB500` | Esser | P3_NO_EAN | None | SMB500-WH Surface Mount Box |
| 46 | `SNR-RMB-1UC` | Honeywell | P3_NO_EAN | Event Timers | Proceedings of the 15th International Workshop on Laser Rang |
| 47 | `T7460A1018` | Honeywell | P3_NO_EAN | Honeywell Industrial Automatio | Датчик Honeywell T7460A1018 |
| 48 | `T7560A1000` | Honeywell | P3_NO_EAN | T7560A,B | Module d'ambiance à affichage numérique |
| 49 | `T7560B1008` | Honeywell | P3_NO_EAN | PANTHER Controller | Контроллер PANTHER |
| 50 | `T7560B1024` | Honeywell | P3_NO_EAN | T7560 | T7560A,B Modules d'ambiance à affichage numérique |
| 51 | `TPPR-V-1030` | Honeywell | P3_NO_EAN | Touchpoint Pro Input/Output Mo | Touchpoint Pro Input/Output Modules |
| 52 | `TPPR-V-1040` | Honeywell | P3_NO_EAN | XNX Universal Transmitter; MPD | Модуль Honeywell TPPR-V-1040 |
| 53 | `U2410F` | Dell | P3_NO_EAN | U2410 | Dell U2410 Flat Panel Monitor |
| 54 | `U2412MB` | Dell | P3_NO_EAN | - | Монитор Honeywell U2412MB |
| 55 | `U2421M` | Dell | P3_NO_EAN | - | Монитор Honeywell U2421M |
| 56 | `V5011R1000` | Honeywell | P3_NO_EAN | V5011R | V5011R Internal Threaded End-Connection Linear Valve PN16 |
| 57 | `V5013R1057` | Honeywell | P3_NO_EAN | V5013R | Клапан Honeywell V5013R1057 |
| 58 | `V5013R1099` | Honeywell | P3_NO_EAN | V5013R | Клапан Honeywell V5013R1099 |
| 59 | `V5015A1151` | Honeywell | P3_NO_EAN | V5015A | V5015A Flanged Linear Valve PN6 |
| 60 | `V5015A1169` | Honeywell | P3_NO_EAN | BF-HWC4, BF-MWC5 | Низовая автоматика и трубопроводная арматура |
| 61 | `V5016A1101` | Honeywell | P3_NO_EAN | [] | Низовая автоматика и трубопроводная арматура |
| 62 | `V5016A1135` | Honeywell | P3_NO_EAN | BF-HWC4, BF-MWC5 SERIES | ДИСКОВОВЫЕ ПОВОРОТТНЫЕ ЗАТВОРЫ, С РУЧНЫМ УПРАВЛЕНИЕМ ЧЕРЕЗ Р |
| 63 | `V5050A1090` | Honeywell | P3_NO_EAN | V5050A | V5050A 3-WAY FLANGED LINEAR VALVE PN16 |
| 64 | `V5050A1116` | Honeywell | P3_NO_EAN | V5050A | Клапан Honeywell V5050A1116 |
| 65 | `V5328A1005` | Honeywell | P3_NO_EAN | V5328A | Клапан Honeywell V5328A1005 |
| 66 | `V5328A1013` | Honeywell | P3_NO_EAN | - | Клапан Honeywell V5328A1013 |
| 67 | `V5328A1047` | Honeywell | P3_NO_EAN | - | Клапан Honeywell V5328A1047 |
| 68 | `V5328A1088` | Honeywell | P3_NO_EAN | FLANGED LINEAR VALVE PN16 | Клапан Honeywell V5328A1088 |
| 69 | `V5328A1112` | Honeywell | P3_NO_EAN | BF-HWC4, BF-MWC5, SS-REJ | BF-HWC4, BF-MWC5 Series Manual Butterfly Valves |
| 70 | `V5329A1004` | Honeywell | P3_NO_EAN | V5329A | Клапан Honeywell V5329A1004 |
| 71 | `V5329A1046` | Honeywell | P3_NO_EAN | V5329A,C | Клапан Honeywell V5329A1046 |
| 72 | `V5329A1053` | Honeywell | P3_NO_EAN | - | Клапан Honeywell V5329A1053 |
| 73 | `V5329C1059` | Honeywell | P3_NO_EAN | V5329A,C | V5329A,C FLANGED LINEAR VALVE PN6/16 |
| 74 | `V5329C1083` | Honeywell | P3_NO_EAN | - | Trade brutto prisliste Maj 2018 |
| 75 | `V5421B1090` | Honeywell | P3_NO_EAN | V5421B | Клапан Honeywell V5421B1090 |
| 76 | `V5832A1046` | Honeywell | P3_NO_EAN | V5832A/V5833A,C Small Linear C | Клапан Honeywell V5832A1046 |
| 77 | `VF00-3B65NW` | Honeywell | P3_NO_EAN | VF00, VF10, VF20, LF00, LF10,  | Датчик Honeywell VF00-3B65NW |
| 78 | `VR420AB1002-0000` | Honeywell | P3_NO_EAN | - | VR400/VR800 Series CLASS „A“ SERVO REGULATED COMBINATION VAL |
| 79 | `VR420VA1004-0000` | Honeywell | P3_NO_EAN | CHAUDAGAZ | NOTICES TECHNIQUES D’INSTALLATION ET D’UTILISATION |
| 80 | `VSOF-320-4.0` | Honeywell | P3_NO_EAN | VSxF-3 | Клапан Honeywell VSOF-320-4.0 |
| 81 | `WD19DCS` | Dell | P3_NO_EAN | Type Approved Equipment List | Док-станция Honeywell WD19DCS |
| 82 | `X-MAP4P` | Inter-M | P3_NO_EAN | - | Centrale Convenzionale a 2 Zone |
| 83 | `XFLR822A` | Honeywell | P3_NO_EAN | Honeywell Excel 5000 Open Syst | Excel Web – LON I/O Modules |
| 84 | `XFLR824A` | Honeywell | P3_NO_EAN | Excel 800 | Excel 800 CONTROL SYSTEM |
| 85 | `XJ1-00-07000000` | Honeywell | P3_NO_EAN | MP Series | Принтер Honeywell XJ1-00-07000000 |
| 86 | `XNX-RMAV-RNNNN` | Honeywell | P3_NO_EAN | - | XNX Universal Transmitter |
| 87 | `МЕТРОВ` | Honeywell | P3_NO_EAN | LF0, LF00, LF10, LF20 | LF20, LF00, LF10, и LF0 ДАТЧИКИ ТЕМПЕРАТУРЫ ВОЗДУХА В КАНАЛЕ |

---

**Reminder:** return only a JSON array conforming to the schema above. One object per SKU, preserving input order. Missing/not-found fields → `null` with explanatory `notes`. Never fabricate.
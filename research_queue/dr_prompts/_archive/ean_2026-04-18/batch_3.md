# DR Batch EAN-3/3 — Biretos Catalog — 2026-04-18

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
| `T7560A1000` | Honeywell | T7560A,B | Module d'ambiance à affichage numérique |
| `T7560B1008` | Honeywell | PANTHER Controller | Контроллер PANTHER |
| `T7560B1024` | Honeywell | T7560 | T7560A,B Modules d'ambiance à affichage numérique |
| `TPPR-V-1030` | Honeywell | Touchpoint Pro Input/Output Modules | Touchpoint Pro Input/Output Modules |
| `TPPR-V-1040` | Honeywell | XNX Universal Transmitter; MPD Multi-Pur | Модуль Honeywell TPPR-V-1040 |
| `U2412M` | Honeywell | - | Монитор Honeywell U2412M |
| `V5011R1000` | Honeywell | V5011R | V5011R Internal Threaded End-Connection Linear Valve PN16 |
| `V5013R1057` | Honeywell | V5013R | Клапан Honeywell V5013R1057 |
| `V5013R1099` | Honeywell | V5013R | Клапан Honeywell V5013R1099 |
| `V5015A1151` | Honeywell | V5015A | V5015A Flanged Linear Valve PN6 |
| `V5015A1169` | Honeywell | BF-HWC4, BF-MWC5 | Низовая автоматика и трубопроводная арматура |
| `V5016A1101` | Honeywell | [] | Низовая автоматика и трубопроводная арматура |
| `V5016A1135` | Honeywell | BF-HWC4, BF-MWC5 SERIES | ДИСКОВОВЫЕ ПОВОРОТТНЫЕ ЗАТВОРЫ, С РУЧНЫМ УПРАВЛЕНИЕМ ЧЕРЕЗ РУКОЯТКУ ИЛИ РЕДУКТОР |
| `V5050A1090` | Honeywell | V5050A | V5050A 3-WAY FLANGED LINEAR VALVE PN16 |
| `V5050A1116` | Honeywell | V5050A | Клапан Honeywell V5050A1116 |
| `V5328A1005` | Honeywell | V5328A | Клапан Honeywell V5328A1005 |
| `V5328A1013` | Honeywell | - | Клапан Honeywell V5328A1013 |
| `V5328A1047` | Honeywell | - | Клапан Honeywell V5328A1047 |
| `V5328A1088` | Honeywell | FLANGED LINEAR VALVE PN16 | Клапан Honeywell V5328A1088 |
| `V5328A1112` | Honeywell | BF-HWC4, BF-MWC5, SS-REJ | BF-HWC4, BF-MWC5 Series Manual Butterfly Valves |
| `V5329A1004` | Honeywell | V5329A | Клапан Honeywell V5329A1004 |
| `V5329A1046` | Honeywell | V5329A,C | Клапан Honeywell V5329A1046 |
| `V5329A1053` | Honeywell | - | Клапан Honeywell V5329A1053 |
| `V5329C1059` | Honeywell | V5329A,C | V5329A,C FLANGED LINEAR VALVE PN6/16 |
| `V5329C1083` | Honeywell | - | Trade brutto prisliste Maj 2018 |
| `V5421B1090` | Honeywell | V5421B | Клапан Honeywell V5421B1090 |
| `V5832A1046` | Honeywell | V5832A/V5833A,C Small Linear Control Val | Клапан Honeywell V5832A1046 |
| `VF00-3B65NW` | Honeywell | VF00, VF10, VF20, LF00, LF10, LF20 | Датчик Honeywell VF00-3B65NW |
| `VQ440MB1005` | Honeywell | - | Solenoid gas valve, normally closed VE400AA |
| `VQ450MA1015` | Honeywell | SLATE system | SLATE system |
| `VQ450MB1006` | Honeywell | SLATE system, VE series gas valves, R800 | SLATE(TM) Combustion Management System - Base Module |
| `VR420AB1002-0000` | Honeywell | - | VR400/VR800 Series CLASS „A“ SERVO REGULATED COMBINATION VALVES |
| `VR420VA1004-0000` | Honeywell | CHAUDAGAZ | NOTICES TECHNIQUES D’INSTALLATION ET D’UTILISATION |
| `VSOF-320-4.0` | Honeywell | VSxF-3 | Клапан Honeywell VSOF-320-4.0 |
| `XFLR822A` | Honeywell | Honeywell Excel 5000 Open System - Excel | Excel Web – LON I/O Modules |
| `XFLR824A` | Honeywell | Excel 800 | Excel 800 CONTROL SYSTEM |
| `XJ1-00-07000000` | Honeywell | MP Series | Принтер Honeywell XJ1-00-07000000 |
| `XNX-RMAV-RNNNN` | Honeywell | - | XNX Universal Transmitter |
| `МЕТРОВ` | Honeywell | LF0, LF00, LF10, LF20 | LF20, LF00, LF10, и LF0 ДАТЧИКИ ТЕМПЕРАТУРЫ ВОЗДУХА В КАНАЛЕ |
| `1012541` | Howard Leight | - | Система обеспечения персонала средствами индивидуальной защиты на объектах гидро |
| `1015021` | Howard Leight | - | Honeywell Catalog 2025 |
| `CAB-010-SC-SM` | Hyperline | HYPERLINE Cabling Systems | CATALOG 2009 |
| `FO-WBI-12A-GY` | Hyperline | - | Бокс Hyperline FO-WBI-12A-GY |
| `SC-SC` | Hyperline | - | E3 Series® Control Panel |
| `X-MAP4P` | Inter-M | - | Centrale Convenzionale a 2 Zone |
| `KD-050` | Kale Kilit | - | Лампа Kale Kilit KD-050 |
| `NE-NICS02` | NEC | Honeywell TPS | Сетевая карта Honeywell NE-NICS02 |
| `NMF-RP16SCUS2-RU` | NIKOMAX | - | Оптический кросс NIKOMAX NMF-RP16SCUS2-RU |
| `P400-RU` | NVIDIA | Quadro | NVIDIA Quadro P400 Professional Graphics Card |
| `EVCS-HSB` | Notifier | EVCS Type B Outstation | TYPE B OUTSTATION |
| `EVCS-MS` | Notifier | Network 8 | NETWORK 8 MASTER HANDSET |
| `L-VOM40A/EN` | Notifier | HN-CL | 6W Ceiling Loudspeaker |
| `2SM-3.0-SCU-SCU-1` | Optcom | - | Шнур Optcom 2SM-3.0-SCU-SCU-1 |
| `2SM-3.0-SCU-SCU-15` | Optcom | - | Шнур Optcom 2SM-3.0-SCU-SCU-15 |
| `SM-0.9-SC-UPC-1.5` | Optcom | - | Сборник трудов IX Международной научной конференции «ИТ – СТАНДАРТ 2019» |
| `2904617` | Phoenix Contact | Safety Manager Release 162 | Источник питания Honeywell 2904617 |
| `3240199` | Phoenix Contact | - | Канал Honeywell 3240199 |
| `3240348` | Phoenix Contact | - | Канал Honeywell 3240348 |
| `LUX` | Produal | - | SW-DCT-USB Configuration Cable |
| `PCD3.W340` | SAIA | PCD3 | Analoges Eingangsmodul, 8 Kanäle, 12 Bit, 0...2.5 V, 0...10 V, 0...20 mA, Pt/Ni  |
| `PCD2.A200` | Saia-Burgess | PCD2 | Digitales Ausgangsmodul, 4 Relais, 250 VAC/2 A, Schliesserkontakt, Kontaktschutz |
| `PCD7.L500` | Saia-Burgess | Saia PCD | Saia PCD3.Mxx60 controllers |
| `PCD3.M3360` | Saia-Burgess Controls | PCD3.M3 | PCD3.M3360 CPU basic power module with Ethernet TCP/IP, 1023 I/Os, 512 kByte of  |
| `LA5496411314` | Schneider Electric | - | Крепления Schneider Electric LA5496411314 |
| `FCP3-RACK` | Siemon | Fiber Connect Panel (FCP3) | Fiber Connect Panel (FCP3) |
| `FP1B-LCUL-01H` | Siemon | XGLO | Пигтейл Honeywell FP1B-LCUL-01H |
| `HCM-4-2U` | Siemon | RouteIT | RouteIT™ Cable Managers |
| `RIC-F-BLNK-01` | Siemon | RIC3 | Rack Mount Interconnect Center (RIC3) |
| `RIC-F-LCU24-01C` | Siemon | - | Панель Honeywell RIC-F-LCU24-01C |
| `SC-SCDUPLEX9/125-1` | Sonlex | - | Кабель Sonlex SC-SCDUPLEX9/125-1 |
| `SC-SCDUPLEX9/125-2` | Sonlex | - | Кабель Sonlex SC-SCDUPLEX9/125-2 |
| `SC-SCDUPLEX9/125-5` | Sonlex | - | Кабель Sonlex SC-SCDUPLEX9/125-5 |
| `SCDUPLEX9/125-10` | Sonlex | - | Кабель Sonlex SCDUPLEX9/125-10 |
| `SCDUPLEX9/125-15` | Sonlex | - | Кабель Sonlex SCDUPLEX9/125-15 |
| `1011893-RU` | Sperian | - | Привязь Sperian 1011893-RU |
| `CWSS-RB-S8` | System Sensor | EVCS Network 8 | Emergency Voice Communication Systems EVCS Network 8 Data Sheet |
| `RA100Z` | System Sensor | DNR | DNR Duct Smoke Detector |
| `7508001857` | Weidmuller | - | Модуль ввода Weidmuller 7508001857 |
| `7508001858` | Weidmuller | - | Модуль ввода Weidmuller 7508001858 |
| `7508002114` | Weidmuller | - | 8-местная стойка с резервным источником питания |
| `7910180000` | Weidmüller | W-Series | WTR 4 |
| `PHASER` | Xerox | LT AC Three Phase Four Wire 40-200 Amps  | TECHNICAL SPECIFICATION OF LT AC THREE PHASE, FOUR WIRE, 40 - 200 AMPS ENERGY ME |
| `KZDS` | unknown | - | Гильза unknown KZDS |

---

**Reminder:** return only a JSON array conforming to the schema above. One object per SKU, preserving input order. Missing/not-found → `null` fields with explanatory `notes`. Never fabricate.
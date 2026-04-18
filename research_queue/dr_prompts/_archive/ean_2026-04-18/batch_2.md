# DR Batch EAN-2/3 — Biretos Catalog — 2026-04-18

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
| `A133230-00` | Honeywell | COMMANDER | COMMANDER Shotblasting Helmet |
| `AF00-B65` | Honeywell | AF00, AF10, AF12, AF20 | AF00, AF10, AF12 and AF20 OUTSIDE TEMPERATURE SENSORS |
| `AT-MMC200LX` | Honeywell | - | Медиаконвертер Honeywell AT-MMC200LX |
| `AT-MMCR18-60-RU` | Honeywell | - | Шасси Honeywell AT-MMCR18-60-RU |
| `AT-TRAY4` | Honeywell | Sky Connect Tracker III | Sky Connect™ Tracking System |
| `BF-HWC4-PN16-0125` | Honeywell | - | Задвижка Honeywell BF-HWC4-PN16-0125 |
| `BWC4-Y-R` | Honeywell | BW™ Clip4 | BW™ Clip4 |
| `C7355A1050` | Honeywell | - | C7355A Room IAQ Monitor |
| `CABLE-0.22-8T` | Honeywell | Honeywell I/O Modules (16UIO, 16UI, 16DI | I/O Modules, Expansion Modules & Wiring Adapter |
| `CATALIST` | Honeywell | None | UOP R-264 CCR Platforming™ Catalyst |
| `CN80-HB-CNV-0` | Honeywell | Dolphin CN80 | CN80 Handheld Computer |
| `CPO-RL4` | Honeywell | ComfortPoint Open CPO-Rxx Room Controlle | ComfortPoint Open CPO-Rxx ROOM CONTROLLERS |
| `CR-M4LC` | Honeywell | ABB Electrification Products - Contracto | Electrification UK Contractor handbook |
| `CR-P/M42` | Honeywell | № 2 (370) 2025 | Fundamental and Applied Problems of Engineering and Technology |
| `CWR` | Honeywell | Sounders | Non-Addressable Audible Visual Devices (Sounders) |
| `DCPSU-24-1.3` | Honeywell | - | Блок питания Honeywell DCPSU-24-1.3 |
| `DPTE1000S` | Honeywell | DPTE | 3-WIRE DIFFERENTIAL PRESSURE TRANSMITTERS WITH CURRENT AND VOLTAGE OUTPUT |
| `DTI6` | Honeywell | DTI/DTU Differential Pressure Transmitte | DIFFERENTIAL PRESSURE TRANSMITTER |
| `EDA61K-HB-2` | Honeywell | - | Зарядное устройство Honeywell EDA61K-HB-2 |
| `EDA61K-SH-DC` | Honeywell | ScanPal EDA61K | SCANPAL EDA61K Enterprise Mobile Computer |
| `FT6960-60` | Honeywell | - | Adapter ring |
| `FUSE-0.5A-5X20` | Honeywell | - | Предохранитель Honeywell FUSE-0.5A-5X20 |
| `FUSE-20A-5X20` | Honeywell | H-S81-HS & S81-HS/C Industrial Fire Pane | H-S81-HS & S81-HS/C Industrial Fire Panels |
| `FUSE-2A-5X20-RU` | Honeywell | GASTER N | GASTER N 119 ÷ 289 AW |
| `FUSE-6.3A-5X20` | Honeywell | ARC300 | ELECTRONIC CONTROL SYSTEM ARC 300 |
| `FX808313` | Honeywell | - | Akku-Erweiterungsgehäuse für 2 x 12 V/24 Ah |
| `FX808338` | Honeywell | IQ8Control | Declaration of Performance |
| `FX808363` | Honeywell | - | Power supply extension 24 V/12 Ah |
| `H3D1F1X` | Honeywell | equIP® Series H3D1F | H3D1F equlP® SERIES 720p VFAI TRUE DAY/NIGHT H.264 INDOOR FIXED MINIDOME IP CAME |
| `H4L6GR2` | Honeywell | equIP Cameras | H4L6GR2 Network TDN Low-Light 6 MP IR Rugged Dome Camera |
| `H4W4GR1Y` | Honeywell | EQUIP Series | 4MP Network TDN Ultra Low-light WDR IR Rugged Dome Cameras |
| `H4W4PER2` | Honeywell | Performance Series | WDR 4 MP IR Rugged Mini Dome Camera |
| `HBL6GR2` | Honeywell | Network TDN Low-Light 2 MP IR LPR Rugged | Network TDN Low-Light 2 MP IR LPR Rugged Bullet Camera |
| `HVAC23C5` | Honeywell | NXL HVAC INVERTERS | Инвертор Honeywell HVAC23C5 |
| `HVAC31C5` | Honeywell | NXL HVAC | Инвертор Honeywell HVAC31C5 |
| `HVAC46C5` | Honeywell | NXL HVAC | NXL HVAC INVERTERS |
| `IMC-101-S-SC` | Honeywell | ControlEdge PLC 900 Series | ControlEdge PLC Specification |
| `KCD2090XI` | Honeywell | - | Монитор Honeywell KCD2090XI |
| `KTF00-65-2M` | Honeywell | KTFxx | KTFxx CABLE-TYPE BULB TEMPERATURE SENSORS |
| `LATITUDE` | Honeywell | RESCU 406 | Ноутбук Honeywell LATITUDE |
| `LEONARDO-OT` | Honeywell | - | Successes in Chemistry and Chemical Technology |
| `LF20-3P65-5M` | Honeywell | LF20, PF20 Duct Temperature Sensors | LF20, PF20 DUCT TEMPERATURE SENSORS |
| `M7294Q1015/U` | Honeywell | Honeywell Industrial Controls, Kromschrö | SLATE(TM) Combustion Management System |
| `MAU8/MS` | Honeywell | Smart DCM DIFF | Smart DCM DIFF |
| `MB3480` | Honeywell | Type Approved Equipment | TABLET PC - HUAWEI DBY-W09 |
| `ML6420A3072` | Honeywell | WP FLYPPER | COMPLETE SET OF PACKINGS |
| `ML6421A3005` | Honeywell | BF-HWC4, BF-MWC5 | Привод Honeywell ML6421A3005 |
| `ML6421A3013` | Honeywell | BF-HWC4, BF-MWC5, SS-REJ | Дисковые поворотные затворы, с ручным управлением через рукоятку или редуктор |
| `ML6425A3014` | Honeywell | - | Дисковые поворотные затворы с ручным управлением |
| `MZ-PCWS77` | Honeywell | SYSTEM HINTS NEWSLETTER | SYSTEM HINTS NEWSLETTER APRIL 2024 |
| `MZ-PCWS84` | Honeywell | Experion Collaboration Station | Experion Collaboration Station |
| `N05010` | Honeywell | VSxF-2 | Низовая автоматика |
| `N05230-2POS` | Honeywell | BF-HWC4, BF-MWC5 | Дисковые поворотные затворы, с ручным управлением через рукоятку или редуктор |
| `N0524` | Honeywell | BF-HWC4, BF-MWC5 SERIES | ДИСКОВОВЫЕ ПОВОРОТНЫЕ ЗАТВОРЫ, С РУЧНЫМ УПРАВЛЕНИЕМ ЧЕРЕЗ РУКОЯТКУ ИЛИ РЕДУКТОР |
| `N0524-SW2` | Honeywell | N0524/N1024, N05230-2POS/N10230-2POS | Привод Honeywell N0524-SW2 |
| `N10010` | Honeywell | BF-HWC4, BF-MWC5 SERIES | Дисковые поворотные затворы, с ручным управлением через рукоятку или редуктор |
| `N34230` | Honeywell | BF-HWC4, BF-MWC5 SERIES | ДИСКОВЫЕ ПОВОРОТНЫЕ ЗАТВОРЫ, С РУЧНЫМ УПРАВЛЕНИЕМ ЧЕРЕЗ РУКОЯТКУ ИЛИ РЕДУКТОР |
| `N3424` | Honeywell | BF-HWC4, BF-MWC5 | Низовая автоматика и трубопроводная арматура |
| `OPTIPLEX` | Honeywell | - | Системный блок Honeywell OPTIPLEX |
| `P2210F` | Honeywell | - | Монитор Honeywell P2210F |
| `P2213F` | Honeywell | - | Системный блок Honeywell P2213F |
| `P2213T` | Honeywell | - | Монитор Honeywell P2213T |
| `P600` | Honeywell | Street Smart Home Control | Street Smart Home Control |
| `PANC300-03` | Honeywell | Experion PKS | PROCESS CONTROLLER OF THE FUTURE |
| `PANC300-04` | Honeywell | - | Панель Honeywell PANC300-04 |
| `PAVILION` | Honeywell | Hanwha Techwin Product Portfolio 2023 | 4K AI IR Bullet Camera |
| `PERTHECTION` | Honeywell | - | Сканер Honeywell PERTHECTION |
| `PIP-003` | Honeywell | VESDA-E | Safety Solutions Product Catalogue |
| `PRECITHION` | Honeywell | - | Системный блок Honeywell PRECITHION |
| `PRECITION` | Honeywell | - | Fault Tolerant Power Systems |
| `PW5K1ENC3E` | Honeywell | Pro-Watch 5000 | Pro-Watch 5000 Remote Enclosure |
| `R4343E1048-ST005` | Honeywell | SLATE system | SLATE system |
| `RMK400AP-IV` | Honeywell | LEONARDO | Извещатель пожарный дымовой оптико-электронный ЕСО1003М |
| `ROL15-2761-04` | Honeywell | I-Class Mark II | I-Class™ Mark II Replacement Parts Catalog |
| `S0324-2POS-SW1` | Honeywell | S03, S05 Series Low-Torque Spring-Return | S03, S05 Series Low-Torque Spring-Return Direct-Coupled Actuators |
| `S05230-2POS` | Honeywell | BF-HWC4, BF-MWC5 SERIES | Низовая автоматика и трубопроводная арматура |
| `S10010` | Honeywell | SmartAct S10010 / S20010 | S10010 / S20010 Damper Actuators 10/20 N-m (88/177 lb-in) for Proportional and F |
| `S10010-SW2` | Honeywell | SmartAct S10010 / S20010 | S10010 / S20010 Damper Actuators 10/20 N-m (88/177 inch-pound) for Proportional  |
| `SDM-S93` | Honeywell | Справочник | Справочник военного переводчика |
| `SF00-B54` | Honeywell | SF00, SF10, SF20 Strap-On Temperature Se | SF00, SF10, SF20 Strap-On Temperature Sensors |
| `SK8115` | Honeywell | BOUNTI BP | BOUNTI BP20/20T/25T/50T/85T Billing Printer User Guide |
| `SNR-RMB-1UC` | Honeywell | Event Timers | Proceedings of the 15th International Workshop on Laser Ranging |
| `T7460A1018` | Honeywell | Honeywell Industrial Automation & Contro | Датчик Honeywell T7460A1018 |

---

**Reminder:** return only a JSON array conforming to the schema above. One object per SKU, preserving input order. Missing/not-found → `null` fields with explanatory `notes`. Never fabricate.
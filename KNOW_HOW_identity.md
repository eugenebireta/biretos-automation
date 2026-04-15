# Know-How: Product Identity / PN Rules

<!-- Sub-file of KNOW_HOW.md. Same format: YYYY-MM-DD | #тег | scope: Суть -->
<!-- Records here are DUPLICATED from KNOW_HOW.md (not moved) per CLAUDE.md rule. -->

## PN suffix rules

2026-04-09 | #rule | pn-suffix: .10=color, -RU=Russian market, -L3=kit, N/U=replacement

## Brand grammar

2026-04-12 | #rule | pn-brand: CWSS grammar CONFIRMED from Honeywell Declaration of Performance: CWSS-[body][flash]-[base][fix]. Body/flash: R=red, W=white. Base: S=shallow, W=deep IP65. Fix: 5=standard, 6=first-fix.
2026-04-12 | #rule | pn-brand: Distech ECL-xxx = LonWorks TP/FT-10 controllers (sister family to ECB BACnet). ECL is separate prefix from ECB.
2026-04-12 | #rule | pn-brand: Eaton Redapt full confirmed grammar: [family][cert][material][plating][male_thread][female_thread].
2026-04-12 | #rule | pn-brand: FT6960 = manual-reset frost thermostat; FT6961 = auto-reset. Suffix 18/30/60 = capillary tube length.
2026-04-12 | #rule | pn-brand: Beckhoff terminal first-digit rule: EL/EP/KL 1xxx=digital input, 2xxx=digital output, 3xxx=analog input, 4xxx=analog output, 5xxx=encoder, 6xxx=communication, 7xxx=drive, 9xxx=infrastructure.
2026-04-12 | #rule | pn-brand: Weidmuller 10-digit PNs almost always end in 0000 for standard products. Non-zero last 4 = variant.
2026-04-12 | #rule | pn-brand: Weidmüller `7508xxxxxx` prefix alone is NOT a safe brand signal. Use `FTA-C300-...` type string for reliable detection.
2026-04-12 | #rule | pn-brand: Kale Kilit real catalog form is KD050/45-106 (slash, no dash). Our import has KD-050 (dash-normalized). Match `KD-?\\d{3}`.
2026-04-12 | #rule | pn-brand: SC-SCDUPLEX9/125-x = Sonlex. 2SM-3.0-SCU-SCU-x and SM-0.9-SC-UPC-x = Optcom/ОПТКОМ. NOT Hyperline.
2026-04-10 | #rule | identity: PEHA Nova Elements PN pattern: 6-digit base maps to 8-digit (00+6digits). Type digit 671/672/673/674 = 1/2/3/4-gang.

## Brand attribution

2026-04-12 | #rule | pn-brand: EVCS-HSB/EVCS-MS = Notifier (Honeywell Fire Safety), NOT Morley-IAS.
2026-04-12 | #rule | pn-brand: CPO-RL = ComfortPoint Open = Honeywell (NOT Distech). CPO-RL1 to CPO-RL8 series.
2026-04-12 | #rule | pn-brand: Distech Controls = subsidiary of Acuity Brands (NOT Honeywell). ECB-xxx are Distech/Acuity.
2026-04-12 | #rule | pn-brand: Novar GmbH ≠ Esser. Both are Honeywell subsidiaries but separate: Novar=intrusion/access, Esser=fire detection.
2026-04-12 | #rule | pn-brand: D-71570 ≠ Murrelektronik product PN. It is the company postal address.
2026-04-12 | #rule | pn-brand: 7508001857/58/2114 = Weidmuller FTA-C300, NOT Honeywell — despite being used in Honeywell DCS.
2026-04-12 | #rule | pn-brand: Esser 6-digit ranges: 802xxx=IQ8Quad w/isolator, 803xxx=without, 804xxx=MCP electronics, 805xxx=detector bases, 704xxx=MCP housings.
2026-04-12 | #rule | pn-brand: LUX 24 = Produal room light level sensor. NOT Honeywell. Discontinued.

## Identity corrections (specific SKUs)

2026-04-10 | #rule | identity: ROL15-2761-04 is Datamax/Honeywell I-Class platen roller, NOT a valve. Price: 85.85 USD.
2026-04-10 | #rule | identity: RDU300504 is Eaton/Redapt ATEX SS316 cable reducer M25→M20, NOT Honeywell.
2026-04-10 | #rule | identity: 902591 is PEHA speaker socket (Busch-Jaeger/ABB), NOT Esser fire detector.
2026-04-10 | #rule | identity: F750E-S0 is Dell PowerEdge server PSU, NOT Honeywell.
2026-04-10 | #rule | identity: 188091, 191191 are PEHA NOVA cover frames, NOT flame detectors.
2026-04-10 | #rule | identity: 583520 confirmed Esser VARIODYN D1 DCS plus digital call station. Price 1450 EUR.
2026-04-10 | #rule | identity: EVCS-MS=1009.62 GBP master handset, EVCS-HSB=155 GBP handset cradle.
2026-04-10 | #rule | identity: 816713 is PEHA Aura decorative frame, Agate Grey. Price: 5.40 EUR.
2026-04-10 | #rule | identity: 902591 identity conflict — Claude="speaker socket", Gemini="rocker switch". Both agree: PEHA.
2026-04-10 | #rule | identity: LCD is Axiomtek P6191PR industrial 19" panel PC. Price: 509 USD.
2026-04-10 | #rule | identity: 3240197 is Phoenix Contact CD 25X80 PVC cable duct. NOT Honeywell.
2026-04-10 | #rule | identity: R4343E1048-ST005 is DISCONTINUED Honeywell Kromschröder UV flame switch. Critical life-safety device.
2026-04-10 | #rule | identity: T7560B1024 is EU/EMEA variant of Honeywell Excel 10/600 digital wall module.

## Bugs

2026-04-12 | #bug | pn_brand_lib: `detect_brand()` returned first-match, not best-match. Fix: rank by confidence (HIGH>MEDIUM>LOW) then pattern length.
2026-04-09 | #bug | dr_prompt_generator: v6 used expected_category as hint — wrong for 33+ PEHA. Fix: use assembled_title only.

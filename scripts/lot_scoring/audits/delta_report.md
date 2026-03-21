# Hybrid Audit Mode - Delta Report

## Lots by Unknown Exposure

| lot_id | unknown_pct | score_10 | cqr | total_effective_usd |
|---:|---:|---:|---:|---:|
| 33 | 100.0% | 4.93 | 0.500 | 92681268.99 |
| 31 | 100.0% | 3.97 | 0.500 | 11803093.07 |
| 14 | 100.0% | 7.05 | 0.500 | 3296260.46 |
| 32 | 100.0% | 6.94 | 0.500 | 2261282.12 |
| 26 | 100.0% | 7.05 | 0.500 | 1772669.35 |
| 27 | 100.0% | 6.67 | 0.500 | 1149289.42 |
| 8 | 100.0% | 7.22 | 0.500 | 961946.93 |
| 28 | 100.0% | 6.62 | 0.500 | 704825.70 |
| 23 | 100.0% | 6.49 | 0.500 | 646835.14 |
| 25 | 92.9% | 7.28 | 0.536 | 556850.75 |
| 16 | 91.5% | 7.05 | 0.543 | 276310.46 |
| 13 | 88.1% | 6.59 | 0.484 | 832997.10 |
| 30 | 88.0% | 6.27 | 0.560 | 861182.05 |
| 20 | 79.2% | 5.66 | 0.573 | 735588.77 |
| 21 | 78.9% | 6.99 | 0.565 | 416649.35 |
| 12 | 72.5% | 6.56 | 0.600 | 881782.04 |
| 19 | 44.0% | 6.85 | 0.276 | 1561631.27 |
| 17 | 42.8% | 6.84 | 0.271 | 3435079.93 |
| 6 | 17.7% | 7.26 | 0.461 | 1256211.65 |
| 3 | 16.1% | 7.59 | 0.766 | 3679024.83 |
| 7 | 8.4% | 7.00 | 0.273 | 699019.59 |
| 2 | 0.0% | 6.30 | 0.100 | 43429795.84 |
| 1 | 0.0% | 5.84 | 0.100 | 22818241.36 |
| 5 | 0.0% | 3.73 | 0.100 | 19067848.83 |
| 9 | 0.0% | 6.58 | 0.246 | 9557241.86 |
| 18 | 0.0% | 6.50 | 0.100 | 8588504.34 |
| 10 | 0.0% | 7.85 | 0.772 | 4082956.10 |
| 24 | 0.0% | 6.54 | 0.100 | 2834321.21 |
| 4 | 0.0% | 6.32 | 0.100 | 2477158.28 |
| 15 | 0.0% | 6.44 | 1.000 | 1370149.19 |
| 11 | 0.0% | 6.86 | 0.500 | 1161115.30 |
| 22 | 0.0% | 4.93 | 0.100 | 1158128.91 |
| 29 | 0.0% | 7.24 | 1.000 | 295176.53 |

## LLM Audit Status

- status: completed

## Audited Lots

- 10, 3, 25, 6, 29, 8, 16, 14, 26, 7, 21, 32, 19, 17, 27, 28, 13, 12, 23, 30, 20, 33, 31

## Lot-level Engine vs LLM (Top 10 rows per audited lot)

### Lot 10

- value impacted by category changes: 1716185.53 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | CCPCF901 | 1716185.53 | fire_safety | unknown | 0.50 | Category mismatch |
| 2 | CPOPC400 | 1439589.74 | hvac_components | hvac_components | 1.00 | Correct category |

### Lot 3

- value impacted by category changes: 0.00 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | C6097A4210B | 1884754.67 | gas_safety | gas_safety | 1.00 | Category matches gas safety. |
| 2 | 8680I505RHSGH | 482296.41 | it_hardware | it_hardware | 1.00 | Category matches IT hardware. |
| 3 | I22605 | 454838.62 | unknown | unknown | 0.50 | Category is not identifiable. |

### Lot 25

- value impacted by category changes: 72847.41 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | PDP04 | 128785.28 | unknown | unknown | 0.00 | Insufficient information |
| 2 | PDP04 | 128785.28 | unknown | unknown | 0.00 | Insufficient information |
| 3 | HNMPE128C144T12R6 | 72847.41 | unknown | it_hardware | 0.80 | NVR system identified |
| 4 | MCXLXW00YRU | 27076.25 | gas_safety | gas_safety | 1.00 | Gas safety sensor identified |
| 5 | C8800 | 22210.45 | unknown | unknown | 0.00 | Insufficient information |

### Lot 6

- value impacted by category changes: 92680.13 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | VHX0200 | 329087.18 | it_hardware | it_hardware | 1.00 | IT hardware |
| 2 | 40PC100G1A | 122707.35 | industrial_sensors | industrial_sensors | 1.00 | Pressure sensor |
| 3 | 2455R99130401 | 92680.13 | unknown | hvac_components | 1.00 | Commercial thermostat |
| 4 | 40PC250G2A | 78112.09 | industrial_sensors | industrial_sensors | 1.00 | Pressure sensor |
| 5 | HEL705T01200 | 51183.31 | industrial_sensors | industrial_sensors | 1.00 | Temperature sensor |
| 6 | PW7K1R2 | 41086.97 | unknown | unknown | 0.50 | Insufficient information |
| 7 | AWM720P1 | 40220.60 | industrial_sensors | industrial_sensors | 1.00 | Airflow sensor |

### Lot 29

- value impacted by category changes: 0.00 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | MCXV0000Y00 | 129444.18 | gas_safety | gas_safety | 1.00 | Correct classification |
| 2 | S080045000 | 74248.11 | fire_safety | fire_safety | 1.00 | Correct classification |

### Lot 8

- value impacted by category changes: 421742.86 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | 04200A1015 | 129000.35 | unknown | hvac_components | 0.80 | Duct mount kit suggests HVAC application. |
| 2 | 04200A1015 | 114863.32 | unknown | hvac_components | 0.80 | Duct mount kit suggests HVAC application. |
| 3 | FTAPKS16DODCFJ6S | 78480.58 | unknown | unknown | 0.50 | Insufficient information to classify. |
| 4 | 900J100001 | 75438.46 | unknown | unknown | 0.50 | Insufficient information to classify. |
| 5 | MCXL000MYRU | 74459.68 | unknown | gas_safety | 0.90 | CO sensor indicates gas safety application. |
| 6 | SPXCDALMB1 | 61806.51 | unknown | industrial_sensors | 0.85 | CO2 sensor indicates industrial sensor application. |
| 7 | 1003232RU | 41613.00 | unknown | fire_safety | 0.75 | Lanyard suggests safety equipment. |
| 8 | R7476B1005 | 31017.26 | unknown | unknown | 0.50 | Insufficient information to classify. |

### Lot 16

- value impacted by category changes: 44789.63 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | RA100Z | 33241.44 | unknown | unknown | 0.50 | Insufficient information |
| 2 | CN80HBCNV0 | 18354.77 | unknown | it_hardware | 0.70 | Home base for devices |
| 3 | FX808332 | 15721.31 | fire_safety | fire_safety | 0.90 | Fire safety equipment |
| 4 | XJ10007000000 | 14949.31 | unknown | unknown | 0.50 | Insufficient information |
| 5 | ROL15276104 | 14693.22 | unknown | unknown | 0.50 | Insufficient information |
| 6 | FX808324 | 14484.50 | unknown | unknown | 0.50 | Insufficient information |
| 7 | H4W4GR1Y | 14033.63 | unknown | it_hardware | 0.80 | IP camera |
| 8 | FX808431 | 13821.80 | unknown | unknown | 0.50 | Insufficient information |
| 9 | EDA61KHB2 | 12401.23 | unknown | it_hardware | 0.70 | Charging device for hardware |
| 10 | PW5K1ENC3E | 11993.23 | unknown | unknown | 0.50 | Insufficient information |

### Lot 14

- value impacted by category changes: 0.00 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | FTAC30016DIFSLIMG3S | 1501793.05 | unknown | unknown | 0.00 | Insufficient information |
| 2 | FTAC30016DIFSLIMG3S | 850071.54 | unknown | unknown | 0.00 | Insufficient information |

### Lot 26

- value impacted by category changes: 1228666.82 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | 1470G | 726562.68 | unknown | packaging_materials | 0.80 | Label for product marking |
| 2 | 470G1472G | 502104.14 | unknown | packaging_materials | 0.80 | Scanner housing component |

### Lot 7

- value impacted by category changes: 0.00 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | PM43A11000000302 | 154910.68 | it_hardware | it_hardware | 1.00 | Category matches |
| 2 | PM43A11000000302 | 154910.68 | it_hardware | it_hardware | 1.00 | Category matches |
| 3 | TC840C3206IV | 44001.28 | fire_safety | fire_safety | 1.00 | Category matches |
| 4 | 6500RS | 37304.49 | unknown | unknown | 1.00 | Category unknown |
| 5 | SAV0501 | 26597.96 | it_hardware | it_hardware | 1.00 | Category matches |
| 6 | ECO1003M | 24640.00 | fire_safety | fire_safety | 1.00 | Category matches |

### Lot 21

- value impacted by category changes: 0.00 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | ESMI22051EI | 45814.15 | fire_safety | fire_safety | 1.00 | Fire safety device |
| 2 | OKP2N34 | 38703.18 | unknown | unknown | 0.50 | Insufficient information |
| 3 | H3W4GR1Y | 34701.44 | unknown | unknown | 0.50 | Insufficient information |
| 4 | VMU400A1010 | 29721.33 | unknown | unknown | 0.50 | Insufficient information |
| 5 | H4W4PER2V | 27176.10 | unknown | unknown | 0.50 | Insufficient information |
| 6 | STND15F030096 | 16503.73 | unknown | unknown | 0.50 | Insufficient information |
| 7 | TM9910 | 16022.22 | unknown | unknown | 0.50 | Insufficient information |
| 8 | PC42TPE01313 | 12508.12 | it_hardware | it_hardware | 1.00 | IT hardware component |
| 9 | H3W4GR1Y | 12247.57 | unknown | unknown | 0.50 | Insufficient information |
| 10 | EA2001E005A00 | 11328.26 | unknown | unknown | 0.50 | Insufficient information |

### Lot 32

- value impacted by category changes: 1714833.08 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | MCX30000Y00 | 116013.49 | unknown | industrial_sensors | 0.90 | Portable detector |
| 2 | 1470G2DR2USBR | 79940.98 | unknown | it_hardware | 0.80 | Barcode scanner |
| 3 | 1470G2DR2USBR | 79940.98 | unknown | it_hardware | 0.80 | Barcode scanner |
| 4 | 1470G2DR2USBR | 79940.98 | unknown | it_hardware | 0.80 | Barcode scanner |
| 5 | 1470G2DR2USBR | 79940.98 | unknown | it_hardware | 0.80 | Barcode scanner |
| 6 | 1470G2DR2USBR | 79940.98 | unknown | it_hardware | 0.80 | Barcode scanner |
| 7 | 1470G2DR2USBR | 79940.98 | unknown | it_hardware | 0.80 | Barcode scanner |
| 8 | 1470G2DR2USBR | 79940.98 | unknown | it_hardware | 0.80 | Barcode scanner |
| 9 | 1470G2DR2USBR | 79940.98 | unknown | it_hardware | 0.80 | Barcode scanner |
| 10 | 1470G2DR2USBR | 79940.98 | unknown | it_hardware | 0.80 | Barcode scanner |

### Lot 19

- value impacted by category changes: 0.00 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | MS7820118 | 280717.95 | unknown | unknown | 0.50 | Unclear product type |
| 2 | PM43A11000040302 | 154910.63 | it_hardware | it_hardware | 0.90 | Identified as IT hardware |
| 3 | PM43A11000040302 | 154910.63 | it_hardware | it_hardware | 0.90 | Identified as IT hardware |
| 4 | PM43A11000040302 | 154910.63 | it_hardware | it_hardware | 0.90 | Identified as IT hardware |
| 5 | PM43A11000000202 | 102855.45 | it_hardware | it_hardware | 0.90 | Identified as IT hardware |
| 6 | MS3580 | 93424.23 | unknown | unknown | 0.50 | Unclear product type |
| 7 | YJHF50011USB | 71806.37 | unknown | unknown | 0.50 | Unclear product type |

### Lot 17

- value impacted by category changes: 1090521.56 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | TPC1881WP473AE | 1459873.04 | it_hardware | it_hardware | 0.90 | Identified as IT hardware |
| 2 | 1472G2D2USB5R | 441352.42 | unknown | it_hardware | 0.90 | Identified as IT hardware |
| 3 | EDA511B663SQGRK | 265989.27 | unknown | it_hardware | 0.90 | Identified as IT hardware |
| 4 | EDA51K0B931SQGRK | 161044.51 | unknown | it_hardware | 0.90 | Identified as IT hardware |
| 5 | EDA50K0C121NGRR | 111067.68 | unknown | it_hardware | 0.90 | Identified as IT hardware |
| 6 | EDA50K0C121NGRR | 111067.68 | unknown | it_hardware | 0.90 | Identified as IT hardware |

### Lot 27

- value impacted by category changes: 182453.38 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | 1470G | 171625.79 | unknown | unknown | 0.00 | Unrelated to any category |
| 2 | 1450G | 131110.48 | unknown | unknown | 0.00 | Unrelated to any category |
| 3 | MCXV0000Y00 | 67157.87 | unknown | industrial_sensors | 0.90 | Portable detector for gas detection |
| 4 | 1470G1472G | 63941.44 | unknown | unknown | 0.00 | Unrelated to any category |
| 5 | 50147862003R | 60761.97 | unknown | unknown | 0.00 | Unrelated to any category |
| 6 | 1450G | 58761.00 | unknown | unknown | 0.00 | Unrelated to any category |
| 7 | EDA51 | 46460.63 | unknown | unknown | 0.00 | Unrelated to any category |
| 8 | CBL500150S00 | 38894.87 | unknown | it_hardware | 0.80 | USB cable for devices |
| 9 | CBL500150S00 | 38894.87 | unknown | it_hardware | 0.80 | USB cable for devices |
| 10 | CBL500150S00 | 37505.77 | unknown | it_hardware | 0.80 | USB cable for devices |

### Lot 28

- value impacted by category changes: 160418.80 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | 1470G | 171594.59 | unknown | unknown | 0.50 | Insufficient information |
| 2 | 1470G1472G | 111897.52 | unknown | unknown | 0.50 | Insufficient information |
| 3 | 50147862003R | 60761.97 | unknown | it_hardware | 0.80 | Scanner component |
| 4 | 50147862003R | 60761.97 | unknown | it_hardware | 0.80 | Scanner component |
| 5 | CBL500150S00 | 38894.87 | unknown | it_hardware | 0.90 | USB cable for scanner |

### Lot 13

- value impacted by category changes: 0.00 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | 1010924H5 | 126701.40 | unknown | unknown | 0.00 | Unclear product description |
| 2 | PW7K1R2 | 74306.23 | unknown | unknown | 0.00 | Unclear product description |
| 3 | VR425AF10031000 | 40767.43 | unknown | unknown | 0.00 | Unclear product description |
| 4 | DPS400 | 28708.11 | it_hardware | it_hardware | 1.00 | Identified as IT hardware |
| 5 | HH400R12USB | 24417.97 | unknown | unknown | 0.00 | Unclear product description |
| 6 | EDA51KHB2 | 23556.92 | unknown | unknown | 0.00 | Unclear product description |
| 7 | EDA51KHB2 | 23066.15 | unknown | unknown | 0.00 | Unclear product description |
| 8 | EDA61KHB2 | 22446.23 | unknown | unknown | 0.00 | Unclear product description |
| 9 | EDA51KHB2 | 19876.15 | unknown | unknown | 0.00 | Unclear product description |
| 10 | DPTE102 | 17721.85 | unknown | unknown | 0.00 | Unclear product description |

### Lot 12

- value impacted by category changes: 0.00 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | 900J020001 | 98682.69 | unknown | unknown | 0.50 | Insufficient information |
| 2 | 94000A1006 | 60081.13 | gas_safety | gas_safety | 0.90 | Related to gas safety equipment |
| 3 | VNU335A1000 | 42286.36 | unknown | unknown | 0.50 | Insufficient information |
| 4 | 2MLLC42B | 39218.22 | unknown | unknown | 0.50 | Insufficient information |
| 5 | 2MLID22A | 33800.44 | unknown | unknown | 0.50 | Insufficient information |
| 6 | 94000A1006 | 32412.19 | gas_safety | gas_safety | 0.90 | Related to gas safety equipment |
| 7 | 22051E63IV | 28904.62 | unknown | unknown | 0.50 | Insufficient information |
| 8 | 2MLQTR2A | 25090.37 | unknown | unknown | 0.50 | Insufficient information |
| 9 | 900A010202 | 23404.36 | unknown | unknown | 0.50 | Insufficient information |
| 10 | 8CPAINA1 | 22216.79 | unknown | unknown | 0.50 | Insufficient information |

### Lot 23

- value impacted by category changes: 286640.98 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | CK65BTSC | 63332.69 | unknown | it_hardware | 0.80 | Battery for device |
| 2 | OPT78273801 | 30680.36 | unknown | unknown | 0.50 | Insufficient information |
| 3 | 8680I3002 | 28344.46 | unknown | it_hardware | 0.80 | Wearable device kit |
| 4 | CK65BTSC | 24699.75 | unknown | it_hardware | 0.80 | Battery for device |
| 5 | VM3W2M3A2BET1HA1 | 24680.88 | unknown | unknown | 0.50 | Insufficient information |
| 6 | 94000A1017 | 23006.56 | unknown | construction_supplies | 0.70 | Sunshade kit for construction |
| 7 | CBL500300S00 | 21388.24 | unknown | it_hardware | 0.80 | USB cable |
| 8 | HEPZ302W0 | 21178.05 | unknown | fire_safety | 0.90 | Explosion-proof camera |
| 9 | VM1AL0N1B1A20E | 19539.83 | unknown | unknown | 0.50 | Insufficient information |
| 10 | RT10WL1018C12E0E | 18813.54 | unknown | it_hardware | 0.80 | Device with WWAN capability |

### Lot 30

- value impacted by category changes: 56014.37 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | M200EEOLR | 412200.85 | unknown | unknown | 0.50 | Insufficient information |
| 2 | TC806ES1012 | 71884.72 | fire_safety | fire_safety | 0.90 | Smoke detector |
| 3 | 50147862003R | 60761.97 | unknown | unknown | 0.50 | Insufficient information |
| 4 | C06XJEM336 | 56014.37 | unknown | hvac_components | 0.70 | Capacitor for HVAC systems |

### Lot 20

- value impacted by category changes: 0.00 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | ATR03COLUMN340COMPLETE | 467589.49 | unknown | unknown | 0.00 | Category not identifiable |
| 2 | M5ARP02FGK01301 | 123133.67 | industrial_sensors | industrial_sensors | 1.00 | Matches industrial sensors category |

### Lot 33

- value impacted by category changes: 0.00 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | WDU4ZR | 58249511.54 | unknown | unknown | 0.50 | Insufficient information |
| 2 | SF12IV2 | 27439799.78 | unknown | unknown | 0.50 | Insufficient information |

### Lot 31

- value impacted by category changes: 0.00 USD

| slice_rank | sku_code | effective_usd | engine_category | llm_category | confidence | reason |
|---:|---|---:|---|---|---:|---|
| 1 | WDU4 | 10553306.73 | unknown | unknown | 0.50 | Insufficient information to classify |

## Patch Pack Proposal

### a) SKU_LOOKUP candidates (sku_code -> category)

- `1470G2DR2USBR` -> `it_hardware` (affected_usd=1598819.59, rows=20)
- `1470G` -> `packaging_materials` (affected_usd=726562.68, rows=1)
- `470G1472G` -> `packaging_materials` (affected_usd=502104.14, rows=1)
- `1472G2D2USB5R` -> `it_hardware` (affected_usd=441352.42, rows=1)
- `EDA511B663SQGRK` -> `it_hardware` (affected_usd=265989.27, rows=1)
- `04200A1015` -> `hvac_components` (affected_usd=243863.67, rows=2)
- `EDA50K0C121NGRR` -> `it_hardware` (affected_usd=222135.36, rows=2)
- `EDA51K0B931SQGRK` -> `it_hardware` (affected_usd=161044.51, rows=1)
- `CBL500150S00` -> `it_hardware` (affected_usd=154190.38, rows=4)
- `50147862003R` -> `it_hardware` (affected_usd=121523.93, rows=2)
- `MCX30000Y00` -> `industrial_sensors` (affected_usd=116013.49, rows=1)
- `2455R99130401` -> `hvac_components` (affected_usd=92680.13, rows=1)
- `CK65BTSC` -> `it_hardware` (affected_usd=88032.44, rows=2)
- `MCXL000MYRU` -> `gas_safety` (affected_usd=74459.68, rows=1)
- `HNMPE128C144T12R6` -> `it_hardware` (affected_usd=72847.41, rows=1)
- `MCXV0000Y00` -> `industrial_sensors` (affected_usd=67157.87, rows=1)
- `SPXCDALMB1` -> `industrial_sensors` (affected_usd=61806.51, rows=1)
- `RT10WL1018C12E0E` -> `it_hardware` (affected_usd=32923.69, rows=2)
- `8680I3002` -> `it_hardware` (affected_usd=28344.46, rows=1)
- `CBL500300S00` -> `it_hardware` (affected_usd=21388.24, rows=1)
- `HEPZ302W0` -> `fire_safety` (affected_usd=21178.05, rows=1)
- `RP4A0000C32` -> `it_hardware` (affected_usd=15404.36, rows=1)
- `CN80L0N2MC120E` -> `it_hardware` (affected_usd=14945.24, rows=1)
- `H4W4GR1Y` -> `it_hardware` (affected_usd=14033.63, rows=1)
- `CN80L1N5EC210E` -> `it_hardware` (affected_usd=13414.09, rows=1)

### b) BRAND_CATEGORY_MAP additions (high-confidence single-category)

- none

### c) Keyword additions (only where needed)

- none

## Risk Flags

Rows where LLM disagrees with confidence < 0.7 (excluded from proposals):

| lot_id | slice_rank | sku_code | engine_category | llm_category | confidence | effective_usd |
|---:|---:|---|---|---|---:|---:|
| 10 | 1 | CCPCF901 | fire_safety | unknown | 0.50 | 1716185.53 |
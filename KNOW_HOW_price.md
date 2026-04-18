# Know-How: Price Lookup Pipeline

<!-- Sub-file of KNOW_HOW.md. Same format: YYYY-MM-DD | #тег | scope: Суть -->
<!-- Records here are DUPLICATED from KNOW_HOW.md (not moved) per CLAUDE.md rule. -->

## Pipeline rules

2026-04-10 | #rule | price-lookup pipeline (финальный, 4-pass): Pass 1 = Google AI / GPT 5.4 Think (18/19, быстро). Pass 2 = ручная проверка PEHA алиасов + Conrad pack-цен. Pass 3 = Яндекс Алиса для RUB цен. Pass 4 = Claude DR только для PEHA + discontinued + спорных позиций.
2026-04-10 | #rule | price validation checklist: (1) source URL = реальная страница товара. (2) PN в URL или заголовке совпадает. (3) Для PEHA: цена <200 EUR = unit, >200 EUR = проверь pack. (4) Conrad/voelkner: читай "N St.". (5) Scribd/PDF = list price. (6) ARS/JPY/KZT = конвертировать осторожно.

## Pack vs Unit

2026-04-10 | #rule | pack vs unit: Conrad.at/voelkner.de/puhy.cz продают PEHA пачками. URL с "10-st" или "5-st" = pack. Делить на кол-во. Надёжные single-unit: watt24.com, pehastore.de, heiz24.de, elektroversand-schmidt.de, alles-mit-stecker.de.
2026-04-10 | #rule | category price limits: см. CANONICAL_CATEGORIES в merge_research_to_evidence.py. Каждая категория: max_eur (порог pack-флага) + can_be_pack (True/False).
2026-04-10 | #platform | pack-цены Conrad/computersalg: товары PEHA продаются пачками (10 st, 5 st). GPT 5.4 Ext Think и Gemini Thinking возвращают pack-цену как unit-цену — ошибка 5-10x.

## Brand-to-site mapping

2026-04-10 | #rule | brand-to-site mapping: PEHA → watt24.com/pehastore.de/heiz24.de/voltking.de. Honeywell HVAC → emoteek.net/automa.net/energycontrolsonline.co.uk. Honeywell Fire → walde.ee/brandmelde-shop.de. Phoenix Contact → rs-online.com/digikey.com/mouser.com. Esser → walde.ee. Gray market → ebay.com/radwell.com. Russia → teslatorg.ru/energoprime.ru/aelektro.ru.

## Key test SKU

2026-04-10 | #rule | 179433 — ключевой тест на качество модели: реальная цена €101.70 (радиорамка NOVA). Модели-провалы: Google AI €8.45, GPT €11.27, Gemini €14.41. Правильно: Claude DR ✅.
2026-04-10 | #platform | Яндекс Алиса: ищет только российский рынок (RUB). 9/19 цен, 0 ошибок продукта. Уникальная ценность: рублёвые цены.

## Data quirks

2026-04-10 | #data_quirk | PEHA Dialog/Nova pricing: 773111=2.80 EUR, 773211=4.50 EUR, 778311=3.20 EUR, 815511=4.10 EUR, 824611=6.50 EUR, 885811=5.80 EUR, 775511=8.90 EUR, 188091=12.40 EUR, 191191=18.70 EUR, 210213=1.20 EUR.
2026-04-10 | #data_quirk | Dell monitor pricing: P2210F=89.99 USD, P2212HB=65 USD, P2213T=69 USD, P2421D=219.80 USD, U2410F=129.99 USD, U2412M=216.70 USD, U2412MB=82 USD. All refurbished market.
2026-04-12 | #data_quirk | phase3a_gpt_think (72 SKU target): 41 normalized updated, 24 not_found, 7 still no price. Coverage: 360→363/370 (98.1%).
2026-04-11 | #data_quirk | price_unit_judge results (275 priced SKU): 265 per_unit, 10 per_pack, 0 unknown.

## Bugs

2026-04-10 | #bug | dr_price wrong sources confirmed (4 SKU): 171411=circular-saw page, 1006186=ear-plugs page, 183791+184791=gov PDF.
2026-04-10 | #bug | dr_price pack-цены в evidence (13 SKU): PEHA рамки с dr_price >200 EUR — вероятно цена за упаковку.
2026-04-09 | #bug | price_extraction: PN 00020211 fails 108x — provider=openai but model=claude-haiku-4-5. Config mismatch.

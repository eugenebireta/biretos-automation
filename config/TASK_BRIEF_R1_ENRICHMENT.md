# Task Brief — R1 Enrichment: 370 SKU

## Goal

370 SKU из honeywell_aggregated_named_v12.xlsx → evidence-grade карточки для InSales.
По каждому PN найти и подтвердить данные из внешних источников.

## Truth from source

Файл: D:\BIRETOS\projects\downloads\honeywell_aggregated_named_v12.xlsx

| Поле | Trust level |
|------|-------------|
| part_number | TRUTH — canonical identity key |
| quantity | TRUTH |
| Всё остальное (title, brand, цены, condition) | HINT — только подсказка для поиска, не факт |

Цены из xlsx — справочные/закупочные. Рыночные цены искать заново.

## Exit condition

Baseline reached: каждый из 370 SKU имеет evidence bundle
с явным card_status (AUTO_PUBLISH / REVIEW_REQUIRED / DRAFT_ONLY).
Ноль SKU без bundle.

Final done: publishable карточки готовы к импорту в InSales.

## 8 enrichment fields + PN identity anchor

PN = identity anchor (из xlsx, не enrichment).

Для каждого PN найти:

1. title_ru — нормализованное русское название с моделью
2. description_ru — 2-4 предложения (что это, где применяется)
3. brand — подтверждённый по evidence / identity logic, не слепо из xlsx
4. insales_category — из фиксированного дерева категорий
5. photo — фото товара (KEEP verdict или placeholder с photo_gap)
6. price — рыночная цена из публичных источников (НЕ из xlsx)
7. specs — технические характеристики (found OR explicit specs_gap)
8. card_status — рассчитывается по policy

## Scope

- 370 SKU, 28 брендов (Honeywell, PEHA, ABB, Cisco, Moxa, Phoenix Contact и др.)
- Target: InSales (Ozon / Shopware — отдельные задачи)

## Hard constraints

- xlsx truth = ТОЛЬКО PN + quantity
- Public / private evidence не смешивать
- Tier-1 frozen files и pinned API не трогать
- card_status policy не переосмыслять внутри batch
- Подробнее: config/catalog_evidence_policy_v1.json, docs/PROJECT_DNA.md §5

## Infrastructure constraints

- Claude API (Anthropic) — для текстового анализа, naming, парсинга, vision
- Gemini API (Google) — доступен (ключ в auditor .env), пока не используется в enrichment
- SerpAPI — для поиска
- OpenAI API — НЕ доступен (не оплачен). Не использовать.

## Current state (обновляет агент)

Обновлено: 2026-04-07

| Метрика | Значение |
|---------|----------|
| Всего SKU | 370 |
| С evidence bundle | 25 (6.8%) |
| Без evidence (gap) | 345 |
| photo KEEP | 11 |
| photo нужна замена | 14 |
| price найдена | 8 |
| price не найдена | 17 |
| title_ru enriched | 0 |
| description_ru | 0 |
| category | 0 |
| specs | 0 |
| Baseline reached | 0 / 370 |
| Provider swap | DONE (ClaudeChatAdapter default) |

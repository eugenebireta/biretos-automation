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

Обновлено: 2026-04-07 (после batch 50)

| Метрика | Значение |
|---------|----------|
| Всего SKU | 370 |
| С evidence bundle | 69 (18.6%) |
| Без evidence (gap) | 301 |
| title_ru | 69/69 в bundles |
| description_ru | 69/69 в bundles |
| brand confirmed | 69/69 в bundles |
| category | 69/69 в bundles |
| photo KEEP | 14/69 |
| photo REJECT | 55/69 |
| price public_price | 8/69 |
| price category_mismatch | 34/69 |
| price not found | 27/69 |
| specs | 0/69 |
| card_status | 69/69 (58 DRAFT_ONLY, 11 REVIEW_REQUIRED) |
| Baseline reached | 0 / 370 (AUTO_PUBLISH = 0) |
| Provider swap | DONE |
| Evidence-first skip | DONE |

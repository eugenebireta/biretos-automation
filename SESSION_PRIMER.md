# Session Primer — Biretos Automation

## Проект
Autonomous B2B Decision & Execution Engine. Каталог ~374 SKU (Honeywell, PEHA, Phoenix Contact и др.)
Локальный AI: 2×RTX 3090 — 70B Worker + 30B Reviewer + Memory Vault (ChromaDB/Qdrant)
Claude Code = координатор/executor. Governance rules: CLAUDE.md

## Текущий статус
> Синхронизировать с `docs/autopilot/STATE.md` — там актуальные seq и phase.

- Ветка: `feat/rev-r1-catalog`
- 374 SKU в evidence. Price: 368 (98%). Photo: 368 (98%). SEO description: 196 (52%). Specs: 249 (67% — после Gemini Flash batch 2026-04-18). Weight: 66 (18%). Dims: 90 (24%). EAN: 121 (32%).
- Canonical 229 SKU: InSales READY 207 (90%). InSales CSV: `downloads/staging/pipeline_v2_export/insales_import_229sku.csv`.
- Strong identity: 262 (70%), weak: 99 (26%), none: 9 (2%).
- Routing decision (specs/datasheet extraction): **Gemini 2.5 Flash default** (3-9× more specs than Haiku, no hallucinations vs Sonnet), Sonnet escalation only for non-empty clean PDFs where Flash returns 0.

## Пайплайны

| Pipeline | Скрипты | KNOW_HOW | Статус |
|----------|---------|----------|--------|
| enrichment (DR) | dr_prompt_generator, dr_results_import, merge_research | [KNOW_HOW_enrichment.md](KNOW_HOW_enrichment.md) | ACTIVE |
| export | export_pipeline, export_ready, card_status | [KNOW_HOW_export.md](KNOW_HOW_export.md) | ACTIVE |
| identity | identity_checker, confidence_recalculator | [KNOW_HOW_identity.md](KNOW_HOW_identity.md) | STABLE |
| price | gemini_price_scout, phase3a_price_import | [KNOW_HOW_price.md](KNOW_HOW_price.md) | ACTIVE |
| telegram | orchestrator/telegram_* | [KNOW_HOW_telegram.md](KNOW_HOW_telegram.md) | IN_PROGRESS |
| email archive | email_bulk_fetcher, email_pn_indexer, auto_annotate_goldset, learn_from_sonnet, rebuild_pn_demand_v4 (all on VPS /root/) | [KNOW_HOW_email.md](KNOW_HOW_email.md) | ACTIVE — 12K emails, shared pn_brand_patterns.json with enrichment |

## Ключевые KNOW_HOW (топ-5 критичных)

1. `expected_category` WRONG в 92% файлов (344/374) — НИКОГДА не использовать как hint
2. Gemini DR переходит в narrative/analytics на смешанных батчах — использовать Claude для сложных SKU
3. PEHA цены >200 EUR вероятно пачка ("N St." в описании)
4. Claude DR: 14/19 цен, 0 ошибок > Gemini Fast: 17/19, 3+ не того товара
5. Доверенные поля: `seed_name`, `our_price_raw`, `brand`, `assembled_title`

## Слои памяти (читать по нужде)

- **Layer 0** (всегда): этот файл + `docs/autopilot/STATE.md`
- **Layer 1** (правила): `CLAUDE.md`, `KNOW_HOW.md`, `KNOW_HOW_*.md`
- **Layer 2** (опыт): `docs/memory/*.jsonl` — 82 structured principles
  - `EXPERIENCE_BOOTSTRAP_v1.jsonl` — 24 operating principles
  - `engineering/ENGINEERING_EXPERIENCE_v1.jsonl` — 17 engineering lessons
  - `enrichment/ENRICHMENT_EXPERIENCE_v1.jsonl` — 41 enrichment rules
  - `PHASE_A_DEVELOPMENT_MEMORY_v1.json` — Phase A proof artifacts
- **Layer 3** (стратегия): `docs/MASTER_PLAN_v1_9_2.md`, `docs/PROJECT_DNA.md`

## Скрипты

Перед любым скриптом → `scripts/MANIFEST.json`. Никогда не писать ad-hoc Python для существующих задач.
Все скрипты поддерживают `--dry-run` — использовать сначала.

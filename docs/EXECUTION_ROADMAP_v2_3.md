BIRETOS AUTOMATION
EXECUTION ROADMAP v2.3
(обновлено 2026-03-26: v1.9.2 — R1 Batch Execution Contract,
8.1 review fabric, Catalog Pipeline Principles, R1 hardening,
Gold SKU Engine, R4, Content Gen, Marketplace Adapt, Observability,
Rollback Matrix, Aged Stock, TD-026..TD-043)

Полный последовательный план от текущего состояния до AI-завода.
Каждый этап усиливает следующий. Порядок строгий.

═══════════════════════════════════════════════════════
КАК ПОЛЬЗОВАТЬСЯ ЭТИМ ДОКУМЕНТОМ
═══════════════════════════════════════════════════════

  Основной инструмент: Claude Code внутри Cursor.
  Cursor AI не используется — только Claude Code как исполнитель.

  1. Открыть Claude Code, скинуть PROJECT_DNA.md + этот файл
  2. Сказать "следующая задача"
  3. Claude Code выполняет задачу с правильным pipeline
  4. Проверить результат
  5. Вернуться: "готово, что дальше"
  6. Новая идея → Claude классифицирует и ставит в нужное место

  Pipeline по уровню риска (роли → текущие модели):

  🔴 CORE CRITICAL — полный pipeline (INV-GOV: все 7 ролей):
    1. SCOUT    → Gemini 2.5 Pro      (разведка кода)
    2. ARCHITECT → Claude Opus        (архитектура решения)
    3. CRITIC   → Gemini 2.5 Pro      (критика)
    4. ARCHITECT → Claude Opus        (ответ на критику)
    5. JUDGE    → Claude (отдельный чат, без контекста Cursor)
    6. PLANNER  → Claude Opus         (план изменений)
    7. BUILDER  → Claude Sonnet/Codex (реализация)
    8. AUDITOR  → Gemini 2.5 Pro      (аудит результата)

  🟡 SEMI-CRITICAL — сокращённый pipeline:
    1. ARCHITECT → Claude Opus
    2. CRITIC    → Gemini 2.5 Pro
    3. PLANNER   → Claude Opus
    4. BUILDER   → Claude Sonnet
    5. AUDITOR   → Gemini 2.5 Pro

  🟢 LOW RISK — минимальный pipeline:
    1. ARCHITECT → Claude Opus
    2. BUILDER   → Claude Sonnet

  Роли постоянны. Модели меняются — обновляй эту секцию.
  Если задача мутирует Core → автоматически 🔴 (INV-GOV).


═══════════════════════════════════════════════════════
PARALLELIZATION POLICY
═══════════════════════════════════════════════════════

  1. Одновременно активна только ОДНА крупная ветка.
     Мы чередуем, а не параллелим:
     Safety (3-5 дней) → Revenue (3-5 дней) → Safety → Revenue.
  2. Naming: infra/acceleration-* для Safety, feat/rev-<n>-* для Revenue.
  3. feat/rev-* не трогает core/, domain/reconciliation/, infra/.
  4. Iron Fence должен быть стабилен (CI зелёный) до открытия
     первой Revenue ветки.


═══════════════════════════════════════════════════════
ТЕКУЩАЯ ПОЗИЦИЯ (обновлено 2026-03-25)
═══════════════════════════════════════════════════════

  Завершено ранее:
  ✔ Phase 1 — Operational Stability (DONE)
  ✔ Idempotency v2, FSM Guards, Hardening F2
  ✔ Governance: review_cases, governance_decisions
  ✔ IC-1..IC-9, Payment/Shipment/Document services
  ✔ TBank adapter + webhook, CDEK adapter (частично)
  ✔ Telegram router (15 команд)
  ✔ Git repo synced
  ✔ Core Freeze зафиксирован (117 тестов, PHASE2_BOUNDARY.md)
  ✔ Этап 2.5 закрыт (PROJECT_DNA v2.0, ai_reviewer, DoD)
  ✔ Этап 6 — Backoffice Task Engine: DONE (PR #7, 2026-03-21)
  ✔ Этап 7 — AI Executive Assistant NLU: DONE (PR #9, JUDGE PASS, 2026-03-22)

  Текущий статус этапов:
  🔄 Этап 1 — Governance Executor: В РАЗРАБОТКЕ (не закрыт формально)
  🔄 Этап 2 — CI настроен (pytest при push). Branch protection — частично
     настроена, но не соответствует целевому состоянию
     (CI required; PR reviews not required; direct push not blocked).
  ❌ Этап 3 — Reconciliation: не начат (заблокирован Этапами 1-2)
  ❌ Этап 4 — Alerting: не начат (заблокирован Этапом 3)
  🔄 Этап 5 — Pydantic: 5.1 ЗАКРЫТ (TaskIntent + ActionSnapshot,
     PR merged, 124/124 тестов). Пп. 5.2–5.5 не сделаны.
  🔄 Этап 5.5 — Iron Fence: 5.5.1 Hash Lock FIXED (CRLF-safe, SHA-256).
     M3a/M3b/M3c — статус не подтверждён.
  🟡 R2 — Telegram Export: scaffold готов (миграция 027, /export stub,
     PR #2 merged). Revenue Gate закрыт — активация запрещена.
  🔵 R1 — Mass Catalog Pipeline: de facto active dev track, code merged to master
     (PR #12, PR #16); owner-authorized по факту, но формальное открытие
     Revenue Gate в документах не зафиксировано.
  ❌ R3 — Lot Analyzer: не начат.

  🔵 АКТИВНО СЕЙЧАС:
  Этап 8 — Stability Gate: MONITOR phase (источник: STATE.md seq 28).
  Awaiting: ≥30 closed cycles, Shadow Mode exit (≥50 req, ≥90% match).

  Примечание: работа продвинулась вперёд (Этапы 6→7) пока
  Этапы 1–4 формально ещё не закрыты. Это технический долг
  по формальному закрытию, не архитектурное нарушение.


═══════════════════════════════════════════════════════
ЧАСТЬ I — CORE FOUNDATION (Этапы 1–8)
Цель: замкнуть Core, стабилизировать, доказать работоспособность
═══════════════════════════════════════════════════════


ЭТАП 1 — GOVERNANCE EXECUTOR                    🔴 CORE CRITICAL
Срок: 1-2 недели
Статус: 🔄 В РАЗРАБОТКЕ (не закрыт формально)

  1.1 governance_execute_approved
  1.2 Corrections apply (HUMAN_APPROVE_WITH_CORRECTION)
  1.3 External idempotency keys
  1.4 Split TX (executing state)
  1.5 Replay verify-only
  1.6 Smoke test

  Усиливает → Этап 2:
    Есть полный governance loop для тестирования в CI.


ЭТАП 2 — CI + BRANCH PROTECTION                🟡 SEMI-CRITICAL
Срок: 1-2 дня
Статус: 🔄 CI настроен. Branch protection — не сделана.

  2.1 GitHub Actions pytest при push
  2.2 Branch protection на master
  2.3 Governance executor тесты в CI

  Усиливает → Этап 2.5:
    Базовый CI готов — можно добавлять guardrails.


ЭТАП 2.5 — CONTEXT CORTEX                      🟡 SEMI-CRITICAL
Статус: ✔ ЗАКРЫТ

  ✔ docs/PROJECT_DNA.md v2.0
  ✔ docs/prompt_library/ai_reviewer.md (C1-C11)
  ✔ docs/DEFINITION_OF_DONE.md


ЭТАП 3 — RECONCILIATION RC-2..RC-7             🔴 CORE CRITICAL
Срок: 1-2 недели

  3.1 RC-2 (CDEK shipment)
  3.2 RC-5 (Document)
  3.3 RC-6 (Order lifecycle)
  3.4 RC-7 (End-to-end transaction)
  3.5 Все RC в CI

  Усиливает → Этап 4:
    Alerting знает о чём алертить.


ЭТАП 4 — ALERTING                               🟡 SEMI-CRITICAL
Срок: 3-5 дней

  4.1 IC/RC нарушение → Telegram алерт
  4.2 FSM staleness, zombie reservations → алерт
  4.3 Alert routing (critical/warning/info)
  4.4 Отдельный Telegram чат для алертов

  Усиливает → Этап 4.5:
    Есть алерты — нужен tracing и observability.


ЭТАП 4.5 — OBSERVABILITY STRATEGY              🟡 SEMI-CRITICAL  ← НОВОЕ v1.9.0
Срок: 2-3 дня

  4.5.1 Tracing Backend
    trace_id обязателен (DNA §7). Определить хранение,
    retention, поисковый интерфейс.
  4.5.2 SLA на диагностику
    < 15 мин для P1, < 1 час для P2.
  4.5.3 Structured Logging Standard
    JSON: trace_id, timestamp, severity, module, operation, duration_ms.
  4.5.4 Health Dashboard
    IC/RC статусы, alert rates, latency percentiles, error budgets.

  Усиливает → Этап 5:
    Есть observability — Pydantic ошибки тоже видны.


ЭТАП 5 — CDM RUNTIME VALIDATION (Pydantic)     🔴 CORE CRITICAL
Срок: 1-2 недели
Статус: 🔄 5.1 ЗАКРЫТ (TaskIntent + ActionSnapshot, 124/124 тестов).
Пп. 5.2–5.5 не сделаны.

  5.1 Pydantic models для CDM v2 + TaskIntent
  5.2 Validation на 3 границах
  5.3 Validation errors → alerting
  5.4 Guardian checks (hardcoded invariant validation)
  5.5 Тесты в CI

  Усиливает → Этап 5.5:
    Есть runtime contracts — можно ставить Iron Fence.


ЭТАП 5.5 — IRON FENCE (Core Freeze Guards)     🟡 SEMI-CRITICAL
Срок: 1-3 дня
Статус: 🔄 5.5.1 Hash Lock FIXED (CRLF-safe, SHA-256).
M3a/M3b/M3c — статус не подтверждён.

  MVP Iron Fence (минимум — 1 час работы):
  5.5.1 Tier-1 Hash Lock (CRLF-safe, SHA-256 по 19 файлам)
  5.5.2 Boundary Grep M3a: запрет DML по reconciliation_* из Tier-3
  5.5.3 Migration DDL Guard: запрет reconciliation_* в migrations/020+

  Полный Iron Fence (после первого Revenue PR):
  5.5.4 Boundary Grep M3b: запрет raw DML по бизнес-таблицам из Tier-3
  5.5.5 Boundary Grep M3c: запрет импортов Tier-1 модулей из Tier-3
  5.5.6 Ruff в CI + pre-commit (warn-only baseline)

  Усиливает → Этап 6:
    Iron Fence стабилен → открываем первую Revenue ветку.


ЭТАП 6 — BACKOFFICE TASK ENGINE                 🔴 CORE CRITICAL
Срок: 2-3 недели

  6.1 TaskIntent router (4 intent'а):
      check_payment, get_tracking, get_waybill, send_invoice
  6.2 EmployeeRole + Permission model
  6.3 employee_actions_log + context_snapshot
  6.4 Intent Risk Registry
  6.5 EDO adapter (базовый)
  6.6 CDEK adapter расширение
  6.7 External Read Snapshotting (INV-ERS)
  6.8 Snapshot Store (external_read_snapshots)
  6.9 Shadow Logging for RAG
  6.10 Rate limits per employee (INV-RATE)
  6.11 Тесты + CI

  Усиливает → Этап 7:
    AI Assistant = NLU обёртка поверх Task Engine.


ЭТАП 7 — AI EXECUTIVE ASSISTANT                 🔴 CORE CRITICAL
Срок: 2-3 недели
Статус: 🔵 АКТИВНО — PR #9 открыт, 321 тест, ожидает CRITIC/AUDITOR/JUDGE

  7.1 Intent Parser (NLU) → TaskIntent
  7.2 Hybrid UI (Full NLU → Assisted → Button-only)
  7.3 Mandatory Button Confirmation (INV-MBC)
  7.4 Intent Versioning (model_version, prompt_version)
  7.5 Graceful Degradation (Level 0→1→2)
  7.6 Prompt Injection Protection
  7.7 Shadow Mode
  7.8 SLA мониторинг
  7.9 Полное тестирование

  Усиливает → Этап 8:
    Максим работает через бота. Данные копятся.


ЭТАП 8 — STABILITY GATE                         🔴 CORE CRITICAL
Срок: 2-4 недели (эксплуатация, не разработка)

  8.1 Максим работает через AI Assistant
  8.2 Мониторинг 19 критериев Stability Gate
  8.3 Shadow Mode → выход при ≥50 запросов, ≥90% совпадение
  8.4 Owner Cognitive Load tracking
  8.5 Weekly review всех метрик
  8.6 Баг фиксы → новые тесты в CI

  Критерии прохождения:
    ≥30 закрытых циклов, 0 corruption, 0 manual interventions,
    IC/RC зелёные, replay divergence=0, эскалация <20%,
    AI прошёл Shadow Mode, PITR работает.

  Результат:
    STOP RULE v1 → можно заморозить.
    ИЛИ продолжить к Этапу 8.1.


ЭТАП 8.1 — LOCAL AI SETUP / REVIEW FABRIC      🟡 SEMI-CRITICAL  ← РАСШИРЕН
Срок: 1-2 недели

  Назначение: shadow review layer и disagreement logging.
  Это не runtime swarm и не live autonomy without review.

  8.1.1 2x RTX 3090 setup (Ollama / vLLM)
  8.1.2 6 AI ролей deployed (Extractor→Guardian)
  8.1.3 AI Provider Flexibility (local/cloud/hybrid)
  8.1.4 Priority Queue (HIGH→cloud fallback)
  8.1.5 Тестирование: local AI vs cloud AI quality comparison
  8.1.6 Shadow Logging for Teacher-Student Pipeline          ← НОВОЕ v1.9.0
    Structured JSONL: cloud responses + prompts (redacted),
    human corrections, reviewer verdicts. Retention 1 год.
    Eval base для quality comparison и будущего distillation.
  8.1.7 Batch Contract Enforcement
    Локальный reviewer проверяет scope boundary, evidence pack,
    semantic diff и verification path до wider run.
  8.1.8 Exception-only Owner Escalation
    Owner вовлекается по gate / exception, а не по каждому микро-шагу.
  8.1.9 Reviewer Disagreement Logging
    Несогласия reviewer'ов сохраняются как отдельный артефакт
    для последующего анализа regressions / distillation.
  8.1.10 Local Reviewer as Shadow Gate
    Local reviewer = дополнительный shadow gate, не authority owner.
  8.1.11 No live autonomy without shadow pass
    Wider run / live side-effects не расширяются без shadow pass.

  MVP: минимальный setup, не "чёрная дыра" настройки.

  Усиливает → Этап SS-1.


ЭТАП SS-1 — DATASHEET LAYER FOUNDATION         🟡 SEMI-CRITICAL
Срок: 1-2 недели
Prerequisite: Iron Fence стабилен, R3 MVP завершён.

  SS-1.1 Схема таблиц DataSheet (versioned, с source_id)
  SS-1.2 Ingestion pipeline (Excel/CSV → stg_datasheets)
  SS-1.3 Version tracking + re-processing
  SS-1.4 Read-only views для Consumer-слоёв
  SS-1.5 Тесты + CI

  SS-2/SS-3/SS-4 реализуются внутри Этапов 10-18.

  Усиливает → Часть II.


── STOP RULE v1: после Этапа 8 можно заморозить и эксплуатировать ──


═══════════════════════════════════════════════════════
REVENUE TRACKS (чередуются с Platform начиная с Этапа 5.5)
═══════════════════════════════════════════════════════

  Условие открытия: Iron Fence MVP (Этап 5.5, пп. 5.5.1–5.5.3) стабилен,
  CI зелёный на MVP grep-проверках (Hash Lock + DML Guard + DDL Guard).
  Полный Iron Fence (5.5.4–5.5.6) вводится после первого Revenue PR.

  Каждый Revenue трек = отдельная ветка feat/rev-<n>-*
  Все Revenue треки = Tier-3 адаптеры (см. PROJECT_DNA §6)


R1 — MASS CATALOG PIPELINE (PN-first industrial MVP)  🟡 SEMI-CRITICAL  ← HARDENED v1.9.1
MVP срок: 3-7 дней
Scope v1: Brand-scoped (один бренд за batch). PN-first. No fuzzy/ML. Safe subset only.
Execution mode: bounded batch execution contract. One narrow change-set per batch.
Evidence pack is mandatory. Out-of-scope touch = reject / reopen.

  R1.0 Start Gate                                              ← НОВОЕ v1.9.1
    CI green, branch protection ok, Iron Fence stable.
  R1.1 Импорт 500 SKU (Excel/CSV → stg_catalog_imports)
    Input contract: brand + part_number + qty + approx_price обязательны.
    Reject if: branded industrial SKU without PN, broken required fields.
  R1.2 Нормализация через Pydantic схему
    PN normalization (clean separators, normalize case, dedupe).
    Confidence gate: HIGH → auto enrich, MEDIUM → review queue,
    LOW → review / minimal draft (не публиковать без review).
  R1.3 Публикация через Shopware/InSales adapter
    Только safe subset (HIGH confidence). Остальное → review bucket.
  R1.4 Фото: raw image first + placeholder policy               ← УТОЧНЕНИЕ v1.9.1
    Raw usable image → publish. Reliable image не найден → placeholder.
    Фото не блокирует revenue. Enhancement — позже (local AI path).
  R1.5 Idempotency + retries + audit log
  R1.6 Тесты в CI
  R1.7 Review Bucket (structured reasons)                        ← НОВОЕ v1.9.1
    missing_pn, ambiguous_pn, duplicate_pn, no_photo,
    title_confidence_low, source_conflict, validation_failed.

  catalog_evidence_policy_v1 обязательна (см. Master Plan §Catalog Pipeline Principles).

  Hard Stop: НЕ auto-delete фото, НЕ fuzzy match, НЕ ML, НЕ multi-agent runtime.
  Метрика: 500 SKU processed deterministically; safe subset published;
  ambiguous → review with evidence.


R2 — TELEGRAM EXPORT INTERFACE                  🟢 LOW RISK
MVP срок: 1-2 дня
Статус: 🟡 Scaffold ready (миграция 027, /export stub, PR #2 merged).
Revenue Gate закрыт — активация запрещена до Iron Fence stable.

  R2.1 Команда /export <category> → Excel/CSV
  R2.2 Rate limit + auth + audit trail (export_logs)
  R2.3 Telegram = тонкий client

  Hard Stop: только одна команда.
  Метрика: выгрузка Excel по категории за <30 сек.


R3 — LOT ANALYZER ENGINE v2                     🟡 SEMI-CRITICAL  ← РАСШИРЕН v1.9.0
MVP срок: 3-5 дней

  R3.1 Вход: Excel/CSV лотов (только, не OCR)
  R3.2 Scoring: топ-20% ядра, плотность стоимости, концентрация SKU
  R3.3 Отдельная схема БД (lot_scoring)
  R3.4 Ingestion из Core только через append-only экспорты
  R3.5 Price Checker интеграция (read-only)
  R3.6 Результаты сохраняются в БД с trace_id + created_at
  R3.7 Lot Document Ingestion                               ← НОВОЕ v1.9.0
    Парсинг Excel / CSV / PDF valuation reports.
    Text-first parsing → structured extraction.
  R3.8 Valuation Mapping Engine                              ← НОВОЕ v1.9.0
    Сопоставление: товары из лота ↔ оценочный отчёт ↔ price-check.
    Результат: matched / fuzzy / unmatched coverage.
  R3.9 Price & Demand Evidence Aggregator                    ← НОВОЕ v1.9.0
    Price checker + market pulse + RFQ history + buyer history.
  R3.10 Lot Research Pack (выходной артефакт)                ← НОВОЕ v1.9.0
    Полный пакет: core slice, valuation matching, price/demand evidence,
    unknown exposure, anchor-buyer fit, decision rationale.

  lot_selection_policy_v1 обязательна для R3+ (см. Master Plan §Policy Packs).

  Handoff R3 → R4:
    Lot Research Pack = входной артефакт для R4.
    R3 = read-only analysis, R4 = outbound actions.

  Hard Stop (v1): нет OCR, нет JOIN в Core, нет ML-scoring.
  Метрика: score лота за <5 мин, результат в БД навсегда.


R4 — ANCHOR BUYER LIQUIDATION ENGINE            🟡 SEMI-CRITICAL  ← НОВОЕ v1.9.0
MVP срок: 3-5 дней
Prerequisite: R3 Lot Analyzer v2 завершён.

  R4.1 Buyer Registry (якорные покупатели + их PN-интересы)
  R4.2 Pre-Alert List (уведомления по типам лотов)
  R4.3 Fast Offer Pack (автогенерация из Lot Research Pack)
  R4.4 Price Ladder (стартовая цена → floor → deadline)
  R4.5 KPI tracking: core payback 14–30 дней
  R4.6 Связь с Buyer Intelligence (Этап 15) через read-only views

  Архитектура: Tier-3. Линейный job_state:
    lot_scored → offer_generated → offer_sent → response_received → closed
  Таблицы: rev_buyer_registry, rev_liquidation_offers, rev_liquidation_kpi

  Hard Stop (v1): НЕ full automation outbound, НЕ auto-pricing beyond D2.
  Метрика: core slice payback ≤ 30 дней.


═══════════════════════════════════════════════════════
ЧАСТЬ II — OPERATIONAL EXCELLENCE (Этапы 9–13)
Цель: система учится, считает деньги, каталог растёт
Prerequisite: Stability Gate PASSED
═══════════════════════════════════════════════════════


ЭТАП 9 — AUTONOMY ENGINE                        🔴 CORE CRITICAL  ← РАСШИРЕН v1.9.0
Срок: 3-4 недели

  9.1 Decision Pattern Mining
  9.2 Auto-Approve Engine (rules-based, versioned)
  9.3 Decision Classes D1-D5 с approval matrix
  9.3.1 Rollback Strategy per Decision Class (D1–D5)        ← НОВОЕ v1.9.0
    D1: нет. D2: revert price. D3: SAGA compensation.
    D4: append-only сторно. D5: SAGA + owner confirm.
  9.4 Policy Packs v1 (pricing_policy_v1, quote_policy_v1,
      inventory_policy_v1, lot_selection_policy_v1)
  9.5 Policy Simulation / Backtesting
  9.6 Governance Rules rollback + Compensation Review
  9.7 Approval Fatigue Protection (batching)
  9.8 Autonomy KPI Dashboard (цель: 90%+)
  9.9 Autonomy ROI tracking

  Усиливает → Этап 10.


ЭТАП 10 — CATALOG FACTORY                       🟡 SEMI-CRITICAL  ← ЗНАЧИТЕЛЬНО РАСШИРЕН v1.9.0
Срок: 3-4 недели

  10.1 DataSheet Database (SS-1 как основа)
  10.2 Identity Resolution (exact MPN + Brand)
  10.3 Cleaning Layer
  10.4 Автоклассификация (SS-2 Category Intelligence)
    10.4.1 Internal Category Tree (canonical, owned by Core)  ← НОВОЕ v1.9.0
    10.4.2 Category Mapping Registry                          ← НОВОЕ v1.9.0
      internal → Shopware / Ozon / WB / YM / eBay / Avito /
      InSales (transitional) + required attributes per platform
    10.4.3 Attribute Transformer (CDM → platform format)      ← НОВОЕ v1.9.0
    10.4.4 Marketplace Schema Sync (мониторинг изменений)     ← НОВОЕ v1.9.0
    10.4.5 AI-assisted initial mapping (SS-2)                 ← НОВОЕ v1.9.0
    10.4.6 Validation Gate (fail loud if attrs missing)       ← НОВОЕ v1.9.0
  10.5 CanonicalListing (CDM v3 migration)
    1 CanonicalProduct / CDM → N platform-specific listings    ← УТОЧНЕНИЕ v1.9.0
  10.5a AI Content Generator                                  ← НОВОЕ v1.9.0
    10.5a.1 Title / description / meta / alt из CDM + DataSheet
    10.5a.2 B2B tone adaptation
    10.5a.3 Platform-specific content (Shopware, Ozon, WB,
            YM, eBay, Avito; InSales if active)
    10.5a.4 Мультиязычность (RU / EN)
    10.5a.5 Structured specs → human-readable
  10.5b Content Review Gate                                   ← НОВОЕ v1.9.0
    REVIEWER проверяет контент. Auto-approve после Shadow Mode
    (≥100 карточек, ≥90% совпадение с human review).
  10.6 FSM для Listing
    ОБНОВЛЕНО: draft → content_generated → content_reviewed → validated → published
  10.7 Фото-пайплайн
  10.8 Адаптация фото под маркетплейсы
  10.9 Compliance Check (Честный знак)
  10.10 Публикация через marketplace adapters
  10.11 SKU Profitability Gate
  10.12 Schema Versioning Protocol (CDM v2 → v3)             ← НОВОЕ v1.9.0
    Schema version tag, idempotent migration, dual-read period,
    Pydantic per version, cutover after 100% verified.


ЭТАП 11 — PRICE INTELLIGENCE                    🟡 SEMI-CRITICAL
Срок: 2-3 недели

  11.1 Price Parser (SS-3 Price Intelligence)
  11.2 Price History (хранение, тренды)
  11.3 Price Rules (margin floor, market position)
       Safety Policies > Growth Policies.
  11.4 Price Update через Governance (INV-FL)
  11.5 Price Intelligence Dashboard


ЭТАП 12 — QUOTE ENGINE                          🔴 CORE CRITICAL
Срок: 2-3 недели

  12.1 RFQ → автоматический расчёт КП
  12.2 Quote FSM (draft→approved→sent→accepted/rejected)
  12.3 Margin Calculator (цена + логистика + налоги)
  12.4 Quote versioning + history
  12.5 Telegram интеграция

  Усиливает → Этап 13.

  ── Stability Gate v2 ──


ЭТАП 13 — DOUBLE-ENTRY LEDGER                   🔴 CORE CRITICAL
Срок: 2-3 недели

  13.1 ledger_entries (debit/credit/currency/fx_snapshot)
  13.2 IC-10: SUM(debits) = SUM(credits) per currency
  13.3 Интеграция с payment/invoice/quote flows
  13.4 System Settings Registry
  13.5 Базовый P&L отчёт
  13.6 Reconciliation: ledger vs bank statement


═══════════════════════════════════════════════════════
ЧАСТЬ III — REVENUE AUTOMATION (Этапы 14–17)
Prerequisite: Часть II завершена
═══════════════════════════════════════════════════════


ЭТАП 14 — CUSTOMER SELF-SERVICE                 🟡 SEMI-CRITICAL  ← РАСШИРЕН v1.9.0
Срок: 3-4 недели

  14.1 AI Chat на СНГ сайте (DataSheet + Price)
  14.2 RFQ форма → Quote Engine
  14.3 Order Status Portal
  14.4 INV-KNOW: каждый ответ со ссылкой на источник
  14.5 Graceful Degradation
  14.6 Demand Sensor Cards                                   ← НОВОЕ v1.9.0
    Карточки "под заказ / запросить цену / запросить срок"
    = сенсоры спроса. Каждый клик, RFQ, повтор — сигнал.
  14.7 Signal Collection Pipeline                            ← НОВОЕ v1.9.0
    RFQ + clicks + repeats + channel signals → SS-4 (Market Pulse).
    Email signals — basic parser until TD-027 (Email Intelligence Hub).


ЭТАП 15 — CLIENT INTELLIGENCE                   🟡 SEMI-CRITICAL  ← РАСШИРЕН v1.9.0
Срок: 2-3 недели

  15.1 ABC классификация клиентов
  15.2 ABC классификация товаров
  15.3 Client Profile (LTV, risk scoring)
  15.4 Персонализация
  15.5 Supplier Relationship Management
  15.6 PN-history per buyer                                  ← НОВОЕ v1.9.0
    Какие PN покупатель заказывал, в каких объёмах.
    Feed для Gold SKU Engine и R4 Anchor Buyer.
  15.7 Decision velocity                                     ← НОВОЕ v1.9.0
    Скорость принятия решения (КП → оплата).
  15.8 Document preferences                                  ← НОВОЕ v1.9.0
    Какие документы требует покупатель.
  15.9 Volume patterns                                       ← НОВОЕ v1.9.0
    Паттерны закупок. Feed для Demand Intelligence.


ЭТАП 15.10 — GOLD SKU ENGINE                    🟡 SEMI-CRITICAL  ← НОВОЕ v1.9.0
Срок: 2-3 недели
Prerequisite: Этап 15 (Client Intelligence) + Этап 11 (Price Intelligence).

  15.10.1 Gold SKU Scoring (demand + margin + supply signals)
  15.10.2 SKU Decision Engine (aptechka / backorder / archive / source-via-lot)
  15.10.3 Brand Gold SKU Discovery mode
  15.10.4 inventory_policy_v1 enforcement через Guardian
  15.10.5 Integration с R4 Anchor Buyer (source-via-lot → lot pipeline)
  15.10.6 Owner Aptechka / Procurement Cockpit
    Три зоны: что купить / что убрать / что срочно распродать.
    Owner queue: D3–D5 approve.

  Таблицы: rev_gold_sku_scores, rev_gold_sku_decisions
  Усиливает → Этап 16: Procurement знает ЧТО закупать.


ЭТАП 16 — PROCUREMENT & SUPPLY CHAIN           🔴 CORE CRITICAL
Срок: 4-6 недель

  S1: Paid order → buy from known supplier
  S2: RFQ → quote as backorder
  S3: Returns/claims minimal loop

  16.1 Supplier Discovery
  16.2 Auto-Purchase (Pessimistic Locking + алерты при сбое)
  16.3 Capital Guardrails
  16.4 Outbound Governance Quota (1 письмо/день v1)
  16.5 Supplier Failover
  16.6 Margin Calculator полный
  16.7 CDEK/DHL adapter

  ── STOP RULE v2: СНГ автономен на 90%+ ──


ЭТАП 17 — RETURNS & CLAIMS                      🔴 CORE CRITICAL
Срок: 2-3 недели

  17.1 Customer Returns
  17.2 Supplier Claims
  17.3 Quality Tracking
  17.4 Ledger интеграция (сторно, возвраты)


═══════════════════════════════════════════════════════
ЧАСТЬ IV — INTELLIGENCE & OPTIMIZATION (Этапы 18–19)
Prerequisite: Часть III завершена
═══════════════════════════════════════════════════════


ЭТАП 18 — DEMAND INTELLIGENCE                   🟡 SEMI-CRITICAL  ← РАСШИРЕН v1.9.0
Срок: 3-4 недели

  18.1 Demand Forecasting (SS-4 Market Pulse)
  18.2 Inventory Optimization (min/max stock, auto-reorder)
  18.3 Dynamic Pricing (через Governance)
  18.4 Competitor Intelligence
  18.5 Sensor-to-Decision Pipeline                           ← НОВОЕ v1.9.0
    Demand Sensor Cards → Demand Intelligence → Gold SKU Engine.
  18.6 Aged Stock Liquidation Assist                         ← НОВОЕ v1.9.0
    18.6.1 Aged Stock Scoring
      age_days, sell_through, capital_locked, views/RFQ, buyer_fit_score.
    18.6.2 Bulky Inventory Penalty
      Штраф для крупногабарита, низкой плотности стоимости.
    18.6.3 Exit Pricing Proposals
      target_price, fast_exit_price, liquidation_price_band.
      Auto: только D2/policy. Большие уценки → owner approve (D5).
    18.6.4 Buyer Shortlist Draft
      По категории/бренду, buyer history, volume patterns.
    18.6.5 Liquidation Recommendation
      keep / small discount / aggressive exit /
      move to lot-bundle / outbound shortlist / owner review.


ЭТАП 19 — BUSINESS MEMORY VAULT                 🟡 SEMI-CRITICAL
Срок: 2-3 недели

  19.1 Векторная БД на Local PC (ChromaDB/Qdrant)
  19.2 Decision Trail Index
  19.3 Contracted Retrieval (memory_evidence_ids)
  19.4 Memory TTL + Compaction
  19.5 Интеграция с AI Assistant

  ── STOP RULE v3: СНГ полностью автономен ──


═══════════════════════════════════════════════════════
ЧАСТЬ V — INTERNATIONAL EXPANSION (Этапы 20–23)
Prerequisite: СНГ стабилен ≥ 3 месяца, profit model validated
═══════════════════════════════════════════════════════

  Этапы 20–23 без изменений относительно v2.2:

  ЭТАП 20 — INTERNATIONAL INFRASTRUCTURE        🔴
  ЭТАП 21 — INTERNATIONAL MARKETPLACE ADAPTERS  🟡
  ЭТАП 22 — INTERNATIONAL OPERATIONS            🔴
  ЭТАП 23 — INTERNATIONAL STABILITY GATE        🔴

  ── STOP RULE v4: AI-завод. Human = стратег ──


═══════════════════════════════════════════════════════
СУММАРНАЯ КАРТА
═══════════════════════════════════════════════════════

  ЧАСТЬ I — CORE FOUNDATION          [~3-4 мес]
    Этап 1:   Governance Executor     🔴 🔄 в разработке
    Этап 2:   CI + Branch Protection  🟡 🔄 CI done, branch protection нет
    Этап 2.5: Context Cortex          ✔  → ЗАКРЫТ
    Этап 3:   Reconciliation          🔴 ❌ не начат
    Этап 4:   Alerting                🟡 ❌ не начат
    Этап 4.5: Observability Strategy  🟡 ❌ не начат                  ← NEW
    Этап 5:   Pydantic Validation     🔴 🔄 5.1 done, 5.2-5.5 нет
    Этап 5.5: Iron Fence              🟡 🔄 Hash Lock done, grep TBD
    Этап 6:   Backoffice Task Engine  🔴 → (работа ушла вперёд к 7)
    Этап 7:   AI Executive Assistant  🔴 🔵 АКТИВНО: PR #9
    Этап 8:   Stability Gate          🔴 ❌ не начат
    Этап 8.1: Local AI Review Fabric (+8.1.6-8.1.11) 🟡 ❌ не начат   ← EXPANDED
    Этап SS-1: DataSheet Foundation   🟡 ❌ не начат
    ── STOP RULE v1: можно заморозить ──

  REVENUE TRACKS
    R1: Mass Catalog Pipeline         🟡 ❌ не начат (PN-first MVP) ← HARDENED
    R2: Telegram Export               🟢 🟡 scaffold ready, Revenue Gate closed
    R3: Lot Analyzer v2               🟡 ❌ не начат               ← EXPANDED
    R4: Anchor Buyer Liquidation      🟡 ❌ не начат               ← NEW

  ЧАСТЬ II — OPERATIONAL EXCELLENCE  [~3-4 мес]
    Этап 9:  Autonomy Engine (+Rollback) 🔴 → 90% без владельца  ← EXPANDED
    Этап 10: Catalog Factory          🟡 → каталог растёт сам    ← MAJOR EXPAND
             (Content Gen, Marketplace Adapt, Schema Versioning)
    Этап 11: Price Intelligence       🟡 → цены актуальны
    Этап 12: Quote Engine             🔴 → КП автоматически
    Этап 13: Double-Entry Ledger      🔴 → система считает деньги
    ── Stability Gate v2 ──

  ЧАСТЬ III — REVENUE AUTOMATION     [~3-4 мес]
    Этап 14: Customer Self-Service    🟡 → покупатели + demand radar  ← EXPANDED
    Этап 15: Client Intelligence      🟡 → знаем клиентов + buyers   ← EXPANDED
    Этап 15.10: Gold SKU Engine       🟡 → что закупать + cockpit    ← NEW
    Этап 16: Procurement              🔴 → закупки автоматически
    ── STOP RULE v2: СНГ автономен ──
    Этап 17: Returns & Claims         🔴 → полный цикл

  ЧАСТЬ IV — INTELLIGENCE            [~2-3 мес]
    Этап 18: Demand Intelligence      🟡 → прогнозы + aged stock     ← EXPANDED
    Этап 19: Business Memory          🟡 → память бизнеса
    ── STOP RULE v3: СНГ полностью автономен ──

  ЧАСТЬ V — INTERNATIONAL            [~3-4 мес]
    Этап 20: INT Infrastructure       🔴 → два кластера
    Этап 21: INT Marketplaces         🟡 → eBay, Amazon
    Этап 22: INT Operations           🔴 → DHL, валюты, таможня
    Этап 23: INT Stability Gate       🔴 → оба рынка стабильны
    ── STOP RULE v4: AI-завод ──

  Общий горизонт: ~14-18 месяцев до полной автономности.
  Можно остановиться на любом STOP RULE.


═══════════════════════════════════════════════════════
ПРАВИЛА ROADMAP
═══════════════════════════════════════════════════════

  1. Этапы выполняются строго последовательно (Platform трек).
  2. Revenue треки открываются после стабильного Iron Fence
     и чередуются с Platform по 3-5 дней.
  3. Нельзя перескакивать платформенные этапы.
  4. Новые идеи → сначала docs/IDEA_INBOX.md → triage → approve → patch в authoritative document.
  5. Master Plan (v1.9.2) — конституция.
     PROJECT_DNA.md — правила для AI-агентов.
  6. Этот Roadmap — единственный источник "что делать дальше".
  7. Pipeline (🔴/🟡/🟢) = уровень риска = градация INV-GOV.
  8. Каждый этап: commit + push + CI green.
  9. STOP RULE: на любом можно заморозить и эксплуатировать.
  10. Назначение моделей на роли (секция КАК ПОЛЬЗОВАТЬСЯ)
      обновляется при смене моделей — без governance pipeline.

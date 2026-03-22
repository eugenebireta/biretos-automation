BIRETOS AUTOMATION
EXECUTION ROADMAP v2.0

Полный последовательный план от текущего состояния до AI-завода.
Каждый этап усиливает следующий. Порядок строгий.

═══════════════════════════════════════════════════════
КАК ПОЛЬЗОВАТЬСЯ ЭТИМ ДОКУМЕНТОМ
═══════════════════════════════════════════════════════

  1. Открыть чат с Claude, скинуть этот файл
  2. Сказать "следующая задача"
  3. Claude даёт промт для Cursor с правильным pipeline
  4. Выполнить в Cursor
  5. Вернуться: "готово, что дальше"
  6. Новая идея → Claude классифицирует и ставит в нужное место

  Pipeline по уровню риска:

  🔴 CORE CRITICAL (мутации, деньги, stock, external API):
    1. ASK Gemini → разведка кода
    2. ASK Opus → архитектура решения
    3. ASK Gemini → критика
    4. ASK Opus → ответ на критику
    5. ASK Claude/GPT (вне Cursor) → архитектурный вердикт
    6. PLAN Opus → план изменений
    7. AGENT Sonnet/Codex → реализация
    8. ASK Gemini → аудит результата

  🟡 SEMI-CRITICAL (Catalog, Price, Telegram, парсинг):
    1. ASK Opus → решение
    2. AGENT Sonnet → реализация
    3. ASK Gemini → аудит

  🟢 LOW RISK (логи, аналитика, дашборды, черновики):
    1. AGENT Sonnet → реализация

  Если задача мутирует Core → автоматически 🔴


═══════════════════════════════════════════════════════
ТЕКУЩАЯ ПОЗИЦИЯ
═══════════════════════════════════════════════════════

  ✔ Phase 1 — Operational Stability (DONE)
  ✔ Idempotency v2, FSM Guards, Hardening F2
  ✔ Governance: review_cases, governance_decisions
  ✔ IC-1..IC-9, Payment/Shipment/Document services
  ✔ TBank adapter + webhook, CDEK adapter (частично)
  ✔ Telegram router (15 команд)
  ✔ Git repo synced
  🔄 CI pipeline (настроен, проверяется)
  🔄 Governance Executor (в разработке)


═══════════════════════════════════════════════════════
ЧАСТЬ I — CORE FOUNDATION (Этапы 1–8)
Цель: замкнуть Core, стабилизировать, доказать работоспособность
═══════════════════════════════════════════════════════


ЭТАП 1 — GOVERNANCE EXECUTOR                    🔴 CORE CRITICAL
Срок: 1-2 недели
Статус: 🔄 В РАЗРАБОТКЕ

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
Статус: 🔄 CI настроен, branch protection осталась

  2.1 GitHub Actions pytest при push
  2.2 Branch protection на master
  2.3 Governance executor тесты в CI

  Усиливает → Этап 3:
    Безопасная разработка, регрессии ловятся автоматически.


ЭТАП 2.5 — CONTEXT CORTEX (Acceleration Kit)    🟡 SEMI-CRITICAL
Срок: 1 день
Prerequisite: ЭТАП 2 завершён (CI работает)

  2.5.1 PROJECT_DNA.md (архитектурные правила, тиры, запреты, глоссарий)
  2.5.2 AI Reviewer Prompt (9 проверок границ и паттернов)
  2.5.3 Definition of Done (9-пунктный чек-лист на каждый PR)

  Артефакты:
    - PROJECT_DNA.md (корень репо)
    - docs/prompt_library/ai_reviewer.md
    - docs/DEFINITION_OF_DONE.md

  Tier-1 impact: NONE (только документация)

  Усиливает → Этап 3:
    Все последующие PR проходят через стандартизированный
    ревью-контекст. AI-ассистенты получают границы сразу.


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

  Усиливает → Этап 5:
    Pydantic validation ошибки тоже алертятся.


ЭТАП 5 — CDM RUNTIME VALIDATION (Pydantic)     🔴 CORE CRITICAL
Срок: 1-2 недели

  5.1 Pydantic models для CDM v2 + TaskIntent
  5.2 Validation на 3 границах
  5.3 Validation errors → alerting
  5.4 Guardian checks (hardcoded invariant validation)
  5.5 Тесты в CI

  Усиливает → Этап 6:
    TaskIntent validated → Backoffice Task Engine получает
    структурированный input. INV-CTB enforced.


ЭТАП 5.5 — IRON FENCE (Core Freeze Guards)      🟡 SEMI-CRITICAL
Срок: 2-3 дня
Prerequisite: ЭТАП 5 завершён, ЭТАП 2.5 внедрён

  5.5.1 Tier-1 Hash Lock в CI (SHA-256, CRLF-safe нормализация)
  5.5.2 Boundary Grep в CI:
        - запрет DML по reconciliation_* из Tier-3
        - запрет raw DML по бизнес-таблицам из Tier-3
        - запрет импортов Tier-1 domain-модулей из Tier-3
  5.5.3 Migration DDL Guard: запрет reconciliation_* в migrations/020+
        Escape hatch: маркер -- CORE-CRITICAL-APPROVED: <reason>
  5.5.4 Ruff в CI (warn-only baseline, только изменённые файлы)

  Tier-1 impact: NONE (только CI скрипты)

  Усиливает → Этап 6:
    Автоматический "забор" вокруг Core. Нарушения границ
    ловятся в CI до code review. Безопасно масштабировать Tier-3.

  Примечание: ЭТАП 20 (Local AI Setup) рекомендуется перенести
  к позиции 8.x после подтверждения Iron Fence на 1-2 реальных PR.


ЭТАП 6 — BACKOFFICE TASK ENGINE                 🔴 CORE CRITICAL
Срок: 2-3 недели

  6.1 TaskIntent router (начать с 4 intent'ов):
      check_payment, get_tracking, get_waybill, send_invoice
  6.2 EmployeeRole + Permission model
  6.3 employee_actions_log + context_snapshot
  6.4 Intent Risk Registry (risk profile per intent)
  6.5 EDO adapter (базовый)
  6.6 CDEK adapter расширение
  6.7 External Read Snapshotting (INV-ERS в коде)
  6.8 Snapshot Store (external_read_snapshots таблица)
  6.9 Shadow Logging for RAG (начать собирать данные)
  6.10 Rate limits per employee (INV-RATE)
  6.11 Тесты + CI

  Усиливает → Этап 7:
    AI Assistant = NLU обёртка поверх работающего Task Engine.


ЭТАП 7 — AI EXECUTIVE ASSISTANT                 🔴 CORE CRITICAL
Срок: 2-3 недели

  7.1 Intent Parser (NLU) → TaskIntent
  7.2 Hybrid UI (Full NLU → Assisted → Button-only)
  7.3 Mandatory Button Confirmation (INV-MBC)
  7.4 Intent Versioning (model_version, prompt_version)
  7.5 Graceful Degradation (Level 0→1→2)
  7.6 Prompt Injection Protection
  7.7 Shadow Mode (AI работает в тени, не отправляет)
  7.8 SLA мониторинг
  7.9 Полное тестирование

  Усиливает → Этап 8:
    Максим работает через бота. Данные копятся.


ЭТАП 8 — STABILITY GATE                         🔴 CORE CRITICAL
Срок: 2-4 недели (эксплуатация, не разработка)

  Это НЕ разработка. Это наблюдение и стабилизация.

  8.1 Максим работает через AI Assistant
  8.2 Мониторинг 19 критериев Stability Gate
  8.3 Shadow Mode → выход при ≥50 запросов, ≥90% совпадение
  8.4 Owner Cognitive Load tracking
  8.5 Weekly review всех метрик
  8.6 Баг фиксы → новые тесты в CI

  Критерии прохождения:
    ≥100 закрытых циклов, 0 corruption, 0 manual interventions,
    IC/RC зелёные, replay divergence=0, эскалация <20%,
    AI прошёл Shadow Mode, PITR работает.

  Результат:
    STOP RULE v1 → можно заморозить, система работает.
    ИЛИ продолжить к Части II.


═══════════════════════════════════════════════════════
ЧАСТЬ II — OPERATIONAL EXCELLENCE (Этапы 9–12)
Цель: система учится, считает деньги, каталог растёт
Prerequisite: Stability Gate PASSED
═══════════════════════════════════════════════════════


ЭТАП 9 — DOUBLE-ENTRY LEDGER                    🔴 CORE CRITICAL
Срок: 2-3 недели

  9.1 ledger_entries таблица (debit/credit/currency/fx_snapshot)
  9.2 IC-10: SUM(debits) = SUM(credits) per currency
  9.3 Интеграция с существующими payment/invoice flows
  9.4 System Settings Registry (бизнес-константы в БД)
  9.5 Базовый P&L отчёт
  9.6 Reconciliation: ledger vs bank statement

  Усиливает → Этап 10:
    Margin Calculator имеет точные финансовые данные.
    Decision Snapshots включают финансовый контекст.


ЭТАП 10 — AUTONOMY ENGINE (Phase 5)             🔴 CORE CRITICAL
Срок: 3-4 недели

  10.1 Decision Pattern Mining
  10.2 Auto-Approve Engine (rules-based, versioned)
  10.3 Decision Classes D1-D5 с approval matrix
  10.4 Policy Packs (pricing_policy_v1, quote_policy_v1)
  10.5 Policy Simulation / Backtesting
  10.6 Governance Rules rollback + Compensation Review
  10.7 Approval Fatigue Protection (batching)
  10.8 Autonomy KPI Dashboard (цель: 90%+)
  10.9 Autonomy ROI tracking (profit per autonomous decision)

  Усиливает → Этап 11:
    Auto-approve для рутинных операций → Catalog Factory
    может публиковать без ручного approve для low-risk.


ЭТАП 11 — CATALOG FACTORY (Phase 3 полная)      🟡 SEMI-CRITICAL
Срок: 3-4 недели

  11.1 DataSheet Database (ingestion, parsing, normalization)
  11.2 Identity Resolution Layer (дедупликация SKU)
  11.3 Cleaning Layer (фильтр мусора перед CDM)
  11.4 Автоклассификация (Ozon, WB, Яндекс Маркет)
  11.5 CanonicalListing (CDM v3 migration)
  11.6 FSM для Listing (draft→validated→published)
  11.7 Фото-пайплайн (SERP + AI генерация из DataSheet)
  11.8 Адаптация фото под каждый маркетплейс
  11.9 Compliance Check (Честный знак)
  11.10 Публикация через marketplace adapters
  11.11 SKU Profitability Gate (не генерировать low-ROI карточки)

  Усиливает → Этап 12:
    Каталог растёт автоматически → Price Monitoring
    имеет что мониторить.


ЭТАП 12 — PRICE & AVAILABILITY INTELLIGENCE     🟡 SEMI-CRITICAL
Срок: 2-3 недели

  12.1 Price Checker (SERP API, прайс-листы, API поставщиков)
  12.2 Observed vs Assumed разделение
  12.3 Competitor monitoring (цены конкурентов на маркетплейсах)
  12.4 Observation Jobs (пишут snapshots) — строгое разделение
  12.5 Price history DB
  12.6 Smart Throttling Layer (P1-P4 приоритеты)
  12.7 Circuit Escalation (L1-L4)

  Усиливает → Этап 13:
    Есть актуальные цены и наличие → Quote Engine
    может формировать КП автоматически.


═══════════════════════════════════════════════════════
ЧАСТЬ III — REVENUE AUTOMATION (Этапы 13–16)
Цель: система продаёт и закупает автоматически
Prerequisite: Часть II завершена
═══════════════════════════════════════════════════════


ЭТАП 13 — QUOTE ENGINE (Automated RFQ)          🔴 CORE CRITICAL
Срок: 2-3 недели

  13.1 RFQ parsing (маппинг на SKU/MPN)
  13.2 Стратегия: "в наличии" / "под заказ"
  13.3 Margin Calculator (закупка + логистика + комиссия + налоги)
  13.4 INV-MARGIN: Guardian проверяет маржу перед approve
  13.5 КП генерация + отправка
  13.6 FSM для Quote (draft→validated→sent→accepted)
  13.7 Decision Snapshot для каждого Quote
  13.8 Governance барьер (сумма > лимит или новый клиент → human)

  Усиливает → Этап 14:
    КП формируются автоматически → нужны клиенты
    через Customer Self-Service.


ЭТАП 14 — CUSTOMER SELF-SERVICE (Phase 10)      🟡 SEMI-CRITICAL
Срок: 3-4 недели

  14.1 AI Chat на СНГ сайте (ответы из DataSheet + Price)
  14.2 RFQ форма на сайте → автоматический Quote Engine
  14.3 Order Status Portal (покупатель видит статус)
  14.4 INV-KNOW: каждый ответ со ссылкой на источник
  14.5 Customer-facing Graceful Degradation

  Усиливает → Этап 15:
    Покупатели обслуживаются автоматически →
    нужно знать кто они (Client Intelligence).


ЭТАП 15 — CLIENT INTELLIGENCE (Phase 8)         🟡 SEMI-CRITICAL
Срок: 2-3 недели

  15.1 ABC классификация клиентов (по обороту, частоте, оплате)
  15.2 ABC классификация товаров (спрос, маржа, оборачиваемость)
  15.3 Client Profile (история, предпочтения, LTV, risk scoring)
  15.4 Персонализация ("Пора заказать?")
  15.5 Supplier Relationship Management (рейтинг, ABC поставщиков)

  Усиливает → Этап 16:
    Знаем клиентов и поставщиков → можно автоматизировать закупки.


ЭТАП 16 — PROCUREMENT & SUPPLY CHAIN (Phase 7)  🔴 CORE CRITICAL
Срок: 4-6 недель

  Начать с 3 сценариев:
    S1: Paid order → buy from known supplier
    S2: RFQ → quote as backorder
    S3: Returns/claims minimal loop

  16.1 Supplier Discovery (scraping, API)
  16.2 Auto-Purchase (SAGA: PO→confirmed→in_transit→delivered)
  16.3 Capital Guardrails (max exposure per supplier/inventory)
  16.4 Outbound Governance Quota (anti-spam)
  16.5 Supplier Failover (auto-search alternative при +5%)
  16.6 Margin Calculator полный (+ логистика + таможня)
  16.7 CDEK/DHL adapter для закупочной логистики

  Усиливает → Этап 17:
    Закупки работают → можно прогнозировать спрос
    и регулировать цены.

  STOP RULE v2: после этого этапа система автономна на 90%+
  для СНГ рынка. Дальнейшее развитие опционально.


═══════════════════════════════════════════════════════
ЧАСТЬ IV — INTELLIGENCE & OPTIMIZATION (Этапы 17–19)
Цель: система предсказывает и оптимизирует
Prerequisite: Часть III завершена
═══════════════════════════════════════════════════════


ЭТАП 17 — DEMAND INTELLIGENCE (Phase 9)         🟡 SEMI-CRITICAL
Срок: 3-4 недели

  17.1 Demand Forecasting (история + сезонность + тренды)
  17.2 Inventory Optimization (min/max stock, auto-reorder)
  17.3 Dynamic Pricing (через Governance, INV-FL для крупных)
  17.4 Competitor Intelligence (позиции, цены, стратегия)

  Усиливает → Этап 18:
    Прогнозы → можно обрабатывать возвраты умно.


ЭТАП 18 — RETURNS & CLAIMS (Phase 11)           🔴 CORE CRITICAL
Срок: 2-3 недели

  18.1 Customer Returns (инициация, обратная накладная, возврат денег)
  18.2 Supplier Claims (рекламация, отслеживание, resolution)
  18.3 Quality Tracking (% возвратов per supplier/brand)
  18.4 Ledger интеграция (сторно, возвраты)

  Усиливает → Этап 19:
    Полный цикл СНГ закрыт → Business Memory заполнена →
    готовы к международке.


ЭТАП 19 — BUSINESS MEMORY VAULT                 🟡 SEMI-CRITICAL
Срок: 2-3 недели

  19.1 Векторная БД на Local PC (ChromaDB/Qdrant)
  19.2 Decision Trail Index (структурный поиск)
  19.3 Contracted Retrieval (memory_evidence_ids)
  19.4 Memory TTL + Compaction
  19.5 Интеграция с AI Assistant ("почему мы так решили?")

  К этому моменту Shadow Logging (с Этапа 6) уже накопил
  месяцы данных → Memory Vault сразу полезен.

  STOP RULE v3: СНГ рынок полностью автономен.
  Можно заморозить и эксплуатировать.


═══════════════════════════════════════════════════════
ЧАСТЬ V — INTERNATIONAL EXPANSION (Этапы 20–24)
Цель: второй рынок, два кластера
Prerequisite: СНГ стабилен ≥ 3 месяца, profit model validated
═══════════════════════════════════════════════════════


ЭТАП 20 — LOCAL AI SETUP                        🟡 SEMI-CRITICAL
Срок: 1-2 недели

  20.1 2x RTX 3090 setup (Ollama / vLLM)
  20.2 6 AI ролей deployed (Extractor→Guardian)
  20.3 AI Provider Flexibility (local/cloud/hybrid)
  20.4 Priority Queue (HIGH→cloud fallback)
  20.5 Тестирование: local AI vs cloud AI quality comparison

  Усиливает → Этап 21:
    AI независим от облачных провайдеров.


ЭТАП 21 — INTERNATIONAL INFRASTRUCTURE          🔴 CORE CRITICAL
Срок: 2-3 недели

  21.1 VPS-2 (USA) setup
  21.2 INT PostgreSQL instance
  21.3 Global Inventory Hub (reservation + quota per cluster)
  21.4 Inter-node Contract Registry (Pydantic schemas)
  21.5 CDC/Outbox синхронизация (events, не snapshots)
  21.6 Ownership isolation enforcement (INV-OWN)
  21.7 Failure Domain testing

  Усиливает → Этап 22:
    Инфраструктура готова → можно подключать площадки.


ЭТАП 22 — INTERNATIONAL MARKETPLACE ADAPTERS    🟡 SEMI-CRITICAL
Срок: 3-4 недели

  22.1 eBay adapter
  22.2 Amazon adapter
  22.3 CanonicalListing для INT (EN locale)
  22.4 Фото адаптация под INT требования
  22.5 Multi-language (RU↔EN для карточек и описаний)
  22.6 International site

  Усиливает → Этап 23:
    Площадки подключены → нужны INT платежи и логистика.


ЭТАП 23 — INTERNATIONAL OPERATIONS              🔴 CORE CRITICAL
Срок: 3-4 недели

  23.1 Multi-currency в Core (amount_minor + currency_code)
  23.2 FX Snapshot Contract
  23.3 DHL adapter
  23.4 International payment adapters
  23.5 Compliance Engine (HS Codes, пошлины, санкции)
  23.6 INV-TAX enforcement
  23.7 Ledger: multi-currency entries
  23.8 Cross-border Margin Calculator

  Усиливает → Этап 24:
    INT операции работают → стабилизация второго кластера.


ЭТАП 24 — INTERNATIONAL STABILITY GATE          🔴 CORE CRITICAL
Срок: 2-4 недели (эксплуатация)

  24.1 INT кластер работает ≥ 2-4 недели
  24.2 Cross-cluster sync стабилен
  24.3 GIL: 0 oversells
  24.4 INT Ledger balances correct
  24.5 Failure Domain verified
  24.6 INT эскалация < 20%

  STOP RULE v4: оба рынка автономны.
  AI-завод работает. Human = стратег.


═══════════════════════════════════════════════════════
СУММАРНАЯ КАРТА
═══════════════════════════════════════════════════════

  ЧАСТЬ I — CORE FOUNDATION          [~3-4 мес]
    Этап 1:  Governance Executor      🔴 → loop замкнут
    Этап 2:  CI + Branch Protection   🟡 → защита от регрессий
    Этап 3:  Reconciliation           🔴 → consistency
    Этап 4:  Alerting                 🟡 → активное наблюдение
    Этап 5:  Pydantic Validation      🔴 → runtime contracts
    Этап 6:  Backoffice Task Engine   🔴 → Максим через систему
    Этап 7:  AI Executive Assistant   🔴 → Максим через бота
    Этап 8:  Stability Gate           🔴 → proof of stability
    ── STOP RULE v1: можно заморозить ──

  ЧАСТЬ II — OPERATIONAL EXCELLENCE   [~3-4 мес]
    Этап 9:  Double-entry Ledger      🔴 → система считает деньги
    Этап 10: Autonomy Engine          🔴 → 90% без владельца
    Этап 11: Catalog Factory          🟡 → каталог растёт сам
    Этап 12: Price Intelligence       🟡 → цены актуальны
    ── Stability Gate v2 ──

  ЧАСТЬ III — REVENUE AUTOMATION      [~3-4 мес]
    Этап 13: Quote Engine             🔴 → КП автоматически
    Этап 14: Customer Self-Service    🟡 → покупатели сами
    Этап 15: Client Intelligence      🟡 → знаем клиентов
    Этап 16: Procurement              🔴 → закупки автоматически
    ── STOP RULE v2: СНГ автономен ──

  ЧАСТЬ IV — INTELLIGENCE             [~2-3 мес]
    Этап 17: Demand Intelligence      🟡 → прогнозы
    Этап 18: Returns & Claims         🔴 → полный цикл
    Этап 19: Business Memory          🟡 → память бизнеса
    ── STOP RULE v3: СНГ полностью автономен ──

  ЧАСТЬ V — INTERNATIONAL             [~3-4 мес]
    Этап 20: Local AI Setup           🟡 → AI независим
    Этап 21: INT Infrastructure       🔴 → два кластера
    Этап 22: INT Marketplaces         🟡 → eBay, Amazon
    Этап 23: INT Operations           🔴 → DHL, валюты, таможня
    Этап 24: INT Stability Gate       🔴 → оба рынка стабильны
    ── STOP RULE v4: AI-завод ──

  Общий горизонт: ~15-19 месяцев до полной автономности.
  Можно остановиться на любом STOP RULE.


═══════════════════════════════════════════════════════
ПРАВИЛА ROADMAP
═══════════════════════════════════════════════════════

  1. Этапы выполняются строго последовательно.
  2. Нельзя перескакивать. Каждый этап — prerequisite следующего.
  3. Новые идеи → Claude классифицирует → ставит в нужный этап.
  4. Master Plan v1.7.2 — конституция. Не меняется без веской причины.
  5. Этот Roadmap — единственный источник "что делать дальше".
  6. Pipeline (🔴/🟡/🟢) выбирается по уровню риска этапа.
  7. Каждый этап заканчивается: commit + push + CI green.
  8. STOP RULE: на любом STOP RULE можно заморозить и эксплуатировать.

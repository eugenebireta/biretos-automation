BIRETOS AUTOMATION
MASTER PLAN v1.7.2

(Complete Vision — Autonomous B2B Trading Platform)

═══════════════════════════════════════════════════════
CHANGELOG
═══════════════════════════════════════════════════════

v1.2-v1.6.2: Core, Governance, Invariants (14), Snapshot Store,
  System Settings, Testing/Deployment/Incident, Tech Debt.
v1.6.2 → v1.7: Full vision, Phases 7-11, Infrastructure Topology,
  Local AI, Business Memory, Multi-currency, Debug.
v1.7 → v1.7.1: Clean Architecture (4 layers), Global Data Ownership,
  5 AI Roles, CanonicalListing, FSM Listing/Quote, Observation vs Decision,
  Decision Snapshot, Policy Packs, INV-TAX, Cleaning Layer, Smart Throttling.

v1.7.1 → v1.7.2:
  - FIX: CanonicalProduct owner → Core (VPS), не Local PC
  - FIX: Conflict resolution → ownership isolation (не timestamp)
  - Decision Classes D1-D5 + approval matrix
  - Double-entry Ledger (минимальный)
  - Identity Resolution Layer (дедупликация SKU)
  - Failure Domain Mapping (каждый узел)
  - Guardian — 6-я AI роль (veto на нарушение инвариантов)
  - State Ownership Locks (human > AI в FSM)
  - Policy Simulation / Backtesting
  - Decision Snapshot Retention Policy
  - Memory TTL + compaction
  - Circuit Escalation L1-L4
  - Outbound Governance Quota (supplier anti-spam)
  - Новый инвариант INV-OWN (Data Ownership)

═══════════════════════════════════════════════════════


0. ГЛОБАЛЬНАЯ ЦЕЛЬ

Автономная AI-платформа для B2B торговли на двух рынках.
Находит, создаёт, продаёт, закупает, доставляет, управляет ценами.
Два кластера. Полная память. Локальный AI.
Human = стратег, не оператор.


═══════════════════════════════════════════════════════
CLEAN ARCHITECTURE — 4 СЛОЯ
═══════════════════════════════════════════════════════

  COGNITIVE LAYER (Local PC, NO side-effects)
    AI Models (70B Worker + 30B Reviewer + Guardian)
    Business Memory Vault
    Draft Generators (Datasheet→CDM, RFQ→Quote, Photo, Procurement)
    OUTPUT: DraftArtifacts + EvidenceLinks + Versions
    RULE: черновики only, truth принадлежит Core

  ORCHESTRATION LAYER (VPS-1 / VPS-2)
    Windmill workflows / job queues
    Observation Jobs → Snapshot Store (write only)
    Decision Jobs → read Snapshot Store only
    RULE: Observation пишет, Decision читает. Never live read in decision.

  CORE LAYER (VPS-1 for RU, VPS-2 for INT)
    CDM v2 + Pydantic Validation
    TaskIntent Router (ONLY mutation entry)
    Governance (review → decisions → executor)
    Idempotency + FSM Guards + Reconciliation + Replay
    System Settings Registry
    RULE: Deterministic. Owner of truth.

  INTEGRATIONS LAYER (Adapters, side-effects)
    RU (VPS-1): Shopware, Ozon, WB, YM, TBank, CDEK, ЭДО
    INT (VPS-2): eBay, Amazon, DHL, Int'l payments, Suppliers
    RULE: Side-effects only inside own cluster. Circuit Breaker each.


═══════════════════════════════════════════════════════
GLOBAL DATA OWNERSHIP (ИСПРАВЛЕНО в v1.7.2)
═══════════════════════════════════════════════════════

  Принцип: Conflict = impossible by design.
  Каждая сущность имеет ровно одного owner.
  Только owner может мутировать. Остальные получают read-only копию.

  Ownership Matrix:

    CanonicalProduct:
      Owner: Core DB (VPS-1 primary, replicated to VPS-2)
      ИСПРАВЛЕНО: Local PC = автор черновиков, НЕ owner of truth
      Draft → CDM migration → Core DB. Core = single source of truth.
      Изменения через CDM Migration Protocol или approved TaskIntent.

    CanonicalListing:
      Owner: VPS кластера где площадка
      RU listings (Ozon/WB/YM) → VPS-1 exclusively
      INT listings (eBay/Amazon) → VPS-2 exclusively
      VPS-1 не может мутировать INT listing и наоборот.

    CanonicalOrder:
      Owner: VPS кластера где продажа
      RU orders → VPS-1 exclusively
      INT orders → VPS-2 exclusively

    Inventory:
      Owner: Global Inventory Hub (VPS-1 primary)
      Quota per cluster: RU_quota + INT_quota ≤ total_stock
      Reservation: pessimistic (лучше отказать чем oversell)
      Минимальный MVP нужен ДО двухрегиональной торговли.

    Pricing:
      Owner: VPS кластера (разные рынки = разные цены)
      Global base price в CDM. Local market price per cluster.

  Conflict Resolution (ИСПРАВЛЕНО в v1.7.2):
    Конфликты невозможны by design через ownership isolation:
      - Каждая сущность имеет ровно одного owner
      - Только owner выполняет writes
      - Другие кластеры получают events (read-only)
      - Event version numbers (monotonic per entity) для ordering
      - НЕ timestamp-based resolution (clock skew unsafe)

  Синхронизация:
    CDC/Outbox: только events, не snapshots состояния
    Events: product_updated, inventory_reserved, price_changed
    Каждый event: global_entity_id + cluster_source + version_number

  Inter-node Contract Registry:
    Версионированные Pydantic schemas для межузловых сообщений.
    Backward-compatible upcasters. Mismatch = reject + alert.

  При сетевом разрыве (CAP theorem):
    VPS-1 down → VPS-2 продолжает INT операции автономно.
      RU операции недоступны до восстановления VPS-1.
    VPS-2 down → VPS-1 продолжает RU операции автономно.
      INT операции недоступны. AI fallback на VPS-1 cloud proxy.
    Local PC down → AI fallback на Cloud через VPS-2.
      Система продолжает работать без AI генерации.
    См. Failure Domain Mapping для полной картины.


═══════════════════════════════════════════════════════
AI ROLES ARCHITECTURE (ОБНОВЛЕНО в v1.7.2)
═══════════════════════════════════════════════════════

  6 ролей с жёсткими контрактами (не "агенты"):

  EXTRACTOR: raw data → structured. Read-only.
  NORMALIZER: structured → CDM draft. Draft-only.
  REVIEWER: draft → approved/rejected. Read-only + verdict.
  PLANNER: snapshots + policies → recommendation draft. Draft-only.
  EXECUTOR: approved TaskIntent → side-effect. Mutation via Core only.

  GUARDIAN (НОВОЕ в v1.7.2):
    Единственная роль с правом ВЕТО.
    Не предлагает решений, только проверяет:
      - INV-FL: сумма в пределах лимита?
      - INV-TAX: таможня/пошлины проверены?
      - INV-SAGA: compensation plan существует?
      - INV-RATE: rate limits не превышены?
      - Margin: выше минимальной маржи?
    Guardian вызывается ПЕРЕД каждой мутацией.
    Вето = операция заблокирована + алерт + escalation.
    Guardian hardcoded (не AI, а детерминированные проверки).
    Guardian нельзя обойти.

  Capability-based permissions:
    AI = draft-only. Mutation = only Executor via Governance.
    Guardian = veto gate перед Executor.


═══════════════════════════════════════════════════════
DECISION CLASSES (НОВОЕ в v1.7.2)
═══════════════════════════════════════════════════════

  Каждое решение системы классифицируется:

  D1 — INFORMATIONAL (read-only ответ)
    Примеры: check_payment, check_delivery, get_tracking
    Риск: нулевой. Не мутирует.
    Auto-approve: всегда (если employee разрешён intent).

  D2 — PRICING (изменение цены)
    Примеры: update_price, apply_discount
    Риск: средний. Reversible.
    Auto-approve: если delta < 5% и policy_version позволяет.
    Иначе: owner confirm.

  D3 — PROCUREMENT (закупка)
    Примеры: create_purchase_order, supplier_payment
    Риск: высокий. Частично irreversible.
    Auto-approve: только S1 (known supplier, known SKU, amount < limit).
    Иначе: owner confirm. SAGA обязательна.

  D4 — FINANCIAL (платежи, возвраты)
    Примеры: send_invoice, process_refund
    Риск: высокий. Irreversible.
    Auto-approve: send_invoice < financial_limit.
    Refund: ВСЕГДА owner confirm.
    Guardian veto обязателен.

  D5 — INVENTORY-AFFECTING (изменение остатков)
    Примеры: reserve_stock, write_off, inter-cluster transfer
    Риск: критический. Влияет на оба кластера.
    Auto-approve: reserve для confirmed order.
    Write-off / transfer: ВСЕГДА owner confirm.

  Правило: Policy Packs могут расширять auto-approve
  только для D1-D2. D3-D5 требуют Stability Gate per rule.


═══════════════════════════════════════════════════════
STATE OWNERSHIP LOCKS (НОВОЕ в v1.7.2)
═══════════════════════════════════════════════════════

  Проблема: AI Executor и человек (Максим) могут одновременно
  попытаться изменить статус одной сущности.

  Правило: HUMAN > AI. Всегда.

  Реализация:
    FSM имеет поле: locked_by (NULL / human:{employee_id} / system:{job_id})

    Если locked_by = human:
      - AI Executor получает BLOCKED + escalation
      - AI НЕ может перезаписать human lock
      - Human завершает действие → lock снимается

    Если locked_by = system:
      - Human может OVERRIDE (force unlock + cancel system action)
      - System action откатывается через SAGA compensation
      - Override логируется как manual intervention

    Если locked_by = NULL:
      - Первый claim wins (optimistic locking с version check)
      - AI claims → locked_by = system
      - Human claims → locked_by = human (приоритет если одновременно)

    Lock TTL: system locks expire после 5 минут (zombie protection).
    Human locks expire после 30 минут + алерт.


═══════════════════════════════════════════════════════
DOUBLE-ENTRY LEDGER (НОВОЕ в v1.7.2)
═══════════════════════════════════════════════════════

  Минимальный финансовый учёт для детерминированной P&L.

  Таблица: ledger_entries

    Поля:
      - id
      - trace_id
      - entry_date
      - debit_account (string: "inventory", "receivables", "revenue",
                       "cogs", "cash_rub", "cash_usd", etc.)
      - credit_account
      - amount_minor (в валюте операции)
      - currency_code (ISO 4217)
      - fx_snapshot_id (ссылка на FX snapshot, если конвертация)
      - amount_base_minor (в базовой валюте для отчётности)
      - entity_type (order / invoice / purchase / shipment / refund)
      - entity_id
      - description

  Принципы:
    - Каждая операция = минимум 2 записи (debit + credit)
    - SUM(debits) = SUM(credits) ВСЕГДА (invariant check)
    - Append-only (никаких правок, только сторно)
    - Replay-safe: fx_snapshot_id фиксирует курс
    - Reconciliation: ledger_balance vs bank_statement

  Примеры:
    Продажа: debit receivables, credit revenue
    Оплата получена: debit cash, credit receivables
    Закупка: debit inventory, credit cash/payables
    Возврат: debit returns, credit receivables (сторно)

  IC-10 (новый invariant check):
    SUM(all_debits) = SUM(all_credits) per currency. Всегда.


═══════════════════════════════════════════════════════
IDENTITY RESOLUTION LAYER (НОВОЕ в v1.7.2)
═══════════════════════════════════════════════════════

  Проблема: Catalog Factory может создать 3 версии одного SKU
  из разных источников (разные DataSheets, разные поставщики).

  Identity Resolution Service:

    При создании CanonicalProduct draft:
      1. Exact match: MPN + brand → existing product? → merge
      2. Fuzzy match: normalized name + category + key attributes
         → confidence score
      3. Cross-datasheet evidence: совпадение характеристик

    Identity Confidence Score:
      HIGH (>0.95): exact MPN match → auto-merge
      MEDIUM (0.7-0.95): fuzzy match → human review
      LOW (<0.7): likely different product → create new

    Дедупликация:
      - Periodic job: scan CDM for potential duplicates
      - Merge = CDM migration (append-only, старый ID → redirect to canonical)
      - Все листинги/заказы с old ID → remapped

    Защита:
      - Merge только через Governance (human confirm для MEDIUM)
      - AUTO-merge только для HIGH confidence
      - Log: identity_resolution_log (trace_id, source_ids, merged_to, confidence)


═══════════════════════════════════════════════════════
FAILURE DOMAIN MAPPING (НОВОЕ в v1.7.2)
═══════════════════════════════════════════════════════

  Автономная система = failure-aware система.
  Для каждого узла: что происходит при его падении.

  VPS-1 (СНГ) DOWN:
    Последствия:
      - RU операции: НЕДОСТУПНЫ (заказы, оплаты, отгрузки РФ)
      - INT операции: РАБОТАЮТ (VPS-2 автономен)
      - Global Inventory Hub: НЕДОСТУПЕН → VPS-2 работает по последней
        известной квоте (pessimistic, не oversell)
      - Telegram bot (RU): НЕДОСТУПЕН
    Recovery: DR procedure (OR-1), PITR restore, RTO < 4ч.
    Митигация: daily backup на VPS-2 или облако.

  VPS-2 (USA) DOWN:
    Последствия:
      - INT операции: НЕДОСТУПНЫ
      - RU операции: РАБОТАЮТ (VPS-1 автономен)
      - AI Cloud proxy: НЕДОСТУПЕН → Local PC используется напрямую
        или VPS-1 cloud proxy fallback
      - INT marketplace listings: не обновляются до восстановления
    Recovery: DR procedure, RTO < 4ч.

  LOCAL PC DOWN:
    Последствия:
      - AI генерация: переключение на Cloud AI (automatic)
      - Business Memory: НЕДОСТУПНА → AI отвечает без memory context
        (degraded, но работает)
      - Каталог генерация: останавливается (LOW priority queue)
      - Customer-facing AI: Cloud fallback (HIGH priority)
    Recovery: включить PC. Нет потери данных (VPS = truth).
    Критичность: НИЗКАЯ. Система продолжает работать.

  SNAPSHOT STORE CORRUPTED:
    Последствия:
      - Replay: НЕВОЗМОЖЕН для corrupted периода
      - Новые операции: РАБОТАЮТ (новые snapshots пишутся)
      - Decision jobs: могут fail если нужен corrupted snapshot
    Recovery: restore from backup. IC check.
    Митигация: snapshot integrity check в RC.

  INTER-NODE CONTRACT MISMATCH:
    Последствия:
      - Сообщение между узлами REJECTED (не silent fail)
      - Алерт владельцу
      - Affected operations queued до fix
    Recovery: deploy fix с backward-compatible schema.

  AI HALLUCINATION IN EXTRACTOR:
    Последствия:
      - Draft содержит неверные данные
      - Reviewer (GPU-2) должен поймать → reject
      - Если Reviewer пропустил → Guardian ловит при mutation
      - Если Guardian пропустил → RC catch при reconciliation
    Митигация: 3 уровня защиты (Reviewer → Guardian → RC).

  PARTIAL CDC EVENT DELIVERY:
    Последствия:
      - Один кластер не получил event
      - Inventory рассинхрон
    Recovery: CDC retry с idempotency. RC cross-cluster check.
    Митигация: pessimistic inventory (quota-based).


═══════════════════════════════════════════════════════
POLICY SIMULATION / BACKTESTING (НОВОЕ в v1.7.2)
═══════════════════════════════════════════════════════

  Перед активацией нового Policy Pack в production:

  Процесс:
    1. Новый policy pack создан (pricing_policy_v2)
    2. System запускает Replay на данных за прошлый месяц
       с новой policy версией
    3. Сравнение: что было бы по-другому?
       - Сколько решений изменилось бы
       - Влияние на маржу
       - Количество auto-approve vs escalation
    4. Результат: simulation_report
    5. Owner review → approve policy → activate

  Это превращает Policy Packs из "надеемся что правильно"
  в "доказано на исторических данных".

  Ограничение: simulation не учитывает поведенческие изменения
  (покупатель мог бы купить по другой цене). Только structural impact.


═══════════════════════════════════════════════════════
CIRCUIT ESCALATION MODEL (НОВОЕ в v1.7.2)
═══════════════════════════════════════════════════════

  Smart Throttling с уровнями деградации:

  L1 — WARN:
    API rate limit приближается к 70%
    → алерт, мониторинг, никаких ограничений

  L2 — THROTTLE:
    Rate limit > 85% ИЛИ latency > 2x SLA
    → P3/P4 задачи приостановлены (каталог, мониторинг)
    → P1/P2 работают нормально

  L3 — FREEZE CATALOG:
    Rate limit > 95% ИЛИ множественные 429 ошибки
    → Все неcritical операции заморожены
    → Только P1 (оплата, отгрузка) работает
    → Алерт владельцу

  L4 — EMERGENCY:
    API полностью недоступен ИЛИ error rate > 50%
    → Circuit Breaker OPEN
    → Все операции через этот API в retry queue
    → Алерт SEV-2


═══════════════════════════════════════════════════════
OUTBOUND GOVERNANCE QUOTA (НОВОЕ в v1.7.2)
═══════════════════════════════════════════════════════

  Защита от AI-спама поставщиков.

  Лимиты per supplier:
    - max_emails_per_day: 3 (default)
    - max_rfq_per_week: 5 (default)
    - cooldown_after_rejection: 7 дней
    - escalation_if_exceeded: алерт владельцу

  Supplier Fatigue Metric:
    - response_rate: % ответов на наши запросы
    - avg_response_time
    - Если response_rate < 20% → supplier помечен "fatigued"
    - Fatigued supplier: только manual outbound (owner initiated)

  Exponential Suppression:
    - 1-й запрос → нормально
    - 2-й за день → 1ч delay
    - 3-й за день → blocked до завтра
    - Blacklist: supplier запросил не писать → permanent block


═══════════════════════════════════════════════════════
INFRASTRUCTURE TOPOLOGY (из v1.7.1 + Local AI Priority Queue)
═══════════════════════════════════════════════════════

  VPS-1 (СНГ): Core RU, Windmill, RU adapters, Global Inventory Hub
  VPS-2 (USA): Core INT, AI proxy, INT adapters, Supplier scraping
  Local PC (2x 3090): AI roles (6), Memory Vault, NO side-effects

  Local AI Priority Queue:
    HIGH → customer-facing (auto-cloud fallback)
    MEDIUM → business operations
    LOW → background (catalog, photos)

  Smart Throttling: P1-P4 priorities, Circuit Escalation L1-L4.


═══════════════════════════════════════════════════════
BUSINESS MEMORY VAULT (ОБНОВЛЕНО в v1.7.2)
═══════════════════════════════════════════════════════

  Memory ≠ Truth. Memory = read-only knowledge plane.

  Strict metadata schema: entity_type, entity_id, decision_id,
  trace_id, time_range, visibility_scope, source_class, embedding.

  Decision Trail Index: queryable по дате/типу/клиенту/поставщику.
  Shadow Logging for RAG: с Phase 2.
  Contracted Retrieval: memory_evidence_ids[] обязательны.

  Memory TTL + Compaction (НОВОЕ в v1.7.2):

    Retention per type:
      Decisions: 3 года (regulatory + audit)
      Actions log: 2 года
      Observation data: 1 год
      Embeddings: refresh every 6 months (recompute with latest model)

    Compaction (еженедельно):
      - AI-Normalizer проходит по новым записям
      - Дедупликация (hash + semantic similarity)
      - Похожие наблюдения → merged summary
      - Original retained in COLD tier, summary in HOT

    Tiering:
      HOT: < 6 мес, ChromaDB/Qdrant in memory
      WARM: 6-24 мес, on disk
      COLD: > 24 мес, compressed archive

  Decision Snapshot Retention (НОВОЕ в v1.7.2):
    Successful decision snapshots: 1 год HOT, then WARM
    Failed/escalated snapshots: 2 года HOT (нужны для learning)
    Observation snapshots (external reads): по Data Retention Policy (OR-4)

  Cross-cluster sync: только decision summaries + policies.


═══════════════════════════════════════════════════════
CORE LAYER (Phase 1–4.5) — сохранён из v1.7.1
═══════════════════════════════════════════════════════

  Все принципы, CDM v2, Phases 1-4.5 без изменений.
  CanonicalListing, FSM Listing/Quote, Observation vs Decision,
  Decision Snapshot, Policy Packs — из v1.7.1.

  Multi-currency: amount_minor + currency_code + fx_snapshot_id.


═══════════════════════════════════════════════════════
PHASES 3, 6-11 — из v1.7.1, сохранены
═══════════════════════════════════════════════════════

  Phase 3: Marketplace AI Factory + Cleaning Layer + Compliance.
  Phase 6: Proactive Operations.
  Phase 7: Procurement (3 сценария, SAGA, Compliance Engine, FX).
  Phase 8: Client Intelligence (ABC, LTV, scoring).
  Phase 9: Demand Intelligence (forecasting, dynamic pricing).
  Phase 10: Customer Self-Service (AI chat, RFQ, two clusters).
  Phase 11: Returns & Claims.


═══════════════════════════════════════════════════════
STABILITY GATE (18 критериев + 1 новый)
═══════════════════════════════════════════════════════

  1-18: из v1.6.2, сохранены.
  19. Ledger balance check: SUM(debits) = SUM(credits) per currency.


═══════════════════════════════════════════════════════
OPERATIONAL RESILIENCE (из v1.6.2)
═══════════════════════════════════════════════════════

  OR-1..OR-6 сохранены.


═══════════════════════════════════════════════════════
INVARIANTS (14 + 2 новых = 16)
═══════════════════════════════════════════════════════

  INV-VC, INV-ERS, INV-CTB, INV-MBC, INV-MI, INV-CR,
  INV-FL, INV-TIER, INV-CB, INV-SAGA, INV-IDEM,
  INV-KNOW, INV-NLOCK, INV-RATE, INV-TAX

  INV-OWN (НОВОЕ в v1.7.2): Data Ownership
    Каждая сущность имеет ровно одного owner (cluster/service).
    Только owner выполняет writes. Остальные = read-only events.
    Конфликт невозможен by design. Нарушение = architectural violation.

  INV-LEDGER (НОВОЕ в v1.7.2): Double-Entry Balance
    SUM(all_debits) = SUM(all_credits) per currency. Всегда.
    Нарушение = SEV-1 инцидент. IC-10 проверяет автоматически.


═══════════════════════════════════════════════════════
EXTENSION PROTOCOL / SELF-LEARNING / TESTING /
DEPLOYMENT / INCIDENT / CONFIG — сохранены из v1.7.1
═══════════════════════════════════════════════════════


═══════════════════════════════════════════════════════
FAILURE INJECTION (5 сценариев из v1.6.1)
═══════════════════════════════════════════════════════


═══════════════════════════════════════════════════════
OWNER COGNITIVE LOAD METRIC
═══════════════════════════════════════════════════════

  manual_interventions_per_week
  Phase 2.5: <20 | Phase 4.5: <5 | Gate: <3 | Phase 5: <1


═══════════════════════════════════════════════════════
TECHNICAL DEBT REGISTER
═══════════════════════════════════════════════════════

  TD-001..TD-020: из v1.7.1, сохранены.
  TD-021: Double-entry Ledger не реализован → Review: Phase 2
  TD-022: Identity Resolution не реализован → Review: Phase 3
  TD-023: Failure Domain → задокументирован, тестировать при Stability Gate
  TD-024: Policy Simulation → Review: Phase 5
  TD-025: Guardian role → Review: Phase 2.5 (hardcoded checks)


═══════════════════════════════════════════════════════
POST-CORE ACCELERATION LADDER (из Addendum v1.0)
═══════════════════════════════════════════════════════

  Стратегия ускорения Tier-3 разработки без деградации качества.
  Четыре ступени, строго последовательно:

  RUNG 1 — ЭТАП 2.5: Context Cortex
    PROJECT_DNA + AI Reviewer Prompt + Definition of Done.
    Цель: стандартизированный контекст и ревью для AI и человека.

  RUNG 2 — ЭТАП 5.5: Iron Fence
    Tier-1 Hash Lock + Boundary Grep + Migration DDL Guard + Ruff.
    Цель: автоматический "забор" вокруг Core в CI.

  RUNG 3 — ЭТАП 8.x: Local AI Reviewer
    Локальные модели как ревьюер (не кодогенератор).
    Prerequisite: Iron Fence подтверждён на реальных PR.

  RUNG 4 — ЭТАП 12.5: Chaos / Replay Regression
    Автоматическое тестирование отказоустойчивости.
    Prerequisite: 3+ Tier-3 автоматизации в production.

  Принцип: механизмы не меняют Core, не требуют постоянной
  поддержки, работают как конвейер автоматических проверок.


═══════════════════════════════════════════════════════
STOP RULES
═══════════════════════════════════════════════════════

  v1: Phase 4.5 — СНГ, сотрудник автономен.
  v2: Phase 5 — автономность 90%+.
  v3: Phase 7+10 — оба рынка, покупатели без владельца.


═══════════════════════════════════════════════════════
МОЯ ЛИЧНАЯ ЦЕЛЬ
═══════════════════════════════════════════════════════

  Автономная B2B платформа. AI-завод.
  Human = стратег. Система умнеет каждый день.


═══════════════════════════════════════════════════════
ПРИОРИТЕТ
═══════════════════════════════════════════════════════

  Архитектурная чистота > скорость
  Детерминизм > магия
  Контракт > хаос
  Стабильность > амбиции
  Human-in-the-loop > полная автономность
  Core first > Vision first

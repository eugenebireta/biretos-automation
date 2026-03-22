BIRETOS AUTOMATION
MASTER PLAN v1.9.1

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
  - FIX: Conflict resolution → ownership isolation
  - Decision Classes D1-D5, Double-entry Ledger, Identity Resolution
  - Failure Domain Mapping, Guardian (6-я роль), State Ownership Locks
  - Policy Simulation, Decision Snapshot Retention, Memory TTL
  - Circuit Escalation L1-L4, Outbound Governance Quota
  - INV-OWN, INV-LEDGER
v1.7.2 → v1.7.3:
  - STOP RULES синхронизированы с Roadmap (v1-v4, привязка к Этапам)
  - POST-CORE ACCELERATION LADDER (Rung 1-4)
  - RETENTION CLASSES (3 класса)
  - Core Freeze зафиксирован (117 тестов)
v1.7.3 → v1.8.0:
  - STRATEGIC MISSION + STRATEGIC DOCTRINE + OPERATIONAL FILTER
  - INTELLIGENCE LAYER (SS-1..SS-4)
  - INTELLIGENCE-TO-CORE BRIDGE
  - POLICY PACKS обновлены (rationale, Safety > Growth иерархия)
  - AI GOVERNANCE WORKFLOW (7 ролей, без привязки к моделям)
  - INV-GOV — 18-й инвариант с градацией рисков
  - Re-processing принцип для Intelligence данных
  - Иерархия документов обновлена
v1.8.0 → v1.9.0:
  - GOLD SKU ENGINE — Decision Layer между Intelligence и Procurement
    + Owner Aptechka / Procurement Cockpit (15.10.x)
  - R4 ANCHOR BUYER LIQUIDATION ENGINE — новый Revenue Track
  - POLICY PACKS: inventory_policy_v1 (Aptechka), lot_selection_policy_v1
  - MARKETPLACE ADAPTATION LAYER — раскрытие Этапа 10.4–10.5
  - CONTENT GENERATION + REVIEW GATE — новый шаг в Catalog Factory FSM
  - BUYER INTELLIGENCE — расширение Этапа 15
  - DEMAND RADAR — усиление формулировок Этапов 14 + 18
  - R3 LOT ANALYZER v2 — углубление lot pipeline + handoff в R4
  - OBSERVABILITY STRATEGY — подэтап 4.5
  - ROLLBACK MATRIX D1–D5 — дополнение Decision Classes
  - CDM MIGRATION / SCHEMA VERSIONING — дополнение Этапа 10
  - SHADOW LOGGING 8.1.6 — задел teacher-student pipeline
  - AGED STOCK LIQUIDATION ASSIST — подэтап 18.6
  - inventory_policy_v1 расширена: aged stock / bulky / auto-discount
  - INFRASTRUCTURE: Shopware = primary platform, Avito adapter
  - TD-026..TD-043 — 18 deferred capabilities
v1.9.0 → v1.9.1:
  - CATALOG PIPELINE PRINCIPLES: PN-first, evidence-grade, raw-first photo
  - catalog_evidence_policy_v1 — обязательна для R1+
  - R1 hardening: PN-first industrial MVP, input contract, confidence gate
  - TD-039..TD-043: Ozon Mirror, FBO/FBS, Warehouse Photo, Demand Fusion,
    B2B Naming Templates

═══════════════════════════════════════════════════════


═══════════════════════════════════════════════════════
СТРАТЕГИЧЕСКАЯ МИССИЯ
═══════════════════════════════════════════════════════

  Автономный B2B Decision & Execution Engine —
  система, которая операционно работает, обучается
  и масштабируется без участия владельца,
  обеспечивая измеримую доходность.


═══════════════════════════════════════════════════════
STRATEGIC DOCTRINE
═══════════════════════════════════════════════════════

  North Star

    Система должна:
    - Принимать решения автономно
    - Исполнять решения детерминированно
    - Минимизировать manual_interventions владельца
    - Поддерживать измеримую доходность (profit-per-decision)

  Safety > Growth (абсолютный приоритет)

    Safety Policies (Guardian / Owner) всегда имеют приоритет
    над Growth Policies (Intelligence / Autonomy Engine).
    Это не конфигурация. Это архитектурный инвариант.
    Нарушение Guardian лимита → блокировка на уровне схемы,
    не просто ошибка.

  Error Budget (принцип)

    Система имеет право на ошибки в рамках допустимого бюджета.
    Превышение бюджета = автоматическая деградация автономности
    (больше human-in-the-loop, меньше auto-approve).
    Восстановление — постепенное, через успешные решения.
    Конкретные пороги: в Policy Packs (Этап 9), не здесь.

  Устойчивость к внешним шокам

    Сбой одного компонента не останавливает критические операции.
    Graceful Degradation на каждом уровне — обязательно.

  Приоритеты (неизменны)

    Архитектурная чистота > скорость
    Детерминизм > магия
    Контракт > хаос
    Стабильность > амбиции
    Human-in-the-loop > полная автономность
    Core first > Vision first


═══════════════════════════════════════════════════════
OPERATIONAL FILTER
═══════════════════════════════════════════════════════

  Любая новая инициатива проходит три вопроса:

  1. Усиливает ли это Decision & Execution Engine?
  2. Снижает ли это manual_interventions владельца?
  3. Улучшает ли это profit-per-decision (PPD)?

  Если "нет" на все три → низкий приоритет.
  Если "нет" на два из трёх → требует обоснования.
  Если "да" хотя бы на один → обсуждаем.

  Profit-per-Decision (PPD) = ключевая метрика зрелости.
  PPD = (автономная выручка) / (количество автономных решений).
  Растёт по мере роста Autonomy Engine (Этап 9+).


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
    RU (VPS-1): Shopware (primary), InSales (transitional),
      Ozon, WB, YM, Avito, TBank, CDEK, ЭДО
    INT (VPS-2): eBay, Amazon, DHL, Int'l payments, Suppliers
    RULE: Side-effects only inside own cluster. Circuit Breaker each.


═══════════════════════════════════════════════════════
INTELLIGENCE LAYER (v1.8.0, ОБНОВЛЕНО в v1.9.0)
═══════════════════════════════════════════════════════

  Intelligence Layer — аналитический слой системы.
  Tier-3. Не мутирует Core. Не создаёт второй truth layer.
  Intelligence генерирует Observation Snapshots и Decision Proposals.
  Core исполняет только после валидации Guardian.

  Evidence-grade Enrichment (v1.9.1):
    Любое обогащение карточки опирается на evidence bundle
    (title_evidence, image_evidence, price_evidence) с confidence score.
    Enrichment без evidence = draft, не publishable fact.

  SS-1 DataSheet Layer
    Сырые структурированные данные о товарах.
    Версионированный, snapshot-зависимый, re-processable.
    Re-processing принцип: rebuild_datasheet(version=N) →
    повторный прогон R3/Catalog/Quote.
    SS-1 данные никогда не становятся необратимыми.

  SS-2 Category Intelligence
    Классификация и таксономия товаров.
    Consumer: Catalog Factory (Этап 10), AI-assisted category mapping (10.4.5).

  SS-3 Price Intelligence
    Ценовая аналитика: конкуренты, история, тренды, маржа.
    Consumer: Quote Engine (Этап 12), Dynamic Pricing (Этап 18),
    Gold SKU Engine (Этап 15.10).
    SS-3 генерирует только Proposals.
    Применение цены — только через Guardian → Core.

  SS-4 Market Pulse
    Рыночные сигналы: спрос, сезонность, позиции конкурентов.
    Consumer: Demand Intelligence (Этап 18), Procurement (Этап 16),
    Gold SKU Engine (Этап 15.10).

  R3 (Lot Analyzer) = R&D площадка Intelligence Layer.
  Intelligence = read-only knowledge plane поверх Core.
  Единственный источник правды — Core DB.


═══════════════════════════════════════════════════════
GOLD SKU ENGINE (НОВОЕ в v1.9.0)
═══════════════════════════════════════════════════════

  Единый Decision Layer, определяющий судьбу каждого SKU
  на основе сигналов спроса, маржи и доступности.
  Позиция: Этап 15.10 (между Client Intelligence и Procurement).

  Архитектура:
    Tier-3 модуль. Consumer SS-3 и SS-4. Выход — Decision Proposals
    через TaskIntent → Guardian → Core Executor.

  Решения по SKU:
    promote to aptechka / backorder / archive / source-via-lot.

  Режим Brand Gold SKU Discovery:
    brand → top demanded PN/series → generate sensor cards
    → collect clicks/RFQ → promote to aptechka/backorder.

  Входные сигналы:
    RFQ count (Этап 14), click/view data (Этап 18),
    margin (SS-3), buyer history (Этап 15), supply (Этап 16).

  Таблицы: rev_gold_sku_scores, rev_gold_sku_decisions
  Схемная изоляция: rev.* префикс (по DNA §5b)

  Owner Aptechka / Procurement Cockpit (15.10.x):
    Unified dashboard — главный экран owner для решений
    по аптечке, закупкам и ликвидации. UI-слой поверх
    Gold SKU Engine + inventory_policy_v1 + Aged Stock (18.6).
    Три зоны: что купить / что убрать / что срочно распродать.
    Owner queue: что требует approve (D3–D5).


═══════════════════════════════════════════════════════
INTELLIGENCE-TO-CORE BRIDGE (v1.8.0)
═══════════════════════════════════════════════════════

  Канонический путь данных:

    Intelligence Layer (SS-1..SS-4)
        ↓ генерирует
    Observation Snapshot
        ↓ поступает в
    Orchestration Layer (Decision Job)
        ↓ формирует
    Decision Proposal (TaskIntent)
        ↓ валидируется
    Guardian (INV-MARGIN, INV-FL, INV-TAX, INV-LEDGER...)
        ↓ если approved
    Core Executor → Core DB (через Tier-2 атомики)

  Жёсткие запреты для Intelligence Layer:
    - Прямые записи в Core таблицы — ЗАПРЕЩЕНО
    - Обход Pydantic-схем — ЗАПРЕЩЕНО
    - Side-effects без trace_id — ЗАПРЕЩЕНО
    - Прямые вызовы Tier-2 атомиков без TaskIntent — ЗАПРЕЩЕНО
    - JOIN'ы в Core таблицы из Intelligence workloads — ЗАПРЕЩЕНО


═══════════════════════════════════════════════════════
GLOBAL DATA OWNERSHIP (v1.7.2, ОБНОВЛЕНО в v1.9.0)
═══════════════════════════════════════════════════════

  Принцип: Conflict = impossible by design.
  Каждая сущность имеет ровно одного owner.
  Только owner может мутировать. Остальные получают read-only копию.

  Ownership Matrix:

    CanonicalProduct:
      Owner: Core DB (VPS-1 primary, replicated to VPS-2)
      Local PC = автор черновиков, НЕ owner of truth
      Draft → CDM migration → Core DB.

    CanonicalListing (ОБНОВЛЕНО в v1.9.0):
      Owner: VPS кластера где площадка
      RU listings → VPS-1. INT listings → VPS-2.
      1 CanonicalProduct / CDM → N platform-specific CanonicalListings.
      Каждый listing: свои категории, атрибуты, тексты, фото-требования.

    CanonicalOrder:
      Owner: VPS кластера где продажа

    Inventory:
      Owner: Global Inventory Hub (VPS-1 primary)
      Quota: RU_quota + INT_quota ≤ total_stock
      Pessimistic reservation (лучше отказать чем oversell)

    Pricing:
      Owner: VPS кластера (разные рынки = разные цены)

  Conflict Resolution:
    Конфликты невозможны через ownership isolation.
    Event version numbers (monotonic per entity) для ordering.
    НЕ timestamp-based resolution (clock skew unsafe).

  Синхронизация:
    CDC/Outbox: только events, не snapshots.
    Events: product_updated, inventory_reserved, price_changed.
    Каждый event: global_entity_id + cluster_source + version_number.

  Inter-node Contract Registry:
    Версионированные Pydantic schemas. Mismatch = reject + alert.

  При сетевом разрыве (CAP theorem):
    VPS-1 down → VPS-2 продолжает INT автономно.
    VPS-2 down → VPS-1 продолжает RU автономно.
    Local PC down → AI fallback на Cloud через VPS-2.


═══════════════════════════════════════════════════════
AI ROLES ARCHITECTURE (v1.7.2)
═══════════════════════════════════════════════════════

  6 операционных ролей (внутри системы):

  EXTRACTOR: raw data → structured. Read-only.
  NORMALIZER: structured → CDM draft. Draft-only.
  REVIEWER: draft → approved/rejected. Read-only + verdict.
  PLANNER: snapshots + policies → recommendation draft. Draft-only.
  EXECUTOR: approved TaskIntent → side-effect. Mutation via Core only.

  GUARDIAN (v1.7.2):
    Единственная роль с правом ВЕТО.
    Проверяет: INV-FL, INV-TAX, INV-SAGA, INV-RATE, Margin.
    Вызывается ПЕРЕД каждой мутацией.
    Вето = операция заблокирована + алерт + escalation.
    Guardian hardcoded (детерминированные проверки, не AI).
    Guardian нельзя обойти.

  Capability-based permissions:
    AI = draft-only. Mutation = only Executor via Governance.
    Guardian = veto gate перед Executor.


═══════════════════════════════════════════════════════
AI GOVERNANCE WORKFLOW (v1.8.0)
═══════════════════════════════════════════════════════

  7 ролей разработки. Роли постоянны — модели меняются.
  Текущее назначение моделей: см. EXECUTION_ROADMAP.

  SCOUT    — разведка текущего состояния кода и зависимостей
  ARCHITECT — проектирование архитектурного решения
  CRITIC   — независимый аудит, поиск рисков и пропусков
  JUDGE    — финальный вердикт (отдельный чат, без контекста Cursor)
  PLANNER  — детальный план реализации
  BUILDER  — реализация изменений
  AUDITOR  — пост-аудит результата против архитектуры

  Инварианты Workflow:
    - Один шаг за раз. Нельзя совмещать роли.
    - JUDGE всегда в отдельном чате (исключает confirmation bias).
    - Core Critical: все 7 ролей (INV-GOV обязателен).
    - Semi-Critical: ARCHITECT → CRITIC → PLANNER → BUILDER → AUDITOR.
    - Low Risk: ARCHITECT → BUILDER.
    - Нельзя пропускать фазу без явного решения владельца.


═══════════════════════════════════════════════════════
DECISION CLASSES (v1.7.2, ОБНОВЛЕНО в v1.9.0)
═══════════════════════════════════════════════════════

  D1 — INFORMATIONAL (read-only ответ)
    Риск: нулевой. Auto-approve: всегда.
    Rollback: не требуется.

  D2 — PRICING (изменение цены)
    Риск: средний. Reversible.
    Auto-approve: если delta < 5% и policy разрешает.
    Rollback: revert to previous price. Автоматический при margin < floor.

  D3 — PROCUREMENT (закупка)
    Риск: высокий. Частично irreversible.
    Auto-approve: только S1 (known supplier, known SKU, amount < limit).
    SAGA обязательна.
    Rollback: SAGA compensation. Может быть irreversible после shipment.

  D4 — FINANCIAL (платежи, возвраты)
    Риск: высокий. Irreversible.
    Refund: ВСЕГДА owner confirm. Guardian veto обязателен.
    Rollback: append-only correction (сторно). Guardian veto на сторно.

  D5 — INVENTORY-AFFECTING (изменение остатков)
    Риск: критический. Влияет на оба кластера.
    Write-off / transfer: ВСЕГДА owner confirm.
    Rollback: SAGA + owner confirmation. Cross-cluster: оба VPS confirm.

  Правило: Policy Packs расширяют auto-approve только для D1-D2.
  D3-D5 требуют Stability Gate per rule.


═══════════════════════════════════════════════════════
STATE OWNERSHIP LOCKS (v1.7.2)
═══════════════════════════════════════════════════════

  Правило: HUMAN > AI. Всегда.

  FSM поле: locked_by (NULL / human:{id} / system:{job_id})

  locked_by = human: AI Executor → BLOCKED + escalation.
  locked_by = system: Human может OVERRIDE → SAGA rollback.
  locked_by = NULL: First claim wins. Human приоритет.

  Lock TTL: system — 5 минут. Human — 30 минут + алерт.


═══════════════════════════════════════════════════════
DOUBLE-ENTRY LEDGER (v1.7.2)
═══════════════════════════════════════════════════════

  Таблица: ledger_entries
    id, trace_id, entry_date, debit_account, credit_account,
    amount_minor, currency_code, fx_snapshot_id,
    amount_base_minor, entity_type, entity_id, description

  Принципы:
    - Каждая операция = минимум 2 записи (debit + credit)
    - SUM(debits) = SUM(credits) ВСЕГДА (INV-LEDGER)
    - Append-only (никаких правок, только сторно)
    - Replay-safe: fx_snapshot_id фиксирует курс

  IC-10: SUM(all_debits) = SUM(all_credits) per currency. Всегда.


═══════════════════════════════════════════════════════
IDENTITY RESOLUTION LAYER (v1.7.2)
═══════════════════════════════════════════════════════

  HIGH (>0.95): exact MPN match → auto-merge
  MEDIUM (0.7-0.95): fuzzy match → human review
  LOW (<0.7): likely different → create new

  Merge только через Governance. AUTO-merge только для HIGH.
  Log: identity_resolution_log (trace_id, source_ids, merged_to, confidence)


═══════════════════════════════════════════════════════
POLICY PACKS (ОБНОВЛЕНО в v1.9.0)
═══════════════════════════════════════════════════════

  Policy Pack = versioned decision rule set.
  Примеры: pricing_policy_v1, quote_policy_v1, liquidity_scoring_v1,
  inventory_policy_v1, lot_selection_policy_v1.

  Иерархия политик:
    Safety Policies (Guardian / Owner) > Growth Policies (Intelligence)
    Нарушение Guardian лимита → блокировка на уровне схемы.

  Обязательное поле rationale:
    {
      "policy_id": "...",
      "version": N,
      "rationale": {
        "observation_id": "obs_...",
        "decision_snapshot_id": "snap_...",
        "description": "обоснование изменения"
      }
    }
    Без rationale Policy Pack не может быть активирован.

  Policy Simulation / Backtesting:
    Перед активацией → Replay на данных прошлого месяца.
    simulation_report → owner review → approve → activate.

  Статус: реализация после Этапа 9. До этого — ручные правила в БД.

  inventory_policy_v1 (Aptechka Portfolio Rules) (v1.9.0):
    Категория D5. Параметры: entry_criteria, exit_criteria,
    max_stock_per_sku, max_capital_per_category, target_sell_through,
    sku_roles, aged_stock_days_threshold, bulky_penalty_factor,
    max_auto_discount_pct. Guardian enforcement обязателен.

  lot_selection_policy_v1 (v1.9.0):
    Категория D3. Обязательна для R3+ Revenue Tracks.
    Параметры: core_slice_progression, cqr_threshold,
    unknown_exposure_max, cost_density_min, red_flags, part_number_driven.
    Backtesting: replay на исторических лотах.


═══════════════════════════════════════════════════════
FAILURE DOMAIN MAPPING (v1.7.2)
═══════════════════════════════════════════════════════

  VPS-1 DOWN: RU недоступны. INT работает. RTO < 4ч.
  VPS-2 DOWN: INT недоступны. RU работает. RTO < 4ч.
  LOCAL PC DOWN: AI → Cloud fallback. Данные не теряются.
  SNAPSHOT STORE CORRUPTED: Restore from backup.
  CONTRACT MISMATCH: REJECTED + алерт + queue.
  AI HALLUCINATION: 3 уровня (Reviewer → Guardian → RC).
  PARTIAL CDC: Retry с idempotency. RC cross-cluster check.


═══════════════════════════════════════════════════════
CIRCUIT ESCALATION MODEL (v1.7.2)
═══════════════════════════════════════════════════════

  L1 — WARN: rate limit > 70%. Алерт, нет ограничений.
  L2 — THROTTLE: > 85% или latency > 2x SLA. P3/P4 приостановлены.
  L3 — FREEZE CATALOG: > 95%. Только P1 работает. Алерт владельцу.
  L4 — EMERGENCY: Circuit Breaker OPEN. Все операции в retry queue.


═══════════════════════════════════════════════════════
OUTBOUND GOVERNANCE QUOTA (v1.7.2)
═══════════════════════════════════════════════════════

  Лимиты per supplier:
    max_emails_per_day: 3. max_rfq_per_week: 5.
    cooldown_after_rejection: 7 дней.

  Supplier Fatigue Metric:
    response_rate < 20% → supplier "fatigued" → только manual outbound.

  Exponential Suppression:
    2-й запрос за день → 1ч delay. 3-й → blocked до завтра.
    Blacklist: permanent block по запросу поставщика.


═══════════════════════════════════════════════════════
INFRASTRUCTURE TOPOLOGY (ОБНОВЛЕНО в v1.9.0)
═══════════════════════════════════════════════════════

  VPS-1 (СНГ): Core RU, Windmill, RU adapters, Global Inventory Hub
  VPS-2 (USA): Core INT, AI proxy, INT adapters, Supplier scraping
  Local PC (2x 3090): AI roles (6), Memory Vault, NO side-effects

  Shopware — основная операционная платформа (B2B магазин).
  InSales — источник / референс на переходный период.

  Local AI Priority Queue:
    HIGH → customer-facing (auto-cloud fallback)
    MEDIUM → business operations
    LOW → background (catalog, photos)

  Smart Throttling: P1-P4 priorities, Circuit Escalation L1-L4.


═══════════════════════════════════════════════════════
BUSINESS MEMORY VAULT (v1.7.2)
═══════════════════════════════════════════════════════

  Memory ≠ Truth. Memory = read-only knowledge plane.

  Strict metadata: entity_type, entity_id, decision_id,
  trace_id, time_range, visibility_scope, source_class, embedding.

  Memory TTL:
    Decisions: 3 года. Actions log: 2 года.
    Observation data: 1 год. Embeddings: refresh every 6 months.

  Tiering:
    HOT: < 6 мес (ChromaDB/Qdrant in memory)
    WARM: 6-24 мес (on disk)
    COLD: > 24 мес (compressed archive)

  Compaction (еженедельно):
    Дедупликация → merged summary. Original → COLD tier.

  Decision Snapshot Retention:
    Successful: 1 год HOT, then WARM.
    Failed/escalated: 2 года HOT (нужны для learning).
    Observation snapshots: по OR-4.

  Cross-cluster sync: только decision summaries + policies.


═══════════════════════════════════════════════════════
INVARIANTS (16 + 2 = 18)
═══════════════════════════════════════════════════════

  INV-VC, INV-ERS, INV-CTB, INV-MBC, INV-MI, INV-CR,
  INV-FL, INV-TIER, INV-CB, INV-SAGA, INV-IDEM,
  INV-KNOW, INV-NLOCK, INV-RATE, INV-TAX

  INV-OWN (v1.7.2): Data Ownership
    Каждая сущность = ровно один owner.
    Нарушение = architectural violation.

  INV-LEDGER (v1.7.2): Double-Entry Balance
    SUM(all_debits) = SUM(all_credits) per currency. Всегда.
    Нарушение = SEV-1.

  INV-GOV (v1.8.0): AI Governance Compliance
    Изменения Core, Policy Packs или инвариантов
    запрещены без AI Governance Workflow.

    Градация рисков:
      🔴 CORE-CRITICAL → Полный pipeline (все 7 ролей)
      🟡 POLICY-MEDIUM → Сокращённый pipeline
      🟢 LOG-LOW → Минимальный pipeline

    Escape hatch (SEV-1): # EMERGENCY-HOTFIX: <incident_id>
    Post-factum полный pipeline в течение 48 часов.


═══════════════════════════════════════════════════════
STABILITY GATE (19 критериев)
═══════════════════════════════════════════════════════

  1-18: из v1.6.2, сохранены.
  19. Ledger balance check: SUM(debits) = SUM(credits) per currency.


═══════════════════════════════════════════════════════
OPERATIONAL RESILIENCE
═══════════════════════════════════════════════════════

  OR-1..OR-6 сохранены из v1.6.2.


═══════════════════════════════════════════════════════
RETENTION CLASSES (v1.7.3)
═══════════════════════════════════════════════════════

  Core Operational (короткий TTL):
    reconciliation_audit_log: 30 дней
    reconciliation_alerts: 90 дней (sent/acked)
    reconciliation_suppressions: 30 дней после истечения

  Audit / Forensics (средний TTL):
    employee_actions_log: 2 года
    governance decisions: 3 года (regulatory)
    external_read_snapshots: по OR-4

  Revenue Artifacts (длинный TTL, дешёвое хранение):
    export_logs: 1 год
    stg_catalog_imports: 6 месяцев после публикации
    lot_scoring: 2 года
    фото/медиа: архив S3 (без удаления в v1)


═══════════════════════════════════════════════════════
POST-CORE ACCELERATION LADDER (v1.7.3)
═══════════════════════════════════════════════════════

  RUNG 1 — ЭТАП 2.5: Context Cortex ✔ ЗАКРЫТ
  RUNG 2 — ЭТАП 5.5: Iron Fence
  RUNG 3 — ЭТАП 8.1: Local AI Reviewer
  RUNG 4 — после 3+ автоматизаций: Chaos / Replay Regression


═══════════════════════════════════════════════════════
STOP RULES (v1.7.3)
═══════════════════════════════════════════════════════

  v1: Этап 8 — СНГ Core стабилен. Cognitive Load < 3/неделю.
  v2: Этап 16 — СНГ автономен на 90%+. Закупки автоматические.
  v3: Этап 19 — СНГ полностью автономен. Human = стратег.
  v4: Этап 23 — оба рынка автономны. AI-завод.

  Правило: можно остановиться на любом STOP RULE.


═══════════════════════════════════════════════════════
CORE LAYER / PHASES — сохранены из v1.7.1
═══════════════════════════════════════════════════════

  Все принципы CDM v2, CanonicalListing, FSM Listing/Quote,
  Observation vs Decision, Decision Snapshot, Multi-currency.

  Phase 3: Marketplace AI Factory + Cleaning Layer + Compliance.
  Phase 6: Proactive Operations.
  Phase 7: Procurement (3 сценария, SAGA, Compliance Engine, FX).
  Phase 8: Client Intelligence (ABC, LTV, scoring).
  Phase 9: Demand Intelligence (forecasting, dynamic pricing).
  Phase 10: Customer Self-Service (AI chat, RFQ, two clusters).
  Phase 11: Returns & Claims.


═══════════════════════════════════════════════════════
CATALOG PIPELINE PRINCIPLES (НОВОЕ в v1.9.1)
═══════════════════════════════════════════════════════

  PN-first Identity:
    Brand + Part Number = canonical identity key для каталога.
    Source names из Excel/supplier feeds = raw input, не truth.
    Карточка без нормализованного PN = draft, не publishable.

  Evidence-grade Enrichment:
    Обогащение карточки опирается на evidence bundles:
    title_evidence, image_evidence, price_evidence — каждый
    с confidence score. Без evidence = placeholder, не факт.

  Raw First, Enhancement Later (Photo Path):
    Найденное изображение сохраняется как raw image evidence.
    Fast publish path = raw usable image или placeholder.
    Slow enhancement path = local AI improvement (background).
    Фото не блокирует revenue. Placeholder допустим.

  catalog_evidence_policy_v1:
    Обязательна для R1+ Revenue Tracks. Определяет: что считается
    acceptable evidence, confidence thresholds, когда safe auto-publish
    допустим, когда review обязателен.
    Реализация: вместе с R1, не раньше.


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
TECHNICAL DEBT REGISTER (ОБНОВЛЕНО в v1.9.0)
═══════════════════════════════════════════════════════

  TD-001..TD-020: из v1.7.1, сохранены.
  TD-021: Double-entry Ledger → Review: Этап 13
  TD-022: Identity Resolution → Review: Этап 10
  TD-023: Failure Domain → тестировать при Stability Gate
  TD-024: Policy Simulation → Review: Этап 9
  TD-025: Guardian role → Review: Этап 5.4

  TD-026: AI Store Operator → Review: Этап 14+
  TD-027: Email Intelligence Hub → Review: Этап 14+
  TD-028: RFQ Sourcing Research Engine → Review: Этап 12
  TD-029: Selective Channel Routing Policy → Review: Этап 10
  TD-030: Image Acquisition Policy → Review: Этап 10
  TD-031: Local Debug & Regression Lab → Review: Этап 8.1
  TD-032: Multi-quantity / Lot-sale Logic → Review: Этап 10
  TD-033: Datasheet-media Pipeline → Review: Этап 10
  TD-034: Owner Context Profile → Review: Этап 19
  TD-035: Active Work Threads Continuity → Review: Этап 19
  TD-036: SOP Memory Registry → Review: Этап 19
  TD-037: Role-Based Retrieval Profiles → Review: Этап 19 + 8.1
  TD-038: Strategy / Hypothesis Memory → Review: Этап 19 + 15.10
  TD-039: Ozon Marketplace Mirror → Review: после R1 hardening
  TD-040: FBO/FBS Allocation Engine → Review: Этап 16
  TD-041: Warehouse Photo Intelligence Pipeline → Review: Этап 8.1 + 10
  TD-042: Demand Signal Fusion Engine → Review: Этап 18
  TD-043: B2B Naming Templates Library → Review: Этап 10

  Детали TD-026..TD-043: см. _archive/MASTER_PLAN_PATCH_v1_9_0.md
  и changelog v1.9.0 → v1.9.1 в этом документе.


═══════════════════════════════════════════════════════
CORE FREEZE STATUS (зафиксировано в v1.7.3)
═══════════════════════════════════════════════════════

  Core заморожен после:
  - Commit Retention Policy (Option A)
  - 117 тестов passed (PHASE2_BOUNDARY.md)
  - 19 файлов Tier-1 зафиксированы

  Дальнейшие изменения Tier-1: только через 🔴 CORE-CRITICAL pipeline.


═══════════════════════════════════════════════════════
ИЕРАРХИЯ ДОКУМЕНТОВ (ОБНОВЛЕНО в v1.9.0)
═══════════════════════════════════════════════════════

  При конфликте между документами:

  1. PROJECT_DNA.md — правила для AI-агентов (оперативный контекст)
  2. PHASE2_BOUNDARY.md + RETENTION_INVARIANT.md — frozen законы Core
  3. MASTER_PLAN v1.9.1 — стратегия, принципы, инварианты
  4. EXECUTION_ROADMAP v2.3 — операционный план и текущие модели
  5. _archive/MASTER_PLAN_PATCH_v1_9_0.md — исторический, детали v1.9.0
  6. _archive/* — исторические, не действуют

  Правило: если принцип есть в Master Plan и противоречит Roadmap —
  Master Plan побеждает. Roadmap обновляется.

  Правило дублирования: если правило есть в PROJECT_DNA —
  в других документах только ссылка, не копия.

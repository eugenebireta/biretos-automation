# PROJECT DNA — Biretos Automation
## Версия: 2.3 (Post-Core Freeze)
## Дата: 2026-03-26

Это единственный источник правил для AI-агентов.
Если правило есть здесь — оно действует.
Если правило только в другом файле — оно не действует для AI.

---

## 1. Identity

Biretos Automation — промышленная система автоматизации e-commerce и B2B-процессов.

Stack: Python 3.11 / PostgreSQL / Windmill / FastAPI / Raw SQL / Idempotency-first

Статус: **Core заморожен.** Система перешла в режим Post-Core Revenue (Tier-3 конвейер).

---

## 1b. Иерархия документов

При конфликте между документами:
1. PROJECT_DNA.md — правила для AI-агентов (этот файл)
2. docs/MASTER_PLAN_v1_9_2.md — стратегия, принципы, инварианты
3. docs/EXECUTION_ROADMAP_v2_3.md — операционный план, текущие статусы

Перед началом работы над любой задачей — прочитай EXECUTION_ROADMAP
для определения текущего этапа и следующей задачи.

---

## 2. Three-Tier Architecture

| Tier | Назначение | Правило |
|------|-----------|---------|
| **Tier 1 — Infrastructure Core** | Reconciliation engine, retention, structural checks, observability | FROZEN — никаких изменений |
| **Tier 2 — Business Domain** | payment, shipment, availability, document, fsm, ports | Stable API — можно расширять, нельзя менять pinned сигнатуры |
| **Tier 3 — Extension Layer** | ru_worker, side_effects, webhook_service, cli, migrations/020+, Revenue воркеры | OPEN — но со строгими ограничениями |

---

## 3. Tier-1 Frozen Files (19 файлов — АВТОРИТЕТНЫЙ СПИСОК)

Эти файлы НЕЛЬЗЯ изменять после Core Freeze.
Источник: `PHASE2_BOUNDARY.md` (зафиксировано 2026-02-20).

### Reconciliation Engine (7 файлов)
- `.cursor/windmill-core-v1/maintenance_sweeper.py`
- `.cursor/windmill-core-v1/retention_policy.py`
- `.cursor/windmill-core-v1/domain/reconciliation_service.py`
- `.cursor/windmill-core-v1/domain/reconciliation_verify.py`
- `.cursor/windmill-core-v1/domain/reconciliation_alerts.py`
- `.cursor/windmill-core-v1/domain/structural_checks.py`
- `.cursor/windmill-core-v1/domain/observability_service.py`

### Reconciliation Schema (4 файла)
- `.cursor/windmill-core-v1/migrations/016_create_reconciliation_audit_log.sql`
- `.cursor/windmill-core-v1/migrations/017_create_reconciliation_suppressions.sql`
- `.cursor/windmill-core-v1/migrations/018_create_reconciliation_alerts.sql`
- `.cursor/windmill-core-v1/migrations/019_add_retention_indexes.sql`

### Safety Contracts and Tests (8 файлов)
- `.cursor/windmill-core-v1/docs/RETENTION_INVARIANT.md`
- `.cursor/windmill-core-v1/tests/validation/test_phase3_alert_emission.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase3_cache_read_model_contract.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase3_l3_structural_checks.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase3_replay_verify.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase3_structural_safety_contract.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase25_contract_guards.py`
- `.cursor/windmill-core-v1/tests/validation/test_phase25_replay_gate.py`

**Итого: 19 замороженных файлов.**

Изменение любого из них = нарушение архитектуры = требует отдельного Core Critical Pipeline.

---

## 4. Tier-2 Pinned API Surface

Следующие сигнатуры НЕ МОГУТ изменяться (имя, аргументы, возвращаемый тип):

- `_derive_payment_status()` — используется reconciliation_service + observability_service
- `_extract_order_total_minor()` — используется reconciliation_service + observability_service
- `recompute_order_cdek_cache_atomic()` — используется reconciliation_service
- `update_shipment_status_atomic()` — используется reconciliation_service
- `_ensure_snapshot_row()` — используется reconciliation_service
- `InvoiceStatusRequest` — используется reconciliation_service
- `ShipmentTrackingStatusRequest` — используется reconciliation_service

Изменение сигнатуры = нарушение архитектуры.
Тело функции менять можно. Сигнатуру — нельзя.

---

## 5. Absolute Prohibitions

### Tier-3 код НЕ МОЖЕТ:

**DML по reconciliation таблицам:**
- INSERT / UPDATE / DELETE по: `reconciliation_audit_log`, `reconciliation_alerts`, `reconciliation_suppressions`

**Raw DML по бизнес-таблицам (только через Tier-2 атомики):**
- INSERT / UPDATE / DELETE напрямую по: `order_ledger`, `shipments`, `payment_transactions`, `reservations`, `stock_ledger_entries`, `availability_snapshot`, `documents`

**Запрещённые импорты:**
- `domain.reconciliation_service`
- `domain.reconciliation_alerts`
- `domain.reconciliation_verify`
- `domain.structural_checks`
- `domain.observability_service`

**DDL в migrations/020+:**
- ALTER / DROP по reconciliation_* таблицам

**Обход Guardian:**
- Tier-3 НЕ МОЖЕТ вызывать Tier-2 atomic functions напрямую в обход Governance/TaskIntent pipeline
- Любое изменение бизнес-состояния Core из Tier-3 ОБЯЗАНО проходить через TaskIntent → Guardian → Executor
- Прямой вызов Tier-2 атомиков без Guardian = нарушение архитектуры

**Исключение для Revenue треков до реализации TaskIntent (Этап 6):**
  R1/R2/R3 НЕ мутируют Core бизнес-таблицы — они пишут только в свои
  staging-таблицы (stg_*, export_logs, lot_scoring) и вызывают внешние API.
  Запрет Guardian применяется только к мутациям Core бизнес-таблиц.
  После Этапа 6 — все мутации только через TaskIntent.

---

## 5b. Revenue-специфичные запреты

**Revenue FSM запрет:**
- Revenue job_state ограничен линейным пайплайном максимум из 5 состояний
- Запрещены: вложенные FSM, ветвления состояний, собственные retry-оркестраторы
- Допустимо: `pending → processing → done / failed` (и аналогичные линейные цепочки)
- Нарушение = Revenue воркер превращается во второй Core

**Схемная изоляция Revenue таблиц:**
- Все Revenue таблицы используют префикс схемы: `rev.` или именование `stg_*` / `rev_*` / `lot_*`
- Core код (Tier-1, Tier-2) НЕ МОЖЕТ делать JOIN к таблицам с этими префиксами
- READ-доступ Revenue воркеров к Core данным — только через определённые read-only views
- Запрещено: произвольные SELECT из Revenue кода напрямую в Core таблицы

---

## 6. Revenue Layer Rules (Post-Core)

Revenue-воркеры (Catalog, Telegram Export, Lot Analyzer) — это Tier-3 адаптеры.

**Обязательные правила для Revenue Tier-3:**
- Общаться с Core ТОЛЬКО через стабильные Tier-2 контракты (атомики и read-only views)
- НЕ делать прямых JOIN'ов в Core таблицы из Revenue workloads
- Единый формат: `trace_id` + `idempotency_key` + `job_state` для всех Revenue воркеров
- Lot Analyzer = отдельная схема/workload, ingestion только через события/экспорты из Core

**Data Scopes (что какому воркеру разрешено):**

| Domain | Основная таблица | Разрешённые side-effects |
|--------|-----------------|-------------------------|
| Catalog Pipeline | `stg_catalog_imports` | InSales API, Shopware API |
| Telegram Export | `export_logs` | Telegram Bot API, S3 |
| Lot Analyzer | `lot_scoring` (отдельная схема) | Price Checker read-only |
| Anchor Buyer Liquidation | `rev_buyer_registry`, `rev_liquidation_offers`, `rev_liquidation_kpi` | Telegram Bot API (offers) |

---

## 7. Mandatory Patterns (для всех новых Tier-3 модулей)

Каждый воркер обязан:
1. Извлекать `trace_id` из payload
2. Использовать `idempotency_key` для side-effects
3. НЕ вызывать commit внутри domain операций
4. Делать commit только на уровне worker boundary
5. НЕ логировать секреты или raw payload без редактирования
6. Быть запускаемым и проверяемым изолированно: иметь точку входа (`if __name__ == '__main__'`, CLI или тест с подставными DB/API) для запуска без полного окружения Core.
7. Иметь хотя бы один детерминированный тест (unit или с подставными DB/API), покрывающий ключевую логику; тест не должен зависеть от live внешних API, немоканного времени или случайности.
8. На границе решения/действия логировать в структурированном виде: trace_id, ключевые входные данные (идентификаторы, тип операции, состояние) и исход/решение (что сделано или почему не сделано); без полного payload и без PII (см. запрет на секреты/raw payload).
9. При ошибке логировать в структурированном виде: trace_id, error_class (TRANSIENT | PERMANENT | POLICY_VIOLATION), severity (WARNING | ERROR), retriable (true | false). Запрещено подавлять исключения без логирования (no silent failure).

---

## 8. Parallelization Rules

**Одновременно активна только ОДНА крупная ветка. Чередование, не параллельность:**
Safety (3-5 дней) → Revenue (3-5 дней) → Safety → Revenue.

Naming convention:
- Safety/infra ветки: `infra/acceleration-*`
- Revenue ветки: `feat/rev-<name>-*`

Ветки `feat/rev-*` запрещено трогать файлы в `core/`, `domain/reconciliation/`, `infra/`.
Только `workers/`, `migrations/020+`, Revenue-специфичные модули.

**Нельзя параллельно:**
- Изменения одних и тех же файлов CI YAML одновременно
- Изменения Tier-1 boundary + рефактор воркеров одновременно
- Два агента в одном файле-воркере

---

## 8b. Batch Execution Contract (R1 / Revenue Tier-3 default)

Для `R1` / `Phase A` / Revenue Tier-3 / `SEMI-CRITICAL` работ
режим исполнения по умолчанию — bounded batch execution, а не
микро-диалог с постоянным возвратом за следующей мелкой командой.

- Один batch = один логический change-set
- Один batch = один risk class
- Один batch = один узкий outcome
- Один batch = максимум одна policy surface
- Любое изменение файла вне согласованного scope делает batch недействительным
- Batch без evidence pack недействителен
- Эскалация к owner допустима только через явные gate
- Для `R1` этот контракт НЕ разрешает multi-agent runtime

Операционные детали живут в policy / entrypoint документах.
Эта секция — authoritative anchor для AI.

---

## 9. Architectural Principles

- Idempotency First
- Fail Loud (никаких silent errors)
- No Hidden State Mutation
- Domain atomics only (Tier-2 owns business state)
- Reconciliation is read-only verification logic
- Retention never affects business correctness
- Revenue = Adapter, not second Core
- AI Executor = governed assistant, not trusted operator
- Execution Risk Classes (LOW/SEMI/CORE) определяют допуск (см. CLAUDE.md)
- Tracked guards must be versioned in repo, not only in .git/hooks
- Task Brief Required: каждая задача длительностью >5 bounded batches
  обязана иметь Task Brief (config/TASK_BRIEF_<name>.md) до начала
  активной разработки. Агенты обязаны прочитать brief перед каждым
  циклом. Brief содержит: goal, truth rules, exit condition, enrichment
  fields, scope, constraints, current state. Frozen секции меняет
  только owner. Current state обновляет агент.

---

## 10. Review Checklist (для AI — проверить перед генерацией кода)

- [ ] Нарушает ли изменение Tier-1 freeze? (сверить с §3)
- [ ] Есть ли trace_id?
- [ ] Есть ли idempotency_key?
- [ ] Нет ли raw SQL bypass по бизнес-таблицам?
- [ ] Не изменены ли pinned API? (сверить с §4)
- [ ] Нет ли ALTER на reconciliation tables?
- [ ] Нет ли прямого импорта из domain.reconciliation_* в Tier-3?
- [ ] Проходит ли мутация Core через Guardian/TaskIntent?
- [ ] Revenue таблицы используют схему rev.* или префикс stg_*/rev_*/lot_*?
- [ ] Revenue READ из Core идёт только через read-only views (не прямые SELECT)?
- [ ] Revenue job_state линейный, не более 5 состояний, без вложенных FSM?
- [ ] Для R1/Revenue batch граница scope объявлена явно и остаётся узкой?
- [ ] Нет ли changed files вне declared scope / policy surface?
- [ ] Есть ли evidence pack с semantic diff, raw logs, verification command и deferred list?
- [ ] Зависимость от out-of-scope items явно отражена как Yes/No?
- [ ] Для R1/Revenue явно подтверждены trace_id, idempotency_key, job_state, auditability и отсутствие hidden mutation / second Core drift?
- [ ] Новый Tier-3 модуль/воркер запускаем изолированно (точка входа или тест со stub-зависимостями)?
- [ ] Новый Tier-3 модуль/воркер имеет детерминированный тест (без live API, без немоканного времени/случайности)?
- [ ] Новый Tier-3 модуль/воркер логирует на границе действия trace_id, ключевые входы и исход/решение (без полного payload/PII)?
- [ ] При сбоях Tier-3 воркер логирует error_class, severity и retriable; нет подавления исключений без лога?

---

## 11. Glossary

- **Sweeper** — reconciliation loop orchestrator
- **Retention** — TTL cleanup of infra tables
- **Structural Checks** — L3 integrity validation
- **Verify-only replay** — read-only divergence detection
- **Atomic (Tier-2)** — единственный допустимый путь изменения business state
- **Side-effect** — внешний API вызов (Shopware, CDEK, TBank, Telegram)
- **Guardian** — veto-слой перед Executor, детерминированные проверки инвариантов
- **TaskIntent** — единственная точка входа для мутаций из Tier-3
- **Revenue Layer** — Tier-3 адаптеры для бизнес-автоматизаций (Catalog, TG Export, Lot Analyzer)

---


## 12. Workflow Compression (Owner-Approved)

Claude Code допущен как combined executor для ролей
SCOUT/ARCHITECT/PLANNER/BUILDER только в рамках Migration Policy.
CRITIC, AUDITOR, JUDGE остаются внешними и раздельными.
Это owner-approved temporary compression, а не отмена INV-GOV.
Для 🔴 CORE допускается только Strict Mode до явной отдельной отмены владельцем.


END OF DNA v2.3

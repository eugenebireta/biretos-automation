# PROJECT DNA --- Biretos Automation

## 1. Identity

Biretos Automation --- промышленная система автоматизации e-commerce и
B2B-процессов.

Цель: автоматизация операций (заказы, платежи, отгрузки, наличие,
сверка, side-effects) с минимальным участием основателя.

Stack: - Python 3.11 - PostgreSQL - Windmill job orchestration - FastAPI
(webhooks) - Raw SQL (без ORM) - Idempotency-first architecture

------------------------------------------------------------------------

## 2. Three-Tier Architecture

  ------------------------------------------------------------------------
  Tier             Назначение                      Правило
  ---------------- ------------------------------- -----------------------
  **Tier 1 ---     Reconciliation engine,          FROZEN --- никаких
  Infrastructure   retention, structural checks,   изменений
  Core**           observability                   

  **Tier 2 ---     payment, shipment,              Stable API --- можно
  Business         availability, document, fsm,    расширять, нельзя
  Domain**         ports                           менять pinned сигнатуры

  **Tier 3 ---     ru_worker, side_effects,        OPEN --- но с
  Extension        webhook_service, cli,           ограничениями
  Layer**          migrations/020+                 
  ------------------------------------------------------------------------

------------------------------------------------------------------------

## 3. Tier-1 Frozen Files (19)

(Список берётся дословно из PHASE2_BOUNDARY.md. Tier-1 никогда не
редактируется без пересмотра архитектуры.)

------------------------------------------------------------------------

## 4. Tier-2 Pinned API Surface

Следующие сигнатуры НЕ МОГУТ изменяться:

-   \_derive_payment_status()
-   \_extract_order_total_minor()
-   recompute_order_cdek_cache_atomic()
-   update_shipment_status_atomic()
-   \_ensure_snapshot_row()
-   InvoiceStatusRequest
-   ShipmentTrackingStatusRequest

Изменение сигнатуры = нарушение архитектуры.

------------------------------------------------------------------------

## 5. Absolute Prohibitions

### Tier-3 code НЕ МОЖЕТ:

-   Делать INSERT / UPDATE / DELETE по:
    -   reconciliation_audit_log
    -   reconciliation_alerts
    -   reconciliation_suppressions
-   Делать raw DML по бизнес-таблицам:
    -   order_ledger
    -   shipments
    -   payment_transactions
    -   reservations
    -   stock_ledger_entries
    -   availability_snapshot
    -   documents
-   Импортировать:
    -   domain.reconciliation_service
    -   domain.reconciliation_alerts
    -   domain.reconciliation_verify
    -   domain.structural_checks
    -   domain.observability_service
-   Делать ALTER / DROP по reconciliation\_\* таблицам в migrations/020+

------------------------------------------------------------------------

## 6. Mandatory Patterns (для всех новых Tier-3 модулей)

Каждый worker обязан:

1.  Извлекать `trace_id` из payload
2.  Использовать `idempotency_key` для side-effects
3.  НЕ вызывать commit внутри domain операций
4.  Делать commit только на уровне worker boundary
5.  НЕ логировать секреты или raw payload без редактирования
6.  Быть запускаемым и проверяемым изолированно: иметь точку входа (`if __name__ == '__main__'`, CLI или тест с подставными DB/API) для запуска без полного окружения Core.
7.  Иметь хотя бы один детерминированный тест (unit или с подставными DB/API), покрывающий ключевую логику; тест не должен зависеть от live внешних API, немоканного времени или случайности.
8.  На границе решения/действия логировать в структурированном виде: trace_id, ключевые входные данные (идентификаторы, тип операции, состояние) и исход/решение (что сделано или почему не сделано); без полного payload и без PII (см. запрет на секреты/raw payload).
9.  При ошибке логировать в структурированном виде: trace_id, error_class (TRANSIENT | PERMANENT | POLICY_VIOLATION), severity (WARNING | ERROR), retriable (true | false). Запрещено подавлять исключения без логирования (no silent failure).

------------------------------------------------------------------------

## 7. Architectural Principles

-   Idempotency First
-   Fail Loud (никаких silent errors)
-   No Hidden State Mutation
-   Domain atomics only (Tier-2 owns business state)
-   Reconciliation is read-only verification logic
-   Retention never affects business correctness

------------------------------------------------------------------------

## 8. Review Checklist (для AI)

Перед генерацией или изменением кода проверить:

-   Нарушает ли изменение Tier-1 freeze?
-   Есть ли trace_id?
-   Есть ли idempotency_key?
-   Нет ли raw SQL bypass?
-   Не изменены ли pinned API?
-   Нет ли ALTER на reconciliation tables?
- [ ] Новый Tier-3 модуль/воркер запускаем изолированно (точка входа или тест со stub-зависимостями)?
- [ ] Новый Tier-3 модуль/воркер имеет детерминированный тест (без live API, без немоканного времени/случайности)?
- [ ] Новый Tier-3 модуль/воркер логирует на границе действия trace_id, ключевые входы и исход/решение (без полного payload/PII)?
- [ ] При сбоях Tier-3 воркер логирует error_class, severity и retriable; нет подавления исключений без лога?

------------------------------------------------------------------------

## 9. Glossary

-   Sweeper --- reconciliation loop orchestrator
-   Retention --- TTL cleanup of infra tables
-   Structural Checks --- L3 integrity validation
-   Verify-only replay --- read-only divergence detection
-   Atomic (Tier-2) --- единственный допустимый путь изменения business
    state
-   Side-effect --- внешний API вызов (Shopware, CDEK, TBank, Telegram)

------------------------------------------------------------------------

## 12. Workflow Compression (Owner-Approved)

Claude Code допущен как combined executor для ролей
SCOUT/ARCHITECT/PLANNER/BUILDER только в рамках Migration Policy.
CRITIC, AUDITOR, JUDGE остаются внешними и раздельными.
Это owner-approved temporary compression, а не отмена INV-GOV.
Для CORE допускается только Strict Mode до явной отдельной отмены владельцем.

END OF DNA

BIRETOS AUTOMATION
EXECUTION ROADMAP v1.0

Последовательный план реализации Master Plan v1.4.3
Каждый шаг усиливает следующий.

═══════════════════════════════════════════════════════
ТЕКУЩАЯ ПОЗИЦИЯ
═══════════════════════════════════════════════════════

Готово:
  ✔ Idempotency v2 (multi-worker safe)
  ✔ FSM Guards (single source of truth)
  ✔ Hardening F2 (CASCADE → RESTRICT, order_total_minor)
  ✔ Governance: review_cases, governance_decisions, governance_case_create
  ✔ Observability IC-1..IC-9
  ✔ Payment/Shipment/Document services
  ✔ Side-effect workers (invoice, CDEK, Shopware)
  ✔ TBank adapter + webhook
  ✔ CDEK adapter (частично)
  ✔ Telegram router (15 команд)
  ✔ Git repo (synced, clean)

Не готово:
  ✗ Governance Executor (loop не замкнут)
  ✗ CI pipeline
  ✗ Branch protection
  ✗ Reconciliation RC-2..RC-7
  ✗ CDM runtime validation (Pydantic)
  ✗ Alerting
  ✗ EDO adapter
  ✗ AI Executive Assistant


═══════════════════════════════════════════════════════
ЭТАП 1 — ЗАМКНУТЬ GOVERNANCE LOOP
═══════════════════════════════════════════════════════
Срок: 1-2 недели
Зависимости: нет (всё готово)

  Шаг 1.1: Governance Executor
    governance_execute_approved:
      - берёт review_cases со статусом "approved"
      - определяет side-effect по action_type
      - вызывает через idempotency layer
      - пишет HUMAN_APPROVE в governance_decisions
      - approved → executing → executed
      - replay mode: verify-only

  Шаг 1.2: Corrections Apply
    governance с HUMAN_APPROVE_WITH_CORRECTION:
      - применяет correction_records
      - формирует новый action_snapshot
      - детерминированность

  Шаг 1.3: Smoke test
    - Создать governance case вручную
    - Approve
    - Убедиться что executor выполнил side-effect
    - Повторить (replay) — убедиться что verify-only

  Почему первый:
    Без executor'а система предлагает, но не делает.
    С executor'ом — замкнутый цикл. Это фундамент для ВСЕГО
    последующего: CI тестирует работающий loop, Backoffice
    использует governance для опасных операций, AI Assistant
    маршрутизирует через тот же Core.

  Усиливает → Этап 2:
    CI теперь может тестировать полный governance цикл.


═══════════════════════════════════════════════════════
ЭТАП 2 — CI + BRANCH PROTECTION
═══════════════════════════════════════════════════════
Срок: 1-2 дня
Зависимости: Этап 1 (есть что тестировать)

  Шаг 2.1: GitHub Actions
    - pytest при каждом push
    - Запускать tests/validation/ (IC checks, contract guards,
      replay gate, tier-1 stability guards)
    - Fail on error → блокирует merge

  Шаг 2.2: Branch Protection
    - Запрет прямого push в master
    - Обязательный PR
    - Обязательный проход тестов

  Шаг 2.3: Добавить governance executor в тесты
    - test_governance_executor_happy_path
    - test_governance_executor_replay_idempotent
    - test_governance_executor_correction_apply

  Почему второй:
    Теперь есть полный governance loop для тестирования.
    CI защищает ВСЁ что уже построено от регрессий.
    Без CI дальнейшая работа рискует сломать предыдущее.

  Усиливает → Этап 3:
    Reconciliation можно разрабатывать безопасно —
    CI ловит если что-то сломалось.


═══════════════════════════════════════════════════════
ЭТАП 3 — RECONCILIATION RC-2..RC-7
═══════════════════════════════════════════════════════
Срок: 1-2 недели
Зависимости: Этап 2 (CI защищает от регрессий)

  Шаг 3.1: RC-2 (CDEK shipment reconciliation)
  Шаг 3.2: RC-5 (Document reconciliation)
  Шаг 3.3: RC-6 (Order lifecycle reconciliation)
  Шаг 3.4: RC-7 (End-to-end transaction reconciliation)
  Шаг 3.5: Оставшиеся RC (по приоритету)
  Шаг 3.6: Добавить все RC в CI pipeline

  Почему третий:
    RC закрывают дыры в consistency. Без них Stability Gate
    не пройти (критерий #6: RC-1..RC-7 зелёные).
    CI гарантирует что новые RC не ломают старый код.

  Усиливает → Этап 4:
    Alerting может опираться на RC — если reconciliation
    обнаруживает расхождение, алерт срабатывает.


═══════════════════════════════════════════════════════
ЭТАП 4 — ALERTING
═══════════════════════════════════════════════════════
Срок: 3-5 дней
Зависимости: Этап 3 (RC готовы как источник алертов)

  Шаг 4.1: Alerting engine
    - IC нарушение → алерт (Telegram владельцу)
    - RC расхождение → алерт
    - FSM staleness → алерт
    - Zombie reservations → алерт

  Шаг 4.2: Alert routing
    - Critical (data corruption) → немедленно
    - Warning (staleness) → батч раз в час
    - Info (reconciliation ok) → daily digest

  Шаг 4.3: Интеграция с Telegram
    - Отдельный канал/чат для алертов (не смешивать с Максимом)

  Почему четвёртый:
    Теперь IC + RC работают, CI защищает. Alerting превращает
    пассивную диагностику в активное наблюдение. Система сама
    скажет если что-то не так. Это prerequisite для Stability Gate
    (критерий #12: alerting работает).

  Усиливает → Этап 5:
    Pydantic validation ошибки тоже можно алертить.
    Alerting станет единым каналом наблюдения.


═══════════════════════════════════════════════════════
ЭТАП 5 — CDM RUNTIME VALIDATION (Pydantic)
═══════════════════════════════════════════════════════
Срок: 1-2 недели
Зависимости: Этап 4 (валидационные ошибки → алерт)

  Шаг 5.1: Pydantic models для CDM v2
    - CanonicalOrder, OrderLineItem
    - CanonicalShipment
    - CanonicalProduct
    - CorrectionRecord
    - TaskIntent (для Phase 2.5)

  Шаг 5.2: Validation на 3 границах
    - Вход адаптеров (TBank webhook, CDEK response)
    - Граница Core (перед domain services)
    - Перед записью в truth tables

  Шаг 5.3: Валидационные ошибки → alerting
    - Невалидные данные не проходят в Core
    - Алерт при каждой блокировке

  Шаг 5.4: Добавить validation тесты в CI

  Почему пятый:
    Contract-First наконец становится runtime enforcement,
    а не просто документом. CDM v2 теперь реально контракт.
    Alerting сообщает если что-то пытается нарушить контракт.
    INV-CTB (Core Trust Boundary) реализован в коде.

  Усиливает → Этап 6:
    TaskIntent model готов — Backoffice Task Engine
    получает validated structured input.


═══════════════════════════════════════════════════════
ЭТАП 6 — BACKOFFICE TASK ENGINE (Phase 2.5)
═══════════════════════════════════════════════════════
Срок: 2-3 недели
Зависимости: Этап 5 (TaskIntent Pydantic model готов)

  Шаг 6.1: TaskIntent router
    - 7 intent'ов: send_invoice, send_upd, get_waybill,
      check_payment, resend_document, check_delivery, get_tracking
    - Маршрутизация intent → Core service

  Шаг 6.2: EmployeeRole + Permission model
    - Таблица employee_roles
    - allowed_intents, financial_limit, escalation_target
    - Проверка прав перед выполнением

  Шаг 6.3: employee_actions_log
    - Логирование каждого действия
    - trace_id привязка

  Шаг 6.4: EDO Adapter
    - Отправка УПД
    - Статус подписания
    - Получение подписанных документов

  Шаг 6.5: Расширение CDEK adapter
    - Получение товарной накладной
    - Полный статус доставки

  Шаг 6.6: External Read Snapshotting (INV-ERS)
    - Каждый ответ от TBank/CDEK/EDO → сохранение raw payload
    - Привязка к trace_id

  Шаг 6.7: Тесты + CI
    - Каждый intent → happy path тест
    - Permission denial тест
    - Escalation тест

  Почему шестой:
    Pydantic models и CI готовы. Task Engine строится на
    валидированных контрактах. Alerting следит. Governance
    loop замкнут. Всё что нужно для безопасного backoffice.

  Усиливает → Этап 7:
    AI Assistant получает готовый Task Engine —
    ему остаётся только парсить текст в TaskIntent.


═══════════════════════════════════════════════════════
ЭТАП 7 — AI EXECUTIVE ASSISTANT (Phase 4.5)
═══════════════════════════════════════════════════════
Срок: 2-3 недели
Зависимости: Этап 6 (Task Engine работает, intent'ы определены)

  Шаг 7.1: Intent Parser (NLU)
    - Принимает свободный текст от Максима
    - Возвращает TaskIntent (structured Pydantic model)
    - confidence score для каждого распознавания

  Шаг 7.2: Hybrid UI
    - confidence ≥ 0.9 → выполняет
    - confidence < 0.9 → кнопки "Вы имели в виду?"
    - AI недоступен → button-only fallback menu

  Шаг 7.3: Mandatory Button Confirmation (INV-MBC)
    - Мутирующий intent + confidence < 0.9 → кнопки
    - Сумма ≥ financial_limit → кнопки
    - Ambiguity (>1 candidate, delta < 0.1) → кнопки

  Шаг 7.4: Intent Versioning
    - model_version, prompt_version, confidence в каждом логе

  Шаг 7.5: Graceful Degradation
    - Level 0 (Nominal) → Level 1 (Degraded) → Level 2 (Fallback)
    - Автоматическое переключение + алерт владельцу

  Шаг 7.6: Escalation logic
    - Нестандартный запрос → владельцу
    - Финансовый риск → владельцу
    - "Позови босса" → владельцу

  Шаг 7.7: SLA мониторинг
    - p95 < 3 сек, accuracy > 95%, false positive < 2%

  Шаг 7.8: Полное тестирование
    - Каждый intent через NLU → happy path
    - Low confidence → кнопки
    - Fallback mode → button menu
    - Escalation → владелец получил уведомление

  Почему седьмой:
    Task Engine уже работает и протестирован. AI Assistant —
    это просто NLU-обёртка поверх него. Если NLU сломался —
    кнопки работают. Core не знает про NLU. Всё детерминированно.

  Усиливает → Этап 8:
    Максим работает через бота. Данные копятся в
    employee_actions_log. Governance decisions накапливаются.
    Система готовится к Stability Gate.


═══════════════════════════════════════════════════════
ЭТАП 8 — STABILITY GATE PREPARATION
═══════════════════════════════════════════════════════
Срок: 2-4 недели (эксплуатация, не разработка)
Зависимости: Этапы 1-7 (всё работает в production)

  Это НЕ разработка. Это наблюдение и стабилизация.

  Шаг 8.1: Запуск в production
    - Максим начинает работать через AI Assistant
    - Все операции через Task Engine
    - Alerting включён

  Шаг 8.2: Мониторинг критериев Stability Gate
    - Счётчик закрытых циклов (цель: ≥ 100)
    - Silent data corruption (цель: 0)
    - Manual interventions (цель: 0)
    - IC/RC статус (цель: все зелёные)
    - Replay divergence (цель: 0)
    - Governance decisions (цель: ≥ 50)
    - AI escalation rate (цель: < 20%)
    - p95 latency (стабильность)

  Шаг 8.3: Фикс багов по мере обнаружения
    - Через CI → PR → тесты → merge
    - Каждый баг → новый тест (regression prevention)

  Шаг 8.4: Weekly review
    - Раз в неделю: проверка всех метрик Stability Gate
    - Документирование прогресса

  Почему восьмой:
    Нельзя перескочить стабилизацию. B2B цикл длинный.
    Некоторые баги всплывут только через 2-4 недели.
    Это период "доказательства" что Core работает.

  Результат:
    Stability Gate PASSED → можно начинать Phase 5 (Autonomy).
    Или STOP RULE v1 → система работает стабильно, развитие опционально.


═══════════════════════════════════════════════════════
СУММАРНАЯ КАРТА
═══════════════════════════════════════════════════════

  Этап 1: Governance Executor      [1-2 нед]  → loop замкнут
      ↓ усиливает
  Этап 2: CI + Branch Protection   [1-2 дня]  → защита от регрессий
      ↓ усиливает
  Этап 3: Reconciliation RC-2..7   [1-2 нед]  → consistency
      ↓ усиливает
  Этап 4: Alerting                 [3-5 дней] → активное наблюдение
      ↓ усиливает
  Этап 5: Pydantic Validation      [1-2 нед]  → runtime contracts
      ↓ усиливает
  Этап 6: Backoffice Task Engine   [2-3 нед]  → Максим → система
      ↓ усиливает
  Этап 7: AI Executive Assistant   [2-3 нед]  → Максим → бот → система
      ↓ усиливает
  Этап 8: Stability Gate           [2-4 нед]  → доказательство стабильности

  Общий срок: ~3-4 месяца до Stability Gate

  После Stability Gate:
    → STOP RULE v1 (заморозить, работает)
    → или Phase 5 (Autonomy Layer)

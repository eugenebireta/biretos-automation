BIRETOS AUTOMATION
MASTER PLAN v1.4.3

(Architectural Clean Version — with Autonomy Vision)

═══════════════════════════════════════════════════════
CHANGELOG
═══════════════════════════════════════════════════════

v1.2 → v1.3:
  - Добавлены инженерные принципы (секция 1.1)
  - Core Layer (Phase 1-4) явно отделён от Autonomy Layer (Phase 5-6)
  - Добавлен Stability Gate между Core и Autonomy
  - Добавлен Stop Rule v2
  - Phase 5-6 описаны как архитектурный вектор, NOT roadmap
  - Запрет self-modifying behaviour без human confirmation
  - Phase 1-4, CDM v2 — без изменений (frozen contract)

v1.3 → v1.3.1:
  - Contract-First конкретизирован: runtime validation обязательна на 3 границах
  - Observability-First: alerting зафиксирован как обязательный milestone
  - Stability Gate усилен: добавлены метрики latency, replay divergence,
    manual DB edits, объём транзакций (≥100 закрытых циклов)
  - Phase 5: добавлена защита от approval fatigue (batching + приоритизация)
  - Phase 5: добавлен rollback механизм для governance_rules
  - Phase 5: governance_rules версионируются как код
  - Phase 5.2: переобучение моделей явно вынесено за пределы Core-цикла

v1.3.1 → v1.4:
  - Добавлена Phase 2.5 — Backoffice & Employee Automation
  - Добавлена Phase 4.5 — AI Executive Assistant
  - Обновлён Stability Gate: Phase 2.5 и 4.5 включены в Core Layer

v1.4 → v1.4.1:
  - Phase 2.5: добавлена таблица employee_actions_log
  - Phase 4.5: добавлен Intent Versioning
  - Phase 4.5: добавлен SLA для AI Assistant
  - Добавлен EXTENSION PROTOCOL

v1.4.1 → v1.4.2:
  - Phase 4.5: Hybrid UI — кнопки + NLU
  - Phase 4.5: Graceful Degradation (3 уровня)
  - Extension Protocol: CDM Schema Migration Protocol

v1.4.2 → v1.4.3:
  - Core Layer header: FROZEN → VERSIONED CONTRACT (INV-VC)
  - Принцип: добавлен External Read Snapshotting (INV-ERS)
  - Contract-First: Core принимает ТОЛЬКО TaskIntent (INV-CTB)
  - Phase 4.5.3: NLU явно определён как Adapter-layer функция
  - Phase 4.5.7: Mandatory Button Confirmation (INV-MBC)
  - Stability Gate: уточнено определение manual intervention (INV-MI)
  - Phase 5.3: Compensation Review при деактивации правила (INV-CR)
  - Добавлена секция INVARIANTS

═══════════════════════════════════════════════════════


0. ГЛОБАЛЬНАЯ ЦЕЛЬ

Построить долгоживущую AI-платформу для B2B индустриальной торговли, которая:

  - снижает моё личное участие
  - не создаёт новые ручные процессы
  - остаётся расширяемой
  - позволяет остановиться после Phase 4.5 и стабильно эксплуатировать систему
  - не требует постоянного переписывания
  - с каждым днём работает эффективнее (через deterministic learning)
  - позволяет сотруднику работать автономно без моего участия

Это не MVP.
Это архитектурная система.
Конечная цель — AI-завод для B2B торговли.


═══════════════════════════════════════════════════════
CORE LAYER (Phase 1–4.5) — DETERMINISTIC, VERSIONED CONTRACT
═══════════════════════════════════════════════════════

  Contract Status: VERSIONED (not ad-hoc mutable).
  "Frozen" означает: никаких неформальных изменений CDM, domain services или FSM.
  Все изменения только через CDM Schema Migration Protocol (см. Extension Protocol).
  Между миграциями контракт иммутабелен.


1. ОСНОВНЫЕ ПРИНЦИПЫ

  Core нельзя ломать.
  Adapter можно заменить.
  Все сущности имеют trace_id.
  Все процессы idempotent.
  Replay-safe по умолчанию.
  Никаких хаотичных JSON без контракта.
  Snapshotting для транзакционных сущностей.
  External Read Snapshotting: любой запрос к внешней системе (банк, СДЭК,
    ЭДО), результат которого влияет на решение или ответ, ОБЯЗАН
    сохранять raw response payload с привязкой к trace_id.
    Replay использует сохранённый snapshot, НЕ live API.
  Backward compatibility обязательна.
  Self-learning только через deterministic correction loop.
  Можно остановиться и не модернизировать бесконечно.


1.1 ИНЖЕНЕРНЫЕ ПРИНЦИПЫ

  SOLID:
    - Single Responsibility — каждый модуль делает одно
    - Open/Closed — расширяем через adapters, не правим Core
    - Liskov Substitution — адаптеры взаимозаменяемы
    - Interface Segregation — порты минимальны (ports.py)
    - Dependency Inversion — Core зависит от абстракций, не от реализаций

  Fail-Fast:
    - Система падает громко и рано
    - Никакого тихого проглатывания ошибок
    - Лучше отказать, чем испортить данные

  Contract-First:
    - CDM v2 — контракт (versioned)
    - Runtime contract validation обязательна на:
        * входах адаптеров (данные из внешних систем)
        * границе Core (перед передачей в domain services)
        * перед записью в truth tables (финальная проверка)
    - Реализация: Pydantic models для domain entities
    - Никаких implicit contracts
    - Core domain services принимают ТОЛЬКО структурированный TaskIntent
      (validated Pydantic model). Свободный текст, raw user input,
      неструктурированные payload'ы — ЗАПРЕЩЕНЫ на границе Core.
      NLU/Intent parsing — это Adapter-функция, не Core-функция.

  Event Mindset:
    - Каждое изменение состояния — это событие, не перезапись
    - CorrectionRecord, status_history, governance_decisions — примеры
    - Append-only для аудита

  Observability-First:
    - IC-1..IC-9 — invariant checks
    - trace_id end-to-end
    - Alerting обязателен:
        * IC/RC нарушения → немедленный алерт
        * FSM staleness → алерт
        * Zombie reservations → алерт
        * Реализация alerting — обязательный milestone перед Stability Gate

  KISS (Keep It Simple, Stupid):
    - Если решение требует объяснения на 3 страницы — оно слишком сложное
    - Простое и работающее > умное и хрупкое

  YAGNI (You Aren't Gonna Need It):
    - Не строить то, что не нужно прямо сейчас
    - Phase 5-6 описаны, но не реализуются до Stability Gate

  DRY (Don't Repeat Yourself):
    - Одна логика — одно место
    - FSM guards — single source of truth
    - Payment cache recompute — один deterministic path


2. ТЕКУЩИЙ СТАТУС (TIER-1 ЗАВЕРШЁН)

  Operational Stability реализована:

    Safe connection pooling (anti-poisoning)
    Zombie job guard
    Optimistic status update
    FOR UPDATE для ledger
    trace_id end-to-end
    Idempotent job processing
    Phase boundary enforcement (Core vs Legacy)

  Фундамент стабилен.


3. CANONICAL DOMAIN MODEL v2 (ЗАФИКСИРОВАН)

  Основные сущности:

  3.1 CanonicalProduct
    sku, brand, category, attributes (AI-enriched), dimensions,
    raw_source_data, media, marketplace_links, trace_id, schema_version

  3.2 MarketplaceProductMapping
    product_id, marketplace_code (ozon/wb), external_id, marketplace_sku,
    category_id, price_sync_status, last_price_sync_at, predicted_payload, status

  3.3 CanonicalOrder
    status, status_changed_at, payment_status, payment_status_changed_at,
    totals, customer, items (OrderLineItem), shipment_ids, trace_id

  3.4 OrderLineItem
    sku_snapshot, name_snapshot, attributes_snapshot, price_unit, quantity

  3.5 CanonicalShipment
    order_id, carrier, tracking, packages (linked via line_item_id),
    address (structured), status_history, trace_id

  3.6 CorrectionRecord
    entity_type, entity_id, field_path, old_value, new_value,
    classifier_version, trace_id

  CDM v2 считается контрактом (versioned).
  Никакие новые фазы не ломают CDM.
  Изменения — только через CDM Schema Migration Protocol.


4. ФАЗЫ РАЗВИТИЯ — CORE LAYER

  PHASE 1 — Operational Stability (DONE)

    Цель: Надёжный Core.

    ✔ RFQ pipeline
    ✔ Price search
    ✔ Shopware sync
    ✔ Stable worker
    ✔ Deterministic processing


  PHASE 2 — Financial + Logistics Core

    Цель: Закрыть жизненный цикл сделки.

    Payment фиксация (банки)
    Invoice generation
    UPD / накладные
    Shipment lifecycle
    SLA tracking
    Order → Shipment связность
    Документ-менеджмент

    Важно:
    Никаких marketplace-хакающих решений.
    Фокус — транзакционная чистота.


  PHASE 2.5 — Backoffice & Employee Automation

    Цель: Убрать владельца из ежедневной рутины сотрудника.
    Сотрудник работает через систему, а не через владельца.

    Контекст:
    Сотрудник (Максим) постоянно обращается к владельцу с задачами:
      - "Отправь счёт клиенту"
      - "Пришли накладную из СДЭК"
      - "Проверь, пришла ли оплата"
      - "Отправь УПД через ЭДО"
      - "Создай накладную"
    Phase 2.5 устраняет эту нагрузку.

    2.5.1 Backoffice Task Engine

      Типы задач (TaskIntent):
        - send_invoice        — отправить счёт клиенту
        - send_upd            — отправить УПД через ЭДО
        - get_waybill         — получить ТН от СДЭК
        - check_payment       — проверить оплату в Т-Банке
        - resend_document     — повторно отправить документ
        - check_delivery      — проверить статус доставки
        - get_tracking        — запросить трек-номер

      Архитектурный принцип:
        Максим НЕ пишет владельцу.
        Максим пишет в UCI (Telegram).
        UCI → TaskIntent → Core service.
        Core → выполняет через адаптеры.
        Core → возвращает результат в UCI.
        Владелец не участвует.

    2.5.2 Adapter Layer (External Integrations)

      Explicit adapters через Ports:

        TBankAdapter:
          - проверка статуса оплаты
          - получение выписки
          - создание счёта на оплату
          - webhook обработка (уже реализован)

        CDEKAdapter:
          - создание заявки на отправку
          - получение трек-номера
          - получение товарной накладной
          - статус доставки
          - (уже частично реализован)

        EDOAdapter (НОВЫЙ):
          - отправка УПД
          - отправка счёт-фактуры
          - статус подписания
          - получение подписанных документов

      Core не знает про конкретные SDK.
      Core вызывает порты (ports.py).
      Адаптеры реализуют порты.

    2.5.3 Employee Permission Model

        EmployeeRole:
          - role_id
          - name (operator, manager, admin)
          - allowed_intents (список разрешённых TaskIntent)
          - financial_limit (максимальная сумма без эскалации)
          - escalation_target (кому эскалировать)

      Правила:
        - Если TaskIntent не в allowed_intents → отказ + объяснение
        - Если сумма > financial_limit → эскалация владельцу
        - Все действия логируются с trace_id
        - Все действия idempotent

    2.5.4 Employee Actions Log

      Таблица аудита: employee_actions_log

        Поля:
          - id
          - employee_id
          - intent (TaskIntent)
          - parameters (structured JSON)
          - executed_at
          - result (success / error / escalated)
          - escalation_flag
          - trace_id

      Назначение:
        - Аудит всех действий сотрудника
        - Основа для будущего Operational Learning (Phase 5)
        - Анализ загрузки и паттернов работы
        - RCA при инцидентах


  PHASE 3 — Marketplace AI Factory

    Цель: Автоматизация карточек и масштабирование.

    3.1 Автоклассификация
      AI определяет категорию Ozon/WB
      AI определяет обязательные характеристики
      confidence score
      threshold < 0.9 → human correction
      CorrectionRecord → dataset update

    3.2 Фото-пайплайн
      Поиск реальных фото (SERP API)
      AI-cleanup
      fallback генерация по datasheet
      media hashing
      marketplace-ready форматирование

    3.3 Price Monitoring
      сбор цен
      конкурентный анализ
      enrichment CDM

    3.4 Datasheet DB
      хранение текста
      re-processing при улучшении моделей


  PHASE 4 — UCI (Unified Control Interface)

    Интерфейс — адаптер, не логика.

    Текущий адаптер: Telegram
    Возможная замена: Messenger Max

    Через UCI сотрудник может:
      проверить оплату, создать счёт, получить накладную, проверить доставку

    Core не зависит от интерфейса.


  PHASE 4.5 — AI Executive Assistant

    Цель: ИИ отвечает сотруднику вместо владельца.
    Controlled Delegation — не автономия, а маршрутизация.

    4.5.1 Как это работает

      Максим пишет в Telegram:
        "Проверь, оплатил ли ООО Ромашка счёт 547"

      AI Executive Assistant:
        1. Парсит сообщение → определяет Intent (check_payment)
        2. Извлекает параметры (client: ООО Ромашка, invoice: 547)
        3. Проверяет права Максима (EmployeeRole)
        4. Вызывает Core service (payment_service.check_status)
        5. Формирует человекочитаемый ответ
        6. Возвращает в Telegram

      Максим получает ответ. Владелец не участвует.

    4.5.2 Эскалация

      AI Executive Assistant эскалирует владельцу ТОЛЬКО если:
        - Запрос нестандартный (Intent не распознан, confidence < threshold)
        - Финансовый риск > threshold (сумма, новый клиент)
        - Правило не определено (новый тип задачи)
        - Сотрудник явно просит "позвать босса"

      Метрика эскалации:
        - Цель: < 10% запросов требуют эскалации
        - Если > 20% → нужно добавить новые Intent'ы или правила

    4.5.3 Архитектурные ограничения

      ИИ НЕ принимает бизнес-решения.
      ИИ — это:
        - Intent parser (NLU) — Adapter-layer функция
        - Контекстный ответчик
        - Объясняющий интерфейс
        - Маршрутизатор к Core services

      Архитектурная граница:
        NLU живёт в Adapter Layer.
        Core получает ТОЛЬКО валидированный TaskIntent (structured).
        Core НИКОГДА не обрабатывает свободный текст.
        Если NLU не может уверенно определить intent → Core не вызывается.

      Все действия:
        - через deterministic Core services
        - с trace_id
        - с idempotency
        - с логированием полного диалога

    4.5.4 Что ИИ может

      Отвечать на вопросы:
        - "Оплачен ли счёт X?" → check_payment
        - "Где посылка X?" → check_delivery
        - "Отправь счёт клиенту Y" → send_invoice
        - "Пришли накладную" → get_waybill
        - "Какой статус заказа Z?" → order_status

      Выполнять действия (через Core):
        - Создать и отправить счёт
        - Отправить УПД через ЭДО
        - Запросить документ из СДЭК
        - Повторно отправить документ клиенту

    4.5.5 Что ИИ НЕ может

      - Изменять цены
      - Давать скидки
      - Отменять заказы
      - Возвращать деньги
      - Принимать решения за пределами определённых правил
      → Всё это → эскалация владельцу

    4.5.6 Intent Versioning

      Каждый вызов Intent Parser логирует:
        - model_version (версия NLU модели)
        - prompt_version (версия промпта)
        - confidence (уверенность распознавания)
        - raw_input (исходное сообщение)
        - parsed_intent (распознанный intent)
        - parsed_params (извлечённые параметры)

    4.5.7 Hybrid UI и Graceful Degradation

      Hybrid UI (кнопки + NLU):

        Режим 1 — Full NLU (нормальная работа):
          Сотрудник пишет свободным текстом.
          AI парсит intent, confidence ≥ 0.9 → выполняет.

        Режим 2 — Assisted NLU (низкая уверенность):
          confidence < 0.9 → система предлагает кнопки:
            "Вы имели в виду?"
            [Проверить оплату] [Отправить счёт] [Статус доставки]
          Сотрудник нажимает кнопку → intent определён точно.

        Режим 3 — Button-only (fallback):
          AI API недоступен или NLU полностью сломан.
          UCI переключается на структурированное меню:
            [Оплата] [Документы] [Доставка] [Заказы]
          Сотрудник работает через кнопки.

      Mandatory Button Confirmation (жёсткое правило):

        Независимо от degradation level, кнопочное подтверждение
        ОБЯЗАТЕЛЬНО перед вызовом Core, если:

          1. Intent мутирует состояние (send_invoice, send_upd,
             resend_document) И confidence < 0.9
          2. Сумма операции ≥ financial_limit сотрудника
          3. NLU вернул >1 candidate intent с разницей confidence < 0.1

        В этих случаях система предъявляет кнопки с распознанными
        вариантами. Core вызывается ТОЛЬКО после явного нажатия кнопки.
        Это защита от false positive (выполнение не того intent).

      Graceful Degradation — 3 уровня:

        Level 0 — NOMINAL:
          AI API доступен, NLU работает, confidence высокий.
          → Full NLU mode.

        Level 1 — DEGRADED:
          AI API доступен, но confidence часто < 0.9
          ИЛИ latency > SLA (p95 > 3 сек).
          → Автоматический переход на Assisted NLU.
          → Алерт владельцу: "NLU деградирует".

        Level 2 — FALLBACK:
          AI API недоступен ИЛИ error rate > 10%.
          → Автоматический переход на Button-only mode.
          → Алерт владельцу: "AI Assistant в fallback режиме".
          → Все функции доступны через кнопки.

      SLA:
        - p95 response time < 3 секунд
        - p99 response time < 10 секунд
        - Uptime > 99% (включая fallback mode)
        - Escalation latency < 5 минут
        - Intent recognition accuracy > 95%
        - False positive rate < 2%


5. ЧТО НЕ ВХОДИТ В CORE

  Inventory high-frequency updates (отдельный домен)
  Rich content тяжёлые JSON (при необходимости вынос в storage)
  Dynamic pricing (опционально)
  Arbitrary AI-эксперименты без traceability


═══════════════════════════════════════════════════════
STABILITY GATE
═══════════════════════════════════════════════════════

  Переход к Autonomy Layer (Phase 5+) ЗАПРЕЩЁН до выполнения ВСЕХ условий:

  Обязательные критерии входа:

    Временные и объёмные:
      1. Core эксплуатируется в production минимум 2-4 недели
      2. ≥ 100 полностью закрытых циклов сделки (RFQ → delivery)

    Целостность данных:
      3. 0 случаев silent data corruption за этот период
      4. 0 manual interventions (все изменения только через код).
         Manual intervention включает:
           - прямые DB edits (SQL вне миграций)
           - Backoffice Task Engine действия, выполненные для исправления
             данных (а не для штатной бизнес-операции)
         НЕ считаются manual intervention:
           - штатные бизнес-операции через Task Engine с полным audit trail
           - idempotent replay/correction через cli/replay.py
      5. IC-1..IC-9 все зелёные (автоматическая проверка)
      6. RC-1..RC-7 реализованы и зелёные

    Детерминизм:
      7. Replay тест пройден на production snapshot
      8. 0 replay divergence (replay даёт идентичный результат)
      9. FSM полностью закрыт (нет обходных путей)

    Операционные:
      10. Governance decisions накоплены (≥ 50 решений для статистики)
      11. p95 latency стабилен (нет деградации)
      12. Alerting работает (IC/RC нарушения → алерт)
      13. AI Executive Assistant эскалация < 20%

    Инфраструктурные:
      14. CI pipeline работает (pytest при каждом push)
      15. Branch protection настроена

  Без прохождения Stability Gate любая работа над Phase 5+
  является преждевременной и ЗАПРЕЩЕНА.


═══════════════════════════════════════════════════════
AUTONOMY LAYER (Phase 5–6) — VISION, SUBJECT TO CHANGE
═══════════════════════════════════════════════════════

  ВАЖНО:
  Этот раздел описывает АРХИТЕКТУРНЫЙ ВЕКТОР, а не roadmap.
  Реализация начинается ТОЛЬКО после прохождения Stability Gate.

  ФУНДАМЕНТАЛЬНЫЙ ЗАПРЕТ:
  Ни одно правило в Autonomy Layer не может изменяться автоматически
  без human confirmation. Нарушение этого принципа:
    - ломает replay
    - делает RCA невозможным
    - превращает governance в stochastic system


  PHASE 5 — Operational Learning + Autonomous Decision Engine

    Цель: Система учится на решениях и снижает нагрузку на человека.

    5.1 Decision Pattern Mining
      Агрегация governance decisions по типу, клиенту, сумме
      Таблица decision_patterns
      Периодический анализ: approval rate по категориям
      Если approval rate > 95% за последние N cases →
        система ПРЕДЛАГАЕТ auto-approve rule
      Человек подтверждает → governance_rules таблица
      Система начинает auto-approve

    5.2 Correction Learning (расширение Phase 3)
      AI классифицирует → confidence < 0.9 → human correction
      CorrectionRecord → dataset update → модель улучшается
      Метрика: correction rate снижается со временем
      Threshold auto-adjustment ТОЛЬКО с human confirmation

      ВАЖНО: Переобучение моделей происходит ВНЕ Core-цикла.
      Core работает с зафиксированной версией модели.
      Новая версия активируется только после:
        - обучения в изолированной среде
        - валидации на test set
        - human confirmation на переключение

    5.3 Auto-Approve Engine
      Rules-based (не ML-based) — детерминистический
      Каждое правило имеет:
        - создатель (human), дата создания, условия применения
        - trace_id, количество срабатываний, возможность отключения
        - schema_version (версионирование как код)
      Правило не может создаться/измениться без human approval

      Governance Rules Storage:
        - governance_rules версионируются как код
        - каждое изменение → новая версия (append-only)
        - старые версии не удаляются (аудит)
        - rollback = активация предыдущей версии

      Rollback механизм:
        - Каждое правило имеет watchdog-метрики (маржинальность,
          error rate, rejection rate после auto-approve)
        - Если метрика деградирует ниже порога:
            → правило автоматически деактивируется
            → алерт human
            → требуется ручной анализ
        - Auto-disable — единственное исключение из запрета
          self-modifying behaviour (аналог circuit breaker)

        Compensation Review (обязательно при деактивации правила):
        - При деактивации определяется affected window
          (время активации → время деактивации)
        - Все решения, принятые правилом в affected window,
          маркируются для ручной проверки (review queue)
        - Human определяет: оставить, откатить, или компенсировать
        - До завершения review — правило не может быть
          переактивировано или заменено новой версией

    5.4 Autonomy KPI Dashboard
      Метрика: % решений система приняла сама vs эскалировала
      Цель: 90%+ решений без участия человека
      Tracking: время от события до resolution
      Alert: если autonomy ratio падает → что-то сломалось

    5.5 Защита от Approval Fatigue
      Решение:
        - Batching: предложения группируются (раз в неделю)
        - Приоритизация: только высокоимпактные требуют немедленного confirm
        - Низкоимпактные накапливаются в review queue
        - Метрика: время на approve decision не должно расти

    Prerequisite: Stability Gate PASSED


  PHASE 6 — Proactive Operations

    Цель: Система инициирует действия, а не только реагирует.

    6.1 Предиктивные алерты
      Мониторинг остатков → "через N дней закончится товар X"
      Мониторинг SLA → проактивное уведомление клиента
      Мониторинг цен → "конкурент снизил цену на X"

    6.2 Auto-Reorder (с подтверждением)
      Система предлагает заказ поставщику
      Human confirms → заказ отправляется

    6.3 Client Intelligence
      История заказов клиента
      Паттерны поведения (частота, объёмы, категории)
      Client scoring (кредитоспособность, надёжность)

    6.4 Process Optimization
      Анализ bottleneck'ов: где задержки в pipeline
      Рекомендации по улучшению (human confirms)
      Метрика: среднее время от RFQ до delivery

    Prerequisite: Phase 5 stable + Stability Gate PASSED


═══════════════════════════════════════════════════════
SELF-LEARNING ARCHITECTURE
═══════════════════════════════════════════════════════

  УРОВЕНЬ 1 — Correction Learning (Phase 3)
    Триггер: AI ошибся в классификации
    Механизм: CorrectionRecord → dataset update
    Детерминизм: ДА (версия классификатора фиксирована)
    Переобучение: вне Core-цикла, с human confirmation

  УРОВЕНЬ 2 — Operational Learning (Phase 5)
    Триггер: накопленные governance decisions
    Механизм: pattern mining → rule proposal → human confirm
    Детерминизм: ДА (правила rules-based, human-approved)
    Защита: approval fatigue prevention, auto-disable watchdog

  УРОВЕНЬ 3 — Process Learning (Phase 6)
    Триггер: метрики pipeline (время, bottleneck, patterns)
    Механизм: анализ → рекомендация → human confirm
    Детерминизм: ДА (рекомендации, не автоматические действия)

  КЛЮЧЕВОЕ ОГРАНИЧЕНИЕ:
  На всех уровнях human остаётся в loop.
  Автоматическое изменение поведения без human confirmation ЗАПРЕЩЕНО.
  Единственное исключение: auto-disable watchdog (circuit breaker).


═══════════════════════════════════════════════════════
EXTENSION PROTOCOL
═══════════════════════════════════════════════════════

  Классификация новой идеи:

    Вопрос 1: Трогает ли она CDM v2?
      ДА → CDM Schema Migration Protocol (ниже)
      НЕТ → продолжаем

    Вопрос 2: Трогает ли она Core domain services?
      ДА → Extension к существующей Phase
      НЕТ → продолжаем

    Вопрос 3: Это новая интеграция / внешний сервис?
      ДА → новый Adapter через Ports. Core не трогается.

    Вопрос 4: Это новый AI-паттерн / learning loop?
      ДА → Autonomy Layer (Phase 5+). ТОЛЬКО после Stability Gate.

    Вопрос 5: Это новый бизнес-домен?
      ДА → отдельный домен за пределами Core.

  Версионирование плана:
    - Микро-правки → v1.4.x
    - Новая Phase → v1.5, v1.6...
    - Изменение Core Layer → v2.0 (full review)


  CDM SCHEMA MIGRATION PROTOCOL

    Когда CDM нужно менять:
      Если новая функциональность НЕ помещается в существующие
      сущности и атрибуты.

    Процесс миграции CDM v2 → v3:

      Шаг 1 — Обоснование:
        - Что не помещается в CDM v2
        - Какие сущности/поля нужно добавить/изменить
        - Какие контракты это затронет

      Шаг 2 — Impact Analysis:
        - Какие domain services затронуты
        - Какие адаптеры нужно обновить
        - Какие миграции БД нужны
        - Влияние на replay

      Шаг 3 — Backward Compatibility Plan:
        - CDM v3 ОБЯЗАН читать данные CDM v2
        - Новые поля — optional с default values
        - Старые поля — не удаляются (deprecation, не deletion)
        - schema_version позволяет различать версии

      Шаг 4 — Migration Execution:
        - Миграция БД (additive only, не destructive)
        - Обновление Pydantic models
        - Обновление domain services, адаптеров, тестов
        - Replay test на production snapshot

      Шаг 5 — Validation:
        - IC-1..IC-9 зелёные после миграции
        - Replay divergence = 0
        - Все тесты проходят

      Принципы: additive only, backward compatible, versioned,
      tested, documented, одна миграция за раз.


═══════════════════════════════════════════════════════
INVARIANTS (НОВОЕ в v1.4.3)
═══════════════════════════════════════════════════════

  Формальный список архитектурных инвариантов:

  INV-VC (Versioned Contract):
    Core contract неизменен между миграциями. Изменения только
    через CDM Schema Migration Protocol. Между миграциями
    контракт иммутабелен.

  INV-ERS (External Read Snapshot):
    Любой вызов внешнего API, результат которого влияет на решение
    или ответ пользователю, обязан сохранять raw response payload
    с привязкой к trace_id. Replay использует snapshot, не live API.

  INV-CTB (Core Trust Boundary):
    Core domain services принимают только структурированный,
    валидированный TaskIntent. Свободный текст на границе Core
    запрещён. NLU — Adapter-функция.

  INV-MBC (Mandatory Button Confirmation):
    Мутирующий intent + confidence < 0.9, ИЛИ сумма ≥ financial_limit,
    ИЛИ ambiguity (>1 candidate, delta < 0.1) → обязательное кнопочное
    подтверждение перед вызовом Core.

  INV-MI (Manual Intervention Definition):
    Manual intervention = прямой DB edit ИЛИ Task Engine действие
    для исправления данных. Штатные бизнес-операции с audit trail
    и idempotent replay не являются manual intervention.

  INV-CR (Compensation Review):
    Деактивация auto-approve правила обязывает маркировать все решения
    в affected window для ручной проверки. Правило не переактивируется
    до завершения review.


═══════════════════════════════════════════════════════
STOP RULES
═══════════════════════════════════════════════════════

  STOP RULE v1:
    После Phase 4.5 система может быть заморожена:
      работает стабильно
      сотрудник работает автономно через AI Assistant
      владелец не участвует в рутине
    Дальнейшее развитие — опционально.

  STOP RULE v2:
    После Phase 5 система автономна на 90%+ задач:
      человек вмешивается только в аномалии
      KPI autonomy ratio стабильно > 90%
    Phase 6 — опционально.


═══════════════════════════════════════════════════════
МОЯ ЛИЧНАЯ ЦЕЛЬ
═══════════════════════════════════════════════════════

  Система должна:
    уменьшать моё рабочее время
    не требовать постоянного контроля
    позволять сотруднику работать без моего участия
    масштабироваться без переписывания базы
    с каждым днём работать эффективнее
    отвечать на вопросы сотрудника вместо меня

  Если какое-либо решение:
    увеличивает ручной труд
    усложняет Core
    создаёт хрупкие зависимости
    вносит недетерминизм без human confirmation
    — оно отвергается.

  Конечная цель:
    AI-завод для B2B торговли.
    Подобно Джарвису — система, которая понимает бизнес,
    принимает решения, учится и работает автономно.
    Но с железным принципом: human всегда может вмешаться.


═══════════════════════════════════════════════════════
ПРИОРИТЕТ
═══════════════════════════════════════════════════════

  Архитектурная чистота > скорость запуска
  Детерминизм > магия
  Контракт > хаос
  Стабильность > амбиции
  Human-in-the-loop > полная автономность

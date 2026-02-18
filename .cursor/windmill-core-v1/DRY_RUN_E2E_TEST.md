# E2E DRY-RUN Test Guide

## Цель

Провести end-to-end проверку системы с `DRY_RUN_EXTERNAL_APIS=true` для подтверждения работы Telegram → FSM → Ledger → Side-Effects потока без реальных API вызовов.

## Предварительные требования

1. **PostgreSQL запущен** и доступен
2. **Таблицы созданы**: `job_queue`, `order_ledger`
3. **Переменные окружения**:
   ```bash
   export DRY_RUN_EXTERNAL_APIS=true
   export POSTGRES_HOST=localhost
   export POSTGRES_PORT=5432
   export POSTGRES_DB=biretos_automation
   export POSTGRES_USER=biretos_user
   export POSTGRES_PASSWORD=your_password
   ```

## Шаги выполнения

### 1. Запуск RU Worker

В первом терминале:

```bash
cd windmill-core-v1/ru_worker
python ru_worker.py
```

Должны увидеть:
```
RU Worker started
POSTGRES: localhost:5432/biretos_automation
POLL_INTERVAL: 5s
LLM_ENABLED_DEFAULT: false
Press Ctrl+C to stop
```

### 2. Запуск тестового скрипта

Во втором терминале:

```bash
cd windmill-core-v1
python test_dry_run_e2e.py
```

Скрипт автоматически:
- Создаст тестовый заказ в `order_ledger`
- Вставит `telegram_update` jobs для `/start`, `check:<order_id>`, `ship:<order_id>`
- Наблюдает за обработкой jobs в течение 20 секунд
- Выведет отчет о выполнении

### 3. Наблюдение за логами

В логах RU Worker должны появиться:

**Для `/start`:**
```
Processing job: <job_id> (telegram_update)
Processing job: <job_id> (telegram_command)
{"timestamp": "...", "event": "dry_run_telegram_send", ...}
```

**Для `check:<order_id>`:**
```
Processing job: <job_id> (telegram_update)
Processing job: <job_id> (telegram_command)
{"timestamp": "...", "event": "dry_run_telegram_send", ...}
```

**Для `ship:<order_id>`:**
```
Processing job: <job_id> (telegram_update)
Processing job: <job_id> (cdek_shipment)
{"timestamp": "...", "event": "dry_run_cdek_post", ...}
{"timestamp": "...", "event": "dry_run_telegram_send", ...}
Processing job: <job_id> (order_event)
```

## Ожидаемые результаты

### Сценарий 1: `/start` команда

**Поток:**
1. `telegram_update` job → `execute_telegram_update()` → создает `telegram_command` job
2. `telegram_command` job → `execute_telegram_command()` → `_handle_start_command()`
3. SQL: `SELECT * FROM order_ledger ORDER BY created_at DESC LIMIT 5`
4. Форматирование списка заказов
5. `_send_telegram_message()` → DRY-RUN: логирует, возвращает mock ответ

**Проверка:**
- ✅ `telegram_update` job статус: `completed`
- ✅ `telegram_command` job статус: `completed`
- ✅ В логах: `dry_run_telegram_send` event
- ✅ Нет реальных HTTP запросов к api.telegram.org

### Сценарий 2: `check:<order_id>` команда

**Поток:**
1. `telegram_update` job → `execute_telegram_update()` → создает `telegram_command` job
2. `telegram_command` job → `execute_telegram_command()` → `_handle_check_command()`
3. SQL: `SELECT * FROM order_ledger WHERE order_id = $1 LIMIT 1`
4. Форматирование статуса заказа (только по Ledger, без T-Bank API)
5. `_send_telegram_message()` + `_answer_callback_query()` → DRY-RUN

**Проверка:**
- ✅ `telegram_update` job статус: `completed`
- ✅ `telegram_command` job статус: `completed`
- ✅ В логах: `dry_run_telegram_send` events (2 вызова)
- ✅ Статус формируется только из Ledger данных

### Сценарий 3: `ship:<order_id>` команда

**Поток:**
1. `telegram_update` job → `execute_telegram_update()` → создает `cdek_shipment` job
2. `cdek_shipment` job → `execute_cdek_shipment()`
3. SQL: `SELECT * FROM order_ledger WHERE order_id = $1`
4. Валидация: `state='paid'`, `cdek_uuid IS NULL`, `phone`/`email` присутствуют
5. DRY-RUN: логирует `dry_run_cdek_post`, генерирует mock `cdek_uuid`
6. Создает `order_event` job (FSM event `SHIPMENT_CREATED`)
7. DRY-RUN: логирует `dry_run_insales_put` (InSales update)
8. DRY-RUN: логирует `dry_run_telegram_send` (успешный ответ)
9. `order_event` job → `execute_order_event()` → FSM v2 → UPDATE Ledger

**Проверка:**
- ✅ `telegram_update` job статус: `completed`
- ✅ `cdek_shipment` job статус: `completed`
- ✅ `order_event` job статус: `completed`
- ✅ В логах: `dry_run_cdek_post`, `dry_run_insales_put`, `dry_run_telegram_send`
- ✅ В `order_ledger`: `state` переходит на `shipment_created` (или остается `paid`, если transition не определен)
- ✅ В `order_ledger.metadata`: появляется `cdek_uuid` (mock UUID)

## Возможные логические стопы

1. **Нет заказов в Ledger для `/start`**: Список будет пустым, но команда выполнится успешно
2. **Заказ не в состоянии `paid` для `ship`**: CDEK worker выбросит Exception
3. **Отсутствуют `phone`/`email` в `customer_data`**: CDEK worker создаст dialog context, не создаст накладную
4. **FSM transition не определен**: `order_event` может не изменить state, но job завершится успешно

## Формат отчета

После выполнения теста скрипт выведет:

```
TEST REPORT
============================================================
Test Order ID: <uuid>
DRY_RUN Mode: True

Total Jobs Observed: <count>

Jobs by Type:
  telegram_update:
    Total: 3
    Completed: 3 ✅
    Failed: 0 ❌
  telegram_command:
    Total: 2
    Completed: 2 ✅
    Failed: 0 ❌
  cdek_shipment:
    Total: 1
    Completed: 1 ✅
    Failed: 0 ❌
  order_event:
    Total: 1
    Completed: 1 ✅
    Failed: 0 ❌

Scenario Check:
  ✅ /start: PASSED
  ✅ check: PASSED
  ✅ ship: PASSED
  ✅ fsm_event: PASSED
```

## Ручная проверка БД

После выполнения теста можно проверить состояние вручную:

```sql
-- Проверка jobs
SELECT job_type, status, COUNT(*) 
FROM job_queue 
WHERE created_at > NOW() - INTERVAL '5 minutes'
GROUP BY job_type, status;

-- Проверка order_ledger
SELECT order_id, state, metadata->>'cdek_uuid' as cdek_uuid
FROM order_ledger
WHERE order_id = '<test_order_id>';
```

## Примечания

- Все HTTP вызовы заменены на логирование в DRY-RUN режиме
- FSM transitions продолжают работать
- Валидации и бизнес-логика остаются без изменений
- Mock данные (UUIDs, URLs) генерируются для продолжения потока























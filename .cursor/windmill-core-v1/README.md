# Windmill Execution Core v1

Минимальный execution core для Windmill на RU-VPS согласно утвержденной архитектуре.

## Архитектурные принципы

- **Queue-first**: Все задачи пишутся в PostgreSQL перед выполнением
- **Windmill = executor**: Windmill НЕ принимает HTTP запросы, только опрашивает очередь
- **No public Windmill**: Windmill слушает только loopback (127.0.0.1)
- **Async by default**: Все операции через очередь
- **RU Worker**: RU-side бизнес-логика (rfq_v1_from_ocr) выполняется отдельным executor на RU-VPS
- **Local PC Worker**: Compute-only задачи (heavy_compute_test, ocr_test) выполняются на Local PC

## Структура

```
windmill-core-v1/
├── schema/
│   ├── job_queue.sql          # PostgreSQL схема очереди
│   ├── job_queue_migration.sql # Миграция для существующих таблиц
│   └── rfq_tables.sql         # RFQ таблицы (rfq_requests, rfq_items)
├── webhook_service/
│   ├── main.py                # FastAPI сервис для приема webhooks + polling/callback API
│   └── requirements.txt       # Python зависимости
├── windmill_executor/
│   ├── job_processor.py       # Windmill script для выполнения задач
│   └── requirements.txt       # Python зависимости
├── ru_worker/
│   ├── ru_worker.py           # RU-side executor (test_job, rfq_v1_from_ocr)
│   ├── rfq_parser.py          # Deterministic RFQ parser
│   ├── llm_client.py          # USA LLM Gateway client (placeholder)
│   └── requirements.txt       # Python зависимости
├── local_worker/
│   ├── local_worker.py        # Local PC worker (polling + callback)
│   └── requirements.txt       # Python зависимости
├── .env.example               # Пример переменных окружения
└── README.md                  # Эта инструкция
```

## Установка

### 1. Создать PostgreSQL схему

**Если таблица job_queue еще не существует:**

```bash
# Подключиться к PostgreSQL
psql -U biretos_user -d biretos_automation

# Выполнить схему
\i schema/job_queue.sql
```

Или через Docker:
```bash
docker exec -i biretos-postgres psql -U biretos_user -d biretos_automation < schema/job_queue.sql
```

**Если таблица job_queue уже существует (миграция):**

```bash
docker exec -i biretos-postgres psql -U biretos_user -d biretos_automation < schema/job_queue_migration.sql
```

Миграция добавляет:
- Поле `job_token` (UUID)
- Поле `dispatched_at` (TIMESTAMPTZ)
- Статус `'dispatched'` в CHECK constraint
- Обновляет индексы

### 2. Установить Webhook Service

```bash
cd webhook_service
pip install -r requirements.txt
```

### 3. Настроить переменные окружения

Для Webhook Service:
```bash
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=biretos_automation
export POSTGRES_USER=biretos_user
export POSTGRES_PASSWORD=your_password
```

### 4. Запустить Webhook Service

```bash
cd webhook_service
uvicorn main:app --host 0.0.0.0 --port 8001
```

Webhook Service будет доступен на `http://localhost:8001`

**ВАЖНО**: В production нужно настроить nginx/Caddy для проксирования запросов к этому сервису.

### 5. Настроить Windmill (опционально)

1. Импортировать `windmill_executor/job_processor.py` в Windmill как Python script
2. Настроить переменные окружения в Windmill:
   - `POSTGRES_HOST`
   - `POSTGRES_PORT`
   - `POSTGRES_DB`
   - `POSTGRES_USER`
   - `POSTGRES_PASSWORD`

3. Настроить Windmill для периодического выполнения скрипта (например, каждые 5 секунд через scheduler)

**ВАЖНО**: Windmill должен запускаться локально и иметь доступ к PostgreSQL (loopback или Docker network).

### 6. Настроить RU Worker (RU-side executor)

1. Установить зависимости:
   ```bash
   cd ru_worker
   pip install -r requirements.txt
   ```

2. Настроить переменные окружения:
   ```bash
   export POSTGRES_HOST=localhost
   export POSTGRES_PORT=5432
   export POSTGRES_DB=biretos_automation
   export POSTGRES_USER=biretos_user
   export POSTGRES_PASSWORD=your_password
   export RU_WORKER_POLL_INTERVAL=5
   export LLM_ENABLED_DEFAULT=false
   
   # Опционально: USA LLM Gateway (placeholder)
   export USA_LLM_BASE_URL=https://usa-llm-gateway.example.com
   export USA_LLM_API_KEY=your_api_key
   ```

3. Запустить RU worker:
   ```bash
   cd ru_worker
   python ru_worker.py
   ```

**ВАЖНО**:
- RU Worker опрашивает очередь и выполняет RU-side jobs (test_job, rfq_v1_from_ocr)
- Работает на RU-VPS, имеет доступ к PostgreSQL
- Не является публичным сервисом (polling только)

#### 6.1. Telegram Router + Dispatch (новая логика)

RU Worker теперь напрямую обрабатывает все Telegram-команды через модульную связку:

- `ru_worker/telegram_router.py` — pure-функция update → action
- `ru_worker/dispatch_action.py` — единый side-effect gateway (T-Bank + CDEK)
- `ru_worker/lib_integrations.py` — вызовы внешних API

Ключевые особенности:

1. **Бизнес-идемпотентность**: состояние записывается в таблицу `wm_state` (создаётся автоматически).  
   Ключи вида `business:ship_paid:{invoice_id}` предотвращают повторное создание накладных.
2. **Ответы в Telegram**: RU Worker сам отправляет сообщения пользователю, никаких дополнительных job'ов не требуется.
3. **Callback Query**: подтверждаются сразу, чтобы Telegram не показывал "часики".

Как обновить код на RU VPS:

```bash
cd /opt/biretos/windmill-core-v1   # пример пути
git pull                           # или rsync/scp новых файлов
pkill -f "ru_worker.py"            # остановить текущий процесс
cd ru_worker
python3 ru_worker.py               # запустить заново (screen/tmux рекомендуется)
```

Проверка после релиза:

1. Открыть Telegram → `/invoices`
2. Убедиться, что бот присылает список счетов с кнопками
3. Нажать «📦 Создать накладную» → дождаться ответа и трек-номера

### 7. Настроить Local PC Worker

1. Установить базовые зависимости:
   ```bash
   cd local_worker
   pip install -r requirements.txt
   ```

2. (Опционально) Установить torch для GPU-light heavy compute:
   ```bash
   # С CUDA support (если есть NVIDIA GPU)
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
   
   # Или CPU-only версия
   pip install torch torchvision torchaudio
   ```
   
   **Примечание**: Если torch не установлен, heavy_compute_test задачи вернут ошибку "torch not installed".
   Worker продолжит работать для других типов задач.

3. Настроить переменные окружения:
   ```bash
   set RU_BASE_URL=https://n8n.biretos.ae
   set POLL_INTERVAL=5
   set WORKER_ID=local-pc-worker
   ```

4. Запустить worker:
   ```bash
   python local_worker.py
   ```

**ВАЖНО**: 
- Worker использует только outbound HTTPS (polling + callback)
- Никакого listening server на Local PC
- Worker работает в бесконечном цикле (Ctrl+C для остановки)
- Для heavy_compute_test: worker автоматически определяет GPU/CPU и использует доступный device
- Если CUDA доступна, но произошла ошибка → автоматический fallback на CPU
- Для ocr_test: worker работает в stub/mock режиме если OCR не установлен (pipeline продолжает работать)

## Validation (Тестирование)

### 1. Проверить, что Webhook Service работает

```bash
curl http://localhost:8001/health
```

Ожидаемый ответ:
```json
{"status": "healthy", "service": "webhook-queue"}
```

### 2. Создать тестовую задачу

**Стандартная задача (test_job):**

```bash
curl -X POST http://localhost:8001/webhook/test-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "test_job",
    "payload": {
      "echo": "Hello Windmill!"
    }
  }'
```

**Heavy compute задача (GPU-light torch):**

```bash
curl -X POST https://<RU_DOMAIN>/webhook/test-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "heavy_compute_test",
    "payload": {
      "matrix": 4096,
      "iters": 8
    }
  }'
```

Параметры payload для heavy_compute_test:
- `matrix` (optional, default=4096): размер матрицы (NxN)
- `iters` (optional, default=8): количество итераций матричного умножения

**OCR задача (stub для RFQ pipeline):**

```bash
curl -X POST https://<RU_DOMAIN>/webhook/test-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "ocr_test",
    "payload": {
      "file_path": "sample.pdf",
      "file_type": "pdf",
      "language": "rus"
    }
  }'
```

Параметры payload для ocr_test:
- `file_path` (required): путь к файлу на Local PC (файл должен быть доступен локально)
- `file_type` (required): "pdf" или "image"
- `language` (optional, default="auto"): "eng", "rus", или "auto"

**Примечание**: OCR-stub режим:
- Если pytesseract и tesseract установлены → выполняет реальный OCR
- Если OCR недоступен → возвращает mock результат (pipeline продолжает работать)
- Это stub для будущего RFQ OCR pipeline

**RFQ Pipeline задача (rfq_v1_from_ocr):**

```bash
curl -X POST https://<RU_DOMAIN>/webhook/test-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "rfq_v1_from_ocr",
    "payload": {
      "ocr_job_id": "uuid-of-completed-ocr-job",
      "source": "telegram",
      "llm_enabled": false
    }
  }'
```

Или с прямым текстом (без OCR):
```bash
curl -X POST https://<RU_DOMAIN>/webhook/test-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "rfq_v1_from_ocr",
    "payload": {
      "text": "Нужны детали: ABC123 (2 шт), DEF456 (5 шт). Email: test@example.com",
      "source": "manual",
      "llm_enabled": false
    }
  }'
```

Параметры payload для rfq_v1_from_ocr:
- `ocr_job_id` (optional): UUID завершенной OCR задачи (берётся sample_text из result)
- `text` (optional): Прямой текст для парсинга (если нет ocr_job_id)
- `source` (required): "telegram" | "email" | "manual"
- `llm_enabled` (optional, default=false): использовать ли LLM для парсинга

**Примечание**: RFQ Pipeline v1:
- Deterministic parser извлекает: part numbers, emails, phones, ИНН
- LLM parsing опционален (через feature flag llm_enabled)
- Результаты сохраняются в rfq_requests и rfq_items
- Исполняется на RU-VPS (ru_worker), не на Local PC

Ожидаемый ответ:
```json
{
  "job_id": "uuid-here",
  "status": "created",
  "idempotency_key": "hash-here"
}
```

### 3. Проверить, что задача появилась в БД

```bash
docker exec -i biretos-postgres psql -U biretos_user -d biretos_automation -c "SELECT id, job_type, status, created_at FROM job_queue ORDER BY created_at DESC LIMIT 5;"
```

Ожидаемый результат:
```
id                                  | job_type | status    | created_at
------------------------------------+----------+-----------+----------------------------
uuid-here                           | test     | pending   | 2025-01-XX XX:XX:XX
```

### 4. Тестирование Local PC Worker (polling + callback)

#### 4.1. Запустить Local PC Worker

На Local PC (Windows):
```bash
cd local_worker
pip install -r requirements.txt

# Настроить переменные окружения
set RU_BASE_URL=https://n8n.biretos.ae
set POLL_INTERVAL=5
set WORKER_ID=local-pc-worker

python local_worker.py
```

#### 4.2. Создать задачу для Local PC

На RU-VPS или локально:

**Стандартная задача:**
```bash
curl -X POST http://localhost:8001/webhook/test-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "test_job",
    "payload": {
      "message": "Test from Local PC worker"
    }
  }'
```

**Heavy compute задача (GPU-light):**
```bash
curl -X POST http://localhost:8001/webhook/test-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "heavy_compute_test",
    "payload": {
      "matrix": 4096,
      "iters": 8
    }
  }'
```

Worker автоматически:
- Определит доступный device (CUDA если есть, иначе CPU)
- Выполнит torch workload
- Вернет метрики: device, elapsed_ms, checksum, torch_version
- При ошибке CUDA выполнит fallback на CPU

**OCR задача (stub):**
```bash
curl -X POST http://localhost:8001/webhook/test-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "ocr_test",
    "payload": {
      "file_path": "sample.pdf",
      "file_type": "pdf",
      "language": "rus"
    }
  }'
```

Worker автоматически:
- Проверит доступность pytesseract и tesseract binary
- Если OCR доступен → выполнит реальное распознавание
- Если OCR недоступен → вернет mock результат (pipeline продолжит работу)
- Вернет метрики: ocr_engine, text_length, sample_text, elapsed_ms
- Это stub для будущего RFQ OCR pipeline (реальный OCR будет добавлен позже)

#### 4.3. Проверить, что задача перешла в dispatched

```bash
docker exec -i biretos-postgres psql -U biretos_user -d biretos_automation -c "SELECT id, job_type, status, dispatched_at, job_token FROM job_queue WHERE status='dispatched' ORDER BY dispatched_at DESC LIMIT 5;"
```

Ожидаемый результат:
```
id                                  | job_type           | status     | dispatched_at           | job_token
------------------------------------+--------------------+------------+-------------------------+----------
uuid-here                           | local_worker_test  | dispatched | 2025-01-XX XX:XX:XX     | uuid-token
```

#### 4.4. Проверить, что Local PC выполнил задачу

После выполнения (через 2-5 секунд), проверить статус:
```bash
docker exec -i biretos-postgres psql -U biretos_user -d biretos_automation -c "SELECT id, job_type, status, updated_at, error FROM job_queue ORDER BY updated_at DESC LIMIT 5;"
```

Ожидаемый результат:
```
id                                  | job_type           | status     | updated_at              | error
------------------------------------+--------------------+------------+-------------------------+------
uuid-here                           | local_worker_test  | completed  | 2025-01-XX XX:XX:XX     | NULL
```

### 5. Тестирование Windmill executor (опционально)

Если Windmill настроен для периодического выполнения `job_processor.py`, задача должна быть обработана автоматически.

Для ручного тестирования (локально):
```bash
cd windmill_executor
python job_processor.py
```

### 6. Smoke Test: RFQ Pipeline v1

Полный smoke test для проверки RFQ pipeline:

#### 6.1. Запустить RU Worker

На RU-VPS:
```bash
cd ru_worker
python ru_worker.py
```

#### 6.2. Создать OCR задачу

```bash
curl -X POST http://localhost:8001/webhook/test-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "ocr_test",
    "payload": {
      "file_path": "sample.pdf",
      "file_type": "pdf",
      "language": "rus"
    }
  }'
```

Сохранить `job_id` из ответа (например: `ocr-job-uuid`)

#### 6.3. Дождаться завершения OCR

Проверить статус OCR задачи:
```bash
docker exec -i biretos-postgres psql -U biretos_user -d biretos_automation -c "SELECT id, job_type, status, result IS NOT NULL as has_result FROM job_queue WHERE id='ocr-job-uuid';"
```

Дождаться `status='completed'` и `has_result=true`

#### 6.4. Создать RFQ задачу с ocr_job_id

```bash
curl -X POST http://localhost:8001/webhook/test-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "rfq_v1_from_ocr",
    "payload": {
      "ocr_job_id": "ocr-job-uuid",
      "source": "telegram",
      "llm_enabled": false
    }
  }'
```

Сохранить `job_id` из ответа (например: `rfq-job-uuid`)

#### 6.5. Дождаться завершения RFQ

Проверить статус RFQ задачи:
```bash
docker exec -i biretos-postgres psql -U biretos_user -d biretos_automation -c "SELECT id, job_type, status, result IS NOT NULL as has_result FROM job_queue WHERE id='rfq-job-uuid';"
```

Дождаться `status='completed'`

#### 6.6. Проверить записи в rfq_requests

```bash
docker exec -i biretos-postgres psql -U biretos_user -d biretos_automation -c "SELECT id, source, status, created_at FROM rfq_requests ORDER BY created_at DESC LIMIT 5;"
```

Должна появиться новая запись со статусом `processed`

#### 6.7. Проверить записи в rfq_items

```bash
docker exec -i biretos-postgres psql -U biretos_user -d biretos_automation -c "SELECT rfq_id, line_no, part_number, qty FROM rfq_items ORDER BY rfq_id DESC, line_no LIMIT 10;"
```

Должны появиться записи с part_number из распознанного текста

#### 6.8. Проверить результат RFQ job

```bash
docker exec -i biretos-postgres psql -U biretos_user -d biretos_automation -c "SELECT result::text FROM job_queue WHERE id='rfq-job-uuid';"
```

Должен вернуться JSON с:
- `rfq_id`
- `items_count`
- `sample_parts`
- `emails`, `phones`
- `llm_used: false`

### 7. Проверить идемпотентность

Отправить тот же запрос еще раз:
```bash
curl -X POST http://localhost:8001/webhook/test-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "test_job",
    "payload": {
      "echo": "Hello Windmill!"
    }
  }'
```

Ожидаемый ответ (статус 200, не 201):
```json
{
  "job_id": "same-uuid-as-before",
  "status": "already_exists",
  "existing_status": "completed",
  "idempotency_key": "same-hash-as-before"
}
```

## Архитектура потоков данных

### Windmill Executor (локальное выполнение на RU-VPS)

```
External Request → Webhook Service → PostgreSQL job_queue → Windmill Executor
                                                                    ↓
                                                              Process Job
                                                                    ↓
                                                              Update Status
```

### Local PC Worker (async через polling)

```
External Request → Webhook Service → PostgreSQL job_queue (status='pending')
                                                      ↓
                                            Local PC Worker (polling)
                                                      ↓
                                            GET /api/jobs/poll
                                                      ↓
                                            UPDATE status='dispatched' + job_token
                                                      ↓
                                            Local PC: Execute Task
                                                      ↓
                                            POST /api/jobs/{id}/callback
                                                      ↓
                                            UPDATE status='completed'/'failed'
```

1. **Webhook Service** (публичный endpoint) принимает запросы
2. **PostgreSQL job_queue** хранит задачи со статусом `pending`
3. **Windmill Executor** (опционально) опрашивает очередь локально на RU-VPS
4. **Local PC Worker** опрашивает через HTTPS polling, получает задачи, выполняет и отправляет callback
5. Статус обновляется на `completed` или `failed`

## T-Bank Webhook Handler (INVOICE_PAID)

### Endpoint

```bash
POST /webhook/tbank-invoice-paid
Content-Type: application/json
```

### Пример запроса (минимальный payload)

```bash
curl -X POST http://localhost:8001/webhook/tbank-invoice-paid \
  -H "Content-Type: application/json" \
  -d '{
    "eventType": "INVOICE_PAID",
    "invoiceId": "TBANK-123456",
    "invoiceNumber": "INV-001",
    "paidAt": "2025-01-15T12:00:00Z"
  }'
```

### Пример ответа

```json
{
  "ok": true,
  "message": "Payment recorded"
}
```

**HTTP Status**: Всегда `200 OK` (даже при дублях идемпотентности)

### Поддерживаемые поля

- **Обязательные**:
  - `eventType` или `event_type`: должен быть `"INVOICE_PAID"`
  - `invoiceId` или `invoice_id`: непустая строка

- **Опциональные**:
  - `invoiceNumber` или `invoice_number`: строка или null
  - `paidAt` или `paid_at`: ISO8601 timestamp (по умолчанию текущее время)

### Идемпотентность

- Webhook-level: через `job_queue.idempotency_key = "tbank:invoice_paid:{invoice_id}"`
- Ledger-level: если `order_ledger.state == "paid"`, переход пропускается

### Обработка ошибок

- Все ошибки логируются в stdout (структурированный JSON)
- Ошибки записи в `order_ledger.error_log` (если order найден)
- Webhook всегда возвращает `200 OK` (кроме критических ошибок БД)

## Ограничения v1

- Нет retry механизма (только базовые статусы)
- Нет приоритетов задач
- Нет планировщика задач
- Нет метрик и мониторинга
- Windmill executor должен быть настроен для периодического выполнения вручную
- RFQ Pipeline: deterministic parser - простые regex, не сложная нормализация
- RFQ Pipeline: LLM integration - placeholder, требует реальный USA LLM Gateway endpoint
- RFQ Pipeline: нет валидации part numbers, нет связи с каталогами
- Local PC worker использует простой polling без backoff
- Heavy compute: torch опциональная зависимость (нужно устанавливать вручную)
- Heavy compute: размер матрицы ограничен доступной памятью GPU/RAM

## Следующие шаги (v2+)

- Добавить retry механизм через `retry_at` поле
- Добавить интеграцию с USA-VPS для LLM запросов
- Добавить интеграцию с Local PC для тяжелых вычислений
- Добавить мониторинг и метрики
- Добавить планировщик задач (cron-like)


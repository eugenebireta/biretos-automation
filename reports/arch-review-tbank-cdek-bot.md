# Архитектурный разбор: T-Bank + CDEK через @biretarus_bot

**trace_id:** orch_20260412T104120Z_0a40e6  
**date:** 2026-04-12  
**risk_class:** LOW (read-only analysis, no code changes)

---

## 1. Описание системы

Система обеспечивает оперативный просмотр финансовых и логистических данных через Telegram и автоматическое создание заказов в InSales при оплате счёта в Т-Банке.

### Компоненты

| Компонент | Файл | Роль |
|-----------|------|------|
| @biretarus_bot | `orchestrator/biretarus_bot.py` | Telegram-бот для просмотра счетов и накладных |
| VPS прокси | `biretos_proxy.py` на `216.9.227.124:9966` | Кэш-прокси между ботом и источниками данных |
| n8n webhook | `n8n-workflows/tbank-invoice-paid-webhook.json` | Обработка событий "счёт оплачен" |
| n8n Telegram flow | `n8n-workflows/tbank-orders-telegram.json` | Ручное создание заказов через Telegram |
| TBankInvoiceAdapter | `.cursor/windmill-core-v1/side_effects/adapters/tbank_adapter.py` | Domain-адаптер Windmill Core |
| CDEKShipmentAdapter | `.cursor/windmill-core-v1/side_effects/adapters/cdek_adapter.py` | Domain-адаптер Windmill Core + waybill download |

### Потоки данных

```
[Telegram /start] → biretarus_bot.py → GET http://216.9.227.124:9966/invoices → biretos_proxy.py → (cached JSON или live T-Bank API)
[Telegram /start] → biretarus_bot.py → GET http://216.9.227.124:9966/shipments → biretos_proxy.py → (cached JSON, populated by n8n)

[T-Bank event: invoice_paid] → n8n webhook → validate → PostgreSQL dedup → InSales order → Telegram notify

[Telegram /orders] → n8n Telegram flow → T-Bank API live pull → interactive select → CDEK PVZ lookup → InSales order
```

---

## 2. ARCHITECT: Оценка корректности по слоям

### 2.1 JSON-on-VPS persistence (`biretos_proxy.py`)

**Корректность:** частичная.

Прокси на `216.9.227.124:9966` выполняет роль буфера между Telegram-ботом (работающим локально или на другом хосте) и данными T-Bank/CDEK. Схема позволяет не хранить API-токены в боте и изолировать внешние вызовы на VPS.

**Проблемы:**
- Транспорт — HTTP (не HTTPS). Данные счетов (суммы, ИНН, статусы) передаются в открытом виде между ботом и прокси.
- Нет аутентификации на эндпоинтах `/invoices` и `/shipments`. Любой, знающий IP:порт, может читать данные.
- TBANK_TOKEN хранится в `/root/biretos_tbank_token.txt` — plaintext на диске VPS без ротации.
- JSON-файлы на диске: нет атомарности записи. Параллельная запись из n8n и read-запрос от бота могут вернуть частично записанный файл.
- Нет механизма TTL или инвалидации кэша — данные могут быть устаревшими без индикации.

**Вывод:** архитектурно допустима для MVP при условии, что VPS закрыт firewall и данные не содержат финансово-критичной информации. Для production требует TLS + auth.

---

### 2.2 Manual CSV import (CDEK накладные)

**Корректность:** неверифицируема.

В `biretarus_bot.py:144–145` явно указано, что CDEK-данные появляются «автоматически после следующей отправки через n8n-вебхук InSales → CDEK». Однако в task description упоминается «ручной CSV-импорт». Код автоматизации для этого пути в репозитории не обнаружен.

**Проблемы:**
- Отсутствие кода означает либо полностью ручной процесс (копирование CSV → JSON на VPS вручную), либо внешний инструмент вне репозитория.
- Ручной процесс: нет аудит-трейла, нет идемпотентности, высокий риск ошибок при конвертации форматов.
- Нет валидации структуры CSV перед загрузкой в proxy-хранилище.

**Вывод:** путь не автоматизирован. Если он активно используется, необходима его формализация.

---

### 2.3 n8n webhook ingestion (`tbank-invoice-paid-webhook.json`)

**Корректность:** хорошая по бизнес-логике, слабая по безопасности.

**Сильные стороны:**
- Идемпотентность через PostgreSQL (`tbank_invoice_id` unique check, `INSERT ON CONFLICT`-equivalent через SELECT + IF).
- Валидация полей payload (event_type, source, invoice_id, status).
- Немедленный 200 OK на webhook + асинхронная обработка.
- Telegram-уведомление на успех.
- Геокодирование + поиск ближайшего ПВЗ CDEK (Haversine).

**Проблемы:**

| # | Проблема | Severity |
|---|----------|----------|
| W1 | Нет HMAC-верификации входящего webhook. Любой может отправить поддельный `invoice_paid` с нужным `invoice_id`. | HIGH |
| W2 | `active: false` — workflow не активирован в n8n. | MEDIUM |
| W3 | При ошибке InSales API (5xx/timeout) mapping сохраняется со статусом "failed", но повторная попытка не предусмотрена. | MEDIUM |
| W4 | `metadata` в `invoice_orders` содержит полный JSON payload включая ПИИ (name, inn, phone, address). Нет маскирования. | MEDIUM |
| W5 | Geocode fallback: если Nominatim вернул пустой ответ, берётся первый PVZ из города — без уведомления оператора. | LOW |
| W6 | `Get CDEK PVZ` вызывается без OAuth-токена (публичный эндпоинт `/v2/deliverypoints`). Корректно для read-only, но может измениться в API v3. | LOW |

---

### 2.4 Live API pull (`biretarus_bot.py` → VPS proxy → T-Bank)

**Корректность:** функциональная, но без устойчивости к сбоям.

**Сильные стороны:**
- Использует `httpx.AsyncClient` — неблокирующий I/O.
- Timeout 20s — разумный.
- Graceful error messages пользователю при сбоях (401, network errors).
- CDEK: статусы локализованы через `_CDEK_STATUSES` dict.

**Проблемы:**

| # | Проблема | Severity |
|---|----------|----------|
| L1 | Нет retry при transient errors. Одна сетевая ошибка = "Ошибка подключения к прокси". | MEDIUM |
| L2 | `httpx.AsyncClient` создаётся заново на каждый запрос — нет connection reuse. | LOW |
| L3 | VPS `216.9.227.124` — единственная точка отказа. Нет fallback. | MEDIUM |
| L4 | Бот работает с `r.json()` без проверки Content-Type — может упасть на HTML error pages. | LOW |
| L5 | `_load_project_env()` читает `.env` на каждый запрос токена — нет кэширования. | LOW |

---

### 2.5 Domain adapters (Windmill Core)

**Корректность:** хорошая. Адаптеры реализуют паттерн Port/Adapter корректно.

**TBankInvoiceAdapter:**
- dry_run поддержка — корректно.
- `X-Request-Id` для idempotency — корректно.
- `InvoiceStatusRequest` принимает `trace_id` — корректно (соответствует CLAUDE.md).

**CDEKShipmentAdapter:**
- OAuth2 `client_credentials` с кэшированием токена — корректно.
- 3-step waybill flow (resolve UUID → create print task → poll → download PDF) — корректно.
- Polling с `time.sleep(3)` × 10 = 30s max — блокирующий вызов в sync context. Для Windmill worker допустимо, но стоит отметить.
- `_cached_token` как class variable — при multi-process deployment возможна ситуация, когда разные processes имеют разные кэши (одна принудительно обновит, другая продолжит с протухшим). Не критично при 1-process setup.

---

## 3. CRITIC: Проверка оценки ARCHITECT

### 3.1 Подтверждённые находки

- **W1 (нет HMAC)** — критично. Нет смягчающих обстоятельств: webhook URL в n8n публичен и не имеет сетевой изоляции.
- **HTTP без TLS на прокси** — подтверждено. Даже если VPS firewall ограничивает доступ, внутри VPS traffic может быть перехвачен.
- **L3 (Single VPS SPOF)** — подтверждено, но для текущего объёма бизнеса это допустимый компромисс.

### 3.2 Уточнения / смягчения

- **W2 (`active: false`)**: это может быть намеренно — workflow в dev/staging состоянии. Не является ошибкой архитектуры, но требует контроля что production-версия активна.
- **L4 (Content-Type)**: частично защищено тем, что `httpx` вызывает `r.json()` только после успешного `r.status_code == 200`. Нестандартные ответы обрабатываются в блоке `except Exception`.
- **CDEK class-level token**: при текущем single-worker deployment на VPS — не проблема. Риск возникает только при масштабировании.
- **Manual CSV import**: отсутствие кода в репозитории не доказывает отсутствие инструмента — может быть реализован вне git (например, ручные команды на VPS). Следует уточнить у владельца.

### 3.3 Пропущенные ARCHITECT-ом риски

- **Два бота, одна роль**: `biretarus_bot.py` (просмотр данных) и n8n Telegram workflow (создание заказов) параллельно обрабатывают Telegram-команды с разными токенами. Нет явного разграничения: `/orders` в n8n и "Последние 5 поступлений" в `biretarus_bot.py` решают схожую задачу по-разному. Риск дублирования/рассинхронизации логики.
- **PostgreSQL как зависимость n8n**: если БД недоступна, idempotency check упадёт, и n8n webhook либо пропустит событие, либо создаст дубль заказа в зависимости от обработки ошибок в workflow. В коде нет явного fallback при DB outage.
- **ПИИ в invoice_orders.metadata**: поле хранит весь payload включая `payer_name`, `payer_inn`, `recipient_phone`, `recipient_email`, `recipient_address`. Для GDPR/152-ФЗ — требует политики хранения и удаления.
- **Прямая зависимость от Nominatim (OpenStreetMap)**: внешний бесплатный сервис без SLA, с rate limiting. Высоконагруженное использование или временный бан IP могут сломать PVZ-lookup для всех PVZ-заказов.

---

## 4. Итоговая оценка рисков

| ID | Слой | Риск | Severity | Рекомендация |
|----|------|------|----------|-------------|
| R1 | Webhook | Нет HMAC-верификации → поддельные события оплаты | **HIGH** | Добавить `X-Webhook-Signature` + HMAC-SHA256 проверку на входе |
| R2 | Прокси | HTTP без TLS на порту 9966 | **HIGH** | Перенести за nginx с TLS, или добавить mTLS между ботом и прокси |
| R3 | Прокси | Нет auth на `/invoices` и `/shipments` | **HIGH** | IP whitelist или Bearer token на прокси |
| R4 | Прокси | TBANK_TOKEN в plaintext файле | **MEDIUM** | Перенести в secrets manager или env-only переменные systemd |
| R5 | Webhook | Нет retry при InSales API failure | **MEDIUM** | Добавить dead-letter queue или n8n retry policy |
| R6 | Webhook | ПИИ в JSONB metadata без политики удаления | **MEDIUM** | Хранить только id/amount, вынести ПИИ в отдельную таблицу |
| R7 | Dual-bot | Перекрывающаяся логика двух ботов | **MEDIUM** | Документировать разделение зон ответственности |
| R8 | Webhook | PostgreSQL SPOF для idempotency | **MEDIUM** | Мониторинг + алерт при DB outage |
| R9 | JSON store | Нет атомарности записи JSON файлов | **LOW** | Атомарная запись через temp file + rename |
| R10 | Bot | Нет retry на transient errors в biretarus_bot | **LOW** | Exponential backoff, 2 попытки |
| R11 | CSV | Manual CSV import не автоматизирован | **LOW** | Либо автоматизировать, либо задокументировать процедуру |
| R12 | Webhook | Nominatim — внешний SPOF для PVZ lookup | **LOW** | Fallback: если geocode не вернул координаты, взять первый PVZ и уведомить оператора |

---

## 5. Приоритизированные рекомендации

### Приоритет 1 (безопасность, HIGH)

1. **HMAC на webhook** — добавить shared secret между T-Bank gateway и n8n, верифицировать подпись до обработки payload.
2. **TLS на прокси** — либо nginx reverse proxy с Let's Encrypt, либо Cloudflare Tunnel. Порт 9966 закрыть firewall, доступ только через 443.
3. **Auth на прокси** — добавить Bearer token в `biretos_proxy.py`, передавать его из `biretarus_bot.py` через env var.

### Приоритет 2 (надёжность, MEDIUM)

4. **Retry в n8n на InSales failure** — включить n8n retry policy (3 попытки, exponential backoff) на ноде `Create InSales Order`.
5. **ПИИ в metadata** — ограничить JSONB до non-sensitive полей; ввести политику удаления через 90 дней.
6. **Документировать разделение ботов** — зафиксировать в README: `biretarus_bot.py` = read-only owner dashboard, n8n Telegram flow = operator order creation tool.

### Приоритет 3 (технический долг, LOW)

7. **Атомарная запись JSON** — `write to .tmp → os.replace()`.
8. **Retry в biretarus_bot** — 1 повтор через 5 секунд при network error.
9. **Автоматизировать CDEK CSV import** — скрипт, вызываемый по расписанию, или переход на прямой CDEK API pull вместо JSON-на-диске.

---

## 6. Архитектурная корректность: вывод

| Слой | Корректность | Статус |
|------|-------------|--------|
| VPS JSON persistence | Функционально рабочая, но небезопасна | ⚠️ NEEDS FIX |
| Manual CSV import | Не верифицируема (код отсутствует) | ❓ UNCLEAR |
| n8n webhook ingestion | Логически корректна, уязвима к webhook spoofing | ⚠️ NEEDS FIX |
| Live API pull (biretarus_bot) | Корректна, без устойчивости к сбоям | ⚠️ MINOR ISSUES |
| Domain adapters (Windmill Core) | Корректна, соответствует стандартам проекта | ✅ OK |

**Общая оценка системы:** архитектура жизнеспособна и решает задачу. Основной gap — безопасность транспортного слоя (R1, R2, R3). Остальные риски — операционные и некритичны при текущем объёме.

---

## 7. AUDITOR вердикт

**can_ship:** YES (отчёт завершён, scope соблюдён, код не изменён)

Scope: только `reports/arch-review-tbank-cdek-bot.md`  
Tier-1 файлы: не тронуты  
Тесты: не применимо (read-only анализ)

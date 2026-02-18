# Найденные креденшалы в проекте

**Дата поиска:** 2026-01-06

## ✅ Найденные креденшалы

### 1. Telegram Bot Token
**Статус:** ✅ НАЙДЕН

**Значение:**
```
<REDACTED>
```

**Где найден:**
- `check_updates.py` (строка 4)
- `windmill-core-v1/TOKEN_INSTALLED_RESULT.txt` (строка 4)
- `windmill-core-v1/COPY_PASTE_RU_VPS.sh` (строка 12)
- `windmill-core-v1/check_telegram_webhook.py` (строка 8)
- `windmill-core-v1/FINAL_INSTRUCTIONS.txt` (строки 23, 37, 53)
- `windmill-core-v1/setup_webhook_ru_vps.sh` (строка 8)
- И другие файлы

**Текущий статус на сервере:**
- Установлен в `/opt/biretos/windmill-core-v1/.env`
- ⚠️ **ПРОБЛЕМА:** Токен дает ошибку `401 Unauthorized` при проверке через Telegram API
- **Действие:** Требуется получить актуальный токен от @BotFather

---

### 2. T-Bank API конфигурация
**Статус:** ⚠️ URL найден, токен НЕ найден

**Найденные значения:**

#### API URL:
```
https://business.tbank.ru/openapi/api/v1/invoice/send
```

**Где найден:**
- `update_invoice_workflow.py` (строка 459)
- `windmill-core-v1/env.example` (строка 27)
- `windmill-core-v1/side_effects/invoice_worker.py` (строка 25)

#### Альтернативный базовый URL (из документации):
```
https://api.tbank.ru
```

**Где найден:**
- `PRODUCTION_SETUP.md` (строка 34)
- `telegram_bot_mvp0.py` (строка 162) - дефолтное значение

#### Пути API (из PRODUCTION_SETUP.md):
```
TBANK_INVOICE_STATUS_PATH=/v1/invoices/{invoice_id}/status
TBANK_INVOICES_LIST_PATH=/v1/invoices
```

**Токен/credentials:**
- ❌ **НЕ НАЙДЕН** в файлах проекта
- Хранится в n8n credentials как `tbank-openapi-credential` (не экспортируется в JSON)
- Упоминается в `update_invoice_workflow.py` (строка 481): `"id": "tbank-openapi-credential"`

**Текущий статус на сервере:**
- `TBANK_API_BASE=` (пусто)
- `TBANK_INVOICE_STATUS_PATH=` (пусто)
- `TBANK_INVOICES_LIST_PATH=` (пусто)

**Действие:** 
1. Получить токен T-Bank API из n8n credentials или у администратора
2. Заполнить переменные в `.env`:
   ```
   TBANK_API_BASE=https://business.tbank.ru/openapi/api/v1
   TBANK_INVOICE_STATUS_PATH=/invoice/{invoice_id}/status
   TBANK_INVOICES_LIST_PATH=/invoice/list
   ```
   Или использовать базовый URL:
   ```
   TBANK_API_BASE=https://api.tbank.ru
   TBANK_INVOICE_STATUS_PATH=/v1/invoices/{invoice_id}/status
   TBANK_INVOICES_LIST_PATH=/v1/invoices
   ```

---

### 3. CDEK API конфигурация
**Статус:** ⚠️ URL найден, credentials НЕ найдены

**Найденные значения:**

#### API URL:
```
https://api.cdek.ru/v2/orders
```

**Где найден:**
- `n8n-workflows/exports/20251227/CDEK_Shipment_Action__SHIPMENT.json` (строка 164)
- `windmill-core-v1/env.example` (строка 23)
- `windmill-core-v1/side_effects/cdek_shipment_worker.py` (строка 23)

#### Базовый URL (из документации):
```
https://api.cdek.ru
```

**Где найден:**
- `PRODUCTION_SETUP.md` (строка 47)

#### Пути API (из PRODUCTION_SETUP.md):
```
CDEK_OAUTH_PATH=/v2/oauth/token
CDEK_ORDERS_PATH=/v2/orders
```

**Credentials:**
- ❌ **НЕ НАЙДЕНЫ** в файлах проекта
- Хранятся в n8n credentials как `sdek-api-credential` (не экспортируется в JSON)
- Упоминается в `CDEK_Shipment_Action__SHIPMENT.json` (строка 186): `"id": "sdek-api-credential"`

**Текущий статус на сервере:**
- `CDEK_API_BASE=` (пусто)
- `CDEK_CLIENT_ID=` (пусто)
- `CDEK_CLIENT_SECRET=` (пусто)
- `CDEK_FROM_LOCATION_CODE=270` (установлено)
- `CDEK_OAUTH_PATH=/oauth/token` (установлено)
- `CDEK_ORDERS_PATH=/orders` (установлено)

**Действие:**
1. Получить `CDEK_CLIENT_ID` и `CDEK_CLIENT_SECRET` из n8n credentials или у администратора
2. Заполнить переменные в `.env`:
   ```
   CDEK_API_BASE=https://api.cdek.ru
   CDEK_CLIENT_ID=<получить из n8n>
   CDEK_CLIENT_SECRET=<получить из n8n>
   CDEK_OAUTH_PATH=/v2/oauth/token
   CDEK_ORDERS_PATH=/v2/orders
   ```

---

## 📋 Сводка

| Креденшал | Статус | Где хранится | Действие |
|-----------|--------|--------------|----------|
| **TELEGRAM_BOT_TOKEN** | ✅ Найден, но невалидный | Файлы проекта | Получить новый от @BotFather |
| **TBANK_API_BASE** | ✅ Найден | Файлы проекта | Использовать найденный URL |
| **TBANK_API_TOKEN** | ❌ Не найден | n8n credentials | Получить из n8n или у админа |
| **CDEK_API_BASE** | ✅ Найден | Файлы проекта | Использовать найденный URL |
| **CDEK_CLIENT_ID** | ❌ Не найден | n8n credentials | Получить из n8n или у админа |
| **CDEK_CLIENT_SECRET** | ❌ Не найден | n8n credentials | Получить из n8n или у админа |

---

## 🔍 Где искать недостающие креденшалы

### 1. n8n Credentials (на сервере)
```bash
# Подключиться к n8n базе данных
psql -U n8n_user -d n8n

# Или через n8n UI:
# Settings → Credentials → найти:
# - "TBank OpenAPI" (tbank-openapi-credential)
# - "SDEK API" (sdek-api-credential)
```

### 2. Проверить на сервере n8n
```bash
ssh root@216.9.227.124
# Проверить n8n credentials через UI или БД
```

### 3. Проверить другие конфигурационные файлы
- `.env` файлы в других проектах
- `secrets.json` (если есть)
- Переменные окружения на сервере

---

## ✅ Рекомендуемые действия

1. **Telegram Bot Token:**
   - Получить новый токен от @BotFather
   - Обновить в `.env` на сервере
   - Перезапустить сервисы

2. **T-Bank API:**
   - Получить токен из n8n credentials
   - Заполнить `TBANK_API_BASE` и пути в `.env`
   - Добавить токен в заголовки запросов (если требуется)

3. **CDEK API:**
   - Получить `CLIENT_ID` и `CLIENT_SECRET` из n8n credentials
   - Заполнить в `.env`
   - Проверить, что OAuth работает

---

## 📝 Примечания

- Креденшалы для T-Bank и CDEK хранятся в n8n и не экспортируются в JSON файлы workflow по соображениям безопасности
- Текущий Telegram токен может быть устаревшим или отозванным
- Все найденные URL являются публичными и не содержат секретной информации







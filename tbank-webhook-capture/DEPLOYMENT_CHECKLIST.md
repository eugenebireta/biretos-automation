# Ручное развёртывание T-Bank Webhook Receiver v0.1

## Зоны ответственности

### ✅ Cursor (выполнено)

- Создан файл `webhook.php` в директории `tbank-webhook-capture/`
- Файл содержит все правки v0.1 (method guard, fail-safe логирование, headers fallback)
- Создана документация

### 👤 Пользователь (ручные действия)

**Все дальнейшие шаги выполняются ВРУЧНУЮ на RU-VPS**

---

## Шаг 1: Определение структуры Shopware

### Задача: Найти public каталог Shopware

Shopware обычно устанавливается в одном из стандартных мест:

**Вариант A**: Стандартная установка Shopware 6
```
/var/www/shopware/
├── bin/
├── config/
├── public/          ← ЭТОТ каталог нужен
│   ├── index.php
│   ├── media/
│   └── theme/
└── var/
```

**Вариант B**: Через Docker/композер
```
/opt/shopware/
└── public/          ← ЭТОТ каталог нужен
```

**Вариант C**: Собственная структура
```
/var/www/html/
└── shopware/
    └── public/      ← ЭТОТ каталог нужен
```

### Команды для поиска

Выполните на RU-VPS вручную:

```bash
# Подключитесь к серверу
ssh root@<RU-VPS-IP>

# Поиск Shopware public каталога
find /var/www -name "index.php" -path "*/public/*" 2>/dev/null | grep -i shopware

# Или поиск через конфиг nginx
grep -r "root" /etc/nginx/sites-enabled/ | grep -i shopware

# Проверка стандартных путей
ls -la /var/www/shopware/public/ 2>/dev/null
ls -la /opt/shopware/public/ 2>/dev/null
ls -la /var/www/html/shopware/public/ 2>/dev/null
```

### Результат

Вы должны определить путь вида:
- `/var/www/shopware/public/`
- `/opt/shopware/public/`
- Или другой путь с каталогом `public/`

**Запишите этот путь** - он понадобится дальше.

---

## Шаг 2: Подготовка директорий

### Задача: Создать директории для webhook и логов

Выполните команды на RU-VPS:

```bash
# Создать директорию для webhook.php (внутри public Shopware)
# ЗАМЕНИТЕ /var/www/shopware/public/ на ВАШ путь
mkdir -p /var/www/shopware/public/tbank-webhook

# Создать директорию для логов
mkdir -p /var/log/tbank-webhook-capture

# Установить права
chmod 755 /var/www/shopware/public/tbank-webhook
chmod 755 /var/log/tbank-webhook-capture

# Права для веб-сервера (обычно www-data или nginx)
chown -R www-data:www-data /var/www/shopware/public/tbank-webhook
chown -R www-data:www-data /var/log/tbank-webhook-capture
```

### Проверка

```bash
# Проверить что директории созданы
ls -la /var/www/shopware/public/tbank-webhook/
ls -la /var/log/tbank-webhook-capture/

# Должны увидеть пустые директории с правами 755
```

---

## Шаг 3: Загрузка файла webhook.php

### Задача: Скопировать файл на сервер

**Вариант A: Через SCP (с локальной машины Windows)**

На локальной машине (Windows PowerShell или Git Bash):

```bash
# Перейти в директорию проекта
cd C:\cursor_project\biretos-automation

# Загрузить файл на сервер
scp tbank-webhook-capture/webhook.php root@<RU-VPS-IP>:/var/www/shopware/public/tbank-webhook/
```

**Вариант B: Через прямую загрузку на сервере**

На RU-VPS:

```bash
# Создать файл через nano/vi
nano /var/www/shopware/public/tbank-webhook/webhook.php
```

Скопируйте содержимое из `tbank-webhook-capture/webhook.php` (локально) и вставьте в редактор.

Сохраните файл (в nano: `Ctrl+O`, `Enter`, `Ctrl+X`).

### Установка прав

```bash
# Установить права на файл
chmod 644 /var/www/shopware/public/tbank-webhook/webhook.php
chown www-data:www-data /var/www/shopware/public/tbank-webhook/webhook.php
```

### Проверка

```bash
# Проверить что файл на месте
ls -la /var/www/shopware/public/tbank-webhook/webhook.php

# Должен показать:
# -rw-r--r-- 1 www-data www-data ... webhook.php
```

---

## Шаг 4: Проверка PHP и веб-сервера

### Задача: Убедиться что PHP работает

```bash
# Проверить версию PHP
php -v

# Должна быть версия 7.4+ или 8.0+

# Проверить PHP-FPM статус
systemctl status php8.1-fpm
# или
systemctl status php-fpm

# Если не запущен, запустить
systemctl start php8.1-fpm
systemctl enable php8.1-fpm
```

### Проверка веб-сервера

```bash
# Проверить nginx статус
systemctl status nginx

# Если не запущен
systemctl start nginx
systemctl enable nginx

# Проверить конфигурацию
nginx -t
```

---

## Шаг 5: Определение домена/URL

### Задача: Узнать публичный URL для webhook

**Вариант A: Shopware доступен по домену**

Если Shopware доступен по адресу: `https://shop.example.ru`

Тогда webhook будет доступен по: `https://shop.example.ru/tbank-webhook/webhook.php`

**Вариант B: Shopware доступен по IP**

Если Shopware доступен по адресу: `http://192.168.1.100`

Тогда webhook будет доступен по: `http://192.168.1.100/tbank-webhook/webhook.php`

### Определение текущего домена

```bash
# Посмотреть nginx конфигурацию
cat /etc/nginx/sites-enabled/default | grep server_name

# Или все конфиги
grep -r "server_name" /etc/nginx/sites-enabled/

# Результат покажет домен, например:
# server_name shop.example.ru;
```

**Запишите полный URL** для webhook (будет нужен в кабинете Т-Банка).

---

## Шаг 6: Тестирование endpoint

### Задача: Проверить что webhook доступен

**Тест 1: Локально на сервере**

```bash
# Проверить что файл существует и доступен
curl -X POST http://localhost/tbank-webhook/webhook.php \
  -H "Content-Type: application/json" \
  -d '{"test": "payload"}'

# Ожидаемый ответ:
# {"status":"ok","received_at":"2025-01-15T10:30:00+03:00"}
```

**Тест 2: Проверка method guard**

```bash
# GET запрос должен вернуть 405
curl -X GET http://localhost/tbank-webhook/webhook.php

# Ожидаемый ответ:
# {"error":"Method not allowed"}
# HTTP код: 405
```

**Тест 3: Снаружи (с локальной машины или другого сервера)**

Если webhook доступен по `https://shop.example.ru/tbank-webhook/webhook.php`:

```bash
# С локальной машины
curl -X POST https://shop.example.ru/tbank-webhook/webhook.php \
  -H "Content-Type: application/json" \
  -d '{"test": "payload"}'

# Должен вернуть: {"status":"ok","received_at":"..."}
```

### Проверка логов

```bash
# Проверить что запись появилась в логе
tail -1 /var/log/tbank-webhook-capture/payload_*.jsonl

# Должна быть строка JSON с вашим тестовым payload
```

---

## Шаг 7: Регистрация webhook в кабинете Т-Банка

### Задача: Зарегистрировать URL в личном кабинете Т-Банка

**Инструкция для кабинета Т-Банка:**

1. Войдите в личный кабинет Т-Банка (бизнес-кабинет)
2. Найдите раздел "Интеграции" / "API" / "Webhooks"
3. Нажмите "Добавить webhook" / "Настроить webhook"

**Параметры для заполнения:**

- **URL webhook**: 
  ```
  https://shop.example.ru/tbank-webhook/webhook.php
  ```
  (Замените на ВАШ URL из Шага 5)

- **HTTP Method**: 
  ```
  POST
  ```

- **Content-Type**:
  ```
  application/json
  ```

- **События** (если есть выбор):
  ```
  invoice-paid
  ```
  или
  ```
  Оплата счёта
  ```

**Важно:**
- URL должен быть доступен извне (не localhost)
- URL должен начинаться с `https://` (или `http://` если SSL не настроен)
- После сохранения Т-Банк может отправить тестовый webhook

---

## Шаг 8: Проверка получения webhook

### Задача: Убедиться что webhook от Т-Банка доходит

**После регистрации в кабинете Т-Банка:**

1. Дождитесь тестового webhook (может прийти сразу или в течение нескольких минут)
2. Проверьте логи:

```bash
# Смотреть логи в реальном времени
tail -f /var/log/tbank-webhook-capture/payload_*.jsonl

# Или посмотреть последние записи
cat /var/log/tbank-webhook-capture/payload_*.jsonl | tail -5 | jq
```

**Что должно быть в логе:**

```json
{
  "timestamp": "2025-01-15T10:30:00+03:00",
  "headers": {
    "Host": "shop.example.ru",
    "Content-Type": "application/json",
    "Authorization": "Bearer ...",
    "User-Agent": "T-Bank-Webhook/1.0"
  },
  "body": {
    "invoice_id": "INV-12345",
    "status": "PAID",
    ...
  },
  "raw_body": "{...}",
  "method": "POST",
  "uri": "/tbank-webhook/webhook.php",
  "remote_addr": "192.0.2.100"
}
```

### Чеклист успешного получения

- [ ] Файл лога создан: `/var/log/tbank-webhook-capture/payload_YYYY-MM-DD.jsonl`
- [ ] В логе есть запись с `invoice_id`
- [ ] В логе есть `status: "PAID"` (или другой статус)
- [ ] Headers содержат `Authorization` или другой токен
- [ ] `remote_addr` содержит IP адрес Т-Банка (не localhost)

---

## Шаг 9: Анализ payload

### Задача: Сохранить пример payload для анализа

```bash
# Сохранить пример payload в отдельный файл
cat /var/log/tbank-webhook-capture/payload_*.jsonl | jq '.[0]' > ~/tbank-webhook-payload-example.json

# Или скопировать последнюю запись
tail -1 /var/log/tbank-webhook-capture/payload_*.jsonl | jq > ~/tbank-webhook-payload-example.json
```

**Что проверить в payload:**

1. **Структура данных:**
   - Есть ли поле `invoice_id`?
   - Есть ли поле `status`?
   - Какие ещё поля есть в `body`?

2. **Headers:**
   - Есть ли `Authorization` заголовок?
   - Какой формат токена?

3. **Формат данных:**
   - JSON валидный?
   - Есть ли вложенные объекты (`payer`, `recipient`, `items`)?

**Сохраните файл `tbank-webhook-payload-example.json`** - он понадобится для настройки v2 gateway.

---

## Шаг 10: Удаление v0.1 (после получения payload)

### Задача: Удалить временный receiver

**После того как payload получен и проанализирован:**

```bash
# Удалить файл webhook
rm /var/www/shopware/public/tbank-webhook/webhook.php

# Удалить директорию (если больше не нужна)
rmdir /var/www/shopware/public/tbank-webhook

# Удалить логи (опционально, можно оставить для справки)
rm -rf /var/log/tbank-webhook-capture/
```

**Важно:** 
- Удаляйте только ПОСЛЕ получения payload
- Сохраните пример payload перед удалением
- Не удаляйте, если планируете тестировать дальше

---

## Troubleshooting

### Проблема: 404 Not Found

**Причина**: Неправильный путь к файлу

**Решение**:
```bash
# Проверить что файл существует
ls -la /var/www/shopware/public/tbank-webhook/webhook.php

# Проверить nginx конфигурацию
nginx -t
systemctl reload nginx
```

### Проблема: 500 Internal Server Error

**Причина**: Ошибка PHP или недостаточные права

**Решение**:
```bash
# Проверить логи PHP
tail -f /var/log/php8.1-fpm.log
# или
tail -f /var/log/nginx/error.log

# Проверить права
ls -la /var/www/shopware/public/tbank-webhook/webhook.php
chmod 644 /var/www/shopware/public/tbank-webhook/webhook.php
```

### Проблема: Лог не создаётся

**Причина**: Недостаточные права на директорию логов

**Решение**:
```bash
# Проверить права
ls -la /var/log/tbank-webhook-capture/

# Исправить права
chmod 755 /var/log/tbank-webhook-capture/
chown www-data:www-data /var/log/tbank-webhook-capture/

# Проверить fallback логирование
tail -f /var/log/syslog | grep TBANK-WEBHOOK
```

### Проблема: Webhook не приходит от Т-Банка

**Причина**: Неправильный URL или недоступность endpoint

**Решение**:
1. Проверить что URL доступен снаружи: `curl -X POST <URL>`
2. Проверить что URL указан правильно в кабинете Т-Банка
3. Проверить что webhook активирован в кабинете Т-Банка
4. Связаться с поддержкой Т-Банка для проверки

---

## Где заканчивается зона Cursor

✅ **Cursor завершил:**
- Создание файла `webhook.php` с правками v0.1
- Создание документации

👤 **Пользователь выполняет ВРУЧНУЮ:**
- Все шаги из этого чеклиста (Шаги 1-10)
- Определение структуры Shopware
- Создание директорий
- Загрузка файла на сервер
- Настройка nginx (если нужно)
- Тестирование endpoint
- Регистрация webhook в кабинете Т-Банка
- Мониторинг получения webhook
- Анализ payload

---

## Следующие шаги (после получения payload)

После успешного получения payload:

1. Сохранить пример payload
2. Удалить v0.1 receiver
3. Использовать пример payload для настройки валидаторов в v2 gateway
4. Развернуть v2 gateway согласно `../tbank-webhook-gateway/DEPLOYMENT.md`
5. Обновить URL в кабинете Т-Банка на v2 endpoint









# ChatGPT USA Route - Обратимая маршрутизация через USA VPS

## Что это

Полностью обратимая схема маршрутизации трафика `chatgpt.com` через USA VPS (X-Ray) для улучшения стабильности и latency, с диагностикой ДО/ПОСЛЕ и автоматическим rollback.

## Архитектура

```
Локальный ПК
  ├─ X-Ray Client (порт 10808)
  │   ├─ Routing: chatgpt.com/*.chatgpt.com/*.openai.com → USA VPS
  │   ├─ Routing: остальное → direct
  │   └─ DNS: 1.1.1.1 через X-Ray для проксируемых доменов
  │
  └─ Браузер (Chrome/Edge)
      └─ Proxy: 127.0.0.1:10808 (только для chatgpt.com)

USA VPS (216.9.227.124)
  └─ X-Ray Server
      ├─ Inbound: VLESS от локального ПК
      └─ Outbound: direct к chatgpt.com
```

## Быстрый старт

1. **Настройка конфигурации:**
   Скрипт `enable_chatgpt_usa.ps1` автоматически проверит наличие `.env` файла. Если его нет, создайте его на основе `.env.example` в директории `net_diag_chatgpt/`.

2. **Включение USA Route:**
   ```powershell
   .\net_diag_chatgpt\enable_chatgpt_usa.ps1
   ```
   Скрипт подготовит конфиги и выведет инструкции. По умолчанию НЕ запускает X-Ray автоматически (только подготовка).

3. **Диагностика ДО/ПОСЛЕ:**
   ```powershell
   python net_diag_chatgpt\run_all.py --mode both
   ```
   Результаты сохраняются в `net_diag_chatgpt/reports/<timestamp>/`

4. **Откат:**
   ```powershell
   .\net_diag_chatgpt\rollback_chatgpt_usa.ps1
   ```

## Структура файлов

- `configs/` - Шаблоны X-Ray конфигов (с плейсхолдерами)
- `diagnostics/` - Модули диагностики (TCP RTT, TLS, DNS leak, HTTP timing, WebSocket, Playwright HAR, Idle TCP)
- `reports/` - Результаты диагностики (JSON + Markdown)
- `.runtime/` - Сгенерированные конфиги (не в git)
- `run_all.py` - Главный runner диагностики
- `enable_chatgpt_usa.ps1` - Скрипт включения USA Route
- `rollback_chatgpt_usa.ps1` - Скрипт отката

## Диагностика

### Метрики

Диагностика измеряет следующие метрики:

1. **TCP RTT** - Время установки TCP соединения (connect, appconnect)
2. **TLS Handshake** - Время TLS handshake
3. **DNS Leak** - Проверка утечки DNS (какой resolver используется)
4. **HTTP Timing** - DNS lookup, connect, SSL, TTFB, total time
5. **WebSocket Stability** - Стабильность WebSocket соединений (опционально)
6. **Browser HAR** - Сбор HAR через Playwright (опционально, без логина)
7. **Idle TCP Stability** - Стабильность idle TCP соединений

### Режимы запуска

- `--mode direct` - Только direct (без proxy)
- `--mode proxy` - Только через proxy
- `--mode both` - Оба режима с сравнением (по умолчанию)

### Формат результатов

Каждый тест возвращает структуру:
```json
{
  "name": "tcp_rtt",
  "status": "SUCCESS|FAIL|ERROR",
  "metrics": {
    "connect_ms": 45.2,
    "appconnect_ms": 120.5
  },
  "details": "...",
  "ts": "2025-01-15T10:30:00Z",
  "mode": "direct|proxy"
}
```

Результаты сохраняются в:
- `report.json` - Полный JSON отчет
- `report.md` - Markdown отчет с таблицей сравнения

## Интерпретация результатов

### Успех (SUCCESS)

- **TCP RTT**: Снижение на 50%+ (например, с 150ms до 50ms)
- **TLS Handshake**: Снижение на 40%+
- **HTTP Timing**: Снижение TTFB на 50%+
- **DNS Leak**: Нет утечки (DNS через X-Ray)
- **Стабильность**: Нет разрывов соединений

### Провал (FAIL)

- **RTT не улучшился**: Остался >100ms или увеличился
- **DNS Leak**: Обнаружена утечка DNS
- **Разрывы соединений**: Частые переподключения
- **Cloudflare блокировки**: 403/429 ошибки (возможен детект прокси)

### Ошибка (ERROR)

- **Недоступен X-Ray**: Proxy не отвечает
- **Отсутствуют утилиты**: openssl, curl не найдены
- **Сетевые ошибки**: Таймауты, connection refused

## Rollback

Rollback выполняется одним скриптом:

```powershell
.\net_diag_chatgpt\rollback_chatgpt_usa.ps1
```

Скрипт:
1. Восстанавливает backup конфигов (если были)
2. Останавливает X-Ray (если был запущен через enable)
3. Очищает временные файлы

**Важно**: Rollback работает только в пределах проекта. Если X-Ray был запущен вручную вне проекта, его нужно остановить отдельно.

## Deterministic Checkpoints

Каждый тест возвращает детерминированный статус:

- **SUCCESS** - Тест выполнен успешно, метрики получены
- **FAIL** - Тест выполнен, но результат неудовлетворительный (например, RTT не улучшился)
- **ERROR** - Тест не выполнен из-за ошибки (недоступен proxy, отсутствуют утилиты)

Статусы сохраняются в JSON отчете и могут быть использованы для автоматической оценки улучшения.

## Browser Proxy Launch

Для использования USA Route в браузере:

1. Запустите X-Ray с конфигом из `.runtime/xray-client-usa.json`
2. Настройте браузер на использование SOCKS5 proxy `127.0.0.1:10808`

**Важно**: Это НЕ меняет системный VPN. Proxy работает только для трафика, который браузер отправляет через указанный proxy. Остальной трафик идет напрямую.

## DNS Strategy

DNS для проксируемых доменов (`chatgpt.com`, `*.chatgpt.com`, `*.openai.com`) резолвится через X-Ray DNS (1.1.1.1), что предотвращает DNS leak. Остальные домены резолвятся через системный DNS.

## IPv6 Leak Protection

X-Ray конфиги настроены на использование IPv4 для проксируемых доменов (domainStrategy: UseIPv4), что предотвращает утечку через IPv6.

## Интеграция с существующими скриптами

- Переиспользован `infrastructure/safe-run/Start-Xray.ps1` для безопасного запуска X-Ray
- Переиспользована логика из `measure_rtt.ps1` для измерения RTT
- Использованы существующие X-Ray конфиги из `infrastructure/vpn-bridge/` как шаблон

## Требования

- Python 3.7+ (для run_all.py)
- curl (для HTTP/TCP тестов)
- openssl (для TLS тестов, опционально)
- Playwright (опционально, для HAR сбора)

## Безопасность

- Все секреты (UUID, ключи) хранятся в `.env` (не в git)
- Конфиги с плейсхолдерами в `configs/`, реальные конфиги генерируются в `.runtime/`
- `.runtime/` и `reports/` добавлены в `.gitignore`

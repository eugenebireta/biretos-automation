# Инструкция по деплою windmill-core-v1 (remote-async)

Документ описывает, как Cursor и человек запускают контракты деплоя для модулей `ru_worker` и `webhook_service` с учётом Crash-Safe Execution.

## 1. Контракты и пути

| Модуль | Локальный контракт | Удалённый runtime |
| --- | --- | --- |
| ru_worker | `C:\cursor_project\biretos-automation\.cursor\windmill-core-v1\ru_worker\deploy.sh` | `/opt/biretos/windmill-core-v1/ru_worker` |
| webhook_service | `C:\cursor_project\biretos-automation\.cursor\windmill-core-v1\webhook_service\deploy.sh` | `/opt/biretos/windmill-core-v1/webhook_service` |

Оба `deploy.sh`:
- ведут лог `deploy.log` и статус `deploy.status.json` прямо в каталоге модуля на сервере,
- поддерживают команды `start | poll | resume`,
- выполняют backup → install → restart → verify строго на VPS (никакого `ssh/scp` внутри скрипта).

## 2. Автоматический деплой (Cursor)

1. **Delivery:** Cursor запускает `infrastructure/scripts/Invoke-SafeScp.ps1` и копирует изменённые файлы в целевой `/opt/...` каталог.
2. **Start:** через `Invoke-SafeSsh.ps1` выполняется `cd /opt/.../<module> && bash deploy.sh start`.
3. **Async:** скрипт уходит в фон, пишет PID и лог. Cursor не держит SSH-сессию.
4. **Polling:** каждые ≤5 секунд Cursor выполняет `bash deploy.sh poll`, читает JSON-статус + `tail -n 5 deploy.log`.
5. **Crash-Resume:** новая сессия всегда начинает с `bash deploy.sh resume` и продолжает поллинг, пока `status` не станет `completed` или `failed`.
6. **Acceptance:** при `completed` Cursor запускает финальный UI-тест (Telegram) и ждёт подтверждения.

## 3. Ручной запуск (fallback)

1. Подключитесь к серверу: `ssh root@216.9.227.124` (пароль `HuPtNj39`, если нет ключа).
2. Перейдите в каталог модуля:
   - `cd /opt/biretos/windmill-core-v1/ru_worker`
   - `cd /opt/biretos/windmill-core-v1/webhook_service`
3. Команды:

```bash
bash deploy.sh start   # асинхронный запуск
bash deploy.sh poll    # текущий статус + tail
bash deploy.sh resume  # то же, что poll (для новой сессии)
tail -n 20 deploy.log  # подробнее, если нужно
```

Если при `poll`/`resume` видите `"status": "failed"`, изучите `deploy.log`, восстановитесь из бэкапа (см. ниже) и повторите `bash deploy.sh start`.

## 4. Проверки после деплоя

### ru_worker (`/opt/biretos/windmill-core-v1/ru_worker`)
- Процесс: `pgrep -f 'ru_worker.py'`
- Логи: `tail -n 50 ru_worker.log`
- Telegram-пошагово:
  1. Откройте бота → `/invoices`
  2. Выберите оплаченный счёт → кнопка «📦 Создать накладную»
  3. Ожидается: `✅ Накладная создана` + трек-номер

### webhook_service (`/opt/biretos/windmill-core-v1/webhook_service`)
- Health: `curl -sf http://localhost:8001/health` → `{"status":"healthy"}`
- Логи: `tail -n 50 webhook_service.log`
- Telegram-бизнес-флоу должен продолжать отдавать ответы из webhook (Cursor напомнит в Acceptance).

## 5. Откат

Оба скрипта создают бэкап каталога `<module>_backup_<timestamp>` рядом с рабочей папкой.

```bash
cd /opt/biretos/windmill-core-v1
pkill -f "python.*ru_worker.py" || true            # или main.py.*webhook_service
rm -rf ru_worker && mv ru_worker_backup_<ts> ru_worker
cd ru_worker && nohup python3 ru_worker.py > ru_worker.log 2>&1 &
```

Для webhook_service замените имена на `webhook_service`.

## 6. Частые проблемы

| Симптом | Действие |
| --- | --- |
| `ModuleNotFoundError` | `pip3 install -r requirements.txt` выполняется в шаге `install`. Если ошибка осталась, выполните `pip3 install <lib>` прямо в каталоге и перезапустите `bash deploy.sh start`. |
| `Health endpoint не отвечает` | Проверьте `curl -v http://localhost:8001/health`, изучите `webhook_service.log`, убедитесь, что порт не занят (например, `lsof -i :8001`). |
| Подключение к PostgreSQL | Проверяйте `echo $POSTGRES_HOST/$POSTGRES_PORT/...` на сервере, обновляйте `.env`, перезапускайте контракт. |
| ru_worker не стартует | Выполните `python3 ru_worker.py` вручную, соберите stacktrace, исправьте код и перезапустите контракт. |

## 7. Резюме

- Любой деплой → `bash deploy.sh start` → `poll/resume` до конца.
- Никаких длинных SSH-сессий; вся диагностика через status/log.
- После `completed` обязателен реальный UI-тест в Telegram.


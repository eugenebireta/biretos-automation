# Uptime-мониторинг biretos.ae

Инструкция по настройке внешнего мониторинга доступности сервисов для быстрого обнаружения падений.

## Рекомендуемый сервис: UptimeRobot

[UptimeRobot](https://uptimerobot.com) — бесплатный план (50 мониторов, интервал 5 минут).

## Шаги настройки

1. Зарегистрируйтесь на https://uptimerobot.com
2. Добавьте мониторы (Add New Monitor):

| URL | Тип | Интервал |
|-----|-----|----------|
| `https://biretos.ae/` | HTTP(s) | 5 минут |
| `https://biretos.ae/webhook/telegram` | HTTP(s) — HEAD | 5 минут |
| `https://n8n.biretos.ae` | HTTP(s) | 5 минут |

3. Настройте алерты:
   - Email при падении
   - Опционально: Telegram-бот (Create Alert Contact → Telegram)

## Альтернативы

- **Better Uptime** — https://betteruptime.com
- **Pingdom** — https://www.pingdom.com (платный)
- **StatusCake** — https://www.statuscake.com

## Рекомендуемые пороги

- Интервал проверки: 5 минут
- Порог перед алертом: 2–3 неудачных проверки подряд (снижает ложные срабатывания при кратковременных сбоях)

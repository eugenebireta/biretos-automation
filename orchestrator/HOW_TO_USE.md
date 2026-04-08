# Как пользоваться Meta Orchestrator

## Что это

Робот, который сам берёт задачу, думает что делать, проверяет безопасность, и выполняет.

## 3 режима работы

### 1. Ручной (по умолчанию)

Ты сам говоришь оркестратору что делать:

```
# Шаг 1: Записать задачу
python orchestrator/main.py init --force

# Шаг 2: Открыть orchestrator/manifest.json и написать:
#   current_sprint_goal = "что сделать"
#   current_task_id = "любой ID"

# Шаг 3: Запустить один цикл
python orchestrator/main.py

# Шаг 4: Он напечатает directive. Скормить Claude Code:
cat orchestrator/orchestrator_directive.md | claude -p
```

### 2. Авто-выполнение (одна задача)

Оркестратор сам запускает Claude Code:

```
# В orchestrator/config.yaml поставь:
auto_execute: true

# Запусти:
python orchestrator/main.py

# Он сам: подумает → напишет directive → запустит claude -p → проверит результат
```

### 3. На таймере (cron)

Оркестратор крутится каждые 10 минут:

```
# Вариант А: двойной клик
orchestrator/start_cron.bat

# Вариант Б: из терминала
python orchestrator/cron_runner.py

# Вариант В: каждые 5 минут
python orchestrator/cron_runner.py --interval 300
```

## Как поставить задачу

Открой `orchestrator/manifest.json` и впиши:

```json
{
  "current_sprint_goal": "Добавить тест для price_pipeline",
  "current_task_id": "TASK-123",
  "fsm_state": "ready"
}
```

Оркестратор сам:
1. Классифицирует риск (LOW / SEMI / CORE)
2. Спросит Claude API что делать
3. Проверит безопасность (7 правил)
4. Если LOW — выполнит сам
5. Если SEMI/CORE — остановится и попросит тебя

## Где смотреть что происходит

| Файл | Что там |
|------|---------|
| `orchestrator/manifest.json` | Текущее состояние |
| `orchestrator/orchestrator_directive.md` | Последняя директива |
| `orchestrator/runs.jsonl` | Лог всех запусков |
| `orchestrator/cron.log` | Лог cron-runner |
| `orchestrator/last_advisor_verdict.json` | Что сказал Claude API |
| `orchestrator/last_execution_packet.json` | Что получилось |

## Как остановить

- **Cron**: Ctrl+C в окне терминала (или закрыть окно)
- **Задачу**: поставь `"fsm_state": "completed"` в manifest.json
- **Всё**: поставь `auto_execute: false` в config.yaml

## Защита

- **LOW задачи**: выполняет сам, проверяет batch gate
- **SEMI задачи**: выполняет, но НЕ мёржит (нужен твой ОК)
- **CORE задачи**: останавливается и зовёт аудиторов (Gemini + Claude Opus)
- **Tier-1 файлы**: НИКОГДА не трогает (frozen)
- **Тесты сломались**: останавливается (batch gate G4)

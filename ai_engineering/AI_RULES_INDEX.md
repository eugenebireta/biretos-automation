# 📚 AI Rules Index — Canonical Entry Point

**СТАТУС:** Канонический entry point для всей системы AI-правил проекта Biretos Automation.

**НАЗНАЧЕНИЕ:** Этот файл является **ЕДИНСТВЕННОЙ АРХИТЕКТУРНОЙ ТОЧКОЙ ВХОДА** для понимания всей системы AI-правил, механизмов и их иерархии.

**ОБЯЗАТЕЛЬНОСТЬ:** Любой новый файл правил ОБЯЗАН быть добавлен в этот индекс. Нарушение считается архитектурной ошибкой.

---

## Иерархия документов

### Мета-уровень (Architectural Foundation)

**SOURCE OF TRUTH для иерархии механизмов:**
- `ai_engineering/MECHANISM_HIERARCHY.md`
  - Определяет PRIMARY/SECONDARY/OBSERVER для каждой области логики
  - Запрещает создание дублирующих механизмов
  - Обязательный gate для всех новых механизмов

**SOURCE OF TRUTH для архитектурных принципов:**
- `ai_engineering/ARCHITECTURE_GUIDE.md`
  - 18 инженерных принципов
  - Архитектурные ограничения
  - Протоколы взаимодействия

**SOURCE OF TRUTH для контекста:**
- `ai_engineering/CONTEXT_RULES.md`
  - Controlled Context Mode
  - Запрет автоматического расширения контекста

**Главная точка загрузки:**
- `ai_engineering/ask_autoload.txt`
  - Автоматически включает все правила через @include
  - Загружается через `.cursorrules`

---

## Структурированная карта правил

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Validation of Plan Structure

| Файл | Роль | Описание |
|------|------|----------|
| `plan_sanitizer_rules.txt` | **PRIMARY** | Валидация структуры планов от ASK (пронумерованные шаги, атомарность, макс. 5 шагов) |
| `agent_safety_executor.txt` (раздел 1) | SECONDARY | Проверка структуры плана перед AGENT |
| `agent_behavior_rules.txt` | OBSERVER | Правила выполнения, не валидирует структуру |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Controlled Context Enforcement

| Файл | Роль | Описание |
|------|------|----------|
| `CONTEXT_RULES.md` | **PRIMARY** | Определение Controlled Context Mode |
| `ask_context_wrapper.txt` | **PRIMARY** | Обёртка контекста для ASK |
| `plan_sanitizer_rules.txt` (раздел 3) | SECONDARY | Контроль областей в планах |
| `agent_safety_executor.txt` (раздел 3) | SECONDARY | Проверка Controlled Context Mode |
| `agent_behavior_rules.txt` (правило 3) | SECONDARY | Запрет сканирования проекта |
| `ask_behavior_rules.txt` (правило 4) | OBSERVER | Напоминание о запрете сканирования |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Risk Assessment / Fail-Safe

| Файл | Роль | Описание |
|------|------|----------|
| `agent_safety_executor.txt` (разделы 5-6) | **PRIMARY** | Оценка риска шагов, блокировка при нарушениях, Fail-Safe Mode |
| `plan_sanitizer_rules.txt` (раздел 7) | SECONDARY | Помечает рискованные шаги как "Needs Clarification" |
| `agent_behavior_rules.txt` (правило 6) | OBSERVER | Запрос подтверждения при опасности |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Loop Detection

| Файл | Роль | Описание |
|------|------|----------|
| `loop_protection_rules.txt` | **PRIMARY** | Обнаружение признаков loop, мягкая коррекция, context refresh |
| `self_reflection_kernel.txt` | OBSERVER | Может заметить повторения в ответах, но не блокирует loop в планах |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Pre-Execution Safety

**5.1. Проверка окружения (Environment/Infrastructure):**

| Файл | Роль | Описание |
|------|------|----------|
| `preflight_check_rules.txt` | **PRIMARY** | Проверка env, ключей, инфраструктуры, автопоиск ключей, гигиена `_scratchpad` |

**5.2. Проверка плана и рисков (Plan/Risk Validation):**

| Файл | Роль | Описание |
|------|------|----------|
| `agent_safety_executor.txt` (разделы 1-6) | **PRIMARY** | Проверка плана перед выполнением, оценка риска, Fail-Safe Mode, прозрачность |

| Файл | Роль | Описание |
|------|------|----------|
| `agent_behavior_rules.txt` | SECONDARY | Правила выполнения в AGENT, но не проверяет перед выполнением |
| `error_protocol_trigger.txt` | OBSERVER | Срабатывает при ошибках, но не предотвращает выполнение |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Error Handling / Emergency Protocol

| Файл | Роль | Описание |
|------|------|----------|
| `error_protocol_trigger.txt` | **PRIMARY** | **ВЫСШИЙ ПРИОРИТЕТ:** "overrides all other instincts. No exceptions." |
| `autonomous_debug_rules.txt` (раздел 0, раздел 2) | **PRIMARY** | Emergency Protocol, автономный debug loop, максимум 3 попытки |
| `AI_ISSUES_LOG.md` | OBSERVER | Журнал проблем, используется Emergency Protocol для поиска решений |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Config Validation

| Файл | Роль | Описание |
|------|------|----------|
| `infrastructure/agent-tools/Lint-ConfigFiles.ps1` | **PRIMARY** | Валидация JSON, проверка BOM/CRLF в WireGuard/CONF |
| `autonomous_debug_rules.txt` (раздел 1.7) | SECONDARY | Требует запуск валидатора перед развёртыванием |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: SSH/SCP Safety

| Файл | Роль | Описание |
|------|------|----------|
| `infrastructure/scripts/Invoke-SafeSsh.ps1` | **PRIMARY** | Безопасная обёртка SSH с таймаутами, логированием, BatchMode |
| `infrastructure/scripts/Invoke-SafeScp.ps1` | **PRIMARY** | Безопасная обёртка SCP с таймаутами, логированием |
| `agent_behavior_rules.txt` (правило 15) | SECONDARY | Запрет прямых вызовов ssh/scp |
| `autonomous_debug_rules.txt` (раздел 1.8) | SECONDARY | Список запрещённых команд |
| `ask_autoload.txt` (строки 19-33) | SECONDARY | Критическое правило сетевой безопасности |
| `infrastructure/agent-tools/Validate-SshUsage.ps1` | OBSERVER | Проверяет логи на нарушение, но не блокирует |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Background Process Safety

| Файл | Роль | Описание |
|------|------|----------|
| `infrastructure/safe-run/Start-Xray.ps1` | **PRIMARY** | Безопасный запуск Xray через Start-Process |
| `infrastructure/safe-run/Start-SSH-Tunnel.ps1` | **PRIMARY** | Безопасный запуск SSH-туннеля |
| `infrastructure/safe-run/Check-Tunnel.ps1` | **PRIMARY** | Проверка состояния туннеля |
| `agent_behavior_rules.txt` (правило 15) | SECONDARY | Запрет прямых вызовов xray/wireguard |
| `ask_autoload.txt` (строки 19-33) | SECONDARY | Критическое правило |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Question Filtering / No-Nagging

| Файл | Роль | Описание |
|------|------|----------|
| `clarification_filter_rules.txt` | **PRIMARY** | Фильтрация вопросов ASK, определение когда вопросы запрещены/разрешены |
| `no_nagging_policy.txt` | **PRIMARY** | Политика без вопросов, правило вероятности (≥0.8) |
| `intent_expansion_rules.txt` | SECONDARY | Умеренное предугадывание, когда не уточнять |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Self-Correction / Reflection

| Файл | Роль | Описание |
|------|------|----------|
| `self_reflection_kernel.txt` | **PRIMARY** | Самокоррекция поведения AI, проверка качества ответов, корректировка будущих ответов |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: ASK Behavior

| Файл | Роль | Описание |
|------|------|----------|
| `ask_behavior_rules.txt` | **BEHAVIOR** | Правила поведения ASK: формирование плана, запрос подтверждения, запрет выполнения |
| `ask_context_wrapper.txt` | **BEHAVIOR** | Обёртка контекста для ASK, Controlled Context Mode |
| `intent_expansion_rules.txt` | **BEHAVIOR** | Расширение намерений пользователя, умеренное предугадывание |
| `clarification_filter_rules.txt` | **BEHAVIOR** | Фильтрация вопросов ASK |
| `no_nagging_policy.txt` | **BEHAVIOR** | Политика без вопросов |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: AGENT Behavior

| Файл | Роль | Описание |
|------|------|----------|
| `agent_behavior_rules.txt` | **BEHAVIOR** | Правила выполнения в AGENT: только указанные изменения, атомарность, идемпотентность, запрет терминальных операций |
| `agent_safety_executor.txt` | **BEHAVIOR** | Проверка плана перед выполнением, оценка риска, блокировка при нарушениях |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Personality / Style

| Файл | Роль | Описание |
|------|------|----------|
| `personality_rules.txt` | **STYLE** | Стиль общения: интеллектуальный партнёр, предугадывание, Shift Expectations |
| `smooth_interaction_rules.txt` | **STYLE** | Плавность общения, профессиональный тон, высокая информационная плотность |
| `AI_WORKSTYLE_GUIDE.md` | **STYLE** | Стиль работы: интеллектуальный партнёр, автономность, минимализация вопросов |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Knowledge / Learning

| Файл | Роль | Описание |
|------|------|----------|
| `AI_ISSUES_LOG.md` | **KNOWLEDGE** | Журнал проблем и решений, используется Emergency Protocol |
| `AI_LEARNING_MEMO.md` | **KNOWLEDGE** | Память обучения, ключевые паттерны, история обучения |
| `key_vault_map.txt` | **KNOWLEDGE** | Карта расположения ключей и секретов |

---

### ЛОГИЧЕСКАЯ ОБЛАСТЬ: Templates / Utilities

| Файл | Роль | Описание |
|------|------|----------|
| `auto_context_template.txt` | **TEMPLATE** | Шаблон автозагрузки контекста |
| `infrastructure/config/servers.json` | **CONFIG** | Конфигурация серверов для SSH/SCP |

---

## Порядок применения правил

### Этап ASK (планирование)

1. **Pre-Flight Check** (`preflight_check_rules.txt`) — проверка окружения
2. **Controlled Context** (`CONTEXT_RULES.md`, `ask_context_wrapper.txt`) — ограничение контекста
3. **Question Filtering** (`clarification_filter_rules.txt`, `no_nagging_policy.txt`) — фильтрация вопросов
4. **Intent Expansion** (`intent_expansion_rules.txt`) — расширение намерений
5. **Plan Sanitizer** (`plan_sanitizer_rules.txt`) — валидация структуры плана
6. **Loop Protection** (`loop_protection_rules.txt`) — обнаружение циклов
7. **MECHANISM_HIERARCHY.md** — проверка новых механизмов

### Этап PLAN (санитизация)

1. **Plan Sanitizer** (`plan_sanitizer_rules.txt`) — проверка структуры, областей, рисков
2. **Loop Protection** (`loop_protection_rules.txt`) — повторная проверка циклов
3. **MECHANISM_HIERARCHY.md** — проверка новых механизмов в плане

### Этап AGENT (выполнение)

**Перед выполнением:**
1. **Agent Safety Executor** (`agent_safety_executor.txt`) — проверка плана, оценка риска
2. **Loop Protection** (`loop_protection_rules.txt`) — финальная проверка циклов
3. **MECHANISM_HIERARCHY.md** — проверка новых механизмов в шагах

**Во время выполнения:**
1. **Agent Behavior Rules** (`agent_behavior_rules.txt`) — правила выполнения
2. **Error Protocol** (`error_protocol_trigger.txt`) — при ошибках (высший приоритет)
3. **Autonomous Debug Rules** (`autonomous_debug_rules.txt`) — автономный debug loop

---

## Критические правила приоритета

1. **Error Protocol** — абсолютный приоритет: "overrides all other instincts. No exceptions."
2. **MECHANISM_HIERARCHY.md** — обязательная проверка перед созданием любого механизма
3. **Controlled Context** — запрет автоматического расширения контекста
4. **Pre-Flight Check** — обязателен перед формированием плана

---

## Обязательное правило обновления индекса

**КРИТИЧЕСКОЕ ПРАВИЛО:** Любой новый файл правил, созданный в `ai_engineering/`, ОБЯЗАН быть добавлен в этот индекс (`AI_RULES_INDEX.md`).

**Процесс добавления:**
1. Определить логическую область нового файла
2. Определить роль (PRIMARY / SECONDARY / OBSERVER / BEHAVIOR / STYLE / KNOWLEDGE / TEMPLATE / CONFIG)
3. Добавить запись в соответствующую таблицу выше
4. Если файл является PRIMARY — обновить также `MECHANISM_HIERARCHY.md`

**Нарушение:** Создание файла правил без добавления в этот индекс считается архитектурной ошибкой.

---

## Связанные документы

- `ai_engineering/MECHANISM_HIERARCHY.md` — SOURCE OF TRUTH для иерархии механизмов
- `ai_engineering/ARCHITECTURE_GUIDE.md` — SOURCE OF TRUTH для архитектурных принципов
- `ai_engineering/CONTEXT_RULES.md` — SOURCE OF TRUTH для Controlled Context Mode
- `.cursorrules` — главная точка загрузки через `ask_autoload.txt`

---

## Статус документа

- **Версия:** 1.0
- **Дата создания:** 2025-12-11
- **Статус:** Канонический entry point для системы AI-правил
- **Обновление:** Обязательно при добавлении любого нового файла правил

---

== END AI_RULES_INDEX ==




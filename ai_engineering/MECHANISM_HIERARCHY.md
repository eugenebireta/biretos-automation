# 🏛 Mechanism Hierarchy — Architectural Rules

Этот документ фиксирует **обязательную архитектурную иерархию** механизмов проекта для исключения повторного создания логики.

**СТАТУС:** Обязательное правило проекта. Все новые механизмы должны следовать этой иерархии.

---

## Принцип SOURCE OF TRUTH

Для каждой области логики существует **один PRIMARY механизм** (SOURCE OF TRUTH), который является главным и определяющим. Все остальные механизмы являются SECONDARY (вспомогательными) или OBSERVER (наблюдающими, не блокирующими).

**КРИТИЧЕСКОЕ ПРАВИЛО:** Если механизм обозначен как PRIMARY для области логики, создание нового механизма в этой области **ЗАПРЕЩЕНО**.

---

## Иерархия механизмов по областям логики

### 1. Validation of Plan Structure

**PRIMARY (SOURCE OF TRUTH):**
- `ai_engineering/plan_sanitizer_rules.txt`
  - Применяется ко всем планам, сформированным ASK
  - Проверяет структуру (пронумерованные шаги, атомарность)
  - Запрещает абстрактные шаги
  - Контролирует минимальность (макс. 5 шагов)

**SECONDARY:**
- `ai_engineering/agent_safety_executor.txt` (раздел 1: проверка структуры перед AGENT)

**OBSERVER:**
- `ai_engineering/agent_behavior_rules.txt` (правила выполнения, не валидирует структуру)

**ЗАПРЕТ:** Не создавать новые механизмы проверки структуры плана. Plan Sanitizer — единственный SOURCE OF TRUTH для структуры планов от ASK.

---

### 2. Controlled Context Enforcement

**PRIMARY (SOURCE OF TRUTH):**
- `ai_engineering/CONTEXT_RULES.md`
- `ai_engineering/ask_context_wrapper.txt`
  - Определяет правило Controlled Context Mode
  - Запрещает автоматическое расширение контекста
  - Запрещает сканирование проекта

**SECONDARY:**
- `ai_engineering/plan_sanitizer_rules.txt` (раздел 3: контроль областей, запрет действий вне указанных файлов)
- `ai_engineering/agent_safety_executor.txt` (раздел 3: проверка Controlled Context Mode)
- `ai_engineering/agent_behavior_rules.txt` (правило 3: запрет сканирования проекта)

**OBSERVER:**
- `ai_engineering/ask_behavior_rules.txt` (правило 4: напоминание о запрете сканирования)

**ЗАПРЕТ:** Не дублировать правило Controlled Context в новых файлах. CONTEXT_RULES.md — единственный SOURCE OF TRUTH.

---

### 3. Risk Assessment / Fail-Safe

**PRIMARY (SOURCE OF TRUTH):**
- `ai_engineering/agent_safety_executor.txt` (разделы 5-6)
  - Оценивает риск шагов
  - Блокирует выполнение при нарушении правил
  - Fail-Safe Mode с указанием нарушений

**SECONDARY:**
- `ai_engineering/plan_sanitizer_rules.txt` (раздел 7: помечает рискованные шаги как "Needs Clarification", требует подтверждение)

**OBSERVER:**
- `ai_engineering/agent_behavior_rules.txt` (правило 6: запрос подтверждения при опасности, но не оценивает риск)

**ЗАПРЕТ:** Не создавать новые механизмы оценки риска. Agent Safety Executor — единственный SOURCE OF TRUTH для оценки риска перед выполнением.

---

### 4. Loop Detection

**PRIMARY (SOURCE OF TRUTH):**
- `ai_engineering/loop_protection_rules.txt`
  - Обнаруживает признаки loop (повторяющиеся шаги, похожие планы)
  - Мягкая коррекция (soft-corrected)
  - Context refresh при усилении loop

**OBSERVER:**
- `ai_engineering/self_reflection_kernel.txt` (может заметить повторения в ответах, но не блокирует loop в планах)

**ЗАПРЕТ:** Не создавать новые механизмы обнаружения циклов. Loop Protection — единственный SOURCE OF TRUTH для обнаружения и предотвращения циклов.

---

### 5. Pre-Execution Safety

**PRIMARY (SOURCE OF TRUTH):**
- `ai_engineering/preflight_check_rules.txt`
  - Проверка env, ключей, инфраструктуры перед выполнением
  - Автопоиск ключей
  - Отчёт о Pre-Flight
  - Гигиена `_scratchpad`

- `ai_engineering/agent_safety_executor.txt` (разделы 1-6)
  - Проверка плана перед выполнением в AGENT
  - Принцип прозрачности (вывод очищенного плана, ожидание подтверждения)

**SECONDARY:**
- `ai_engineering/agent_behavior_rules.txt` (правила выполнения в AGENT, но не проверяет перед выполнением)

**OBSERVER:**
- `ai_engineering/error_protocol_trigger.txt` (срабатывает при ошибках, но не предотвращает выполнение)

**ЗАПРЕТ:** Не создавать новые механизмы предвыполнительной проверки. Pre-Flight — SOURCE OF TRUTH для проверки окружения. Agent Safety Executor — SOURCE OF TRUTH для проверки плана.

---

### 6. Error Handling / Emergency Protocol

**PRIMARY (SOURCE OF TRUTH):**
- `ai_engineering/error_protocol_trigger.txt`
  - **ВЫСШИЙ ПРИОРИТЕТ:** "overrides all other instincts. No exceptions."
  - Срабатывает при любой ошибке инструмента
  - Требует чтение `AI_ISSUES_LOG.md` перед повторной попыткой

- `ai_engineering/autonomous_debug_rules.txt` (раздел 0: Emergency Protocol, раздел 2: стандартный цикл debug)
  - Максимум 3 попытки исправления
  - Автономный debug loop

**OBSERVER:**
- `ai_engineering/AI_ISSUES_LOG.md` (журнал проблем, используется Emergency Protocol для поиска решений)

**ЗАПРЕТ:** Не создавать новые механизмы обработки ошибок. Error Protocol — SOURCE OF TRUTH с высшим приоритетом, переопределяет все остальные инстинкты.

---

### 7. Config Validation

**PRIMARY (SOURCE OF TRUTH):**
- `infrastructure/agent-tools/Lint-ConfigFiles.ps1`
  - Валидация JSON (структура через `python -m json.tool`)
  - Проверка WireGuard/CONF (BOM, CRLF)
  - Обязательный запуск перед развёртыванием

**SECONDARY:**
- `ai_engineering/autonomous_debug_rules.txt` (раздел 1.7: требует запуск валидатора перед развёртыванием)

**ЗАПРЕТ:** Не создавать новые валидаторы конфигов. Lint-ConfigFiles.ps1 — единственный SOURCE OF TRUTH для валидации конфигурационных файлов.

---

### 8. SSH/SCP Safety

**PRIMARY (SOURCE OF TRUTH):**
- `infrastructure/scripts/Invoke-SafeSsh.ps1`
- `infrastructure/scripts/Invoke-SafeScp.ps1`
  - Безопасные обёртки с таймаутами
  - Централизованный конфиг (`servers.json`)
  - Логирование в `_scratchpad/ssh_activity.log`
  - BatchMode для SSH

**SECONDARY:**
- `ai_engineering/agent_behavior_rules.txt` (правило 15: запрет прямых вызовов ssh/scp)
- `ai_engineering/autonomous_debug_rules.txt` (раздел 1.8: список запрещённых команд)
- `ai_engineering/ask_autoload.txt` (строки 19-33: критическое правило сетевой безопасности)

**OBSERVER:**
- `infrastructure/agent-tools/Validate-SshUsage.ps1` (проверяет логи на нарушение, но не блокирует)

**ЗАПРЕТ:** Не создавать новые обёртки для SSH/SCP. Invoke-SafeSsh/Invoke-SafeScp — единственный SOURCE OF TRUTH для безопасного SSH/SCP.

---

### 9. Background Process Safety

**PRIMARY (SOURCE OF TRUTH):**
- `infrastructure/safe-run/Start-Xray.ps1`
- `infrastructure/safe-run/Start-SSH-Tunnel.ps1`
- `infrastructure/safe-run/Check-Tunnel.ps1`
  - Безопасный запуск фоновых процессов через Start-Process
  - Предотвращение deadlock в tool protocol

**SECONDARY:**
- `ai_engineering/agent_behavior_rules.txt` (правило 15: запрет прямых вызовов xray/wireguard)
- `ai_engineering/ask_autoload.txt` (строки 19-33: критическое правило)

**ЗАПРЕТ:** Не создавать новые скрипты для запуска фоновых процессов. safe-run/*.ps1 — единственный SOURCE OF TRUTH для безопасного запуска фоновых процессов.

---

### 10. Question Filtering / No-Nagging

**PRIMARY (SOURCE OF TRUTH):**
- `ai_engineering/clarification_filter_rules.txt`
  - Фильтрация вопросов ASK
  - Определяет, когда вопросы запрещены/разрешены

- `ai_engineering/no_nagging_policy.txt`
  - Политика без вопросов
  - Правило вероятности (≥0.8 — делать действие)

**SECONDARY:**
- `ai_engineering/intent_expansion_rules.txt` (умеренное предугадывание, когда не уточнять)

**ЗАПРЕТ:** Не создавать новые механизмы фильтрации вопросов. Clarification Filter + No-Nagging Policy — единственный SOURCE OF TRUTH для управления вопросами ASK.

---

### 11. Self-Correction / Reflection

**PRIMARY (SOURCE OF TRUTH):**
- `ai_engineering/self_reflection_kernel.txt`
  - Самокоррекция поведения AI
  - Проверка качества ответов (длина, вода, структура)
  - Корректировка будущих ответов

**ЗАПРЕТ:** Не создавать новые механизмы самокоррекции. Self-Reflection Kernel — единственный SOURCE OF TRUTH для самокоррекции стиля и качества ответов.

---

## Reuse-First Rule

### Обязательное правило использования существующих механизмов

**ПРАВИЛО:** Если механизм уже существует и обозначен как PRIMARY для области логики, создание нового механизма в этой области **СТРОГО ЗАПРЕЩЕНО**.

### Допустимые действия

1. **Использование существующего механизма:**
   - Ссылаться на PRIMARY механизм в документации
   - Вызывать PRIMARY механизм в коде/скриптах
   - Расширять функциональность PRIMARY механизма (если это не создаёт дублирование)

2. **Создание SECONDARY механизма:**
   - Допускается только если PRIMARY механизм явно требует вспомогательной логики
   - SECONDARY механизм должен ссылаться на PRIMARY как SOURCE OF TRUTH
   - SECONDARY механизм не должен дублировать логику PRIMARY

3. **Создание OBSERVER механизма:**
   - Допускается для мониторинга и сигнализации
   - OBSERVER не должен блокировать или изменять поведение PRIMARY
   - OBSERVER должен явно указывать, что он является наблюдателем

### Запрещённые действия

1. **Создание нового PRIMARY механизма:**
   - Если для области логики уже существует PRIMARY механизм
   - Даже если новый механизм "лучше" или "оптимизированнее"
   - Даже если новый механизм решает "другую задачу" в той же области

2. **Дублирование логики:**
   - Копирование проверок из PRIMARY в новый файл
   - Создание "альтернативной" реализации той же логики
   - Разделение одного механизма на несколько без явной необходимости

3. **Создание "улучшенной версии":**
   - Замена существующего PRIMARY механизма новым
   - Создание "v2" или "improved" версии без удаления старого
   - Параллельное существование двух PRIMARY механизмов для одной области

### Процесс добавления нового механизма

Перед созданием нового механизма **ОБЯЗАТЕЛЬНО:**

1. Проверить таблицу иерархии выше
2. Определить область логики, к которой относится новый механизм
3. Проверить, существует ли PRIMARY механизм для этой области
4. Если PRIMARY существует:
   - **ОТКАЗАТЬСЯ** от создания нового механизма
   - Использовать существующий PRIMARY механизм
   - Если нужна дополнительная функциональность — расширить PRIMARY (не создавать новый)
5. Если PRIMARY не существует:
   - Создать новый PRIMARY механизм
   - **НЕМЕДЛЕННО** обновить этот документ, добавив новый механизм в таблицу
   - Обозначить его как PRIMARY (SOURCE OF TRUTH)

---

## Критические правила приоритета

### Правило 1: Error Protocol — высший приоритет

`error_protocol_trigger.txt` имеет **абсолютный приоритет**:
- "overrides all other instincts. No exceptions."
- Все остальные механизмы должны учитывать это правило
- При любой ошибке инструмента Error Protocol срабатывает первым

### Правило 2: Порядок применения

1. **ASK этап:**
   - Plan Sanitizer (валидация плана)
   - Loop Protection (обнаружение циклов в плане)
   - Pre-Flight Check (проверка окружения)

2. **AGENT этап (перед выполнением):**
   - Agent Safety Executor (проверка плана перед выполнением)
   - Loop Protection (повторная проверка перед выполнением)

3. **Во время выполнения:**
   - Agent Behavior Rules (правила выполнения)
   - Error Protocol (при ошибках — немедленно)

### Правило 3: Запрет на изменение PRIMARY

PRIMARY механизмы **НЕ ДОЛЖНЫ** изменяться без явной необходимости:
- Изменения должны быть задокументированы
- Изменения не должны нарушать совместимость с SECONDARY механизмами
- Изменения должны быть согласованы с архитектурными принципами

---

## Обязательная проверка перед созданием механизмов

### Архитектурный Gate для ASK / PLAN / AGENT

**КРИТИЧЕСКОЕ ПРАВИЛО:** Перед предложением ЛЮБОГО нового механизма (validation, safety, guard, protocol, enforcement, preflight, compliance, rules checking и т.д.) ИИ ОБЯЗАН проверить этот документ (`ai_engineering/MECHANISM_HIERARCHY.md`).

### Формулировка запрета

**"Если PRIMARY механизм существует — создание нового запрещено."**

Это правило применяется на всех этапах:
- **ASK:** перед формированием плана с новым механизмом
- **PLAN:** при санитизации плана, содержащего создание нового механизма
- **AGENT:** перед выполнением шага по созданию нового механизма

### Статус нарушения

**Нарушение этого правила считается архитектурной ошибкой** и приводит к:
- Блокировке плана (для PLAN/AGENT)
- Требованию переформулировки (для ASK)
- Обязательной ссылке на существующий PRIMARY механизм

### Процесс проверки

1. **Обнаружение намерения создать механизм:**
   - ИИ обнаруживает в запросе/плане намерение создать новый механизм
   - ИИ ОБЯЗАН немедленно проверить MECHANISM_HIERARCHY.md

2. **Проверка существования PRIMARY:**
   - Определить область логики нового механизма
   - Проверить таблицу иерархии выше
   - Найти PRIMARY механизм для этой области (если существует)

3. **Действие при существовании PRIMARY:**
   - **ОТКАЗАТЬСЯ** от создания нового механизма
   - Использовать существующий PRIMARY механизм
   - Ссылаться на PRIMARY в документации/плане
   - Если нужна дополнительная функциональность — расширить PRIMARY (не создавать новый)

4. **Действие при отсутствии PRIMARY:**
   - Создать новый PRIMARY механизм
   - **НЕМЕДЛЕННО** обновить этот документ, добавив новый механизм в таблицу
   - Обозначить его как PRIMARY (SOURCE OF TRUTH)

---

## Обязательные ссылки

Все новые файлы правил должны ссылаться на этот документ:

```markdown
# Правила [название]

См. также: `ai_engineering/MECHANISM_HIERARCHY.md` для определения роли этого механизма в архитектуре.
```

---

## Обновление документа

Этот документ должен обновляться **НЕМЕДЛЕННО** при:
- Создании нового PRIMARY механизма (добавить в таблицу)
- Изменении роли существующего механизма (обновить статус)
- Обнаружении дублирования логики (зафиксировать запрет)

**Ответственность:** Любой, кто создаёт или изменяет механизмы в `ai_engineering/`, обязан обновить этот документ.

---

## Статус документа

- **Версия:** 1.0
- **Дата создания:** 2025-12-11
- **Статус:** Обязательное правило проекта
- **Связанные документы:**
  - `ai_engineering/ARCHITECTURE_GUIDE.md`
  - `ai_engineering/CONTEXT_RULES.md`
  - `.cursorrules`

---

== END MECHANISM_HIERARCHY ==




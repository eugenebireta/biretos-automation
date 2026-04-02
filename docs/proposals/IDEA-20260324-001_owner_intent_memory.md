# IDEA-20260324-001 — Owner Intent Memory / Jarvis Context Layer

> **Status:** DRAFT
> **INBOX entry:** `docs/IDEA_INBOX.md` → IDEA-20260324-001
> **Risk class:** SEMI
> **Created:** 2026-03-24

---

## 1. Problem / Context

Каждый новый разговор с AI-ассистентом (Claude Code, ChatGPT, Weekly Planner)
начинается с нуля. Владелец вынужден повторять:
- текущие приоритеты и активные задачи,
- контекст недавних решений,
- роли и SOP для текущего этапа,
- стратегические гипотезы и открытые вопросы.

Это manual overhead — прямое нарушение North Star ("минимизировать manual_interventions").

Кроме того, Business Memory Vault (Этап 19) и TD-034..TD-038 уже зарезервированы
в плане, но не детализированы. Без детальной проработки они рискуют остаться
пустыми ячейками в момент реализации.

---

## 2. Why Now

- Текущая фаза: Post-Core Freeze, активный Revenue (Tier-3).
- Claude Code сессии участились — overhead на re-contextualization растёт.
- TD-034..TD-038 назначены на "Review: Этап 19", но Этап 19 — далеко.
  Документная база нужна уже сейчас, чтобы фиксировать intent по ходу работы.
- Появилась практика работы с несколькими AI-клиентами (Claude Code + ChatGPT Judge).
  Нужен единый источник правды об owner intent, а не разрозненные промпты.

---

## 3. Relation to Master Plan / Roadmap / DNA

### Прямые связи

| Элемент | Связь |
|---------|-------|
| **Этап 19: Business Memory Vault** | Это и есть implementation scope для данной идеи |
| **TD-034: Owner Context Profile** | Один из core entities ниже |
| **TD-035: Active Work Threads Continuity** | Один из core entities ниже |
| **TD-036: SOP Memory Registry** | Один из core entities ниже |
| **TD-037: Role-Based Retrieval Profiles** | Consumer-layer этой идеи |
| **TD-038: Strategy / Hypothesis Memory** | Один из core entities ниже |
| **Business Memory Vault** (Cognitive Layer) | Физическое место хранения |
| **COGNITIVE LAYER** (Local PC, NO side-effects) | Архитектурная зона размещения |
| **North Star: минимизировать manual_interventions** | Прямая мотивация |
| **Decision Snapshot / Re-processing** | Принцип: memory читается, не мутирует Core |

### Что НЕ затрагивается

- Frozen Files (DNA §3) — не касается.
- Pinned API (DNA §4) — не касается.
- Reconciliation / Guardian / Core FSM — не касается.
- Master Plan и Roadmap — **не меняются** на этапе DRAFT.

---

## 4. Goals

1. Создать persistent memory layer, где фиксируется owner intent в структурированном виде.
2. Обеспечить чтение этого layer из Claude Code, ChatGPT и Weekly Planner без ручного copy-paste.
3. Сократить время re-contextualization в начале AI-сессии с ~5-10 мин до ~0.
4. Дать детальный контент для TD-034..TD-038, чтобы они не остались пустыми ячейками.
5. Создать документную основу (этот proposal) до написания кода.

---

## 5. Non-Goals

- Не создавать новый AI-агент или оркестратор.
- Не мутировать Core tables из memory layer.
- Не реализовывать автоматическое обновление memory (только owner-driven writes на DRAFT этапе).
- Не заменять CLAUDE.md, STATE.md, MASTER_PLAN — они остаются источниками правды.
- Не строить RAG/vector store на DRAFT этапе — начинаем с plain-text структурированных файлов.

---

## 6. Core Entities / Concepts

### 6.1 Owner Context Profile (← TD-034)

Статичный профиль владельца: роль, горизонт, ключевые приоритеты, стиль работы.
Обновляется редко (раз в несколько недель).

```
owner_context_profile.md
  - current_role: "Builder + Operator"
  - planning_horizon: "3-6 months"
  - current_focus: [список из 3-5 пунктов]
  - working_style: [...]
  - preferred_AI_interaction: [...]
```

### 6.2 Active Work Threads (← TD-035)

Реестр активных задач / треков, которые не завершены.
Владелец добавляет/закрывает треды явно.

```
active_threads.md
  - thread_id: "rev-r1-catalog"
    status: "IN_PROGRESS"
    last_action: "..."
    next_step: "..."
    context: "..."
```

### 6.3 SOP Memory Registry (← TD-036)

Каталог стандартных операционных процедур. Ссылки на SOP-файлы + краткое описание.
AI-ассистент читает этот реестр, чтобы знать "как мы делаем X".

```
sop_registry.md
  - sop_id: "COMMIT_WORKFLOW"
    file: "docs/howto/WORKFLOW_NOW.md"
    summary: "..."
    applies_when: "..."
```

### 6.4 Strategy / Hypothesis Memory (← TD-038)

Фиксирует стратегические гипотезы и открытые вопросы, которые влияют на решения.
Не замена Roadmap, а рабочий слой гипотез между сессиями.

```
strategy_hypotheses.md
  - hypothesis_id: "H-001"
    statement: "..."
    status: "OPEN / VALIDATED / INVALIDATED"
    evidence: "..."
    impact_on: [Этап 14, TD-042]
```

### 6.5 Role-Based Retrieval Profiles (← TD-037)

Описание того, какие части memory layer нужны каждому AI-клиенту.
Claude Code читает одно подмножество, ChatGPT Judge — другое.

```
retrieval_profiles.md
  - client: "claude-code"
    reads: [owner_context_profile, active_threads, sop_registry]
    format: "compact"
  - client: "chatgpt-judge"
    reads: [active_threads, strategy_hypotheses]
    format: "full"
```

---

## 7. Consumers

| Клиент | Что читает | Когда |
|--------|-----------|-------|
| **Claude Code** | Context Profile + Active Threads + SOP Registry | Начало каждой сессии |
| **ChatGPT (Judge / Weekly Planner)** | Active Threads + Strategy Hypotheses | Weekly review, Judge submissions |
| **AI Assistant (NLU layer, Этап 7+)** | Role Profiles + SOP Registry | При обработке входящих запросов |
| **Owner** | Всё | Review и update |

---

## 8. Data Sources

| Источник | Что поставляет |
|---------|---------------|
| `docs/autopilot/STATE.md` | Текущий статус проекта (читается, не дублируется) |
| `docs/MASTER_PLAN_v1_9_2.md` | Стратегические приоритеты (читается, не дублируется) |
| `docs/EXECUTION_ROADMAP_v2_3.md` | Активные этапы (читается, не дублируется) |
| `docs/IDEA_INBOX.md` | Активные идеи на проработке |
| **Owner input (manual)** | Гипотезы, приоритеты, треды — владелец пишет явно |
| Git log / commit messages | Косвенный источник для Active Threads |

**Принцип:** memory layer **читает** авторитетные документы, но **не дублирует** их.
Хранит только то, чего нет в авторитетных источниках: рабочий intent владельца.

---

## 9. Constraints

1. **Cognitive Layer only.** Business Memory Vault размещается на Local PC.
   Никаких side-effects, никаких записей в Core tables.
2. **Read-only от Core.** Memory layer может читать Core через read-only views или файлы,
   но не пишет в Core.
3. **Plain-text first.** На начальном этапе — Markdown файлы. Никаких баз данных.
   Vector store / RAG — только после подтверждения ценности (TD-037 Review gate).
4. **Owner-driven updates.** На DRAFT этапе обновляет только владелец.
   Автоматическое обновление — отдельная фича, в scope DRAFT не входит.
5. **No new FSM.** Memory — это key-value / документы. Никаких state machines.
6. **Не замена CLAUDE.md.** CLAUDE.md остаётся источником правды для Claude Code rules.
   Memory layer добавляет рабочий контекст поверх правил.

---

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Memory устаревает и вводит AI в заблуждение | Средняя | Высокий | Явная дата "last_updated" на каждом файле; AI-инструкция проверять свежесть |
| Дублирование с STATE.md / MASTER_PLAN | Средняя | Средний | Четкое разграничение: memory хранит только рабочий intent, не стратегию |
| Scope creep: "добавим RAG, vector store, автообновление" | Высокая | Средний | Явные Non-Goals; расширение только через IDEA_INBOX |
| Owner забывает обновлять треды | Высокая | Средний | Weekly review hook; short-form формат тредов |
| Конфликт с NLU/Phase 7 architecture | Низкая | Высокий | Согласовать с NLU ownership rules перед реализацией |

---

## 11. Promotion Options

### Option A (рекомендуемый) — Детализировать TD-034..TD-038 + sub-stage Этапа 19

1. Расширить описание TD-034..TD-038 в MASTER_PLAN с ссылкой на этот proposal.
2. Добавить в EXECUTION_ROADMAP под Этап 19 подэтапы:
   - 19.1: Owner Context Profile + Active Threads (plain-text MVP)
   - 19.2: SOP Registry + Strategy Hypotheses
   - 19.3: Role-Based Retrieval Profiles + multi-client читалка
3. Создать `docs/memory/` директорию с шаблонами файлов (без данных).

### Option B — Минимальный патч

Добавить ссылку на этот proposal в MASTER_PLAN внутри TD-034..TD-038 без изменения roadmap.
Реализовать как standalone набор Markdown файлов в `docs/memory/` без формального этапа.

### Option C — Отложить до Этапа 18

Зафиксировать в INBOX как `PARKED`. Вернуться, когда Business Intelligence (Этап 18) будет в работе.

---

## 12. Open Questions

1. **Формат Active Threads:** YAML front-matter в Markdown или отдельный YAML файл?
2. **Где физически лежит `docs/memory/`?** В repo (версионировано) или вне repo (приватно)?
   Trade-off: repo = история изменений, но intent попадает в git log.
3. **Как Claude Code загружает memory?** Через CLAUDE.md include? Через отдельный контекстный файл?
4. **Разграничение с `docs/autopilot/STATE.md`:** STATE отражает automation state,
   memory — owner intent. Нужно ли формализовать границу?
5. **Trigger для Weekly Review:** Cron + Claude Code reminder? Ручной процесс?

---

## Review Log

| Date | Reviewer | Status change | Notes |
|------|----------|---------------|-------|
| 2026-03-24 | Claude Code (SCOUT) | INBOX → DRAFT | Proposal создан по запросу owner. Код не написан. |

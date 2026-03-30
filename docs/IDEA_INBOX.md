# IDEA INBOX — Biretos Automation

## Purpose

Реестр крупных идей и инициатив, которые ещё не включены в Master Plan / Roadmap / DNA.
Защищает авторитетные документы от хаотичного расширения.
Обеспечивает трассируемость: идея → proposal → patch в authoritative document.

## Rules

- **Append-only.** Записи не редактируются и не удаляются.
- **Review и promotion** фиксируются как новая запись под идеей (с датой и статусом).
- **Proposal-path** обязателен для идей в статусе `DRAFT` и выше.
- **Promotion** в Master Plan / Roadmap только через явный owner-approve + patch-commit.
- Roadmap Rule 4: новые идеи → сначала сюда → triage → approve → patch в authoritative document.

## Statuses

| Статус    | Значение                                                              |
|-----------|-----------------------------------------------------------------------|
| `INBOX`   | Зафиксирована, не разобрана                                           |
| `DRAFT`   | Proposal-файл создан, проходит проработку                             |
| `REVIEW`  | Proposal готов, ждёт owner-решения                                    |
| `PROMOTE` | Owner одобрил, готовится patch в authoritative document               |
| `MERGED`  | Идея включена в Master Plan / Roadmap / DNA + proposal archived       |
| `PARKED`  | Откладывается без срока (причина зафиксирована в записи)              |
| `DROPPED` | Отклонена (причина зафиксирована в записи)                            |

## Triage Rules

1. Любая идея, требующая изменения архитектуры, нового Этапа или нового TD-*,
   должна получить proposal-файл до начала реализации.
2. Малые уточнения (typo, clarification) можно патчить напрямую — без INBOX.
3. Идеи, затрагивающие Frozen Files (DNA §3) или Pinned API (DNA §4),
   автоматически повышаются до `CORE` и требуют Strict Mode.
4. Proposal без owner-approve не становится частью плана.

---

## Inbox

### IDEA-20260324-001 — Owner Intent Memory / Jarvis Context Layer

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-24                                                                    |
| Статус          | `DRAFT`                                                                       |
| Автор           | Owner                                                                         |
| Связанные TD    | TD-034, TD-035, TD-036, TD-037, TD-038                                        |
| Связанный этап  | Этап 19 (Business Memory Vault)                                               |
| Proposal        | `docs/proposals/IDEA-20260324-001_owner_intent_memory.md`                     |
| Краткое описание | Persistent memory layer для AI-ассистентов: владелец не повторяет контекст каждый раз. Claude Code, ChatGPT, Weekly Planner читают один источник правды об intent'е, активных тредах, SOP, ролях. |

---

### IDEA-20260324-002 — Max Executive Layer (Channel-Agnostic Owner Interface)

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-25                                                                    |
| Статус          | `DRAFT`                                                                       |
| Автор           | Owner                                                                         |
| Связанные TD    | TD-029 (Selective Channel Routing Policy)                                     |
| Связанный этап  | Этап 7 (NLU foundation) → Этап 8+ (evolution)                                |
| Зависит от      | IDEA-20260324-001 (Owner Intent Memory)                                       |
| Proposal        | `docs/proposals/IDEA-20260324-002_max_executive_layer.md`                     |
| Краткое описание | Channel-agnostic owner assistant layer. Max = primary UX. Telegram = fallback/alerts/export. Voice-first capture. Decouples NLU engine from delivery channel. |

---

### IDEA-20260324-003 — Personal Scheduler (Owner-Focused Planning Engine)

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-25                                                                    |
| Статус          | `DRAFT`                                                                       |
| Автор           | Owner                                                                         |
| Связанные TD    | TD-031 (косвенно), кандидат на TD-049                                         |
| Связанный этап  | Этап 8.4 (Cognitive Load tracking) → Этап 19 (Business Memory)               |
| Зависит от      | IDEA-20260324-001 (Owner Intent Memory — prerequisite)                        |
| Proposal        | `docs/proposals/IDEA-20260324-003_personal_scheduler.md`                      |
| Краткое описание | Owner planning engine: task ingestion, strategic/tactical + urgent/not-urgent classification, next best action, Today/This Week/Backlog buckets, morning plan, reminders, reschedule. Logic layer — НЕ интерфейс. |

---

### IDEA-20260324-004 — Synthetic Bot E2E / Integration Validation Layer

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-25                                                                    |
| Статус          | `DRAFT`                                                                       |
| Автор           | Owner                                                                         |
| Связанные TD    | TD-031 (Local Debug & Regression Lab — прямая связь)                         |
| Связанный этап  | Этап 8.1 / Этап 8.3 (Shadow Mode gate)                                       |
| Proposal        | `docs/proposals/IDEA-20260324-004_synthetic_bot_e2e.md`                       |
| Краткое описание | Synthetic validation layer для NLU/Task Engine. MessageInjector, WebhookSimulator, CallbackSimulator, TranscriptCapture, ShadowRunner. НЕ autoclikker. DRY_RUN only. Local PC, zero side-effects. Telegram now, Max later. |


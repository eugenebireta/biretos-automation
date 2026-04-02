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

---

### IDEA-20260325-005 — Ozon FBO/FBS Integration Worker

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-25                                                                    |
| Статус          | `INBOX`                                                                       |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | Кандидат на новый Этап (Revenue Tier-3, после Этапа 8)                       |
| Proposal        | —                                                                             |
| Краткое описание | Интеграция с Ozon Seller API: выгрузка отчётов FBO/FBS по отправлениям, синхронизация статусов заказов Ozon с основным order ledger. Источник: legacy-скрипт `legacy_scripts/ozon/ozon_reports.py`, найденный при аудите старого ПК. |

---

### IDEA-20260325-006 — Autonomy Layer (Phase 5-6 Vision)

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-25                                                                    |
| Статус          | `INBOX`                                                                       |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | После Stability Gate (за пределами текущего Roadmap)                         |
| Proposal        | —                                                                             |
| Краткое описание | Архитектурный вектор из Master Plan v1.3 (найден при аудите старого ПК). Phase 5: Decision Pattern Mining (governance_decisions → auto-approve rules, human confirms), Correction Learning (AI classifier → CorrectionRecord → dataset update), Autonomy KPI Dashboard (цель 90%+ решений без человека). Phase 6: Proactive Operations — предиктивные алерты по остаткам/SLA, Auto-Reorder с подтверждением, Client Intelligence (паттерны заказов, client scoring), Process Optimization (анализ bottleneck'ов). Три уровня learning: Correction (Phase 3) → Operational (Phase 5) → Process (Phase 6). Железный принцип: система предлагает — человек подтверждает. Self-modifying поведение без human confirmation ЗАПРЕЩЕНО. |

---

### IDEA-20260325-007 — Pricing Tiers & Ozon Акции Logic

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-25                                                                    |
| Статус          | `INBOX`                                                                       |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | Кандидат на Этап Catalog/Pricing (Revenue Tier-3)                            |
| Proposal        | —                                                                             |
| Краткое описание | Бизнес-логика скидок из операционных заметок (аудит старого ПК): 3 уровня liquidation скидок — 60% (безнадёга: кронштейны и т.п.), 40% (средне), 20% (лайт). Ozon акции: 40% на товары с платным размещением + конверсия <2% + доля оборота 100%; 20% по рекомендации Ozon на снижение цен; 40% на товары на вывоз по рекомендации Ozon. Интеграция через ВПР → акции. Полезно при построении автоматизации ценообразования и управления стоком. |

---

### IDEA-20260325-008 — Industrial Lot Evaluation Automation

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-25                                                                    |
| Статус          | `INBOX`                                                                       |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | Отдельный трек, не связан с текущим Roadmap                                  |
| Proposal        | —                                                                             |
| Краткое описание | Автоматизация оценки банкротных промышленных лотов по готовым фреймворкам (найдены при аудите старого ПК). Бизнес-модель: покупка электронники/датчиков/контроллеров из банкротных лотов → перепродажа через маркетплейсы. Готовые фреймворки: LOT_FILTER_0 (DATA_PREPARATION) → LOT_FILTER_1 (CAPITAL_COMPOSITION, Hard Gate: A+B≥60%, E≤20%) → LOT_FILTER_2 (CAPITAL_SAFETY) → LOT_FILTER_3 (STRUCTURAL_RANKING) → LOT_FILTER_4 (REALITY_CHECK) → ASYMMETRY. Скоринг GATE+SAFETY(0-40)+STRUCTURE(0-35)+VELOCITY+ASYMMETRY. Вход: Excel лота с SKU/CalculatedLotCost/Qty. Выход: BUY/REVIEW/STOP + балл. Источник: `\\home-pc\c\Users\Eugene\Desktop\оценка лотов 3\` + `Downloads\INDUSTRIAL_LOT_DOCTRINE_v2.md`. |

---

### IDEA-20260331-009 — Provider-agnostic Scout Layer

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | После bounded proof batch                                                     |
| Proposal        | —                                                                             |
| Краткое описание | Discovery contract с единым интерфейсом для любого AI-провайдера. Провайдеры как плагины: Claude, GPT, Gemini, Perplexity. Scout ищет price/photo candidates, deterministic layer проверяет. |

---

### IDEA-20260331-010 — Browser Research Operator

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | После scout pilot                                                             |
| Proposal        | —                                                                             |
| Краткое описание | Anthropic Computer Use как Tier-3 scout для сайтов без API. Read-only, allowlisted domains, no publish. Только для high-value SKU по `margin_threshold`. |

---

### IDEA-20260331-011 — Cost-based Routing

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | После scout pilot                                                             |
| Proposal        | —                                                                             |
| Краткое описание | Эшелон 0 (локальный AI, `$0`) → Эшелон 1 (дешёвый API) → Эшелон 2 (дорогой API). Простые задачи локально, сложные отправляются в облако по cost-aware routing. |

---

### IDEA-20260331-012 — Agent-scalable Execution (TD-048)

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | TD-048                                                                        |
| Связанный этап  | После стабилизации single-agent                                               |
| Proposal        | —                                                                             |
| Краткое описание | `1 orchestrator + N disposable workers + deterministic gate` только для независимых Tier-3 задач. Предусловие: single-agent execution должен стабильно работать. |

---

### IDEA-20260331-013 — Negative Evidence Classes

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | При evidence schema hardening                                                 |
| Proposal        | —                                                                             |
| Краткое описание | First-class negative markers: `for use with`, `same brand wrong family`, `reused photo`, `series page only` для объяснимого отклонения ложных совпадений. |

---

### IDEA-20260331-014 — Enrichment Staleness / TTL Decay

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | После scout pilot                                                             |
| Proposal        | —                                                                             |
| Краткое описание | Если `price_date` старше `N` дней, карточка теряет актуальность и уходит на re-validation вместо бессрочного доверия к старому enrichment output. |

---

### IDEA-20260331-015 — Feedback Loop

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | После scout pilot                                                             |
| Proposal        | —                                                                             |
| Краткое описание | Ручные review decisions логируются и подмешиваются как few-shot examples в scout prompts. Self-improving pipeline допускается только under governance. |

---

### IDEA-20260331-016 — Dual Confidence Scoring

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | При discovery contract design                                                 |
| Proposal        | —                                                                             |
| Краткое описание | Разделить `match_confidence` (правильный ли товар) и `extraction_confidence` (правильно ли извлечена цена/фото), чтобы не смешивать identity и parsing quality. |

---

### IDEA-20260331-017 — Canonical Disposition Classes

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | При disposition hardening                                                     |
| Proposal        | —                                                                             |
| Краткое описание | Конечный реестр классов решений плюс fail-closed fallback вместо комбинаторного роста disposition matrix и ad hoc route explosion. |

---

### IDEA-20260331-018 — Review Queue Prioritization

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | При review queue design                                                       |
| Proposal        | —                                                                             |
| Краткое описание | `review_priority = business_value × publishability × confidence_gap`, чтобы review queue сортировалась по полезности для бизнеса, а не только по arrival order. |

---

### IDEA-20260331-019 — Semantic Leakage Guard

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | При evidence schema hardening                                                 |
| Proposal        | —                                                                             |
| Краткое описание | Принцип: `Discovery ≠ Normalization ≠ Evidence ≠ Acceptance ≠ Disposition`. Candidate не становится evidence без policy gate; при formalization может затронуть `PROJECT_DNA`. |

---

### IDEA-20260331-020 — Shared Product Intelligence Kernel (SPIK)

| Поле            | Значение                                                                      |
|-----------------|-------------------------------------------------------------------------------|
| Дата добавления | 2026-03-31                                                                    |
| Статус          | `PARKED`                                                                      |
| Автор           | Owner                                                                         |
| Связанные TD    | —                                                                             |
| Связанный этап  | После стабилизации R1 enrichment + provider adapter seam                      |
| Proposal        | `docs/proposals/IDEA-SPIK.md`                                                 |
| Краткое описание | Переиспользуемое ядро товарного интеллекта: identity normalization, evidence acquisition, spec extraction, category inference, price observation, image intelligence и unified disposition. Принцип: `one acquisition -> many consumers`; channel adapters остаются вне kernel. |

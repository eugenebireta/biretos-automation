# PromptOps Acceleration Pack v1

> Рекомендованный вход: `docs/promptpacks/ONE_LINER_TASK.md` (минимальный шаблон постановки задачи в Cursor).

## Цель

Убрать ручной копипаст между окнами и вести цикл в одном окне Cursor.  
Контекст подтягивается через `.cursorrules` + `.cursor/rules/*`, а работа идет через короткие role-based шаги с approve-gate.

## Quickstart

### LOW (LOG-LOW)

1) `/risk LOW`  
2) `/arch <задача>`  
3) Проверить scope, сказать `approve`  
4) `/build`  
5) Опционально `/audit`

### SEMI (POLICY-MEDIUM)

1) `/risk SEMI`  
2) `/arch <задача>` → `approve`  
3) `/critic` → исправить замечания → `approve`  
4) `/plan` → `approve`  
5) `/build` → `/audit`

### CORE (CORE-CRITICAL)

1) `/risk CORE`  
2) В Cursor: SCOUT → ARCHITECT → CRITIC  
3) Сформировать пакет `/pack`  
4) Отправить пакет во внешний JUDGE чат  
5) Вернуться в Cursor: PLANNER → BUILDER → AUDITOR (с approve между фазами)

## Risk Router (one-screen)

- 🔴 CORE-CRITICAL: все 7 ролей, JUDGE строго external, без батчинга действий.
- 🟡 SEMI: ARCHITECT → CRITIC → PLANNER → BUILDER → AUDITOR.
- 🟢 LOW: ARCHITECT → BUILDER.

Никогда не батчить:
- Tier-1 freeze.
- DB schema/migrations/DDL.
- Governance/policy packs.
- Новые side-effects.
- Идемпотентность, multi-worker coordination, replay guarantees.

## Когда нужен внешний JUDGE

Только для CORE-CRITICAL задач.  
Причина: независимый вердикт вне контекста Cursor (anti-confirmation-bias).

## Как работает approve-gate

- Каждый шаг завершает ответ маркером ожидания (`WAITING_FOR_APPROVE`).
- Следующая фаза запускается только после явного слова `approve`.
- Без `approve` допускаются только уточнения и корректировка текущей фазы.

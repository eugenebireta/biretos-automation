# WORKFLOW NOW (после PromptOps Pack v1)

## Что изменилось

- Ролевые правила теперь подхватываются через `globs` в `.cursor/rules/roles/*.mdc`.
- Базовые guardrails всегда активны: `risk_router.mdc` и `tier1_frozen.mdc` (`alwaysApply: true`).
- Tier-1 граница больше не дублируется в ролях: единый источник — `PHASE2_BOUNDARY.md` (backup: `PROJECT_DNA.md`).

## Работа по рискам

- LOW: ARCHITECT → (approve) → BUILDER → (audit optional)
- SEMI: ARCHITECT → (approve) → CRITIC → (approve) → PLANNER → (approve) → BUILDER → AUDITOR
- CORE: полный pipeline; JUDGE строго external; в Cursor до JUDGE готовится пакет Architect+Critic

## Как экономится время

- Не нужно каждый раз вручную вставлять длинные правила: контекст подтягивается из `.mdc`.
- Меньше переключений окон для LOW/SEMI: основной цикл идет внутри Cursor.
- Быстрее старт задачи через короткий one-liner вход вместо длинного промпта.

## Approve-gate

`approve` — это дисциплина процесса пользователя и ассистента, а не технический hard-enforcement.

## Что отправлять во внешний JUDGE (CORE)

Короткий пакет:

1) Task + Risk  
2) Architect summary  
3) Critic findings  
4) Boundaries (Tier-1 / migrations / side-effects)  
5) Open questions

## Однострочные постановки (примеры)

- LOW: `RISK: LOW | TASK: обновить docs/howto инструкции по PromptOps | FILES: docs/howto/* | CONSTRAINTS: без runtime/DB изменений`
- SEMI: `RISK: SEMI | TASK: усилить audit-чеклист по инвариантам в docs | FILES: docs/howto/*, docs/promptpacks/* | CONSTRAINTS: one-step + approve-gate`
- CORE: `RISK: CORE | TASK: оценить изменение boundary-политики | FILES: PHASE2_BOUNDARY.md, PROJECT_DNA.md | CONSTRAINTS: JUDGE external only`
